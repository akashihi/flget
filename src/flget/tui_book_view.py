import io
from typing import cast

import humanize
from rich.emoji import Emoji
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Collapsible, Markdown, Static
from textual.worker import Worker, WorkerState
from textual_image.widget import Image as CoverImage

from flget.filters import genre_display_names, language_display
from flget.library import TheLibrary
from flget.mirror import BookEntry

COVER_GROUP = "cover"


class BookViewWidget(Widget):
    def __init__(self, library: TheLibrary):
        super().__init__()

        self._library = library

        self._cover_image = CoverImage(id="book-cover")
        self._cover_image.display = False
        self._current_lib_id: int | None = None

        self._title = Static("", id="book-title")
        self._author = Static("", id="book-author")
        self._series = Static("", id="book-series")
        self._genre = Static("", id="book-genre")
        self._keywords = Static("", id="book-keywords")
        self._file_data = Static("", id="book-file")

        self._annotation = Markdown()
        self._reviews = Markdown()
        self._annotation_box = Collapsible(
            self._annotation, title="Annotation", collapsed=False
        )
        self._reviews_box = Collapsible(self._reviews, title="Reviews")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self._cover_image
            with VerticalScroll():
                yield self._title
                yield self._author
                yield self._series
                yield self._genre
                yield self._keywords
                yield self._file_data
                yield self._annotation_box
                yield self._reviews_box

    def update(self, book: BookEntry) -> None:
        # Hide the previous cover right away so it can never show against the
        # new book's details while the lookup runs.
        self._current_lib_id = book.lib_id
        self._cover_image.display = False
        self._load_cover(book.lib_id)

        title_text = Text()
        title_text.append(book.title, style="bold")
        year = book.year
        if year is not None:
            title_text.append(f" ({year})")
        if book.rating > 0:
            title_text.append(" " + Emoji.replace(":star:") * book.rating)
        self._title.update(title_text)

        self._author.update(Text(",".join(book.author_names)))

        book = self._library.fill_book_digest(book)
        self._series.display = bool(book.series)
        if book.series:
            self._series.update(
                Text("; ".join(f"{name} ({serno})" for name, serno in book.series))
            )

        genres = genre_display_names(book.genres, self._library.genre_titles())
        self._genre.display = bool(genres)
        self._genre.update(Text(",".join(genres)))
        keywords = ",".join(book.keywords)
        self._keywords.display = bool(keywords)
        self._keywords.update(Text(keywords))

        file_data = Text(
            f"{self._library._archive_member_name(book.filename, book.ext)} ({humanize.naturalsize(book.filesize or 0, gnu=True)}) Language: {language_display(book.lang)}"
        )
        self._file_data.update(file_data)

        self._annotation_box.display = bool(book.annotation)
        if book.annotation:
            self._annotation.update(book.annotation)
        self._reviews_box.display = bool(book.reviews)
        if book.reviews:
            self._reviews.update(book.reviews)

    @work(thread=True, exclusive=True, group=COVER_GROUP)
    def _load_cover(self, lib_id: int) -> tuple[int, bytes | None]:
        return lib_id, self._library.get_cover(lib_id)

    @on(Worker.StateChanged)
    def on_cover_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker.group != COVER_GROUP or event.state != WorkerState.SUCCESS:
            return
        lib_id, data = cast("tuple[int, bytes | None]", event.worker.result)
        # Thread cancellation is cooperative, so a superseded lookup can still
        # reach SUCCESS; the id check drops its stale result.
        if lib_id != self._current_lib_id:
            return
        if data:
            self._cover_image.image = io.BytesIO(data)
            self._cover_image.display = True
