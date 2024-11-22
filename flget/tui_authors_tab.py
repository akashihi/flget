from textual import on
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable

from library import TheLibrary
from inpx import AuthorEntry
from tui_book_table import BookTable


class AuthorsWidget(Widget):
    def __init__(self, library: TheLibrary):
        super().__init__()

        self._library = library

        self._authors_table = DataTable(cursor_type="row", id="authors-table")
        self._books_table = BookTable(widget_id="authors-books-table")

    def compose(self) -> ComposeResult:
        yield self._authors_table
        yield self._books_table

    def on_mount(self) -> None:
        self._authors_table.add_columns("ID", "Name", "Books", "Series")

    def populate(self, authors: list[AuthorEntry]) -> None:
        print(authors)
        self._authors_table.clear()
        for entry in authors:
            self._authors_table.add_row(str(entry.id), entry.name, str(entry.books), str(entry.series), key=str(entry.id))

    @on(DataTable.RowHighlighted, "#authors-table")
    def on_author_select(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            books = []
            series_ids = self._library.get_author_series(event.row_key.value)
            for series_id in series_ids:
                books += self._library.get_series(series_id)
            books += self._library.get_author_books(event.row_key.value)
            self._books_table.populate(books)
