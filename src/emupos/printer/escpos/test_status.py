import pytest

from emupos.printer.escpos.status import StatusState, asb, asb_changed, dle_eot, gs_r

NO_FAULTS = StatusState()
COVER_OPEN = StatusState(cover_open=True)
PAPER_OUT = StatusState(paper_out=True)
NEAR_END = StatusState(paper_near_end=True)
OFFLINE = StatusState(offline=True)
DRAWER_HIGH = StatusState(drawer_pin3_high=True)


@pytest.mark.parametrize(
    ("state", "replies"),
    [
        (NO_FAULTS, "12 12 12 12"),
        (COVER_OPEN, "1a 16 12 12"),
        (PAPER_OUT, "1a 32 12 7e"),
        (NEAR_END, "12 12 12 1e"),
        (OFFLINE, "1a 12 12 12"),
        (DRAWER_HIGH, "16 12 12 12"),
        (StatusState(cover_open=True, drawer_pin3_high=True), "1e 16 12 12"),
    ],
)
def test_dle_eot_replies(state: StatusState, replies: str) -> None:
    assert b"".join(dle_eot(n, state) or b"" for n in (1, 2, 3, 4)) == bytes.fromhex(replies)


@pytest.mark.parametrize("n", [0, 5, 7, 255])
def test_dle_eot_without_a_simulated_status_has_no_reply(n: int) -> None:
    assert dle_eot(n, NO_FAULTS) is None


@pytest.mark.parametrize(
    ("n", "state", "reply"),
    [
        (1, NO_FAULTS, "00"),
        (49, NEAR_END, "03"),
        (1, PAPER_OUT, "0f"),
        (2, NO_FAULTS, "00"),
        (50, DRAWER_HIGH, "01"),
    ],
)
def test_gs_r_replies(n: int, state: StatusState, reply: str) -> None:
    assert gs_r(n, state) == bytes.fromhex(reply)


def test_gs_r_ink_status_is_not_simulated() -> None:
    assert gs_r(4, NO_FAULTS) is None


@pytest.mark.parametrize(
    ("state", "status"),
    [
        (NO_FAULTS, "10 00 00 00"),
        (DRAWER_HIGH, "14 00 00 00"),
        (OFFLINE, "18 00 00 00"),
        (COVER_OPEN, "38 00 00 00"),
        (NEAR_END, "10 00 03 00"),
        (PAPER_OUT, "18 00 0f 00"),
    ],
)
def test_asb_status(state: StatusState, status: str) -> None:
    assert asb(state) == bytes.fromhex(status)


def test_asb_changes_only_count_for_enabled_categories() -> None:
    assert asb_changed(0xFF, NO_FAULTS, NEAR_END)
    assert not asb_changed(0x02, NO_FAULTS, NEAR_END)  # online/offline only
    assert asb_changed(0x02, NO_FAULTS, COVER_OPEN)
    assert asb_changed(0x01, NO_FAULTS, DRAWER_HIGH)
    assert not asb_changed(0x08, NO_FAULTS, DRAWER_HIGH)
    assert not asb_changed(0xFF, NO_FAULTS, NO_FAULTS)
