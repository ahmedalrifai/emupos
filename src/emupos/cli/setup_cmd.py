"""`emupos setup print-queue` (windows-print-queue spec)."""

import sys
from typing import Annotated

import typer

from emupos.cli.client import DeviceOption
from emupos.cli.output import CliError

setup_app = typer.Typer(help="Set up operating-system integrations.", no_args_is_help=True)


@setup_app.command("print-queue")
def print_queue(
    device: DeviceOption = None,
    remove: Annotated[
        bool, typer.Option("--remove", help="Delete the queue and port created for the printer.")
    ] = False,
) -> None:
    """Windows: create a print queue emupos-<device id> that sends raw jobs to a simulated printer."""
    if sys.platform != "win32":
        raise CliError(
            "print queues are only supported on Windows; on this operating system the POS "
            "connects to the printer's TCP port or serial connection directly",
            "point the POS at the printer's endpoint shown by `emupos devices`",
            code="unsupported_platform",
        )
    raise CliError(
        "`emupos setup print-queue` is not implemented yet",
        "connect the POS to the printer's TCP port directly",
        code="not_implemented",
    )
