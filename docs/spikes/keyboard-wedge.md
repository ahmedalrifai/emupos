# Spike result: Keyboard wedge (task 1.2)

Status: macOS and Windows done; Linux not run (no machine available); no real scanner available · Date: 2026-09-15 · Run by: Ahmed Alrifai · Kit: `spikes/keyboard-wedge/`

## Question

1. Do injected keystrokes (Windows `SendInput`, macOS `CGEventPost`, X11 XTest) give the same `key`, `code` and timing as a real USB scanner, in a browser and in a native text field?
2. With an Arabic keyboard layout active, are letter-bearing scans garbled the same way as with a real scanner, and does `--unicode` type the exact characters?
3. Which app does macOS attribute the Accessibility permission to (Terminal, other terminals, uv's tool Python)?

## Environment

| | Windows | macOS | Linux |
|---|---|---|---|
| OS version / desktop session | Windows 11 Pro 10.0.26200 | macOS 26.5 (25F71) | |
| Browser and version | Edge 152 (Chromium; the runbook said Chrome, the logs' user agent says `Edg/152`) | Chrome 153 | |
| Native text field app | Notepad | TextEdit | |
| Keyboard layouts installed | en-US (`0x04090409`) and Arabic (Libya) with the Arabic (101) keyboard (`0x04011001`); Arabic (Saudi Arabia) `0x04010401` added during step 1.9 | US-compatible default (48/48 key codes match) + Arabic – PC | |
| Scanner model (if used) | none available | none available | |
| Python / uv version | CPython 3.13 via uv 0.7.13 | Homebrew Python 3.13.7 / uv 0.8.18 | |

## Observations

### Windows

Logs: `kb-*.json` and `kb-*.txt` from the Windows results zip. Every run had `sizeof(INPUT) = 40`; `repeat` and `isComposing` were false on every event.

1. Dry run: `sizeof(INPUT)` 40; the US layout (`0x04090409`) was already installed, so the script neither loaded nor unloaded it; language switcher changed? "no" (the runbook's pre-filled note, consistent with US already being installed). Key events: VK `0x35 0x39 0x30 0x31 …` with scan codes `0x06 0x0a 0x0b 0x02 …`, Enter VK `0x0d` scan `0x1c`.
2. Edge, `--keys vk-scan` (`kb-02`): assembled `5901234123457⏎`, field `5901234123457`; `code` of digits `Digit0` to `Digit9` (keyCode 48 to 57); Enter `code` `Enter`; accepted 28 of 28 (159 ms). Keydowns arrived 10.8 to 12.5 ms apart, 149 ms in total: Windows kept the 10 ms spacing, where macOS delivered a burst.
3. Edge, `--keys vk` (`kb-03`): `code` **empty** on every keydown and keyup; `key` and keyCode correct, field `5901234123457`.
4. Edge, `--keys scan` (`kb-04`): `code` `DigitN` and `Enter`, identical to vk-scan (the foreground layout was US).
5. Edge, `"Ab1-"` (`kb-05`): `Shift`/`ShiftLeft` down, `A`/`KeyA` down and up with `shiftKey` true, `ShiftLeft` up, then `b`/`KeyB`, `1`/`Digit1`, `-`/`Minus` (keyCode 189), `Enter`, all with `shiftKey` false; field `Ab1-`; accepted 12 of 12. Same sequence as macOS.
6. Edge, `--unicode "كود-42"` (`kb-06`): field `كود-42` exactly; every keydown had `key` = the exact character, `code` empty and keyCode **231** (VK_PACKET), including `-`, `4` and `2`; every keyup had `key` `Unidentified`; Enter kept `Enter`/13; accepted 14 of 14.
7. Notepad (default, `"Ab1-"`): `5901234123457` and `Ab1-`, each followed by a new line.
8. Arabic layout (default, `"Ab1-"`), Edge / Notepad (foreground layout `0x04011001`, Arabic (101)):
   - Default, Edge (`kb-08`): field `5901234123457` in **ASCII digits**, `key` the ASCII digit, `code` `DigitN`. The Arabic (101) keyboard types ASCII digits on the number row, unlike macOS "Arabic – PC", which types Arabic-Indic digits.
   - `"Ab1-"`, Edge (`kb-09`): field `ِلا1-` (kasra, lam-alef, `1`, `-`). Shift+`KeyA` gave the kasra (keyCode 65); `KeyB` typed the two characters `لا`, but its keydown and keyup reported `key` `Unidentified` (keyCode 66); `Digit1` gave `1`. Assembled from keydown `key`: `ِ1-`, so an app reading `key` loses `لا` completely (macOS reported `ا` and lost only the lam).
   - Notepad: `5901234123457` and `ِلا1-`, the same as the Edge field.
9. Notepad as administrator (`kb-11`, run twice, Arabic still the foreground layout): SendInput accepted **28 of 28** both times; text arrived? "no" (the runbook's pre-filled note, to confirm). If nothing arrived, Windows discarded the keystrokes and still reported every one as accepted, as Microsoft documents for UIPI.
10. Real scanner: not tried, no scanner available.

### macOS

1. Dry run from Terminal.app: AX trusted False; CGPreflightPostEventAccess False; responsible app `/System/Applications/Utilities/Terminal.app` (`TERM_PROGRAM` Apple_Terminal, bundle id `com.apple.Terminal`); layout check 48/48 US key codes match. The script printed the NOT TRUSTED message; same key codes as below.
   - From Warp (already granted Accessibility): AX trusted True; CGPreflightPostEventAccess True; responsible app `/Applications/Warp.app` (`TERM_PROGRAM` WarpTerminal, bundle id `dev.warp.Warp-Stable`); layout check 48/48 US key codes match. Events for `5901234123457` + Enter were the expected US ANSI key codes (`0x17 0x19 0x1d 0x12 0x13 0x14 0x15 0x12 0x13 0x14 0x15 0x17 0x1a`, then `0x24`), no shift.
2. Not trusted: message and named app matched System Settings? Yes: enabling Terminal in Accessibility and restarting Terminal made both checks True; `--prompt` dialog named ___ (not tried)
3. Attribution with only Terminal.app granted: other terminal (Warp) reports not trusted (both checks False, responsible app `/Applications/Warp.app`); uvx Python from Terminal reports trusted (both True, responsible app Terminal.app). uvx picked the same Homebrew Python 3.13.7 as `uv run`, so the permission follows the terminal app, not the Python binary. Confirmed with `uvx --managed-python` (uv-managed CPython 3.13.7 in `~/.local/share/uv/python/`): still trusted, responsible app Terminal.app.
4. Chrome (default, `"Ab1-"`): key/code as below; TextEdit: `5901234123457` and `Ab1-` typed exactly, each followed by a new line (Enter)
   - Default (`5901234123457` + Enter, `--delay-ms 10`), log `macos-chrome-default.json`: field value `5901234123457`, Enter delivered. Every digit had `key` = the digit and `code` `DigitN` (keyCode 48 to 57); Enter had `key`/`code` `Enter`, keyCode 13; `shiftKey`, `repeat` and `isComposing` false throughout. Timing as seen by the page (`performance.now()` in the handler): 91 ms from the first keydown to the last keyup; the first keyup came 67 ms after its keydown, then the remaining 13 keystrokes arrived within 24 ms (0 to 5 ms apart), so Chrome received the posted 10 ms spacing in a burst.
   - `"Ab1-"`, log `macos-chrome-Ab1.json`: field value `Ab1-`, Enter delivered. Sequence: `Shift`/`ShiftLeft` down, `A`/`KeyA` down and up with `shiftKey` true, `ShiftLeft` up, then `b`/`KeyB`, `1`/`Digit1`, `-`/`Minus` (keyCode 189), `Enter`, all with `shiftKey` false. Shift wraps only the capital letter, as a US keyboard does. 109 ms from Shift down to Enter up, with the same burst pattern (76 ms before the first letter, then 0 to 15 ms apart).
5. `--unicode "كود-42"`: Chrome key/code: field value `كود-42` exactly, Enter delivered (log `macos-chrome-unicode.json`). Every character's keydown had `key` = the exact character but `code` `KeyA` (the script posts key code 0 with the text attached); keyCode was 65 for the Arabic letters and 189, 52, 50 for `-`, `4`, `2`. Every keyup reported `key` `a` / `code` `KeyA`, even though the script attaches the text to the keyup too. So `--unicode` gives the right text in the field and in keydown `key`, but an app that reads `code`, keyCode of letters or keyup `key` sees `KeyA` / `a`. The Enter suffix kept its real `Enter` code. TextEdit: `كود-42` typed exactly, followed by a new line
6. Arabic input source (default, `"Ab1-"`), Chrome / TextEdit (input source "Arabic – PC"; the dry run's layout check reported `4/48 US key codes match` and listed each mismatch, e.g. key 0x00 gives `ش`, 0x0b gives `لا`, 0x12 gives `١`, so the check can tell a non-US input source apart):
   - Default, Chrome (log `macos-chrome-arabic-default.json`): field value `٥٩٠١٢٣٤١٢٣٤٥٧`, Arabic-Indic digits (U+0660 to U+0669) instead of ASCII; Enter delivered. `code` stayed `DigitN` and keyCode 48 to 57, only `key` changed to the Arabic-Indic digit. A POS that looks up the field value gets no match unless it converts the digits.
   - Default, TextEdit: `٥٩٠١٢٣٤١٢٣٤٥٧`, Arabic-Indic digits. The first attempt showed the first `٥` doubled (14 digits); a re-run in a new document gave the correct 13, so the doubling did not reproduce.
   - `"Ab1-"`, Chrome (log `macos-chrome-arabic-Ab1.json`): field value `ِلا١-` (kasra U+0650, lam-alef `لا`, `١`, `-`). Shift+`KeyA` gave the kasra with keyCode 65; `KeyB` typed two characters `لا` but its keydown reported `key` `ا` only and keyCode 229, keyup keyCode 66; `Digit1` gave `١`; `Minus` stayed `-`. The string assembled from keydown `key` (`ِا١-`) differs from the field value, so an app reading `key` loses the lam.
   - `"Ab1-"`, TextEdit: `ِلا١-`, same as the Chrome field.
   - The script sends US key codes regardless of the input source, so this is the garbling a real US-layout scanner should also produce; not yet compared with a real scanner.
7. Real scanner: not tried, no scanner available

### Linux (X11)

1. `XDG_SESSION_TYPE` ___; XTEST version ___; libXtst package ___
2. Chrome (default, `"Ab1-"`): key/code ___; gedit ___
3. `us,ara` layout with Arabic active, `"Ab1-"`: ___ (the script uses the current keymap; a real scanner sends the physical US key)
4. Wayland with `--try-xwayland` (optional): ___
5. Real scanner: `code` ___; delta ___ ms

## Decision

- Windows key events: [x] vk-scan [ ] vk [ ] scan. Reason: without a scan code Chromium leaves `code` empty (step 3); scan alone matched vk-scan in the browser, and vk-scan also gives applications that read virtual-key codes the US key.
- macOS permission check: [x] Quartz `CGPreflightPostEventAccess` is enough [ ] also needs `AXIsProcessTrustedWithOptions` (adds pyobjc-framework-ApplicationServices). Reason: the two checks agreed in every run (Warp granted and not granted, Terminal before and after the grant, uvx with Homebrew and uv-managed Python).
- X11 key lookup: [ ] `XKeysymToKeycode` is acceptable [ ] use a fixed US keycode table (not decided: Linux not run)
- Default `inter_key_delay_ms` of 10: [x] fine [ ] change to ___. Reason: no keystroke was lost on either OS; Windows delivered them about 11 ms apart, macOS in a burst.

## Impact on specs and tasks

- barcode-scanner spec ("US-layout key codes by default", "macOS Accessibility permission", "Linux keyboard mode requires X11", "Windows privilege limitation"): "US-layout key codes by default" holds on Windows and macOS: with an Arabic layout the letters change, and digits change or not depending on the layout (Arabic (101) keeps ASCII digits, macOS Arabic – PC does not). "Unicode mode" types the exact text, but the key events carry no physical key (`code` empty and keyCode 231 on Windows, `KeyA`/`a` on macOS), which the spec should say. "macOS Accessibility permission": the permission belongs to the terminal app that starts emupos, whatever Python runs it. "Windows privilege limitation": SendInput reported 28 of 28 accepted for an elevated Notepad, so the warning for fewer accepted keystrokes does not catch UIPI; the spec should say Windows reports such keystrokes as accepted. "Linux keyboard mode requires X11": not tested.
- design.md D10 and the Open Question on `KeyboardEvent.code`: Windows row becomes `SendInput` with virtual-key and scan codes. The question is answered for Chromium browsers (Edge 152 on Windows, Chrome 153 on macOS): `code`, `key` and keyCode match a US keyboard. Electron, WPF and Java apps were not tested, and nothing was compared with a real scanner.
- pyproject.toml darwin dependencies: no change; `transports/keyboard/macos.py` already checks only `CGPreflightPostEventAccess`.
- tasks 9.2 to 9.5: 9.2 sends both the US virtual-key code and its scan code, uses `KEYEVENTF_UNICODE` for the Unicode mode, and cannot rely on the accepted count to detect UIPI. 9.3 matches this spike. 9.4 is implemented but its spike checklist was not run. 9.5 unchanged.
