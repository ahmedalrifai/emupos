# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Linux X11 keyboard-wedge spike (task 1.2): do XTest keystrokes look like a USB barcode
scanner to browsers and native apps?

    uv run spikes/keyboard-wedge/type_x11.py --dry-run
    uv run spikes/keyboard-wedge/type_x11.py                 # types 5901234123457 + Enter
    uv run spikes/keyboard-wedge/type_x11.py "Ab1-" --delay-ms 25

Uses libX11 + libXtst through ctypes: XOpenDisplay, XKeysymToKeycode, XTestFakeKeyEvent,
XFlush. Printable ASCII only (keysym == character code), Shift_L pressed for characters
that need Shift on a US keyboard.

Known limitation (record it, don't fix it here): XKeysymToKeycode looks the character up
in the CURRENT keymap. A real scanner sends the physical US key, so on a layout that moves
letters (AZERTY) or has no Latin group at all, this differs from real hardware.
No --unicode mode on X11 in this spike.
"""

import argparse
import ctypes
import ctypes.util
import os
import sys
import time

XK_TAB, XK_RETURN, XK_SHIFT_L = 0xFF09, 0xFF0D, 0xFFE1
SUFFIX_KEYSYMS = {"enter": XK_RETURN, "tab": XK_TAB, "none": None}
US_SHIFTED = set('~!@#$%^&*()_+{}|:"<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ')


def check_session(try_xwayland: bool) -> None:
    session = os.environ.get("XDG_SESSION_TYPE", "")
    if session == "wayland" and not try_xwayland:
        sys.exit(
            "This is a Wayland session: keyboard mode needs X11 (use mode: serial instead).\n"
            "Pass --try-xwayland to see whether XWayland windows receive the keys anyway."
        )
    if not os.environ.get("DISPLAY"):
        sys.exit("No DISPLAY: keyboard mode needs an X11 session (use mode: serial instead).")


def load_libraries():
    x11_path, xtst_path = ctypes.util.find_library("X11"), ctypes.util.find_library("Xtst")
    if not x11_path:
        sys.exit("libX11 not found (Debian/Ubuntu: sudo apt install libx11-6).")
    if not xtst_path:
        sys.exit(
            "libXtst not found. Debian/Ubuntu: sudo apt install libxtst6; "
            "Fedora: sudo dnf install libXtst; Arch: sudo pacman -S libxtst."
        )
    x11, xtst = ctypes.CDLL(x11_path), ctypes.CDLL(xtst_path)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xtst.XTestQueryExtension.argtypes = [ctypes.c_void_p, *[ctypes.POINTER(ctypes.c_int)] * 4]
    xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    return x11, xtst


def keystrokes_for(text: str, suffix: str) -> list[tuple[int, bool]]:
    """(keysym, needs Shift) per keystroke."""
    keystrokes = []
    for char in text:
        if not " " <= char <= "~":
            sys.exit(f"{char!r} is not printable ASCII; this X11 spike has no unicode mode")
        keystrokes.append((ord(char), char in US_SHIFTED))  # Latin-1 keysym == code point
    if (suffix_keysym := SUFFIX_KEYSYMS[suffix]) is not None:
        keystrokes.append((suffix_keysym, False))
    return keystrokes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text", nargs="?", default="5901234123457")
    parser.add_argument("--suffix", choices=list(SUFFIX_KEYSYMS), default="enter")
    parser.add_argument("--delay-ms", type=float, default=10, help="delay between keystrokes")
    parser.add_argument("--countdown", type=int, default=3, help="seconds to focus the target")
    parser.add_argument("--dry-run", action="store_true", help="print the events, send nothing")
    parser.add_argument("--try-xwayland", action="store_true")
    args = parser.parse_args()

    keystrokes = keystrokes_for(args.text, args.suffix)
    check_session(args.try_xwayland)
    x11, xtst = load_libraries()
    display = x11.XOpenDisplay(None)
    if not display:
        sys.exit(f"XOpenDisplay failed for DISPLAY={os.environ['DISPLAY']!r}.")
    try:
        ints = [ctypes.c_int() for _ in range(4)]
        if not xtst.XTestQueryExtension(display, *[ctypes.byref(i) for i in ints]):
            sys.exit("The X server has no XTEST extension.")
        print(
            f"XTEST {ints[2].value}.{ints[3].value}, XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE')}"
        )
        shift = x11.XKeysymToKeycode(display, XK_SHIFT_L)
        events = []
        for keysym, needs_shift in keystrokes:
            keycode = x11.XKeysymToKeycode(display, keysym)
            if keycode == 0:
                sys.exit(f"keysym 0x{keysym:04x} is not in the current keymap")
            events.append((keycode, needs_shift))
            print(f"  keysym 0x{keysym:04x} -> keycode {keycode} shift={needs_shift}")
        if args.dry_run:
            return
        for remaining in range(args.countdown, 0, -1):
            print(f"typing in {remaining}... focus the target field")
            time.sleep(1)
        started = time.perf_counter()
        for keycode, needs_shift in events:
            if needs_shift:
                xtst.XTestFakeKeyEvent(display, shift, True, 0)
            xtst.XTestFakeKeyEvent(display, keycode, True, 0)
            xtst.XTestFakeKeyEvent(display, keycode, False, 0)
            if needs_shift:
                xtst.XTestFakeKeyEvent(display, shift, False, 0)
            x11.XFlush(display)
            time.sleep(args.delay_ms / 1000)
        print(f"sent {len(events)} keystrokes in {(time.perf_counter() - started) * 1000:.0f} ms")
    finally:
        x11.XCloseDisplay(display)


if __name__ == "__main__":
    main()
