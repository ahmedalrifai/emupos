"""Scanner endpoint: request a scan, delivered in the background after a countdown."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from emupos.api.dependencies import SimulatorDep, TargetScanner, timestamp
from emupos.api.errors import ApiError
from emupos.api.schemas import ScanAccepted, ScanRequest
from emupos.scanner.scanner import ScanRejectedError
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

router = APIRouter()


@router.post("/devices/{device_id}/scans", status_code=202)
async def request_scan(
    scanner: TargetScanner, body: ScanRequest, simulator: SimulatorDep
) -> ScanAccepted:
    try:
        accepted = simulator.request_scan(scanner, body.data, body.countdown_seconds, body.unicode)
    except ScanRejectedError as error:
        if error.conflict:
            raise ApiError(409, error.code, error.message, error.fix) from None
        raise ApiError(422, "validation_error", error.message, error.fix) from None
    except KeyboardUnavailableError as error:
        raise ApiError(409, "keyboard_unavailable", error.message, error.fix) from None
    delay = max(0.0, accepted.deliver_at - simulator.now())
    return ScanAccepted(
        id=accepted.id, deliver_at=timestamp(datetime.now(UTC) + timedelta(seconds=delay))
    )
