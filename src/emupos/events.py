"""Events, device output, and the in-process event bus.

Device and protocol code is pure (design D2): an operation such as "bytes arrived on a
connection" returns an `Output` describing the bytes to write back and the events to
publish. The daemon performs the writes and publishes the events. Pure code never reads
the clock, so events are created without a timestamp; the bus stamps them on publish.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    CONNECTION_OPENED = "connection.opened"
    CONNECTION_CLOSED = "connection.closed"
    CONNECTION_FRAMING_MISMATCH = "connection.framing-mismatch"
    PRINTER_JOB_COMPLETED = "printer.job.completed"
    PRINTER_COMMAND_UNKNOWN = "printer.command.unknown"
    PRINTER_CODEPAGE_UNSUPPORTED = "printer.codepage.unsupported"
    PRINTER_STATUS_CHANGED = "printer.status.changed"
    DRAWER_OPENED = "drawer.opened"
    DRAWER_CLOSED = "drawer.closed"
    SCALE_WEIGHT_CHANGED = "scale.weight.changed"
    SCALE_REQUEST_ANSWERED = "scale.request.answered"
    SCANNER_SCAN_DELIVERED = "scanner.scan.delivered"
    SNMP_QUERY_ANSWERED = "snmp.query.answered"


# Event data must be JSON-serialisable: str, int, float, bool, None, lists and mappings of those.
type EventData = Mapping[str, object]

# Identifies one open connection to a device, e.g. "tcp:127.0.0.1:9100<-127.0.0.1:53422" or "serial:/tmp/emupos/deli".
type ConnectionId = str


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    device_id: str
    data: EventData = field(default_factory=dict[str, object])


@dataclass(frozen=True, slots=True)
class PublishedEvent:
    event: Event
    at: datetime

    def to_json(self) -> dict[str, object]:
        """The event as sent on the control API event stream."""
        return {
            "type": str(self.event.type),
            "device_id": self.event.device_id,
            "at": self.at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "data": dict(self.event.data),
        }


@dataclass(frozen=True, slots=True)
class Write:
    connection: ConnectionId
    data: bytes


@dataclass(frozen=True, slots=True)
class Output:
    """What a pure device operation produced."""

    writes: tuple[Write, ...] = ()
    events: tuple[Event, ...] = ()

    def __add__(self, other: Self) -> Self:
        return type(self)(self.writes + other.writes, self.events + other.events)


NO_OUTPUT = Output()

type Subscriber = Callable[[PublishedEvent], None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EventBus:
    """Delivers every published event to every subscriber, in publish order."""

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        """Register a subscriber and return a function that unsubscribes it."""
        self._subscribers.append(subscriber)
        return lambda: self._subscribers.remove(subscriber)

    def publish(self, event: Event) -> PublishedEvent:
        published = PublishedEvent(event, self._clock())
        for subscriber in list(self._subscribers):
            try:
                subscriber(published)
            except Exception:
                # One broken subscriber (e.g. a dropped WebSocket) must not stop delivery to others.
                logger.exception("event subscriber failed for %s", event.type)
        return published
