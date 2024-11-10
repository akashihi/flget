from textual.app import App, ComposeResult
from textual.widgets import Footer, Input, TabbedContent, TabPane, Markdown, DataTable


class FlTui(App):
    CSS_PATH = "fltui.tcss"
    BINDINGS = [("Ctrl+s","save","Save book"), ("Ctrl+Y", "sync", "Sync mirror"), ("Ctrl+O", "options", "Set options"), ("Esc", "quit", "Quit")]

    def __init__(self):
        super().__init__()

        self._books_table = DataTable(cursor_type="row")

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search...")

        with TabbedContent():
            with TabPane("Books",):
                yield self._books_table
            with TabPane("Authors",):
                yield Input(placeholder="Authors...")
            with TabPane("Series",):
                yield Input(placeholder="Series...")

        yield Markdown("Book info")

        yield Footer()

    def on_mount(self) -> None:
        self._books_table.add_columns("ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language")
        self._books_table.add_row(1,"Wool", "Howy", "SF,POSTAP","5","Silo","en")
        self._books_table.add_row(2, "Dust", "Howy", "SF,POSTAP", "4", "Silo", "en")

if __name__ == "__main__":
    app = FlTui()
    app.run()