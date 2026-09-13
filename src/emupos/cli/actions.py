"""The physical actions: `scan`, `scale set | zero | tare`, `fault set | clear`, `drawer close`."""

import contextlib
import math
import time
from typing import Annotated

import typer
from rich.status import Status
from rich.text import Text

from emupos.cli.client import DeviceOption, api, device_path, pick_device
from emupos.cli.output import CliError, console, kilograms
from emupos.printer.printer import PrinterFault
from emupos.scale.weights import parse_weight

WEIGHT_FORMS = "a number with the unit kg or g, e.g. 1.25kg or 1250g"
CONFIRM_SECONDS = 10  # cli spec: wait this long after typing was due to finish


def weight_value(text: str, name: str) -> int:
    try:
        return parse_weight(text)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint=name) from None


# --- scan ------------------------------------------------------------------------------------


def scan(
    ctx: typer.Context,
    data: Annotated[str, typer.Argument(help="The text the scanner reads, e.g. 6291041500213.")],
    device: DeviceOption = None,
    countdown: Annotated[
        int,
        typer.Option(min=0, metavar="N", help="Seconds before typing starts, to focus the POS."),
    ] = 3,
    unicode: Annotated[
        bool,
        typer.Option(
            "--unicode",
            help="Type each character exactly, whatever the keyboard layout (for non-ASCII data).",
        ),
    ] = False,
) -> None:
    """Scan a barcode, then wait until the simulator confirms it was typed or written."""
    client = api(ctx)
    scanner = pick_device(client, "scanner", device)
    with client.events() as receive:  # subscribed before the request, so no delivery is missed
        body: dict[str, object] = {"data": data, "countdown_seconds": countdown, "unicode": unicode}
        accepted = client.post(device_path(scanner, "scans"), body)
        deliver_at = time.monotonic() + countdown
        delay_ms = client.get(device_path(scanner))["state"].get("inter_key_delay_ms", 0)
        deadline = deliver_at + delay_ms * (len(data) + 1) / 1000 + CONFIRM_SECONDS
        out = console()
        status = out.status("") if out.is_terminal else contextlib.nullcontext()
        with status as spinner:
            while (remaining := deadline - time.monotonic()) > 0:
                if isinstance(spinner, Status):
                    left = math.ceil(deliver_at - time.monotonic())
                    spinner.update(
                        f"Focus the POS window: typing starts in {left} s"
                        if left > 0
                        else f"Typing {data}"
                    )
                event = receive(min(0.25, remaining))
                if (
                    event is not None
                    and event["type"] == "scanner.scan.delivered"
                    and event["data"].get("id") == accepted["id"]
                ):
                    out.print(Text.assemble(("✓ ", "green"), f"{scanner} delivered ", data))
                    return
    raise CliError(
        f"the scan on {scanner} was accepted, but its delivery was not confirmed",
        "check the `emupos run` output for a warning about this scan",
        code="scan_not_confirmed",
    )


# --- scale -----------------------------------------------------------------------------------

scale_app = typer.Typer(help="Put weight on a scale, zero it or tare it.", no_args_is_help=True)


@scale_app.command("set", context_settings={"ignore_unknown_options": True})
def set_weight(
    ctx: typer.Context,
    value: Annotated[
        str,
        typer.Argument(
            metavar="VALUE",
            help=f"Gross weight: {WEIGHT_FORMS}. Whole grams only. Negative values such as -100g "
            "are allowed (also written as `emupos scale set -- -100g`).",
        ),
    ],
    device: DeviceOption = None,
    unstable: Annotated[
        bool,
        typer.Option("--unstable", help="Report the weight as in motion until the scale settles."),
    ] = False,
) -> None:
    """Set the weight on the scale, stable unless --unstable is given."""
    grams = weight_value(value, "VALUE")  # a usage error, before contacting the simulator
    client = api(ctx)
    scale = pick_device(client, "scale", device)
    client.send("PUT", device_path(scale, "weight"), {"grams": grams, "stable": not unstable})
    console().print(f"{scale}: {kilograms(grams)}, {'in motion' if unstable else 'stable'}")


@scale_app.command("zero")
def zero(ctx: typer.Context, device: DeviceOption = None) -> None:
    """Zero the scale, as pressing its ZERO key does."""
    client = api(ctx)
    scale = pick_device(client, "scale", device)
    client.post(device_path(scale, "zero"))
    console().print(f"{scale}: zeroed")


@scale_app.command("tare")
def tare(ctx: typer.Context, device: DeviceOption = None) -> None:
    """Tare the scale: the current weight becomes the tare."""
    client = api(ctx)
    scale = pick_device(client, "scale", device)
    client.post(device_path(scale, "tare"))
    console().print(f"{scale}: tared")


# --- printer faults and the drawer -----------------------------------------------------------

fault_app = typer.Typer(help="Make a printer report a fault, or clear it.", no_args_is_help=True)
PrinterArgument = Annotated[str, typer.Argument(metavar="DEVICE", help="Printer id, e.g. front.")]
FaultArgument = Annotated[
    PrinterFault,
    typer.Argument(metavar="FAULT", help="paper-near-end, paper-out, cover-open or offline."),
]


@fault_app.command("set")
def set_fault(ctx: typer.Context, device: PrinterArgument, fault: FaultArgument) -> None:
    """Activate a fault, e.g. `emupos fault set front paper-out`."""
    api(ctx).send("PUT", device_path(device, "faults", fault.value))
    console().print(f"{device}: {fault.value} active")


@fault_app.command("clear")
def clear_fault(ctx: typer.Context, device: PrinterArgument, fault: FaultArgument) -> None:
    """Clear a fault, e.g. `emupos fault clear front paper-out`."""
    api(ctx).send("DELETE", device_path(device, "faults", fault.value))
    console().print(f"{device}: {fault.value} cleared")


drawer_app = typer.Typer(help="Act on a printer's cash drawer.", no_args_is_help=True)


@drawer_app.command("close")
def close_drawer(ctx: typer.Context, device: DeviceOption = None) -> None:
    """Push the drawer shut. The POS sees it closed on its next status request."""
    client = api(ctx)
    printer = pick_device(client, "printer", device)
    client.post(device_path(printer, "drawer", "close"))
    console().print(f"{printer}: drawer closed")
