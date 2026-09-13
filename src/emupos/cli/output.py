"""Everything the `emupos` command prints (cli spec, "Output modes").

- In a terminal: Rich styles. Piped: plain text with no escape sequences. `NO_COLOR`: no styling.
- `--json`: exactly one JSON document on standard output.
- Errors go to standard error; with `--json` as `{ "error": { "code", "message", "fix" } }`.

Nothing here parses Rich markup: user data such as `devices[1].port` or scanned text is printed as is.
"""

import json
import os

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

_JSON_MODE = "emupos.json"
PIPED_WIDTH = 10_000  # piped output is never wrapped, so each line stays greppable


class CliError(Exception):
    """A command failed. Printed as `error: <message>` and `fix: <fix>`; exits with `exit_code`.

    Exit codes (cli spec): 1 operation failed, 2 usage error, 3 simulator unreachable.
    """

    def __init__(
        self, message: str, fix: str | None = None, *, code: str = "failed", exit_code: int = 1
    ) -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.code = code
        self.exit_code = exit_code


def console(*, stderr: bool = False) -> Console:
    """A console for one command. Built per call so it sees the current stream and environment."""
    no_color = os.environ.get("NO_COLOR", "") != ""
    out = Console(
        stderr=stderr,
        color_system=None if no_color else "auto",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    if not out.is_terminal:
        out.width = PIPED_WIDTH
    return out


def table(*columns: str) -> Table:
    grid = Table(box=None, pad_edge=False, header_style="bold")
    for column in columns:
        grid.add_column(column)
    return grid


def use_json(ctx: typer.Context, enabled: bool) -> None:
    """Record that this command prints JSON, so that its errors are printed as JSON too."""
    ctx.meta[_JSON_MODE] = enabled


def print_json(document: object) -> None:
    typer.echo(json.dumps(document, indent=2))


def print_error(error: CliError, ctx: typer.Context) -> None:
    if ctx.meta.get(_JSON_MODE, False):
        body = {"error": {"code": error.code, "message": error.message, "fix": error.fix}}
        typer.echo(json.dumps(body), err=True)
        return
    err = console(stderr=True)
    err.print(Text.assemble(("error: ", "bold red"), error.message))
    if error.fix:
        err.print(Text.assemble(("fix: ", "bold"), error.fix))


def kilograms(grams: int) -> str:
    """1250 -> "1.250 kg", exactly (weights are integers, never floats)."""
    sign = "-" if grams < 0 else ""
    return f"{sign}{abs(grams) // 1000}.{abs(grams) % 1000:03d} kg"


def warning(out: Console, message: str) -> None:
    out.print(Text.assemble(("warning: ", "bold yellow"), message))


def note(message: str) -> None:
    """A side message that must not mix with the command's data on standard output."""
    console(stderr=True).print(message)
