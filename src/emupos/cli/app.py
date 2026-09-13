"""The `emupos` command-line application (cli spec).

Exit codes: 0 success, 1 operation failed, 2 usage error, 3 simulator not reachable.
Every command module raises CliError; `_Commands.invoke` prints it and exits with its code.
"""

import io
import sys
import urllib.parse
from importlib.metadata import version
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from emupos.cli import actions, barcode, config_cmd, devices, doctor, run, setup_cmd
from emupos.cli.client import DEFAULT_API
from emupos.cli.output import CliError, print_error


class _Commands(TyperGroup):
    # `ctx` is Typer's own click Context; typer.Context is only the annotation for commands.
    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except CliError as error:
            print_error(error, ctx)
            raise typer.Exit(error.exit_code) from None


app = typer.Typer(
    name="emupos",
    cls=_Commands,
    help="Simulate POS hardware at the wire-protocol level.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"emupos {version('emupos')}")
        raise typer.Exit


def _check_api(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise typer.BadParameter(f"`{value}` is not an http or https URL, e.g. {DEFAULT_API}")
    return value


@app.callback()
def main_options(
    ctx: typer.Context,
    api: Annotated[
        str,
        typer.Option(
            "--api",
            envvar="EMUPOS_API",
            callback=_check_api,
            metavar="URL",
            help="Control API of the running simulator.",
        ),
    ] = DEFAULT_API,
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
    """Simulate POS hardware at the wire-protocol level.

    `emupos run` starts the simulated devices; the other commands act on them the way a person
    acts on real hardware.
    """
    ctx.obj = api


app.command("run")(run.run)
app.command("devices")(devices.devices)
app.add_typer(devices.receipt_app, name="receipt")
app.command("scan")(actions.scan)
app.add_typer(actions.scale_app, name="scale")
app.add_typer(actions.fault_app, name="fault")
app.add_typer(actions.drawer_app, name="drawer")
app.add_typer(barcode.barcode_app, name="barcode")
app.add_typer(config_cmd.config_app, name="config")
app.command("doctor")(doctor.doctor)
app.add_typer(setup_cmd.setup_app, name="setup")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        # A Windows console or pipe may not encode ✓ and ✗; print a replacement instead of crashing.
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")
    app()


if __name__ == "__main__":
    main()
