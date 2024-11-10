from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Footer, Input, TabbedContent, TabPane, Markdown, DataTable

from config import Config
from library import TheLibrary


class FlTui(App):
    CSS_PATH = "fltui.tcss"
    BINDINGS = [("ctrl+s","save","Save book"), ("ctrl+y", "sync", "Sync mirror"), ("ctrl+o", "options", "Set options"), ("escape", "quit", "Quit")]

    def __init__(self):
        super().__init__()

        self._config = Config()
        self._library = TheLibrary(self._config)

        self._books_table = DataTable(cursor_type="row")

        self._book_info = Markdown("Book info")

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search...", id="search-input")

        with TabbedContent():
            with TabPane("Books",):
                yield self._books_table
            with TabPane("Authors",):
                yield Input(placeholder="Authors...")
            with TabPane("Series",):
                yield Input(placeholder="Series...")

        yield self._book_info

        yield Footer()

    def on_mount(self) -> None:
        self._books_table.add_columns("ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language")
        self._books_table.add_row(1,"Wool", "Howy", "SF,POSTAP","5","Silo","en")
        self._books_table.add_row(2, "Dust", "Howy", "SF,POSTAP", "4", "Silo", "en")

    def action_quit(self) -> None:
        self.exit()

    @on(Input.Changed,"#search-input")
    def on_search_input(self, event: Input.Changed) -> None:
        results = self._library.search_books(event.value)
        self._books_table.clear()
        for result in results:
            self._books_table.add_row(result.lib_id, result.title, ",".join(result.authors), result.genres, result.rating, result.keywords, result.lang)


if __name__ == "__main__":
    app = FlTui()
    app.run()