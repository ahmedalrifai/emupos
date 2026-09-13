"""Printer endpoints: fault injection, closing the cash drawer, and completed receipts."""

from fastapi import APIRouter, Response

from emupos.api.dependencies import SimulatorDep, TargetPrinter, timestamp
from emupos.api.errors import ApiError
from emupos.api.schemas import ReceiptInfo
from emupos.printer.printer import PrinterFault
from emupos.printer.receipts import LATEST, ReceiptMeta, ReceiptStore

router = APIRouter()


@router.put("/devices/{device_id}/faults/{fault}", status_code=204)
async def activate_fault(printer: TargetPrinter, fault: str, simulator: SimulatorDep) -> Response:
    simulator.set_fault(printer, _fault(fault), active=True)
    return Response(status_code=204)


@router.delete("/devices/{device_id}/faults/{fault}", status_code=204)
async def clear_fault(printer: TargetPrinter, fault: str, simulator: SimulatorDep) -> Response:
    simulator.set_fault(printer, _fault(fault), active=False)
    return Response(status_code=204)


@router.post("/devices/{device_id}/drawer/close", status_code=204)
async def close_drawer(printer: TargetPrinter, simulator: SimulatorDep) -> Response:
    simulator.close_drawer(printer)
    return Response(status_code=204)


@router.get("/devices/{device_id}/receipts")
async def list_receipts(printer: TargetPrinter, simulator: SimulatorDep) -> list[ReceiptInfo]:
    store = simulator.receipts[printer.device_id]
    return [_receipt_info(meta) for meta in store.list(printer.device_id)]


@router.get("/devices/{device_id}/receipts/{receipt_id}")
async def get_receipt(
    printer: TargetPrinter, receipt_id: str, simulator: SimulatorDep
) -> ReceiptInfo:
    return _receipt_info(
        _find(simulator.receipts[printer.device_id], printer.device_id, receipt_id)
    )


@router.get("/devices/{device_id}/receipts/{receipt_id}/image", response_class=Response)
async def get_receipt_image(
    printer: TargetPrinter, receipt_id: str, simulator: SimulatorDep
) -> Response:
    store = simulator.receipts[printer.device_id]
    meta = _find(store, printer.device_id, receipt_id)
    return Response(store.image(printer.device_id, meta.id), media_type="image/png")


@router.get("/devices/{device_id}/receipts/{receipt_id}/text", response_class=Response)
async def get_receipt_text(
    printer: TargetPrinter, receipt_id: str, simulator: SimulatorDep
) -> Response:
    store = simulator.receipts[printer.device_id]
    meta = _find(store, printer.device_id, receipt_id)
    return Response(store.text(printer.device_id, meta.id), media_type="text/plain; charset=utf-8")


def _fault(name: str) -> PrinterFault:
    try:
        return PrinterFault(name)
    except ValueError:
        valid = ", ".join(PrinterFault)
        raise ApiError(
            422, "validation_error", f"unknown fault `{name}`; valid faults: {valid}"
        ) from None


def _find(store: ReceiptStore, device_id: str, receipt_id: str) -> ReceiptMeta:
    meta = store.get(device_id, receipt_id)
    if meta is None:
        problem = (
            "has no receipts yet" if receipt_id == LATEST else f"has no receipt `{receipt_id}`"
        )
        fix = f"list receipts with GET /api/v1/devices/{device_id}/receipts"
        raise ApiError(404, "receipt_not_found", f"`{device_id}` {problem}", fix)
    return meta


def _receipt_info(meta: ReceiptMeta) -> ReceiptInfo:
    return ReceiptInfo(
        id=meta.id,
        device_id=meta.device_id,
        completed_at=timestamp(meta.completed_at),
        width_dots=meta.width_dots,
        height_dots=meta.height_dots,
        boundary=meta.boundary,
    )
