# Keyboard-wedge spike (task 1.2)

**Question.** A USB barcode scanner in keyboard mode "types" the barcode. Do keystrokes injected by emupos (`SendInput` on Windows, `CGEventPost` on macOS, XTest on X11) look the same to a browser and to a native text field: same `key`, same `code`, similar timing? What happens with an Arabic keyboard layout? Which app does macOS ask to trust?

Record everything in `docs/spikes/keyboard-wedge.md`.

## Files

| File | What it does |
|---|---|
| `keylogger.html` | Open in a browser. Logs every keydown/keyup (`key`, `code`, `keyCode`, `shiftKey`, `repeat`, `isComposing`, time and delta in ms), shows the assembled string, and has a **Copy log as JSON** button. |
| `type_windows.py` | `SendInput` with US-layout virtual-key codes, `--keys vk-scan` (default), `vk` or `scan`, and `--unicode`. Reports how many events Windows accepted. |
| `type_macos.py` | `CGEventPost` with US ANSI key codes, and `--unicode`. Prints both permission checks and the app macOS will ask about. |
| `type_x11.py` | XTest through libX11/libXtst. Refuses Wayland and a missing `DISPLAY` or libXtst with a clear message. |

All scripts type `5901234123457` followed by Enter by default, after a 3-second countdown (`--countdown N`) so you can click into the target field. Other options: a text argument (`"Ab1-"`), `--suffix enter|tab|none`, `--delay-ms 10`, `--dry-run` (print the events, send nothing).

## Save each log

After each run: click **Copy log as JSON**, paste into a new file named `<os>-<app>-<mode>.json` (for example `windows-chrome-vk-scan.json`), then click **Clear** before the next run. For native fields, write down (or screenshot) what appeared.

Tip: start the script from a terminal, then click into the target within the countdown. Don't type while it runs.

## Optional: a real scanner

Make a printable EAN-13 for `5901234123457` (python-barcode adds the check digit `7`):

```sh
uv run --no-project --python 3.13 --with python-barcode python -c "import barcode; print(barcode.get('ean13', '590123412345').save('ean13'))"
```

Open `ean13.svg` in a browser and print it (or show it large on a phone). Put the scanner in USB keyboard (HID) mode, scan into `keylogger.html`, and save the log as `<os>-chrome-real-scanner.json`. This is the reference the injected logs are compared with.

## Windows checklist

- [ ] `uv run spikes/keyboard-wedge/type_windows.py --dry-run`: record `sizeof(INPUT)` (must be 40 on 64-bit Python), the installed layouts, and whether it says the US layout was loaded and unloaded. Note if a new "ENG" entry appeared in the taskbar language switcher.
- [ ] Open `keylogger.html` in Chrome, click the field, run each and save the log:
  - [ ] `uv run spikes/keyboard-wedge/type_windows.py` (vk-scan)
  - [ ] `uv run spikes/keyboard-wedge/type_windows.py --keys vk`
  - [ ] `uv run spikes/keyboard-wedge/type_windows.py --keys scan`
  - [ ] `uv run spikes/keyboard-wedge/type_windows.py "Ab1-"`
  - [ ] `uv run spikes/keyboard-wedge/type_windows.py "كود-42" --unicode`
- [ ] Notepad: run the default and `"Ab1-"`; write down what appeared.
- [ ] Arabic layout: *Settings > Time & language > Language & region*, add Arabic with an Arabic keyboard; switch with Win+Space **in the target window**. Repeat the default and `"Ab1-"` in Chrome and Notepad.
- [ ] Privilege level: open Notepad with *Run as administrator*, run the script from a normal terminal. Record "SendInput accepted X of Y" and whether anything arrived.
- [ ] Real scanner in Chrome (optional, see above).
- [ ] Copy each script's console output into the template.

## macOS checklist

- [ ] `uv run spikes/keyboard-wedge/type_macos.py --dry-run` from **Terminal.app**: record the two permission lines, the responsible app, and the layout check line ("48/48 US key codes match" on a US/ABC layout).
- [ ] If it says NOT TRUSTED: check the named app matches what System Settings wants. Grant it in *System Settings > Privacy & Security > Accessibility*, quit and reopen the terminal, run again. (`--prompt` makes macOS show its own dialog.)
- [ ] Attribution: grant only Terminal.app, then run the same dry-run from another launcher (iTerm2, VS Code's terminal, or Warp). Record what each reports. Then run it once via uv's tool Python: `uvx --python 3.13 --with pyobjc-framework-Quartz --with pyobjc-framework-ApplicationServices python spikes/keyboard-wedge/type_macos.py --dry-run` and record whether the answer changes.
- [ ] Open `keylogger.html` in Chrome, click the field, run and save the log:
  - [ ] `uv run spikes/keyboard-wedge/type_macos.py`
  - [ ] `uv run spikes/keyboard-wedge/type_macos.py "Ab1-"`
  - [ ] `uv run spikes/keyboard-wedge/type_macos.py "كود-42" --unicode`
- [ ] TextEdit: the same three; write down what appeared.
- [ ] Arabic input source: *System Settings > Keyboard > Input Sources*, add Arabic, switch to it, repeat the default and `"Ab1-"` in Chrome and TextEdit.
- [ ] Real scanner in Chrome (optional).

## Linux (X11) checklist

- [ ] `echo $XDG_SESSION_TYPE` must print `x11` (on Ubuntu pick "Ubuntu on Xorg" on the login screen). Install libXtst if the script asks.
- [ ] `uv run spikes/keyboard-wedge/type_x11.py --dry-run`: record the XTEST version and keycodes.
- [ ] Chrome with `keylogger.html`: default and `"Ab1-"`, save logs.
- [ ] gedit (or any GTK text editor): default and `"Ab1-"`.
- [ ] Arabic: `setxkbmap -layout us,ara -option grp:alt_shift_toggle`, switch to Arabic in the target window (Alt+Shift), repeat `"Ab1-"`. The script looks characters up in the current keymap, so this may differ from a real scanner; record it. Restore with `setxkbmap us`.
- [ ] Wayland (optional): from a Wayland session, `--try-xwayland`, and record whether Chrome or gedit receive anything.
- [ ] Real scanner in Chrome (optional).

## Send back

`docs/spikes/keyboard-wedge.md` filled in, the saved JSON logs, and the console output of each run.
