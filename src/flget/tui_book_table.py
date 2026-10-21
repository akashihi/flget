from typing import Any

from rich.text import Text
from textual import events, on
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets.data_table import ColumnKey, RowKey

from flget.filters import genre_display_names, language_display
from flget.library import TheLibrary
from flget.mirror import BookEntry


class BookTable(DataTable[Any]):
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
            # Textual scrolls the new cursor row into view after the next
            # refresh, one row too far, hiding the first group header.
            self.call_after_refresh(self.scroll_home, animate=False, force=True)

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
            Text(book.title),
            Text(",".join(book.author_names)),
            Text(",".join(genre_display_names(book.genres, titles))),
            book.rating if book.rating > 0 else "",
            Text(",".join(book.keywords)),
            Text(language_display(book.lang)),
        )

    def book_id(self, row_key: RowKey) -> int | None:
        if row_key not in self.rows or row_key in self._header_rows:
            return None
        return int(self.get_cell(row_key, self._id_column))

    def _is_separator(self, row_index: int) -> bool:
        return self.ordered_rows[row_index].key in self._header_rows

    def _next_book_row(self, start: int, step: int) -> int | None:
        row = start
        while 0 <= row < self.row_count:
            if not self._is_separator(row):
                return row
            row += step
        return None

    @on(events.Click)
    def _on_header_click(self, event: events.Click) -> None:
        # Textual selects a row only when the click lands on the cursor row, so
        # move the cursor onto a clicked group header first: DataTable's own
        # click handler (dispatched after this one) then selects it, toggling
        # the group with a single click.
        meta = event.style.meta
        row = meta.get("row", -1)
        if 0 <= row < self.row_count and self._is_separator(row):
            self.cursor_coordinate = Coordinate(row, meta.get("column", 0))

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
