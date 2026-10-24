import zipfile
from pathlib import Path

import pytest

from flget.inpx import parse_inpx
from flget.mirror import AuthorEntry, BookEntry, Mirror, SeriesBookLink, SeriesEntry


def short_line(
    authors: str = "Толстой,Лев,Николаевич:",
    genres: str = "prose_classic:",
    title: str = "Война и мир",
    series: str = "",
    serno: str = "",
    file: str = "100",
    size: str = "1024",
    lib_id: str = "100",
    deleted: str = "0",
    ext: str = "fb2",
    date: str = "2007-11-08",
    lang: str = "ru",
    rating: str = "5",
    keywords: str = "",
) -> list[str]:
    """The 15-field layout: the archive is the ``.inp`` member's name. The
    trailing ``\\x04`` adds the 15th, empty field."""
    return [
        authors,
        genres,
        title,
        series,
        serno,
        file,
        size,
        lib_id,
        deleted,
        ext,
        date,
        lang,
        rating,
        keywords,
        "",
    ]


def long_line(archive: str, **fields: str) -> list[str]:
    """The 17-field layout: an insert number and the archive name follow the
    date, before the language."""
    line = short_line(**fields)
    return [*line[:11], "1", archive, *line[11:]]


def write_inpx(lib_dir: Path, inps: dict[str, list[list[str]]]) -> None:
    with zipfile.ZipFile(lib_dir / "flibusta.INPX", "w") as inpx:
        inpx.writestr("collection.info", "Flibusta")
        for name, lines in inps.items():
            text = "\r\n".join("\x04".join(fields) for fields in lines)
            inpx.writestr(name, (text + "\r\n").encode("utf-8"))


def parse(lib_dir: Path) -> tuple[Mirror, list[float]]:
    progress: list[float] = []
    return parse_inpx(str(lib_dir), progress.append), progress


def book(mirror: Mirror, lib_id: int) -> BookEntry:
    return dict(mirror.books())[str(lib_id)]


def test_short_layout(tmp_path: Path) -> None:
    write_inpx(
        tmp_path,
        {
            "fb2-000001-000200.inp": [
                short_line(
                    authors="Pratchett,Terry,:Gaiman,Neil,:",
                    genres="sf_fantasy:humor:",
                    title="Good Omens",
                    series="Discworld",
                    serno="3",
                    file="Good_Omens",
                    size="2048",
                    lib_id="101",
                    deleted="1",
                    date="1990-05-01",
                    lang="en",
                    keywords="angels,demons",
                )
            ]
        },
    )
    mirror, _ = parse(tmp_path)

    assert book(mirror, 101) == BookEntry(
        authors=[0, 1],
        author_names=["Pratchett Terry", "Gaiman Neil"],
        genres=["sf_fantasy", "humor"],
        title="Good Omens",
        series=[("Discworld", 3)],
        filename="Good_Omens",
        filesize=2048,
        lib_id=101,
        deleted=True,
        ext="fb2",
        year=1990,
        lang="en",
        rating=5,
        keywords=["angels", "demons"],
        archive="fb2-000001-000200",
        original_name=True,
    )


def test_long_layout(tmp_path: Path) -> None:
    write_inpx(
        tmp_path,
        {"index.inp": [long_line("fb2-000101-000300", lib_id="150", file="150")]},
    )
    mirror, _ = parse(tmp_path)

    entry = book(mirror, 150)
    assert entry.archive == "fb2-000101-000300"
    assert entry.lang == "ru"
    assert entry.rating == 5
    assert entry.keywords == []
    assert entry.year == 2007
    # The filename is just the id, so it is not an original name.
    assert not entry.original_name


@pytest.mark.parametrize(
    ("serno", "rating", "expected"),
    [("", "", -1), ("x", "?", -1), ("0", "0", 0)],
)
def test_optional_numbers(
    tmp_path: Path, serno: str, rating: str, expected: int
) -> None:
    write_inpx(
        tmp_path, {"a.inp": [short_line(series="S", serno=serno, rating=rating)]}
    )
    mirror, _ = parse(tmp_path)

    entry = book(mirror, 100)
    assert entry.series == [("S", expected)]
    assert entry.rating == expected


def test_skips_lines_with_other_field_counts(tmp_path: Path) -> None:
    write_inpx(
        tmp_path,
        {"a.inp": [short_line(lib_id="1"), ["broken", "line"], short_line()[:-2]]},
    )
    mirror, _ = parse(tmp_path)

    assert [b.lib_id for _, b in mirror.books()] == [1]


def test_authors_and_series_get_synthetic_ids(tmp_path: Path) -> None:
    write_inpx(
        tmp_path,
        {
            "a.inp": [
                short_line(authors="A,,:B,,:", series="S1", serno="1", lib_id="1"),
                short_line(authors="A,,:", series="S1", serno="2", lib_id="2"),
                short_line(authors="B,,:", series="S2", serno="1", lib_id="3"),
            ],
            # Authors and series are shared across .inp members.
            "b.inp": [short_line(authors="C,,:A,,:", lib_id="4")],
        },
    )
    mirror, progress = parse(tmp_path)

    # Every zip member advances the progress, .inp or not.
    assert progress == pytest.approx([100 / 3] * 3)
    assert mirror.authors() == [
        AuthorEntry(0, "A", books=3, series=1),
        AuthorEntry(1, "B", books=2, series=2),
        AuthorEntry(2, "C", books=1, series=None),
    ]
    assert mirror.series() == [
        SeriesEntry(0, "S1", books=2, authors=2),
        SeriesEntry(1, "S2", books=1, authors=1),
    ]
    assert mirror.series_books() == [
        SeriesBookLink(0, 1, 1, "S1", [0, 1]),
        SeriesBookLink(0, 2, 2, "S1", [0]),
        SeriesBookLink(1, 3, 1, "S2", [1]),
    ]
    assert book(mirror, 4).authors == [2, 0]
    assert book(mirror, 4).series == []


def test_missing_library_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse(tmp_path / "nowhere")


def test_missing_inpx(tmp_path: Path) -> None:
    (tmp_path / "fb2-000001-000100.zip").touch()
    with pytest.raises(FileNotFoundError):
        parse(tmp_path)
