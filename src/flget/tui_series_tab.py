from textual import on, work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable
from textual.worker import get_current_worker

from flget.library import TheLibrary
from flget.inpx import SeriesEntry
from flget.tui_book_table import BookTable


class SeriesWidget(Widget):
    def __init__(self, library: TheLibrary):
        super().__init__()

        self._library = library

        self._series_table: DataTable[str] = DataTable(
            cursor_type="row", id="series-table"
        )
        self._books_table = BookTable(widget_id="series-books-table", library=library)

    def compose(self) -> ComposeResult:
        yield self._series_table
        yield self._books_table

    def on_mount(self) -> None:
        self._series_table.add_columns("ID", "Name", "Books", "Authors")

    def populate(self, series: list[SeriesEntry]) -> None:
        self._series_table.clear()
        for entry in series:
            self._series_table.add_row(
                str(entry.id),
                entry.name,
                str(entry.books),
                str(entry.authors),
                key=str(entry.id),
            )

    @on(DataTable.RowHighlighted, "#series-table")
    def on_series_select(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            self._load_series_books(int(event.row_key.value))

    @work(thread=True, exclusive=True, group="series-detail")
    def _load_series_books(self, series_id: int) -> None:
        worker = get_current_worker()
        is_cancelled = worker.cancelled_event.is_set
        books = self._library.get_series(series_id, is_cancelled)
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._books_table.populate, books)
