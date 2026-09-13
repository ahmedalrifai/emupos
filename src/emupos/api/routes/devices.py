"""`GET /api/v1/devices` and `GET /api/v1/devices/{device_id}`: devices, endpoints and state."""

from dataclasses import asdict

from fastapi import APIRouter

from emupos.api.dependencies import RuntimeDep, SimulatorDep
from emupos.api.schemas import ConnectionInfo, DeviceInfo
from emupos.config import ScannerDevice
from emupos.daemon.runtime import DeviceRuntime
from emupos.printer.printer import Printer
from emupos.scale.scale import Scale
from emupos.scanner.scanner import Scanner

router = APIRouter()


@router.get("/devices")
async def list_devices(simulator: SimulatorDep) -> list[DeviceInfo]:
    now = simulator.now()
    return [describe(simulator.runtime(device_id), now) for device_id in simulator.device_ids()]


@router.get("/devices/{device_id}")
async def get_device(runtime: RuntimeDep, simulator: SimulatorDep) -> DeviceInfo:
    return describe(runtime, simulator.now())


def describe(runtime: DeviceRuntime, now: float) -> DeviceInfo:
    config = runtime.config
    return DeviceInfo(
        id=config.id,
        type=config.type,
        profile=None if isinstance(config, ScannerDevice) else config.profile,
        connections=[ConnectionInfo(**asdict(endpoint)) for endpoint in runtime.endpoints],
        state=_state(runtime.device, now),
    )


def _state(device: Printer | Scale | Scanner, now: float) -> dict[str, object]:
    match device:
        case Printer():
            state = device.state()
            return {"faults": list(state.faults), "drawer": state.drawer}
        case Scale():
            weight = device.state(now)
            return {
                "grams": weight.grams,
                "tare_grams": weight.tare_grams,
                "net_grams": weight.net_grams,
                "stable": weight.stable,
                "capacity_grams": weight.capacity_grams,
            }
        case Scanner():
            return {
                "mode": device.mode,
                "suffix": device.suffix,
                "inter_key_delay_ms": device.inter_key_delay_ms,
            }
