import os
import zipfile

import platformdirs
import sqlite3

from config import Config
from inpx import INPX, BookEntry
from index import TheIndex

FILES_DDL = """
CREATE TABLE IF NOT EXISTS files (
lib_id INTEGER PRIMARY KEY,
archive TEXT NOT NULL,
file TEXT NOT NULL UNIQUE,
filesize INTEGER NOT NULL,
ext TEXT NOT NULL 
)
"""

FILES_QUERY = """
SELECT archive, file, filesize, ext FROM files where lib_id=? 
"""

FILES_UPDATE = """
INSERT INTO files (lib_id, archive, file, filesize, ext) VALUES (?, ?, ?, ?, ?)
"""

class TheLibrary:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._index = TheIndex()

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

    def search_books(self, query: str) -> list[BookEntry]:
        return self._index.search_books(query)

    def get(self, book_id: int)-> None:
        book_file = self._file_db.execute(FILES_QUERY, (book_id,)).fetchone()
        zippath = os.path.join(self._config.libdir(), f"{book_file[0]}.zip")
        with zipfile.ZipFile(zippath, "r") as archive:
            archive.extract(f"{book_file[1]}.{book_file[3]}", "/tmp")