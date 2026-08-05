"""Stream a mysqldump ``.sql`` file straight into an open SQLite connection.

The Flibusta DB dumps are standard ``mysqldump`` output: backtick-quoted
identifiers, single-quoted string literals with backslash escaping, ``NULL``
for missing values and ``0x...`` literals for binary blobs. We only care about
``CREATE TABLE`` (to learn the column order) and ``INSERT INTO ... VALUES``
(the data); everything else (comments, ``LOCK TABLES``, ``/*!... */`` hints) is
ignored.

Values are re-bound through parameterised ``executemany`` calls, so we never
re-serialise data back into SQL text -- escaping and injection are non-issues.
"""

import re
import sqlite3
from pathlib import Path
from typing import Any

# When scanning *outside* a string we only care about the next quote (string
# start) or the statement terminator. When *inside* a string we care about the
# next quote (string end) or backslash (escape). Jumping between these with
# ``re.search`` lets us skip long runs of text cheaply instead of looping char
# by char over ~1.4 GB of dumps.
_OUTSIDE = re.compile(r"['\;]")
_INSIDE = re.compile(r"['\\]")

_CREATE_RE = re.compile(
    r"\s*CREATE\s+TABLE\s+`([^`]+)`\s*\((.*)\)[^)]*$", re.DOTALL | re.IGNORECASE
)
_INSERT_RE = re.compile(r"\s*INSERT\s+INTO\s+`([^`]+)`\s+VALUES\s*", re.IGNORECASE)
_COLUMN_RE = re.compile(r"^`([^`]+)`")

# MySQL backslash escape sequences. Anything not listed maps to itself
# (``\x`` -> ``x``), which matches MySQL's behaviour.
_UNESCAPE = {
    "0": "\0",
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "\\": "\\",
    "'": "'",
    '"': '"',
}

_CHUNK = 1 << 22  # 4 MiB


class _DumpLoader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._buf = ""

    def feed(self, chunk: str) -> None:
        self._buf += chunk
        self._drain(final=False)

    def close(self) -> None:
        # Flush whatever is left; a well-formed dump ends on a terminator so
        # nothing meaningful should remain, but be defensive.
        self._drain(final=True)

    def _drain(self, final: bool) -> None:
        buf = self._buf
        pos = 0
        while True:
            end = _find_statement_end(buf, pos)
            if end == -1:
                break
            self._dispatch(buf[pos:end])
            pos = end + 1
        self._buf = buf[pos:]

    def _dispatch(self, statement: str) -> None:
        head = statement.lstrip()[:12].upper()
        if head.startswith("INSERT INTO"):
            self._insert(statement)
        elif head.startswith("CREATE TABLE"):
            self._create(statement)

    def _create(self, statement: str) -> None:
        m = _CREATE_RE.match(statement)
        if not m:
            return
        table = m.group(1)
        columns = _parse_columns(m.group(2))
        if not columns:
            return
        cols_sql = ", ".join(f'"{c}"' for c in columns)
        self._conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        self._conn.execute(f'CREATE TABLE "{table}" ({cols_sql})')

    def _insert(self, statement: str) -> None:
        m = _INSERT_RE.match(statement)
        if not m:
            return
        table = m.group(1)
        rows = _parse_values(statement, m.end())
        if not rows:
            return
        placeholders = ", ".join("?" * len(rows[0]))
        self._conn.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)


def load_dump(conn: sqlite3.Connection, path: Path) -> None:
    """Import one decompressed mysqldump ``.sql`` file into ``conn``."""
    loader = _DumpLoader(conn)
    with path.open(encoding="utf-8", errors="replace") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            loader.feed(chunk)
    loader.close()


def _find_statement_end(buf: str, pos: int) -> int:
    """Index of the next unquoted ``;`` at/after ``pos``, or -1 if the buffer
    ends mid-statement (caller should read more and retry from ``pos``)."""
    i = pos
    in_string = False
    while True:
        if not in_string:
            m = _OUTSIDE.search(buf, i)
            if m is None:
                return -1
            if m.group() == ";":
                return m.start()
            in_string = True
            i = m.end()
        else:
            m = _INSIDE.search(buf, i)
            if m is None:
                return -1
            if m.group() == "'":
                in_string = False
                i = m.end()
            else:  # backslash: skip the escaped character
                i = m.end() + 1


def _parse_columns(body: str) -> list[str]:
    """Column names, in declaration order, from a CREATE TABLE body.

    mysqldump puts every column and key on its own line; column definitions
    start with a backtick-quoted name, key/constraint lines start with a
    keyword (PRIMARY KEY, UNIQUE KEY, KEY, CONSTRAINT, ...). We keep the
    former and skip the latter.
    """
    columns = []
    for line in body.splitlines():
        m = _COLUMN_RE.match(line.strip())
        if m:
            columns.append(m.group(1))
    return columns


def _parse_values(s: str, start: int) -> list[list[Any]]:
    """Parse the ``(...),(...),...`` tuples following ``VALUES`` into rows."""
    rows: list[list[Any]] = []
    i = start
    n = len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":
            i += 1
        if i >= n or s[i] != "(":
            break
        i += 1
        row: list[Any] = []
        while True:
            while i < n and s[i] in " \t\r\n":
                i += 1
            c = s[i]
            if c == ")":
                i += 1
                break
            if c == "'":
                value, i = _read_string(s, i)
                row.append(value)
            else:
                j = i
                while s[j] not in ",)":
                    j += 1
                row.append(_parse_scalar(s[i:j].strip()))
                i = j
            while i < n and s[i] in " \t\r\n":
                i += 1
            if s[i] == ",":
                i += 1
            elif s[i] == ")":
                i += 1
                break
        rows.append(row)
    return rows


def _read_string(s: str, i: int) -> tuple[str, int]:
    """Read a single-quoted MySQL string starting at ``s[i] == "'"``."""
    i += 1  # past the opening quote
    parts: list[str] = []
    while True:
        m = _INSIDE.search(s, i)
        assert m is not None  # statement is complete, so the string closes
        parts.append(s[i : m.start()])
        if m.group() == "'":
            return "".join(parts), m.end()
        esc = s[m.end()]
        parts.append(_UNESCAPE.get(esc, esc))
        i = m.end() + 1


def _parse_scalar(token: str) -> Any | None:
    if token == "NULL":
        return None
    if token[:2] in ("0x", "0X"):
        return bytes.fromhex(token[2:])
    if _INT_RE.match(token):
        return int(token)
    try:
        return float(token)
    except ValueError:
        return token


_INT_RE = re.compile(r"-?\d+$")
