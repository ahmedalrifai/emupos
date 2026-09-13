"""What the daemon keeps for each running device, and how devices are built from configuration."""

import asyncio
from dataclasses import dataclass, field

from emupos.config import LoadedConfig, PrinterDevice, ScaleDevice, ScannerDevice
from emupos.events import ConnectionId
from emupos.printer.printer import Printer
from emupos.printer.receipts import ReceiptStore
from emupos.scale.scale import Scale
from emupos.scanner.scanner import Scanner

type Device = Printer | Scale | Scanner
type DeviceConfig = PrinterDevice | ScaleDevice | ScannerDevice


class StartupError(Exception):
    """A device connection or the control API could not be opened. Nothing is left open."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    """A resolved connection endpoint, as shown by `emupos run` and the control API."""

    kind: str  # "tcp" or "serial"
    endpoint: str  # "127.0.0.1:9100", a link path, or a port name
    link_path: str | None = None
    device_path: str | None = None


@dataclass(slots=True)
class DeviceRuntime:
    config: DeviceConfig
    device: Device
    receipts: ReceiptStore | None = None  # printers only
    endpoints: list[Endpoint] = field(default_factory=list[Endpoint])
    writers: dict[ConnectionId, asyncio.StreamWriter] = field(
        default_factory=dict[ConnectionId, asyncio.StreamWriter]
    )
    timer: asyncio.TimerHandle | None = None  # the next `tick` of a printer or scale


def build_runtime(config: DeviceConfig, loaded: LoadedConfig) -> DeviceRuntime:
    match config:
        case PrinterDevice():
            printer = Printer(
                config.id,
                loaded.printer_profile(config.id),
                sensor_open_level=loaded.drawer_sensor_open_level(config),
                job_idle_timeout_ms=config.job_idle_timeout_ms,
            )
            return DeviceRuntime(config, printer, ReceiptStore(loaded.receipts_dir(config)))
        case ScaleDevice():
            return DeviceRuntime(config, Scale(config.id, loaded.scale_profile(config.id)))
        case ScannerDevice():
            scanner = Scanner(config.id, config.mode, config.suffix, config.inter_key_delay_ms)
            return DeviceRuntime(config, scanner)
