"""Test helpers shared by the printer, drawer and rendering tests (no tests here).

`Pos` plays the POS and the operator against one `Printer`, collecting everything the printer
outputs. Time only moves when a test calls `wait`.
"""

import io
from pathlib import Path

from PIL import Image, ImageChops

from emupos.config import Level, PrinterProfile, parse_config
from emupos.events import Event, EventType
from emupos.printer.escpos.render import RenderedReceipt
from emupos.printer.printer import Printer, PrinterFault, PrinterOutput


def load_profile(name: str = "epson-tm-t20iii") -> PrinterProfile:
    text = (
        "schema: 1\n"
        f"devices: [ {{ id: front, type: printer, profile: {name}, "
        "connections: [ { tcp: { port: 9100 } } ] } ]\n"
    )
    return parse_config(text, "test configuration", Path()).printer_profile("front")


class Pos:
    def __init__(
        self,
        profile: str = "epson-tm-t20iii",
        *,
        sensor_open_level: Level = "high",
        job_idle_timeout_ms: int = 2000,
        connections: tuple[str, ...] = ("A",),
    ) -> None:
        self.printer = Printer(
            "front",
            load_profile(profile),
            sensor_open_level=sensor_open_level,
            job_idle_timeout_ms=job_idle_timeout_ms,
        )
        self.now = 0.0
        self.received: dict[str, bytearray] = {}
        self.events: list[Event] = []
        self.receipts: list[RenderedReceipt] = []
        for connection in connections:
            self.connect(connection)

    def connect(self, connection: str = "A") -> None:
        self._collect(self.printer.open_connection(connection, self.now))

    def send(self, data: str | bytes, connection: str = "A") -> None:
        """Send bytes, given as bytes or as spaced hex."""
        payload = bytes.fromhex(data) if isinstance(data, str) else data
        self._collect(self.printer.receive(connection, payload, self.now))

    def close(self, connection: str = "A") -> None:
        self._collect(self.printer.close_connection(connection, self.now))

    def set_fault(self, fault: str, active: bool = True) -> None:
        self._collect(self.printer.set_fault(PrinterFault(fault), active, self.now))

    def close_drawer(self) -> None:
        self._collect(self.printer.close_drawer(self.now))

    def wait(self, seconds: float) -> None:
        self.now += seconds
        self._collect(self.printer.tick(self.now))

    def take(self, connection: str = "A") -> bytes:
        """The bytes received on a connection since the last call."""
        return bytes(self.received.pop(connection, b""))

    def events_of(self, event_type: EventType) -> list[Event]:
        return [event for event in self.events if event.type == event_type]

    @property
    def texts(self) -> list[str]:
        return [receipt.text for receipt in self.receipts]

    def _collect(self, output: PrinterOutput) -> None:
        for write in output.writes:
            self.received.setdefault(write.connection, bytearray()).extend(write.data)
        self.events += output.events
        self.receipts += output.receipts


def image_of(receipt: RenderedReceipt) -> Image.Image:
    return Image.open(io.BytesIO(receipt.png)).convert("1")


def ink_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box (left, top, right, bottom; right and bottom exclusive) of the black dots."""
    return ImageChops.invert(image.convert("L")).getbbox()
