import os
import zipfile
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from xmlrpc.client import DateTime


@dataclass(frozen=True)
class BookEntry:
    authors: list[str]
    genres: list[str]
    title: str
    series: list[str]
    serno: int
    filename: str
    filesize: int
    lib_id: int
    deleted: bool
    ext: str
    date: DateTime
    lang: str
    rating: str
    keywords: list[str]
    archive: str


def multi_entry_clean(input: list[str]) -> list[str]:
    if not input[-1]:
        del input[-1]
    return list(map(lambda s: s.strip(","), input))


def optional_int_parse(input: str) -> Optional[int]:
    try:
        return int(input) if input else None
    except ValueError:
        return None


class INPX:
    def __init__(self, lib_dir: str):
        if not os.path.exists(lib_dir):
            raise FileNotFoundError
        self._lib_dir = lib_dir

        for f in os.listdir(self._lib_dir):
            if f.lower().endswith(".inpx"):
                self._inpx_file = os.path.join(self._lib_dir, f)
                break
        if not self._inpx_file:
            raise FileNotFoundError

        self._books = {}
        with zipfile.ZipFile(self._inpx_file, "r") as inpx:
            for entry in inpx.namelist():
                if entry.lower().endswith(".inp"):
                    archive = Path(entry).stem
                    info_raw = inpx.read(entry)
                    for line in info_raw.split(b'\r\n'):
                        book_entry = line.split(b'\x04')
                        if len(book_entry) == 15:
                            authors = multi_entry_clean(book_entry[0].decode("UTF-8").split(":"))
                            genres = multi_entry_clean(book_entry[1].decode("UTF-8").split(":"))
                            title = book_entry[2].decode("UTF-8")
                            series = multi_entry_clean(book_entry[3].decode("UTF-8").split(":"))
                            serno = optional_int_parse(book_entry[4].decode("UTF-8"))
                            filename = book_entry[5].decode("UTF-8")
                            filesize = int(book_entry[6].decode("UTF-8"))
                            libid = int(book_entry[7].decode("UTF-8"))
                            deleted = book_entry[8].decode("UTF-8") == '1'
                            ext = book_entry[9].decode("UTF-8")
                            date = datetime.strptime(book_entry[10].decode("UTF-8"), "%Y-%m-%d")
                            lang = book_entry[11].decode("UTF-8")
                            rating = optional_int_parse(book_entry[12].decode("UTF-8"))
                            keywords = multi_entry_clean(book_entry[13].decode("UTF-8").split(","))
                            book = BookEntry(authors, genres, title, series, serno, filename, filesize,libid, deleted, ext, date, lang, rating, keywords, archive)
                            self._books[filename] = book

    def __iter__(self):
        return iter(self._books)

    def __next__(self):
        return next(self._books)

    def __len__(self):
        return self._books.__len__()

    def exists(self, id: str) -> bool:
        return id in self._books

    def items(self):
        return self._books.items()