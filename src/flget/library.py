import dataclasses
import sqlite3
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from flget import naming
from flget.config import Config
from flget.filters import BookFilter
from flget.index import BookIndex
from flget.mirror import AuthorEntry, BookEntry, Mirror, SeriesEntry

# Series larger than this are too generic to be useful in a filename, so the
# series/serno segment is skipped for them.
MAX_SERIES_SIZE = 50

FILES_DDL = """
CREATE TABLE IF NOT EXISTS files (
lib_id INTEGER PRIMARY KEY,
archive TEXT NOT NULL,
file TEXT NOT NULL,
filesize INTEGER NOT NULL,
ext TEXT NOT NULL,
year INTEGER,
original_name INTEGER NOT NULL DEFAULT 0
)
"""

GENRE_TITLES_DDL = """
CREATE TABLE IF NOT EXISTS genre_titles (
code TEXT PRIMARY KEY,
title TEXT NOT NULL
)
"""

# Separate from files to keep search fast(er?)
BOOK_DIGEST_DDL = """
CREATE TABLE IF NOT EXISTS book_digest (
lib_id INTEGER PRIMARY KEY,
annotation TEXT NOT NULL DEFAULT '',
reviews TEXT NOT NULL DEFAULT ''
)
"""

COVERS_DDL = """
CREATE TABLE IF NOT EXISTS covers (
lib_id INTEGER PRIMARY KEY,
file TEXT NOT NULL
)
"""

FILES_INDEX = """
CREATE INDEX IF NOT EXISTS files_file ON files(file)
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

FILES_BY_NAME_QUERY = """
SELECT archive, file, filesize, ext, year FROM files where file=?
"""

FILES_QUERY = """
SELECT archive, file, filesize, ext, year, original_name FROM files where lib_id=?
"""

FILES_UPDATE = """
INSERT INTO files (lib_id, archive, file, filesize, ext, year, original_name) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

GENRE_TITLES_UPDATE = """
INSERT INTO genre_titles (code, title) VALUES (?, ?)
"""

GENRE_TITLES_QUERY = """
SELECT code, title FROM genre_titles
"""

BOOK_DIGEST_UPDATE = """
INSERT INTO book_digest (lib_id, annotation, reviews) VALUES (?, ?, ?)
"""

BOOK_DIGEST_QUERY = """
SELECT annotation, reviews FROM book_digest WHERE lib_id=?
"""

COVERS_UPDATE = """
INSERT INTO covers (lib_id, file) VALUES (?, ?)
"""

COVERS_QUERY = """
SELECT file FROM covers WHERE lib_id=?
"""

FORMATS_QUERY = """
SELECT DISTINCT ext FROM files ORDER BY ext
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

# For one book, every series it belongs to with that series' total book count
# (resolved by series_id to avoid name-collision ambiguity).
SERIES_SIZES_QUERY = """
SELECT s.name, s.serno, cnt.n
FROM series s
JOIN (SELECT series_id, COUNT(*) AS n FROM series GROUP BY series_id) cnt
  ON cnt.series_id = s.series_id
WHERE s.lib_id = ?
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


def _never_cancelled() -> bool:
    return False


@dataclass(frozen=True)
class MirrorValidationResult:
    missing_archives: int
    unknown_archives: int
    unknown_books: int


class TheLibrary:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._index = BookIndex()

        self._file_db_path = (
            Path(platformdirs.user_cache_dir("flget", ensure_exists=True)) / "files.db"
        )
        # files.db is read-only during search, which now runs in Textual thread
        # workers. SQLite connections are bound to their creating thread, so each
        # thread gets its own connection (see the _file_db property).
        self._local = threading.local()

        # Cached code->title map; the table is read-only outside sync().
        self._genre_titles_cache: dict[str, str] | None = None

        # Pre-create tables on the main-thread connection.
        self._file_db.execute(FILES_DDL)
        self._file_db.execute(FILES_INDEX)
        self._file_db.execute(SERIES_DDL)
        self._file_db.execute(AUTHORS_SERIES_DDL)
        self._file_db.execute(AUTHORS_BOOKS_DDL)
        self._file_db.execute(GENRE_TITLES_DDL)
        self._file_db.execute(BOOK_DIGEST_DDL)
        self._file_db.execute(COVERS_DDL)
        self._migrate_files_schema()

        self._file_db.commit()

    def _migrate_files_schema(self) -> None:
        """CREATE TABLE IF NOT EXISTS won't alter a pre-existing files.db, so add
        the original_name column when missing. Existing rows default to 0 until the
        next sync repopulates the table."""
        columns = {row[1] for row in self._file_db.execute("PRAGMA table_info(files)")}
        if "original_name" not in columns:
            self._file_db.execute(
                "ALTER TABLE files ADD COLUMN original_name INTEGER NOT NULL DEFAULT 0"
            )

    @property
    def _file_db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._file_db_path)
            self._local.conn = conn
        return conn

    def sync(self, mirror: Mirror, progress_update: Callable[[float], None]) -> None:
        self._index.create_index(mirror, progress_update)
        cur = self._file_db.cursor()
        cur.execute("DELETE FROM files")
        cur.execute("DELETE FROM series")
        cur.execute("DELETE FROM authors_series")
        cur.execute("DELETE FROM authors_books")
        cur.execute("DELETE FROM genre_titles")
        cur.execute("DELETE FROM book_digest")
        cur.execute("DELETE FROM covers")

        progress = 50.0 / float(len(mirror.books()))

        for lib_id, book in mirror.books():
            progress_update(progress)
            cur.execute(
                FILES_UPDATE,
                (
                    lib_id,
                    book.archive,
                    book.filename,
                    book.filesize,
                    book.ext,
                    book.year,
                    int(book.original_name),
                ),
            )
            if book.annotation or book.reviews:
                cur.execute(BOOK_DIGEST_UPDATE, (lib_id, book.annotation, book.reviews))
            if book.cover:
                cur.execute(COVERS_UPDATE, (lib_id, book.cover))
            if not book.series:
                for author_id in book.authors:
                    cur.execute(AUTHORS_BOOKS_UPDATE, (author_id, lib_id))

        for series_book in mirror.series_books():
            cur.execute(
                SERIES_UPDATE,
                (
                    series_book.series_id,
                    series_book.book_id,
                    series_book.serno,
                    series_book.series_name,
                ),
            )
            for author_id in series_book.authors:
                cur.execute(AUTHORS_SERIES_UPDATE, (author_id, series_book.series_id))

        for code, title in mirror.genre_titles().items():
            cur.execute(GENRE_TITLES_UPDATE, (code, title))

        self._file_db.commit()
        self._genre_titles_cache = None

    def _refill_book(self, book: BookEntry) -> BookEntry | None:
        """Populate file fields (archive/filename/ext/filesize) and the stored
        year onto an index-only ``BookEntry`` from files.db. Returns ``None``
        when the book has no files.db row."""
        book_file = self._file_db.execute(FILES_QUERY, (book.lib_id,)).fetchone()
        if book_file is None:
            return None
        return dataclasses.replace(
            book,
            archive=book_file[0],
            filename=book_file[1],
            filesize=book_file[2],
            ext=book_file[3],
            year=book_file[4],
        )

    def fill_book_digest(self, book: BookEntry) -> BookEntry:
        row = self._file_db.execute(BOOK_DIGEST_QUERY, (book.lib_id,)).fetchone()
        if row is None:
            return book
        return dataclasses.replace(book, annotation=row[0], reviews=row[1])

    @property
    def _attached_zip(self) -> zipfile.ZipFile:
        # TLS handler for a pics archive
        archive = getattr(self._local, "attached_zip", None)
        if archive is None:
            archive = zipfile.ZipFile(
                Path(platformdirs.user_cache_dir("flget")) / "lib.b.attached.zip",
                "r",
            )
            self._local.attached_zip = archive
        return archive

    def get_cover(self, book_id: int) -> bytes | None:
        row = self._file_db.execute(COVERS_QUERY, (book_id,)).fetchone()
        if row is None:
            return None
        try:
            return self._attached_zip.read(row[0])
        except (OSError, KeyError, zipfile.BadZipFile):
            return None

    def search_authors(
        self,
        query: str,
        book_filter: BookFilter | None = None,
        is_cancelled: Callable[[], bool] = _never_cancelled,
    ) -> list[AuthorEntry]:
        authors = self._index.search_authors(query, is_cancelled)
        if book_filter is None or book_filter.is_empty():
            return authors
        result: list[AuthorEntry] = []
        for a in authors:
            if is_cancelled():
                return result
            if self._author_has_match(a.id, book_filter, is_cancelled):
                result.append(a)
        return result

    def _author_has_match(
        self,
        author_id: int,
        book_filter: BookFilter,
        is_cancelled: Callable[[], bool] = _never_cancelled,
    ) -> bool:
        if any(
            book_filter.matches(b)
            for b in self.get_author_books(author_id, is_cancelled)
        ):
            return True
        for series_id in self.get_author_series(author_id):
            if is_cancelled():
                return False
            if any(
                book_filter.matches(b) for b in self.get_series(series_id, is_cancelled)
            ):
                return True
        return False

    def suggest_authors(self, query: str) -> str | None:
        return self._index.suggest_authors(query)

    def search_series(
        self,
        query: str,
        book_filter: BookFilter | None = None,
        is_cancelled: Callable[[], bool] = _never_cancelled,
    ) -> list[SeriesEntry]:
        series = self._index.search_series(query, is_cancelled)
        if book_filter is None or book_filter.is_empty():
            return series
        result: list[SeriesEntry] = []
        for s in series:
            if is_cancelled():
                return result
            if any(book_filter.matches(b) for b in self.get_series(s.id, is_cancelled)):
                result.append(s)
        return result

    def suggest_series(self, query: str) -> str | None:
        return self._index.suggest_series(query)

    def search_books(
        self,
        query: str,
        book_filter: BookFilter | None = None,
        is_cancelled: Callable[[], bool] = _never_cancelled,
    ) -> list[BookEntry]:
        result: list[BookEntry] = []
        for book in self._index.search_books(query, is_cancelled):
            if is_cancelled():
                return result
            refilled = self._refill_book(book)
            if refilled is None:
                continue
            if book_filter is None or book_filter.matches(refilled):
                result.append(refilled)
        return result

    def genre_titles(self) -> dict[str, str]:
        """Cached code->title map for genres. Empty when the catalog carries no
        genre titles (e.g. an INPX-only sync), in which case callers fall back to
        the raw codes."""
        if self._genre_titles_cache is None:
            self._genre_titles_cache = {
                row[0]: row[1]
                for row in self._file_db.execute(GENRE_TITLES_QUERY).fetchall()
            }
        return self._genre_titles_cache

    def list_genres(self) -> list[tuple[str, str | None]]:
        titles = self.genre_titles()
        return [(code, titles.get(code)) for code in self._index.field_values("genres")]

    def list_languages(self) -> list[str]:
        return self._index.field_values("lang")

    def list_formats(self) -> list[str]:
        return [row[0] for row in self._file_db.execute(FORMATS_QUERY).fetchall()]

    @staticmethod
    def _archive_member_name(file: str | None, ext: str | None) -> str:
        if not file:
            return ""
        if not ext:
            return file
        return file if file.lower().endswith(f".{ext.lower()}") else f"{file}.{ext}"

    def build_filename(self, book_id: int) -> str:
        book_file = self._file_db.execute(FILES_QUERY, (book_id,)).fetchone()
        file, ext, original_name = book_file[1], book_file[3], book_file[5]
        if original_name:
            return self._archive_member_name(file, ext)

        books = self.get_books([book_id])
        if not books:
            return self._archive_member_name(file, ext)
        book = books[0]

        author = book.author_names[0] if book.author_names else None

        series: str | None = None
        serno: int | None = None
        rows = self._file_db.execute(SERIES_SIZES_QUERY, (book_id,)).fetchall()
        candidates = [row for row in rows if row[2] <= MAX_SERIES_SIZE]
        if candidates:
            name, position, _ = min(candidates, key=lambda row: row[2])
            series, serno = name, position

        return naming.build_book_filename(
            author, series, serno, book.title, book_id, book.ext or "", book.lang
        )

    def save(self, book_id: int, target_path: str) -> None:
        book_file = self._file_db.execute(FILES_QUERY, (book_id,)).fetchone()
        libdir = Path(self._config.libdir())
        if book_file[0].lower().endswith(".zip"):
            zippath = libdir / book_file[0]
        else:
            zippath = libdir / f"{book_file[0]}.zip"
        member = self._archive_member_name(book_file[1], book_file[3])
        out_name = self.build_filename(book_id)
        with zipfile.ZipFile(zippath, "r") as archive:
            data = archive.read(member)
        with (Path(target_path) / out_name).open("wb") as fh:
            fh.write(data)

    def _count_unknown_archives(self, progress_update: Callable[[float], None]) -> int:
        archives = set(x[0] for x in self._file_db.execute(ARCHIVES_QUERY).fetchall())
        unknown_archives = 0
        files_in_lib = list(Path(self._config.libdir()).iterdir())
        progress = 50.0 / float(len(files_in_lib))
        for entry in files_in_lib:
            progress_update(progress)
            name = entry.name.lower()
            if (
                name.endswith(".zip")
                and Path(name).stem not in archives
                and name not in archives
            ):
                unknown_archives += 1
        return unknown_archives

    def _count_unknown_entries(
        self, progress_update: Callable[[float], None]
    ) -> tuple[int, int]:
        archives = set(x[0] for x in self._file_db.execute(ARCHIVES_QUERY).fetchall())
        progress = 50.0 / float(len(archives))
        unknown_entries = 0
        missing_archives = 0
        for archive in archives:
            progress_update(progress)
            if archive.lower().endswith(".zip"):
                archive_path = Path(self._config.libdir()) / archive
            else:
                archive_path = Path(self._config.libdir()) / f"{archive}.zip"
            if not archive_path.exists():
                missing_archives += 1
            else:
                with zipfile.ZipFile(archive_path, "r") as zip_archive:
                    for member in zip_archive.namelist():
                        file_id = Path(member).stem
                        if (
                            not self._file_db.execute(
                                FILES_QUERY, (file_id,)
                            ).fetchone()
                            and not self._file_db.execute(
                                FILES_BY_NAME_QUERY, (member,)
                            ).fetchone()
                        ):
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

    def get_books(
        self,
        book_ids: list[int],
        is_cancelled: Callable[[], bool] = _never_cancelled,
    ) -> list[BookEntry]:
        result: list[BookEntry] = []
        for book in self._index.get_books(book_ids, is_cancelled):
            refilled = self._refill_book(book)
            if refilled is not None:
                result.append(refilled)
        return result

    def get_series_name(self, series_id: int) -> str:
        row = self._file_db.execute(SERIES_NAME_QUERY, (series_id,)).fetchone()
        return str(row[0])

    def get_series(
        self, series_id: int, is_cancelled: Callable[[], bool] = _never_cancelled
    ) -> list[BookEntry]:
        book_ids = self._file_db.execute(SERIES_QUERY, (series_id,)).fetchall()
        return self.get_books([book_id[0] for book_id in book_ids], is_cancelled)

    def get_author_series(self, author_id: int) -> list[int]:
        series_ids = self._file_db.execute(
            AUTHORS_SERIES_QUERY, (author_id,)
        ).fetchall()
        return [s[0] for s in series_ids]

    def get_author_books(
        self, author_id: int, is_cancelled: Callable[[], bool] = _never_cancelled
    ) -> list[BookEntry]:
        book_ids = self._file_db.execute(AUTHORS_BOOKS_QUERY, (author_id,)).fetchall()
        return self.get_books([book_id[0] for book_id in book_ids], is_cancelled)
