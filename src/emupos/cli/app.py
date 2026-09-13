"""The `emupos` command-line application."""

from importlib.metadata import version
from typing import Annotated

import typer

app = typer.Typer(
    name="emupos",
    help="Simulate POS hardware at the wire-protocol level.",
    no_args_is_help=True,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"emupos {version('emupos')}")
        raise typer.Exit


@app.callback()
def main_options(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the installed emupos version and exit.",
        ),
    ] = False,
) -> None:
    """Simulate POS hardware at the wire-protocol level."""


def main() -> None:
    app()
