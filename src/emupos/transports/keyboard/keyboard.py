"""The operating system's keyboard, as seen by a keyboard-wedge scan (design D10).

One implementation per OS: macos.py (Quartz), windows.py (SendInput), x11.py (XTest).
"""

import asyncio
import sys
from collections.abc import Sequence
from typing import Protocol

from emupos.scanner.keys import Key


class KeyboardUnavailableError(Exception):
    """Keystrokes cannot be typed on this system right now; `fix` says what to do."""

    def __init__(self, message: str, fix: str) -> None:
        self.message = message
        self.fix = fix
        super().__init__(f"{message}; {fix}")


class Keyboard(Protocol):
    def check_ready(self) -> None:
        """Raise KeyboardUnavailableError when keystrokes would not be delivered.

        Queries the system on every call, so a permission granted while emupos runs counts.
        """
        ...

    def start_scan(self, keys: Sequence[Key]) -> None:
        """Get ready to type one scan's `keys`. Called before its first key."""
        ...

    def press(self, key: Key) -> bool:
        """Press and release one key (with Shift when the key says so).

        Returns False when the OS reported that it did not accept the key's events.
        """
        ...

    def end_scan(self) -> None:
        """Undo what `start_scan` changed. Called after the last key, also when typing stops early."""
        ...


def system_keyboard() -> Keyboard:
    """The keyboard of the running OS. Opens nothing: call `check_ready()` before each scan."""
    if sys.platform == "darwin":
        from emupos.transports.keyboard.macos import MacKeyboard

        return MacKeyboard()
    if sys.platform == "win32":
        from emupos.transports.keyboard.windows import WindowsKeyboard

        return WindowsKeyboard()
    from emupos.transports.keyboard.x11 import X11Keyboard

    return X11Keyboard()


async def type_keys(keyboard: Keyboard, keys: Sequence[Key], inter_key_delay_ms: int) -> int:
    """Press `keys` in order, starting each at least `inter_key_delay_ms` after the previous one.

    Returns how many keys the OS accepted.
    """
    loop = asyncio.get_running_loop()
    accepted = 0
    keyboard.start_scan(keys)
    try:
        next_start = loop.time()
        for key in keys:
            # A timer may fire up to the clock resolution early (about 16 ms on Windows): re-check.
            while (remaining := next_start - loop.time()) > 0:
                await asyncio.sleep(remaining)
            accepted += keyboard.press(key)
            # Counted from the end of the press.
            next_start = loop.time() + inter_key_delay_ms / 1000
    finally:
        keyboard.end_scan()
    return accepted
