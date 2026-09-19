# emupos documentation

emupos simulates point-of-sale hardware — a receipt printer with its cash drawer, a weight scale and a barcode scanner — at the wire-protocol level, so your POS talks to it exactly as it talks to real devices.

It runs on Windows, macOS and Linux, on a laptop or in CI. What software cannot simulate at all is listed in [limits.md](limits.md).

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

- **Your POS** talks to emupos only through the real device protocols: it prints to TCP port 9100, reads the scale on a serial port, receives scans as keystrokes or serial data. It never uses the emupos API. The integration code you test is the code that runs with real devices: moving to real hardware changes your POS's device settings, not its code ([how](moving-to-real-hardware.md)).
- **You** do what a person does with the hardware: put an item on the scale, pull the scanner trigger, let the paper run out, push the drawer shut, look at the receipt. You do it with `emupos` commands. Automated tests can do the same through the [control API](automation.md).
- **Keyboard scans are typed by the machine emupos runs on.** When emupos has no desktop of its own — in a container, or over SSH — set `typed_by: client` on the scanner: emupos still validates the scan, plans the keystrokes and publishes the event, and `emupos scan` presses the keys where you are ([configuration](configuration.md#scanner-type-scanner)).

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

## Where to start

New here? [Install emupos](installation.md), then run the [quickstart](quickstart.md): it prints a receipt the way your POS does, reads it back and runs the printer out of paper. After that, write your own [configuration](configuration.md) and point your POS at the endpoints `emupos run` prints.

Driving emupos from automated tests instead? [Testing and CI](automation.md) covers the control API, with examples in curl, Python and Node.js, and a GitHub Actions workflow.

Only keyboard-mode scanning and serial devices need setting up per operating system; TCP printing needs none anywhere. What software cannot simulate at all is in [hard limits](limits.md).

## The project

Development setup, code rules and how to report a vulnerability live with the source: [CONTRIBUTING.md](https://github.com/ahmedalrifai/emupos/blob/main/CONTRIBUTING.md) and [SECURITY.md](https://github.com/ahmedalrifai/emupos/blob/main/SECURITY.md).
