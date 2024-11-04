import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import platformdirs
import sqlite3

from config import Config
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

ARCHIVES_QUERY = """
SELECT DISTINCT archive from files 
"""

FILES_QUERY = """
SELECT archive, file, filesize, ext FROM files where lib_id=? 
"""

FILES_UPDATE = """
INSERT INTO files (lib_id, archive, file, filesize, ext) VALUES (?, ?, ?, ?, ?)
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

        file_db_path = os.path.join(platformdirs.user_cache_dir("flget", ensure_exists=True), "files.db")
        self._file_db = sqlite3.connect(file_db_path)

        # Pre-create tables
        self._file_db.execute(FILES_DDL)
        self._file_db.commit()

    def sync(self, inpx: INPX) -> None:
        self._index.create_index(inpx)
        cur = self._file_db.cursor()
        cur.execute("DELETE FROM files")
        for lib_id, book in inpx.items():
            cur.execute(FILES_UPDATE, (lib_id, book.archive, book.filename, book.filesize, book.ext))
        self._file_db.commit()

    def search_authors(self, query: str) -> list[AuthorEntry]:
        return self._index.search_authors(query)

    def suggest_authors(self, query: str) -> list[AuthorEntry]:
        return self._index.suggest_authors(query)

    def search_books(self, query: str) -> list[BookEntry]:
        return self._index.search_books(query)

    def get(self, book_id: int)-> None:
        book_file = self._file_db.execute(FILES_QUERY, (book_id,)).fetchone()
        zippath = os.path.join(self._config.libdir(), f"{book_file[0]}.zip")
        with zipfile.ZipFile(zippath, "r") as archive:
            archive.extract(f"{book_file[1]}.{book_file[3]}", "/tmp")

    def _count_unknown_archives(self, progress_update: Callable[[float],None]) -> int:
        archives = set(self._file_db.execute(ARCHIVES_QUERY).fetchall())
        unknown_archives = 0
        files_in_lib = list(os.listdir(self._config.libdir()))
        progress = 50.0/float(len(files_in_lib))
        for filename in files_in_lib:
            progress_update(progress)
            if filename.lower().endswith(".zip"):
                if Path(filename.lower()).stem not in archives:
                    unknown_archives += 1
        return unknown_archives

    def _count_unknown_entries(self, progress_update: Callable[[float],None]) -> (int, int):
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
                        if not self._file_db.execute(FILES_QUERY, (file_id,)).fetchone():
                            unknown_entries += 1
        return unknown_entries, missing_archives

    def validate(self, progress_update: Callable[[float],None]) -> MirrorValidationResult:
        unknown_archives = self._count_unknown_archives(progress_update)
        unknown_entries, missing_archives = self._count_unknown_entries(progress_update)
        return MirrorValidationResult(missing_archives, unknown_archives, unknown_entries)