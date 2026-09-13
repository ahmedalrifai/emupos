# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Windows keyboard-wedge spike (task 1.2): do SendInput keystrokes look like a USB
barcode scanner to browsers and native apps?

    uv run spikes/keyboard-wedge/type_windows.py --dry-run         # print events, send nothing
    uv run spikes/keyboard-wedge/type_windows.py                   # types 5901234123457 + Enter
    uv run spikes/keyboard-wedge/type_windows.py "Ab1-" --keys vk --delay-ms 25
    uv run spikes/keyboard-wedge/type_windows.py "كود-42" --unicode

Key codes come from the US layout, loaded with LoadKeyboardLayoutW("00000409") and read
with VkKeyScanExW, so a character is always typed as the key that produces it on a US
keyboard, with Shift where needed. What appears then depends on the target window's
active layout, as with a real scanner. --keys picks what each event carries:

    vk-scan  virtual-key code + its US scan code (default)
    vk       virtual-key code only, scan code 0
    scan     scan code only (KEYEVENTF_SCANCODE): closest to a physical key press

Browsers compute KeyboardEvent.code from the scan code, so compare `code` across the
three modes in keylogger.html. --unicode sends KEYEVENTF_UNICODE events instead.

Each event is sent with its own SendInput call and the script reports how many Windows
accepted. SendInput returns fewer when input is blocked; UIPI (typing into an elevated
window) is often NOT reported, so also check what actually arrived.
"""

import argparse
import ctypes
import sys
import time
from ctypes import wintypes

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
VK_TAB, VK_RETURN, VK_SHIFT = 0x09, 0x0D, 0x10
US_LAYOUT_ID = "00000409"
SUFFIX_VKS = {"enter": VK_RETURN, "tab": VK_TAB, "none": None}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),  # ULONG_PTR
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    # MOUSEINPUT is the largest member; without it sizeof(INPUT) is wrong and SendInput
    # fails with ERROR_INVALID_PARAMETER.
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


def load_user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, wintypes.HKL]
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.HKL]
    user32.MapVirtualKeyExW.restype = wintypes.UINT
    user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
    user32.LoadKeyboardLayoutW.restype = wintypes.HKL
    user32.UnloadKeyboardLayout.argtypes = [wintypes.HKL]
    user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(wintypes.HKL)]
    user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    return user32


def layout_list(user32) -> list[int]:
    count = user32.GetKeyboardLayoutList(0, None)
    buffer = (wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, buffer)
    return [hkl or 0 for hkl in buffer]


def key_event(vk: int, scan: int, flags: int) -> INPUT:
    event = INPUT(type=INPUT_KEYBOARD)
    event.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)
    return event


def key_press(user32, hkl: int, vk: int, keys: str) -> list[INPUT]:
    """Down and up events for one virtual key, in the chosen --keys mode."""
    scan = user32.MapVirtualKeyExW(vk, MAPVK_VK_TO_VSC, hkl)
    if keys == "vk":
        down = key_event(vk, 0, 0)
        up = key_event(vk, 0, KEYEVENTF_KEYUP)
    elif keys == "vk-scan":
        down = key_event(vk, scan, 0)
        up = key_event(vk, scan, KEYEVENTF_KEYUP)
    else:
        down = key_event(0, scan, KEYEVENTF_SCANCODE)
        up = key_event(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP)
    return [down, up]


def keystrokes_for(user32, hkl: int, text: str, args: argparse.Namespace) -> list[list[INPUT]]:
    keystrokes = []
    for char in text:
        if args.unicode:
            units = char.encode("utf-16-le")
            for i in range(0, len(units), 2):
                unit = int.from_bytes(units[i : i + 2], "little")
                keystrokes.append(
                    [
                        key_event(0, unit, KEYEVENTF_UNICODE),
                        key_event(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
                    ]
                )
            continue
        result = user32.VkKeyScanExW(char, hkl)
        vk, shift_state = result & 0xFF, (result >> 8) & 0xFF
        if result == -1 or shift_state & ~1:
            sys.exit(f"{char!r} has no plain or Shift key on the US layout; use --unicode")
        press = key_press(user32, hkl, vk, args.keys)
        if shift_state & 1:
            shift_down, shift_up = key_press(user32, hkl, VK_SHIFT, args.keys)
            press = [shift_down, *press, shift_up]
        keystrokes.append(press)
    if (suffix_vk := SUFFIX_VKS[args.suffix]) is not None:
        keystrokes.append(key_press(user32, hkl, suffix_vk, args.keys))
    return keystrokes


def describe(event: INPUT) -> str:
    ki = event.u.ki
    return f"vk=0x{ki.wVk:02x} scan=0x{ki.wScan:04x} flags=0x{ki.dwFlags:x}"


def foreground_layout(user32) -> str:
    thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    return f"0x{user32.GetKeyboardLayout(thread) or 0:08x}"


def send(user32, keystrokes: list[list[INPUT]], delay_ms: float) -> None:
    sent = accepted = 0
    errors: dict[int, int] = {}
    started = time.perf_counter()
    for keystroke in keystrokes:
        for event in keystroke:
            sent += 1
            if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) == 1:
                accepted += 1
            else:
                code = ctypes.get_last_error()
                errors[code] = errors.get(code, 0) + 1
        time.sleep(delay_ms / 1000)
    elapsed = (time.perf_counter() - started) * 1000
    print(f"SendInput accepted {accepted} of {sent} events in {elapsed:.0f} ms")
    if errors:
        print(f"GetLastError codes (code: count): {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text", nargs="?", default="5901234123457")
    parser.add_argument("--keys", choices=["vk-scan", "vk", "scan"], default="vk-scan")
    parser.add_argument("--unicode", action="store_true", help="type exact characters")
    parser.add_argument("--suffix", choices=list(SUFFIX_VKS), default="enter")
    parser.add_argument("--delay-ms", type=float, default=10, help="delay between keystrokes")
    parser.add_argument("--countdown", type=int, default=3, help="seconds to focus the target")
    parser.add_argument("--dry-run", action="store_true", help="print the events, send nothing")
    args = parser.parse_args()
    if sys.platform != "win32":
        sys.exit("type_windows.py runs on Windows only")

    user32 = load_user32()
    print(f"sizeof(INPUT) = {ctypes.sizeof(INPUT)} (must be 40 on 64-bit Python, 28 on 32-bit)")
    before = layout_list(user32)
    hkl = user32.LoadKeyboardLayoutW(US_LAYOUT_ID, 0) or 0
    if not hkl:
        # With a null handle VkKeyScanExW would silently use the current layout instead.
        sys.exit(f"LoadKeyboardLayoutW({US_LAYOUT_ID!r}) failed (error {ctypes.get_last_error()})")
    print(f"installed layouts: {[f'0x{h:08x}' for h in before]}; US layout handle 0x{hkl:08x}")
    try:
        keystrokes = keystrokes_for(user32, hkl, args.text, args)
        if args.dry_run:
            for number, keystroke in enumerate(keystrokes, start=1):
                for event in keystroke:
                    print(f"  keystroke {number:2}: {describe(event)}")
            return
        for remaining in range(args.countdown, 0, -1):
            print(f"typing in {remaining}... focus the target field")
            time.sleep(1)
        print(f"foreground window layout: {foreground_layout(user32)}")
        send(user32, keystrokes, args.delay_ms)
    finally:
        if hkl not in before:
            print("US layout was not installed before; unloading it again")
            user32.UnloadKeyboardLayout(hkl)


if __name__ == "__main__":
    main()
