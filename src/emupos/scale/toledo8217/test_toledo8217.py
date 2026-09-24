"""Toledo 8217 protocol tests.

Each `dialogues/<scenario>.txt` replays one weight-scale spec scenario against a `Scale` with the
built-in `toledo8217-15kg` profile (15000 g capacity, 5 g divisions, 500 ms settle time).
Lines, in order:

    # comment
    @ t=0.4                         set the clock (seconds) for the lines below; it starts at 0
    @ set grams=1250 stable=false   set the gross weight and stability
    @ tare                          tare the scale
    @ zero                          zero the scale
    > 57 0d 0a                      bytes the POS sends in one chunk, as spaced hex
    < 02 30 31 2e 32 35 30 0d       every byte the scale writes back for the `>` line above

A `>` line with no `<` line after it expects no reply at all.
"""

import re
from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from emupos.config import Toledo8217Profile
from emupos.scale.scale import Scale, ScaleState
from emupos.scale.toledo8217.toledo8217 import Status, Toledo8217, kilograms, status, weight_reply


class Reading:
    """The little a Toledo protocol asks of a scale: the reading in front of it."""

    def __init__(self, scale_state: ScaleState) -> None:
        self._state = scale_state

    def now(self) -> float:
        return 0.0

    def state(self) -> ScaleState:
        return self._state

    def unit(self) -> None:
        return None  # the Toledo protocol has no unit of measure


PROFILE = Toledo8217Profile.model_validate(
    yaml.safe_load(
        resources.files("emupos").joinpath("profiles/scales/toledo8217-15kg.yaml").read_text()
    )
)
DIALOGUES = sorted((Path(__file__).parent / "dialogues").glob("*.txt"))

# The reply patterns a POS client such as Odoo's Toledo 8217 driver matches (weight-scale spec).
MEASURE = re.compile(rb"\x02\s*([0-9.]+)N?\r")
STATUS = re.compile(rb"\x02\?(.)\r")


def replay(text: str) -> tuple[list[str], list[str]]:
    """Run a dialogue; return its `>`/`<` lines as written and as actually produced."""
    scale = Scale("deli", PROFILE)
    now = 0.0
    expected: list[str] = []
    actual: list[str] = []
    for line in text.splitlines():
        kind, _, rest = line.partition(" ")
        words = {key: value for key, _, value in (word.partition("=") for word in rest.split())}
        match kind:
            case "@" if "t" in words:
                now = float(words["t"])
            case "@" if rest.startswith("set "):
                stable = {"true": True, "false": False}[words["stable"]]
                scale.set_weight(int(words["grams"]), stable, now)
            case "@" if rest == "tare":
                scale.tare(now)
            case "@" if rest == "zero":
                scale.zero(now)
            case ">":
                data = bytes.fromhex(rest)
                expected.append(f"> {data.hex(' ')}")
                actual.append(f"> {data.hex(' ')}")
                reply = b"".join(write.data for write in scale.receive("pos", data, now).writes)
                if reply:
                    actual.append(f"< {reply.hex(' ')}")
            case "<":
                expected.append(f"< {bytes.fromhex(rest).hex(' ')}")
            case "#" | "":
                pass
            case _:
                raise ValueError(f"unknown dialogue line: {line!r}")
    return expected, actual


@pytest.mark.parametrize("path", DIALOGUES, ids=[path.stem for path in DIALOGUES])
def test_dialogue(path: Path) -> None:
    expected, actual = replay(path.read_text(encoding="utf-8"))

    assert actual == expected


def test_every_spec_wire_scenario_has_a_dialogue() -> None:
    assert len(DIALOGUES) == 14


# Replies as POS clients parse them


def state(grams: int, tare_grams: int = 0, stable: bool = True) -> ScaleState:
    return ScaleState(grams, tare_grams, grams - tare_grams, stable, PROFILE.capacity_grams)


def test_stable_gross_weight_matches_the_client_pattern() -> None:
    match = MEASURE.fullmatch(weight_reply(state(1250), PROFILE))

    assert match is not None
    assert b"N" not in match[0]
    assert Decimal(match[1].decode()) == Decimal("1.250")


def test_stable_net_weight_matches_the_client_pattern() -> None:
    match = re.fullmatch(
        rb"\x02\s*([0-9.]+)N\r", weight_reply(state(1450, tare_grams=200), PROFILE)
    )

    assert match is not None
    assert Decimal(match[1].decode()) == Decimal("1.250")


def test_weight_exactly_at_capacity_matches_the_client_pattern() -> None:
    match = MEASURE.fullmatch(weight_reply(state(15000), PROFILE))

    assert match is not None
    assert Decimal(match[1].decode()) == Decimal("15.000")


@pytest.mark.parametrize(
    ("scale_state", "bits"),
    [
        (state(1250, stable=False), Status.IN_MOTION),
        (state(15001), Status.OVER_CAPACITY),  # status byte 02, the same value as STX
        (state(-100), Status.UNDER_ZERO),
        (state(100, tare_grams=200), Status.UNDER_ZERO | Status.NET_WEIGHT),
        (
            state(16000, 200, stable=False),
            Status.IN_MOTION | Status.OVER_CAPACITY | Status.NET_WEIGHT,
        ),
    ],
)
def test_status_replies_match_the_client_pattern(scale_state: ScaleState, bits: Status) -> None:
    reply = weight_reply(scale_state, PROFILE)

    match = STATUS.fullmatch(reply)
    assert match is not None
    assert Status(match[1][0]) == bits
    assert MEASURE.search(reply) is None


def test_bad_command_status_matches_the_client_pattern() -> None:
    written, _ = Toledo8217(PROFILE).receive(b"X", Reading(state(1250)))

    match = STATUS.fullmatch(written)
    assert match is not None
    assert Status(match[1][0]) == Status.BAD_COMMAND


# Rounding to the profile's division


@pytest.mark.parametrize(
    ("grams", "text"),
    [(0, "00.000"), (1250, "01.250"), (1252, "01.250"), (1253, "01.255"), (15000, "15.000")],
)
def test_weight_is_rounded_to_the_nearest_division(grams: int, text: str) -> None:
    assert kilograms(grams, PROFILE) == text


def test_division_ties_round_away_from_zero() -> None:
    ten_gram_divisions = PROFILE.model_copy(update={"division_grams": 10})

    assert kilograms(1245, ten_gram_divisions) == "01.250"
    assert kilograms(1244, ten_gram_divisions) == "01.240"


def test_integer_digits_widen_rather_than_truncate() -> None:
    assert kilograms(150000, PROFILE) == "150.000"


def test_center_of_zero_is_reported_with_the_other_bits() -> None:
    assert status(state(0, stable=False)) == Status.IN_MOTION | Status.CENTER_OF_ZERO


# Fuzzing (design D15)

states = st.builds(
    state, st.integers(-30000, 30000), st.one_of(st.just(0), st.integers(1, 30000)), st.booleans()
)
# Bias towards bytes the protocol handles so the echo, weight and line-terminator paths are reached.
handled_bytes = st.sampled_from(b"WEF\r\n")
streams = st.lists(st.one_of(handled_bytes, st.integers(0, 255)), max_size=64).map(bytes)


@given(scale_state=states, data=streams)
def test_random_bytes_never_raise(scale_state: ScaleState, data: bytes) -> None:
    Toledo8217(PROFILE).receive(data, Reading(scale_state))


@given(scale_state=states, data=streams, cuts=st.lists(st.integers(0, 64), max_size=8))
def test_any_split_of_a_byte_stream_gives_the_same_replies(
    scale_state: ScaleState, data: bytes, cuts: list[int]
) -> None:
    whole = Toledo8217(PROFILE).receive(data, Reading(scale_state))

    protocol = Toledo8217(PROFILE)
    written = b""
    answers: list[tuple[bytes, bytes]] = []
    points = sorted({min(cut, len(data)) for cut in cuts})
    for start, end in zip([0, *points], [*points, len(data)], strict=True):
        chunk_written, chunk_answers = protocol.receive(data[start:end], Reading(scale_state))
        written += chunk_written
        answers += chunk_answers

    assert (written, answers) == whole


@given(scale_state=states, data=streams)
def test_replies_outside_the_echo_probe_are_7_bit(scale_state: ScaleState, data: bytes) -> None:
    written, answers = Toledo8217(PROFILE).receive(data.replace(b"E", b""), Reading(scale_state))

    assert all(byte < 0x80 for byte in written)
    assert b"".join(reply for _, reply in answers) == written


@given(scale_state=states)
def test_every_weight_reply_matches_exactly_one_client_pattern(scale_state: ScaleState) -> None:
    reply = weight_reply(scale_state, PROFILE)

    measure, status_match = MEASURE.fullmatch(reply), STATUS.fullmatch(reply)
    assert (measure is None) != (status_match is None)
    if status_match is not None:
        assert status_match[1][0] & 0b1000_1000 == 0  # bits 3 and 7 are always clear
