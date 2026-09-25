from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import DataTable, Label, Switch
from textual.worker import Worker, WorkerState, get_current_worker

from flget.library import TheLibrary
from flget.mirror import AuthorEntry, BookEntry
from flget.tui_book_table import BookTable


class AuthorsWidget(Widget):
    def __init__(self, library: TheLibrary):
        super().__init__()

        self._library = library

        self._authors_table: DataTable[str] = DataTable(
            cursor_type="row", id="authors-table"
        )
        self._author_only = Switch(value=False, id="author-only-switch")
        self._books_table = BookTable(widget_id="authors-books-table", library=library)
        self._author_id: int | None = None

    def compose(self) -> ComposeResult:
        yield self._authors_table
        with Horizontal(id="authors-series-mode"):
            yield self._author_only
            yield Label("This author only")
        yield self._books_table

    def on_mount(self) -> None:
        self._authors_table.add_columns("ID", "Name", "Books", "Series")

    def populate(self, authors: list[AuthorEntry]) -> None:
        self._author_id = None
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
            self._author_id = int(event.row_key.value)
            self._start_author_load(self._author_id, self._author_only.value)

    @on(Switch.Changed, "#author-only-switch")
    def on_author_only_changed(self, event: Switch.Changed) -> None:
        if self._author_id is not None:
            self._start_author_load(self._author_id, event.value)

    def _start_author_load(self, author_id: int, author_only: bool) -> None:
        self._books_table.loading = True
        self._load_author_books(author_id, author_only)

    def _author_load_running(self) -> bool:
        return any(
            worker.group == "author-detail"
            and worker.state in (WorkerState.PENDING, WorkerState.RUNNING)
            for worker in self.workers
        )

    @on(Worker.StateChanged)
    def on_author_load_state(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "author-detail":
            return
        # A superseding load keeps the overlay up until it finishes too.
        if (
            event.state
            in (WorkerState.SUCCESS, WorkerState.CANCELLED, WorkerState.ERROR)
            and not self._author_load_running()
        ):
            self._books_table.loading = False

    @work(thread=True, exclusive=True, group="author-detail")
    def _load_author_books(self, author_id: int, author_only: bool) -> None:
        worker = get_current_worker()
        is_cancelled = worker.cancelled_event.is_set
        named_series = sorted(
            (
                (self._library.get_series_name(series_id), series_id)
                for series_id in self._library.get_author_series(author_id)
            ),
            key=lambda pair: pair[0].casefold(),
        )
        groups: list[tuple[str, list[BookEntry]]] = []
        seen: set[int] = set()
        for name, series_id in named_series:
            if is_cancelled():
                return
            series_books = self._library.get_series(
                series_id, author_id if author_only else None, is_cancelled
            )
            if series_books:
                groups.append((name, series_books))
                seen.update(book.lib_id for book in series_books)
        other = [
            book
            for book in self._library.get_author_books(author_id, is_cancelled)
            if book.lib_id not in seen
        ]
        other.sort(key=lambda book: book.title.casefold())
        if other:
            groups.append(("Other books", other))
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._books_table.populate_grouped, groups)
