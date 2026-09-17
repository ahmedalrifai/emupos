"""Linux keyboard: XTest through libX11 and libXtst via ctypes (design D10). X11 only.

Keys are pressed by physical position (evdev key code + 8), not looked up in the current
keymap, so the active layout decides the characters exactly as for a real USB scanner.
Unicode text uses the active layout's own keys where it has the character, and spare key
codes bound to the character otherwise, as `xdotool type` does.
"""

import atexit
import ctypes
import os
from collections.abc import Callable, Sequence

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

XKB_USE_CORE_KBD = 0x0100
LOCK_MASK = 0x02
_KEYPAD_KEYSYMS = range(0xFF80, 0xFFBE)  # KP_*: the level they type depends on Num Lock

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
    x11.XkbGetState.argtypes = [display, ctypes.c_uint, ctypes.c_void_p]
    x11.XkbLockModifiers.argtypes = [display, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
    xtst.XTestQueryExtension.argtypes = [display, c_int_p, c_int_p, c_int_p, c_int_p]
    xtst.XTestFakeKeyEvent.argtypes = [display, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    return x11, xtst


def load_keysym_to_utf32() -> Callable[[int], int] | None:
    """libxkbcommon's keysym -> code point (0 for none), or None when it is not installed."""
    try:
        xkbcommon = _load_library("libxkbcommon.so.0")
    except OSError:
        return None
    convert = xkbcommon.xkb_keysym_to_utf32
    convert.argtypes = [ctypes.c_uint32]
    convert.restype = ctypes.c_uint32
    return convert


class X11Keyboard:
    def __init__(self) -> None:
        # ponytail: one display connection for the whole run, never closed. If the X server
        # goes away, Xlib's I/O error handler still exits the process.
        self._libraries: tuple[ctypes.CDLL, ctypes.CDLL] | None = None
        self._display: int | None = None
        self._keysym_to_utf32: Callable[[int], int] | None = None
        self._layout_keys: dict[str, tuple[int, bool]] = {}  # char -> (keycode, Shift), per scan
        self._spare_keycodes: list[int] | None = None  # found on the first missing character
        self._bound: dict[str, int] = {}  # char -> spare keycode, least recently used first
        self._open_scans = 0
        self._relock_caps = False

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
        self._keysym_to_utf32 = load_keysym_to_utf32()
        atexit.register(self._unbind_all)

    def start_scan(self, keys: Sequence[Key]) -> None:
        """For Unicode text: Caps Lock off, find the layout's keys, bind the missing characters."""
        if self._libraries is None or self._display is None:
            return
        x11, display = self._libraries[0], self._display
        self._open_scans += 1
        chars = [key.char for key in keys if isinstance(key, UnicodeText)]
        if not chars:
            return
        group, locked_modifiers = _xkb_state(x11, display)
        # Xlib capitalises a looked-up letter while Caps Lock is on, even on a spare key code.
        if not self._relock_caps and locked_modifiers & LOCK_MASK:
            x11.XkbLockModifiers(display, XKB_USE_CORE_KBD, LOCK_MASK, 0)
            self._relock_caps = True
        keymap = _keymap(x11, display)
        if any(keymap.get(code, [0])[:1] != [_keysym(char)] for char, code in self._bound.items()):
            self._bound.clear()  # the keymap was reloaded (setxkbmap): the bindings are gone
            self._spare_keycodes = None
        self._layout_keys = _layout_keys(
            keymap, group, self._keysym_to_utf32, set(self._bound.values())
        )
        # Bound before the first key: binding between keys lost characters at 0 ms delay.
        for char in chars:
            if char in self._layout_keys:
                continue
            if char not in self._bound and self._spare_keycodes == []:
                break  # reusing a key code is left to `press`, as late as possible
            self._bind_spare_keycode(x11, display, char)
        x11.XSync(display, 0)

    def end_scan(self) -> None:
        if self._libraries is None or self._display is None or not self._open_scans:
            return
        self._open_scans -= 1
        if not self._open_scans and self._relock_caps:
            x11, display = self._libraries[0], self._display
            x11.XkbLockModifiers(display, XKB_USE_CORE_KBD, LOCK_MASK, LOCK_MASK)
            x11.XFlush(display)
            self._relock_caps = False

    def press(self, key: Key) -> bool:
        if self._libraries is None or self._display is None:
            return False
        (x11, xtst), display = self._libraries, self._display
        if isinstance(key, UnicodeText):
            layout_key = self._layout_keys.get(key.char)
            if layout_key is not None:
                keycode, shift = layout_key
            else:
                keycode, shift = self._bind_spare_keycode(x11, display, key.char), False
        else:
            keycode, shift = KEYCODES.get(key.usage), key.shift
        if keycode is None:
            return False
        events = [(keycode, True), (keycode, False)]
        if shift:
            shift_keycode = KEYCODES[LEFT_SHIFT]
            events = [(shift_keycode, True), *events, (shift_keycode, False)]
        results = [xtst.XTestFakeKeyEvent(display, code, down, 0) for code, down in events]
        x11.XFlush(display)
        return all(results)

    def _bind_spare_keycode(self, x11: ctypes.CDLL, display: int, char: str) -> int | None:
        """Map a spare keycode to `char`'s keysym, as xdotool does, and return it.

        Each character keeps its keycode: an app looks a key up in the keymap as it is when the
        app gets to the event, so rebinding the keycode would change what a late app reads.
        """
        if (keycode := self._bound.pop(char, None)) is not None:
            self._bound[char] = keycode  # now the most recently used
            return keycode
        if self._spare_keycodes is None:
            self._spare_keycodes = _find_unused_keycodes(x11, display)
        if self._spare_keycodes:
            keycode = self._spare_keycodes.pop()
        elif self._bound:
            # ponytail: more missing characters than spare keycodes (19 on Xvfb): take the least
            # recently used one's, which an app still that far behind reads as the new character.
            keycode = self._bound.pop(next(iter(self._bound)))
        else:
            return None
        keysym = _keysym(char)
        # On both levels: a lone letter keysym types the lowercase letter unless Shift is held.
        x11.XChangeKeyboardMapping(display, keycode, 2, (ctypes.c_ulong * 2)(keysym, keysym), 1)
        x11.XSync(display, 0)
        self._bound[char] = keycode
        return keycode

    def _unbind_all(self) -> None:
        """Clear the spare keycodes, so the next emupos finds them unused.

        ponytail: at exit, not after each scan (an app that reads late would lose characters);
        a killed emupos leaves them bound until `setxkbmap` reloads the keymap.
        """
        if self._libraries is None or self._display is None:
            return
        x11, display = self._libraries[0], self._display
        for keycode in self._bound.values():
            x11.XChangeKeyboardMapping(display, keycode, 1, (ctypes.c_ulong * 1)(0), 1)
        self._bound.clear()
        x11.XSync(display, 0)


def _keysym(char: str) -> int:
    code_point = ord(char)
    latin1 = 0x20 <= code_point <= 0x7E or 0xA0 <= code_point <= 0xFF
    return code_point if latin1 else 0x01000000 | code_point


def _xkb_state(x11: ctypes.CDLL, display: int) -> tuple[int, int]:
    """(active group, locked modifiers) of the core keyboard; (0, 0) without XKB."""
    state = ctypes.create_string_buffer(32)  # XkbStateRec: group is byte 0, locked_mods byte 9
    x11.XkbGetState(display, XKB_USE_CORE_KBD, state)
    return state.raw[0], state.raw[9]


def _keymap(x11: ctypes.CDLL, display: int) -> dict[int, list[int]]:
    """Keycode -> its keysyms in the core keymap: group 1's two levels, then group 2's, ..."""
    lowest, highest, per_keycode = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    x11.XDisplayKeycodes(display, ctypes.byref(lowest), ctypes.byref(highest))
    count = highest.value - lowest.value + 1
    keysyms = x11.XGetKeyboardMapping(display, lowest.value, count, ctypes.byref(per_keycode))
    if not keysyms:
        return {}
    try:
        width = per_keycode.value
        return {
            lowest.value + index: keysyms[index * width : (index + 1) * width]
            for index in range(count)
        }
    finally:
        x11.XFree(keysyms)


def _find_unused_keycodes(x11: ctypes.CDLL, display: int) -> list[int]:
    """The keycodes with no keysyms in the current keymap, lowest first."""
    return [keycode for keycode, keysyms in _keymap(x11, display).items() if not any(keysyms)]


def _layout_keys(
    keymap: dict[int, list[int]],
    group: int,
    keysym_to_utf32: Callable[[int], int] | None,
    skip: set[int],
) -> dict[str, tuple[int, bool]]:
    """Characters on the active group's first and Shift levels -> (keycode, needs Shift).

    Keysyms are turned into characters, so a layout's legacy keysyms (`Arabic_kaf`) count too.
    """
    if keysym_to_utf32 is None or group > 1:  # the core keymap shows the first two groups only
        return {}
    found: dict[str, tuple[int, bool]] = {}
    for level in (0, 1):
        column = 2 * group + level
        for keycode, keysyms in keymap.items():
            keysym = keysyms[column] if column < len(keysyms) else 0
            if keycode in skip or not keysym or keysym in _KEYPAD_KEYSYMS:
                continue
            if code_point := keysym_to_utf32(keysym):
                found.setdefault(chr(code_point), (keycode, level == 1))
    return found
