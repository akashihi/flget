from textual import on
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button


class FilterScreen(ModalScreen):
    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, parent):
        super().__init__(parent)

    def compose(self) -> ComposeResult:
        yield Button("Apply", variant="error", id="filter-apply")
        yield Button("Reset", variant="primary", id="filter-reset")

    def _reset_filter(self):
        pass # TODO reset logic

    @on(Button.Pressed, "#filter-reset")
    def on_reset_clicked(self):
        self._reset_filter()
        self.dismiss()

    @on(Button.Pressed, "#filter-apply")
    def on_apply_clicked(self):
        # TODO application logic
        self.dismiss()

    def action_save(self):
        self.on_apply_clicked()

    def action_close(self):
        self.on_reset_clicked()