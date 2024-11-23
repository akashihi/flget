from textual.widgets import DataTable

from inpx import BookEntry


class BookTable(DataTable):
    def __init__(self, widget_id: str):
        super().__init__(cursor_type="row", id=widget_id)

    def on_mount(self) -> None:
        self.add_columns("ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language")

    def populate(self, books: list[BookEntry]) -> None:
        self.clear()
        for book in books:
            row_key = self.add_row(book.lib_id, book.title, ",".join(book.authors), ",".join(book.genres),
                                   book.rating if book.rating > 0 else "", ",".join(book.keywords), book.lang,
                                   key=str(book.lib_id))
            self.log(row_key)
