from typing import Optional

from textual.widgets import DataTable
from textual.widgets._data_table import ColumnKey, RowKey

from flget.inpx import BookEntry


class BookTable(DataTable):
    def __init__(self, widget_id: str):
        super().__init__(cursor_type="row", id=widget_id)
        self._id_column: ColumnKey

    def on_mount(self) -> None:
        columns = self.add_columns(
            "ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language"
        )
        self._id_column = columns[0]

    def populate(self, books: list[BookEntry]) -> None:
        self.clear()
        for book in books:
            self.add_row(
                book.lib_id,
                book.title,
                ",".join(book.authors),
                ",".join(book.genres),
                book.rating if book.rating > 0 else "",
                ",".join(book.keywords),
                book.lang,
            )

    def book_id(self, row_key: RowKey) -> Optional[int]:
        if row_key not in self.rows:
            return None
        return int(self.get_cell(row_key, self._id_column))
