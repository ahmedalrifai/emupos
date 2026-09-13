"""`POST /api/v1/barcodes/weighed`: weight- or price-embedded EAN-13 digits. Needs no device."""

from fastapi import APIRouter

from emupos.api.errors import ApiError
from emupos.api.schemas import WeighedBarcode, WeighedBarcodeRequest
from emupos.barcodes.weighed import WeighedBarcodeError, generate

router = APIRouter()


@router.post("/barcodes/weighed")
async def weighed_barcode(body: WeighedBarcodeRequest) -> WeighedBarcode:
    try:
        digits = generate(
            body.layout, item=body.item, grams=body.grams, price_minor=body.price_minor
        )
    except WeighedBarcodeError as error:
        raise ApiError(422, "validation_error", error.message, error.fix) from None
    return WeighedBarcode(digits=digits)
