"""Windows keyboard tests on every OS: SendInput is replaced by a recorder, nothing is typed."""

import ctypes

import pytest

from emupos.scanner.keys import ENTER, TAB, US_LAYOUT, PhysicalKey, UnicodeText
from emupos.transports.keyboard import windows

type Event = tuple[int, int, int]  # (virtual key, scan code, flags)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[Event]]:
    calls: list[list[Event]] = []

    def record(events: "ctypes.Array[windows.INPUT]") -> int:
        assert all(e.type == windows.INPUT_KEYBOARD == 1 for e in events)
        calls.append([(e.u.ki.wVk, e.u.ki.wScan, e.u.ki.dwFlags) for e in events])
        return len(events)

    monkeypatch.setattr(windows, "_send_input", record)
    return calls


def test_input_has_the_windows_layout() -> None:
    assert ctypes.sizeof(windows.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_every_us_character_has_a_key() -> None:
    usages = {key.usage for key in US_LAYOUT.values()} | {ENTER, TAB}

    assert usages <= set(windows.KEY_CODES)


@pytest.mark.parametrize(
    ("char", "codes"),
    [
        ("a", (0x41, 0x1E)),
        ("5", (0x35, 0x06)),
        ("-", (189, 0x0C)),  # VK_OEM_MINUS, as the spike observed
        (" ", (0x20, 0x39)),
        ("/", (0xBF, 0x35)),
        ("`", (0xC0, 0x29)),
        ("\\", (0xDC, 0x2B)),
    ],
)
def test_key_codes(char: str, codes: tuple[int, int]) -> None:
    assert windows.KEY_CODES[US_LAYOUT[char].usage] == codes


def test_plain_key(sent: list[list[Event]]) -> None:
    assert windows.WindowsKeyboard().press(US_LAYOUT["1"])

    assert sent == [[(0x31, 0x02, 0), (0x31, 0x02, windows.KEYEVENTF_KEYUP)]]


def test_shifted_key_is_wrapped_in_shift_in_one_call(sent: list[list[Event]]) -> None:
    windows.WindowsKeyboard().press(US_LAYOUT["A"])

    up = windows.KEYEVENTF_KEYUP
    assert sent == [[(0x10, 0x2A, 0), (0x41, 0x1E, 0), (0x41, 0x1E, up), (0x10, 0x2A, up)]]


def test_unicode_sends_utf16_units(sent: list[list[Event]]) -> None:
    keyboard = windows.WindowsKeyboard()
    keyboard.press(UnicodeText("ك"))
    keyboard.press(UnicodeText("😀"))  # outside the BMP: a surrogate pair

    unicode, up = windows.KEYEVENTF_UNICODE, windows.KEYEVENTF_UNICODE | windows.KEYEVENTF_KEYUP
    assert sent[0] == [(0, 0x0643, unicode), (0, 0x0643, up)]
    assert [(scan, flags) for _, scan, flags in sent[1]] == [
        (0xD83D, unicode),
        (0xD83D, up),
        (0xDE00, unicode),
        (0xDE00, up),
    ]


def test_refused_events_report_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse_one(events: "ctypes.Array[windows.INPUT]") -> int:
        return len(events) - 1

    monkeypatch.setattr(windows, "_send_input", refuse_one)

    assert not windows.WindowsKeyboard().press(US_LAYOUT["1"])


def test_unknown_key_sends_nothing(sent: list[list[Event]]) -> None:
    assert not windows.WindowsKeyboard().press(PhysicalKey(0x3A))  # F1

    assert sent == []
