from importlib import resources

import pytest
import yaml

from emupos.config import ScaleProfile
from emupos.events import Event, EventType, Output, Write
from emupos.scale.scale import Scale, ScaleInMotionError, ScaleState

PROFILE = ScaleProfile.model_validate(
    yaml.safe_load(
        resources.files("emupos").joinpath("profiles/scales/toledo8217-15kg.yaml").read_text()
    )
)
WEIGHT_1250 = bytes.fromhex("02 30 31 2e 32 35 30 0d")


def weight_events(output: Output) -> list[dict[str, object]]:
    return [dict(e.data) for e in output.events if e.type is EventType.SCALE_WEIGHT_CHANGED]


def change(grams: int, tare_grams: int, stable: bool) -> dict[str, object]:
    return {
        "grams": grams,
        "tare_grams": tare_grams,
        "net_grams": grams - tare_grams,
        "stable": stable,
    }


# Scale weight state


def test_initial_state_after_start() -> None:
    assert Scale("deli", PROFILE).state(0.0) == ScaleState(
        grams=0, tare_grams=0, net_grams=0, stable=True, capacity_grams=15000
    )


# Setting the weight


def test_set_a_stable_weight() -> None:
    scale = Scale("deli", PROFILE)

    output = scale.set_weight(1250, stable=True, now=0.0)

    assert scale.state(0.0).grams == 1250
    assert scale.state(0.0).stable
    assert output == Output(
        events=(Event(EventType.SCALE_WEIGHT_CHANGED, "deli", change(1250, 0, stable=True)),)
    )


def test_weight_above_capacity_accepted() -> None:
    scale = Scale("deli", PROFILE)

    scale.set_weight(15001, stable=True, now=0.0)

    assert scale.state(0.0).grams == 15001


def test_negative_weight_accepted() -> None:
    scale = Scale("deli", PROFILE)

    scale.set_weight(-100, stable=True, now=0.0)

    assert (scale.state(0.0).grams, scale.state(0.0).net_grams) == (-100, -100)


def test_setting_the_weight_does_not_change_the_tare() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=True, now=0.0)
    scale.tare(now=0.0)

    output = scale.set_weight(900, stable=False, now=1.0)

    assert scale.state(1.0).tare_grams == 200
    assert weight_events(output) == [change(900, 200, stable=False)]


# Unstable readings settle


def test_reading_settles_after_the_settle_time() -> None:
    scale = Scale("deli", PROFILE)
    set_output = scale.set_weight(1250, stable=False, now=10.0)

    assert weight_events(set_output) == [change(1250, 0, stable=False)]
    assert not scale.state(10.1).stable
    assert scale.next_deadline() == 10.5
    assert scale.tick(10.4) == Output()
    assert weight_events(scale.tick(10.6)) == [change(1250, 0, stable=True)]
    assert scale.state(10.6).stable
    assert scale.next_deadline() is None
    assert scale.tick(10.7) == Output()


def test_settle_event_published_once_when_a_request_arrives_before_the_tick() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(1250, stable=False, now=0.0)

    output = scale.receive("pos", b"W", now=0.6)

    assert weight_events(output) == [change(1250, 0, stable=True)]
    assert output.writes == (Write("pos", WEIGHT_1250),)
    assert scale.tick(0.7) == Output()


def test_new_unstable_weight_restarts_settling() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(1000, stable=False, now=0.0)
    scale.set_weight(1250, stable=False, now=0.4)

    assert scale.tick(0.5) == Output()
    assert scale.next_deadline() == pytest.approx(0.9)
    assert not scale.state(0.8).stable


def test_stable_weight_cancels_settling() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(1000, stable=False, now=0.0)

    scale.set_weight(1250, stable=True, now=0.1)

    assert scale.next_deadline() is None
    assert scale.tick(1.0) == Output()


def test_zero_settle_time_makes_an_unstable_weight_stable_at_once() -> None:
    scale = Scale("deli", PROFILE.model_copy(update={"settle_ms": 0}))

    output = scale.set_weight(1250, stable=False, now=0.0)

    assert weight_events(output) == [change(1250, 0, stable=True)]
    assert scale.next_deadline() is None


# Zero and tare


def test_tare_a_container_then_weigh_the_item() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=True, now=0.0)

    tare_output = scale.tare(now=0.0)
    scale.set_weight(1450, stable=True, now=0.0)

    assert weight_events(tare_output) == [change(200, 200, stable=True)]
    state = scale.state(0.0)
    assert (state.grams, state.tare_grams, state.net_grams) == (1450, 200, 1250)


def test_tare_on_an_empty_scale_clears_the_tare() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=True, now=0.0)
    scale.tare(now=0.0)
    scale.set_weight(0, stable=True, now=0.0)

    scale.tare(now=0.0)

    assert scale.state(0.0).tare_grams == 0


def test_tare_below_zero_clears_the_tare() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=True, now=0.0)
    scale.tare(now=0.0)
    scale.set_weight(-50, stable=True, now=0.0)

    scale.tare(now=0.0)

    assert scale.state(0.0).tare_grams == 0


def test_zero_clears_weight_and_tare() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=True, now=0.0)
    scale.tare(now=0.0)
    scale.set_weight(350, stable=True, now=0.0)

    output = scale.zero(now=0.0)

    state = scale.state(0.0)
    assert (state.grams, state.tare_grams, state.net_grams) == (0, 0, 0)
    assert weight_events(output) == [change(0, 0, stable=True)]


def test_tare_refused_in_motion() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=False, now=0.0)

    with pytest.raises(ScaleInMotionError) as refused:
        scale.tare(now=0.1)

    assert "wait for the reading to settle" in refused.value.fix
    assert "in motion" in refused.value.message
    assert scale.state(0.1).tare_grams == 0


def test_zero_refused_in_motion() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=False, now=0.0)

    with pytest.raises(ScaleInMotionError, match="wait for the reading to settle"):
        scale.zero(now=0.1)

    assert scale.state(0.1).grams == 200


def test_tare_accepted_once_the_reading_has_settled_without_a_tick() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(200, stable=False, now=0.0)

    output = scale.tare(now=0.5)

    assert weight_events(output) == [change(200, 0, stable=True), change(200, 200, stable=True)]


# Request events


def test_weight_request_event() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(1250, stable=True, now=0.0)

    output = scale.receive("pos", bytes.fromhex("57"), now=0.0)

    assert output.writes == (Write("pos", WEIGHT_1250),)
    assert output.events == (
        Event(
            EventType.SCALE_REQUEST_ANSWERED,
            "deli",
            {"request": "57", "reply": "02 30 31 2e 32 35 30 0d"},
        ),
    )


def test_echoed_bytes_publish_no_extra_events() -> None:
    scale = Scale("deli", PROFILE)

    output = scale.receive("pos", b"Ehello", now=0.0) + scale.receive("pos", b"WF", now=0.0)

    assert [dict(e.data) for e in output.events] == [{"request": "45", "reply": "02 45 0d"}]
    assert b"".join(w.data for w in output.writes) == bytes.fromhex("02 45 0d 68 65 6c 6c 6f 57")


def test_line_terminators_publish_nothing() -> None:
    scale = Scale("deli", PROFILE)

    assert scale.receive("pos", b"\r\n", now=0.0) == Output()


# Connections


def test_echo_mode_is_per_connection() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(1250, stable=True, now=0.0)
    scale.open_connection("a", now=0.0)
    scale.open_connection("b", now=0.0)

    scale.receive("a", b"E", now=0.0)

    assert scale.receive("b", b"W", now=0.0).writes == (Write("b", WEIGHT_1250),)
    assert scale.receive("a", b"W", now=0.0).writes == (Write("a", b"W"),)


def test_reopened_connection_starts_outside_echo_mode() -> None:
    scale = Scale("deli", PROFILE)
    scale.set_weight(1250, stable=True, now=0.0)
    scale.open_connection("a", now=0.0)
    scale.receive("a", b"E", now=0.0)

    scale.close_connection("a", now=0.0)
    scale.open_connection("a", now=0.0)

    assert scale.receive("a", b"W", now=0.0).writes == (Write("a", WEIGHT_1250),)
