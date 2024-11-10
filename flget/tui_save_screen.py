import os

import platformdirs
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Input

from inpx import BookEntry


class SaveScreen(ModalScreen):
    def __init__(self, parent, book: BookEntry):
        super().__init__(parent)
        self._book = book
        filename = os.path.join(platformdirs.user_documents_dir(), f"{book.filename}.{book.ext}")
        self._filename_input = Input(id="save-input", value=filename)

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(f"Are you sure you want to save {self._book.title} by {self._book.authors[0]}?", id="save-question"),
            self._filename_input,
            Button("Quit", variant="error", id="quit"),
            Button("Cancel", variant="primary", id="cancel"),
            id="save-dialog",
        )