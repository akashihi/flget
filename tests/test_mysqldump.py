import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from flget import mysqldump
from flget.mysqldump import load_dump

# Trimmed from a real Flibusta dump: header comments, /*! */ hints, a DROP, key
# lines in the CREATE body and LOCK TABLES around the data are all noise the
# loader has to skip.
DUMP = r"""-- MySQL dump 10.13  Distrib 8.0.36, for Linux (x86_64)
--
-- Host: localhost    Database: flibusta
-- ------------------------------------------------------
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!50503 SET NAMES utf8mb4 */;

--
-- Table structure for table `libseqname`
--

DROP TABLE IF EXISTS `libseqname`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE `libseqname` (
  `SeqId` int unsigned NOT NULL AUTO_INCREMENT,
  `SeqName` varchar(254) CHARACTER SET utf8mb3 NOT NULL DEFAULT '',
  `Rate` decimal(4,2) DEFAULT NULL,
  `Blob` blob,
  PRIMARY KEY (`SeqId`),
  UNIQUE KEY `SeqName` (`SeqName`),
  KEY `Rate` (`Rate`)
) ENGINE=MyISAM AUTO_INCREMENT=100 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `libseqname`
--

LOCK TABLES `libseqname` WRITE;
/*!40000 ALTER TABLE `libseqname` DISABLE KEYS */;
INSERT INTO `libseqname` VALUES (1,'Плоский мир',4.5,NULL),(2,'It\'s; a \"test\"\\',-1,0x48690A),
(3,'',0,0x);
INSERT INTO `libseqname` VALUES (4,'line\nbreak\ttab\0nul\Zsub\q',1e3,NULL);
/*!40000 ALTER TABLE `libseqname` ENABLE KEYS */;
UNLOCK TABLES;
"""

ROWS = [
    (1, "Плоский мир", 4.5, None),
    (2, 'It\'s; a "test"\\', -1, b"Hi\n"),
    (3, "", 0, b""),
    (4, "line\nbreak\ttab\0nul\x1asubq", 1000.0, None),
]


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(":memory:")) as c:
        yield c


def load(conn: sqlite3.Connection, path: Path, text: str) -> list[tuple[Any, ...]]:
    path.write_text(text, encoding="utf-8")
    load_dump(conn, path)
    return conn.execute("SELECT * FROM libseqname ORDER BY SeqId").fetchall()


def test_load_dump(conn: sqlite3.Connection, tmp_path: Path) -> None:
    assert load(conn, tmp_path / "dump.sql", DUMP) == ROWS
    columns = [r[1] for r in conn.execute("PRAGMA table_info(libseqname)")]
    assert columns == ["SeqId", "SeqName", "Rate", "Blob"]


# Small chunks split statements, strings and escape sequences across reads.
@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 64])
def test_load_dump_across_chunk_boundaries(
    conn: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    chunk: int,
) -> None:
    monkeypatch.setattr(mysqldump, "_CHUNK", chunk)
    assert load(conn, tmp_path / "dump.sql", DUMP) == ROWS


def test_create_table_replaces_existing(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    conn.execute('CREATE TABLE libseqname ("Old")')
    conn.execute("INSERT INTO libseqname VALUES ('stale')")
    assert load(conn, tmp_path / "dump.sql", DUMP) == ROWS


def test_identifier_quotes_are_escaped(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    path = tmp_path / "dump.sql"
    path.write_text(
        'CREATE TABLE `we"ird` (\n  `a"b` int\n);\n'
        'INSERT INTO `we"ird` VALUES (1),(2);\n',
        encoding="utf-8",
    )
    load_dump(conn, path)
    assert conn.execute('SELECT "a""b" FROM "we""ird"').fetchall() == [(1,), (2,)]


def test_invalid_utf8_is_replaced(conn: sqlite3.Connection, tmp_path: Path) -> None:
    path = tmp_path / "dump.sql"
    path.write_bytes(
        b"CREATE TABLE `t` (\n  `v` text\n);\nINSERT INTO `t` VALUES ('a\xffb');\n"
    )
    load_dump(conn, path)
    assert conn.execute("SELECT v FROM t").fetchall() == [("a�b",)]
