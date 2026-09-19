"""`emupos setup print-queue` (windows-print-queue spec)."""

import sys
from typing import Annotated

import typer

from emupos.cli.client import DeviceOption, Json, api, device_path, pick_device
from emupos.cli.output import CliError, console

setup_app = typer.Typer(help="Set up operating-system integrations.", no_args_is_help=True)

ONE_WAY = (
    "status replies (DLE EOT, GS r, Automatic Status Back) are not delivered through a print "
    "queue; to test status, connect the POS to the printer's TCP port or serial connection directly"
)


@setup_app.command("print-queue")
def print_queue(
    ctx: typer.Context,
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
    from emupos.windows_queue.setup import (
        QueueSetupError,
        create_queue,
        queue_name,
        remove_queue,
    )

    out = console()
    try:
        if remove:
            # With --device, `pick_device` returns it without asking the API: removing needs no
            # running simulator.
            printer = pick_device(api(ctx), "printer", device)
            outcome = remove_queue(printer)
            summary = (
                f"removed print queue {queue_name(printer)} and its port"
                if outcome.changed
                else f"nothing to remove: no print queue or port named {queue_name(printer)}"
            )
        else:
            client = api(ctx)
            printer = pick_device(client, "printer", device)
            port = _tcp_port(client.get(device_path(printer)))
            outcome = create_queue(printer, port)
            verb = "created" if outcome.changed else "already set up:"
            summary = f"{verb} print queue {queue_name(printer)} → raw jobs to 127.0.0.1:{port}"
    except QueueSetupError as error:
        raise CliError(error.message, error.fix, code="print_queue_failed") from None
    for note in outcome.notes:
        out.print(note)
    out.print(summary)
    if not remove:
        out.print(f"note: {ONE_WAY}")
        out.print(
            "note: text printed from ordinary Windows applications arrives as plain text from the "
            "Generic / Text Only driver, and characters outside its code page, such as Arabic, "
            "are replaced"
        )
        out.print(
            "note: Windows asks for the status of a printer without faults only about every 10 "
            "minutes, so a new fault can take that long to show on the queue"
        )


def _tcp_port(printer: Json) -> int:
    """The port of the printer's first TCP connection (the queue always targets 127.0.0.1)."""
    if printer["type"] != "printer":
        raise CliError(
            f"`{printer['id']}` is not a printer",
            "choose a printer with --device; `emupos devices` lists them",
            code="not_a_printer",
            exit_code=2,
        )
    for connection in printer["connections"]:
        if connection["kind"] == "tcp":
            return int(connection["endpoint"].rsplit(":", 1)[1])
    raise CliError(
        f"printer `{printer['id']}` has no TCP connection; a `tcp` connection must be added to "
        f"`{printer['id']}` in `emupos.yaml`, because a print queue sends jobs over TCP",
        f"add a `tcp` connection to `{printer['id']}` in emupos.yaml, "
        "e.g. `connections: [ { tcp: { port: 9100 } } ]`, and restart `emupos run`",
        code="no_tcp_connection",
    )
