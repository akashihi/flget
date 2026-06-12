from typing import Annotated, List, Optional

import platformdirs
import pyfiglet
import typer
import humanize
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flget import filters
from flget.config import Config
from flget.filters import BookFilter
from flget.inpx import BookEntry
from flget.library import TheLibrary
from flget.sync import mirror_sync

app = typer.Typer()
search_app = typer.Typer()
show_app = typer.Typer()
filters_app = typer.Typer()
console = Console()
error_console = Console(stderr=True, style="bold red")
config = Config()
library = TheLibrary(config)

GenreOption = Annotated[
    Optional[List[str]],
    typer.Option(
        "--genre", "-g", help="Filter by genre code (repeatable; see 'filters genres')."
    ),
]
FormatOption = Annotated[
    Optional[List[str]],
    typer.Option(
        "--format",
        "-f",
        help="Filter by file format (repeatable; see 'filters formats').",
    ),
]
LanguageOption = Annotated[
    Optional[List[str]],
    typer.Option(
        "--language",
        "-l",
        help="Filter by language code (repeatable; see 'filters languages').",
    ),
]
YearFromOption = Annotated[
    Optional[int],
    typer.Option("--year-from", help="Only books published this year or later."),
]
YearToOption = Annotated[
    Optional[int],
    typer.Option("--year-to", help="Only books published this year or earlier."),
]
MinSizeOption = Annotated[
    Optional[str],
    typer.Option("--min-size", help="Minimum file size (e.g. 500K, 2M, 1.5G)."),
]
MaxSizeOption = Annotated[
    Optional[str],
    typer.Option("--max-size", help="Maximum file size (e.g. 500K, 2M, 1.5G)."),
]


def _build_filter(
    genre: Optional[List[str]],
    format: Optional[List[str]],
    language: Optional[List[str]],
    year_from: Optional[int],
    year_to: Optional[int],
    min_size: Optional[str],
    max_size: Optional[str],
) -> BookFilter:
    return BookFilter(
        genres=frozenset(g.lower() for g in genre) if genre else frozenset(),
        formats=frozenset(f.lower() for f in format) if format else frozenset(),
        languages=frozenset(lang.lower() for lang in language)
        if language
        else frozenset(),
        year_from=year_from,
        year_to=year_to,
        min_size=filters.parse_size(min_size) if min_size is not None else None,
        max_size=filters.parse_size(max_size) if max_size is not None else None,
    )


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
def author_search(
    query: str,
    genre: GenreOption = None,
    format: FormatOption = None,
    language: LanguageOption = None,
    year_from: YearFromOption = None,
    year_to: YearToOption = None,
    min_size: MinSizeOption = None,
    max_size: MaxSizeOption = None,
) -> None:
    """
    Search for the author.

    """
    book_filter = _build_filter(
        genre, format, language, year_from, year_to, min_size, max_size
    )
    results = library.search_authors(query, book_filter)

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
def series_search(
    query: str,
    genre: GenreOption = None,
    format: FormatOption = None,
    language: LanguageOption = None,
    year_from: YearFromOption = None,
    year_to: YearToOption = None,
    min_size: MinSizeOption = None,
    max_size: MaxSizeOption = None,
) -> None:
    """
    Search for the series.

    """
    book_filter = _build_filter(
        genre, format, language, year_from, year_to, min_size, max_size
    )
    results = library.search_series(query, book_filter)

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
def book_search(
    query: str,
    genre: GenreOption = None,
    format: FormatOption = None,
    language: LanguageOption = None,
    year_from: YearFromOption = None,
    year_to: YearToOption = None,
    min_size: MinSizeOption = None,
    max_size: MaxSizeOption = None,
) -> None:
    """
    Search for the book

    """
    book_filter = _build_filter(
        genre, format, language, year_from, year_to, min_size, max_size
    )
    _book_list_render("Books", library.search_books(query, book_filter))


@search_app.command(name="all")
def all_search(
    query: str,
    genre: GenreOption = None,
    format: FormatOption = None,
    language: LanguageOption = None,
    year_from: YearFromOption = None,
    year_to: YearToOption = None,
    min_size: MinSizeOption = None,
    max_size: MaxSizeOption = None,
) -> None:
    """
    Search for the book/series/author

    """
    author_search(
        query, genre, format, language, year_from, year_to, min_size, max_size
    )
    series_search(
        query, genre, format, language, year_from, year_to, min_size, max_size
    )
    book_search(query, genre, format, language, year_from, year_to, min_size, max_size)


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
        series_list = [f"{s[0]} ({s[1]})" for s in zip(book.series, book.serno)]
        output.append(f"Series: {','.join(series_list)}\n", style="bold magenta")
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
def sync(
    force_db_sync: Annotated[
        bool, typer.Option(is_flag=True, help="Skip INPX import.")
    ] = False,
    force_download: Annotated[
        bool, typer.Option(help="Ignore cached metadata and re-download all DB dumps.")
    ] = False,
) -> None:
    """
    Synchronize the internal database with a library.

    Reads INPX file (if provided), DB dump file (if provided), and analyzes content of
    the library mirror. Processed books are indexed into a local database.


    """
    mirror_sync(force_db_sync, force_download, config, library, console, error_console)


@filters_app.command(name="genres")
def filters_genres() -> None:
    """
    List the genre codes available for filtering.

    """
    table = Table(title="Genres", box=box.SIMPLE_HEAVY)
    table.add_column("Code", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    for code, title in library.list_genres():
        table.add_row(code, title or "")
    console.print(table)


@filters_app.command(name="formats")
def filters_formats() -> None:
    """
    List the file formats available for filtering.

    """
    table = Table(title="Formats", box=box.SIMPLE_HEAVY)
    table.add_column("Format", style="cyan", no_wrap=True)
    for ext in library.list_formats():
        table.add_row(ext)
    console.print(table)


@filters_app.command(name="languages")
def filters_languages() -> None:
    """
    List the language codes available for filtering.

    """
    table = Table(title="Languages", box=box.SIMPLE_HEAVY)
    table.add_column("Code", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    for code in library.list_languages():
        table.add_row(code, filters.LANGUAGE_NAMES.get(code, ""))
    console.print(table)


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
    app.add_typer(filters_app, name="filters", help="List possible filter values")
    app()


if __name__ == "__main__":
    main()
