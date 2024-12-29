from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict


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
    series: str
    serno: int
    filename: str
    filesize: int
    lib_id: int
    deleted: bool
    ext: str
    date: datetime
    lang: str
    rating: int
    keywords: list[str]
    archive: str


class Mirror:
    def __init__(
        self,
        books: Dict[str,BookEntry],
        series: list[SeriesEntry],
        authors: list[AuthorEntry],
        series_index: dict[str, int],
        authors_index: dict[str, int],
    ):
        self._books = books
        self._series = series
        self._authors = authors
        self._series_index = series_index
        self._authors_index = authors_index

    def __len__(self):
        return self._books.__len__()

    def authors(self) -> list[AuthorEntry]:
        return self._authors

    def series(self) -> list[SeriesEntry]:
        return self._series

    def books(self) -> list[BookEntry]:
        return self._books.items()

    def series_to_id(self, name: str) -> Optional[int]:
        return self._series_index.get(name, None)

    def author_to_id(self, name: str) -> Optional[int]:
        return self._authors_index.get(name, None)
