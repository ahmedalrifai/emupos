# macOS: Accessibility permission for keyboard scans

A scanner with `mode: keyboard` types each scan into the focused window, like a USB keyboard-wedge scanner. macOS only lets an app post keystrokes to other apps after you allow it under **Accessibility**. Without that permission macOS drops the keystrokes silently, so emupos checks before every keyboard scan and refuses the scan instead of pretending it was typed.

Serial scanners (`mode: serial`) need no permission.

**The permission is needed on the machine that types.** With `typed_by: server` (the default) that is the machine running `emupos run`. With `typed_by: client` it is the machine running `emupos scan`: the simulator neither checks nor needs Accessibility, and the command refuses the scan with this same message and fix when the permission is missing where you are.

## Which app to allow

macOS gives the permission to the **app that started emupos**, not to emupos itself:

| You start emupos from | Allow |
|---|---|
| Terminal | Terminal (in `/System/Applications/Utilities`) |
| iTerm2, Warp, Ghostty, … | that terminal app |
| The terminal inside VS Code, Cursor, PyCharm, … | the editor (for example Visual Studio Code) |

How emupos is installed (`uv tool install emupos`, `pipx`, `uvx`, a project virtual environment) does not change this: the terminal app is still the one macOS asks about. Allowing one terminal does not allow another; each app you run emupos from needs its own switch.

You don't have to work this out yourself: when the permission is missing, the error names the app, for example `turn on Warp (/Applications/Warp.app)`. If emupos was not started from an app (for example from a launchd job), the error names the Python executable instead.

## Allow it

1. Run `emupos doctor`. The Accessibility check shows ✗ and names the app.
2. Open **System Settings > Privacy & Security > Accessibility**.
3. Turn on the app. If it is not in the list, click **+**, choose the app (Terminal is in `/System/Applications/Utilities`) and turn it on.
4. Scan again, or run `emupos doctor` again. emupos checks on every scan, so there is no need to restart `emupos run`.
5. If the scan is still refused, quit the app completely (⌘Q) and open it again, then start emupos from it.

## When it stops working

macOS ties the permission to the app's signature. After an app update, the switch can still look on while macOS no longer honours it. Scans are then refused again with the same message. To fix it:

1. In **System Settings > Privacy & Security > Accessibility**, select the app and click **−** to remove it.
2. Add it again with **+** and turn it on.
3. Quit and reopen the app.

## What you see when it is missing

- `emupos scan` exits with status 1 and prints the message and fix.
- `POST /api/v1/devices/{id}/scans` returns status 409 with code `keyboard_unavailable`; `error.fix` names System Settings > Privacy & Security > Accessibility and the app to allow. Nothing is typed and no `scanner.scan.delivered` event is published.
- `emupos doctor` marks the Accessibility check ✗ when the configuration has a keyboard scanner this machine types (`typed_by: server`), and as a warning otherwise — including for a `typed_by: client` scanner, which is typed wherever `emupos scan` runs.

## Keyboard layout

emupos presses the keys that produce each character on a US keyboard, as a real scanner does. With another input source active (for example Arabic), letters come out as that input source's characters, exactly as with real hardware. Use `emupos scan --unicode` (or `"unicode": true` in the API) to type the exact characters instead.
