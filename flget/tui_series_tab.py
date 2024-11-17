from textual import on
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable

from library import TheLibrary
from inpx import SeriesEntry
from tui_book_table import BookTable


class SeriesWidget(Widget):
    def __init__(self, library: TheLibrary):
        super().__init__()

        self._library = library

        self._series_table = DataTable(cursor_type="row", id="series-table")
        self._books_table = BookTable(widget_id="series-books-table")

    def compose(self) -> ComposeResult:
        yield self._series_table
        yield self._books_table

    def on_mount(self) -> None:
        self._series_table.add_columns("ID", "Name", "Books", "Authors")

    def populate(self, series: list[SeriesEntry]) -> None:
        self._series_table.clear()
        for entry in series:
            self._series_table.add_row(str(entry.id), entry.name, str(entry.books), str(entry.authors), key=str(entry.id))

    @on(DataTable.RowHighlighted, "#series-table")
    def on_series_select(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            books = self._library.get_series(int(event.row_key.value))
            self._books_table.populate(books)
