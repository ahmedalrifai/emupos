"""Linux keyboard: XTest through libX11 and libXtst via ctypes (design D10). X11 only.

Keys are pressed by physical position (evdev key code + 8), not looked up in the current
keymap, so the active layout decides the characters exactly as for a real USB scanner.
Unicode text uses the active layout's own keys where it has the character, and spare key
codes bound to the character otherwise, as `xdotool type` does.
"""

import asyncio
import atexit
import ctypes
import os
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any

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

# Per scan, the longest total wait for the focused app to read the keymap before spare
# keycodes are reused.
REUSE_WAIT_S = 2.0
# After an app reads the keymap: time for it to handle the reply. A keymap change arriving while
# Xlib handles that reply is dropped, and the app keeps typing the old character (seen at 0 ms).
READ_GRACE_S = 0.02
# Root window property of one emupos process: (keycode, keysym) pairs it has bound.
BINDINGS_PREFIX = "_EMUPOS_KEYCODES_"
_XA_CARDINAL = 6
_X_CHANGE_KEYBOARD_MAPPING = 100
_X_GET_KEYBOARD_MAPPING = 101
_XKB_GET_MAP = 8
_RECORD_FROM_CLIENT = 1
_RECORD_START_OF_DATA = 4
_RECORD_ALL_CLIENTS = 3


class _RecordRange8(ctypes.Structure):
    _fields_ = (("first", ctypes.c_ubyte), ("last", ctypes.c_ubyte))


class _RecordRange16(ctypes.Structure):
    _fields_ = (("first", ctypes.c_ushort), ("last", ctypes.c_ushort))


class _RecordExtRange(ctypes.Structure):
    _fields_ = (("ext_major", _RecordRange8), ("ext_minor", _RecordRange16))


class _RecordRange(ctypes.Structure):
    """XRecordRange from X11/extensions/record.h."""

    _fields_ = (
        ("core_requests", _RecordRange8),
        ("core_replies", _RecordRange8),
        ("ext_requests", _RecordExtRange),
        ("ext_replies", _RecordExtRange),
        ("delivered_events", _RecordRange8),
        ("device_events", _RecordRange8),
        ("errors", _RecordRange8),
        ("client_started", ctypes.c_int),
        ("client_died", ctypes.c_int),
    )


class _RecordInterceptData(ctypes.Structure):
    """XRecordInterceptData from X11/extensions/record.h."""

    _fields_ = (
        ("id_base", ctypes.c_ulong),
        ("server_time", ctypes.c_ulong),
        ("client_seq", ctypes.c_ulong),
        ("category", ctypes.c_int),
        ("client_swapped", ctypes.c_int),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
        ("data_len", ctypes.c_ulong),
    )


class _DisplayStart(ctypes.Structure):
    """The first fields of Xlib's Display (`_XPrivDisplay` in Xlib.h; private3 and private4)."""

    _fields_ = (
        ("ext_data", ctypes.c_void_p),
        ("private1", ctypes.c_void_p),
        ("fd", ctypes.c_int),
        ("private2", ctypes.c_int),
        ("proto_major_version", ctypes.c_int),
        ("proto_minor_version", ctypes.c_int),
        ("vendor", ctypes.c_char_p),
        ("resource_base", ctypes.c_ulong),
        ("resource_mask", ctypes.c_ulong),
    )


_RecordCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(_RecordInterceptData))

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
    xid, c_uint = ctypes.c_ulong, ctypes.c_uint
    x11.XDefaultRootWindow.argtypes = [display]
    x11.XDefaultRootWindow.restype = xid
    x11.XCreateSimpleWindow.argtypes = [display, xid, ctypes.c_int, ctypes.c_int]
    x11.XCreateSimpleWindow.argtypes += [c_uint, c_uint, c_uint, xid, xid]
    x11.XCreateSimpleWindow.restype = xid
    x11.XInternAtom.argtypes = [display, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = xid
    x11.XGetAtomName.argtypes = [display, xid]
    x11.XGetAtomName.restype = ctypes.c_void_p  # freed with XFree
    x11.XSetSelectionOwner.argtypes = [display, xid, xid, xid]
    x11.XGetSelectionOwner.argtypes = [display, xid]
    x11.XGetSelectionOwner.restype = xid
    x11.XListProperties.argtypes = [display, xid, c_int_p]
    x11.XListProperties.restype = c_ulong_p
    x11.XGetWindowProperty.argtypes = [display, xid, xid, ctypes.c_long, ctypes.c_long]
    x11.XGetWindowProperty.argtypes += [ctypes.c_int, xid, c_ulong_p, c_int_p, c_ulong_p]
    x11.XGetWindowProperty.argtypes += [c_ulong_p, ctypes.POINTER(ctypes.c_void_p)]
    x11.XChangeProperty.argtypes = [display, xid, xid, xid, ctypes.c_int, ctypes.c_int]
    x11.XChangeProperty.argtypes += [ctypes.c_void_p, ctypes.c_int]
    x11.XDeleteProperty.argtypes = [display, xid, xid]
    x11.XGetInputFocus.argtypes = [display, c_ulong_p, c_int_p]
    x11.XQueryExtension.argtypes = [display, ctypes.c_char_p, c_int_p, c_int_p, c_int_p]
    xtst.XTestQueryExtension.argtypes = [display, c_int_p, c_int_p, c_int_p, c_int_p]
    xtst.XTestFakeKeyEvent.argtypes = [display, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    xtst.XRecordQueryVersion.argtypes = [display, c_int_p, c_int_p]
    xtst.XRecordAllocRange.restype = ctypes.POINTER(_RecordRange)
    xtst.XRecordCreateContext.argtypes = [display, ctypes.c_int, c_ulong_p, ctypes.c_int]
    xtst.XRecordCreateContext.argtypes += [
        ctypes.POINTER(ctypes.POINTER(_RecordRange)),
        ctypes.c_int,
    ]
    xtst.XRecordCreateContext.restype = xid
    xtst.XRecordEnableContextAsync.argtypes = [display, xid, _RecordCallback, ctypes.c_void_p]
    xtst.XRecordProcessReplies.argtypes = [display]
    xtst.XRecordFreeData.argtypes = [ctypes.POINTER(_RecordInterceptData)]
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
        self._resource_base = self._resource_mask = 0  # this connection's X resource IDs
        self._bindings_atom = 0  # the root property listing this process's bindings
        self._pressed_at: dict[str, float] = {}  # char -> when its spare keycode was pressed
        self._watch: KeymapWatch | None = None
        self._watch_started = False
        self._changes = 0  # keymap changes since the watch started
        self._wait_left = REUSE_WAIT_S  # of this scan

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
        self._resource_base, self._resource_mask = _resource_ids(display)
        # The X server drops this selection when emupos's connection closes, even on SIGKILL:
        # a later emupos then knows that this process's bindings are left over.
        # ponytail: one atom per emupos process; X never frees atoms.
        name = f"{BINDINGS_PREFIX}{uuid.uuid4().hex}"
        self._bindings_atom = x11.XInternAtom(display, name.encode(), 0)
        root = x11.XDefaultRootWindow(display)
        owner = x11.XCreateSimpleWindow(display, root, 0, 0, 1, 1, 0, 0, 0)
        x11.XSetSelectionOwner(display, self._bindings_atom, owner, 0)
        _clear_dead_bindings(x11, display, root)
        atexit.register(self._unbind_all)

    def start_scan(self, keys: Sequence[Key]) -> None:
        """For Unicode text: Caps Lock off, find the layout's keys, bind the missing characters."""
        if self._libraries is None or self._display is None:
            return
        x11, display = self._libraries[0], self._display
        self._open_scans += 1
        self._wait_left = REUSE_WAIT_S
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
            self._record_bindings(x11, display)
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

    async def prepare_key(self, key: Key) -> None:
        """Before a spare keycode is reused, wait until the focused app has read the keymap.

        Until then the app may not have handled the key that the keycode typed last, and would
        read it as the new character. Without X RECORD or a focused app, wait until that key
        was pressed REUSE_WAIT_S ago instead. A scan waits REUSE_WAIT_S at most in total; after
        that, keycodes are reused without waiting.
        """
        if not self._reuse_needed(key) or self._libraries is None or self._display is None:
            return
        x11, display = self._libraries[0], self._display
        client = _focused_client(x11, display, self._resource_mask)
        oldest = next(iter(self._bound))
        started = time.monotonic()
        try:
            while time.monotonic() - started < self._wait_left:
                if self._watch is not None and client is not None:
                    self._watch.poll()
                    if self._watch.has_read(client, self._changes):
                        await asyncio.sleep(READ_GRACE_S)
                        return
                elif time.monotonic() - self._pressed_at.get(oldest, 0.0) >= REUSE_WAIT_S:
                    return
                await asyncio.sleep(0.005)
        finally:
            self._wait_left = max(0.0, self._wait_left - (time.monotonic() - started))

    def _reuse_needed(self, key: Key) -> bool:
        return (
            isinstance(key, UnicodeText)
            and key.char not in self._layout_keys
            and key.char not in self._bound
            and self._spare_keycodes == []
            and bool(self._bound)
        )

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
                self._pressed_at[key.char] = time.monotonic()
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
            if not self._watch_started and self._libraries is not None:
                self._watch_started = True
                xtst = self._libraries[1]
                self._watch = KeymapWatch.start(x11, xtst, display, self._resource_base)
                self._changes = 0
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
        self._changes += 1
        self._bound[char] = keycode
        self._record_bindings(x11, display)
        x11.XSync(display, 0)
        return keycode

    def _record_bindings(self, x11: ctypes.CDLL, display: int) -> None:
        """Keep this process's root property in step with its bindings (for _clear_dead_bindings)."""
        pairs = [
            value for char, keycode in self._bound.items() for value in (keycode, _keysym(char))
        ]
        values = (ctypes.c_ulong * len(pairs))(*pairs)
        root = x11.XDefaultRootWindow(display)
        x11.XChangeProperty(
            display, root, self._bindings_atom, _XA_CARDINAL, 32, 0, values, len(pairs)
        )

    def _unbind_all(self) -> None:
        """Clear the spare keycodes, so the next emupos finds them unused.

        ponytail: at exit, not after each scan (an app that reads late would lose characters);
        a killed emupos leaves them to the next emupos (_clear_dead_bindings).
        """
        if self._libraries is None or self._display is None:
            return
        x11, display = self._libraries[0], self._display
        for keycode in self._bound.values():
            x11.XChangeKeyboardMapping(display, keycode, 1, (ctypes.c_ulong * 1)(0), 1)
        self._bound.clear()
        x11.XDeleteProperty(display, x11.XDefaultRootWindow(display), self._bindings_atom)
        x11.XSync(display, 0)


class KeymapWatch:
    """Which X clients have read the keymap since emupos's latest change (X RECORD extension).

    RECORD reports the requests of every client in the order the server handles them, on a
    second connection: emupos's own keymap changes, and the keymap reads of other clients.
    """

    def __init__(self, own_client: int, xkb_opcode: int, poll: Callable[[], None]) -> None:
        self.own_client = own_client
        self.xkb_opcode = xkb_opcode
        self.poll = poll
        self.started = False
        self.changes = 0  # emupos's keymap changes reported so far
        self.read_after: dict[int, int] = {}  # client -> changes reported before its last read
        self._keep: object = None  # the ctypes callback must outlive the recording

    def note(self, client: int, category: int, opcode: int, minor: int) -> None:
        if category == _RECORD_START_OF_DATA:
            self.started = True
        elif category != _RECORD_FROM_CLIENT:
            return
        elif client == self.own_client:
            self.changes += opcode == _X_CHANGE_KEYBOARD_MAPPING
        elif opcode == _X_GET_KEYBOARD_MAPPING or (opcode, minor) == (
            self.xkb_opcode,
            _XKB_GET_MAP,
        ):
            self.read_after[client] = self.changes

    def has_read(self, client: int, changes: int) -> bool:
        """Whether `client` read the keymap after emupos's first `changes` changes."""
        return self.read_after.get(client, -1) >= changes

    @classmethod
    def start(
        cls, x11: ctypes.CDLL, xtst: ctypes.CDLL, display: int, own_client: int
    ) -> "KeymapWatch | None":
        """Record keymap requests on a second connection; None without RECORD."""
        data_display: int | None = x11.XOpenDisplay(None)
        if not data_display:
            return None
        major, minor, xkb_opcode, first_event, first_error = (ctypes.c_int() for _ in range(5))
        if not xtst.XRecordQueryVersion(data_display, ctypes.byref(major), ctypes.byref(minor)):
            x11.XCloseDisplay(data_display)
            return None
        x11.XQueryExtension(
            data_display,
            b"XKEYBOARD",
            ctypes.byref(xkb_opcode),
            ctypes.byref(first_event),
            ctypes.byref(first_error),
        )
        watched = xtst.XRecordAllocRange()
        watched.contents.core_requests.first = _X_CHANGE_KEYBOARD_MAPPING
        watched.contents.core_requests.last = _X_GET_KEYBOARD_MAPPING
        if xkb_opcode.value:
            ext = watched.contents.ext_requests
            ext.ext_major.first = ext.ext_major.last = xkb_opcode.value
            ext.ext_minor.first = ext.ext_minor.last = _XKB_GET_MAP
        all_clients = (ctypes.c_ulong * 1)(_RECORD_ALL_CLIENTS)
        # RECORD reports on a connection of its own; the main one controls the recording.
        # ponytail: the data connection stays open for the whole run, like the main one.
        context = xtst.XRecordCreateContext(display, 0, all_clients, 1, ctypes.byref(watched), 1)
        x11.XFree(watched)
        if not context:
            x11.XCloseDisplay(data_display)
            return None
        x11.XSync(display, 0)
        watch = cls(own_client, xkb_opcode.value, lambda: xtst.XRecordProcessReplies(data_display))

        def on_data(_closure: object, data: Any) -> None:  # POINTER(_RecordInterceptData)
            record = data.contents
            request = record.data if record.data_len else None
            opcode, minor = (request[0], request[1]) if request else (0, 0)
            watch.note(record.id_base, record.category, opcode, minor)
            xtst.XRecordFreeData(data)

        callback = _RecordCallback(on_data)
        watch._keep = callback
        if not xtst.XRecordEnableContextAsync(data_display, context, callback, None):
            return None
        deadline = time.monotonic() + 1
        while not watch.started and time.monotonic() < deadline:  # changes before this go unseen
            watch.poll()
            time.sleep(0.001)
        return watch if watch.started else None


def _resource_ids(display: int) -> tuple[int, int]:
    """(resource base, resource mask) of a connection: a client's windows are base | n."""
    start = _DisplayStart.from_address(display)
    return start.resource_base, start.resource_mask


def _focused_client(x11: ctypes.CDLL, display: int, resource_mask: int) -> int | None:
    """The resource base of the client owning the focused window; None for none or the root."""
    window, revert_to = ctypes.c_ulong(), ctypes.c_int()
    x11.XGetInputFocus(display, ctypes.byref(window), ctypes.byref(revert_to))
    client = window.value & ~resource_mask
    return client if window.value > 1 and client else None  # 0: None, 1: PointerRoot


def _clear_dead_bindings(x11: ctypes.CDLL, display: int, root: int) -> None:
    """Unbind the spare keycodes that killed emupos processes left behind.

    Each emupos lists its bindings in a root property and owns a selection of the same name.
    A property whose selection has no owner belongs to a process that is gone. A keycode is
    only cleared while it still holds the recorded keysym.
    """
    keymap: dict[int, list[int]] | None = None
    for atom in _list_properties(x11, display, root):
        if not _atom_name(x11, display, atom).startswith(BINDINGS_PREFIX):
            continue
        if x11.XGetSelectionOwner(display, atom):
            continue  # that emupos is still running
        keymap = keymap if keymap is not None else _keymap(x11, display)
        values = _read_cardinals(x11, display, root, atom)
        for keycode, keysym in zip(values[::2], values[1::2], strict=False):
            if keymap.get(keycode, [0])[:1] == [keysym]:
                x11.XChangeKeyboardMapping(display, keycode, 1, (ctypes.c_ulong * 1)(0), 1)
        x11.XDeleteProperty(display, root, atom)
    x11.XSync(display, 0)


def _list_properties(x11: ctypes.CDLL, display: int, window: int) -> list[int]:
    count = ctypes.c_int()
    atoms = x11.XListProperties(display, window, ctypes.byref(count))
    if not atoms:
        return []
    try:
        return atoms[: count.value]
    finally:
        x11.XFree(atoms)


def _atom_name(x11: ctypes.CDLL, display: int, atom: int) -> str:
    name = x11.XGetAtomName(display, atom)
    if not name:
        return ""
    try:
        return ctypes.string_at(name).decode(errors="replace")
    finally:
        x11.XFree(name)


def _read_cardinals(x11: ctypes.CDLL, display: int, window: int, atom: int) -> list[int]:
    kind, size, count, remaining = (
        ctypes.c_ulong(),
        ctypes.c_int(),
        ctypes.c_ulong(),
        ctypes.c_ulong(),
    )
    data = ctypes.c_void_p()
    x11.XGetWindowProperty(
        display,
        window,
        atom,
        0,
        1024,
        0,
        _XA_CARDINAL,
        ctypes.byref(kind),
        ctypes.byref(size),
        ctypes.byref(count),
        ctypes.byref(remaining),
        ctypes.byref(data),
    )
    if not data.value:
        return []
    try:
        if size.value != 32:
            return []
        return ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[: count.value]
    finally:
        x11.XFree(data)


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
