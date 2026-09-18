# emupos

emupos simulates point-of-sale hardware — a receipt printer with its cash drawer, a weight scale and a barcode scanner — at the wire-protocol level, so your POS talks to it exactly as it talks to real devices.

It runs on Windows, macOS and Linux (see the [operating system notes](#operating-system-notes) for what works where), on a laptop or in CI.

## Two sides

emupos sits between two things, and they never mix:

```
     DEVICE SIDE                                          OPERATOR SIDE
     the same as real hardware                            replaces your hands

+----------+   ESC/POS over TCP 9100      +--------+   emupos CLI          +---------------+
| your POS | <--------------------------> | emupos | <-------------------> | you, or your  |
|   code   |   Toledo 8217 over serial    |        |   control API         | test scripts  |
+----------+   scanner keystrokes/serial  +--------+   (127.0.0.1:8765)    +---------------+
```

- **Your POS** talks to emupos only through the real device protocols: it prints to TCP port 9100, reads the scale on a serial port, receives scans as keystrokes or serial data. It never uses the emupos API. The integration code you test is the code that runs with real devices: moving to real hardware changes your POS's device settings, not its code ([how](#moving-to-real-hardware)).
- **You** do what a person does with the hardware: put an item on the scale, pull the scanner trigger, let the paper run out, push the drawer shut, look at the receipt. You do it with `emupos` commands. Automated tests can do the same through the [control API](docs/automation.md).
- **Keyboard scans are typed by the machine emupos runs on.** When that is not the machine with your POS window — emupos in a container, or on another machine — set `typed_by: client` on the scanner: emupos still validates the scan, plans the keystrokes and publishes the event, and `emupos scan` presses the keys where you are ([configuration](docs/configuration.md#scanner-type-scanner)).

| With real hardware you… | With emupos you run… |
|---|---|
| put 1.25 kg of tomatoes on the scale | `emupos scale set 1.25kg` |
| put them down so the reading still moves | `emupos scale set 1.25kg --unstable` |
| press ZERO or TARE on the scale | `emupos scale zero`, `emupos scale tare` |
| pull the scanner trigger on a barcode | `emupos scan 5901234123457` |
| scan the label a label scale printed | `emupos barcode weighed --layout weight-21 --item 12345 --weight 1.25kg`, then `emupos scan 2112345012506` |
| let the paper run low, or run out | `emupos fault set front paper-near-end`, `emupos fault set front paper-out` |
| open the printer cover, or switch the printer off-line | `emupos fault set front cover-open`, `emupos fault set front offline` |
| put in a new roll, close the cover | `emupos fault clear front paper-out`, `emupos fault clear front cover-open` |
| push the cash drawer shut | `emupos drawer close` |
| tear off the receipt and read it | `emupos receipt show` (add `--save receipt.png` for the image) |
| glance at the devices | `emupos devices` |

## What it simulates

| Device | What emupos does |
|---|---|
| **Receipt printer** | Accepts ESC/POS over raw TCP (port 9100 in the demo) and, on macOS and Linux, over a serial port. Renders every receipt as a PNG image and a text dump: text styles and sizes, raster and bit images, barcodes and QR codes, at the dot width of the printer profile. Answers `DLE EOT`, `GS r` and Automatic Status Back from its real state. Faults: `paper-near-end`, `paper-out`, `cover-open`, `offline`. Profiles: Epson TM-T20III, Xprinter XP-80T, Rongta RP326 (all 80 mm). |
| **Cash drawer** | One per printer. Opened by the POS with `ESC p` or `DLE DC4`; stays open until you close it. The POS sees it through the printer's status replies, with a configurable sensor level. |
| **Weight scale** | Speaks Mettler Toledo 8217 on a serial port (macOS and Linux). Stable and moving readings, zero, tare, over capacity and under zero. Profile: 15 kg × 5 g. |
| **Barcode scanner** | Keyboard mode types each scan into the focused window, like a USB keyboard-wedge scanner (macOS, and Linux on X11). Serial mode writes scans to a serial port (macOS and Linux). |
| **Weighed-item barcodes** | Generates the weight- or price-embedded EAN-13 barcodes that label scales print, from layouts such as `21IIIIIWWWWWC`. |

Around the devices: a CLI with live event output, `emupos doctor`, configuration validation with JSON Schema, and a local control API with an event stream.

## Install

emupos needs Python 3.13 or newer. [uv](https://docs.astral.sh/uv/) downloads a suitable Python for you, so it is the easiest way:

```sh
uv tool install emupos        # recommended
```

Other ways:

```sh
uvx emupos run --demo         # run without installing
pipx install emupos
pip install emupos            # for example inside a CI virtual environment
```

From a clone of the repository:

```sh
git clone https://github.com/ahmedalrifai/emupos.git
cd emupos
uv run emupos run --demo
```

Check the installation with `emupos --version`.

## Quickstart

This takes about five minutes and works on every operating system; the scale and scan steps need macOS or Linux. Use two terminals.

### 1. Start the demo devices

In the first terminal:

```sh
emupos run --demo
```

```
emupos <version> · built-in demo configuration
DEVICE  TYPE     PROFILE          CONNECTIONS
front   printer  epson-tm-t20iii  tcp 127.0.0.1:9100
lane1   scanner  keyboard mode    types into the focused window
deli    scale    toledo8217-15kg  serial $TMPDIR/emupos/deli -> /dev/ttys009
control API http://127.0.0.1:8765
Running the demo configuration. Write your own with `emupos config init`.
Showing events as they happen. Press Ctrl+C to stop.
```

The demo has a printer `front` on TCP port 9100, a keyboard scanner `lane1` and, on macOS and Linux, a scale `deli` on a serial port. Leave it running: events appear here as they happen.

### 2. Look at the devices

In the second terminal:

```sh
emupos devices
```

```
DEVICE  TYPE     PROFILE          CONNECTIONS                                 STATE
front   printer  epson-tm-t20iii  tcp 127.0.0.1:9100                          drawer closed, faults: none
lane1   scanner  -                -                                           keyboard mode, suffix enter, 10 ms between keys
deli    scale    toledo8217-15kg  serial $TMPDIR/emupos/deli -> /dev/ttys009  0.000 kg stable
```

### 3. Print a receipt, as your POS would

Send ESC/POS bytes to port 9100: initialise (`ESC @`), a line of text, and a cut (`GS V 0`).

macOS and Linux:

```sh
printf '\x1b\x40Hello from emupos\n\x1d\x56\x00' | nc -w 1 127.0.0.1 9100
```

Any operating system, with uv:

```sh
uv run --no-project python -c "import socket; s = socket.create_connection(('127.0.0.1', 9100)); s.sendall(b'\x1b@Hello from emupos\n\x1dV\x00'); s.close()"
```

The first terminal shows the receipt being completed:

```
00:26:32.881  front  printer.job.completed         job 1 · cut → front-20260913T222632880Z-a04808eb
```

### 4. Read the receipt

```sh
emupos receipt show
```

```
Hello from emupos
```

`emupos receipt show --save receipt.png` also writes the rendered image. Receipts are kept in `./receipts`.

### 5. Run out of paper

```sh
emupos fault set front paper-out
```

Now ask the printer for its paper status (`DLE EOT 4`), as a POS does:

```sh
printf '\x10\x04\x04' | nc -w 1 127.0.0.1 9100 | od -An -tx1
```

```
7e
```

`7e` means "paper not present". Any operating system:

```sh
uv run --no-project python -c "import socket; s = socket.create_connection(('127.0.0.1', 9100)); s.sendall(b'\x10\x04\x04'); print(s.recv(1).hex())"
```

Print another receipt now (step 3 with different text): it is held, like on a real printer without paper. Put a new roll in and it prints:

```sh
emupos fault clear front paper-out
emupos receipt show
```

All status bytes are listed in [docs/protocols/escpos-status.md](docs/protocols/escpos-status.md).

### 6. Weigh something (macOS and Linux)

```sh
emupos scale set 1.25kg
```

Ask the scale for the weight over its serial port (`W`), as a POS does, here with pyserial:

```sh
uv run --no-project --with pyserial python -c "import serial; s = serial.Serial('${TMPDIR:-/tmp}/emupos/deli', 9600, bytesize=7, parity='E', timeout=1); s.write(b'W'); print(s.read_until(b'\r'))"
```

```
b'\x0201.250\r'
```

The protocol is described in [docs/protocols/toledo8217.md](docs/protocols/toledo8217.md).

### 7. Scan a barcode (optional)

```sh
emupos scan 5901234123457
```

During the 3-second countdown, click the window that should receive the scan: emupos types `5901234123457` and Enter there, like a USB scanner. If the terminal you ran the command in still has focus when the countdown ends, emupos cancels the scan instead of typing it into your shell. This needs the Accessibility permission on macOS ([guide](docs/macos-accessibility.md)) and an X11 session on Linux ([guide](docs/linux-x11.md)). On Windows emupos cannot tell whether the terminal still has focus, so make sure you click the target window in time ([guide](docs/windows-keyboard.md)).

### 8. Stop

Press Ctrl+C in the first terminal. emupos closes its ports and removes its serial links.

Next, write your own configuration with `emupos config init` ([reference](docs/configuration.md)), and point your POS at the endpoints `emupos run` prints.

## Moving to real hardware

Your POS already stores where each device is: a printer address, a serial port name. Moving from emupos to real hardware changes those settings in **your POS**. Nothing in emupos changes, and your integration code stays the same.

| Device | Development, with emupos | Production, real hardware | What you change in your POS |
|---|---|---|---|
| Network receipt printer | `127.0.0.1:9100` | `192.168.1.50:9100` (the printer's IP) | printer address |
| Serial scale | `$TMPDIR/emupos/deli` (macOS/Linux) or a com0com port such as `COM6` (Windows) | `/dev/ttyUSB0` or `COM3` | serial port |
| Serial scanner | `$TMPDIR/emupos/lane2` or a com0com port | the scanner's port, e.g. `COM4` | serial port |
| Keyboard-wedge scanner | keystrokes | keystrokes | nothing |

This holds as long as development and production use the same kind of connection. Watch for these:

- **Use the same transport.** If you develop against TCP port 9100 but deploy a USB-only printer, your POS needs a different code path (USB through a driver or print queue), which is a code change. Choose a network printer for production, or the same printing path in both places.
- **Match the printer brand with the profile.** Vendors number code pages differently: PC864 is 37 on Epson and 22 on Rongta. If your POS sends these numbers, run emupos with the profile of the printer you will deploy (`epson-tm-t20iii`, `rongta-rp326`, `xprinter-xp80t`), so a wrong number shows up during development.
- **Match the serial settings.** Real devices misread bytes sent with the wrong baud rate or parity (a Toledo 8217 scale expects 9600 baud, 7 data bits, even parity). emupos warns when your POS uses other settings, where the operating system lets it see them.
- **Port pickers.** Serial ports that emupos creates on macOS and Linux are not listed by the operating system, so during development you type the path instead of choosing it from a list.

## Operating system notes

### macOS and Linux

- **Serial devices.** With `serial: { pty: true }`, emupos creates the serial port itself, with no driver to install, and publishes it at a stable path: `$TMPDIR/emupos/<device id>`, or `/tmp/emupos/<device id>` when `TMPDIR` is not set. Configure your POS with that path. A link belongs to the `emupos run` that published it: a second simulator using the same link name refuses to start instead of taking it over.
- **Serial settings.** If your POS opens the port with other settings than the device expects (for example 8N1 instead of 7E1 for the scale), emupos still passes the data and shows a warning. macOS lets emupos see the baud rate, data bits and parity; Linux only the baud rate.
- **Keyboard scanners** need the Accessibility permission on macOS ([docs/macos-accessibility.md](docs/macos-accessibility.md)), and an X11 session with libXtst on Linux ([docs/linux-x11.md](docs/linux-x11.md)). Serial scanners need neither.
- **Existing serial ports.** `serial: { port: /dev/ttyUSB0 }` opens a serial device that already exists, such as a USB serial adapter looped to another machine or a `tty0tty` virtual pair, with the device profile's serial settings. On Linux your user needs access to the device (usually the `dialout` group).

### Windows

- **The receipt printer and cash drawer work over TCP**, including status replies and faults.
- **Serial devices open existing COM ports.** emupos cannot create serial ports on Windows: a serial device uses `serial: { port: COM5 }`, one end of a COM port pair, and the POS opens the other end. The free com0com driver is blocked on Windows 11 while Secure Boot is on; [docs/windows-serial.md](docs/windows-serial.md) lists the options. The demo leaves the scale out.
- **Keyboard-mode scanning** types with `SendInput`. emupos and the POS must run at the same privilege level: a POS started as administrator does not receive scans from emupos running as a normal user, and emupos cannot detect that ([docs/windows-keyboard.md](docs/windows-keyboard.md)).
- **`emupos setup print-queue`** creates a Windows print queue that sends raw jobs to a simulated printer, and the queue shows the printer's faults, such as out of paper ([docs/windows-print-queue.md](docs/windows-print-queue.md)).

`emupos doctor` checks your machine and `./emupos.yaml`, and prints a fix for every problem it finds.

## Hard limits

Some things cannot be simulated in software, or not on every operating system:

| Limit | What it means for you |
|---|---|
| Virtual serial ports on Windows need a driver | Windows has no built-in virtual serial port pairs, so serial devices there need a port pair driver such as com0com, which Secure Boot blocks on current Windows 11, or two USB serial adapters (see [docs/windows-serial.md](docs/windows-serial.md)). |
| Simulator-created serial ports are not listed | The ports emupos creates on macOS and Linux do not appear in serial port lists or pickers, including the browser's Web Serial API. Open them by path. A browser POS that uses Web Serial cannot reach them. |
| USB devices are not emulated | USB printer-class devices and HID POS scanners cannot be emulated in software. emupos offers the same devices over TCP, serial and keyboard input. |
| No keyboard scanning on Wayland | Wayland does not let one program type into another's windows. Use a serial scanner, or an X11 session. |
| macOS needs the Accessibility permission for keyboard scans | Without it macOS silently drops the keystrokes, so emupos refuses the scan and tells you which app to allow. |
| Windows print queues are one-way | A POS that prints through a Windows print queue never receives status replies such as paper out. Test status over TCP. Windows also takes up to 10 minutes to show a new fault on the queue. |
| Windows scans into elevated windows are lost | Windows drops keystrokes sent to a window running as administrator from a normal-user emupos, and reports them as delivered. Run both at the same privilege level. |
| Glyph shapes are approximate | Receipt geometry is dot-accurate (paper width, columns, line breaks, images, barcode module sizes), but characters are drawn with open-licensed bitmap fonts, not the printer's own. The code pages the built-in profiles name have glyphs: PC437, PC850, PC852, PC858, PC860, PC863, PC865, PC866, WPC1252, PC720, PC864 and WPC1256. Another code page prints placeholders, while the text dump still shows the characters. |
| Right-to-left layout belongs to the POS | Like the printers it simulates, emupos prints the bytes it receives left to right, one character cell each: it never reorders them and never joins Arabic letters. A POS shapes and reverses its Arabic before sending it, so text that comes out backwards on paper comes out backwards here too. |
| Virtual serial pairs ignore baud rate and parity | Data passes whatever settings your POS chooses, while a real device would misread the bytes. Watch for emupos's framing warnings, which cover what the operating system exposes (macOS: baud rate, data bits, parity; Linux: baud rate only). |

## Documentation

- [docs/README.md](docs/README.md): every guide, with one line each
- [docs/configuration.md](docs/configuration.md): `emupos.yaml` and device profiles
- [docs/cli.md](docs/cli.md): every command and option
- [docs/automation.md](docs/automation.md): driving emupos from automated tests and CI
- [docs/protocols/](docs/protocols/): ESC/POS status bytes and the Toledo 8217 scale protocol

## Contributing and security

Contributions are welcome: device profiles, protocols and platform fixes. Start with [CONTRIBUTING.md](CONTRIBUTING.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Please report security problems privately, as described in [SECURITY.md](SECURITY.md).

## Licence

emupos is licensed under the [Apache License 2.0](LICENSE). Third-party attributions are in [NOTICE](NOTICE).
