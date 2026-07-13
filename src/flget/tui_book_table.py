from typing import Optional

from rich.text import Text
from textual import on
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
        self._groups: list[tuple[str, list[BookEntry]]] = []
        self._collapsed: set[int] = set()
        self._header_rows: dict[RowKey, int] = {}

    def on_mount(self) -> None:
        columns = self.add_columns(
            "ID", "Title", "Author", "Genres", "Rating", "Keywords", "Language"
        )
        self._id_column = columns[0]

    def populate(self, books: list[BookEntry]) -> None:
        self.clear()
        self._groups = []
        self._collapsed.clear()
        self._header_rows.clear()
        titles = self._library.genre_titles()
        for book in books:
            self._add_book_row(book, titles)

    def populate_grouped(self, groups: list[tuple[str, list[BookEntry]]]) -> None:
        self._groups = groups
        self._collapsed.clear()
        self._render_groups()
        first = self._next_book_row(0, 1)
        if first is not None:
            self.move_cursor(row=first)

    def _render_groups(self) -> None:
        self.clear()
        self._header_rows.clear()
        titles = self._library.genre_titles()
        for index, (name, books) in enumerate(self._groups):
            if index in self._collapsed:
                header = f"▶ {name} ({len(books)} books)"
            else:
                header = f"▼ {name}"
            key = self.add_row(
                "",
                Text(header, style="bold italic reverse"),
                "",
                "",
                "",
                "",
                "",
                key=f"group-{index}",
            )
            self._header_rows[key] = index
            if index not in self._collapsed:
                for book in books:
                    self._add_book_row(book, titles)

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
        if row_key not in self.rows or row_key in self._header_rows:
            return None
        return int(self.get_cell(row_key, self._id_column))

    def _is_separator(self, row_index: int) -> bool:
        return self.ordered_rows[row_index].key in self._header_rows

    def _next_book_row(self, start: int, step: int) -> Optional[int]:
        row = start
        while 0 <= row < self.row_count:
            if not self._is_separator(row):
                return row
            row += step
        return None

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        group = self._header_rows.get(event.row_key)
        if group is None:
            return
        event.stop()
        if group in self._collapsed:
            self._collapsed.remove(group)
        else:
            self._collapsed.add(group)
        self._render_groups()
        self.move_cursor(row=self.get_row_index(f"group-{group}"))
