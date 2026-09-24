"""SMA protocol tests, against a `Scale` with the built-in `sma-15kg` profile.

That profile is 15000 g by 5 g, reporting kilograms with 3 decimals first and pounds with 2
decimals second, and repeating a continuous weight every 200 ms.
"""

from importlib import resources

import pytest
import yaml

from emupos.config import SmaProfile
from emupos.events import Event, EventType, Output
from emupos.scale.scale import Scale

PROFILE = SmaProfile.model_validate(
    yaml.safe_load(resources.files("emupos").joinpath("profiles/scales/sma-15kg.yaml").read_text())
)


class Pos:
    """One POS talking to one scale, with a clock that only moves when a test moves it."""

    def __init__(self, connection: str = "A") -> None:
        self.scale = Scale("deli", PROFILE)
        self.now = 0.0
        self.events: list[Event] = []
        self.written: dict[str, bytearray] = {}
        self.connect(connection)

    def connect(self, connection: str) -> None:
        self._collect(self.scale.open_connection(connection, self.now))

    def send(self, frame: str, connection: str = "A") -> str:
        """Send one command frame and return what the scale wrote back, as text."""
        self._collect(self.scale.receive(connection, f"\n{frame}\r".encode(), self.now))
        return self.take(connection)

    def send_bytes(self, data: bytes, connection: str = "A") -> str:
        self._collect(self.scale.receive(connection, data, self.now))
        return self.take(connection)

    def set_weight(self, grams: int, stable: bool = True) -> None:
        self._collect(self.scale.set_weight(grams, stable, self.now))

    def wait(self, seconds: float) -> None:
        """Move the clock, letting the scale settle and send any repeats that fall due."""
        target = self.now + seconds
        while (deadline := self.scale.next_deadline()) is not None and deadline <= target:
            self.now = max(deadline, self.now)
            self._collect(self.scale.tick(self.now))
            self._collect(self.scale.due_writes(self.now))
        self.now = target

    def take(self, connection: str = "A") -> str:
        return bytes(self.written.pop(connection, b"")).decode("ascii")

    def weights(self) -> list[dict[str, object]]:
        return [dict(e.data) for e in self.events if e.type is EventType.SCALE_WEIGHT_CHANGED]

    def _collect(self, output: Output) -> None:
        for write in output.writes:
            self.written.setdefault(write.connection, bytearray()).extend(write.data)
        self.events += output.events


# --- framing ----------------------------------------------------------------------------------


def test_a_command_split_across_reads_is_answered_once() -> None:
    pos, whole = Pos(), Pos()
    pos.set_weight(1000)
    whole.set_weight(1000)

    reply = ""
    for chunk in (b"\n", b"W", b"\r"):
        reply += pos.send_bytes(chunk)

    assert reply == whole.send("W")


def test_bytes_outside_a_frame_are_not_a_command() -> None:
    pos = Pos()

    assert pos.send_bytes(b"W\r") == ""
    assert pos.send_bytes(b"\n\r") == ""  # an empty frame asks nothing


def test_a_new_frame_discards_a_half_received_one() -> None:
    pos = Pos()
    pos.set_weight(1000)

    assert pos.send_bytes(b"\nW\nW\r") == "\n 1G       1.000kg_\r"


# --- weighing ---------------------------------------------------------------------------------


def test_stable_gross_weight_in_kilograms() -> None:
    pos = Pos()
    pos.set_weight(1250)

    assert pos.send("W") == "\n 1G       1.250kg_\r"


def test_net_weight_in_pounds() -> None:
    pos = Pos()
    pos.set_weight(200)
    pos.send("T")
    pos.set_weight(1450)
    pos.send("Ulb_")

    assert pos.send("W") == "\n 1N        2.76lb_\r"


def test_high_resolution_lowercases_the_gross_character() -> None:
    pos = Pos()
    pos.set_weight(1252)

    assert pos.send("H") == "\n 1g      1.2520kg_\r"
    assert pos.send("Q") == "\n 1g      1.2520kg_\r"


def test_displayed_weight_answers_like_a_weight_request() -> None:
    pos = Pos()
    pos.set_weight(1250)

    assert pos.send("P") == "\n 1G       1.250kg_\r"


@pytest.mark.parametrize(
    ("grams", "stable", "status", "motion"),
    [(0, True, "Z", " "), (15001, True, "O", " "), (1250, False, " ", "M"), (1250, True, " ", " ")],
)
def test_status_and_motion_characters(grams: int, stable: bool, status: str, motion: str) -> None:
    pos = Pos()
    pos.set_weight(grams, stable)

    reply = pos.send("W")

    assert reply[1] == status
    assert reply[4] == motion


def test_under_zero_weight() -> None:
    pos = Pos()
    pos.set_weight(-100)

    assert pos.send("W") == "\nU1G      -0.100kg_\r"


# --- zero and tare ----------------------------------------------------------------------------


def test_zero_reports_the_zeroed_weight() -> None:
    pos = Pos()
    pos.set_weight(350)
    pos.send("T")

    assert pos.send("Z") == "\nZ1G       0.000kg_\r"
    assert pos.scale.state(pos.now).grams == 0
    assert pos.scale.state(pos.now).tare_grams == 0
    assert pos.weights()[-1] == {"grams": 0, "tare_grams": 0, "net_grams": 0, "stable": True}


def test_zero_refused_in_motion_clears_when_the_reading_settles() -> None:
    pos = Pos()
    pos.set_weight(350, stable=False)

    assert pos.send("Z") == "\nE1GM ----------kg_\r"
    assert pos.scale.state(pos.now).grams == 350

    pos.wait(0.6)

    assert pos.send("Z") == "\nZ1G       0.000kg_\r"


def test_tare_refused_in_motion_is_reported_once() -> None:
    pos = Pos()
    pos.set_weight(200, stable=False)

    assert pos.send("T") == "\nT1GM ----------kg_\r"
    assert pos.scale.state(pos.now).tare_grams == 0
    assert pos.send("W")[1] != "T"


def test_preset_tare_uses_the_current_unit() -> None:
    pos = Pos()
    pos.set_weight(1450)

    assert pos.send("T0.200") == "\n 1N       1.250kg_\r"
    assert pos.scale.state(pos.now).tare_grams == 200


def test_report_and_clear_the_tare() -> None:
    pos = Pos()
    pos.set_weight(200)
    pos.send("T")
    pos.set_weight(1450)

    assert pos.send("M") == "\n 1T       0.200kg_\r"
    assert pos.scale.state(pos.now).tare_grams == 200
    assert pos.send("C") == "\n 1G       1.450kg_\r"
    assert pos.scale.state(pos.now).tare_grams == 0


def test_a_tare_through_the_protocol_publishes_the_weight_event() -> None:
    pos = Pos()
    pos.set_weight(200)

    pos.send("T")

    assert pos.weights()[-1] == {"grams": 200, "tare_grams": 200, "net_grams": 0, "stable": True}


def test_a_tare_value_that_is_not_a_number_is_unknown() -> None:
    pos = Pos()

    assert pos.send("Theavy") == "\n?\r"


# --- units ------------------------------------------------------------------------------------


def test_the_unit_cycles_and_wraps() -> None:
    pos = Pos()
    pos.set_weight(1000)

    assert pos.send("U").endswith("lb_\r")
    assert pos.send("W").endswith("lb_\r")
    assert pos.send("U").endswith("kg_\r")


def test_a_unit_the_profile_does_not_list_is_ignored() -> None:
    pos = Pos()
    pos.set_weight(1000)

    assert pos.send("Uozt").endswith("kg_\r")


def test_the_unit_is_shared_by_every_connection() -> None:
    pos = Pos()
    pos.connect("B")
    pos.set_weight(1000)

    pos.send("U", "A")

    assert pos.send("W", "B").endswith("lb_\r")
    unit = pos.scale.unit()
    assert unit is not None
    assert unit.unit == "lb_"


# --- continuous weight ------------------------------------------------------------------------


def test_repeats_continue_until_the_next_command() -> None:
    pos = Pos()
    pos.set_weight(1000)

    first = pos.send("R")
    pos.wait(0.5)
    repeats = pos.take()

    assert first == "\n 1G       1.000kg_\r"
    assert repeats.count("kg_") == 2  # 200 ms and 400 ms

    pos.send("W")
    pos.wait(0.5)

    assert pos.take() == ""


def test_repeats_follow_the_weight() -> None:
    pos = Pos()
    pos.set_weight(1000)
    pos.send("R")

    pos.set_weight(2000)
    pos.wait(0.25)

    assert "2.000kg_" in pos.take()


def test_high_resolution_repeats() -> None:
    pos = Pos()
    pos.set_weight(1252)

    assert pos.send("S") == "\n 1g      1.2520kg_\r"
    pos.wait(0.25)
    assert "1.2520kg_" in pos.take()


def test_repeats_go_only_to_the_connection_that_asked() -> None:
    pos = Pos()
    pos.connect("B")
    pos.set_weight(1000)

    pos.send("R", "A")
    pos.wait(0.25)

    assert pos.take("A") != ""
    assert pos.take("B") == ""


# --- diagnostics, About and Information ---------------------------------------------------------


def test_diagnostics_report_nothing_wrong() -> None:
    assert Pos().send("D") == "\n    \r"


def test_the_about_dialogue() -> None:
    pos = Pos()

    replies = [pos.send("A"), *[pos.send("B") for _ in range(4)]]

    assert replies == [
        "\nSMA:2/1.0\r",
        "\nMFG:emupos\r",
        "\nMOD:SMA 15kg\r",
        "\nREV:1.0\r",
        "\nEND:\r",
    ]
    assert pos.send("B") == "\n?\r"  # past the last field


def test_the_information_dialogue_reports_the_scale() -> None:
    pos = Pos()

    replies = [pos.send("I"), *[pos.send("N") for _ in range(4)]]

    assert replies == [
        "\nSMA:2/1.0\r",
        "\nTYP:S\r",
        "\nCAP:kg_:15.000:5:3\r",
        "\nCMD:HPQRSTMCU\r",
        "\nEND:\r",
    ]


def test_the_capacity_line_follows_the_current_unit() -> None:
    pos = Pos()
    pos.send("Ulb_")
    pos.send("I")

    assert pos.send("N") == "\nTYP:S\r"
    assert pos.send("N") == "\nCAP:lb_:33.07:1:2\r"


def test_dialogue_pointers_belong_to_one_connection() -> None:
    pos = Pos()
    pos.connect("B")

    pos.send("A", "A")
    pos.send("B", "A")

    assert pos.send("B", "B") == "\n?\r"


# --- unknown commands and abort -----------------------------------------------------------------


@pytest.mark.parametrize("frame", ["K", "Xc"])
def test_unrecognised_commands(frame: str) -> None:
    assert Pos().send(frame) == "\n?\r"


def test_abort_stops_a_repeat_and_changes_nothing() -> None:
    pos = Pos()
    pos.set_weight(1000)
    pos.send("T")
    pos.send("R")
    pos.take()

    assert pos.send_bytes(b"\x1b") == ""
    pos.wait(0.5)
    assert pos.take() == ""
    assert pos.scale.state(pos.now).grams == 1000
    assert pos.scale.state(pos.now).tare_grams == 1000
    unit = pos.scale.unit()
    assert unit is not None
    assert unit.unit == "kg_"


def test_abort_discards_a_partial_frame() -> None:
    pos = Pos()
    pos.set_weight(1000)

    assert pos.send_bytes(b"\nW") == ""
    assert pos.send_bytes(b"\x1b\nW\r") == "\n 1G       1.000kg_\r"


def test_abort_resets_the_about_pointer() -> None:
    pos = Pos()
    pos.send("A")

    pos.send_bytes(b"\x1b")

    assert pos.send("B") == "\n?\r"


def test_every_answered_frame_publishes_a_request_event() -> None:
    pos = Pos()
    pos.set_weight(1250)

    pos.send("W")

    answered = [e for e in pos.events if e.type is EventType.SCALE_REQUEST_ANSWERED]
    assert answered[-1].data["request"] == "0a 57 0d"
    assert str(answered[-1].data["reply"]).startswith("0a 20 31 47")
