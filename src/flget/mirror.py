from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, ItemsView


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
    author_names: list[str]
    genres: list[str]
    title: str
    series: list[str]
    serno: list[int]
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


@dataclass(frozen=True)
class SeriesBookLink:
    series_id: int
    book_id: int
    serno: int
    series_name: str
    authors: list[str]


class Mirror:
    def __init__(
        self,
        books: Dict[str, BookEntry],
        series: list[SeriesEntry],
        authors: list[AuthorEntry],
        series_books: list[SeriesBookLink],
        genre_titles: Optional[Dict[str, str]] = None,
    ):
        self._books = books
        self._series = series
        self._authors = authors
        self._series_books = series_books
        self._genre_titles = genre_titles or {}

    def __len__(self):
        return self._books.__len__()

    def authors(self) -> list[AuthorEntry]:
        return self._authors

    def series(self) -> list[SeriesEntry]:
        return self._series

    def books(self) -> ItemsView[str, BookEntry]:
        return self._books.items()

    def series_books(self) -> list[SeriesBookLink]:
        return self._series_books

    def genre_titles(self) -> Dict[str, str]:
        return self._genre_titles
