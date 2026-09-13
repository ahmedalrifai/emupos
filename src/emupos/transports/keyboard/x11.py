"""Linux keyboard: XTest through libX11 and libXtst via ctypes (design D10). X11 only.

Keys are pressed by physical position (evdev key code + 8), not looked up in the current
keymap, so the active layout decides the characters exactly as for a real USB scanner.
"""

import ctypes
import os

from emupos.scanner.keys import ENTER, LEFT_SHIFT, TAB, US_LAYOUT, Key, UnicodeText
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

NEEDS_X11_FIX = (
    "keyboard mode types through X11: log in to an X11 (Xorg) session, "
    "or set `mode: serial` for this scanner (see docs/linux-x11.md)"
)

# Linux evdev KEY_* codes (linux/input-event-codes.h) run along the rows of a PC keyboard.
_EVDEV_ROWS = (
    (2, "1234567890-="),  # KEY_1 = 2 ... KEY_EQUAL = 13
    (16, "qwertyuiop[]"),  # KEY_Q = 16 ... KEY_RIGHTBRACE = 27
    (30, "asdfghjkl;'`"),  # KEY_A = 30 ... KEY_GRAVE = 41
    (43, "\\zxcvbnm,./"),  # KEY_BACKSLASH = 43 ... KEY_SLASH = 53
    (57, " "),  # KEY_SPACE
)
# ponytail: assumes the X server numbers keys evdev + 8 (Xorg with libinput/evdev, Xvfb, Xvnc);
# look keycodes up with XKeysymToKeycode if a server with another numbering matters.
_X_KEYCODE_OFFSET = 8

# HID usage ID -> X keycode. KEY_ENTER = 28, KEY_TAB = 15, KEY_LEFTSHIFT = 42.
KEYCODES: dict[int, int] = {
    **{
        US_LAYOUT[char].usage: first + offset + _X_KEYCODE_OFFSET
        for first, chars in _EVDEV_ROWS
        for offset, char in enumerate(chars)
    },
    ENTER: 28 + _X_KEYCODE_OFFSET,
    TAB: 15 + _X_KEYCODE_OFFSET,
    LEFT_SHIFT: 42 + _X_KEYCODE_OFFSET,
}

# Xlib's default error handler exits the process; a refused request must not stop emupos.
_ErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


def _ignore_error(_display: int | None, _error: int | None) -> int:
    return 0


_IGNORE_ERRORS = _ErrorHandler(_ignore_error)


def _load_library(name: str) -> ctypes.CDLL:
    return ctypes.CDLL(name)


def check_session() -> None:
    """Raise KeyboardUnavailableError unless this is an X11 session."""
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":  # checked first: XWayland sets DISPLAY
        raise KeyboardUnavailableError(
            "keystrokes cannot be typed: this is a Wayland session", NEEDS_X11_FIX
        )
    if not os.environ.get("DISPLAY"):
        raise KeyboardUnavailableError(
            "keystrokes cannot be typed: no X11 display (DISPLAY is not set)", NEEDS_X11_FIX
        )


def load_libraries() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    """libX11 and libXtst with their function signatures. Raises KeyboardUnavailableError."""
    try:
        x11 = _load_library("libX11.so.6")
    except OSError:
        raise KeyboardUnavailableError(
            "keystrokes cannot be typed: libX11 is not installed",
            "install libX11: `sudo apt install libx11-6` (Debian/Ubuntu) "
            "or `sudo dnf install libX11` (Fedora)",
        ) from None
    try:
        xtst = _load_library("libXtst.so.6")
    except OSError:
        raise KeyboardUnavailableError(
            "keystrokes cannot be typed: the X11 test extension library libXtst is not installed",
            "install libXtst: `sudo apt install libxtst6` (Debian/Ubuntu) "
            "or `sudo dnf install libXtst` (Fedora), then scan again",
        ) from None
    display, c_int_p, c_ulong_p = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
    )
    x11.XSetErrorHandler.argtypes = [_ErrorHandler]
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = display
    x11.XCloseDisplay.argtypes = [display]
    x11.XFlush.argtypes = [display]
    x11.XSync.argtypes = [display, ctypes.c_int]
    x11.XDisplayKeycodes.argtypes = [display, c_int_p, c_int_p]
    x11.XGetKeyboardMapping.argtypes = [display, ctypes.c_ubyte, ctypes.c_int, c_int_p]
    x11.XGetKeyboardMapping.restype = c_ulong_p
    x11.XChangeKeyboardMapping.argtypes = [
        display,
        ctypes.c_int,
        ctypes.c_int,
        c_ulong_p,
        ctypes.c_int,
    ]
    x11.XFree.argtypes = [ctypes.c_void_p]
    xtst.XTestQueryExtension.argtypes = [display, c_int_p, c_int_p, c_int_p, c_int_p]
    xtst.XTestFakeKeyEvent.argtypes = [display, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    return x11, xtst


class X11Keyboard:
    def __init__(self) -> None:
        # ponytail: one display connection for the whole run, never closed. If the X server
        # goes away, Xlib's I/O error handler still exits the process.
        self._libraries: tuple[ctypes.CDLL, ctypes.CDLL] | None = None
        self._display: int | None = None
        self._spare_keycode: int | None = None

    def check_ready(self) -> None:
        check_session()
        if self._display is not None:
            return
        x11, xtst = load_libraries()
        x11.XSetErrorHandler(_IGNORE_ERRORS)
        display: int | None = x11.XOpenDisplay(None)
        if not display:
            raise KeyboardUnavailableError(
                f"keystrokes cannot be typed: cannot connect to the X11 display {os.environ.get('DISPLAY')!r}",
                "check that DISPLAY names your running X session and that this user may use it "
                "(XAUTHORITY), or set `mode: serial` for this scanner",
            )
        numbers = [ctypes.c_int() for _ in range(4)]
        if not xtst.XTestQueryExtension(display, *[ctypes.byref(n) for n in numbers]):
            x11.XCloseDisplay(display)
            raise KeyboardUnavailableError(
                "keystrokes cannot be typed: the X server has no XTEST extension",
                "enable the XTEST extension in the X server, or set `mode: serial` for this scanner",
            )
        self._libraries, self._display = (x11, xtst), display

    def press(self, key: Key) -> bool:
        if self._libraries is None or self._display is None:
            return False
        (x11, xtst), display = self._libraries, self._display
        if isinstance(key, UnicodeText):
            keycode = self._bind_spare_keycode(x11, display, key.char)
            if keycode is None:
                return False
            events = [(keycode, True), (keycode, False)]
        else:
            keycode = KEYCODES.get(key.usage)
            if keycode is None:
                return False
            events = [(keycode, True), (keycode, False)]
            if key.shift:
                shift = KEYCODES[LEFT_SHIFT]
                events = [(shift, True), *events, (shift, False)]
        results = [xtst.XTestFakeKeyEvent(display, code, down, 0) for code, down in events]
        x11.XFlush(display)
        return all(results)

    def _bind_spare_keycode(self, x11: ctypes.CDLL, display: int, char: str) -> int | None:
        """Map an unused keycode to `char`'s keysym, as xdotool does, and return it."""
        if self._spare_keycode is None:
            self._spare_keycode = _find_unused_keycode(x11, display)
            if self._spare_keycode is None:
                return None
        code_point = ord(char)
        latin1 = 0x20 <= code_point <= 0x7E or 0xA0 <= code_point <= 0xFF
        keysym = ctypes.c_ulong(code_point if latin1 else 0x01000000 | code_point)
        # ponytail: the mapping is left in place after the key, not restored, so an app that
        # reads the keymap a little late still sees this character (reverting races with it).
        x11.XChangeKeyboardMapping(display, self._spare_keycode, 1, ctypes.byref(keysym), 1)
        x11.XSync(display, 0)
        return self._spare_keycode


def _find_unused_keycode(x11: ctypes.CDLL, display: int) -> int | None:
    """The highest keycode with no keysyms in the current keymap."""
    lowest, highest, per_keycode = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    x11.XDisplayKeycodes(display, ctypes.byref(lowest), ctypes.byref(highest))
    count = highest.value - lowest.value + 1
    keysyms = x11.XGetKeyboardMapping(display, lowest.value, count, ctypes.byref(per_keycode))
    if not keysyms:
        return None
    try:
        width = per_keycode.value
        for index in reversed(range(count)):
            if not any(keysyms[index * width + level] for level in range(width)):
                return lowest.value + index
        return None
    finally:
        x11.XFree(keysyms)
