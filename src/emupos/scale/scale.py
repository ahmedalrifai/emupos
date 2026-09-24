"""Scale weight state: gross, tare, stability, settling and the unit it reports (weight-scale spec).

Pure (design D2): the clock is passed in as `now`, monotonic seconds. Every operation first
settles an unstable reading whose settle time has passed, so the settle event is published
even when the daemon's timer for `next_deadline()` fires late.

A protocol may act on the scale, not only read it: SMA zeroes, tares and switches units on
command. It does so through `ScaleOps`, so the scale stays the only thing that changes scale
state and publishes `scale.weight.changed` (design D1).
"""

from dataclasses import dataclass
from typing import Protocol

from emupos.config import ScaleProfile, ScaleUnit, SmaProfile, Toledo8217Profile
from emupos.events import NO_OUTPUT, ConnectionId, Event, EventType, Output, Write
from emupos.scale.sma.sma import Sma
from emupos.scale.toledo8217.toledo8217 import Toledo8217


@dataclass(frozen=True, slots=True)
class ScaleState:
    """A snapshot of the scale, in whole grams ("Scale weight state")."""

    grams: int  # gross
    tare_grams: int  # 0 when no tare is set
    net_grams: int  # gross minus tare
    stable: bool
    capacity_grams: int


class ScaleInMotionError(Exception):
    """Zero or tare was refused because the reading has not settled ("Zero and tare")."""

    def __init__(self, operation: str) -> None:
        self.message = f"cannot {operation} while the reading is in motion"
        self.fix = "wait for the reading to settle, then try again"
        super().__init__(f"{self.message}; {self.fix}")


class ScaleReading(Protocol):
    """What the scale shows, for a protocol that only reports it."""

    def now(self) -> float: ...
    def state(self) -> ScaleState: ...
    def unit(self) -> ScaleUnit | None: ...


class ScaleOps(ScaleReading, Protocol):
    """What a protocol may also ask of the scale it speaks for.

    `zero` and `tare` return whether the scale accepted the operation: a protocol reports a
    refusal on the wire, where the control API raises `ScaleInMotionError` instead.
    """

    def zero(self) -> bool: ...
    def tare(self, grams: int | None = None) -> bool: ...
    def clear_tare(self) -> None: ...
    def select_unit(self, name: str) -> bool: ...
    def next_unit(self) -> None: ...


class ScaleProtocol(Protocol):
    """One connection's protocol state.

    Every protocol answers received bytes; some also speak on their own, which `next_deadline`
    and `due` drive.
    """

    def receive(self, data: bytes, ops: ScaleOps) -> tuple[bytes, list[tuple[bytes, bytes]]]: ...
    def next_deadline(self) -> float | None: ...
    def due(self, now: float, ops: ScaleOps) -> bytes: ...


def make_protocol(profile: ScaleProfile) -> ScaleProtocol:
    """The protocol object for one connection, chosen by the profile."""
    match profile:
        case Toledo8217Profile():
            return Toledo8217(profile)
        case SmaProfile():
            return Sma(profile)
        case _:  # a profile shape with no protocol behind it never reaches a running device
            raise ValueError(f"no protocol for scale profile `{profile.name}`")


class Scale:
    def __init__(self, device_id: str, profile: ScaleProfile) -> None:
        self.device_id = device_id
        self.profile = profile
        self._grams = 0
        self._tare_grams = 0
        self._settles_at: float | None = None  # None while the reading is stable
        self._units = list(profile.units) if isinstance(profile, SmaProfile) else []
        self._unit_index = 0
        self._connections: dict[ConnectionId, ScaleProtocol] = {}

    def state(self, now: float) -> ScaleState:
        stable = self._settles_at is None or now >= self._settles_at
        return ScaleState(
            grams=self._grams,
            tare_grams=self._tare_grams,
            net_grams=self._grams - self._tare_grams,
            stable=stable,
            capacity_grams=self.profile.capacity_grams,
        )

    def unit(self) -> ScaleUnit | None:
        """The unit the scale reports in, or None for a protocol without units."""
        return self._units[self._unit_index] if self._units else None

    def set_weight(self, grams: int, stable: bool, now: float) -> Output:
        """Set the gross weight; negative and over-capacity weights are accepted on purpose."""
        output = self.tick(now)
        self._grams = grams
        settle_seconds = self.profile.settle_ms / 1000
        self._settles_at = None if stable or settle_seconds == 0 else now + settle_seconds
        return output + self._weight_changed(now)

    def zero(self, now: float) -> Output:
        """Set the gross weight to 0 g and clear the tare, or refuse while in motion."""
        accepted, output = self.try_zero(now)
        if not accepted:
            raise ScaleInMotionError("zero")
        return output

    def tare(self, now: float, grams: int | None = None) -> Output:
        """Tare the current gross weight, or the given weight, or refuse while in motion."""
        accepted, output = self.try_tare(now, grams)
        if not accepted:
            raise ScaleInMotionError("tare")
        return output

    def try_zero(self, now: float) -> tuple[bool, Output]:
        """Zero the scale when the reading has settled. False means it was refused, unchanged."""
        output = self.tick(now)
        if not self.state(now).stable:
            return False, output
        self._grams = 0
        self._tare_grams = 0
        return True, output + self._weight_changed(now)

    def try_tare(self, now: float, grams: int | None = None) -> tuple[bool, Output]:
        """Tare when the reading has settled. False means it was refused, unchanged.

        Without a weight, tare the current gross weight, which clears the tare when the gross is
        0 g or below.
        """
        output = self.tick(now)
        if not self.state(now).stable:
            return False, output
        self._tare_grams = max(self._grams if grams is None else grams, 0)
        return True, output + self._weight_changed(now)

    def clear_tare(self, now: float) -> Output:
        """Clear the tare. A scale accepts this whatever the reading is doing."""
        output = self.tick(now)
        self._tare_grams = 0
        return output + self._weight_changed(now)

    def select_unit(self, name: str) -> bool:
        """Report in the named unit when the profile lists it; otherwise leave the unit alone."""
        for index, entry in enumerate(self._units):
            if entry.unit == name:
                self._unit_index = index
                return True
        return False

    def next_unit(self) -> None:
        """Move to the next unit the profile lists, wrapping, as a unit key does."""
        if self._units:
            self._unit_index = (self._unit_index + 1) % len(self._units)

    def tick(self, now: float) -> Output:
        """Settle an unstable reading once its settle time has elapsed."""
        if self._settles_at is None or now < self._settles_at:
            return NO_OUTPUT
        self._settles_at = None
        return self._weight_changed(now)

    def due_writes(self, now: float) -> Output:
        """What the protocols have to say on their own, such as a continuous weight."""
        writes: list[Write] = []
        events: list[Event] = []
        for connection, protocol in self._connections.items():
            if data := protocol.due(now, _Ops(self, now, events)):
                writes.append(Write(connection, data))
        return Output(tuple(writes), tuple(events))

    def next_deadline(self) -> float | None:
        """When `tick` or `due_writes` next has something to do, or None."""
        deadlines = [self._settles_at] + [p.next_deadline() for p in self._connections.values()]
        return min((at for at in deadlines if at is not None), default=None)

    def open_connection(self, connection: ConnectionId, now: float) -> Output:
        self._connections[connection] = make_protocol(self.profile)
        return self.tick(now)

    def receive(self, connection: ConnectionId, data: bytes, now: float) -> Output:
        output = self.tick(now)
        protocol = self._connections.get(connection)
        if protocol is None:  # bytes before open_connection: answer them anyway
            protocol = self._connections[connection] = make_protocol(self.profile)
        events: list[Event] = []
        written, answers = protocol.receive(data, _Ops(self, now, events))
        writes = (Write(connection, written),) if written else ()
        events += [
            Event(
                EventType.SCALE_REQUEST_ANSWERED,
                self.device_id,
                {"request": request.hex(" "), "reply": reply.hex(" ")},
            )
            for request, reply in answers
        ]
        return output + Output(writes, tuple(events))

    def close_connection(self, connection: ConnectionId, now: float) -> Output:
        self._connections.pop(connection, None)
        return self.tick(now)

    def _weight_changed(self, now: float) -> Output:
        state = self.state(now)
        data = {
            "grams": state.grams,
            "tare_grams": state.tare_grams,
            "net_grams": state.net_grams,
            "stable": state.stable,
        }
        return Output(events=(Event(EventType.SCALE_WEIGHT_CHANGED, self.device_id, data),))


class _Ops:
    """`ScaleOps` for one call, collecting the events the operations publish."""

    def __init__(self, scale: Scale, now: float, events: list[Event]) -> None:
        self._scale = scale
        self._now = now
        self._events = events

    def now(self) -> float:
        return self._now

    def state(self) -> ScaleState:
        return self._scale.state(self._now)

    def unit(self) -> ScaleUnit | None:
        return self._scale.unit()

    def zero(self) -> bool:
        accepted, output = self._scale.try_zero(self._now)
        self._events += output.events
        return accepted

    def tare(self, grams: int | None = None) -> bool:
        accepted, output = self._scale.try_tare(self._now, grams)
        self._events += output.events
        return accepted

    def clear_tare(self) -> None:
        self._events += self._scale.clear_tare(self._now).events

    def select_unit(self, name: str) -> bool:
        return self._scale.select_unit(name)

    def next_unit(self) -> None:
        self._scale.next_unit()
