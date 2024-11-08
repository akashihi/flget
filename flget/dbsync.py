from gzip import GzipFile
from io import TextIOWrapper

import requests
import os
import platformdirs
import sqlite3

FLIBUSTA_DB_PAGE = "https://flibusta.is/sql/{}"
DB_FILE = [
    "lib.libavtor.sql.gz",
    "lib.libtranslator.sql.gz",
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


def get_dumps():
    flget_cache_dir = platformdirs.user_cache_dir("flget", ensure_exists=True)
    #    if not os.path.exists(flget_cache_dir):
    #        os.makedirs(flget_cache_dir)
    for file in DB_FILE:
        _download_file(flget_cache_dir, file)


def db_import_dumps():
    flget_cache_dir = platformdirs.user_cache_dir("flget")
    tmp_dir = platformdirs.site_runtime_dir("flget", ensure_exists=True)
    tmp_db_path = os.path.join(tmp_dir, "tmp_db.sqlite3")
    con = sqlite3.connect(tmp_db_path)
    with GzipFile("~/.cache/flget/lib.libbook.sql.gz", "r") as dbfile:
        con.cursor().executescript(TextIOWrapper(dbfile).read())
