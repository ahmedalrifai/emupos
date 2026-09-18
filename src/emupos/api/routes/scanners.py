"""Scanner endpoints: request a scan, and report back on a scan the client typed."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response

from emupos.api.dependencies import SimulatorDep, TargetScanner, timestamp
from emupos.api.errors import ApiError
from emupos.api.schemas import ScanAccepted, ScanRequest, ScanTypedReport, key_out
from emupos.scanner.scanner import ScanRejectedError
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

router = APIRouter()

# A machine with no desktop of its own has a second way out, beside serial mode.
CLIENT_TYPING_FIX = (
    "or set `typed_by: client` on this scanner and run `emupos scan` on the machine with your "
    "POS window"
)


@router.post("/devices/{device_id}/scans", status_code=202)
async def request_scan(
    scanner: TargetScanner, body: ScanRequest, simulator: SimulatorDep, response: Response
) -> ScanAccepted:
    try:
        accepted = simulator.request_scan(scanner, body.data, body.countdown_seconds, body.unicode)
    except ScanRejectedError as error:
        if error.conflict:
            raise ApiError(409, error.code, error.message, error.fix) from None
        raise ApiError(422, "validation_error", error.message, error.fix) from None
    except KeyboardUnavailableError as error:
        fix = f"{error.fix}; {CLIENT_TYPING_FIX}"
        raise ApiError(409, "keyboard_unavailable", error.message, fix) from None
    delay = max(0.0, accepted.deliver_at - simulator.now())
    deliver_at = timestamp(datetime.now(UTC) + timedelta(seconds=delay))
    if scanner.typed_by == "client":
        # Nothing further happens here: the client types these keys and reports back (design D3).
        response.status_code = 200
        return ScanAccepted(
            id=accepted.id,
            deliver_at=deliver_at,
            typed_by="client",
            keys=[key_out(key) for key in accepted.keys],
            inter_key_delay_ms=scanner.inter_key_delay_ms,
        )
    return ScanAccepted(id=accepted.id, deliver_at=deliver_at, typed_by="server")


@router.post("/devices/{device_id}/scans/{scan_id}/typed", status_code=204)
async def report_typed(
    scanner: TargetScanner, scan_id: str, body: ScanTypedReport, simulator: SimulatorDep
) -> None:
    """How the client's typing went. A scan id that is not the one in progress does nothing."""
    if scanner.typed_by != "client":
        raise ApiError(
            409,
            "typed_by_mismatch",
            f"`{scanner.device_id}` types its own scans, so it takes no report",
            "report a scan only for a scanner configured with `typed_by: client`",
        )
    simulator.report_typed(scanner, scan_id, body.outcome, body.keys_accepted, body.reason)
