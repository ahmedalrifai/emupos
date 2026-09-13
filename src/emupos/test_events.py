from datetime import UTC, datetime

from emupos.events import Event, EventBus, EventType, Output, PublishedEvent, Write

FIXED_TIME = datetime(2026, 9, 13, 12, 4, 51, 123456, tzinfo=UTC)


def test_subscribers_receive_events_in_publish_order() -> None:
    bus = EventBus(clock=lambda: FIXED_TIME)
    first: list[str] = []
    second: list[str] = []
    bus.subscribe(lambda e: first.append(e.event.device_id))
    bus.subscribe(lambda e: second.append(e.event.device_id))

    bus.publish(Event(EventType.DRAWER_OPENED, "front"))
    bus.publish(Event(EventType.DRAWER_CLOSED, "back"))

    assert first == ["front", "back"]
    assert second == ["front", "back"]


def test_unsubscribed_subscriber_receives_nothing() -> None:
    bus = EventBus()
    received: list[PublishedEvent] = []
    unsubscribe = bus.subscribe(received.append)

    unsubscribe()
    bus.publish(Event(EventType.DRAWER_OPENED, "front"))

    assert received == []


def test_failing_subscriber_does_not_block_others() -> None:
    bus = EventBus()
    received: list[PublishedEvent] = []

    def broken(_: PublishedEvent) -> None:
        raise RuntimeError("socket gone")

    bus.subscribe(broken)
    bus.subscribe(received.append)
    bus.publish(Event(EventType.DRAWER_OPENED, "front"))

    assert len(received) == 1


def test_json_form_uses_rfc3339_utc_with_milliseconds() -> None:
    published = PublishedEvent(
        Event(EventType.SCALE_WEIGHT_CHANGED, "deli", {"grams": 1250}), FIXED_TIME
    )

    assert published.to_json() == {
        "type": "scale.weight.changed",
        "device_id": "deli",
        "at": "2026-09-13T12:04:51.123Z",
        "data": {"grams": 1250},
    }


def test_outputs_combine_in_order() -> None:
    a = Output((Write("tcp:a", bytes.fromhex("12")),), (Event(EventType.DRAWER_OPENED, "front"),))
    b = Output((Write("tcp:b", bytes.fromhex("16")),))

    combined = a + b

    assert [w.connection for w in combined.writes] == ["tcp:a", "tcp:b"]
    assert len(combined.events) == 1
