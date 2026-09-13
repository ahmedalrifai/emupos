"""The running simulator — the only file that wires everything together (design D4).

configuration → devices → connections → device output → events, receipts and replies.

Device code is pure and single-threaded: every call into a device happens on the event loop,
so no locks are needed. The loop's monotonic clock is the `now` passed to devices.
"""

import asyncio
import contextlib
import logging
import signal
import socket
import sys
from collections.abc import Awaitable, Callable, Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from emupos.config import (
    Connection,
    LoadedConfig,
    PrinterDevice,
    ScaleDevice,
    ScannerDevice,
    SerialFraming,
)
from emupos.events import ConnectionId, Event, EventBus, EventType, Output, PublishedEvent
from emupos.printer.printer import Printer, PrinterFault, PrinterOutput
from emupos.printer.receipts import ReceiptStore
from emupos.scale.scale import Scale
from emupos.scanner.scanner import AcceptedScan, Scanner
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.framing import Mismatch, watch_framing
from emupos.transports.keyboard.keyboard import Keyboard, system_keyboard, type_keys
from emupos.transports.pty import PtyPort, open_pty
from emupos.transports.serial_port import SerialPort, open_serial_port
from emupos.transports.tcp import TcpListener, serve_tcp

logger = logging.getLogger("emupos")

type Device = Printer | Scale | Scanner

# A serial-mode scanner has no profile; it expects the framing most scanners ship with.
SCANNER_FRAMING = SerialFraming(baud=9600, data_bits=8, parity="none", stop_bits=1)
READ_SIZE = 65536


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
    """What the daemon keeps for one device while it runs."""

    config: PrinterDevice | ScaleDevice | ScannerDevice
    device: Device
    endpoints: list[Endpoint] = field(default_factory=list[Endpoint])
    writers: dict[ConnectionId, asyncio.StreamWriter] = field(
        default_factory=dict[ConnectionId, asyncio.StreamWriter]
    )
    timer: asyncio.TimerHandle | None = None


class Simulator:
    def __init__(self, loaded: LoadedConfig, *, link_dir: Path | None = None) -> None:
        self.loaded = loaded
        self.bus = EventBus()
        self.receipts: dict[str, ReceiptStore] = {}
        self._link_dir = link_dir
        self._runtimes: dict[str, DeviceRuntime] = {}
        self._listeners: list[TcpListener] = []
        self._ports: list[PtyPort | SerialPort] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._keyboard: Keyboard | None = None
        self.startup_events: tuple[PublishedEvent, ...] = ()
        for device in loaded.config.devices:
            self._runtimes[device.id] = DeviceRuntime(device, self._build(device))

    # --- lifecycle -----------------------------------------------------------------------

    async def start(self) -> None:
        """Open every connection, or close whatever was opened and raise StartupError.

        Events published while starting (e.g. serial ports opening) are kept in `startup_events`,
        because subscribers that need the started simulator can only subscribe afterwards.
        """
        recorded: list[PublishedEvent] = []
        stop_recording = self.bus.subscribe(recorded.append)
        try:
            for runtime in self._runtimes.values():
                try:
                    for connection in runtime.config.connections:
                        await self._open(runtime, connection)
                except EndpointUnavailableError as error:
                    await self.stop()
                    raise StartupError(f"device `{runtime.config.id}`: {error}") from None
        finally:
            stop_recording()
        self.startup_events = tuple(recorded)

    async def stop(self) -> None:
        """Close every connection and link. Safe to call more than once."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for listener in self._listeners:
            await listener.close()
        for port in self._ports:
            await port.close()
        self._listeners.clear()
        self._ports.clear()
        for runtime in self._runtimes.values():
            if runtime.timer is not None:
                runtime.timer.cancel()

    # --- queries for the control API --------------------------------------------------------

    def device_ids(self) -> list[str]:
        return list(self._runtimes)

    def runtime(self, device_id: str) -> DeviceRuntime:
        return self._runtimes[device_id]  # KeyError: unknown device, mapped to 404 by the API

    def now(self) -> float:
        return asyncio.get_running_loop().time()

    # --- operations for the control API ----------------------------------------------------

    def set_fault(self, printer: Printer, fault: PrinterFault, active: bool) -> None:
        self.apply(printer.device_id, printer.set_fault(fault, active, self.now()))

    def close_drawer(self, printer: Printer) -> None:
        self.apply(printer.device_id, printer.close_drawer(self.now()))

    def set_weight(self, scale: Scale, grams: int, stable: bool) -> None:
        self.apply(scale.device_id, scale.set_weight(grams, stable, self.now()))

    def zero(self, scale: Scale) -> None:
        self.apply(scale.device_id, scale.zero(self.now()))  # may raise ScaleInMotionError

    def tare(self, scale: Scale) -> None:
        self.apply(scale.device_id, scale.tare(self.now()))  # may raise ScaleInMotionError

    def request_scan(
        self, scanner: Scanner, data: str, countdown_seconds: int, unicode: bool
    ) -> AcceptedScan:
        """Accept a scan and deliver it in the background. Raises the scanner's rejection errors."""
        keyboard: Keyboard | None = None
        if scanner.mode == "keyboard":
            keyboard = self._keyboard or system_keyboard()
            keyboard.check_ready()  # may raise KeyboardUnavailableError
            self._keyboard = keyboard
        accepted = scanner.request(data, countdown_seconds, unicode, self.now())
        self._spawn(self._deliver_scan(scanner, accepted, keyboard))
        return accepted

    # --- applying device output ------------------------------------------------------------

    def apply(self, device_id: str, output: Output) -> None:
        """Perform what a device operation produced: replies, receipts, events, next timer."""
        runtime = self._runtimes[device_id]
        for write in output.writes:
            writer = runtime.writers.get(write.connection)
            if writer is not None and not writer.is_closing():
                # ponytail: replies are a few bytes; no backpressure unless a client never reads.
                writer.write(write.data)
        for event in output.events:
            self.bus.publish(event)
        if isinstance(output, PrinterOutput):
            store = self.receipts[device_id]
            for receipt in output.receipts:
                meta = store.save(device_id, receipt, datetime.now(UTC))
                data = {"receipt_id": meta.id, "boundary": receipt.boundary}
                self.bus.publish(Event(EventType.PRINTER_JOB_COMPLETED, device_id, data))
        self._schedule_tick(runtime)

    def _schedule_tick(self, runtime: DeviceRuntime) -> None:
        device = runtime.device
        if runtime.timer is not None:
            runtime.timer.cancel()
            runtime.timer = None
        if isinstance(device, Scanner) or (deadline := device.next_deadline()) is None:
            return
        loop = asyncio.get_running_loop()
        runtime.timer = loop.call_at(
            deadline, lambda: self.apply(device.device_id, device.tick(self.now()))
        )

    # --- connections ----------------------------------------------------------------------

    def _build(self, device: PrinterDevice | ScaleDevice | ScannerDevice) -> Device:
        match device:
            case PrinterDevice():
                self.receipts[device.id] = ReceiptStore(self.loaded.receipts_dir(device))
                return Printer(
                    device.id,
                    self.loaded.printer_profile(device.id),
                    sensor_open_level=self.loaded.drawer_sensor_open_level(device),
                    job_idle_timeout_ms=device.job_idle_timeout_ms,
                )
            case ScaleDevice():
                return Scale(device.id, self.loaded.scale_profile(device.id))
            case ScannerDevice():
                return Scanner(device.id, device.mode, device.suffix, device.inter_key_delay_ms)

    async def _open(self, runtime: DeviceRuntime, connection: Connection) -> None:
        device_id = runtime.config.id
        if connection.tcp is not None:
            tcp = connection.tcp

            async def on_client(
                conn: ConnectionId, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
            ) -> None:
                client = writer.get_extra_info("peername")
                endpoint = {
                    "kind": "tcp",
                    "endpoint": f"{tcp.host}:{tcp.port}",
                    "client": f"{client[0]}:{client[1]}",
                }
                await self._serve_connection(runtime, conn, reader, writer, endpoint)

            listener = await serve_tcp(tcp.host, tcp.port, on_client)
            self._listeners.append(listener)
            runtime.endpoints.append(Endpoint("tcp", f"{tcp.host}:{tcp.port}"))
        elif connection.serial is not None and connection.serial.pty:
            framing = self._framing(runtime)
            port = await open_pty(connection.serial.link or device_id, framing, self._link_dir)
            self._ports.append(port)
            runtime.endpoints.append(
                Endpoint("serial", str(port.link_path), str(port.link_path), port.device_path)
            )
            endpoint = {"kind": "serial", "endpoint": str(port.link_path)}
            self._spawn(
                self._serve_connection(
                    runtime, port.connection_id, port.reader, port.writer, endpoint
                )
            )
            self._spawn(
                watch_framing(
                    port.slave_fd, framing, self._framing_reporter(device_id, str(port.link_path))
                )
            )
        elif connection.serial is not None and connection.serial.port is not None:
            # Existing device paths on macOS/Linux; Windows COM ports wait for the serial spike (task 4.4).
            port = await open_serial_port(connection.serial.port, self._framing(runtime))
            self._ports.append(port)
            runtime.endpoints.append(Endpoint("serial", port.path))
            endpoint = {"kind": "serial", "endpoint": port.path}
            self._spawn(
                self._serve_connection(
                    runtime, port.connection_id, port.reader, port.writer, endpoint
                )
            )

    async def _serve_connection(
        self,
        runtime: DeviceRuntime,
        conn: ConnectionId,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        endpoint: dict[str, str],
    ) -> None:
        device, device_id = runtime.device, runtime.config.id
        runtime.writers[conn] = writer
        self.bus.publish(Event(EventType.CONNECTION_OPENED, device_id, endpoint))
        try:
            if not isinstance(device, Scanner):
                self.apply(device_id, device.open_connection(conn, self.now()))
            while data := await reader.read(READ_SIZE):
                if not isinstance(device, Scanner):  # a scanner ignores bytes sent to it
                    self.apply(device_id, device.receive(conn, data, self.now()))
        finally:
            runtime.writers.pop(conn, None)
            if not isinstance(device, Scanner):
                self.apply(device_id, device.close_connection(conn, self.now()))
            self.bus.publish(Event(EventType.CONNECTION_CLOSED, device_id, endpoint))

    def _framing(self, runtime: DeviceRuntime) -> SerialFraming:
        device = runtime.config
        if isinstance(device, ScannerDevice):
            return SCANNER_FRAMING
        profile = self.loaded.profiles[device.id]
        if profile.serial is None:  # config validation rejects this; kept for type narrowing
            raise EndpointUnavailableError(f"profile `{device.profile}` defines no serial framing")
        return profile.serial

    def _framing_reporter(
        self, device_id: str, link: str
    ) -> Callable[[tuple[Mismatch, ...]], None]:
        def report(mismatches: tuple[Mismatch, ...]) -> None:
            settings = [
                {"setting": m.setting, "expected": m.expected, "observed": m.observed}
                for m in mismatches
            ]
            self.bus.publish(
                Event(
                    EventType.CONNECTION_FRAMING_MISMATCH,
                    device_id,
                    {"endpoint": link, "mismatches": settings},
                )
            )
            described = ", ".join(
                f"{m.setting} expected {m.expected} observed {m.observed}" for m in mismatches
            )
            logger.warning("%s: serial framing mismatch on %s: %s", device_id, link, described)

        return report

    # --- scans ----------------------------------------------------------------------------

    async def _deliver_scan(
        self, scanner: Scanner, scan: AcceptedScan, keyboard: Keyboard | None
    ) -> None:
        runtime = self._runtimes[scanner.device_id]
        try:
            await asyncio.sleep(max(0.0, scan.deliver_at - self.now()))
            if keyboard is None:
                for writer in runtime.writers.values():
                    writer.write(scan.serial_bytes)
                    await writer.drain()
            else:
                accepted = await type_keys(keyboard, scan.keys, scanner.inter_key_delay_ms)
                if accepted < len(scan.keys):
                    logger.warning(
                        "%s: the operating system accepted %d of %d keystrokes; on Windows, keystrokes do not reach "
                        "a window running with higher privileges than emupos",
                        scanner.device_id,
                        accepted,
                        len(scan.keys),
                    )
                    scanner.failed(scan.id)
                    return
        except BaseException:
            scanner.failed(scan.id)
            raise
        self.apply(scanner.device_id, scanner.finished(scan.id))

    def _spawn(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def bind_api_socket(host: str, port: int) -> socket.socket:
    """Bind the control API port before any device opens, so a conflict opens nothing."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    if sys.platform != "win32":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as error:
        sock.close()
        raise StartupError(
            f"control API port {port} on {host} is not available: {error.strerror or error}"
        ) from None
    sock.listen(128)
    sock.setblocking(False)
    return sock


class _ApiServer(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield  # `run` handles Ctrl+C and SIGTERM itself so devices shut down cleanly


async def run(loaded: LoadedConfig, on_started: Callable[[Simulator], None]) -> None:
    """Run the simulator and its control API until Ctrl+C or SIGTERM, then shut down cleanly.

    Raises StartupError, with nothing left open, when the API port or a device endpoint is unavailable.
    """
    api = loaded.config.api
    api_socket = bind_api_socket(api.host, api.port)
    simulator = Simulator(loaded)
    try:
        await simulator.start()
    except BaseException:
        api_socket.close()
        raise
    from emupos.api.app import create_app  # imported here: the API modules import this module

    config = uvicorn.Config(
        create_app(simulator),
        log_level="warning",
        access_log=False,
        lifespan="off",
        timeout_graceful_shutdown=2,  # never let a stuck client block Ctrl+C
    )
    server = _ApiServer(config)
    serving = asyncio.create_task(server.serve(sockets=[api_socket]))
    stopping = asyncio.Event()
    if sys.platform != "win32":
        # Ctrl+C cancels this coroutine (asyncio.run); SIGTERM gets the same clean shutdown.
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stopping.set)
    try:
        on_started(simulator)
        waiting = asyncio.create_task(stopping.wait())
        await asyncio.wait({serving, waiting}, return_when=asyncio.FIRST_COMPLETED)
        waiting.cancel()
    finally:
        server.should_exit = True
        await asyncio.gather(serving, return_exceptions=True)
        await simulator.stop()
        api_socket.close()


def serve(loaded: LoadedConfig, on_started: Callable[[Simulator], None]) -> None:
    """Blocking entry point for `emupos run`; returns after a clean shutdown.

    Raises StartupError when the control API port or a device endpoint is unavailable.
    """
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(loaded, on_started))
