from collections.abc import Callable
from pathlib import Path

import platformdirs
from whoosh import index, writing
from whoosh.analysis import StemmingAnalyzer
from whoosh.collectors import Collector, WrappingCollector
from whoosh.fields import ID, KEYWORD, NUMERIC, TEXT, Schema
from whoosh.index import FileIndex
from whoosh.qparser import QueryParser
from whoosh.query import And, FuzzyTerm, NullQuery, Or, Prefix, Query, Term
from whoosh.searching import Hit

from flget.mirror import AuthorEntry, BookEntry, Mirror, SeriesEntry


def _never_cancelled() -> bool:
    return False


# Tokens shorter than this are matched exactly (or as a prefix), never fuzzily
MIN_FUZZY_LEN = 4


def _build_search_query(schema: Schema, fieldname: str, qstring: str) -> Query:
    tokens = list(schema[fieldname].process_text(qstring, mode="query"))
    if not tokens:
        return NullQuery

    # A trailing space means the user finished the last word — no prefix then.
    prefix_last = not qstring[-1].isspace()
    last = len(tokens) - 1
    parts: list[Query] = []
    for i, token in enumerate(tokens):
        alternatives: list[Query] = [Term(fieldname, token)]
        if len(token) >= MIN_FUZZY_LEN:
            alternatives.append(FuzzyTerm(fieldname, token, maxdist=1, prefixlength=1))
        if i == last and prefix_last:
            alternatives.append(Prefix(fieldname, token))
        parts.append(Or(alternatives))
    return parts[0] if len(parts) == 1 else And(parts)


class SearchCancelled(Exception):  # noqa: N818 - control flow, not an error
    """Raised by :class:`_CancellableCollector` when the external cancellation
    flag is set, aborting an in-flight Whoosh search."""


class CancellableCollector(WrappingCollector):
    """Wraps another collector and aborts the search by raising
    :class:`SearchCancelled` whenever ``is_cancelled()`` returns ``True``.

    Modelled on Whoosh's ``TimeLimitCollector``: it delegates collection to the
    wrapped child (preserving sorting/limit behaviour) but polls the external
    flag between matched documents."""

    def __init__(self, child: Collector, is_cancelled: Callable[[], bool]) -> None:
        super().__init__(child)
        self._is_cancelled = is_cancelled

    def collect_matches(self) -> None:
        child = self.child
        for sub_docnum in child.matches():
            if self._is_cancelled():
                raise SearchCancelled
            child.collect(sub_docnum)


def _open_index(index_name: str, schema: Schema) -> FileIndex:
    book_index_path = (
        Path(platformdirs.user_cache_dir("flget", ensure_exists=True)) / "index"
    )
    book_index_path.mkdir(parents=True, exist_ok=True)
    # whoosh 2.7 predates os.PathLike support, so hand it a plain string.
    index_dir = str(book_index_path)
    if not index.exists_in(index_dir, indexname=index_name):
        ix = index.create_in(index_dir, schema, indexname=index_name)
    else:
        ix = index.open_dir(index_dir, indexname=index_name)
    return ix


def _book_result_to_entry(book_result: Hit) -> BookEntry:
    # The file-resolution fields (filename/filesize/deleted/ext/date/archive) are
    # None on an index-only entry; TheLibrary._refill_book fills them from files.db.
    return BookEntry(
        [],
        book_result["authors"].split(","),
        book_result["genres"].split(" "),
        book_result["title"],
        book_result["series"].split(",") if book_result["series"] else [],
        [int(x) for x in book_result["serno"].split(",")]
        if book_result["serno"]
        else [],
        None,
        None,
        int(book_result["lib_id"]),
        None,
        None,
        None,
        book_result["lang"],
        book_result["rating"],
        book_result["keywords"].split(","),
        None,
    )


class BookIndex:
    def __init__(self) -> None:
        self._book_schema = Schema(
            title=TEXT(analyzer=StemmingAnalyzer(), stored=True),
            lib_id=ID(stored=True),
            lang=ID(stored=True),
            rating=NUMERIC(stored=True, sortable=True),
            genres=KEYWORD(stored=True, scorable=True, lowercase=True),
            keywords=KEYWORD(stored=True, scorable=True, lowercase=True, commas=True),
            authors=ID(stored=True),
            series=ID(stored=True),
            serno=ID(stored=True),
        )
        self._author_schema = Schema(
            author=TEXT(analyzer=StemmingAnalyzer(), stored=True),
            author_id=ID(stored=True),
            no_books=NUMERIC(stored=True, sortable=True),
            no_series=NUMERIC(stored=True),
        )
        self._series_schema = Schema(
            series=TEXT(analyzer=StemmingAnalyzer(), stored=True),
            series_id=ID(stored=True),
            no_books=NUMERIC(stored=True, sortable=True),
            no_authors=NUMERIC(stored=True),
        )

        self._book_index = _open_index("book", self._book_schema)
        self._author_index = _open_index("author", self._author_schema)
        self._series_index = _open_index("series", self._series_schema)

    def create_index(
        self, mirror: Mirror, progress__update: Callable[[float], None]
    ) -> None:
        a_writer = self._author_index.writer()
        a_writer.commit(mergetype=writing.CLEAR)
        a_writer = self._author_index.writer(procs=32, multisegment=True)
        for author in mirror.authors():
            a_writer.add_document(
                author=author.name,
                author_id=str(author.id),
                no_books=author.books,
                no_series=author.series,
            )
        a_writer.commit()

        s_writer = self._series_index.writer()
        s_writer.commit(mergetype=writing.CLEAR)
        s_writer = self._series_index.writer(procs=32, multisegment=True)
        for s in mirror.series():
            s_writer.add_document(
                series=s.name,
                series_id=str(s.id),
                no_books=s.books,
                no_authors=s.authors,
            )
        s_writer.commit()

        b_writer = self._book_index.writer()
        b_writer.commit(mergetype=writing.CLEAR)
        b_writer = self._book_index.writer(procs=32, multisegment=True)

        progress = 50.0 / float(len(mirror.books()))
        for lib_id, book in mirror.books():
            progress__update(progress)
            clean_title = book.title.replace("[/", "[_/")
            b_writer.add_document(
                title=clean_title,
                lib_id=lib_id,
                lang=book.lang,
                rating=book.rating,
                genres=" ".join(book.genres),
                keywords=",".join(book.keywords),
                authors=",".join(book.author_names),
                series=",".join(book.series),
                serno=",".join(str(x) for x in book.serno),
            )
        b_writer.commit()

    def search_authors(
        self, query: str, is_cancelled: Callable[[], bool] = _never_cancelled
    ) -> list[AuthorEntry]:
        q = _build_search_query(self._author_schema, "author", query)
        with self._author_index.searcher() as searcher:
            collector = searcher.collector(
                limit=None, sortedby="no_books", reverse=True
            )
            cancellable = CancellableCollector(collector, is_cancelled)
            try:
                searcher.search_with_collector(q, cancellable)
            except SearchCancelled:
                return []
            return [
                AuthorEntry(
                    e["author_id"],
                    e["author"],
                    e["no_books"],
                    e.get("no_series", None),
                )
                for e in cancellable.results()
            ]

    def suggest_authors(self, query: str) -> str | None:
        qp = QueryParser("author", schema=self._author_schema)
        q = qp.parse(query)
        with self._author_index.searcher() as searcher:
            corrected = searcher.correct_query(q, query)
            if corrected.query != q:
                return str(corrected.string)
            return None

    def search_series(
        self, query: str, is_cancelled: Callable[[], bool] = _never_cancelled
    ) -> list[SeriesEntry]:
        q = _build_search_query(self._series_schema, "series", query)
        with self._series_index.searcher() as searcher:
            collector = searcher.collector(
                limit=None, sortedby="no_books", reverse=True
            )
            cancellable = CancellableCollector(collector, is_cancelled)
            try:
                searcher.search_with_collector(q, cancellable)
            except SearchCancelled:
                return []
            return [
                SeriesEntry(e["series_id"], e["series"], e["no_books"], e["no_authors"])
                for e in cancellable.results()
            ]

    def suggest_series(self, query: str) -> str | None:
        qp = QueryParser("series", schema=self._series_schema)
        q = qp.parse(query)
        with self._series_index.searcher() as searcher:
            corrected = searcher.correct_query(q, query)
            if corrected.query != q:
                return str(corrected.string)
            return None

    def search_books(
        self, query: str, is_cancelled: Callable[[], bool] = _never_cancelled
    ) -> list[BookEntry]:
        q = _build_search_query(self._book_schema, "title", query)
        with self._book_index.searcher() as searcher:
            collector = searcher.collector(limit=None, sortedby="rating", reverse=True)
            cancellable = CancellableCollector(collector, is_cancelled)
            try:
                searcher.search_with_collector(q, cancellable)
            except SearchCancelled:
                return []
            return [_book_result_to_entry(e) for e in cancellable.results()]

    def field_values(self, field: str) -> list[str]:
        with self._book_index.searcher() as searcher:
            return sorted(
                term.decode("utf-8") if isinstance(term, bytes) else term
                for term in searcher.lexicon(field)
            )

    def get_books(
        self,
        book_ids: list[int],
        is_cancelled: Callable[[], bool] = _never_cancelled,
    ) -> list[BookEntry]:
        result: list[BookEntry] = []
        with self._book_index.searcher() as searcher:
            for book_id in book_ids:
                if is_cancelled():
                    return result
                book = searcher.document(lib_id=str(book_id))
                if book is not None:
                    result.append(_book_result_to_entry(book))
        return result
