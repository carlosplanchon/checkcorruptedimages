#!/usr/bin/env python3

from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import typer

from checkcorruptedimages.checkcorruptedimages import CheckCorruptedImages

DEFAULT_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff"]

app = typer.Typer(add_completion=False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(package_version("checkcorruptedimages"))
        raise typer.Exit()


@app.command()
def main(
    folder: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Folder to scan recursively for corrupted images."
            ),
        ],
    ext: Annotated[
        list[str],
        typer.Option(
            "--ext", "-e",
            help="Image extension to check; repeat for several."
            ),
        ] = DEFAULT_EXTENSIONS,
    lenient: Annotated[
        bool,
        typer.Option(
            "--lenient",
            help="Only report files Pillow cannot decode at all, "
                 "tolerating truncated files and warnings."
            ),
        ] = False,
    timeout: Annotated[
        float,
        typer.Option(
            help="Seconds allowed per image; 0 disables the limit."
            ),
        ] = 60.0,
    workers: Annotated[
        int | None,
        typer.Option(
            help="Worker processes to use; defaults to one per CPU."
            ),
        ] = None,
    max_memory_mb: Annotated[
        int | None,
        typer.Option(
            "--max-memory-mb",
            help="Best-effort memory cap per decoder worker, in MiB "
                 "(POSIX only)."
            ),
        ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v",
            help="Print the status and reason of every checked image."
            ),
        ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit."
            ),
        ] = False
        ) -> None:
    """
    Check FOLDER recursively for corrupted images.

    Prints one corrupted path per line (a summary goes to stderr) and
    exits with code 1 if any corrupted image was found.
    """

    checker = CheckCorruptedImages(
        verbose=verbose,
        regard_warnings=not lenient,
        timeout=timeout if timeout > 0 else None,
        max_worker_memory=(
            max_memory_mb * 1024 * 1024 if max_memory_mb else None
            )
        )

    results = checker.get_check_results(
        folder_to_check=folder,
        file_extensions_list=ext,
        max_workers=workers
        )

    corrupted = [result for result in results if result.corrupted]

    if not verbose:
        for result in corrupted:
            typer.echo(result.file_path)

    typer.echo(
        f"{len(corrupted)} corrupted out of {len(results)} checked images.",
        err=True
        )

    if corrupted:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
