"""`emupos barcode weighed` (weighed-item-barcodes spec, "Barcode generation in the CLI")."""

from pathlib import Path
from typing import Annotated

import typer

from emupos.barcodes.weighed import PRESETS, WeighedBarcodeError, generate, render_png
from emupos.cli.actions import WEIGHT_FORMS, weight_value
from emupos.cli.output import CliError, note

barcode_app = typer.Typer(
    help="Generate barcodes that a POS decodes. Works without the simulator.",
    no_args_is_help=True,
)


@barcode_app.command("weighed")
def weighed(
    layout: Annotated[
        str,
        typer.Option(
            metavar="PATTERN",
            help=f"13-character pattern such as 21IIIIIWWWWWC, or a preset: {', '.join(PRESETS)}.",
        ),
    ],
    item: Annotated[int, typer.Option(metavar="N", help="Item code for the I field.")],
    weight: Annotated[
        str | None,
        typer.Option(
            metavar="VALUE",
            help=f"Weight for a W field: {WEIGHT_FORMS}.",
        ),
    ] = None,
    price: Annotated[
        int | None,
        typer.Option(metavar="MINOR", help="Price for a P field, in minor units: 1299 is 12.99."),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option(metavar="PATH", help="Also write a PNG label with the digits beneath it."),
    ] = None,
) -> None:
    """Print the EAN-13 digits for a weighed or priced item, e.g.

    emupos barcode weighed --layout weight-21 --item 12345 --weight 1.25kg
    """
    if weight is not None and price is not None:
        raise CliError(
            "--weight and --price are mutually exclusive",
            "give --weight for a layout with a W field, or --price for a layout with a P field",
            code="usage_error",
            exit_code=2,
        )
    grams = None if weight is None else weight_value(weight, "--weight")
    try:
        digits = generate(layout, item=item, grams=grams, price_minor=price)
    except WeighedBarcodeError as error:
        raise CliError(error.message, error.fix, code="invalid_barcode", exit_code=2) from None
    if save is not None:
        try:
            save.write_bytes(render_png(digits))
        except OSError as error:
            raise CliError(f"cannot write {save}: {error.strerror}") from None
        note(f"Saved the label image to {save}")
    typer.echo(digits)
