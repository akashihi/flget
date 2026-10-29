from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from flget.config import Config
from flget.dbsync import (
    build_mirror,
    db_import_dumps,
    decompress_dumps,
    import_dumps,
)
from flget.inpx import parse_inpx
from flget.library import MirrorValidationResult, TheLibrary
from flget.mirror import Mirror


def validate_mirror(library: TheLibrary) -> MirrorValidationResult:
    with Progress() as progress:
        mirror_task = progress.add_task(
            total=100, description="[green]Scanning local mirror"
        )

        def task_updater(advance: float) -> None:
            progress.update(mirror_task, advance=advance)

        return library.validate(task_updater)


def report_validation_results(
    console: Console, validation_results: MirrorValidationResult
) -> None:
    if validation_results.missing_archives > 0:
        console.print(
            f"Found {validation_results.missing_archives} missing archives, please check your mirror.",
            style="deep_pink3",
        )
    if validation_results.unknown_archives > 0:
        console.print(
            f"Found {validation_results.unknown_archives}  book(s) with unknown archives",
            style="royal_blue1",
        )
    if validation_results.unknown_books > 0:
        console.print(
            f"Found {validation_results.unknown_books} unknown books",
            style="royal_blue1",
        )


def index_books(inpx_mirror: Mirror, library: TheLibrary) -> None:
    with Progress() as progress:
        index_task = progress.add_task(
            total=100, description="[spring_green4]Indexing books"
        )

        def task_updater(advance: float) -> None:
            progress.update(index_task, advance=advance)

        library.sync(inpx_mirror, task_updater)


def _inpx_sync(
    config: Config,
    library: TheLibrary,
    console: Console,
    error_console: Console,
) -> None:
    with Progress() as progress:
        inpx_task = progress.add_task(
            total=100, description="[spring_green4]INPX import"
        )

        def task_updater(advance: float) -> None:
            progress.update(inpx_task, advance=advance)

        try:
            inpx_mirror = parse_inpx(config.libdir(), task_updater)
        except FileNotFoundError:
            error_console.print(
                f"INPX file is not available in {config.libdir()}. "
                "Set the mirror location with `flget set-library-path PATH`.",
                markup=False,
            )
            return
    console.print(
        f"Found [spring_green4]{len(inpx_mirror)}[/spring_green4] books",
        style="royal_blue1",
    )

    index_books(inpx_mirror, library)

    validation_results = validate_mirror(library)
    report_validation_results(console, validation_results)

    if validation_results.unknown_archives > 0 or validation_results.unknown_books > 0:
        console.print(
            "The INPX looks incomplete. For a full catalogue, run "
            "`flget sync --dumps-dir PATH` with the SQL dumps.",
            style="royal_blue1",
            markup=False,
        )


def _dump_sync(
    dumps_dir: Path, config: Config, library: TheLibrary, console: Console
) -> None:
    with Progress() as progress:
        copy_task = progress.add_task(
            total=100, description="[magenta]Copying DB dumps"
        )

        def task_updater(advance: float) -> None:
            progress.update(copy_task, advance=advance)

        import_dumps(dumps_dir, task_updater)
    with Progress() as progress:
        decompress_task = progress.add_task(
            total=100, description="[magenta]Decompressing DB dumps"
        )

        def task_updater(advance: float) -> None:
            progress.update(decompress_task, advance=advance)

        decompress_dumps(task_updater)
    with Progress() as progress:
        import_task = progress.add_task(
            total=100, description="[green]Importing DB dumps"
        )

        def task_updater(advance: float) -> None:
            progress.update(import_task, advance=advance)

        db_import_dumps(task_updater)

    with Progress() as progress:
        mirror_task = progress.add_task(
            total=100, description="[spring_green4]Preparing mirror information"
        )

        def task_updater(advance: float) -> None:
            progress.update(mirror_task, advance=advance)

        db_mirror = build_mirror(config.libdir(), task_updater)
        console.print(
            f"Found [spring_green4]{len(db_mirror)}[/spring_green4] books",
            style="royal_blue1",
        )

    index_books(db_mirror, library)
    validation_results = validate_mirror(library)
    report_validation_results(console, validation_results)


def mirror_sync(
    dumps_dir: Path | None,
    config: Config,
    library: TheLibrary,
    console: Console,
    error_console: Console,
) -> None:
    """
    Synchronize the internal database with a library.

    Imports the INPX file, or the SQL dumps from ``dumps_dir`` when given, indexes
    the books and validates them against the library mirror.
    """
    if dumps_dir:
        _dump_sync(dumps_dir, config, library, console)
    else:
        _inpx_sync(config, library, console, error_console)
