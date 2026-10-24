import dataclasses

import pytest
import typer

from flget.filters import (
    BookFilter,
    genre_display_names,
    language_display,
    parse_size,
)
from flget.mirror import BookEntry

BOOK = BookEntry(
    authors=[1],
    author_names=["Author"],
    genres=["SF_Fantasy", "humor"],
    title="Title",
    series=[],
    filename="1",
    filesize=2048,
    lib_id=1,
    deleted=False,
    ext="FB2",
    year=1999,
    lang="RU",
    rating=-1,
    keywords=[],
    archive="fb2-000001-000100",
)


@pytest.mark.parametrize(
    ("lang", "expected"),
    [("ru", "Russian (ru)"), ("EN", "English (EN)"), ("xx", "xx"), ("", "")],
)
def test_language_display(lang: str, expected: str) -> None:
    assert language_display(lang) == expected


def test_genre_display_names() -> None:
    titles = {"sf_fantasy": "Фэнтези"}
    assert genre_display_names(["SF_Fantasy", "unknown"], titles) == [
        "Фэнтези",
        "unknown",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("100", 100),
        ("10B", 10),
        ("500K", 500 * 1024),
        ("500kb", 500 * 1024),
        (" 2m ", 2 * 1024**2),
        ("2 MB", 2 * 1024**2),
        ("1.5G", int(1.5 * 1024**3)),
        ("0", 0),
    ],
)
def test_parse_size(text: str, expected: int) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "K", "-1K", "1T", "1..5M"])
def test_parse_size_rejects_malformed(text: str) -> None:
    with pytest.raises(typer.BadParameter):
        parse_size(text)


def test_empty_filter_matches_everything() -> None:
    f = BookFilter()
    assert f.is_empty()
    assert f.matches(BOOK)
    bare = dataclasses.replace(BOOK, ext=None, year=None, filesize=None)
    assert f.matches(bare)


@pytest.mark.parametrize(
    "f",
    [
        BookFilter(genres=frozenset({"x"})),
        BookFilter(formats=frozenset({"x"})),
        BookFilter(languages=frozenset({"x"})),
        BookFilter(year_from=0),
        BookFilter(year_to=0),
        BookFilter(min_size=0),
        BookFilter(max_size=0),
    ],
)
def test_any_criterion_makes_filter_non_empty(f: BookFilter) -> None:
    assert not f.is_empty()


@pytest.mark.parametrize(
    ("f", "expected"),
    [
        # Book values are mixed-case; filter sets hold lowercased values.
        (BookFilter(genres=frozenset({"sf_fantasy"})), True),
        (BookFilter(genres=frozenset({"detective", "humor"})), True),
        (BookFilter(genres=frozenset({"detective"})), False),
        (BookFilter(formats=frozenset({"fb2", "epub"})), True),
        (BookFilter(formats=frozenset({"epub"})), False),
        (BookFilter(languages=frozenset({"ru"})), True),
        (BookFilter(languages=frozenset({"en"})), False),
        (BookFilter(year_from=1999, year_to=1999), True),
        (BookFilter(year_from=2000), False),
        (BookFilter(year_to=1998), False),
        (BookFilter(min_size=2048, max_size=2048), True),
        (BookFilter(min_size=2049), False),
        (BookFilter(max_size=2047), False),
    ],
)
def test_filter_matches(f: BookFilter, expected: bool) -> None:
    assert f.matches(BOOK) is expected


@pytest.mark.parametrize(
    ("f", "missing"),
    [
        (BookFilter(formats=frozenset({"fb2"})), {"ext": None}),
        (BookFilter(year_from=1900), {"year": None}),
        (BookFilter(year_to=2100), {"year": None}),
        (BookFilter(min_size=0), {"filesize": None}),
        (BookFilter(max_size=10**9), {"filesize": None}),
    ],
)
def test_filter_rejects_books_missing_the_field(
    f: BookFilter, missing: dict[str, None]
) -> None:
    assert not f.matches(dataclasses.replace(BOOK, **missing))  # type: ignore[arg-type]
