"""Opening a device's connections and pumping bytes between them and the device.

Every accepted client or opened serial port becomes one connection: bytes read from it go to the
device, and the device's output goes back through `apply` (see simulator.py).
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from emupos.config import Connection, LoadedConfig, ScannerDevice, SerialFraming
from emupos.daemon.runtime import DeviceRuntime, Endpoint
from emupos.events import ConnectionId, Event, EventType, Output
from emupos.scanner.scanner import Scanner
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.framing import Mismatch, watch_framing
from emupos.transports.pty import PtyPort, open_pty
from emupos.transports.serial_port import SerialPort, open_serial_port
from emupos.transports.tcp import TcpListener, serve_tcp

logger = logging.getLogger("emupos")

# A serial-mode scanner has no profile; it expects the framing most scanners ship with.
SCANNER_FRAMING = SerialFraming(baud=9600, data_bits=8, parity="none", stop_bits=1)
READ_SIZE = 65536


class Connections:
    def __init__(
        self,
        loaded: LoadedConfig,
        *,
        apply: Callable[[str, Output], None],
        publish: Callable[[Event], object],
        now: Callable[[], float],
        link_dir: Path | None,
    ) -> None:
        self._loaded = loaded
        self._apply = apply
        self._publish = publish
        self._now = now
        self._link_dir = link_dir
        self._listeners: list[TcpListener] = []
        self._ports: list[PtyPort | SerialPort] = []
        self._tasks: set[asyncio.Task[None]] = set()

    async def open(self, runtime: DeviceRuntime, connection: Connection) -> None:
        """Open one connection entry. Raises EndpointUnavailableError."""
        if connection.tcp is not None:
            await self._open_tcp(runtime, connection.tcp.host, connection.tcp.port)
        elif connection.serial is not None and connection.serial.pty:
            await self._open_pty(runtime, connection.serial.link or runtime.config.id)
        elif connection.serial is not None and connection.serial.port is not None:
            await self._open_serial_port(runtime, connection.serial.port)

    async def close(self) -> None:
        """Close every connection, listener and link. Safe to call more than once."""
        for task in list(self._tasks):
            task.cancel()  # framing watchers first: they must stop before their pty closes
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for listener in self._listeners:
            await listener.close()
        for port in self._ports:
            await port.close()
        self._listeners.clear()
        self._ports.clear()

    # --- each kind of connection ------------------------------------------------------------

    async def _open_tcp(self, runtime: DeviceRuntime, host: str, port: int) -> None:
        async def on_client(
            conn: ConnectionId, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            client = writer.get_extra_info("peername")
            endpoint = {
                "kind": "tcp",
                "endpoint": f"{host}:{port}",
                "client": f"{client[0]}:{client[1]}",
            }
            await self._pump(runtime, conn, reader, writer, endpoint)

        self._listeners.append(await serve_tcp(host, port, on_client))
        runtime.endpoints.append(Endpoint("tcp", f"{host}:{port}"))

    async def _open_pty(self, runtime: DeviceRuntime, link: str) -> None:
        framing = self._framing(runtime)
        port = await open_pty(link, framing, self._link_dir)
        self._ports.append(port)
        link_path = str(port.link_path)
        runtime.endpoints.append(Endpoint("serial", link_path, link_path, port.device_path))
        endpoint = {"kind": "serial", "endpoint": link_path}
        self._spawn(self._pump(runtime, port.connection_id, port.reader, port.writer, endpoint))
        report = self._framing_reporter(runtime.config.id, link_path)
        self._spawn(watch_framing(port.slave_fd, framing, report))

    async def _open_serial_port(self, runtime: DeviceRuntime, path: str) -> None:
        # Existing device paths on macOS/Linux; Windows COM ports wait for the serial spike (task 4.4).
        port = await open_serial_port(path, self._framing(runtime))
        self._ports.append(port)
        runtime.endpoints.append(Endpoint("serial", port.path))
        endpoint = {"kind": "serial", "endpoint": port.path}
        self._spawn(self._pump(runtime, port.connection_id, port.reader, port.writer, endpoint))

    # --- the byte pump ----------------------------------------------------------------------

    async def _pump(
        self,
        runtime: DeviceRuntime,
        conn: ConnectionId,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        endpoint: dict[str, str],
    ) -> None:
        device, device_id = runtime.device, runtime.config.id
        runtime.writers[conn] = writer
        self._publish(Event(EventType.CONNECTION_OPENED, device_id, endpoint))
        try:
            if not isinstance(device, Scanner):
                self._apply(device_id, device.open_connection(conn, self._now()))
            while data := await reader.read(READ_SIZE):
                if not isinstance(device, Scanner):  # a scanner ignores bytes sent to it
                    self._apply(device_id, device.receive(conn, data, self._now()))
        finally:
            runtime.writers.pop(conn, None)
            if not isinstance(device, Scanner):
                self._apply(device_id, device.close_connection(conn, self._now()))
            self._publish(Event(EventType.CONNECTION_CLOSED, device_id, endpoint))

    # --- serial framing ---------------------------------------------------------------------

    def _framing(self, runtime: DeviceRuntime) -> SerialFraming:
        config = runtime.config
        if isinstance(config, ScannerDevice):
            return SCANNER_FRAMING
        profile = self._loaded.profiles[config.id]
        if profile.serial is None:  # configuration validation rejects this; kept for typing
            raise EndpointUnavailableError(f"profile `{config.profile}` defines no serial framing")
        return profile.serial

    def _framing_reporter(
        self, device_id: str, link: str
    ) -> Callable[[tuple[Mismatch, ...]], None]:
        def report(mismatches: tuple[Mismatch, ...]) -> None:
            settings = [
                {"setting": m.setting, "expected": m.expected, "observed": m.observed}
                for m in mismatches
            ]
            data = {"endpoint": link, "mismatches": settings}
            self._publish(Event(EventType.CONNECTION_FRAMING_MISMATCH, device_id, data))
            described = ", ".join(
                f"{m.setting} expected {m.expected} observed {m.observed}" for m in mismatches
            )
            logger.warning("%s: serial framing mismatch on %s: %s", device_id, link, described)

        return report

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
