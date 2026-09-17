"""Windows keyboard: `SendInput` with US-layout virtual-key codes and scan codes (design D10).

Each key carries its virtual-key code and its scan code: without the scan code, browsers report
an empty `KeyboardEvent.code` (spike 1.2). The receiving window turns the key into a character
with its own active layout, exactly as with a real USB scanner.

Windows discards keystrokes sent into a window with higher privileges (UIPI) and still counts
them as accepted, so `press` returning True does not prove the keys arrived.
"""

import ctypes
import sys
from collections.abc import Sequence

from emupos.scanner.keys import ENTER, LEFT_SHIFT, TAB, US_LAYOUT, Key, UnicodeText
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# Scan code set 1 runs along the rows of a PC keyboard (Linux evdev codes use the same numbers).
_SCAN_ROWS = (
    (0x02, "1234567890-="),
    (0x10, "qwertyuiop[]"),
    (0x1E, "asdfghjkl;'`"),
    (0x2B, "\\zxcvbnm,./"),
    (0x39, " "),
)
# VK_OEM_* codes of the US punctuation keys; letters, digits and space use their ASCII code.
_OEM_VIRTUAL_KEYS = {
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, "`": 0xC0, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}  # fmt: skip

# HID usage ID -> (virtual-key code, scan code). VK_RETURN, VK_TAB, VK_SHIFT.
KEY_CODES: dict[int, tuple[int, int]] = {
    **{
        US_LAYOUT[char].usage: (_OEM_VIRTUAL_KEYS.get(char, ord(char.upper())), first + offset)
        for first, chars in _SCAN_ROWS
        for offset, char in enumerate(chars)
    },
    ENTER: (0x0D, 0x1C),
    TAB: (0x09, 0x0F),
    LEFT_SHIFT: (0x10, 0x2A),
}


# Fixed-width fields rather than ctypes.wintypes, whose DWORD is 8 bytes off Windows: the layout
# stays the Windows one everywhere, so the tests check it on every OS.
class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_int32),
        ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT is the largest member: without it sizeof(INPUT) is wrong and SendInput fails.
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", ctypes.c_uint32), ("u", _INPUTUNION))


if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
    _user32.SendInput.restype = ctypes.c_uint


def _send_input(events: "ctypes.Array[INPUT]") -> int:
    """How many of `events` Windows accepted."""
    if sys.platform != "win32":
        return 0
    return _user32.SendInput(len(events), events, ctypes.sizeof(INPUT))


def _event(virtual_key: int, scan: int, flags: int) -> INPUT:
    event = INPUT(type=INPUT_KEYBOARD)
    event.u.ki = KEYBDINPUT(wVk=virtual_key, wScan=scan, dwFlags=flags)
    return event


def key_events(key: Key) -> list[INPUT] | None:
    """The down and up events for `key`, or None when it has no Windows key."""
    if isinstance(key, UnicodeText):
        units = key.char.encode("utf-16-le")
        return [
            _event(0, int.from_bytes(units[i : i + 2], "little"), KEYEVENTF_UNICODE | up)
            for i in range(0, len(units), 2)
            for up in (0, KEYEVENTF_KEYUP)
        ]
    if (codes := KEY_CODES.get(key.usage)) is None:
        return None
    events = [_event(*codes, 0), _event(*codes, KEYEVENTF_KEYUP)]
    if key.shift:
        shift = KEY_CODES[LEFT_SHIFT]
        events = [_event(*shift, 0), *events, _event(*shift, KEYEVENTF_KEYUP)]
    return events


class WindowsKeyboard:
    def check_ready(self) -> None:
        if sys.platform != "win32":
            raise KeyboardUnavailableError(
                "the Windows keyboard is only available on Windows", "use system_keyboard()"
            )

    def start_scan(self, keys: Sequence[Key]) -> None:
        pass  # each event carries its own key code or text: nothing to prepare

    def end_scan(self) -> None:
        pass

    def press(self, key: Key) -> bool:
        if (events := key_events(key)) is None:
            return False
        # One call, so the user's own typing cannot land between Shift and the key.
        return _send_input((INPUT * len(events))(*events)) == len(events)
