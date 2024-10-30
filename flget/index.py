import platformdirs
import os

from whoosh import index, writing
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import QueryParser

from inpx import BookEntry
from inpx import INPX


class TheIndex:
    def __init__(self):
        self._book_schema = Schema(title=TEXT(analyzer=StemmingAnalyzer(), stored=True), lib_id=ID(stored=True))

        book_index_path = os.path.join(platformdirs.user_cache_dir("flget", ensure_exists=True), "index")
        if not os.path.exists(book_index_path):
            os.makedirs(book_index_path)
        if not index.exists_in(book_index_path, indexname="book"):
            book_ix = index.create_in(book_index_path, self._book_schema, indexname="book")
        else:
            book_ix = index.open_dir(book_index_path, indexname="book")
        self._book_index = book_ix


    def create_index(self, inpx: INPX):
        writer = self._book_index.writer()
        writer.commit(mergetype=writing.CLEAR)
        writer = self._book_index.writer()
        for lib_id,book in inpx.items():
            writer.add_document(title=book.title, lib_id=lib_id)
        writer.commit()

    def search_books(self, query: str) -> list[BookEntry]:
        qp = QueryParser("title", schema=self._book_schema)
        q = qp.parse(query)
        with self._book_index.searcher() as searcher:
            results = searcher.search(q)
            entries = [BookEntry(None, None, e["title"], None, None, None, None,e["lib_id"], None, None, None, None, None, None, None) for e in results]
            return entries

