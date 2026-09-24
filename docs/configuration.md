# Configuration reference

emupos reads its devices from `emupos.yaml`. `emupos run` looks for it in the current directory; use `emupos run --config path/to/file.yaml` for another location, or `emupos run --demo` to try emupos without a file.

```sh
emupos config init       # write a commented starter emupos.yaml
emupos config validate   # check a file without starting anything
emupos config schema > emupos.schema.json   # JSON Schema for editor autocomplete
```

Every problem in a file is reported at once, with its exact location, for example `devices[1].connections[0].tcp.port: a port from 1 to 65535 is expected`. Unknown keys are errors, so a typo never silently falls back to a default.

## A complete example

```yaml
schema: 1

api:
  host: 127.0.0.1
  port: 8765

devices:
  - id: front
    type: printer
    profile: epson-tm-t20iii
    connections:
      - tcp: { port: 9100 }
      - serial: { pty: true, link: front }   # macOS/Linux
    job_idle_timeout_ms: 2000
    receipts_dir: ./receipts
    drawer: { sensor_open_level: high }

  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections:
      - serial: { pty: true }                # Windows: serial: { port: COM5 }

  - id: lane1
    type: scanner
    mode: keyboard
    suffix: enter
    inter_key_delay_ms: 10

  - id: lane2
    type: scanner
    mode: serial
    suffix: enter
    connections:
      - serial: { pty: true }
```

## Top level

| Key | Required | Default | Meaning |
|---|---|---|---|
| `schema` | yes | — | Format version of the file. This version of emupos reads `1`. A newer number means you need to upgrade emupos. |
| `api.host` | no | `127.0.0.1` | Address of the control API. The API has no authentication: keep it on loopback. |
| `api.port` | no | `8765` | Port of the control API. No device may use this port. |
| `devices` | yes | — | List of at least one device. |

## Devices

Every device has:

| Key | Meaning |
|---|---|
| `id` | Unique name used by the CLI and the API. Lowercase letters, digits and hyphens, starting with a letter or digit, e.g. `front`, `lane-2`. |
| `type` | `printer`, `scale` or `scanner`. A cash drawer is not a device: it belongs to its printer. |

### Printer (`type: printer`)

| Key | Required | Default | Meaning |
|---|---|---|---|
| `profile` | yes | — | Built-in profile name or path to a profile file (see below). |
| `connections` | yes | — | At least one connection. |
| `job_idle_timeout_ms` | no | `2000` | A receipt ends after this long without bytes on a connection (it also ends at a cut or when the connection closes). |
| `receipts_dir` | no | `./receipts` | Where rendered receipts (PNG and text) are stored. |
| `drawer.sensor_open_level` | no | from profile | Level of the drawer sensor (pin 3) when the drawer is open: `high` or `low`. Drawers differ; match yours. |

### Scale (`type: scale`)

| Key | Required | Meaning |
|---|---|---|
| `profile` | yes | Built-in scale profile or profile file. |
| `connections` | yes | At least one connection, normally `serial`. |

### Scanner (`type: scanner`)

| Key | Required | Default | Meaning |
|---|---|---|---|
| `mode` | yes | — | `keyboard`: types scans into the focused window like a USB keyboard-wedge scanner (setup: [macOS](macos-accessibility.md), [Linux](linux-x11.md)). `serial`: writes scans to its connections. |
| `suffix` | no | `enter` | Sent after each scan: `enter`, `tab` or `none`. |
| `inter_key_delay_ms` | no | `10` | Delay between keystrokes in keyboard mode. |
| `typed_by` | keyboard mode only | `server` | Which machine presses the keys. `server`: the machine running `emupos run`. `client`: the machine running `emupos scan`, for a simulator with no desktop of its own such as one in a container — it still validates the scan, plans the keys and publishes the event. |
| `connections` | serial mode only | — | A keyboard scanner must not have connections; a serial scanner needs at least one. Serial scanners expect 9600 baud, 8 data bits, no parity, 1 stop bit. |

## Connections

Each item of `connections` has exactly one of `tcp` or `serial`.

### `tcp`

| Key | Required | Default | Meaning |
|---|---|---|---|
| `port` | yes | — | 1–65535. Two devices cannot share a port on the same host. |
| `host` | no | `127.0.0.1` | Address to listen on. Use `0.0.0.0` to accept connections from other machines. |

### `serial`

Exactly one of `pty` or `port`:

| Key | Meaning |
|---|---|
| `pty: true` | **macOS and Linux.** emupos creates the serial port itself, with no driver to install, and publishes it as a link, by default `$TMPDIR/emupos/<device id>` (or `/tmp/emupos/<device id>`). Point your POS at that path. Not available on Windows. |
| `link` | Only with `pty: true`: the link name, if you want something other than the device id. Links must be unique and must not end in `.pid`. A link belongs to the running `emupos run` that published it; another simulator using the same name refuses to start. |
| `port` | An existing serial port: a device path on macOS or Linux, such as `/dev/ttyUSB0`, a USB serial adapter looped to another machine, or one end of a `tty0tty` pair, or a COM port name on Windows, such as `COM5` ([windows-serial.md](windows-serial.md)). On Linux your user needs access to it (usually the `dialout` group). |

Serial framing (baud rate, data bits, parity, stop bits) comes from the device profile. emupos warns when your POS opens the port with different settings, where the operating system lets it see them.

## Profiles

A profile describes a device model. Built-in profiles:

| Profile | Type | Notes |
|---|---|---|
| `epson-tm-t20iii` | printer | 80 mm, 576 dots, Arabic code pages PC720 = 32, PC864 = 37, WPC1256 = 50 |
| `xprinter-xp80t` | printer | 80 mm, 576 dots; Arabic code-page number unverified |
| `rongta-rp326` | printer | 80 mm, 576 dots, PC720 = 27, PC864 = 22, WPC1256 = 34 |
| `toledo8217-15kg` | scale | Toledo 8217 protocol, 15 kg × 5 g, 9600 baud 7E1 |
| `sma-15kg` | scale | SMA protocol, 15 kg × 5 g, kilograms and pounds, 9600 baud 8N1 |

To use your own, set `profile` to a path (any value containing `/` or ending in `.yaml`). Relative paths are resolved from the folder that contains `emupos.yaml`. Start from a copy of a built-in profile in [`src/emupos/profiles/`](https://github.com/ahmedalrifai/emupos/tree/main/src/emupos/profiles).

### Printer profile keys

| Key | Meaning |
|---|---|
| `type` | `printer` |
| `name` | Human-readable model name |
| `dpi` | Print resolution |
| `width_dots` | Printable width in dots (576 for 80 mm at 203 dpi) |
| `font_a`, `font_b` | Character cell size in dots: `{ width, height }` |
| `code_pages` | Map from the `ESC t` number to the code page name, e.g. `37: PC864` |
| `default_code_page` | Number selected after `ESC @`; must be in `code_pages` |
| `drawer_sensor_open_level` | `high` or `low` |
| `printer_id` | Optional. What the printer answers to `GS I`; left out, it answers nothing |
| `serial` | `{ baud, data_bits, parity, stop_bits }`, needed for serial connections |

`printer_id` keys, all taken from the model's programming manual — see [ESC/POS status replies](protocols/escpos-status.md) for the bytes they produce:

| Key | Meaning |
|---|---|
| `model` | Printer model ID, 0–255, e.g. `0x63` for a TM-T20III |
| `autocutter` | Whether an autocutter is installed; it sets bit 1 of the type ID |
| `maker` | Maker name, printable ASCII, e.g. `EPSON` |
| `name` | Model name, printable ASCII, e.g. `TM-T20III` |
| `column_emulation_mode` | Optional, default `false`. Whether the model answers `GS I 35` |

### Scale profile keys

| Key | Meaning |
|---|---|
| `type` | `scale` |
| `name` | Human-readable model name |
| `protocol` | `toledo8217` or `sma`. The keys below it depend on this |
| `capacity_grams` | Maximum weight |
| `division_grams` | Resolution of reported weights |
| `settle_ms` | How long an unstable reading takes to become stable |
| `serial` | `{ baud, data_bits, parity, stop_bits }` |

With `protocol: toledo8217`:

| Key | Meaning |
|---|---|
| `reply_integer_digits`, `reply_decimals` | Format of weight replies in kilograms, e.g. `2` and `3` give `01.250` |

With `protocol: sma` — see [the SMA protocol](protocols/sma.md):

| Key | Meaning |
|---|---|
| `units` | The units the scale offers, in the order its unit key cycles them, each `{ unit, decimals, count_by }`. The first is the unit after start |
| `maker`, `model`, `revision` | What the scale reports in its About dialogue, printable ASCII |
| `serial_number` | Optional. Reported in the About dialogue when it is set |
| `repeat_interval_ms` | Optional, default 200. How often `R` and `S` repeat the weight |

A key belonging to the other protocol is a validation error, so a profile cannot quietly carry a setting nothing reads.

## Security note

Configuration and profile files are read as plain data. YAML object tags such as `!!python/object` are rejected and never executed.
