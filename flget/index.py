import platformdirs
import os

from whoosh import index, writing
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import Schema, TEXT, ID, NUMERIC
from whoosh.index import FileIndex
from whoosh.qparser import QueryParser

from inpx import BookEntry
from inpx import INPX


def _open_index(index_name: str, schema: Schema) -> FileIndex:
    book_index_path = os.path.join(platformdirs.user_cache_dir("flget", ensure_exists=True), "index")
    if not os.path.exists(book_index_path):
        os.makedirs(book_index_path)
    if not index.exists_in(book_index_path, indexname=index_name):
        ix = index.create_in(book_index_path, schema, indexname=index_name)
    else:
        ix = index.open_dir(book_index_path, indexname=index_name)
    return ix


class BookIndex:
    def __init__(self):
        self._book_schema = Schema(title=TEXT(analyzer=StemmingAnalyzer(), stored=True), lib_id=ID(stored=True))
        self._author_schema = Schema(author=TEXT(analyzer=StemmingAnalyzer(), stored=True), author_id=ID(stored=True),
                                     no_books=NUMERIC(stored=True), no_series=NUMERIC(stored=True))
        self._series_schema = Schema(series=TEXT(analyzer=StemmingAnalyzer(), stored=True), series_id=ID(stored=True),
                                     no_books=NUMERIC(stored=True), no_authors=NUMERIC(stored=True))

        self._book_index = _open_index("book", self._book_schema)
        self._author_index = _open_index("author", self._author_schema)
        self._series_index = _open_index("series", self._series_schema)

    def create_index(self, inpx: INPX):
        a_writer = self._author_index.writer()
        a_writer.commit(mergetype=writing.CLEAR)
        a_writer = self._author_index.writer(procs=32, multisegment=True)
        for author in inpx.authors():
            a_writer.add_document(author=author.name, author_id=str(author.id), no_books=author.books, no_series=author.series)
        a_writer.commit()

        s_writer = self._series_index.writer()
        s_writer.commit(mergetype=writing.CLEAR)
        s_writer = self._series_index.writer(procs=32, multisegment=True)
        for s in inpx.series():
            s_writer.add_document(series=s.name, series_id=str(s.id), no_books=s.books, no_authors=s.authors)
        s_writer.commit()

        b_writer = self._book_index.writer()
        b_writer.commit(mergetype=writing.CLEAR)
        b_writer = self._book_index.writer(procs=32, multisegment=True)
        for lib_id, book in inpx.items():
            b_writer.add_document(title=book.title, lib_id=lib_id)
        b_writer.commit()

    def search_books(self, query: str) -> list[BookEntry]:
        qp = QueryParser("title", schema=self._book_schema)
        q = qp.parse(query)
        with self._book_index.searcher() as searcher:
            results = searcher.search(q)
            entries = [
                BookEntry(None, None, e["title"], None, None, None, None, e["lib_id"], None, None, None, None, None,
                          None, None) for e in results]
            return entries
