"""Request and response bodies of the control API. They also document the API in OpenAPI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class ScanAccepted(BaseModel):
    id: str
    deliver_at: str


class WeighedBarcode(BaseModel):
    digits: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fix: str | None


class ErrorResponse(BaseModel):
    error: ErrorDetail
