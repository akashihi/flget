from typing import Optional, cast

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    TabbedContent,
    TabPane,
    Tabs,
)
from textual.worker import Worker, WorkerState, get_current_worker

from flget.config import Config
from flget.filters import BookFilter
from flget.tui_authors_tab import AuthorsWidget
from flget.tui_book_view import BookViewWidget
from flget.tui_filter_screen import FilterScreen
from flget.tui_series_tab import SeriesWidget
from flget.tui_book_table import BookTable
from flget.inpx import BookEntry
from flget.tui_save_screen import SaveScreen
from flget.library import TheLibrary

# Debounce policy for search-as-you-type
SHORT_LEN = 3
LONG_DEBOUNCE = 2.0
SHORT_DEBOUNCE = 0.3
SEARCH_GROUP = "search"


class FlTui(App):
    CSS_PATH = "fltui.tcss"
    BINDINGS = [
        ("ctrl+s", "save", "Save book"),
        ("ctrl+y", "sync", "Sync mirror"),
        ("ctrl+o", "options", "Set options"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()

        self._config = Config()
        self._library = TheLibrary(self._config)

        self._books_table = BookTable(widget_id="books-table", library=self._library)
        self._series_view = SeriesWidget(self._library)
        self._authors_view = AuthorsWidget(self._library)

        self._book_info = BookViewWidget(self._library)

        self._selected_book: Optional[BookEntry] = None
        self._book_filter: BookFilter = BookFilter()
        self._current_query: str = ""
        self._search_timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar"):
            yield Input(placeholder="Search...", id="search-input")
            yield Button("Filter", id="filter-books", variant="primary")

        with TabbedContent():
            with TabPane("Books", id="tab-books"):
                yield self._books_table
            with TabPane("Authors", id="tab-authors"):
                yield self._authors_view
            with TabPane("Series", id="tab-series"):
                yield self._series_view

        yield self._book_info

        yield Footer()

    async def action_quit(self) -> None:
        self.exit()

    @work
    async def action_save(self) -> None:
        if self._selected_book:
            await self.push_screen_wait(
                SaveScreen(self, self._library, self._selected_book)
            )

    @work
    @on(Button.Pressed, "#filter-books")
    async def action_filter(self) -> None:
        result = await self.push_screen_wait(
            FilterScreen(self, self._library, self._book_filter)
        )
        if result is not None:  # None == cancelled
            self._book_filter = result
            self._update_filter_indicator()
            self._start_search()

    def _update_filter_indicator(self) -> None:
        btn = self.query_one("#filter-books", Button)
        if self._book_filter.is_empty():
            btn.variant = "primary"
            btn.label = "Filter"
        else:
            btn.variant = "warning"
            btn.label = "Filter ✓"

    def _result_widget(self, active: str) -> Widget:
        if active == "tab-series":
            return self._series_view
        if active == "tab-authors":
            return self._authors_view
        return self._books_table

    def _populate_results(self, active: str, results: list) -> None:
        if active == "tab-books":
            self._books_table.populate(results)
        elif active == "tab-series":
            self._series_view.populate(results)
        elif active == "tab-authors":
            self._authors_view.populate(results)

    def _search_running(self) -> bool:
        return any(
            worker.group == SEARCH_GROUP
            and worker.state in (WorkerState.PENDING, WorkerState.RUNNING)
            for worker in self.workers
        )

    def _schedule_search(self) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
            self._search_timer = None

        query = self._current_query
        if len(query) == 0:
            # Empty box: abort any in-flight search, clear results, unblock tabs.
            self.workers.cancel_group(self, SEARCH_GROUP)
            active = self.query_one(TabbedContent).active
            self._populate_results(active, [])
            self.query_one(Tabs).disabled = False
            for widget in (self._books_table, self._series_view, self._authors_view):
                widget.loading = False
            return

        delay = LONG_DEBOUNCE if len(query) <= SHORT_LEN else SHORT_DEBOUNCE
        self._search_timer = self.set_timer(delay, self._start_search)

    def _start_search(self) -> None:
        active = self.query_one(TabbedContent).active
        # Block tab switching and show a loading state while the search runs.
        self.query_one(Tabs).disabled = True
        self._result_widget(active).loading = True
        self._search_worker(active, self._current_query, self._book_filter)

    @work(thread=True, exclusive=True, group=SEARCH_GROUP)
    def _search_worker(
        self, active: str, query: str, book_filter: BookFilter
    ) -> tuple[str, list]:
        worker = get_current_worker()
        is_cancelled = worker.cancelled_event.is_set
        if active == "tab-series":
            return active, self._library.search_series(query, book_filter, is_cancelled)
        if active == "tab-authors":
            return active, self._library.search_authors(
                query, book_filter, is_cancelled
            )
        return active, self._library.search_books(query, book_filter, is_cancelled)

    @on(Worker.StateChanged)
    def on_search_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker.group != SEARCH_GROUP:
            return
        if event.state == WorkerState.SUCCESS:
            active, results = cast(tuple[str, list], event.worker.result)
            self._populate_results(active, results)
        if event.state in (
            WorkerState.SUCCESS,
            WorkerState.CANCELLED,
            WorkerState.ERROR,
        ):
            # Re-enable tab switching only once no search is left running, so a
            # superseding search keeps the tabs blocked.
            if not self._search_running():
                self.query_one(Tabs).disabled = False
                for widget in (
                    self._books_table,
                    self._series_view,
                    self._authors_view,
                ):
                    widget.loading = False

    @on(Input.Changed, "#search-input")
    def on_search_input(self, event: Input.Changed) -> None:
        self._current_query = event.value
        self._schedule_search()

    @on(DataTable.RowHighlighted, "BookTable")
    def on_book_select(self, event: DataTable.RowHighlighted) -> None:
        table = cast(BookTable, event.data_table)
        book_id = table.book_id(event.row_key)
        if book_id is not None:
            search_result = self._library.get_books([book_id])
            if search_result:
                book = search_result[0]
                self._book_info.update(book)
                self._selected_book = book
            else:
                self._selected_book = None
        else:
            self._selected_book = None


def main():
    app = FlTui()
    app.run()


if __name__ == "__main__":
    main()
