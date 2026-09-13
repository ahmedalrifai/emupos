import pytest

from emupos.events import NO_OUTPUT, Event, EventType, Output
from emupos.scanner.keys import PhysicalKey, Suffix, UnicodeText
from emupos.scanner.scanner import Mode, Scanner, ScanRejectedError

ENTER, TAB = PhysicalKey(0x28), PhysicalKey(0x2B)


def scanner(mode: Mode = "keyboard", suffix: Suffix = "enter", device_id: str = "lane1") -> Scanner:
    return Scanner(device_id, mode, suffix, inter_key_delay_ms=10)


def rejection(
    target: Scanner, data: str, countdown_seconds: int = 3, unicode: bool = False
) -> ScanRejectedError:
    with pytest.raises(ScanRejectedError) as caught:
        target.request(data, countdown_seconds, unicode, now=100.0)
    return caught.value


# Scan requests


def test_scan_accepted_with_countdown() -> None:
    lane1 = scanner()

    scan = lane1.request("2112345012506", countdown_seconds=3, unicode=False, now=100.0)

    assert scan.deliver_at == 103.0
    assert scan.data == "2112345012506"
    assert scan.mode == "keyboard"
    assert lane1.busy


def test_no_countdown_delivers_immediately() -> None:
    assert (
        scanner().request("123", countdown_seconds=0, unicode=False, now=100.0).deliver_at == 100.0
    )


def test_empty_data_rejected() -> None:
    lane1 = scanner()

    error = rejection(lane1, "")

    assert (error.code, error.conflict) == ("validation_error", False)
    assert not lane1.busy


def test_negative_countdown_rejected() -> None:
    lane1 = scanner()

    error = rejection(lane1, "123", countdown_seconds=-1)

    assert (error.code, error.conflict) == ("validation_error", False)
    assert not lane1.busy


@pytest.mark.parametrize("mode", ["keyboard", "serial"])
def test_lone_surrogate_rejected(mode: Mode) -> None:
    error = rejection(scanner(mode), "12\ud80034", unicode=True)

    assert not error.conflict


def test_scan_ids_are_unique_and_skip_rejections() -> None:
    lane1, lane2 = scanner(), scanner("serial", device_id="lane2")

    first = lane1.request("1", 0, False, now=0.0)
    lane1.finished(first.id)
    rejection(lane1, "")
    second = lane1.request("2", 0, False, now=0.0)

    assert [first.id, second.id] == ["lane1-1", "lane1-2"]
    assert lane2.request("1", 0, False, now=0.0).id == "lane2-1"


# One scan at a time per scanner


def test_second_scan_during_countdown_rejected() -> None:
    lane1 = scanner()
    first = lane1.request("111", 3, False, now=100.0)

    error = rejection(lane1, "222")

    assert (error.code, error.conflict) == ("scan_in_progress", True)
    assert error.message == "a scan is already in progress on lane1"
    assert lane1.finished(first.id).events[0].data["data"] == "111"


def test_scan_after_delivery_finishes() -> None:
    lane1 = scanner()
    lane1.finished(lane1.request("111", 0, False, now=0.0).id)

    assert lane1.request("222", 0, False, now=1.0).data == "222"


def test_different_scanner_is_independent() -> None:
    lane1, lane2 = scanner(), scanner("serial", device_id="lane2")
    lane1.request("111", 3, False, now=0.0)

    assert lane2.request("222", 3, False, now=0.0).mode == "serial"


# Delivery event


def test_finished_publishes_exactly_one_event() -> None:
    lane1 = scanner()
    scan = lane1.request("2112345012506", 3, False, now=0.0)

    output = lane1.finished(scan.id)

    data = {"id": scan.id, "data": "2112345012506", "mode": "keyboard"}
    assert output == Output(events=(Event(EventType.SCANNER_SCAN_DELIVERED, "lane1", data),))
    assert lane1.finished(scan.id) == NO_OUTPUT
    assert not lane1.busy


def test_failed_scan_publishes_nothing_and_frees_the_scanner() -> None:
    lane1 = scanner()
    scan = lane1.request("123", 0, False, now=0.0)

    lane1.failed(scan.id)

    assert not lane1.busy
    assert lane1.finished(scan.id) == NO_OUTPUT


def test_report_for_another_scan_leaves_the_current_one() -> None:
    lane1 = scanner()
    scan = lane1.request("123", 0, False, now=0.0)

    lane1.failed("lane1-99")

    assert lane1.finished("lane1-99") == NO_OUTPUT
    assert lane1.busy
    assert lane1.finished(scan.id).events


# Keyboard mode


def test_keys_for_mixed_characters() -> None:
    scan = scanner().request("Ab1-", 0, False, now=0.0)

    assert scan.keys == (
        PhysicalKey(0x04, shift=True),
        PhysicalKey(0x05),
        PhysicalKey(0x1E),
        PhysicalKey(0x2D),
        ENTER,
    )
    assert scan.serial_bytes == b""


@pytest.mark.parametrize(("suffix", "last"), [("tab", (TAB,)), ("none", ())])
def test_keyboard_suffix(suffix: Suffix, last: tuple[PhysicalKey, ...]) -> None:
    scan = scanner(suffix=suffix).request("123", 0, False, now=0.0)

    assert scan.keys == (PhysicalKey(0x1E), PhysicalKey(0x1F), PhysicalKey(0x20), *last)


def test_non_ascii_without_unicode_rejected() -> None:
    lane1 = scanner()

    error = rejection(lane1, "كود42")

    assert not error.conflict
    assert error.fix is not None
    assert "unicode: true" in error.fix
    assert "--unicode" in error.fix
    assert not lane1.busy


def test_arabic_characters_typed_exactly_with_unicode() -> None:
    scan = scanner().request("كود-42", 0, True, now=0.0)

    assert scan.keys == (*(UnicodeText(char) for char in "كود-42"), ENTER)
    assert scan.unicode


@pytest.mark.parametrize("unicode", [False, True])
def test_control_characters_rejected_in_keyboard_mode(unicode: bool) -> None:
    assert not rejection(scanner(), "12\n34", unicode=unicode).conflict


# Serial mode


@pytest.mark.parametrize(
    ("suffix", "data", "expected"),
    [
        ("enter", "123", "31 32 33 0d"),
        ("enter", "2112345012506", "32 31 31 32 33 34 35 30 31 32 35 30 36 0d"),
        ("tab", "ABC-123", "41 42 43 2d 31 32 33 09"),
        ("none", "123", "31 32 33"),
    ],
)
def test_serial_bytes(suffix: Suffix, data: str, expected: str) -> None:
    scan = scanner("serial", suffix).request(data, 0, False, now=0.0)

    assert scan.serial_bytes == bytes.fromhex(expected)
    assert scan.keys == ()


def test_serial_countdown() -> None:
    assert scanner("serial").request("123", 2, False, now=10.0).deliver_at == 12.0


def test_serial_mode_ignores_unicode_and_sends_utf8() -> None:
    lane2 = scanner("serial", device_id="lane2")

    arabic = lane2.request("كود", 0, False, now=0.0)
    lane2.failed(arabic.id)
    group_separator = lane2.request("12\x1d34", 0, True, now=0.0)

    assert arabic.serial_bytes == bytes.fromhex("d9 83 d9 88 d8 af 0d")
    assert group_separator.serial_bytes == bytes.fromhex("31 32 1d 33 34 0d")


def test_serial_event_mode() -> None:
    lane2 = scanner("serial", device_id="lane2")
    scan = lane2.request("123", 0, False, now=0.0)

    assert lane2.finished(scan.id).events[0].data == {
        "id": "lane2-1",
        "data": "123",
        "mode": "serial",
    }
