import subprocess
from gzip import GzipFile
from os import listdir
from os.path import isfile, join
from typing import Callable, Dict
import shutil
from zipfile import ZipFile

import requests
import os
import platformdirs
import mysql.connector

from library import SERIES_QUERY
from mirror import Mirror, BookEntry, AuthorEntry, SeriesEntry, SeriesBookLink

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
]

BOOKS_QUERY = """
select GROUP_CONCAT(distinct concat_ws(' ', lan.firstname, lan.middlename, lan.lastname)) as authors,
       GROUP_CONCAT(distinct lgl.GenreCode)                                               as genres,
       lb.title                                                                           as title,
       GROUP_CONCAT(DISTINCT lsn.seqname ORDER BY ls.seqid)                               as series,
       GROUP_CONCAT(DISTINCT ls.SeqNumb ORDER BY ls.seqid)                                as serno,
       lfn.filename                                                                       as filename,
       lb.FileSize                                                                        as filesize,
       lb.BookId                                                                          as lib_id,
       lb.FileType                                                                        as ext,
       date(str_to_date(lb.Time, '%Y-%m-%d %H:%m:%s'))                                    as year,
       lb.Lang                                                                            as lang,
       CEIL(AVG(lr.Rate))                                                                 as rating,
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
         left join flibusta.libavtor la on lan.AvtorId = la.AvtorId
         left join flibusta.libseq ls on la.BookId = ls.BookId
group by id, name
"""

SERIES_QUERY = """
select lsn.seqid as id, lsn.seqname as name, count(distinct ls.BookId) as books, count(distinct la.avtorid) as authors
from libseqname as lsn
         left join libseq as ls on lsn.SeqId = ls.SeqId
         left join flibusta.libavtor la on ls.BookId = la.BookId
group by id, name
"""

SERIES_BOOKS_QUERY = """
select libseq.SeqId,BookId,SeqNumb,SeqName from libseq join libseqname on libseqname.SeqId=libseq.SeqId
"""

def _download_file(target_dir: str, dump: str) -> str:
    url = FLIBUSTA_DB_PAGE.format(dump)
    local_filename = os.path.join(target_dir, url.split("/")[-1])
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=1048576):
                f.write(chunk)
    return local_filename


def get_dumps(progress_update: Callable[[float], None]):
    flget_cache_dir = platformdirs.user_cache_dir("flget", ensure_exists=True)
    progress = 100.0 / len(DB_FILE)
    for file in DB_FILE:
        _download_file(flget_cache_dir, file)
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

    con = mysql.connector.connect(user="root", password="mysql", host="localhost")
    db_cursor = con.cursor()
    db_cursor.execute("CREATE DATABASE IF NOT EXISTS flibusta")
    db_cursor.close()
    con.commit()
    con.close()

    progress = 100.0 / len(DB_FILE)
    for file in DB_FILE:
        fname = os.path.join(flget_cache_dir, os.path.splitext(file)[0])
        with open(fname, "rb") as f:
            subprocess.call(
                [
                    "/usr/bin/mysql",
                    "-h",
                    "127.0.0.1",
                    "-u",
                    "root",
                    "--password=mysql",
                    "-D",
                    "flibusta",
                ],
                stdin=f,
            )
            progress_update(progress)


def _build_archives_map(lib_dir: str) -> Dict[str, str]:
    archives_map = {}
    archive = [f for f in listdir(lib_dir) if isfile(join(lib_dir, f)) and f.lower().endswith(".zip")]
    for a in archive:
        with ZipFile(os.path.join(lib_dir, a), "r") as z:
            for file in z.namelist():
                archives_map[file] = a
    return archives_map


def build_mirror(lib_dir: str, progress_update: Callable[[float], None]) -> Mirror:
    archives_map = _build_archives_map(lib_dir)
    con = mysql.connector.connect(user="root", password="mysql", host="localhost", database="flibusta")
    # db_cursor = con.cursor()
    # db_cursor.execute("ALTER TABLE libavtorname MODIFY firstname VARCHAR(255) NULL")
    # db_cursor.execute("ALTER TABLE libavtorname MODIFY middlename VARCHAR(255) NULL")
    # db_cursor.execute("""UPDATE
    #     libavtorname
    # SET
    #     firstname = CASE firstname WHEN '' THEN NULL ELSE firstname END,
    #     middlename = CASE middlename WHEN '' THEN NULL ELSE middlename END
    # """)
    # db_cursor.close()
    # con.commit()
    #
    db_cursor = con.cursor()
    db_cursor.execute("SELECT COUNT(*) FROM libbook")

    total_books = db_cursor.fetchone()[0]
    progress = 34.0 / total_books

    db_cursor.execute(BOOKS_QUERY)
    books = {}
    for (
    authors, genres, title, series, serno, filename, filesize, libid, ext, year, lang, rating, keywords) in db_cursor:
        progress_update(progress)

        if ext.lower() == "fb2":
            full_filename = f"{libid}.fb2"
            if full_filename not in archives_map:
                continue
            archive = archives_map[full_filename]
            filename = libid
        elif filename:
            if filename not in archives_map:
                archive = ""
            else:
                archive = archives_map[filename]
        else:
            continue

        book = BookEntry(
            authors.split(",") if authors else [],
            genres.split(",") if genres else [],
            title,
            series,
            serno,
            filename,
            filesize,
            str(libid),
            False,
            ext,
            str(year),
            lang,
            rating,
            keywords,
            archive,
        )
        books[str(libid)]=book

    db_cursor.execute("SELECT COUNT(*) FROM libavtorname")

    total_authors = db_cursor.fetchone()[0]
    progress = 33.0 / total_authors

    db_cursor.execute(AUTHORS_QUERY)
    authors = []
    for (id, name, books_no, series_no) in db_cursor:
        progress_update(progress)
        author = AuthorEntry(id, name, books_no, series_no)
        authors.append(author)

    db_cursor.execute("SELECT COUNT(*) FROM libseqname")

    total_series = db_cursor.fetchone()[0]
    progress = 33.0 / total_series

    db_cursor.execute(SERIES_QUERY)
    series = []
    for (id, name, books_no, authors_no) in db_cursor:
        progress_update(progress)
        s = SeriesEntry(id, name, books_no, authors_no)
        series.append(s)

    db_cursor.execute(SERIES_BOOKS_QUERY)
    series_index = []
    for (id, book_id, serno, series_name) in db_cursor:
        series_index.append(SeriesBookLink(id, book_id, serno, series_name))

    con.close()

    return Mirror(books, series, authors, series_index, {})
