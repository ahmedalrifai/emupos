"""Scale weight state: gross, tare, stability and settling (weight-scale spec).

Pure (design D2): the clock is passed in as `now`, monotonic seconds. Every operation first
settles an unstable reading whose settle time has passed, so the settle event is published
even when the daemon's timer for `next_deadline()` fires late.
"""

from dataclasses import dataclass

from emupos.config import ScaleProfile
from emupos.events import NO_OUTPUT, ConnectionId, Event, EventType, Output, Write
from emupos.scale.toledo8217.toledo8217 import Toledo8217

# Protocol implementations by the profile's `protocol` value.
PROTOCOLS = {"toledo8217": Toledo8217}


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


class Scale:
    def __init__(self, device_id: str, profile: ScaleProfile) -> None:
        self.device_id = device_id
        self.profile = profile
        self._grams = 0
        self._tare_grams = 0
        self._settles_at: float | None = None  # None while the reading is stable
        self._protocol = PROTOCOLS[profile.protocol]
        self._connections: dict[ConnectionId, Toledo8217] = {}

    def state(self, now: float) -> ScaleState:
        stable = self._settles_at is None or now >= self._settles_at
        return ScaleState(
            grams=self._grams,
            tare_grams=self._tare_grams,
            net_grams=self._grams - self._tare_grams,
            stable=stable,
            capacity_grams=self.profile.capacity_grams,
        )

    def set_weight(self, grams: int, stable: bool, now: float) -> Output:
        """Set the gross weight; negative and over-capacity weights are accepted on purpose."""
        output = self.tick(now)
        self._grams = grams
        settle_seconds = self.profile.settle_ms / 1000
        self._settles_at = None if stable or settle_seconds == 0 else now + settle_seconds
        return output + self._weight_changed(now)

    def zero(self, now: float) -> Output:
        """Set the gross weight to 0 g and clear the tare."""
        output = self._refuse_in_motion("zero", now)
        self._grams = 0
        self._tare_grams = 0
        return output + self._weight_changed(now)

    def tare(self, now: float) -> Output:
        """Tare the current gross weight, or clear the tare when the gross is 0 g or below."""
        output = self._refuse_in_motion("tare", now)
        self._tare_grams = max(self._grams, 0)
        return output + self._weight_changed(now)

    def tick(self, now: float) -> Output:
        """Settle an unstable reading once its settle time has elapsed."""
        if self._settles_at is None or now < self._settles_at:
            return NO_OUTPUT
        self._settles_at = None
        return self._weight_changed(now)

    def next_deadline(self) -> float | None:
        """When `tick` next has something to do, or None."""
        return self._settles_at

    def open_connection(self, connection: ConnectionId, now: float) -> Output:
        self._connections[connection] = self._protocol(self.profile)
        return self.tick(now)

    def receive(self, connection: ConnectionId, data: bytes, now: float) -> Output:
        output = self.tick(now)
        protocol = self._connections.get(connection)
        if protocol is None:  # bytes before open_connection: answer them anyway
            protocol = self._connections[connection] = self._protocol(self.profile)
        written, answers = protocol.receive(data, self.state(now))
        writes = (Write(connection, written),) if written else ()
        events = tuple(
            Event(
                EventType.SCALE_REQUEST_ANSWERED,
                self.device_id,
                {"request": request.hex(" "), "reply": reply.hex(" ")},
            )
            for request, reply in answers
        )
        return output + Output(writes, events)

    def close_connection(self, connection: ConnectionId, now: float) -> Output:
        self._connections.pop(connection, None)
        return self.tick(now)

    def _refuse_in_motion(self, operation: str, now: float) -> Output:
        output = self.tick(now)
        if not self.state(now).stable:
            raise ScaleInMotionError(operation)
        return output

    def _weight_changed(self, now: float) -> Output:
        state = self.state(now)
        data = {
            "grams": state.grams,
            "tare_grams": state.tare_grams,
            "net_grams": state.net_grams,
            "stable": state.stable,
        }
        return Output(events=(Event(EventType.SCALE_WEIGHT_CHANGED, self.device_id, data),))
