from typing import ClassVar

import humanize
import typer
from textual import on
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList
from textual.widgets.selection_list import Selection

from flget.filters import LANGUAGE_NAMES, BookFilter, parse_size
from flget.library import TheLibrary


class FilterScreen(ModalScreen[BookFilter | None]):
    BINDINGS: ClassVar[list[BindingType]] = [("escape", "close", "Close")]

    def __init__(self, library: TheLibrary, current: BookFilter) -> None:
        super().__init__()
        self._library = library
        self._current = current

        self._genres = SelectionList[str](
            *[
                Selection(title or code, code.lower(), code.lower() in current.genres)
                for code, title in sorted(
                    library.list_genres(), key=lambda g: (g[1] or g[0]).lower()
                )
            ],
            id="filter-genres",
        )
        self._formats = SelectionList[str](
            *[
                Selection(ext, ext.lower(), ext.lower() in current.formats)
                for ext in library.list_formats()
            ],
            id="filter-formats",
        )
        self._languages = SelectionList[str](
            *[
                Selection(
                    LANGUAGE_NAMES.get(code.lower(), code),
                    code.lower(),
                    code.lower() in current.languages,
                )
                for code in library.list_languages()
            ],
            id="filter-languages",
        )

        self._year_from = Input(
            value="" if current.year_from is None else str(current.year_from),
            placeholder="From",
            type="integer",
            id="filter-year-from",
        )
        self._year_to = Input(
            value="" if current.year_to is None else str(current.year_to),
            placeholder="To",
            type="integer",
            id="filter-year-to",
        )
        self._min_size = Input(
            value=""
            if current.min_size is None
            else humanize.naturalsize(current.min_size, gnu=True),
            placeholder="Min (e.g. 500K)",
            id="filter-min-size",
        )
        self._max_size = Input(
            value=""
            if current.max_size is None
            else humanize.naturalsize(current.max_size, gnu=True),
            placeholder="Max (e.g. 2M)",
            id="filter-max-size",
        )

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Filter results", id="filter-title"),
            Horizontal(
                Vertical(Label("Genres"), self._genres, classes="filter-col"),
                Vertical(Label("Formats"), self._formats, classes="filter-col"),
                Vertical(Label("Languages"), self._languages, classes="filter-col"),
                id="filter-lists",
            ),
            Horizontal(
                Label("Year:", classes="filter-range-label"),
                self._year_from,
                self._year_to,
                Label("Size:", classes="filter-range-label"),
                self._min_size,
                self._max_size,
                id="filter-ranges",
            ),
            Horizontal(
                Button("Apply", variant="success", id="filter-apply"),
                Button("Reset", variant="warning", id="filter-reset"),
                Button("Cancel", variant="primary", id="filter-cancel"),
                id="filter-buttons",
            ),
            id="filter-dialog",
        )

    @on(Button.Pressed, "#filter-apply")
    def on_apply_clicked(self) -> None:
        try:
            year_from = (
                int(self._year_from.value) if self._year_from.value.strip() else None
            )
            year_to = int(self._year_to.value) if self._year_to.value.strip() else None
            min_size = (
                parse_size(self._min_size.value)
                if self._min_size.value.strip()
                else None
            )
            max_size = (
                parse_size(self._max_size.value)
                if self._max_size.value.strip()
                else None
            )
        except (typer.BadParameter, ValueError) as exc:
            self.notify(f"Invalid filter value: {exc}", severity="error")
            return

        book_filter = BookFilter(
            genres=frozenset(self._genres.selected),
            formats=frozenset(self._formats.selected),
            languages=frozenset(self._languages.selected),
            year_from=year_from,
            year_to=year_to,
            min_size=min_size,
            max_size=max_size,
        )
        self.dismiss(book_filter)

    @on(Button.Pressed, "#filter-reset")
    def on_reset_clicked(self) -> None:
        self.dismiss(BookFilter())

    @on(Button.Pressed, "#filter-cancel")
    def on_cancel_clicked(self) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)  # On esc we just close dialog, not touching filter state
