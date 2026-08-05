from typing import ClassVar

import platformdirs
from textual import on
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from flget.library import TheLibrary
from flget.mirror import BookEntry


class SaveScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [("escape", "close", "Close")]

    def __init__(self, library: TheLibrary, book: BookEntry) -> None:
        super().__init__()
        self._book = book
        self._library = library
        self._filename_input = Input(
            id="save-input", value=platformdirs.user_documents_dir()
        )

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(
                f"Where to save {self._library.build_filename(self._book.lib_id)}?",
                id="save-question",
            ),
            self._filename_input,
            Button("Save", variant="error", id="save-commit"),
            Button("Cancel", variant="primary", id="save-cancel"),
            id="save-dialog",
        )

    @on(Button.Pressed, "#save-cancel")
    def on_cancel_clicked(self) -> None:
        self.dismiss()

    @on(Input.Submitted, "#save-input")
    @on(Button.Pressed, "#save-commit")
    def on_save_clicked(self) -> None:
        self._library.save(self._book.lib_id, self._filename_input.value)
        self.dismiss()

    def action_save(self) -> None:
        self.on_save_clicked()

    def action_close(self) -> None:
        self.dismiss()
