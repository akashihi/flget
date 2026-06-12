from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from rich.text import Text
from rich.emoji import Emoji
import humanize

from flget.inpx import BookEntry
from flget.filters import _book_year


class BookViewWidget(Widget):
    def __init__(self):
        super().__init__()

        self._title = Static("")
        self._author = Static("")
        self._series = Static("")
        self._genre = Static("")
        self._keywords = Static("")
        self._file_data = Static("")

    def compose(self) -> ComposeResult:
        yield self._title
        yield self._author
        yield self._series
        yield self._genre
        yield self._keywords
        yield self._file_data

    def update(self, book: BookEntry) -> None:
        title_text = Text(justify="center")
        title_text.append(book.title, style="bold")
        year = _book_year(book)
        if year is not None:
            title_text.append(f" ({year})")
        if book.rating > 0:
            title_text.append(" " + Emoji.replace(":star:") * book.rating)
        self._title.update(title_text)

        self._author.update(
            Text(",".join(book.authors), justify="center", style="bold sea_green1")
        )
        if book.series:
            self._series.update(
                Text(
                    ",".join(
                        [f"{s[0]} ({s[1]})" for s in zip(book.series, book.serno)]
                    ),
                    justify="left",
                    style="bold magenta",
                )
            )
        else:
            self._series.update("")

        self._genre.update(Text(",".join(book.genres), style="deep_sky_blue4"))
        self._keywords.update(Text(",".join(book.keywords), style="deep_sky_blue4"))

        file_data = Text(
            f"{book.filename}.{book.ext} ({humanize.naturalsize(book.filesize, gnu=True)}) Language: {book.lang}",
            style="magenta",
        )
        self._file_data.update(file_data)
