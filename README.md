# emupos

emupos simulates point-of-sale hardware — a receipt printer with its cash drawer, a weight scale and a barcode scanner — at the wire-protocol level, so your POS talks to it exactly as it talks to real devices.

It runs on Windows, macOS and Linux, on a laptop or in CI. **Full documentation: [emupos.readthedocs.io](https://emupos.readthedocs.io/).**

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

- **Your POS** talks to emupos only through the real device protocols: it prints to TCP port 9100, reads the scale on a serial port, receives scans as keystrokes or serial data. It never uses the emupos API. The integration code you test is the code that runs with real devices: moving to real hardware changes your POS's device settings, not its code ([how](https://emupos.readthedocs.io/en/latest/moving-to-real-hardware/)).
- **You** do what a person does with the hardware: put an item on the scale, pull the scanner trigger, let the paper run out, push the drawer shut, look at the receipt. You do it with `emupos` commands. Automated tests can do the same through the [control API](https://emupos.readthedocs.io/en/latest/automation/).

## What it simulates

- **Receipt printer** — ESC/POS over raw TCP and, on macOS and Linux, over a serial port. Every receipt is rendered as a PNG image and a text dump, at the dot width of the profile. Real status replies (`DLE EOT`, `GS r`, Automatic Status Back) and faults: paper near end, paper out, cover open, off-line. Profiles: Epson TM-T20III, Xprinter XP-80T, Rongta RP326.
- **Cash drawer** — one per printer, opened by the POS with `ESC p` or `DLE DC4`, seen through the printer's status replies.
- **Weight scale** — Mettler Toledo 8217 over a serial port: stable and moving readings, zero, tare, over capacity and under zero.
- **Barcode scanner** — keyboard mode types each scan into the focused window like a USB wedge scanner; serial mode writes scans to a serial port.
- **Weighed-item barcodes** — the weight- and price-embedded EAN-13 barcodes that label scales print.

Around the devices: a CLI with live event output, `emupos doctor`, configuration validation with JSON Schema, and a local control API with an event stream. The full device tables are in the [documentation](https://emupos.readthedocs.io/en/latest/#what-it-simulates).

## Install

```sh
uv tool install emupos
```

Running without installing, pipx, pip, the Docker image and a source clone are covered in [the installation guide](https://emupos.readthedocs.io/en/latest/installation/).

## Try it in a minute

Start the demo devices in one terminal:

```sh
emupos run --demo
```

In a second terminal, print a receipt the way your POS does — `ESC @`, a line of text, `GS V 0` — and read it back:

```sh
uv run --no-project python -c "import socket; s = socket.create_connection(('127.0.0.1', 9100)); s.sendall(b'\x1b@Hello from emupos\n\x1dV\x00'); s.close()"
emupos receipt show
```

```
Hello from emupos
```

Now run the printer out of paper and ask it for its paper status (`DLE EOT 4`), as a POS does:

```sh
emupos fault set front paper-out
uv run --no-project python -c "import socket; s = socket.create_connection(('127.0.0.1', 9100)); s.sendall(b'\x10\x04\x04'); print(s.recv(1).hex())"
```

```
7e
```

`7e` means "paper not present", and receipts printed now are held until you put a new roll in with `emupos fault clear front paper-out` — like a real printer.

The [quickstart](https://emupos.readthedocs.io/en/latest/quickstart/) takes this further: the scale, a barcode scan, and your own configuration.

## Contributing and security

Contributions are welcome: device profiles, protocols and platform fixes. Start with [CONTRIBUTING.md](CONTRIBUTING.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Please report security problems privately, as described in [SECURITY.md](SECURITY.md).

## Licence

emupos is licensed under the [Apache License 2.0](LICENSE). Third-party attributions are in [NOTICE](NOTICE).
