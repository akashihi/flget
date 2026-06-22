from typing import Optional

from textual.widgets import DataTable
from textual.widgets._data_table import ColumnKey, RowKey

from flget.filters import genre_display_names, language_display
from flget.inpx import BookEntry
from flget.library import TheLibrary


class BookTable(DataTable):
    def __init__(self, widget_id: str, library: TheLibrary):
        super().__init__(cursor_type="row", id=widget_id)
        self._library = library
        self._id_column: ColumnKey

    def on_mount(self) -> None:
        columns = self.add_columns(
            "ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language"
        )
        self._id_column = columns[0]

    def populate(self, books: list[BookEntry]) -> None:
        self.clear()
        titles = self._library.genre_titles()
        for book in books:
            self.add_row(
                book.lib_id,
                book.title,
                ",".join(book.authors),
                ",".join(genre_display_names(book.genres, titles)),
                book.rating if book.rating > 0 else "",
                ",".join(book.keywords),
                language_display(book.lang),
            )

    def book_id(self, row_key: RowKey) -> Optional[int]:
        if row_key not in self.rows:
            return None
        return int(self.get_cell(row_key, self._id_column))
