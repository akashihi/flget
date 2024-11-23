import dataclasses
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import platformdirs
import sqlite3

from config import Config
from inpx import SeriesEntry
from inpx import AuthorEntry
from inpx import INPX, BookEntry
from index import BookIndex

FILES_DDL = """
CREATE TABLE IF NOT EXISTS files (
lib_id INTEGER PRIMARY KEY,
archive TEXT NOT NULL,
file TEXT NOT NULL UNIQUE,
filesize INTEGER NOT NULL,
ext TEXT NOT NULL 
)
"""

SERIES_DDL = """
CREATE TABLE IF NOT EXISTS series (
series_id INTEGER NOT NULL ,
lib_id INTEGER NOT NULL,
serno INTEGER NOT NULL,
name TEXT NOT NULL,
FOREIGN KEY(lib_id) REFERENCES files(lib_id),
PRIMARY KEY(series_id, lib_id)
)
"""

AUTHORS_SERIES_DDL = """
CREATE TABLE IF NOT EXISTS authors_series (
author_id INTEGER NOT NULL,
series_id INTEGER NOT NULL,
FOREIGN KEY(series_id) REFERENCES series(series_id),
PRIMARY KEY(author_id, series_id)
)
"""

AUTHORS_BOOKS_DDL = """
CREATE TABLE IF NOT EXISTS authors_books (
author_id INTEGER NOT NULL,
lib_id INTEGER NOT NULL,
FOREIGN KEY(lib_id) REFERENCES files(lib_id),
PRIMARY KEY(author_id, lib_id)
)
"""

ARCHIVES_QUERY = """
SELECT DISTINCT archive from files 
"""

FILES_QUERY = """
SELECT archive, file, filesize, ext FROM files where lib_id=? 
"""

FILES_UPDATE = """
INSERT INTO files (lib_id, archive, file, filesize, ext) VALUES (?, ?, ?, ?, ?)
"""

SERIES_UPDATE = """
INSERT INTO series(series_id, lib_id, serno, name) VALUES (?, ?, ?, ?)
"""

SERIES_QUERY = """
SELECT lib_id FROM series WHERE series_id=? ORDER BY serno ASC
"""

SERIES_NAME_QUERY = """
SELECT DISTINCT name FROM series WHERE series_id=? LIMIT 1
"""

AUTHORS_SERIES_UPDATE = """
INSERT INTO authors_series (author_id, series_id) VALUES (?, ?) ON CONFLICT (author_id, series_id) DO NOTHING
"""

AUTHORS_BOOKS_UPDATE = """
INSERT INTO authors_books (author_id, lib_id) VALUES (?, ?)
"""

AUTHORS_SERIES_QUERY = """
SELECT DISTINCT series_id FROM authors_series WHERE author_id=? 
"""

AUTHORS_BOOKS_QUERY = """
SELECT DISTINCT lib_id FROM authors_books WHERE author_id=? 
"""


@dataclass(frozen=True)
class MirrorValidationResult:
    missing_archives: int
    unknown_archives: int
    unknown_books: int


class TheLibrary:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._index = BookIndex()

        file_db_path = os.path.join(
            platformdirs.user_cache_dir("flget", ensure_exists=True), "files.db"
        )
        self._file_db = sqlite3.connect(file_db_path)

        # Pre-create tables
        self._file_db.execute(FILES_DDL)
        self._file_db.execute(SERIES_DDL)
        self._file_db.execute(AUTHORS_SERIES_DDL)
        self._file_db.execute(AUTHORS_BOOKS_DDL)
        self._file_db.commit()

    def sync(self, inpx: INPX, progress_update: Callable[[float], None]) -> None:
        self._index.create_index(inpx, progress_update)
        cur = self._file_db.cursor()
        cur.execute("DELETE FROM files")
        cur.execute("DELETE FROM series")
        cur.execute("DELETE FROM authors_series")
        cur.execute("DELETE FROM authors_books")

        progress = 50.0 / float(len(inpx.items()))

        for lib_id, book in inpx.items():
            progress_update(progress)
            cur.execute(
                FILES_UPDATE,
                (lib_id, book.archive, book.filename, book.filesize, book.ext),
            )
            series_id = inpx.series_to_id(book.series)
            if series_id:
                cur.execute(SERIES_UPDATE, (series_id, lib_id, book.serno, book.series))
                for author in book.authors:
                    author_id = inpx.author_to_id(author)
                    cur.execute(AUTHORS_SERIES_UPDATE, (author_id, series_id))
            else:
                for author in book.authors:
                    author_id = inpx.author_to_id(author)
                    cur.execute(AUTHORS_BOOKS_UPDATE, (author_id, lib_id))

        self._file_db.commit()

    def search_authors(self, query: str) -> list[AuthorEntry]:
        return self._index.search_authors(query)

    def suggest_authors(self, query: str) -> Optional[str]:
        return self._index.suggest_authors(query)

    def search_series(self, query: str) -> list[SeriesEntry]:
        return self._index.search_series(query)

    def suggest_series(self, query: str) -> Optional[str]:
        return self._index.suggest_series(query)

    def search_books(self, query: str) -> list[BookEntry]:
        return self._index.search_books(query)

    def save(self, book_id: int, target_path: str) -> None:
        book_file = self._file_db.execute(FILES_QUERY, (book_id,)).fetchone()
        zippath = os.path.join(self._config.libdir(), f"{book_file[0]}.zip")
        with zipfile.ZipFile(zippath, "r") as archive:
            archive.extract(f"{book_file[1]}.{book_file[3]}", target_path)

    def _count_unknown_archives(self, progress_update: Callable[[float], None]) -> int:
        archives = set(self._file_db.execute(ARCHIVES_QUERY).fetchall())
        unknown_archives = 0
        files_in_lib = list(os.listdir(self._config.libdir()))
        progress = 50.0 / float(len(files_in_lib))
        for filename in files_in_lib:
            progress_update(progress)
            if filename.lower().endswith(".zip"):
                if Path(filename.lower()).stem not in archives:
                    unknown_archives += 1
        return unknown_archives

    def _count_unknown_entries(
        self, progress_update: Callable[[float], None]
    ) -> Tuple[int, int]:
        archives = set(self._file_db.execute(ARCHIVES_QUERY).fetchall())
        progress = 50.0 / float(len(archives))
        unknown_entries = 0
        missing_archives = 0
        for archive in archives:
            progress_update(progress)
            archive_path = os.path.join(self._config.libdir(), f"{archive[0]}.zip")
            if not Path(archive_path).exists():
                missing_archives += 1
            else:
                with zipfile.ZipFile(archive_path, "r") as zip_archive:
                    for member in zip_archive.namelist():
                        file_id = Path(member).stem
                        if not self._file_db.execute(
                            FILES_QUERY, (file_id,)
                        ).fetchone():
                            unknown_entries += 1
        return unknown_entries, missing_archives

    def validate(
        self, progress_update: Callable[[float], None]
    ) -> MirrorValidationResult:
        unknown_archives = self._count_unknown_archives(progress_update)
        unknown_entries, missing_archives = self._count_unknown_entries(progress_update)
        return MirrorValidationResult(
            missing_archives, unknown_archives, unknown_entries
        )

    def get_books(self, book_ids: list[int]) -> list[BookEntry]:
        books = self._index.get_books(book_ids)
        result = []
        for book in books:
            book_file = self._file_db.execute(FILES_QUERY, (book.lib_id,)).fetchone()
            result.append(dataclasses.replace(
                book,
                filename=book_file[1],
                ext=book_file[3],
                archive=book_file[0],
                filesize=book_file[2],
            ))
        return result

    def get_series_name(self, series_id: int) -> Optional[str]:
        return self._file_db.execute(SERIES_NAME_QUERY, (series_id,)).fetchone()[0]

    def get_series(self, series_id: int) -> list[BookEntry]:
        book_ids = self._file_db.execute(SERIES_QUERY, (series_id,)).fetchall()
        return self.get_books([book_id[0] for book_id in book_ids])

    def get_author_series(self, author_id: int) -> list[int]:
        series_ids = self._file_db.execute(
            AUTHORS_SERIES_QUERY, (author_id,)
        ).fetchall()
        return [s[0] for s in series_ids]

    def get_author_books(self, author_id: int) -> list[BookEntry]:
        book_ids = self._file_db.execute(AUTHORS_BOOKS_QUERY, (author_id,)).fetchall()
        return self.get_books([book_id[0] for book_id in book_ids])
