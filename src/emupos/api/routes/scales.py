"""Scale endpoints: set the weight, zero and tare."""

import contextlib
from collections.abc import Generator

from fastapi import APIRouter, Response

from emupos.api.dependencies import SimulatorDep, TargetScale
from emupos.api.errors import ApiError
from emupos.api.schemas import WeightRequest
from emupos.scale.scale import ScaleInMotionError

router = APIRouter()


@router.put("/devices/{device_id}/weight", status_code=204)
async def set_weight(scale: TargetScale, body: WeightRequest, simulator: SimulatorDep) -> Response:
    simulator.set_weight(scale, body.grams, body.stable)
    return Response(status_code=204)


@router.post("/devices/{device_id}/zero", status_code=204)
async def zero(scale: TargetScale, simulator: SimulatorDep) -> Response:
    with _refused_in_motion():
        simulator.zero(scale)
    return Response(status_code=204)


@router.post("/devices/{device_id}/tare", status_code=204)
async def tare(scale: TargetScale, simulator: SimulatorDep) -> Response:
    with _refused_in_motion():
        simulator.tare(scale)
    return Response(status_code=204)


@contextlib.contextmanager
def _refused_in_motion() -> Generator[None]:
    """A real scale refuses zero and tare while the reading moves: answer 409 with the reason."""
    try:
        yield
    except ScaleInMotionError as error:
        raise ApiError(409, "scale_in_motion", error.message, error.fix) from None
