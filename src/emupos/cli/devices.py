"""The read commands: `devices`, `receipt list`, `receipt show` (cli spec, "Devices and receipts commands")."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from emupos.cli.client import DeviceOption, api, device_path, pick_device
from emupos.cli.output import CliError, console, kilograms, note, print_json, table, use_json

JsonOption = Annotated[
    bool, typer.Option("--json", help="Print one JSON document instead of text.")
]


def devices(ctx: typer.Context, json_output: JsonOption = False) -> None:
    """List the running devices with their connections and current state."""
    use_json(ctx, json_output)
    items = api(ctx).get("/devices")
    if json_output:
        print_json(items)
        return
    rows = table("DEVICE", "TYPE", "PROFILE", "CONNECTIONS", "STATE")
    for device in items:
        connections = "\n".join(connection_text(c) for c in device["connections"]) or "-"
        rows.add_row(
            device["id"], device["type"], device["profile"] or "-", connections, state_text(device)
        )
    console().print(rows)


def connection_text(connection: dict[str, Any]) -> str:
    text = f"{connection['kind']} {connection['endpoint']}"
    if connection.get("device_path"):
        text += f" -> {connection['device_path']}"
    return text


def state_text(device: dict[str, Any]) -> str:
    state = device["state"]
    match device["type"]:
        case "printer":
            faults = ", ".join(state["faults"]) or "none"
            return f"drawer {state['drawer']}, faults: {faults}"
        case "scale":
            text = f"{kilograms(state['grams'])} {'stable' if state['stable'] else 'in motion'}"
            if state["tare_grams"]:
                text += (
                    f", tare {kilograms(state['tare_grams'])}, net {kilograms(state['net_grams'])}"
                )
            # Weights are shown in kilograms whatever the scale reports in, so name the unit the
            # POS reads: a host can switch it over the protocol, without anyone touching emupos.
            if state.get("unit"):
                text += f", reporting {state['unit']}"
            return text
        case "scanner":
            text = f"{state['mode']} mode, suffix {state['suffix']}, {state['inter_key_delay_ms']} ms between keys"
            if state.get("typed_by") == "client":
                text += ", typed by the client"
            return text
        case _:
            return ""


receipt_app = typer.Typer(help="Read the receipts a printer has completed.", no_args_is_help=True)


@receipt_app.command("list")
def list_receipts(
    ctx: typer.Context, device: DeviceOption = None, json_output: JsonOption = False
) -> None:
    """List a printer's receipts, newest first."""
    use_json(ctx, json_output)
    client = api(ctx)
    printer = pick_device(client, "printer", device)
    receipts = client.get(device_path(printer, "receipts"))
    if json_output:
        print_json(receipts)
        return
    if not receipts:
        console().print(f"{printer} has no receipts yet")
        return
    rows = table("RECEIPT", "COMPLETED", "ENDED BY", "SIZE")
    for receipt in receipts:
        completed = datetime.fromisoformat(receipt["completed_at"]).astimezone()
        size = f"{receipt['width_dots']}x{receipt['height_dots']} dots"
        rows.add_row(receipt["id"], f"{completed:%Y-%m-%d %H:%M:%S}", receipt["boundary"], size)
    console().print(rows)


@receipt_app.command("show")
def show_receipt(
    ctx: typer.Context,
    receipt_id: Annotated[
        str, typer.Argument(metavar="RECEIPT_ID", help="Receipt id from `emupos receipt list`.")
    ] = "latest",
    device: DeviceOption = None,
    save: Annotated[
        Path | None, typer.Option(metavar="PATH", help="Also write the receipt image as PNG.")
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Print a receipt as text; the latest one unless RECEIPT_ID is given."""
    use_json(ctx, json_output)
    client = api(ctx)
    printer = pick_device(client, "printer", device)
    receipt = client.get(device_path(printer, "receipts", receipt_id))
    # Use the resolved id from here on, so `latest` cannot change between requests.
    text = client.send("GET", device_path(printer, "receipts", receipt["id"], "text")).decode()
    if save is not None:
        image = client.send("GET", device_path(printer, "receipts", receipt["id"], "image"))
        try:
            save.write_bytes(image)
        except OSError as error:
            raise CliError(f"cannot write {save}: {error.strerror}") from None
    if json_output:
        print_json({**receipt, "text": text})
        return
    typer.echo(text, nl=not text.endswith("\n"))
    if save is not None:
        note(f"Saved the receipt image to {save}")
