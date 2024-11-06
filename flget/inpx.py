import os
import zipfile
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
from xmlrpc.client import DateTime
import itertools


@dataclass(frozen=True)
class AuthorEntry:
    id: int
    name: str
    books: int
    series: Optional[int]

@dataclass(frozen=True)
class SeriesEntry:
    id: int
    name: str
    books: int
    authors: int

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
    rating: int
    keywords: list[str]
    archive: str


def multi_entry_clean(input: list[str]) -> list[str]:
    if not input[-1]:
        del input[-1]
    return list(map(lambda s: s.strip(","), input))


def optional_int_parse(input: str) -> int:
    try:
        return int(input) if input else -1
    except ValueError:
        return -1


class INPX:
    def __init__(self, lib_dir: str, progress_update: Callable[[float], None]):
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

        authors_counter = {}
        series_counter = {}
        authors_series_counter = {}
        series_authors_counter = {}
        series_author_sentinel = set()
        with zipfile.ZipFile(self._inpx_file, "r") as inpx:
            progress = 100.0 / float(len(inpx.namelist()))
            for entry in inpx.namelist():
                progress_update(progress)
                if entry.lower().endswith(".inp"):
                    archive = Path(entry).stem
                    info_raw = inpx.read(entry)
                    for line in info_raw.split(b'\r\n'):
                        book_entry = line.split(b'\x04')
                        if len(book_entry) == 15:
                            authors = multi_entry_clean(book_entry[0].decode("UTF-8").split(":"))
                            for author in authors:
                                authors_counter[author] = authors_counter.get(author, 0) + 1

                            genres = multi_entry_clean(book_entry[1].decode("UTF-8").split(":"))
                            title = book_entry[2].decode("UTF-8")

                            series = multi_entry_clean(book_entry[3].decode("UTF-8").split(":"))
                            if series:
                                for s in series:
                                    series_counter[s] = series_counter.get(s, 0) + 1
                                for s_a in itertools.product(authors, series):
                                    if s_a not in series_author_sentinel:
                                        series_author_sentinel.add(s_a)
                                        authors_series_counter[s_a[0]] = authors_series_counter.get(s_a[0], 0) + 1
                                        series_authors_counter[s_a[1]] = series_authors_counter.get(s_a[1], 0) + 1
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
                            books_count = BookEntry(authors, genres, title, series, serno, filename, filesize, libid, deleted,
                                             ext, date, lang, rating, keywords, archive)
                            self._books[filename] = books_count

        self._authors = []
        for (index,(name, books_count)) in enumerate(authors_counter.items()):
            if name in authors_series_counter:
                series_count = authors_series_counter[name]
            else:
                series_count = None
            self._authors.append(AuthorEntry(index, name, books_count, series_count))

        self._series = []
        for (index,(name, books_count)) in enumerate(series_counter.items()):
            authors_count = series_authors_counter[name]
            self._series.append(SeriesEntry(index, name, books_count, authors_count))

    def __iter__(self):
        return iter(self._books)

    def __next__(self):
        return next(self._books)

    def __len__(self):
        return self._books.__len__()

    def authors(self):
        return self._authors

    def series(self):
        return self._series

    def exists(self, id: str) -> bool:
        return id in self._books

    def items(self):
        return self._books.items()
