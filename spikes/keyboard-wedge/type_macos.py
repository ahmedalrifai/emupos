# /// script
# requires-python = ">=3.13"
# dependencies = ["pyobjc-framework-Quartz", "pyobjc-framework-ApplicationServices"]
# ///
"""macOS keyboard-wedge spike (task 1.2): do CGEventPost keystrokes look like a USB
barcode scanner to browsers and native apps, and which app needs Accessibility?

    uv run spikes/keyboard-wedge/type_macos.py --dry-run          # print events, post nothing
    uv run spikes/keyboard-wedge/type_macos.py                    # types 5901234123457 + Enter
    uv run spikes/keyboard-wedge/type_macos.py "Ab1-" --delay-ms 25
    uv run spikes/keyboard-wedge/type_macos.py "كود-42" --unicode

Default mode posts US ANSI virtual key codes (kVK_ANSI_* from Carbon HIToolbox Events.h)
with an explicit Shift key, like a scanner's physical key presses: the characters that
appear depend on the active input source. --unicode attaches the text to each event with
CGEventKeyboardSetUnicodeString instead (key code 0), independent of the layout.

Two permission checks are printed: HIServices AXIsProcessTrustedWithOptions (needs
pyobjc-framework-ApplicationServices) and Quartz CGPreflightPostEventAccess (Quartz only).
macOS attributes the permission to the "responsible" app, usually the terminal that
started Python, so the script also prints the parent .app bundle it finds.
--dry-run also checks the key code table against the current layout (valid on US/ABC).
"""

import argparse
import os
import subprocess
import sys
import time

import HIServices
import Quartz

# (key code, character, character with Shift) on the US ANSI layout.
US_ANSI_KEYS = [
    (0x00, "a", "A"), (0x01, "s", "S"), (0x02, "d", "D"), (0x03, "f", "F"),
    (0x04, "h", "H"), (0x05, "g", "G"), (0x06, "z", "Z"), (0x07, "x", "X"),
    (0x08, "c", "C"), (0x09, "v", "V"), (0x0B, "b", "B"), (0x0C, "q", "Q"),
    (0x0D, "w", "W"), (0x0E, "e", "E"), (0x0F, "r", "R"), (0x10, "y", "Y"),
    (0x11, "t", "T"), (0x12, "1", "!"), (0x13, "2", "@"), (0x14, "3", "#"),
    (0x15, "4", "$"), (0x16, "6", "^"), (0x17, "5", "%"), (0x18, "=", "+"),
    (0x19, "9", "("), (0x1A, "7", "&"), (0x1B, "-", "_"), (0x1C, "8", "*"),
    (0x1D, "0", ")"), (0x1E, "]", "}"), (0x1F, "o", "O"), (0x20, "u", "U"),
    (0x21, "[", "{"), (0x22, "i", "I"), (0x23, "p", "P"), (0x25, "l", "L"),
    (0x26, "j", "J"), (0x27, "'", '"'), (0x28, "k", "K"), (0x29, ";", ":"),
    (0x2A, "\\", "|"), (0x2B, ",", "<"), (0x2C, "/", "?"), (0x2D, "n", "N"),
    (0x2E, "m", "M"), (0x2F, ".", ">"), (0x31, " ", " "), (0x32, "`", "~"),
]  # fmt: skip
KEY_RETURN, KEY_TAB, KEY_SHIFT = 0x24, 0x30, 0x38
SUFFIX_KEYS = {"enter": KEY_RETURN, "tab": KEY_TAB, "none": None}

KEY_FOR_CHAR: dict[str, tuple[int, bool]] = {}
for _code, _plain, _shifted in US_ANSI_KEYS:
    KEY_FOR_CHAR.setdefault(_plain, (_code, False))
    KEY_FOR_CHAR.setdefault(_shifted, (_code, True))

# An event to post: (key code, key down?, Shift flag?, unicode text or None)
Event = tuple[int, bool, bool, str | None]


def keystroke_events(text: str, unicode: bool, suffix: str) -> list[list[Event]]:
    """One list of events per keystroke; the inter-key delay goes between keystrokes."""
    keystrokes = []
    for char in text:
        if unicode:
            keystrokes.append([(0, True, False, char), (0, False, False, char)])
            continue
        if char not in KEY_FOR_CHAR:
            sys.exit(f"{char!r} is not on the US keyboard; use --unicode")
        code, shift = KEY_FOR_CHAR[char]
        press = [(code, True, shift, None), (code, False, shift, None)]
        if shift:
            press = [(KEY_SHIFT, True, True, None), *press, (KEY_SHIFT, False, False, None)]
        keystrokes.append(press)
    if (suffix_code := SUFFIX_KEYS[suffix]) is not None:
        keystrokes.append([(suffix_code, True, False, None), (suffix_code, False, False, None)])
    return keystrokes


def make_event(code: int, down: bool, shift: bool, text: str | None):
    event = Quartz.CGEventCreateKeyboardEvent(None, code, down)
    Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskShift if shift else 0)
    if text is not None:
        utf16_units = len(text.encode("utf-16-le")) // 2
        Quartz.CGEventKeyboardSetUnicodeString(event, utf16_units, text)
    return event


def layout_char(code: int) -> str:
    """The character the current input source gives this key code (no modifiers)."""
    _, chars = Quartz.CGEventKeyboardGetUnicodeString(
        Quartz.CGEventCreateKeyboardEvent(None, code, True), 4, None, None
    )
    return chars


def responsible_app() -> str:
    """Walk up the parent processes to the first .app bundle (usually the terminal)."""
    pid = os.getppid()
    for _ in range(20):
        out = subprocess.run(
            ["/bin/ps", "-o", "ppid=,comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        if not out:
            break
        ppid, _, command = out.partition(" ")
        if ".app/" in command:
            return command[: command.index(".app/") + 4]
        if int(ppid) <= 1:
            break
        pid = int(ppid)
    return "(no .app found among parent processes)"


def report_permissions(prompt: bool) -> bool:
    options = {HIServices.kAXTrustedCheckOptionPrompt: prompt}
    ax_trusted = bool(HIServices.AXIsProcessTrustedWithOptions(options))
    post_access = bool(Quartz.CGPreflightPostEventAccess())
    print(f"AXIsProcessTrustedWithOptions: {ax_trusted}")
    print(f"CGPreflightPostEventAccess:    {post_access}")
    print(f"responsible app (guess):       {responsible_app()}")
    bundle_id = os.environ.get("__CFBundleIdentifier")  # noqa: SIM112 (macOS spells it so)
    print(f"TERM_PROGRAM / bundle id:      {os.environ.get('TERM_PROGRAM')} / {bundle_id}")
    print(f"python executable:             {os.path.realpath(sys.executable)}")
    if not (ax_trusted and post_access):
        print(
            "NOT TRUSTED: open System Settings > Privacy & Security > Accessibility and enable\n"
            "the responsible app above (then restart it). Keystrokes would be dropped silently."
        )
    return ax_trusted and post_access


def dry_run(keystrokes: list[list[Event]]) -> None:
    mismatches = 0
    for code, plain, _ in US_ANSI_KEYS:
        if (actual := layout_char(code)) != plain:
            mismatches += 1
            print(
                f"layout check: key 0x{code:02x} expected {plain!r}, current layout gives {actual!r}"
            )
    print(
        f"layout check: {len(US_ANSI_KEYS) - mismatches}/{len(US_ANSI_KEYS)} US key codes match the current input source"
    )
    for number, keystroke in enumerate(keystrokes, start=1):
        for code, down, shift, text in keystroke:
            make_event(code, down, shift, text)  # proves the event can be built
            action = "down" if down else "up  "
            extra = f" unicode={text!r}" if text is not None else ""
            print(f"  keystroke {number:2}: key 0x{code:02x} {action} shift={shift}{extra}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text", nargs="?", default="5901234123457")
    parser.add_argument("--unicode", action="store_true", help="type exact characters")
    parser.add_argument("--suffix", choices=list(SUFFIX_KEYS), default="enter")
    parser.add_argument("--delay-ms", type=float, default=10, help="delay between keystrokes")
    parser.add_argument("--countdown", type=int, default=3, help="seconds to focus the target")
    parser.add_argument("--dry-run", action="store_true", help="print the events, post nothing")
    parser.add_argument(
        "--prompt", action="store_true", help="let macOS show its permission prompt"
    )
    args = parser.parse_args()

    keystrokes = keystroke_events(args.text, args.unicode, args.suffix)
    trusted = report_permissions(args.prompt)
    if args.dry_run:
        dry_run(keystrokes)
        return
    if not trusted:
        sys.exit(2)
    for remaining in range(args.countdown, 0, -1):
        print(f"typing in {remaining}... focus the target field")
        time.sleep(1)
    started = time.perf_counter()
    for keystroke in keystrokes:
        for spec in keystroke:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, make_event(*spec))
        time.sleep(args.delay_ms / 1000)
    elapsed = (time.perf_counter() - started) * 1000
    print(
        f"posted {len(keystrokes)} keystrokes in {elapsed:.0f} ms (CGEventPost reports no errors)"
    )


if __name__ == "__main__":
    main()
