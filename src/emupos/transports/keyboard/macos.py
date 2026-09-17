"""macOS keyboard: Quartz `CGEventPost` with US ANSI virtual key codes (design D10).

macOS drops posted keystrokes silently unless the app that started emupos (normally the
terminal) is allowed under Accessibility, so `check_ready` asks Quartz before every scan.
"""

import importlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from emupos.scanner.keys import ENTER, LEFT_SHIFT, TAB, US_LAYOUT, Key, UnicodeText
from emupos.transports.keyboard.focus import outermost_bundle, ps_ancestors
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

if sys.platform == "darwin":
    Quartz: Any = importlib.import_module("Quartz")  # pyobjc ships no type information

# kVK_ANSI_* key codes (Carbon HIToolbox Events.h) of the keys typing these characters on the
# US layout; checked against a US input source by test_macos.py.
_KEY_CODE_BY_US_CHAR = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06, "x": 0x07,
    "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10,
    "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "o": 0x1F, "u": 0x20,
    "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29,
    "\\": 0x2A, ",": 0x2B, "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, " ": 0x31, "`": 0x32,
}  # fmt: skip

# HID usage ID -> macOS key code: kVK_Return 0x24, kVK_Tab 0x30, kVK_Shift 0x38.
KEY_CODES: dict[int, int] = {
    **{US_LAYOUT[char].usage: code for char, code in _KEY_CODE_BY_US_CHAR.items()},
    ENTER: 0x24,
    TAB: 0x30,
    LEFT_SHIFT: 0x38,
}

ACCESSIBILITY_SETTINGS = "System Settings > Privacy & Security > Accessibility"


class MacKeyboard:
    def check_ready(self) -> None:
        if sys.platform != "darwin":
            raise KeyboardUnavailableError(
                "the macOS keyboard is only available on macOS", "use system_keyboard()"
            )
        if not Quartz.CGPreflightPostEventAccess():
            app = _app_to_allow()
            raise KeyboardUnavailableError(
                f"keystrokes cannot be posted: macOS has not given {app} Accessibility permission",
                f"open {ACCESSIBILITY_SETTINGS}, turn on {app} (add it with + if it is not listed), "
                "then scan again; if it is still refused, quit and reopen that app "
                "(see docs/macos-accessibility.md)",
            )

    def start_scan(self, keys: Sequence[Key]) -> None:
        pass  # each event carries its own key code or text: nothing to prepare

    def end_scan(self) -> None:
        pass

    async def prepare_key(self, key: Key) -> None:
        pass

    def press(self, key: Key) -> bool:
        if sys.platform != "darwin":
            return False
        if isinstance(key, UnicodeText):
            # Key code 0 carries the text; apps insert the attached string, whatever the layout.
            text: str | None = key.char
            strokes = [(0, True, 0), (0, False, 0)]
        else:
            text = None
            code = KEY_CODES.get(key.usage)
            if code is None:
                return False
            flags = Quartz.kCGEventFlagMaskShift if key.shift else 0
            strokes = [(code, True, flags), (code, False, flags)]
            if key.shift:
                shift = KEY_CODES[LEFT_SHIFT]
                strokes = [(shift, True, flags), *strokes, (shift, False, 0)]
        for code, down, flags in strokes:
            event = Quartz.CGEventCreateKeyboardEvent(None, code, down)
            if event is None:
                return False
            Quartz.CGEventSetFlags(event, flags)
            if text is not None:
                Quartz.CGEventKeyboardSetUnicodeString(
                    event, len(text.encode("utf-16-le")) // 2, text
                )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        # CGEventPost reports nothing: True means posted, not that an app received the keys.
        return True


def _app_to_allow() -> str:
    """The app macOS attributes the permission to: the first .app among the parent processes."""
    for _pid, executable in ps_ancestors():
        if (bundle := outermost_bundle(executable)) is not None:
            return f"{Path(bundle).stem} ({bundle})"
    return f"the app that started emupos (Python is {os.path.realpath(sys.executable)})"
