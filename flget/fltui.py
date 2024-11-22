from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Input, TabbedContent, TabPane, Markdown, DataTable

from config import Config
from tui_authors_tab import AuthorsWidget
from tui_series_tab import SeriesWidget
from tui_book_table import BookTable
from inpx import BookEntry
from tui_save_screen import SaveScreen
from library import TheLibrary


class FlTui(App):
    CSS_PATH = "fltui.tcss"
    BINDINGS = [("ctrl+s", "save", "Save book"), ("ctrl+y", "sync", "Sync mirror"),
                ("ctrl+o", "options", "Set options"), ("escape", "quit", "Quit")]

    def __init__(self):
        super().__init__()

        self._config = Config()
        self._library = TheLibrary(self._config)

        self._books_table = BookTable(widget_id="books-table")
        self._series_view = SeriesWidget(self._library)
        self._authors_view = AuthorsWidget(self._library)

        self._book_info = Markdown("Book info")

        self._selected_book:Optional[BookEntry] = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search...", id="search-input")

        with TabbedContent():
            with TabPane("Books", id="tab-books"):
                yield self._books_table
            with TabPane("Authors", id="tab-authors"):
                yield self._authors_view
            with TabPane("Series", id="tab-series"):
                yield self._series_view

        yield self._book_info

        yield Footer()

    def action_quit(self) -> None:
        self.exit()

    @work
    async def action_save(self) -> None:
        if self._selected_book:
            await self.push_screen_wait(SaveScreen(self, self._library, self._selected_book))

    @on(Input.Changed, "#search-input")
    def on_search_input(self, event: Input.Changed) -> None:
        if self.query_one(TabbedContent).active == "tab-books":
            results = self._library.search_books(event.value)
            self._books_table.populate(results)
        elif self.query_one(TabbedContent).active == "tab-series":
            results = self._library.search_series(event.value)
            self._series_view.populate(results)
        elif self.query_one(TabbedContent).active == "tab-authors":
            results = self._library.search_authors(event.value)
            self._authors_view.populate(results)

    @on(DataTable.RowHighlighted, "BookTable")
    def on_book_select(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            book = self._library.get_book(int(event.row_key.value))
            self._book_info.update(book.title)
            self._selected_book = book
        else:
            self._selected_book = None


if __name__ == "__main__":
    app = FlTui()
    app.run()
