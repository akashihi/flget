from typing import Annotated

import platformdirs
import pyfiglet
import typer
import humanize
from rich import box
from rich.console import Console
from prompt_toolkit import prompt
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table
from rich.text import Text

from config import Config
from dbsync import get_dumps, decompress_dumps, db_import_dumps
from inpx import BookEntry
from library import TheLibrary
from inpx import INPX

app = typer.Typer()
search_app = typer.Typer()
show_app = typer.Typer()
console = Console()
error_console = Console(stderr=True, style="bold red")
config = Config()
library = TheLibrary(config)


@app.command()
def get(
    book_id: int,
    target_path: Annotated[str, typer.Argument()] = platformdirs.user_documents_dir(),
) -> None:
    """
    Retrieves book by id and stores it into the specified folder.

    """
    library.save(book_id, target_path)


@search_app.command(name="author")
def author_search(query: str) -> None:
    """
    Search for the author.

    """
    results = library.search_authors(query)

    if results:
        table = Table(title="Authors", expand=True, box=box.SIMPLE_HEAVY)
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("Books", justify="center", style="indian_red1", no_wrap=True)
        table.add_column("Series", justify="center", style="indian_red1", no_wrap=True)

        for result in results:
            table.add_row(
                str(result.id), result.name, str(result.books), str(result.series)
            )

        console.print(table)
    else:
        suggestion = library.suggest_authors(query)
        if suggestion:
            console.print(f"Did you meant '{suggestion}'?")
        else:
            console.print("Nothing found")


@search_app.command(name="series")
def series_search(query: str) -> None:
    """
    Search for the series.

    """
    results = library.search_series(query)

    if results:
        table = Table(title="Series", expand=True, box=box.SIMPLE_HEAVY)
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("Books", justify="center", style="indian_red1", no_wrap=True)
        table.add_column("Authors", justify="center", style="indian_red1", no_wrap=True)

        for result in results:
            table.add_row(
                str(result.id), result.name, str(result.books), str(result.authors)
            )

        console.print(table)
    else:
        suggestion = library.suggest_series(query)
        if suggestion:
            console.print(f"Did you meant '{suggestion}'?")
        else:
            console.print("Nothing found")


def _book_list_render(title: str, books: list[BookEntry]) -> None:
    table = Table(title=title)
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("Authors", style="sea_green1")
    table.add_column("Genres", style="deep_sky_blue4")
    table.add_column("Rating", justify="center", style="indian_red1", no_wrap=True)
    table.add_column("Keywords", style="deep_sky_blue4")
    table.add_column("Language", justify="center", style="indian_red1", no_wrap=True)

    for book in books:
        table.add_row(
            str(book.lib_id),
            book.title,
            ", ".join(book.authors),
            ", ".join(book.genres),
            str(book.rating) if book.rating >= 0 else "",
            ", ".join(book.keywords),
            book.lang,
        )

    console.print(table)


@search_app.command(name="book")
def book_search(query: str) -> None:
    """
    Search for the book

    """
    _book_list_render("Books", library.search_books(query))


@search_app.command(name="all")
def all_search(query: str) -> None:
    """
    Search for the book/series/author

    """
    author_search(query)
    series_search(query)
    book_search(query)


@show_app.command(name="book")
def show_book(book_id: int) -> None:
    """
    Show book details
    """
    search_result = library.get_books([book_id])
    if not search_result:
        console.print("Book not found")
        return

    book = search_result[0]

    output = Text()
    output.append(f"Authors: {", ".join(book.authors)}\n", style="bold sea_green1")
    if book.series:
        output.append(f"Series: {book.series} ({book.serno})\n", style="bold magenta")
    output.append(f"Genres: {", ".join(book.genres)}\n", style="deep_sky_blue4")
    output.append(
        f"Rating: {str(book.rating) if book.rating >= 0 else 'Not yet set'}\n",
        style="indian_red1",
    )
    output.append(f"Keywords: {", ".join(book.keywords)}\n", style="deep_sky_blue4")
    output.append(f"Language: {book.lang}\n", style="indian_red1")
    output.append(
        f"{book.filename}.{book.ext} in {config.libdir()}{book.archive}.zip ({humanize.naturalsize(book.filesize, gnu=True)} bytes)\n",
        style="magenta",
    )
    console.print(Panel(output, title=book.title, subtitle=str(book.lib_id)))


@show_app.command(name="series")
def show_series(series_id: int) -> None:
    """
    Show series books

    """
    _book_list_render(library.get_series_name(series_id), library.get_series(series_id))


@show_app.command(name="author")
def show_author(author_id: int) -> None:
    """
    Show author's series and books

    """
    for s in library.get_author_series(author_id):
        show_series(s)

    _book_list_render("Non-series Books", library.get_author_books(author_id))


@app.command()
def sync(force_db_sync : Annotated[bool, typer.Option(help="Skip INPX import.")] = False, skip_download:Annotated[bool, typer.Option(help="Skip DB dump downloading and use existing copy.")] = False) -> None:
    """
    Synchronize the internal database with a library.

    Reads INPX file (if provided), DB dump file (if provided), and analyzes content of
    the library mirror. Processed books are indexed into a local database.

    
    """
    db_sync_answer=""
    if not force_db_sync:
        with Progress() as progress:
            inpx_task = progress.add_task(
                total=100, description="[spring_green4]INPX import"
            )

            def task_updater(advance: float) -> None:
                progress.update(inpx_task, advance=advance)

            try:
                inpx = INPX(config.libdir(), task_updater)
            except FileNotFoundError:
                error_console.print("INPX file is not available")
                return
        console.print(
            f"Found [spring_green4]{len(inpx)}[/spring_green4] books", style="royal_blue1"
        )

        with Progress() as progress:
            index_task = progress.add_task(
                total=100, description="[spring_green4]Indexing books"
            )

            def task_updater(advance: float) -> None:
                progress.update(index_task, advance=advance)

            library.sync(inpx, task_updater)

        with Progress() as progress:
            mirror_task = progress.add_task(
                total=100, description="[green]Scanning local mirror"
            )

            def task_updater(advance: float) -> None:
                progress.update(mirror_task, advance=advance)

            validation_results = library.validate(task_updater)
        if validation_results.missing_archives > 0:
            console.print(
                f"Found {validation_results.missing_archives} missing archives, please check your mirror.",
                style="deep_pink3",
            )
        if validation_results.unknown_archives > 0:
            console.print(
                f"Found {validation_results.unknown_archives} unknown archives",
                style="royal_blue1",
            )
        if validation_results.unknown_books > 0:
            console.print(
                f"Found {validation_results.unknown_books} unknown books",
                style="royal_blue1",
            )

        if validation_results.unknown_archives > 0 and validation_results.unknown_books > 0:
            db_sync_answer = prompt(
                "Unknown items found, would you like to sync with a DB dump? (y/N)"
            )

    if db_sync_answer.lower() == 'y' or force_db_sync:
        if not skip_download:
            with Progress() as progress:
                download_task = progress.add_task(
                    total=100, description="[magenta]Downloading DB dumps"
                )

                def task_updater(advance: float) -> None:
                    progress.update(download_task, advance=advance)
                get_dumps(task_updater)
            with Progress() as progress:
                download_task = progress.add_task(
                    total=100, description="[magenta]Decompressing DB dumps"
                )

                def task_updater(advance: float) -> None:
                    progress.update(download_task, advance=advance)

                decompress_dumps(task_updater)
        with console.status("Importing DB dumps", spinner="shark"):
            db_import_dumps()


@app.command()
def set_library_path(path: str):
    """
    Set and store PATH to the flibusta mirror.
    """
    config.set_libdir(path)

    console.print(
        f"[royal_blue1]Library location set to[/royal_blue1]: {config.libdir()}"
    )


def main():
    # Banner
    f = pyfiglet.figlet_format("FlGet", font="univers")
    console.print(f, style="chartreuse4")

    # Library directory:
    console.print(f"[royal_blue1]Library location[/royal_blue1]: {config.libdir()}")

    # CLI setup
    app.add_typer(search_app, name="search", help="Search books/authors/series")
    app.add_typer(show_app, name="show", help="Show books/authors/series")
    app()


if __name__ == "__main__":
    main()
