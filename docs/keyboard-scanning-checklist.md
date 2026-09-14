# Keyboard scanning: manual verification checklist

Typing into other windows cannot run in CI, so keyboard-mode scanning is checked by hand before a release that touches `src/emupos/scanner/` or `src/emupos/transports/keyboard/`. Serial-mode scans are covered by automated tests and are not part of this checklist.

Record the OS version, desktop session, apps and the result of each item in the pull request.

## Setup

`emupos.yaml`:

```yaml
schema: 1
devices:
  - id: lane1
    type: scanner
    mode: keyboard
```

Start `emupos run` in one terminal and run the scan commands from another.

Targets:

- a browser with `spikes/keyboard-wedge/keylogger.html` open: it logs `key`, `code`, `shiftKey` and the time between keys;
- a native text field: TextEdit (macOS), gedit or another GTK editor (Linux), Notepad (Windows).

For every scan: run the command, then click into the target during the 3-second countdown.

## Every OS

- [ ] `emupos doctor` passes its keyboard checks.
- [ ] `emupos scan 5901234123457`: a countdown is shown, `5901234123457` then Enter arrive in both targets, and the command exits with status 0.
- [ ] `emupos scan 5901234123457` and leave the terminal focused (macOS, X11): the command exits with status 1 saying the terminal still has keyboard focus, and nothing is typed. Repeat inside tmux.
- [ ] `emupos scan "Ab1-"`: the key logger shows `ShiftLeft`, then `KeyA` with Shift (`A`), `KeyB`, `Digit1`, `Minus`, `Enter`.
- [ ] `suffix: tab` in the configuration (restart `emupos run`), `emupos scan 123`: `1 2 3` then `Tab`.
- [ ] `suffix: none`: `emupos scan 123` types `123` and nothing after it.
- [ ] `inter_key_delay_ms: 25`: `emupos scan 123`: every delta in the key logger is at least 25 ms.
- [ ] `emupos scan "كود-42" --unicode`: both targets receive exactly `كود-42`, then Enter.
- [ ] `emupos scan "كود42"` without `--unicode`: exits with status 1, the fix mentions `--unicode`, nothing is typed.
- [ ] `emupos scan 111 --countdown 10`, then `emupos scan 222` during the countdown: the second is refused with "a scan is already in progress on lane1"; only `111` and Enter arrive.
- [ ] Non-US layout, Arabic: switch the target window to an Arabic keyboard layout, `emupos scan ABC123`: the targets receive the characters the Arabic layout puts on the A, B, C, 1, 2 and 3 keys, not `ABC123` (compare by pressing those keys yourself). The key logger's `code` values are still `KeyA`, `KeyB`, `KeyC`, `Digit1`, `Digit2`, `Digit3`.
- [ ] Non-US layout, French AZERTY: `emupos scan a1`: the targets receive `q&`, as the US A and 1 keys are Q and & on AZERTY.
- [ ] With the non-US layout still active, `emupos scan ABC123 --unicode`: exactly `ABC123`.
- [ ] Optional, with a real USB scanner in keyboard mode: scan the same barcode into the key logger and compare `code` values and timing with the emupos scan.

## macOS

- [ ] Accessibility not granted for the terminal: `emupos scan 123` is refused; the message names System Settings > Privacy & Security > Accessibility and the terminal app, and nothing is typed.
- [ ] Grant the permission while `emupos run` keeps running, then scan again: accepted without restarting `emupos run`. Record whether the terminal app had to be quit and reopened first.
- [ ] Revoke the permission while `emupos run` keeps running: the next scan is refused again.
- [ ] Run emupos from a second terminal app that is not allowed (iTerm2, VS Code's terminal, …): the error names that app.
- [ ] Installed with `uv tool install emupos`: the error still names the terminal app.

## Linux (X11)

- [ ] `echo $XDG_SESSION_TYPE` prints `x11`.
- [ ] Arabic layout: `setxkbmap -layout us,ara -option grp:alt_shift_toggle`, switch the target window to Arabic with Alt+Shift, run the Arabic item above. Restore with `setxkbmap us`.
- [ ] `--unicode` into gedit and the browser with the default 10 ms delay and with `inter_key_delay_ms: 0`: every character arrives exactly, in order.
- [ ] Wayland session: `emupos scan 123` is refused and the fix mentions `mode: serial`.
- [ ] `env -u DISPLAY emupos run`: scans are refused and the fix mentions `mode: serial`.
- [ ] Without libXtst (for example a container without `libxtst6`): scans are refused and the fix names libXtst.

The key codes, Shift, Enter and `--unicode` typing can also be checked without a desktop, in a container with a virtual X server:

```sh
docker run --rm -it -v "$PWD/src:/src:ro" python:3.13-slim bash
apt-get update && apt-get install -y --no-install-recommends xvfb x11-xkb-utils xkb-data x11-utils libxtst6
Xvfb :99 & export DISPLAY=:99 XDG_SESSION_TYPE=x11 PYTHONPATH=/src
xev -root -event keyboard &
python -c 'import asyncio
from emupos.transports.keyboard.x11 import X11Keyboard
from emupos.transports.keyboard.keyboard import type_keys
from emupos.transports.keyboard.keys import plan_keys
keyboard = X11Keyboard(); keyboard.check_ready()
print(asyncio.run(type_keys(keyboard, plan_keys("Ab1-", "enter", unicode=False), 10)))'
```

`xev` should print key codes 50 (`Shift_L`), 38 (`A`), 56 (`b`), 10 (`1`), 20 (`minus`) and 36 (`Return`).

## Windows

Pending the Windows injector (task 9.2). Keyboard-mode scans on Windows are refused until then, pointing to serial mode. When it lands, this section adds at least:

- [ ] Every item of "Every OS" in the browser and in Notepad.
- [ ] Notepad started with *Run as administrator* while emupos runs as a normal user: the scan does not arrive, `emupos run` prints a warning naming the privilege-level limitation when Windows reports refused keystrokes, and no `scanner.scan.delivered` event is published.
- [ ] Both emupos and Notepad as administrator: the scan arrives.
