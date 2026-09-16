## Context

The repository is empty apart from OpenSpec scaffolding. This change creates emupos: a simulator that behaves like real POS hardware on the wire, so that a POS talks to it exactly as it would talk to a device.

Research behind this design (September 2026) established:

- **Prior art** simulates devices at the API level (OPOS/JavaPOS simulators) or on Windows only. Existing open-source ESC/POS emulators mostly answer every status query with "online, no errors", so faults cannot be tested. No cross-platform, wire-level, multi-device simulator exists.
- **Real-world devices** in the first target market (Libya, and MENA generally) are Xprinter, Epson TM-T20 and Rongta receipt printers; Honeywell and Netum scanners in keyboard mode; and Rongta label scales. Label scales print a weight-embedded barcode that the POS scans. Where a scale is connected to the POS directly, the Toledo 8217 serial protocol is the de facto standard (it is the only protocol Odoo's IoT box reads).
- **Arabic receipts** are almost always printed as raster images, because thermal printers neither join Arabic letters nor reorder right-to-left text. Vendors also number Arabic code pages differently (PC864 is 37 on Epson, 22 on Rongta).
- **Transport parity differs by OS.** TCP is identical everywhere. Serial needs a virtual port pair: the simulator can create one itself on macOS and Linux (pty), but Windows needs a user-installed driver (com0com). USB device classes cannot be emulated in software.

Constraints: Apache-2.0; first-class support for Windows, macOS and Linux; the maintainer's strongest language is Python; code must be easy for new contributors to read and extend.

## Goals / Non-Goals

**Goals:**

- A POS integrates with emupos using the same protocol bytes, and where the OS allows the same connection type, as with the real device. Moving to hardware changes only configuration.
- Faults and edge states (paper out, cover open, unstable weight, drawer left open) are first-class features that can be triggered on demand, not only the happy path.
- Everything is scriptable, so the simulator is as useful in CI as on a developer's machine.
- Adding a device profile or a protocol touches one folder and is obvious from reading one existing example.

**Non-Goals:**

- Graphical interface. The CLI is the only interface in this change.
- Payment terminals and customer displays.
- USB-level device emulation (USB printer class, HID-POS scanners). This is not achievable in software alone.
- Printer protocols other than raw ESC/POS: Epson ePOS-Print XML, Star StarPRNT/WebPRNT, LPD.
- ESC/POS page mode, NV graphics stored in the printer's non-volatile memory, and PDF417.
- Rendering Arabic *text* sent through code pages. Raster images are rendered in this change; code-page glyph tables for Arabic are separate work.
- Scale protocols other than Toledo 8217.
- Keyboard-wedge scanning on Wayland; serial scanner mode covers those systems.
- Standalone binaries and installers. This change distributes through PyPI only.

## Decisions

### D1. Python 3.13+ with asyncio

Four stacks were assessed against the requirements, with prototypes and adversarial verification: TypeScript/Node, Go, Rust and Python. No blocker was found for Python. The following were verified on macOS:

- the simulator creates a pty pair itself;
- it reads the baud rate, data bits and parity the host set;
- binary bytes round-trip unchanged;
- a Toledo request/response takes under 100 µs;
- the standard `codecs` module provides cp864, cp720 and cp1256, decoding Arabic to unjoined letter forms exactly as a thermal printer prints them.

Python's costs are known and bounded. No Python ESC/POS decoder exists, but in practice that is true of every stack: the only TypeScript and Rust renderers are weeks old, lack Arabic glyphs and ignore status. Keyboard injection needs about 150 lines per OS. There is no single-file binary, which does not matter while distribution is PyPI-only.

- **Alternatives:**
  - **TypeScript** scored highest on paper, thanks to ready native addons and an SNMP library. Its binaries are ~41 MB, and its serial bindings have had no release in 20 months.
  - **Go** has the best distribution (4 MB static binaries) but is unfamiliar to the maintainer.
  - **Rust** has the smallest contributor pool.
- **Why Python:** the maintainer reviews every protocol pull request, so maintainer fluency decided it.

### D2. Pure device logic, I/O only at the edges

Device and protocol code is pure: it takes the current state and incoming bytes, and returns reply bytes plus events. Only `transports/`, `api/` and `daemon/` may perform I/O. A ruff `banned-api` rule enforces this: `asyncio`, `socket`, `ctypes`, `termios` and `serial*` are banned everywhere else, with per-file ignores for the three I/O locations.

Time is passed in as an argument (`now: float`), never read inside pure code. Scale settling and scan timing are therefore deterministic in tests.

- **Why:** protocol logic becomes plain functions tested with byte fixtures in milliseconds, contributors can add a protocol without understanding asyncio, and OS quirks stay contained.
- **Alternatives:** a plugin framework or abstract base classes for devices. Rejected: there is one implementation of each today. Registries are plain dicts, and a `typing.Protocol` is introduced only when a second implementation exists.

### D3. Every connection is an asyncio stream pair

Device code receives an `asyncio.StreamReader` and `StreamWriter` and never knows the connection type:

| Connection | How the stream pair is obtained |
|---|---|
| TCP | `asyncio.start_server` |
| pty (macOS/Linux) | `os.openpty()` in raw mode, wrapped via `loop.connect_read_pipe` / `connect_write_pipe` (verified on macOS) |
| COM port (Windows) | serialx's asyncio support. Compared with pyserial in a worker thread over a com0com pair (Secure Boot off, 2026-09-16): both ran 100 open/send/close cycles without a failure, so serialx wins on being asyncio-native. Reads arrive about 15 ms after the bytes, because serialx waits for a gap in the incoming data |

The simulator keeps the pty's slave end open so a POS can disconnect and reconnect, and publishes a stable symlink (for example `$TMPDIR/emupos/deli`) so POS configuration survives restarts.

- **Alternatives:** a custom `Transport` interface. Rejected, because the standard library already defines the interface.

### D4. Repository layout grouped by device, tests beside code

```
emupos/
├── pyproject.toml  uv.lock  README.md  CONTRIBUTING.md  CHANGELOG.md  LICENSE  NOTICE
├── src/emupos/
│   ├── cli/                   # Typer app; one module per command group
│   ├── daemon/                # the running simulator: simulator · connections · scans · runtime · server
│   ├── config.py              # YAML loading, Pydantic models, JSON Schema export
│   ├── events.py              # event types + in-process pub/sub
│   ├── api/                   # app · dependencies · schemas · errors · guard · routes/ (one router per resource)
│   ├── transports/            # tcp.py · pty.py · serial_port.py · snmp.py · keyboard/{windows,macos,x11}.py
│   ├── printer/
│   │   ├── printer.py         # state, faults, job boundaries
│   │   └── escpos/            # tokenizer.py · status.py · render.py · cases/<family>/<case>/{input.hex,expected.png,expected.txt,notes.md}
│   ├── drawer/drawer.py
│   ├── scale/
│   │   ├── scale.py
│   │   └── toledo8217/        # toledo8217.py · test_toledo8217.py · dialogues/*.txt
│   ├── barcodes/weighed.py
│   ├── scanner/scanner.py
│   ├── windows_queue/         # setup (PowerShell) + queue status mapping
│   └── profiles/{printers,scales}/*.yaml
├── docs/                      # windows-serial.md · macos-accessibility.md · linux-x11.md · protocols/
└── .github/workflows/         # ci.yml · release.yml · release-please.yml
```

Test files (`test_*.py`) and fixtures live next to the code they test. The wheel excludes them.

- **Why:** adding a protocol is one folder: code, test, dialogue fixture, one registry line and a profile.
- **Alternatives:** a top-level `tests/` tree. More conventional, but it splits every device across two trees.

### D5. ESC/POS processing: tokenizer → real-time path → print path

1. An incremental tokenizer turns the byte stream into commands. A command split across reads waits for more bytes, and unknown bytes produce an `UnknownCommand` event instead of an exception, as real firmware skips them.
2. Real-time commands (`DLE EOT`, `DLE ENQ`, `DLE DC4`) are handled before the print buffer. They are answered from current state even while printing is blocked by a fault.
3. Everything else feeds a print model, which the renderer draws onto a 1-bit Pillow canvas at the profile's dot width.
   - Command coverage in this change: text styles, alignment and sizes; feeds; cuts; tabs, margins, print width and positioning; `ESC p`; `GS v 0`; `ESC *`; buffered `GS ( L` graphics; `GS k` barcodes; `GS ( k` QR codes.
   - Barcode and QR matrices come from python-barcode and segno, scaled to the requested module sizes.

**Job boundaries.** A receipt ends at a cut command, when the connection closes, or after an idle timeout (default 2 s, configurable). Each finished job is stored as a PNG plus a text dump.

**Fidelity promise.** Dot-accurate geometry (paper width in dots, columns, line breaks, raster images, barcode module sizes) with approximate glyph shapes. Vendor ROM fonts are proprietary, so glyphs come from open-licensed bitmap fonts. A code page without a glyph table renders a visible placeholder and emits an event naming the code page.

- **Alternatives:** vendoring a TypeScript or Rust renderer through a subprocess or FFI. Rejected: both are weeks old, batch-only (the Rust one crashes on inline `DLE EOT`), and would split the core across languages.

### D6. Printer state is the single source for status replies

One state object holds: paper (ok / near end / out), cover (closed / open), online/offline, and drawer pin level. Faults injected through the API mutate this state.

`DLE EOT n`, `GS r n` and Automatic Status Back (`GS a n`) are all computed from it, using Epson's bit layouts. When ASB is enabled, a 4-byte status is pushed on enable and on every change. While paper is out or the cover is open, print data is buffered rather than printed, as on a real printer.

### D7. Windows print queue: generic driver + minimal SNMP responder

`emupos setup print-queue` uses the `Add-PrinterPort` and `Add-Printer` PowerShell cmdlets. It creates a Standard TCP/IP port targeting `127.0.0.1:<printer port>` and a queue using the built-in "Generic / Text Only" driver, which passes raw jobs through unchanged. Text printed from ordinary applications (Notepad, `Out-Printer`) is converted by the driver to plain text with CR LF and a closing form feed, and characters outside its code page, such as Arabic, become `.`. `--remove` undoes it.

Windows polls SNMP on UDP 161 to decide whether the queue is online, so emupos runs a minimal SNMPv1/v2c GET/GETNEXT responder, bound to 127.0.0.1, answering printer-status objects from printer state. The spike (1.3) found that Windows sends SNMP v1: GETNEXT `1.3.6.1.4.1.2699.1.2` and GET `sysDescr.0` every 10 minutes, and GET of hrDeviceStatus, hrPrinterStatus and hrPrinterDetectedErrorState for the port's SNMP index about every 10 minutes while the printer is healthy, every 30 to 60 s while it reports an error, and every 60 s while it does not answer. running/idle/`00` shows Idle, down/other with `40` Out of paper, with `08` Door open and with `02` Offline; a low-paper warning (`80`) shows nothing; no answer shows Offline. Each printer's port gets its own SNMP index, which Windows puts in every status request; two queues on 127.0.0.1 with different indexes showed their own states. `emupos setup print-queue` uses the printer's TCP port as the index, so the responder can map an index to its printer without shared numbering, and the index stays the same when printers are added to or reordered in `emupos.yaml`.

- **Documented limit:** this path is one-way. A POS printing through a queue never receives `DLE EOT` replies; status testing requires raw TCP or serial.
- **Alternatives:** pysnmp (heavier dependency for a handful of objects); telling users to untick "SNMP Status Enabled" (a manual step, and the queue could no longer show faults).

### D8. Scale model and Toledo 8217

- **State:** weight is held in integer grams (never float), plus tare, stable/unstable, and capacity limits from the profile. An unstable reading settles to stable after a configurable time, with the clock passed in (D2).
- **Protocol:** Toledo 8217 implements the wire contract used by common POS clients: 9600 baud, 7 data bits, even parity; `W` returns the weight or a status byte; the `E` echo probe is supported.
- **Validation:** conformance is checked by running a public client driver (Odoo's Toledo 8217 driver) as a black-box client against the pty. Its LGPL source is never copied.

### D9. Weighed-item barcode layouts as pattern strings

A layout is a 13-character pattern such as `21IIIIIWWWWWC`:

- literal digits are the prefix;
- `I` is the item code;
- `W` is weight in grams;
- `P` is price in minor currency units;
- the final `C` is the EAN-13 check digit.

Validation rejects wrong lengths, a missing or misplaced check position, and values that do not fit their field. Built-in presets cover common layouts, and custom patterns are accepted because layouts vary by store and country.

- **Alternatives:** Odoo-style regular expressions. Rejected: powerful, but hard to read.

### D10. Keyboard wedge: hand-written injectors, explicit triggers

| OS | Mechanism |
|---|---|
| Windows | `ctypes` `SendInput` with virtual-key codes and scan codes |
| macOS | pyobjc Quartz `CGEventPost`, after checking Accessibility trust |
| Linux X11 | XTest via `ctypes` |

- **Key codes:** by default the injectors send US-layout key codes, as a real HID scanner does, so an Arabic OS layout garbles letter-bearing barcodes just as it does with real hardware. `--unicode` types exact characters instead.
- **Triggers:** scans come from the CLI or API after a countdown (default 3 s, so the user can focus the POS window). There is no global hotkey or keyboard hook.
- **Alternatives:** pynput. Rejected: it is LGPL-3.0, crashes on recent macOS when used off the main thread, and its hooks trigger antivirus heuristics.

### D11. Configuration and profiles

- **Config file:** `emupos.yaml` with a top-level `schema: 1`.
- **Profiles:** built-in YAML files in the package; users can add their own directory. A profile holds dot width, columns per font, code-page number map, drawer sensor polarity, serial framing and scale capacity.
- **Validation:** Pydantic models validate everything at load. Errors name the exact path (for example `devices[1].connections[0].tcp.port`).
- **Editor support:** `emupos config schema` prints JSON Schema for autocomplete.
- **Why Pydantic:** configuration is a trust boundary. It is the one place a validation library pays for itself.

### D12. Local control API as a stable contract

emupos has two sides:

```
POS code ──real protocols (TCP 9100, serial, keystrokes)──▶ emupos ◀──CLI / API── person or test
            device side: identical to real hardware                    operator side: replaces hands
```

A POS never uses the control API: its integration code is exactly what it would be for real hardware. The API exists because `emupos run` is a long-running process that owns the ports and device state, while the actions a person performs on real hardware (placing an item on the scale, pulling the scanner trigger, running out of paper, closing the drawer) arrive from other processes. People perform them with CLI commands, which call the API. Automated tests may call it directly, which real hardware cannot offer at all. HTTP is used because test suites are written in every language, and every language and `curl` can call it.

FastAPI serves REST under `/api/v1` and an event WebSocket at `/api/v1/events`, bound to `127.0.0.1` by default. Binding elsewhere requires an explicit option and prints a warning, because the API has no authentication.

`emupos run` hosts the API. Every other CLI command that talks to devices is a thin client of it, so humans and CI exercise the same contract. The OpenAPI document is published at `/api/v1/openapi.json`.

A localhost API with no authentication is still reachable from any web page open in the user's browser, and this one can type keystrokes. The API therefore:

- refuses any request carrying an `Origin` header, which blocks cross-site requests;
- refuses `Host` headers other than loopback names, which blocks DNS rebinding;
- accepts request bodies only as `application/json`, which blocks form-based requests.

Command-line tools, test scripts and CI never send `Origin`, so they are unaffected.

- **Alternatives:** token authentication. It adds setup friction to every CI script for a tool that only listens on localhost.

### D13. CLI: Typer with Rich

Commands: `run`, `devices`, `receipt`, `scan`, `scale`, `fault`, `drawer`, `barcode`, `config`, `doctor`, `setup`, plus `--version` and shell completion.

Output formats:

| Situation | Output |
|---|---|
| Interactive terminal | Rich: banner, colour-coded live events, panels and tables |
| Piped | Plain text |
| `--json` | Machine-readable |
| `NO_COLOR` set | No colour |

`emupos doctor` prints a ✓/✗ checklist in which every failure names its fix.

- **Alternatives:** `argparse`. Rejected: no dependency, but a dated user experience.

### D14. Versioning and distribution

- **Semantic versioning.** Before 1.0, a minor release may contain breaking changes, and each one is listed under "⚠ BREAKING CHANGES" in `CHANGELOG.md`. After 1.0, standard SemVer applies.
- **Three independent version numbers:**
  - the **package version**: single source in `pyproject.toml`; shown by `emupos --version` and the API health endpoint;
  - the **API version**: the `/api/v1` path; a breaking API change introduces `/api/v2`;
  - the **configuration schema version**: the `schema:` integer; a newer schema than the installed emupos understands fails with "upgrade emupos".
- **Release flow:**
  1. Pull request titles follow Conventional Commits, and PRs are squash-merged.
  2. release-please keeps an open release PR that bumps the version and updates `CHANGELOG.md`.
  3. Merging it tags `vX.Y.Z`.
  4. The release workflow builds the wheel and sdist with `uv build`.
  5. It installs the built wheel on Windows, macOS and Linux runners and smoke-tests it (`emupos --version`, `emupos doctor --json`, rendering a fixture receipt).
  6. It publishes to PyPI with Trusted Publishing (no stored tokens, attestations enabled) and creates a GitHub Release from the changelog.
- **Package shape:** one pure-Python wheel (`py3-none-any`). OS-specific dependencies use environment markers (for example `pyobjc-framework-Quartz; sys_platform == "darwin"`).
- **Install paths:** `uv tool install emupos` (recommended; uv downloads a suitable Python automatically), `uvx emupos`, `pipx install emupos`, or `pip install emupos` in CI.
- **Python support:** `requires-python = ">=3.13"`; CI tests 3.13 and 3.14. Dropping a Python version is called out in the changelog.
- **Alternatives:** tag-derived versions via hatch-vcs (odd development versions); manual bump-and-tag (no generated changelog, more maintainer toil); standalone binaries (need code signing and antivirus handling; out of scope for this change).

### D15. Tooling and contribution rules

- **Tooling:**
  - uv for environments and locking;
  - hatchling as the build backend;
  - ruff for formatting and linting, including import sorting, security (`S`) rules and the D2 import ban;
  - pyright in strict mode;
  - pytest with syrupy snapshots for receipts;
  - Hypothesis (development only) to fuzz the tokenizer and scale protocol with random bytes.
- **CI:** a Windows/macOS/Linux matrix on Python 3.13 and 3.14, plus a licence check that fails on GPL, LGPL or AGPL runtime dependencies.
- **Rules in `CONTRIBUTING.md`:**
  - Modern type hints only (`list[str]`, `X | None`).
  - `@dataclass(frozen=True, slots=True)` for state and events.
  - `IntFlag` for status bits.
  - Weights and money are integers or `Decimal`, never float.
  - Protocol bytes are written as spaced hex (`bytes.fromhex("1b 40 0a")`). Dialogue fixtures use `>` for bytes the POS sends and `<` for replies.
  - Every handled command cites its source (manual and section) in a one-line comment and lands with a fixture.
  - OS-specific files stay small, and their error messages name the fix.
  - `__init__.py` files stay empty.
  - Around 12 runtime dependencies, each justified in `CONTRIBUTING.md`.
- **Attribution:** printer capability data from escpos-printer-db (CC-BY-4.0) and code-page mappings from ReceiptPrinterEncoder (MIT) are credited in `NOTICE`.

## Risks / Trade-offs

- **[com0com 3.0.0.0 blocked by Secure Boot (Code 52) on Windows 11]** (confirmed by spike 1.1 on build 26200) → `emupos doctor` detects it and links a guide listing the alternatives; TCP devices are unaffected.
- **[Virtual ports on macOS/Linux do not appear in port lists or Web Serial]** → Documented: the POS opens the printed path directly. Browser POS apps using Web Serial cannot use simulated serial devices.
- **[Parity and data bits cannot be observed on Linux ptys, nor any settings on Windows COM pairs]** → Framing mismatches are warned about where observable (macOS fully, Linux baud only) and documented elsewhere.
- **[macOS keystroke posting fails silently without Accessibility permission]** → Trust is checked before every scan, failing loudly with the exact settings path.
- **[Windows UIPI blocks typing into an elevated POS window]** → Documented; run both at the same privilege level. In spike 1.2 `SendInput` still reported every keystroke as accepted, so the simulator cannot rely on the count to warn.
- **[Windows shows a new printer fault only at its next SNMP poll, up to about 10 minutes later]** → Documented in the print-queue guide; faults clear within a minute because Windows polls a printer in error every 30 to 60 s.
- **[Another program holds a default TCP port, such as Logitech G HUB's updater on 9100]** → `emupos doctor` names the process; the user picks another port in `emupos.yaml`.
- **[Print-queue path cannot report status to the POS]** → Documented as a Windows limitation; raw TCP and serial remain available for status testing.
- **[Glyph shapes differ from printer ROM fonts]** → The promise is dot-accurate geometry, not identical glyphs; golden tests pin geometry.
- **[serialx has a single maintainer; pyserial has had no release since 2020]** → The COM transport is one small file, so swapping it for pyserial in a thread stays a contained change; the comparison run shows pyserial handles the same cycles.
- **[UDP 161 already in use by the Windows SNMP service]** → `emupos doctor` reports the conflict and the fix.
- **[Pure-Python rendering may be slow on large raster jobs]** → A benchmark fixture in CI; optimise only if a real job is measurably slow.

## Migration Plan

Not applicable: this is the first release. A broken release is yanked on PyPI and superseded by a patch release.

## Open Questions

- ~~Is serialx or pyserial in a worker thread the reliable Windows COM backend?~~ Answered on 2026-09-16 with a com0com pair and Secure Boot off: neither failed a cycle, so serialx stays. With com0com's defaults, a write while the other end is closed blocks (serialx 5 s, pyserial 2 s), which `EmuOverrun=yes` on the pair avoids; the docs say so.
- Do injected keystrokes produce the same `KeyboardEvent.code` values as a real USB scanner in Electron, WPF and Java apps? Spike 1.2 confirmed US-keyboard `code`, `key` and keyCode values in Chromium browsers on Windows and macOS, without a real scanner to compare; the Linux X11 run is still to do.
- Which open-licensed bitmap fonts best approximate Font A (12×24) and Font B (9×17)? Terminus (OFL) offers 12×24.
- Xprinter's Arabic code-page numbers are unconfirmed; the profile ships with them marked unverified until checked against a printer self-test page.
