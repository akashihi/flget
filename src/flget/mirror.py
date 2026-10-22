from collections.abc import ItemsView
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthorEntry:
    id: int
    name: str
    books: int
    series: int | None


@dataclass(frozen=True)
class SeriesEntry:
    id: int
    name: str
    books: int
    authors: int


@dataclass(frozen=True)
class BookEntry:
    authors: list[int]
    author_names: list[str]
    genres: list[str]
    title: str
    series: list[tuple[str, int]]  # Series are filled by fill_book_digest
    filename: str | None
    filesize: int | None
    lib_id: int
    deleted: bool | None
    ext: str | None
    year: int | None
    lang: str
    rating: int
    keywords: list[str]
    archive: str | None
    original_name: bool = False
    annotation: str = ""
    reviews: str = ""
    cover: str = ""  # member path inside lib.b.attached.zip, empty when no cover


@dataclass(frozen=True)
class SeriesBookLink:
    series_id: int
    book_id: int
    serno: int
    series_name: str
    authors: list[int]


class Mirror:
    def __init__(
        self,
        books: dict[str, BookEntry],
        series: list[SeriesEntry],
        authors: list[AuthorEntry],
        series_books: list[SeriesBookLink],
        genre_titles: dict[str, str] | None = None,
    ):
        self._books = books
        self._series = series
        self._authors = authors
        self._series_books = series_books
        self._genre_titles = genre_titles or {}

    def __len__(self) -> int:
        return self._books.__len__()

    def authors(self) -> list[AuthorEntry]:
        return self._authors

    def series(self) -> list[SeriesEntry]:
        return self._series

    def books(self) -> ItemsView[str, BookEntry]:
        return self._books.items()

    def series_books(self) -> list[SeriesBookLink]:
        return self._series_books

    def genre_titles(self) -> dict[str, str]:
        return self._genre_titles
