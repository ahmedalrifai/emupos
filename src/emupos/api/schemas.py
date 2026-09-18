"""Request and response bodies of the control API. They also document the API in OpenAPI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from emupos.scanner.keys import Key, key_to_json


class RequestBody(BaseModel):
    """Request bodies reject unknown fields and never coerce types (1.25 is not an integer)."""

    model_config = ConfigDict(extra="forbid", strict=True)


# --- requests ------------------------------------------------------------------------------


class WeightRequest(RequestBody):
    grams: int
    stable: bool = True


class ScanRequest(RequestBody):
    data: str
    countdown_seconds: int = 3
    unicode: bool = False


class ScanTypedReport(RequestBody):
    outcome: Literal["delivered", "failed"]
    keys_accepted: int | None = None
    reason: str | None = None


class WeighedBarcodeRequest(RequestBody):
    layout: str
    item: int
    grams: int | None = None
    price_minor: int | None = None


# --- responses -----------------------------------------------------------------------------


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    api_version: int


class ConnectionInfo(BaseModel):
    kind: Literal["tcp", "serial"]
    endpoint: str
    link_path: str | None = None
    device_path: str | None = None


class DeviceInfo(BaseModel):
    id: str
    type: Literal["printer", "scale", "scanner"]
    profile: str | None
    connections: list[ConnectionInfo]
    state: dict[str, object]


class ReceiptInfo(BaseModel):
    id: str
    device_id: str
    completed_at: str
    width_dots: int
    height_dots: int
    boundary: str


class PhysicalKeyOut(BaseModel):
    """A key by position: its HID usage ID on page 0x07, and whether Shift is held."""

    usage: int
    shift: bool


class UnicodeTextOut(BaseModel):
    """One character, typed exactly whatever the active keyboard layout."""

    char: str


type KeyOut = PhysicalKeyOut | UnicodeTextOut


def key_out(key: Key) -> KeyOut:
    """One planned key as the API returns it. `scanner.keys` owns the wire form (design D9)."""
    value = key_to_json(key)
    return (
        UnicodeTextOut.model_validate(value)
        if "char" in value
        else PhysicalKeyOut.model_validate(value)
    )


class ScanAccepted(BaseModel):
    id: str
    deliver_at: str  # when delivery starts: emupos types then, or the client is to start typing
    typed_by: Literal["server", "client"] = "server"
    # `typed_by` client only: the keys to press, and the delay to leave between them.
    keys: list[KeyOut] | None = None
    inter_key_delay_ms: int | None = None


class WeighedBarcode(BaseModel):
    digits: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fix: str | None


class ErrorResponse(BaseModel):
    error: ErrorDetail
