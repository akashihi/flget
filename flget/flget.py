import os.path
import zipfile
import pyfiglet
import typer
from rich.console import Console
from prompt_toolkit import prompt

from config import Config
from dbsync import get_dumps,db_import_dumps
from mirror import list_unknown_archives, list_unknown_entries
from inpx import INPX

app = typer.Typer()
console = Console()
error_console = Console(stderr=True, style="bold red")
config = Config()

@app.command()
def get(id: int):
    # INPX discovery
    with console.status("Importing INPX", spinner="shark"):
        inpx = INPX(config.libdir())
    for book in inpx:
        if book.lib_id == id:
            print(book)
            zippath = os.path.join(config.libdir(), f"{book.archive}.zip")
            with zipfile.ZipFile(zippath, "r") as archive:
                archive.extract(f"{book.filename}.{book.ext}", "/tmp")

@app.command()
def sync():
    """
    Synchronize the internal database with a library.

    Reads INPX file (if provided), DB dump file (if provided), and analyzes content of
    the library mirror. Processed books are indexed into a local database.
    """
    with console.status("Importing INPX", spinner="shark"):
        try:
            inpx = INPX(config.libdir())
            console.print(f"Found [spring_green4]{len(inpx)}[/spring_green4] books", style="royal_blue1")
        except FileNotFoundError:
            error_console.print("INPX file is not available")

    with console.status("Scanning local mirror", spinner="shark"):
        unknown_archives = list_unknown_archives(config.libdir(), inpx)
        unknown_entries = list_unknown_entries(config.libdir(), inpx)
    if unknown_archives:
        console.print(f"Found {len(unknown_archives)} unknown archives", style="royal_blue1")
    if unknown_entries:
        console.print(f"Found {len(unknown_entries)} unknown books", style="royal_blue1")

    if unknown_archives and unknown_entries:
        db_sync = prompt("Unknown items found, would you like to sync with a DB dump? (y/N)")
        if db_sync.lower() == 'y':
            with console.status("Downloading DB dumps", spinner="shark"):
                #get_dumps()
                pass
            with console.status("Importing DB dumps", spinner="shark"):
                db_import_dumps()


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
    app()




if __name__ == "__main__":
    main()