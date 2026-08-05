import dataclasses
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from flget.mirror import AuthorEntry, BookEntry, Mirror, SeriesBookLink, SeriesEntry

INPX_FIELDS_SHORT = 15
INPX_FIELDS_LONG = 17


def multi_entry_clean(input: list[str]) -> list[str]:
    if not input[-1]:
        del input[-1]
    return list(map(lambda s: s.strip(","), input))


def optional_int_parse(input: str) -> int:
    try:
        return int(input) if input else -1
    except ValueError:
        return -1


def parse_inpx(lib_dir: str, progress_update: Callable[[float], None]) -> Mirror:
    lib_path = Path(lib_dir)
    if not lib_path.exists():
        raise FileNotFoundError

    inpx_file = None
    for f in lib_path.iterdir():
        if f.name.lower().endswith(".inpx"):
            inpx_file = f
            break
    if not inpx_file:
        raise FileNotFoundError

    books = {}

    authors_counter: dict[str, int] = {}
    series_counter: dict[str, int] = {}
    authors_series_counter: dict[str, int] = {}
    series_authors_counter: dict[str, int] = {}
    series_author_sentinel = set()
    with zipfile.ZipFile(inpx_file, "r") as inpx:
        progress = 100.0 / float(len(inpx.namelist()))
        for entry in inpx.namelist():
            progress_update(progress)
            if entry.lower().endswith(".inp"):
                info_raw = inpx.read(entry)
                for line in info_raw.split(b"\r\n"):
                    book_entry = line.split(b"\x04")
                    if len(book_entry) in (INPX_FIELDS_SHORT, INPX_FIELDS_LONG):
                        authors = multi_entry_clean(
                            book_entry[0].decode("UTF-8").split(":")
                        )
                        authors = [author.replace(",", " ") for author in authors]
                        for author in authors:
                            authors_counter[author] = authors_counter.get(author, 0) + 1

                        genres = multi_entry_clean(
                            book_entry[1].decode("UTF-8").split(":")
                        )
                        title = book_entry[2].decode("UTF-8")

                        series_names = book_entry[3].decode("UTF-8")
                        if series_names:
                            series_counter[series_names] = (
                                series_counter.get(series_names, 0) + 1
                            )
                            for a in authors:
                                s_a = (a, series_names)
                                if s_a not in series_author_sentinel:
                                    series_author_sentinel.add(s_a)
                                    authors_series_counter[s_a[0]] = (
                                        authors_series_counter.get(s_a[0], 0) + 1
                                    )
                                    series_authors_counter[s_a[1]] = (
                                        series_authors_counter.get(s_a[1], 0) + 1
                                    )
                        serno = optional_int_parse(book_entry[4].decode("UTF-8"))
                        series_list = [series_names] if series_names else []
                        serno_list = [serno] if series_names else []
                        filename = book_entry[5].decode("UTF-8")
                        filesize = int(book_entry[6].decode("UTF-8"))
                        libid = int(book_entry[7].decode("UTF-8"))
                        deleted = book_entry[8].decode("UTF-8") == "1"
                        ext = book_entry[9].decode("UTF-8")
                        date = datetime.strptime(  # noqa: DTZ007
                            book_entry[10].decode("UTF-8"), "%Y-%m-%d"
                        )
                        if len(book_entry) == INPX_FIELDS_SHORT:
                            archive = Path(entry).stem
                            lang = book_entry[11].decode("UTF-8")
                            rating = optional_int_parse(book_entry[12].decode("UTF-8"))
                            keywords = multi_entry_clean(
                                book_entry[13].decode("UTF-8").split(",")
                            )
                        else:  # INPX_FIELDS_LONG
                            archive = book_entry[12].decode("UTF-8")
                            lang = book_entry[13].decode("UTF-8")
                            rating = optional_int_parse(book_entry[14].decode("UTF-8"))
                            keywords = multi_entry_clean(
                                book_entry[15].decode("UTF-8").split(",")
                            )

                        # INPX stores real names without an extension.
                        original_name = bool(filename) and filename != str(libid)

                        books_count = BookEntry(
                            authors,
                            [],
                            genres,
                            title,
                            series_list,
                            serno_list,
                            filename,
                            filesize,
                            libid,
                            deleted,
                            ext,
                            date,
                            lang,
                            rating,
                            keywords,
                            archive,
                            original_name,
                        )
                        books[str(libid)] = books_count

    authors = []
    authors_index = {}
    for index, (name, books_count) in enumerate(authors_counter.items()):
        if name in authors_series_counter:
            series_count = authors_series_counter[name]
        else:
            series_count = None
        authors.append(AuthorEntry(index, name, books_count, series_count))
        authors_index[name] = index

    for book_id, book in books.items():
        books[book_id] = dataclasses.replace(
            book,
            authors=list(map(lambda x: authors_index[x], book.authors)),
            author_names=book.authors,
        )

    series = []
    series_index = {}
    for index, (name, books_count) in enumerate(series_counter.items()):
        authors_count = series_authors_counter[name]
        series.append(SeriesEntry(index, name, books_count, authors_count))
        series_index[name] = index

    series_link = []
    for book in filter(lambda b: b[1].series, books.items()):
        series_link.append(
            SeriesBookLink(
                series_index.get(book[1].series[0]),
                book[1].lib_id,
                book[1].serno[0],
                book[1].series[0],
                book[1].authors,
            )
        )

    return Mirror(books, series, authors, series_link)
