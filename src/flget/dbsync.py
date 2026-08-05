import dataclasses
import json
import math
import os
import shutil
import sqlite3
from collections.abc import Callable
from gzip import GzipFile
from os import listdir
from os.path import isfile, join
from typing import Any
from zipfile import ZipFile

import platformdirs
import requests
from markdownify import markdownify

from flget.mirror import AuthorEntry, BookEntry, Mirror, SeriesBookLink, SeriesEntry
from flget.mysqldump import load_dump

FLIBUSTA_DB_PAGE = "https://flibusta.is/sql/{}"
DB_FILE = [
    "lib.libtranslator.sql.gz",
    "lib.libavtor.sql.gz",
    "lib.libavtorname.sql.gz",
    "lib.libbook.sql.gz",
    "lib.libfilename.sql.gz",
    "lib.libgenre.sql.gz",
    "lib.libgenrelist.sql.gz",
    "lib.libjoinedbooks.sql.gz",
    "lib.librate.sql.gz",
    "lib.librecs.sql.gz",
    "lib.libseqname.sql.gz",
    "lib.libseq.sql.gz",
    "lib.b.annotations.sql.gz",
    "lib.b.annotations_pics.sql.gz",
    "lib.reviews.sql.gz",
]

ATTACHMENT_FILE = [
    "lib.b.attached.zip",
]

BOOKS_QUERY = """
select GROUP_CONCAT(distinct la.AvtorId) as authors, 
    GROUP_CONCAT(distinct concat_ws(' ', lan.firstname, lan.middlename, lan.lastname)) as author_names,
    GROUP_CONCAT(distinct lgl.GenreCode)                                               as genres,
    lb.title                                                                           as title,
    COALESCE(ordered_concat(lsn.seqname, ls.seqid), '')                                as series,
    COALESCE(ordered_concat(ls.SeqNumb, ls.seqid), '-1')                               as serno,
    lfn.filename                                                                       as filename,
    lb.FileSize                                                                        as filesize,
    lb.BookId                                                                          as lib_id,
    lb.FileType                                                                        as ext,
    substr(lb.Time, 1, 10)                                                             as year,
    lb.Lang                                                                            as lang,
    COALESCE(CEIL(AVG(lr.Rate)), -1)                                                   as rating,
    lb.keywords                                                                        as keywords
from libbook as lb
    left join libavtor as la on lb.BookId = la.BookId
    left join libavtorname as lan on lan.AvtorId = la.AvtorId
    left join libgenre as lg on lg.BookId = lb.BookId
    left join libgenrelist as lgl on lgl.GenreId = lg.GenreId
    left join libseq as ls on ls.BookId = lb.BookId
    left join libseqname as lsn on lsn.SeqId = ls.SeqId
    left join librate as lr on lr.BookId = lb.BookId
    left join libfilename as lfn on lfn.BookId = lb.BookId
group by title, filename, filesize, lib_id, ext, year, lang, keywords
"""

AUTHORS_QUERY = """
select lan.AvtorId                                                 as id,
       concat_ws(' ', lan.firstname, lan.middlename, lan.lastname) as name,
       count(distinct la.BookId)                                   as books,
       count(distinct ls.SeqId)                                    as series
from libavtorname as lan
         left join libavtor la on lan.AvtorId = la.AvtorId
         left join libseq ls on la.BookId = ls.BookId
group by id, name
"""

SERIES_QUERY = """
select lsn.seqid as id, lsn.seqname as name, count(distinct ls.BookId) as books, count(distinct la.avtorid) as authors
from libseqname as lsn
         left join libseq as ls on lsn.SeqId = ls.SeqId
         left join libavtor la on ls.BookId = la.BookId
group by id, name
"""

GENRE_TITLES_QUERY = """
SELECT GenreCode, GenreDesc FROM libgenrelist
"""

SERIES_BOOKS_QUERY = """
                     select libseq.SeqId, libseq.BookId, SeqNumb, SeqName, group_concat(distinct AvtorId) as authors
                     from libseq
                              join libseqname on libseqname.SeqId = libseq.SeqId
                              join libavtor on libavtor.BookId = libseq.BookId
                     group by libseq.SeqId, libseq.BookId, SeqNumb, SeqName
"""


# Indexes on the columns the four Mirror queries join on. Built once after
# import; without them the multi-table joins degrade to full scans. The dumps'
# own keys are not recreated -- only these matter for our queries.
_JOIN_INDEXES = [
    ("libavtor", "BookId"),
    ("libavtor", "AvtorId"),
    ("libgenre", "BookId"),
    ("libgenre", "GenreId"),
    ("libgenrelist", "GenreId"),
    ("libseq", "BookId"),
    ("libseq", "SeqId"),
    ("libseqname", "SeqId"),
    ("librate", "BookId"),
    ("libfilename", "BookId"),
    ("libbook", "BookId"),
    ("libavtorname", "AvtorId"),
    ("libbannotations", "BookId"),
    ("libreviews", "BookId"),
    ("libbpics", "BookId"),
]

ANNOTATIONS_QUERY = "SELECT BookId, Body FROM libbannotations ORDER BY BookId, nid"
REVIEWS_QUERY = "SELECT BookId, Name, Time, Text FROM libreviews ORDER BY BookId, Time"
PICS_QUERY = "SELECT BookId, File FROM libbpics ORDER BY BookId, nid"


def _db_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "flibusta.db")


def _html_to_markdown(html: str | None) -> str:
    if not html:
        return ""
    return markdownify(html).strip()


def _concat_ws(sep: str, *args: Any) -> str:
    """MySQL CONCAT_WS: join the non-NULL arguments with ``sep``."""
    return sep.join(str(a) for a in args if a is not None)


def _ceil(value: Any) -> Any:
    """MySQL CEIL, NULL-safe (so COALESCE around it still fires)."""
    return None if value is None else math.ceil(value)


class _OrderedConcat:
    """Aggregate replacing MySQL ``GROUP_CONCAT(DISTINCT v ORDER BY k)``.

    SQLite's built-in ``group_concat`` cannot order its output, so we collect
    ``(sortkey, value)`` pairs, sort by the key, drop duplicate values and
    comma-join. Returns NULL when empty so the surrounding COALESCE applies.
    """

    def __init__(self) -> None:
        self._items: list[Any] = []

    def step(self, *values: Any) -> None:
        value, sortkey = values
        if value is not None:
            self._items.append((sortkey, value))

    def finalize(self) -> str | None:
        seen = set()
        out = []
        for _, value in sorted(self._items, key=lambda x: (x[0] is None, x[0])):
            text = str(value)
            if text not in seen:
                seen.add(text)
                out.append(text)
        return ",".join(out) if out else None


def _register_functions(con: sqlite3.Connection) -> None:
    con.create_function("concat_ws", -1, _concat_ws)
    con.create_function("ceil", 1, _ceil)
    # typeshed's _AggregateProtocol only models single-argument aggregates, so
    # it cannot express this 2-arg (value, sortkey) aggregate.
    con.create_aggregate("ordered_concat", 2, _OrderedConcat)  # type: ignore[arg-type]


def _meta_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, "dumps_meta.json")


def _load_meta(cache_dir: str) -> dict[str, Any]:
    try:
        with open(_meta_path(cache_dir)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_meta(cache_dir: str, meta: dict[str, Any]) -> None:
    with open(_meta_path(cache_dir), "w") as f:
        json.dump(meta, f)


def _download_file(
    target_dir: str, dump: str, meta: dict[str, Any], force: bool = False
) -> str:
    url = FLIBUSTA_DB_PAGE.format(dump)
    local_filename = os.path.join(target_dir, url.split("/")[-1])

    headers: dict[str, str] = {}
    entry = meta.get(dump)
    if not force and entry and os.path.isfile(local_filename):
        size = entry.get("size")
        # Only trust the cached validators when the local file is intact.
        if size is None or os.path.getsize(local_filename) == size:
            if entry.get("etag"):
                headers["If-None-Match"] = entry["etag"]
            if entry.get("last_modified"):
                headers["If-Modified-Since"] = entry["last_modified"]

    with requests.get(url, stream=True, headers=headers) as r:
        r.raise_for_status()
        if r.status_code == 304:
            return local_filename
        written = 0
        with open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=1048576):
                f.write(chunk)
                written += len(chunk)
        meta[dump] = {
            "etag": r.headers.get("ETag"),
            "last_modified": r.headers.get("Last-Modified"),
            "size": written,
        }
    return local_filename


def get_dumps(progress_update: Callable[[float], None], force: bool = False):
    flget_cache_dir = platformdirs.user_cache_dir("flget", ensure_exists=True)
    meta = _load_meta(flget_cache_dir)
    all_downloads = DB_FILE + ATTACHMENT_FILE
    progress = 100.0 / len(all_downloads)
    for file in all_downloads:
        _download_file(flget_cache_dir, file, meta, force=force)
        _save_meta(flget_cache_dir, meta)
        progress_update(progress)


def decompress_dumps(progress_update: Callable[[float], None]):
    flget_cache_dir = platformdirs.user_cache_dir("flget", ensure_exists=True)
    progress = 100.0 / len(DB_FILE)
    for file in DB_FILE:
        nongz_file = os.path.join(flget_cache_dir, os.path.splitext(file)[0])
        with GzipFile(os.path.join(flget_cache_dir, file), "rb") as f_in:
            with open(nongz_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        progress_update(progress)


def db_import_dumps(progress_update: Callable[[float], None]):
    flget_cache_dir = platformdirs.user_cache_dir("flget")
    db_path = _db_path(flget_cache_dir)

    # Rebuild the staging DB from scratch every sync -- it is a throwaway
    # representation of the dumps, not durable data.
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    # This is a one-shot bulk load into a disposable file, so trade durability
    # for speed.
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")

    progress = 100.0 / len(DB_FILE)
    for file in DB_FILE:
        fname = os.path.join(flget_cache_dir, os.path.splitext(file)[0])
        load_dump(con, fname)
        con.commit()
        progress_update(progress)

    for table, column in _JOIN_INDEXES:
        con.execute(
            f'CREATE INDEX IF NOT EXISTS "ix_{table}_{column}" ON "{table}"("{column}")'
        )
    con.commit()
    con.close()


def _build_archives_map(lib_dir: str) -> dict[str, str]:
    archives_map = {}
    archive = [
        f
        for f in listdir(lib_dir)
        if isfile(join(lib_dir, f)) and f.lower().endswith(".zip")
    ]
    for a in archive:
        with ZipFile(os.path.join(lib_dir, a), "r") as z:
            for file in z.namelist():
                archives_map[file] = a
                archives_map[file.encode("utf-8").decode("cp437")] = a
    return archives_map


def build_mirror(lib_dir: str, progress_update: Callable[[float], None]) -> Mirror:
    archives_map = _build_archives_map(lib_dir)
    flget_cache_dir = platformdirs.user_cache_dir("flget")
    con = sqlite3.connect(_db_path(flget_cache_dir))
    _register_functions(con)

    db_cursor = con.cursor()
    db_cursor.execute("SELECT COUNT(*) FROM libbook")

    total_books = db_cursor.fetchone()[0]
    progress = 34.0 / total_books

    db_cursor.execute(BOOKS_QUERY)
    books = {}
    for (
        authors,
        author_names,
        genres,
        title,
        series,
        serno,
        filename,
        filesize,
        libid,
        ext,
        year,
        lang,
        rating,
        keywords,
    ) in db_cursor:
        progress_update(progress)

        # usr archives have an actual name sometimes
        original_name = False
        if ext.lower() == "fb2":
            full_filename = f"{libid}.fb2"
            if full_filename not in archives_map:
                continue
            archive = archives_map[full_filename]
            filename = libid
        elif filename:
            if filename not in archives_map:
                continue
            archive = archives_map[filename]
            original_name = True
        else:
            filename = f"{libid}.{ext}"
            if filename not in archives_map:
                filename = f"{filename}.zip"
                if filename not in archives_map:
                    continue
            archive = archives_map[filename]

        series_list = series.split(",") if series else []
        serno_list = [int(x) for x in serno.split(",")] if series else []

        book = BookEntry(
            authors.split(",") if authors else [],
            author_names.split(",") if authors else [],
            genres.split(",") if genres else [],
            title,
            series_list,
            serno_list,
            filename,
            filesize,
            str(libid),
            False,
            ext,
            str(year),
            lang,
            rating,
            keywords.split(",") if keywords else [],
            archive,
            original_name,
        )
        books[str(libid)] = book

    db_cursor.execute("SELECT COUNT(*) FROM libavtorname")

    total_authors = db_cursor.fetchone()[0]
    progress = 33.0 / total_authors

    db_cursor.execute(AUTHORS_QUERY)
    authors = []
    for id, name, books_no, series_no in db_cursor:
        progress_update(progress)
        author = AuthorEntry(id, name, books_no, series_no)
        authors.append(author)

    db_cursor.execute("SELECT COUNT(*) FROM libseqname")

    total_series = db_cursor.fetchone()[0]
    progress = 33.0 / total_series

    db_cursor.execute(SERIES_QUERY)
    series = []
    for id, name, books_no, authors_no in db_cursor:
        progress_update(progress)
        s = SeriesEntry(id, name, books_no, authors_no)
        series.append(s)

    db_cursor.execute(SERIES_BOOKS_QUERY)
    series_index = []
    for id, book_id, serno, series_name, series_authors in db_cursor:
        series_index.append(
            SeriesBookLink(id, book_id, serno, series_name, series_authors.split(","))
        )

    genre_titles = {}
    db_cursor.execute(GENRE_TITLES_QUERY)
    for code, desc in db_cursor:
        if code and desc:
            genre_titles[code.lower()] = desc

    # Pre-render annotations/reviews to Markdown and attach to the books
    annotation_md: dict[str, str] = {}
    db_cursor.execute(ANNOTATIONS_QUERY)
    for book_id, body in db_cursor:
        key = str(book_id)
        if key not in books:
            continue
        md = _html_to_markdown(body)
        if not md:
            continue
        annotation_md[key] = (
            f"{annotation_md[key]}\n\n{md}" if key in annotation_md else md
        )

    review_md: dict[str, str] = {}
    db_cursor.execute(REVIEWS_QUERY)
    for book_id, name, time, text in db_cursor:
        key = str(book_id)
        if key not in books:
            continue
        body = _html_to_markdown(text)
        if not body:
            continue
        block = f"**{name or 'Anonymous'}** — _{time}_\n\n{body}\n\n---\n"
        review_md[key] = review_md[key] + block if key in review_md else block

    cover_map: dict[str, str] = {}
    db_cursor.execute(PICS_QUERY)
    for book_id, file in db_cursor:
        key = str(book_id)
        if key not in books or not file or key in cover_map:
            continue
        cover_map[key] = file

    for key in annotation_md.keys() | review_md.keys() | cover_map.keys():
        books[key] = dataclasses.replace(
            books[key],
            annotation=annotation_md.get(key, ""),
            reviews=review_md.get(key, ""),
            cover=cover_map.get(key, ""),
        )

    con.close()

    return Mirror(books, series, authors, series_index, genre_titles=genre_titles)
