import os
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Callable

from mirror import BookEntry, AuthorEntry, SeriesEntry, Mirror


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
    if not os.path.exists(lib_dir):
        raise FileNotFoundError
    lib_dir = lib_dir

    for f in os.listdir(lib_dir):
        if f.lower().endswith(".inpx"):
            inpx_file = os.path.join(lib_dir, f)
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
                archive = Path(entry).stem
                info_raw = inpx.read(entry)
                for line in info_raw.split(b"\r\n"):
                    book_entry = line.split(b"\x04")
                    if len(book_entry) == 15:
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

                        series = book_entry[3].decode("UTF-8")
                        if series:
                            series_counter[series] = series_counter.get(series, 0) + 1
                            for a in authors:
                                s_a = (a, series)
                                if s_a not in series_author_sentinel:
                                    series_author_sentinel.add(s_a)
                                    authors_series_counter[s_a[0]] = (
                                        authors_series_counter.get(s_a[0], 0) + 1
                                    )
                                    series_authors_counter[s_a[1]] = (
                                        series_authors_counter.get(s_a[1], 0) + 1
                                    )
                        serno = optional_int_parse(book_entry[4].decode("UTF-8"))
                        filename = book_entry[5].decode("UTF-8")
                        filesize = int(book_entry[6].decode("UTF-8"))
                        libid = int(book_entry[7].decode("UTF-8"))
                        deleted = book_entry[8].decode("UTF-8") == "1"
                        ext = book_entry[9].decode("UTF-8")
                        date = datetime.strptime(
                            book_entry[10].decode("UTF-8"), "%Y-%m-%d"
                        )
                        lang = book_entry[11].decode("UTF-8")
                        rating = optional_int_parse(book_entry[12].decode("UTF-8"))
                        keywords = multi_entry_clean(
                            book_entry[13].decode("UTF-8").split(",")
                        )
                        books_count = BookEntry(
                            authors,
                            genres,
                            title,
                            series,
                            serno,
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
                        )
                        books[filename] = books_count

    authors = []
    authors_index = {}
    for index, (name, books_count) in enumerate(authors_counter.items()):
        if name in authors_series_counter:
            series_count = authors_series_counter[name]
        else:
            series_count = None
        authors.append(AuthorEntry(index, name, books_count, series_count))
        authors_index[name] = index

    series = []
    series_index = {}
    for index, (name, books_count) in enumerate(series_counter.items()):
        authors_count = series_authors_counter[name]
        series.append(SeriesEntry(index, name, books_count, authors_count))
        series_index[name] = index

    return Mirror(books, series, authors, series_index, authors_index)
