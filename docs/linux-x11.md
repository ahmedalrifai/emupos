# Linux: keyboard scans need X11

A scanner with `mode: keyboard` types each scan into the focused window, like a USB keyboard-wedge scanner. On Linux emupos does this through X11's XTest extension, using the `libXtst` library.

**Wayland is not supported.** Wayland has no general way for one program to type into another program's windows. On a Wayland session emupos refuses keyboard scans (even though `DISPLAY` may be set for XWayland apps) and points you to serial mode. Serial scanners work on every session type.

## Check your session

```sh
echo $XDG_SESSION_TYPE
```

- `x11`: keyboard mode works once libXtst is installed.
- `wayland`: log out and pick an X11 session on the login screen if your desktop offers one (on Ubuntu, the gear icon → "Ubuntu on Xorg"). Otherwise use serial mode (below).
- empty, with no `DISPLAY` either (SSH, containers, CI): there is no display to type into. Use serial mode, or run a virtual X server (see "Headless machines").

Run emupos as the user logged in to the desktop. Under `sudo` or as a system service, `DISPLAY` and `XAUTHORITY` are usually missing and the X server refuses the connection.

## Install libXtst

| Distribution | Command |
|---|---|
| Debian, Ubuntu | `sudo apt install libxtst6` |
| Fedora | `sudo dnf install libXtst` |
| Arch | `sudo pacman -S libxtst` |

Most X11 desktops already have it. `emupos doctor` checks for it: a failure when the configuration has a keyboard scanner, a warning when it has none.

## Serial mode instead

A serial scanner writes each scan to a virtual serial port that the POS opens, with no keyboard involved:

```yaml
  - id: lane1
    type: scanner
    mode: serial
    suffix: enter
    connections:
      - serial: { pty: true }
```

`emupos run` prints the port path (for example `$TMPDIR/emupos/lane1`, or `/tmp/emupos/lane1`). Configure the POS to read the scanner from that path.

## Keyboard layout

emupos presses keys by their physical position on a US keyboard, as a real scanner does. The active layout decides which characters appear: with an Arabic or AZERTY layout active, letter-bearing barcodes come out as that layout's characters, exactly as with real hardware.

`emupos scan --unicode` (or `"unicode": true` in the API) types the exact characters instead. For each character emupos maps one unused key code to that character, the same technique `xdotool type` uses. That key code keeps the last character typed; no physical key uses it.

## Headless machines

A virtual X server is enough for keyboard scans, for example in CI:

```sh
Xvfb :99 &
export DISPLAY=:99 XDG_SESSION_TYPE=x11
emupos run
```

## What you see when it is not available

- `emupos scan` exits with status 1 and prints the message and fix.
- `POST /api/v1/devices/{id}/scans` returns status 409 with code `keyboard_unavailable`: the fix mentions `mode: serial` for a Wayland session or a missing display, and names libXtst when the library is missing. Nothing is typed.
