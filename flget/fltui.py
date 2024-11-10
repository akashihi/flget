from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Input, TabbedContent, TabPane, Markdown, DataTable

from config import Config
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

        self._books_table = DataTable(cursor_type="row", id="books-table")

        self._book_info = Markdown("Book info")

        self._selected_book:Optional[BookEntry] = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search...", id="search-input")

        with TabbedContent():
            with TabPane("Books", ):
                yield self._books_table
            with TabPane("Authors", ):
                yield Input(placeholder="Authors...")
            with TabPane("Series", ):
                yield Input(placeholder="Series...")

        yield self._book_info

        yield Footer()

    def on_mount(self) -> None:
        self._books_table.add_columns("ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language")


    def action_quit(self) -> None:
        self.exit()

    @work
    async def action_save(self) -> None:
        if self._selected_book:
            await self.push_screen_wait(SaveScreen(self, self._library, self._selected_book))

    @on(Input.Changed, "#search-input")
    def on_search_input(self, event: Input.Changed) -> None:
        results = self._library.search_books(event.value)
        self._books_table.clear()
        for result in results:
            self._books_table.add_row(result.lib_id, result.title, ",".join(result.authors), result.genres,
                                      result.rating, result.keywords, result.lang, key=str(result.lib_id))

    @on(DataTable.RowHighlighted, "#books-table")
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
