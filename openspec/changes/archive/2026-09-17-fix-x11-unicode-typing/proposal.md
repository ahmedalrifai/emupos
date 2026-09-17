## Why

The first Linux run of the keyboard-scanning checklist (issue #24) found that `--unicode` on X11 does not type the exact characters, although the barcode-scanner spec requires it. Capital letters arrive in lowercase, and characters are wrong whenever the target app handles the keys later than emupos types them. The run also found that the checklist's Docker recipe does not run.

All of this reproduces in a `python:3.13-slim` container with Xvfb at `8fc149a`. Follow-up tests of candidate fixes found two more problems:

- Caps Lock turns lowercase into capitals.
- A 0 ms delay can still lose characters.

The same tests showed a fix for each problem found, and a way to make the remaining limit on different characters rarely matter.

## What Changes

- **Characters the active layout has are typed with the layout's own keys.**
  - Only characters the layout lacks borrow a spare key code, as `xdotool type` does.
  - In tests, `كود-42` under an Arabic layout and 62 letters and digits under a US layout needed no spare key codes, and came out exact even with the app paused during the whole scan.
  - Such characters carry the key's position, like a real keyboard. For example, `ش` under Arabic is typed with the A key; browsers were not tested.
- **Capital letters keep their case.** `--unicode` of `ABC123` types `ABC123`, not `abc123`. Today a key bound to a single letter reads as lowercase unless Shift is held.
- **Characters arrive exactly when the target app is behind.**
  - Today every character is typed through one spare key code that is rebound for each character, so an app that reads a key after the rebind gets the later character.
  - `كود-42` came out, for example, as `وووووو` at 0 ms, and as `222222` at 10 ms and 50 ms when the app was paused during the scan.
  - Each missing character of a scan will keep its own spare key code.
- **All missing characters of a scan are mapped before its first key.** In tests, per-character key codes alone still lost characters at 0 ms (6 of 6 runs with 19 characters). Mapping them first made every 0 ms run exact (24 of 24).
- **Caps Lock no longer changes `--unicode` text.**
  - With Caps Lock on, `abc123` came out as `ABC123`.
  - emupos will turn Caps Lock off for a `--unicode` scan and turn it back on afterwards. In tests this gave exact text, including with the app paused and at 0 ms, and Caps Lock was on again after every scan.
  - Scans without `--unicode` still follow Caps Lock, as a real scanner does.
- **The keyboard interface gets start-of-scan and end-of-scan steps.** Mapping before a scan and switching Caps Lock off and on happen there. The macOS and Windows keyboards do nothing in these steps.
- **Spare key codes are released when emupos stops.** Today each emupos process leaves its key code bound, and Xvfb has 19 free key codes, so `--unicode` would eventually stop working. With the change, stopping with Ctrl+C or SIGTERM gives every key code back. A killed emupos (SIGKILL) still leaves them bound.
- **The checklist's Docker recipe runs.** It imports `plan_keys` from `emupos.transports.keyboard.keys`, which does not exist. The module is `emupos.scanner.keys`.
- **`docs/linux-x11.md` explains the new behaviour:**
  - layout keys and spare key codes, and the use of libxkbcommon;
  - the limit of 19 different missing characters per scan on Xvfb;
  - Caps Lock handling;
  - what to do after a killed emupos.

## Non-goals

- **Cleaning up after a killed emupos.** It was tested and works (see design), but costs about 40 lines of X11 code. `setxkbmap` recovers the key codes by hand. This is left for a follow-up.
- **Characters on a key's AltGr level.** They keep using spare key codes.
- **The checklist items that need a real desktop:** browser `code` values, GTK text entry, Wayland, running without libXtst, countdown and focus checks, and a USB scanner. They stay open in #24.
- Filling in the Linux column of `docs/spikes/keyboard-wedge.md`.
- Unicode typing on Windows and macOS. Both attach the character to the key event itself.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `barcode-scanner`: "Exact-character typing" changes as follows:
  - On Linux, characters the active layout has are typed with its keys and carry that key's position.
  - New scenarios cover:
    - capital letters and Caps Lock;
    - the active layout's keys;
    - no inter-key delay, and a target app that handles the keys late;
    - more different missing characters than free key codes;
    - no keyboard changes left after a normal stop.
  - It states the Linux limits: different missing characters per scan, and a killed simulator.

## Impact

- `src/emupos/transports/keyboard/keyboard.py`: `start_scan` and `end_scan` in the `Keyboard` protocol; `type_keys` calls them.
- `src/emupos/transports/keyboard/x11.py`: layout key lookup, spare key code mapping, Caps Lock handling, and releasing spare key codes.
- `src/emupos/transports/keyboard/macos.py` and `windows.py`: empty `start_scan` and `end_scan`.
- Tests: `test_x11.py`, and `test_keyboard.py` with its `FakeKeyboard`.
- `docs/keyboard-scanning-checklist.md`: the import in the Docker recipe, and new Linux checks.
- `docs/linux-x11.md`: the `--unicode` section.
- **Dependencies:** no new Python dependency. On Linux, emupos loads the system library libxkbcommon through `ctypes` when it is installed; GTK and Qt desktops have it. Without it, every `--unicode` character uses a spare key code.
- No API or configuration changes. Physical-key typing (`unicode` false) does not change.
