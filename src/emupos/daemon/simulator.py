"""The running simulator: devices, their connections, and what their output does.

configuration → devices → connections → device output → replies, receipts, events, timers.

Device code is pure and single-threaded: every call into a device happens on the event loop,
so no locks are needed. The loop's monotonic clock is the `now` passed to devices.
"""

import asyncio
import logging
import sys
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from emupos.config import LoadedConfig
from emupos.daemon.connections import Connections
from emupos.daemon.runtime import DeviceRuntime, StartupError, build_runtime
from emupos.daemon.scans import deliver_scan
from emupos.events import Event, EventBus, EventType, Output, PublishedEvent
from emupos.printer.printer import Printer, PrinterFault, PrinterOutput
from emupos.printer.receipts import ReceiptStore
from emupos.scale.scale import Scale
from emupos.scanner.scanner import AcceptedScan, Scanner
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.keyboard.keyboard import Keyboard, system_keyboard
from emupos.transports.udp import serve_udp
from emupos.windows_queue import snmp

logger = logging.getLogger("emupos")


class Simulator:
    def __init__(
        self,
        loaded: LoadedConfig,
        *,
        link_dir: Path | None = None,
        snmp_port: int | None = snmp.PORT if sys.platform == "win32" else None,
    ) -> None:
        self.loaded = loaded
        self.bus = EventBus()
        self.startup_events: tuple[PublishedEvent, ...] = ()
        self._runtimes = {
            config.id: build_runtime(config, loaded) for config in loaded.config.devices
        }
        self._connections = Connections(
            loaded, apply=self.apply, publish=self.bus.publish, now=self.now, link_dir=link_dir
        )
        self._tasks: set[asyncio.Task[None]] = set()
        self._keyboard: Keyboard | None = None
        self._snmp_port = snmp_port
        self._snmp: asyncio.DatagramTransport | None = None
        # A queue's SNMP index is its printer's TCP port (see `emupos setup print-queue`).
        self._snmp_printers = {
            connection.tcp.port: runtime.device
            for runtime in self._runtimes.values()
            if isinstance(runtime.device, Printer)
            for connection in runtime.config.connections
            if connection.tcp is not None
        }

    # --- lifecycle ------------------------------------------------------------------------

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
                        await self._connections.open(runtime, connection)
                except EndpointUnavailableError as error:
                    await self.stop()
                    raise StartupError(f"device `{runtime.config.id}`: {error}") from None
        finally:
            stop_recording()
        self.startup_events = tuple(recorded)
        await self._start_snmp()

    async def stop(self) -> None:
        """Close every connection and link, and stop scans and timers. Safe to call twice."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._connections.close()
        if self._snmp is not None:
            self._snmp.close()
            self._snmp = None
            await asyncio.sleep(0)  # the transport closes its socket on the next iteration
        for runtime in self._runtimes.values():
            if runtime.timer is not None:
                runtime.timer.cancel()

    # --- queries for the control API ------------------------------------------------------

    def device_ids(self) -> list[str]:
        return list(self._runtimes)

    def runtime(self, device_id: str) -> DeviceRuntime:
        return self._runtimes[device_id]  # KeyError: unknown device, mapped to 404 by the API

    def receipt_store(self, printer: Printer) -> ReceiptStore:
        store = self._runtimes[printer.device_id].receipts
        if store is None:
            raise TypeError(f"`{printer.device_id}` has no receipt store")
        return store

    def now(self) -> float:
        return asyncio.get_running_loop().time()

    # --- the physical-world actions (control API and CLI) ---------------------------------

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
        runtime = self._runtimes[scanner.device_id]
        self._spawn(
            deliver_scan(runtime, scanner, accepted, keyboard, now=self.now, apply=self.apply)
        )
        return accepted

    # --- device output --------------------------------------------------------------------

    def apply(self, device_id: str, output: Output) -> None:
        """Perform what a device operation produced: replies, events, receipts, next timer."""
        runtime = self._runtimes[device_id]
        for write in output.writes:
            writer = runtime.writers.get(write.connection)
            if writer is not None and not writer.is_closing():
                # ponytail: replies are a few bytes; no backpressure unless a client never reads.
                writer.write(write.data)
        for event in output.events:
            self.bus.publish(event)
        if isinstance(output, PrinterOutput) and runtime.receipts is not None:
            for receipt in output.receipts:
                meta = runtime.receipts.save(device_id, receipt, datetime.now(UTC))
                data = {"receipt_id": meta.id, "boundary": receipt.boundary}
                self.bus.publish(Event(EventType.PRINTER_JOB_COMPLETED, device_id, data))
        self._schedule_tick(runtime)

    # --- Windows print queue status (windows-print-queue spec) ---------------------------

    async def _start_snmp(self) -> None:
        if self._snmp_port is None or not self._snmp_printers:
            return
        try:
            self._snmp = await serve_udp("127.0.0.1", self._snmp_port, self._answer_snmp)
        except OSError:
            # The devices keep running: only the queues' status display is lost.
            logger.error("%s; to fix it, %s", snmp.PORT_IN_USE, snmp.STOP_SNMP_SERVICE)

    def _answer_snmp(self, packet: bytes) -> bytes | None:
        statuses = {
            index: snmp.printer_status(printer.state().faults)
            for index, printer in self._snmp_printers.items()
        }
        if (answer := snmp.answer(packet, statuses)) is None:
            return None
        data = {"type": answer.type, "oids": list(answer.oids)}
        for device_id in sorted({self._snmp_printers[index].device_id for index in answer.indexes}):
            self.bus.publish(Event(EventType.SNMP_QUERY_ANSWERED, device_id, data))
        return answer.reply

    def _schedule_tick(self, runtime: DeviceRuntime) -> None:
        """Call the device's `tick` at its next deadline (idle-timeout receipts, scale settling)."""
        device = runtime.device
        if runtime.timer is not None:
            runtime.timer.cancel()
            runtime.timer = None
        if isinstance(device, Scanner) or (deadline := device.next_deadline()) is None:
            return
        runtime.timer = asyncio.get_running_loop().call_at(
            deadline, lambda: self.apply(device.device_id, device.tick(self.now()))
        )

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
