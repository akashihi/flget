import subprocess
from gzip import GzipFile
from typing import Callable
import shutil

import requests
import os
import platformdirs
import mysql.connector

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
    progress = 100.0/len(DB_FILE)
    for file in DB_FILE:
        _download_file(flget_cache_dir, file)
        progress_update(progress)


def decompress_dumps(progress_update: Callable[[float], None]):
    flget_cache_dir = platformdirs.user_cache_dir("flget", ensure_exists=True)
    progress = 100.0/len(DB_FILE)
    for file in DB_FILE:
        nongz_file = os.path.join(flget_cache_dir, os.path.splitext(file)[0])
        with GzipFile(os.path.join(flget_cache_dir,file), 'rb') as f_in:
            with open(nongz_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        progress_update(progress)


def db_import_dumps():
    flget_cache_dir = platformdirs.user_cache_dir("flget")

    con = mysql.connector.connect(user='root',
                                  password='mysql',
                                  host='localhost')
    db_cursor = con.cursor()
    db_cursor.execute('CREATE DATABASE IF NOT EXISTS flibusta')
    db_cursor.close()
    con.commit()
    con.close()

    for file in DB_FILE:
        fname = os.path.join(flget_cache_dir, os.path.splitext(file)[0])
        with open(fname, "rb") as f:
            subprocess.call(["/usr/bin/mysql", "-h", "127.0.0.1", "-u", "root", "--password=mysql", "-D", "flibusta" ], stdin=f)