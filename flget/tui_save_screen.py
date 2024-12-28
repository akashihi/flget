import platformdirs
from textual import on
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Input

from library import TheLibrary
from inpx import BookEntry


class SaveScreen(ModalScreen):
    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, parent, library: TheLibrary, book: BookEntry):
        super().__init__(parent)
        self._book = book
        self._library = library
        self._filename_input = Input(
            id="save-input", value=platformdirs.user_documents_dir()
        )

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(
                f"Where to save {self._book.filename}.{self._book.ext}?",
                id="save-question",
            ),
            self._filename_input,
            Button("Save", variant="error", id="save-commit"),
            Button("Cancel", variant="primary", id="save-cancel"),
            id="save-dialog",
        )

    @on(Button.Pressed, "#save-cancel")
    def on_cancel_clicked(self):
        self.dismiss()

    @on(Input.Submitted, "#save-input")
    @on(Button.Pressed, "#save-commit")
    def on_save_clicked(self):
        self._library.save(self._book.lib_id, self._filename_input.value)
        self.dismiss()

    def action_save(self):
        self.on_save_clicked()

    def action_close(self):
        self.dismiss()
