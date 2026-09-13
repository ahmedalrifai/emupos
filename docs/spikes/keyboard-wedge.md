# Spike result: Keyboard wedge (task 1.2)

Status: not run · Date: ___ · Run by: ___ · Kit: `spikes/keyboard-wedge/`

## Question

1. Do injected keystrokes (Windows `SendInput`, macOS `CGEventPost`, X11 XTest) give the same `key`, `code` and timing as a real USB scanner, in a browser and in a native text field?
2. With an Arabic keyboard layout active, are letter-bearing scans garbled the same way as with a real scanner, and does `--unicode` type the exact characters?
3. Which app does macOS attribute the Accessibility permission to (Terminal, other terminals, uv's tool Python)?

## Environment

| | Windows | macOS | Linux |
|---|---|---|---|
| OS version / desktop session | | | |
| Browser and version | | | |
| Native text field app | | | |
| Keyboard layouts installed | | | |
| Scanner model (if used) | | | |
| Python / uv version | | | |

## Observations

### Windows

1. Dry run: `sizeof(INPUT)` ___; US layout already installed / loaded and unloaded ___; language switcher changed? ___
2. Chrome, `--keys vk-scan`: assembled ___; `code` of digits ___; Enter `code` ___; accepted ___ of ___
3. Chrome, `--keys vk`: `code` ___
4. Chrome, `--keys scan`: `code` ___
5. Chrome, `"Ab1-"`: key/code/shiftKey sequence ___
6. Chrome, `--unicode "كود-42"`: `key` ___ `code` ___ field value ___
7. Notepad (default, `"Ab1-"`): ___
8. Arabic layout (default, `"Ab1-"`), Chrome / Notepad: ___
9. Notepad as administrator: accepted ___ of ___; text arrived? ___
10. Real scanner: `code` ___; delta between keys ___ ms; matches which mode? ___

### macOS

1. Dry run from Terminal.app: AX trusted ___; CGPreflightPostEventAccess ___; responsible app ___; layout check ___
2. Not trusted: message and named app matched System Settings? ___; `--prompt` dialog named ___
3. Attribution with only Terminal.app granted: other terminal (___) reports ___; uvx Python reports ___
4. Chrome (default, `"Ab1-"`): key/code ___; TextEdit ___
5. `--unicode "كود-42"`: Chrome key/code ___; TextEdit ___
6. Arabic input source (default, `"Ab1-"`), Chrome / TextEdit: ___
7. Real scanner: `code` ___; delta ___ ms

### Linux (X11)

1. `XDG_SESSION_TYPE` ___; XTEST version ___; libXtst package ___
2. Chrome (default, `"Ab1-"`): key/code ___; gedit ___
3. `us,ara` layout with Arabic active, `"Ab1-"`: ___ (the script uses the current keymap; a real scanner sends the physical US key)
4. Wayland with `--try-xwayland` (optional): ___
5. Real scanner: `code` ___; delta ___ ms

## Decision

- Windows key events: [ ] vk-scan [ ] vk [ ] scan. Reason: ___
- macOS permission check: [ ] Quartz `CGPreflightPostEventAccess` is enough [ ] also needs `AXIsProcessTrustedWithOptions` (adds pyobjc-framework-ApplicationServices)
- X11 key lookup: [ ] `XKeysymToKeycode` is acceptable [ ] use a fixed US keycode table
- Default `inter_key_delay_ms` of 10: [ ] fine [ ] change to ___

## Impact on specs and tasks

- barcode-scanner spec ("US-layout key codes by default", "macOS Accessibility permission", "Linux keyboard mode requires X11", "Windows privilege limitation"): ___
- design.md D10 and the Open Question on `KeyboardEvent.code`: ___
- pyproject.toml darwin dependencies: ___
- tasks 9.2 to 9.5: ___
