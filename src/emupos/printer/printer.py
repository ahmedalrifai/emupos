"""A simulated receipt printer: connections, faults, jobs, status replies and its cash drawer.

Pure device logic (design D2): every operation returns a `PrinterOutput` with the bytes to
write, the events to publish and the receipts completed. The daemon stores each receipt and
publishes `printer.job.completed` with the stored id.

What is shared and what belongs to one connection (receipt-printer spec, "Multiple
simultaneous connections"):
- shared: faults, paper, cover, online state and the cash drawer;
- per connection: pending undecoded bytes, print settings, the current job and ASB.

While a blocking fault (paper-out, cover-open, offline) is active, print data and
non-real-time commands are held in order and no job completes. Real-time commands are always
answered at once. Clearing the last blocking fault processes the held data.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Self

from emupos.config import Level, PrinterProfile
from emupos.drawer.drawer import Drawer, Pulse, dle_dc4_pulse, esc_p_pulse
from emupos.events import ConnectionId, Event, EventType, Output, Write
from emupos.printer.escpos import status
from emupos.printer.escpos.model import PrintModel, unknown_command_event
from emupos.printer.escpos.render import Boundary, RenderedReceipt
from emupos.printer.escpos.tokenizer import Command, Token, Tokenizer


class PrinterFault(StrEnum):
    PAPER_NEAR_END = "paper-near-end"
    PAPER_OUT = "paper-out"
    COVER_OPEN = "cover-open"
    OFFLINE = "offline"


BLOCKING_FAULTS = frozenset({PrinterFault.PAPER_OUT, PrinterFault.COVER_OPEN, PrinterFault.OFFLINE})


# GS ( L fn 48 / fn 51 (m fn) -> header 37h, identifier, capacity as decimal text, NUL. A capacity
# of "0" tells the POS that NV graphics cannot be used, which is true of the simulator.
NV_GRAPHICS_CAPACITY_REPLIES = {
    b"\x30\x00": b"\x37\x300\x00",  # fn 0: entire capacity
    b"\x30\x30": b"\x37\x300\x00",  # fn 48
    b"\x30\x03": b"\x37\x310\x00",  # fn 3: remaining capacity
    b"\x30\x33": b"\x37\x310\x00",  # fn 51
}


@dataclass(frozen=True, slots=True)
class PrinterState:
    faults: tuple[str, ...]  # active faults, sorted by name
    drawer: Literal["open", "closed"]


@dataclass(frozen=True, slots=True)
class PrinterOutput(Output):
    receipts: tuple[RenderedReceipt, ...] = ()

    def __add__(self, other: Output) -> Self:
        receipts = other.receipts if isinstance(other, PrinterOutput) else ()
        return type(self)(
            self.writes + other.writes, self.events + other.events, self.receipts + receipts
        )


class _Collector:
    def __init__(self) -> None:
        self.writes: list[Write] = []
        self.events: list[Event] = []
        self.receipts: list[RenderedReceipt] = []

    def output(self) -> PrinterOutput:
        return PrinterOutput(tuple(self.writes), tuple(self.events), tuple(self.receipts))


class _Connection:
    def __init__(self, connection_id: ConnectionId, model: PrintModel, now: float) -> None:
        self.id = connection_id
        self.tokenizer = Tokenizer()
        self.model = model
        self.held: list[Token] = []  # print data waiting for the blocking faults to clear
        self.asb = 0  # GS a n; 0 means Automatic Status Back is disabled
        self.last_byte_at = now
        self.closed = False


class Printer:
    def __init__(
        self,
        device_id: str,
        profile: PrinterProfile,
        *,
        sensor_open_level: Level,
        job_idle_timeout_ms: int,
    ) -> None:
        self.device_id = device_id
        self._profile = profile
        self._idle_timeout = job_idle_timeout_ms / 1000
        self._faults: set[PrinterFault] = set()
        self._drawer = Drawer(device_id, sensor_open_level)
        self._connections: dict[ConnectionId, _Connection] = {}
        self._closed_while_blocked: list[_Connection] = []

    # --- operations ------------------------------------------------------------------------

    def open_connection(self, connection: ConnectionId, now: float) -> PrinterOutput:
        """A POS connected. It starts with the settings in effect after ESC @."""
        out = _Collector()
        if connection in self._connections:
            self._close(self._connections[connection], out)
        model = PrintModel(self.device_id, self._profile)
        self._connections[connection] = _Connection(connection, model, now)
        return out.output()

    def receive(self, connection: ConnectionId, data: bytes, now: float) -> PrinterOutput:
        out = _Collector()
        current = self._connections[connection]
        current.last_byte_at = now
        for token in current.tokenizer.feed(data):
            if isinstance(token, Command) and token.realtime:
                self._realtime(current, token, out)
            else:
                self._submit(current, token, out)
        return out.output()

    def close_connection(self, connection: ConnectionId, now: float) -> PrinterOutput:
        out = _Collector()
        self._close(self._connections[connection], out)
        return out.output()

    def tick(self, now: float) -> PrinterOutput:
        """End jobs whose connection has been idle for `job_idle_timeout_ms`."""
        out = _Collector()
        if not self._blocked:
            for current in self._connections.values():
                if current.model.receipt.has_content and now >= self._deadline(current):
                    self._complete_job(current, "idle-timeout", out)
        return out.output()

    def next_deadline(self) -> float | None:
        """When `tick` must next be called, or None when no job can time out."""
        if self._blocked:
            return None
        waiting = [c for c in self._connections.values() if c.model.receipt.has_content]
        return min((self._deadline(current) for current in waiting), default=None)

    def set_fault(self, fault: PrinterFault, active: bool, now: float) -> PrinterOutput:
        out = _Collector()
        if (fault in self._faults) == active:
            return out.output()
        before, was_blocked = self._status(), self._blocked
        if active:
            self._faults.add(fault)
        else:
            self._faults.discard(fault)
        data = {"faults": list(self.state().faults)}
        out.events.append(Event(EventType.PRINTER_STATUS_CHANGED, self.device_id, data))
        self._push_asb(before, out)
        if was_blocked and not self._blocked:
            self._release_held_data(out)
        return out.output()

    def close_drawer(self, now: float) -> PrinterOutput:
        out = _Collector()
        before = self._status()
        if (event := self._drawer.close()) is not None:
            out.events.append(event)
            self._push_asb(before, out)
        return out.output()

    def state(self) -> PrinterState:
        return PrinterState(
            faults=tuple(sorted(self._faults)),
            drawer="open" if self._drawer.is_open else "closed",
        )

    # --- command handling ------------------------------------------------------------------

    def _realtime(self, connection: _Connection, command: Command, out: _Collector) -> None:
        """DLE EOT, DLE ENQ and DLE DC4: answered at once, even while printing is blocked."""
        match command.name, command.params[0]:
            case "DLE EOT", n if (reply := status.dle_eot(n, self._status())) is not None:
                self._write(connection, reply, out)
            case "DLE DC4", 1 if (
                pulse := dle_dc4_pulse(command.data[0], command.data[1])
            ) is not None:
                self._kick(pulse, out)
            case _:
                out.events.append(
                    unknown_command_event(self.device_id, command.raw, command=command.name)
                )

    def _submit(self, connection: _Connection, token: Token, out: _Collector) -> None:
        if self._blocked:
            connection.held.append(token)
        else:
            self._print(connection, token, out)

    def _print(self, connection: _Connection, token: Token, out: _Collector) -> None:
        """Process print data and non-real-time commands, in the order received."""
        if isinstance(token, Command):
            match token.name:
                case "GS r":  # gs_lr
                    if (reply := status.gs_r(token.params[0], self._status())) is not None:
                        self._write(connection, reply, out)
                        return
                case "GS a":  # gs_la: enabling sends the current status at once
                    connection.asb = token.params[0]
                    if connection.asb:
                        self._write(connection, status.asb(self._status()), out)
                    return
                case "ESC p":  # esc_lp
                    if (pulse := esc_p_pulse(token.params[0], token.params[1])) is not None:
                        self._kick(pulse, out)
                        return
                case "GS V":  # gs_cv: the cut ends the job
                    self._complete_job(connection, "cut", out)
                    return
                case "GS ( L" | "GS 8 L" if token.data in NV_GRAPHICS_CAPACITY_REPLIES:
                    # gs_lparen_cl_fn48, gs_lparen_cl_fn51: emupos has no NV graphics memory
                    self._write(connection, NV_GRAPHICS_CAPACITY_REPLIES[token.data], out)
                    return
                case "ESC @":  # esc_atsign: GS a is effective until ESC @ (gs_la)
                    connection.asb = 0
                case _:
                    pass
        # Everything else, and the commands above with parameters they do not accept.
        out.events += connection.model.process(token)

    # --- helpers ---------------------------------------------------------------------------

    @property
    def _blocked(self) -> bool:
        return bool(self._faults & BLOCKING_FAULTS)

    def _status(self) -> status.StatusState:
        return status.StatusState(
            paper_near_end=PrinterFault.PAPER_NEAR_END in self._faults,
            paper_out=PrinterFault.PAPER_OUT in self._faults,
            cover_open=PrinterFault.COVER_OPEN in self._faults,
            offline=PrinterFault.OFFLINE in self._faults,
            drawer_pin3_high=self._drawer.pin3_high,
        )

    def _deadline(self, connection: _Connection) -> float:
        return connection.last_byte_at + self._idle_timeout

    def _write(self, connection: _Connection, data: bytes, out: _Collector) -> None:
        if not connection.closed:  # replies to held data of a closed connection go nowhere
            out.writes.append(Write(connection.id, data))

    def _kick(self, pulse: Pulse, out: _Collector) -> None:
        before = self._status()
        if (event := self._drawer.kick(pulse)) is not None:
            out.events.append(event)
            self._push_asb(before, out)

    def _push_asb(self, before: status.StatusState, out: _Collector) -> None:
        after = self._status()
        for connection in self._connections.values():
            if connection.asb and status.asb_changed(connection.asb, before, after):
                self._write(connection, status.asb(after), out)

    def _complete_job(self, connection: _Connection, boundary: Boundary, out: _Collector) -> None:
        if (receipt := connection.model.finish(boundary)) is not None:
            out.receipts.append(receipt)

    def _close(self, connection: _Connection, out: _Collector) -> None:
        del self._connections[connection.id]
        connection.closed = True
        if (incomplete := connection.tokenizer.close()) is not None:
            out.events.append(unknown_command_event(self.device_id, incomplete.raw))
        if self._blocked:
            self._closed_while_blocked.append(connection)
        else:
            self._complete_job(connection, "connection-closed", out)

    def _release_held_data(self, out: _Collector) -> None:
        closed, self._closed_while_blocked = self._closed_while_blocked, []
        for connection in [*closed, *self._connections.values()]:
            held, connection.held = connection.held, []
            for token in held:
                self._print(connection, token, out)
        for connection in closed:
            self._complete_job(connection, "connection-closed", out)
