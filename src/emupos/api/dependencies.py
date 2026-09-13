"""FastAPI dependencies: the running simulator, and devices looked up by `{device_id}`.

A route asks for the device it needs, e.g. `printer: TargetPrinter`, and gets a 404 for an
unknown id or a 409 `wrong_device_type` for a device of another type without any code of its own.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from emupos.api.errors import ApiError
from emupos.daemon.runtime import DeviceRuntime
from emupos.daemon.simulator import Simulator
from emupos.printer.printer import Printer
from emupos.scale.scale import Scale
from emupos.scanner.scanner import Scanner


def get_simulator(connection: HTTPConnection) -> Simulator:
    simulator: Simulator = connection.app.state.simulator
    return simulator


SimulatorDep = Annotated[Simulator, Depends(get_simulator)]


def get_runtime(device_id: str, simulator: SimulatorDep) -> DeviceRuntime:
    try:
        return simulator.runtime(device_id)
    except KeyError:
        raise ApiError(
            404,
            "device_not_found",
            f"no device `{device_id}`",
            "list device ids with GET /api/v1/devices",
        ) from None


RuntimeDep = Annotated[DeviceRuntime, Depends(get_runtime)]


def _device_of_type[T](runtime: DeviceRuntime, kind: type[T], name: str) -> T:
    if not isinstance(runtime.device, kind):
        message = (
            f"`{runtime.config.id}` is a {runtime.config.type} and this operation needs a {name}"
        )
        raise ApiError(409, "wrong_device_type", message)
    return runtime.device


def get_printer(runtime: RuntimeDep) -> Printer:
    return _device_of_type(runtime, Printer, "printer")


def get_scale(runtime: RuntimeDep) -> Scale:
    return _device_of_type(runtime, Scale, "scale")


def get_scanner(runtime: RuntimeDep) -> Scanner:
    return _device_of_type(runtime, Scanner, "scanner")


TargetPrinter = Annotated[Printer, Depends(get_printer)]
TargetScale = Annotated[Scale, Depends(get_scale)]
TargetScanner = Annotated[Scanner, Depends(get_scanner)]


def timestamp(moment: datetime) -> str:
    """RFC 3339 UTC with milliseconds, the timestamp format used across the API."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
