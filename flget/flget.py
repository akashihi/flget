import pyfiglet
import typer
from rich import box
from rich.console import Console
from prompt_toolkit import prompt
from rich.progress import Progress
from rich.table import Table

from config import Config
from dbsync import get_dumps, db_import_dumps
from library import TheLibrary
from inpx import INPX

app = typer.Typer()
search_app = typer.Typer()
console = Console()
error_console = Console(stderr=True, style="bold red")
config = Config()
library = TheLibrary(config)


@app.command()
def get(book_id: int) -> None:
    """
    Retrieves book by id and stores it into the specified folder.

    """
    library.get(book_id)


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
            table.add_row(str(result.id), result.name, str(result.books), str(result.series))

        console.print(table)
    else:
        suggestion = library.suggest_authors(query)
        if suggestion:
            console.print(f"Did you meant '{suggestion}'?")
        else:
            console.print("Nothing found")

@search_app.command(name="all")
def search(query: str) -> None:
    """
    Search for the author/series/book

    """
    results = library.search_books(query)

    table = Table(title="Books")
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")

    for result in results:
        table.add_row(str(result.lib_id), result.title)

    console.print(table)


@app.command()
def sync():
    """
    Synchronize the internal database with a library.

    Reads INPX file (if provided), DB dump file (if provided), and analyzes content of
    the library mirror. Processed books are indexed into a local database.
    """
    with Progress() as progress:
        inpx_task = progress.add_task(total=100, description="[spring_green4]INPX import")

        def task_updater(advance: float) -> None:
            progress.update(inpx_task, advance=advance)

        try:
            inpx = INPX(config.libdir(), task_updater)
        except FileNotFoundError:
            error_console.print("INPX file is not available")
            return
    console.print(f"Found [spring_green4]{len(inpx)}[/spring_green4] books", style="royal_blue1")

    with Progress() as progress:
        mirror_task = progress.add_task(total=100, description="[green]Scanning local mirror")

        def task_updater(advance: float) -> None:
            progress.update(mirror_task, advance=advance)

        validation_results = library.validate(task_updater)
    if validation_results.missing_archives > 0:
        console.print(f"Found {validation_results.missing_archives} missing archives, please check your mirror.",
                      style="deep_pink3")
    if validation_results.unknown_archives > 0:
        console.print(f"Found {validation_results.unknown_archives} unknown archives", style="royal_blue1")
    if validation_results.unknown_books > 0:
        console.print(f"Found {validation_results.unknown_books} unknown books", style="royal_blue1")

    if validation_results.unknown_archives > 0 and validation_results.unknown_books > 0:
        db_sync = prompt("Unknown items found, would you like to sync with a DB dump? (y/N)")
    #     if db_sync.lower() == 'y':
    #         with console.status("Downloading DB dumps", spinner="shark"):
    #             #get_dumps()
    #             pass
    #         with console.status("Importing DB dumps", spinner="shark"):
    #             db_import_dumps()

    with console.status("Indexing books", spinner="shark"):
        library.sync(inpx)


@app.command()
def set_library_path(path: str):
    """
    Set and store PATH to the flibusta mirror.
    """
    config.set_libdir(path)

    console.print(f"[royal_blue1]Library location set to[/royal_blue1]: {config.libdir()}")


def main():
    # Banner
    f = pyfiglet.figlet_format("FlGet", font="univers")
    console.print(f, style="chartreuse4")

    # Library directory:
    console.print(f"[royal_blue1]Library location[/royal_blue1]: {config.libdir()}")

    # CLI setup
    app.add_typer(search_app, name="search", help="Search books/authors/series")
    app()


if __name__ == "__main__":
    main()
