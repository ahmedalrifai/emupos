## Why

Building a point-of-sale system means integrating receipt printers, cash drawers, barcode scanners and weight scales, and today the only way to test that integration is to buy the hardware. emupos is a cross-platform simulator that speaks the same wire protocols as real devices, so a POS can be developed and tested — on a laptop or in CI — without hardware, and switching to a real device is a configuration change rather than a code change.

This first change creates the project and delivers the devices a typical retail counter needs.

## What Changes

- New Apache-2.0 Python package and command-line tool `emupos`, supported on Windows, macOS and Linux.
- Simulated **receipt printer** reachable over raw TCP (port 9100) and serial. It decodes ESC/POS into rendered receipts (PNG and text), answers real-time status queries from its actual state, and accepts injected faults (paper out, paper near end, cover open, offline).
- Simulated **cash drawer** opened by the printer's drawer-kick command, with its open/closed sensor reported back through printer status.
- **Windows print queue** support: a setup command that creates a Windows printer queue pointed at the simulated printer, plus an SNMP responder so the queue reports the printer as online.
- Simulated **weight scale** with stable/unstable weight, zero, tare and capacity limits, speaking the Mettler Toledo 8217 serial protocol.
- **Weighed-item barcodes**: a generator for weight- and price-embedded EAN-13 barcodes as printed by label scales, with configurable layouts.
- Simulated **barcode scanner** in keyboard-wedge mode (typing into the focused window) and serial mode.
- **Virtual serial connections**: the simulator creates pty pairs itself on macOS and Linux, and opens user-provided COM ports (such as com0com pairs) on Windows.
- **YAML configuration and device profiles** (Epson TM-T20III, Xprinter XP-80T, Rongta 80 mm), validated against a published JSON Schema.
- Local **control API** (REST and an event stream) for the operator side of testing. A POS never uses this API; it talks to emupos only through the real device protocols. The API replaces the physical actions a person performs on real hardware (placing an item on the scale, pulling the scanner trigger, running out of paper, closing the drawer). People perform those actions with the CLI, which uses the API underneath, and automated tests can call the API directly.
- A modern **CLI** with live event output, `emupos doctor` diagnostics and shell completion.
- **Versioned releases** published to PyPI from CI, following semantic versioning.

## Capabilities

### New Capabilities

- `device-connections`: How devices are reached — TCP listeners, simulator-created pty pairs on macOS/Linux, user-provided COM ports on Windows, and stable connection paths.
- `configuration`: The YAML configuration file, device profiles, schema versioning and JSON Schema export.
- `receipt-printer`: ESC/POS decoding, receipt rendering, job boundaries, real-time status, automatic status back, and fault injection.
- `cash-drawer`: Drawer-kick handling, open/closed state, and the drawer sensor as seen through printer status.
- `windows-print-queue`: Creating a Windows printer queue for a simulated printer and answering the SNMP status queries that queue makes.
- `weight-scale`: Scale state (weight, motion, zero, tare, capacity) and the Toledo 8217 serial protocol.
- `weighed-item-barcodes`: Generating weight- and price-embedded EAN-13 barcodes from configurable layouts.
- `barcode-scanner`: Delivering scans as keyboard-wedge keystrokes or serial data, with suffix and timing options.
- `control-api`: The local REST API and event stream used to observe devices and perform the physical-world actions on them (set weight, trigger scans, inject faults, close the drawer, fetch receipts). It is never part of a POS's integration code.
- `cli`: The `emupos` commands, their output, diagnostics and shell completion.
- `release-and-versioning`: Version numbering, changelog, supported Python versions, and how releases are built and published.

### Modified Capabilities

_None — this is the first change in the repository._

## Impact

- **Repository**: new Python package under `src/emupos/`, device profiles, documentation (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, and `docs/` with per-OS setup guides, configuration, automation and CLI references, and protocol notes), GitHub issue and pull request templates, `LICENSE` and `NOTICE`, and GitHub Actions workflows for a Windows/macOS/Linux test matrix and releases.
- **Runtime dependencies** (kept to a small, justified set): Typer with Rich, FastAPI and Uvicorn, Pydantic, PyYAML, Pillow, segno, python-barcode, serialx (Windows COM ports), and pyobjc-framework-Quartz (macOS keyboard wedge only). All are permissively licensed.
- **External prerequisites users may need**: com0com for serial devices on Windows, Accessibility permission for keyboard-wedge scanning on macOS, and libXtst for keyboard-wedge scanning on Linux X11.
- **Distribution**: the `emupos` name on PyPI and a GitHub organization/repository for releases.
