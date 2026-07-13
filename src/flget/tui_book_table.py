from typing import Optional

from rich.text import Text
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
        self._separator_rows: set[RowKey] = set()

    def on_mount(self) -> None:
        columns = self.add_columns(
            "ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language"
        )
        self._id_column = columns[0]

    def populate(self, books: list[BookEntry]) -> None:
        self.clear()
        self._separator_rows.clear()
        titles = self._library.genre_titles()
        for book in books:
            self._add_book_row(book, titles)

    def populate_grouped(self, groups: list[tuple[str, list[BookEntry]]]) -> None:
        self.clear()
        self._separator_rows.clear()
        titles = self._library.genre_titles()
        for name, books in groups:
            key = self.add_row(
                "", Text(name, style="bold italic reverse"), "", "", "", "", ""
            )
            self._separator_rows.add(key)
            for book in books:
                self._add_book_row(book, titles)
        first = self._next_book_row(0, 1)
        if first is not None:
            self.move_cursor(row=first)

    def _add_book_row(self, book: BookEntry, titles: dict[str, str]) -> None:
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
        if row_key not in self.rows or row_key in self._separator_rows:
            return None
        return int(self.get_cell(row_key, self._id_column))

    def _is_separator(self, row_index: int) -> bool:
        return self.ordered_rows[row_index].key in self._separator_rows

    def _next_book_row(self, start: int, step: int) -> Optional[int]:
        row = start
        while 0 <= row < self.row_count:
            if not self._is_separator(row):
                return row
            row += step
        return None

    def action_cursor_down(self) -> None:
        target = self._next_book_row(self.cursor_row + 1, 1)
        if target is not None:
            self.move_cursor(row=target)

    def action_cursor_up(self) -> None:
        target = self._next_book_row(self.cursor_row - 1, -1)
        if target is not None:
            self.move_cursor(row=target)
