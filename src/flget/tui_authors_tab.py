from textual import on, work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable
from textual.worker import get_current_worker

from flget.library import TheLibrary
from flget.inpx import AuthorEntry
from flget.tui_book_table import BookTable


class AuthorsWidget(Widget):
    def __init__(self, library: TheLibrary):
        super().__init__()

        self._library = library

        self._authors_table: DataTable[str] = DataTable(
            cursor_type="row", id="authors-table"
        )
        self._books_table = BookTable(widget_id="authors-books-table", library=library)

    def compose(self) -> ComposeResult:
        yield self._authors_table
        yield self._books_table

    def on_mount(self) -> None:
        self._authors_table.add_columns("ID", "Name", "Books", "Series")

    def populate(self, authors: list[AuthorEntry]) -> None:
        self._authors_table.clear()
        for entry in authors:
            self._authors_table.add_row(
                str(entry.id),
                entry.name,
                str(entry.books),
                str(entry.series),
                key=str(entry.id),
            )

    @on(DataTable.RowHighlighted, "#authors-table")
    def on_author_select(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            self._load_author_books(int(event.row_key.value))

    @work(thread=True, exclusive=True, group="author-detail")
    def _load_author_books(self, author_id: int) -> None:
        worker = get_current_worker()
        is_cancelled = worker.cancelled_event.is_set
        books = []
        for series_id in self._library.get_author_series(author_id):
            if is_cancelled():
                return
            books += self._library.get_series(series_id, is_cancelled)
        books += self._library.get_author_books(author_id, is_cancelled)
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._books_table.populate, books)
