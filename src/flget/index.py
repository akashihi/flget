from typing import Optional, Callable

import platformdirs
import os

from whoosh import index, writing
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import Schema, TEXT, ID, NUMERIC, KEYWORD
from whoosh.index import FileIndex
from whoosh.qparser import QueryParser
from whoosh.searching import Hit

from flget.mirror import SeriesEntry
from flget.mirror import AuthorEntry
from flget.mirror import BookEntry
from flget.mirror import Mirror


def _open_index(index_name: str, schema: Schema) -> FileIndex:
    book_index_path = os.path.join(
        platformdirs.user_cache_dir("flget", ensure_exists=True), "index"
    )
    if not os.path.exists(book_index_path):
        os.makedirs(book_index_path)
    if not index.exists_in(book_index_path, indexname=index_name):
        ix = index.create_in(book_index_path, schema, indexname=index_name)
    else:
        ix = index.open_dir(book_index_path, indexname=index_name)
    return ix


def _book_result_to_entry(book_result: Hit) -> BookEntry:
    return BookEntry(
        book_result["authors"].split(","),
        [],
        book_result["genres"].split(" "),
        book_result["title"],
        book_result["series"].split(","),
        [int(x) for x in book_result["serno"].split(",")],
        None,
        None,
        book_result["lib_id"],
        None,
        None,
        None,
        book_result["lang"],
        book_result["rating"],
        book_result["keywords"].split(","),
        None,
    )


class BookIndex:
    def __init__(self):
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

    def create_index(self, mirror: Mirror, progress__update: Callable[[float], None]):
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
                series=book.series,
                serno=str(book.serno),
            )
        b_writer.commit()

    def search_authors(self, query: str) -> list[AuthorEntry]:
        qp = QueryParser("author", schema=self._author_schema)
        q = qp.parse(query)
        with self._author_index.searcher() as searcher:
            results = searcher.search(q, limit=None, sortedby="no_books", reverse=True)
            entries = [
                AuthorEntry(
                    e["author_id"],
                    e["author"],
                    e["no_books"],
                    e["no_series"] if "no_series" in e else "",
                )
                for e in results
            ]
            return entries

    def suggest_authors(self, query: str) -> Optional[str]:
        qp = QueryParser("author", schema=self._author_schema)
        q = qp.parse(query)
        with self._author_index.searcher() as searcher:
            corrected = searcher.correct_query(q, query)
            if corrected.query != q:
                return corrected.string
            else:
                return None

    def search_series(self, query: str) -> list[SeriesEntry]:
        qp = QueryParser("series", schema=self._series_schema)
        q = qp.parse(query)
        with self._series_index.searcher() as searcher:
            results = searcher.search(q, limit=None, sortedby="no_books", reverse=True)
            entries = [
                SeriesEntry(e["series_id"], e["series"], e["no_books"], e["no_authors"])
                for e in results
            ]
            return entries

    def suggest_series(self, query: str) -> Optional[str]:
        qp = QueryParser("series", schema=self._series_schema)
        q = qp.parse(query)
        with self._series_index.searcher() as searcher:
            corrected = searcher.correct_query(q, query)
            if corrected.query != q:
                return corrected.string
            else:
                return None

    def search_books(self, query: str) -> list[BookEntry]:
        qp = QueryParser("title", schema=self._book_schema)
        q = qp.parse(query)
        with self._book_index.searcher() as searcher:
            results = searcher.search(q, limit=None, sortedby="rating", reverse=True)
            entries = [_book_result_to_entry(e) for e in results]
            return entries

    def get_books(self, book_ids: list[int]) -> list[BookEntry]:
        result = []
        with self._book_index.searcher() as searcher:
            for book_id in book_ids:
                book = searcher.document(lib_id=str(book_id))
                if book is not None:
                    result.append(_book_result_to_entry(book))
        return result
