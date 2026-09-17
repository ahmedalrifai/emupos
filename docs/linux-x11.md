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

`emupos scan --unicode` (or `"unicode": true` in the API) types the exact characters instead, as `xdotool type` does:

- **Characters the active layout has** are typed with that layout's keys, with Shift where needed. An application sees those keys' positions, as with a real keyboard. For example, `ش` under an Arabic layout is typed with the A key.
- **Other characters** get an unused key code that emupos maps to the character. No physical key uses these key codes, so an application sees no key position for them.

Looking characters up in the layout needs the libxkbcommon library (`sudo apt install libxkbcommon0` on Debian and Ubuntu, `sudo dnf install libxkbcommon` on Fedora). GTK and Qt desktops already have it. Without it, every character uses an unused key code.

Caps Lock does not change `--unicode` text: emupos turns it off for the scan and back on afterwards. Scans without `--unicode` follow Caps Lock, as a real scanner does.

### Limits

- **Different characters per scan.** Each different character the layout lacks keeps its own key code while emupos runs, so an application that is slow to handle the keys still reads the right characters. An X server has only a few unused key codes (19 on Xvfb). A scan with more different missing characters than that reuses the key code of the least recently typed one. An application that has not yet handled that earlier keystroke then reads the new character. For example, 28 different Arabic letters while a US layout is active can hit this; the same scan under an Arabic layout cannot.
- **Stopping emupos.** emupos clears its key codes when it stops with Ctrl+C or SIGTERM. A killed emupos (`kill -9`, a crash) leaves them mapped. Run `setxkbmap` with your usual layout (for example `setxkbmap us`), or log in again, to get them back.

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
