## 1. Spikes (before feature work)

- [ ] 1.1 Windows serial spike: on a clean Windows 11 VM with Secure Boot on, install signed com0com 3.0.0.0; open one end with serialx (asyncio) and with pyserial in a worker thread while a client opens the other end; run 100 open/close/write cycles, including writes while the peer is closed; record Code 52 behaviour and whether com0com installs on a GitHub-hosted Windows runner. Findings go in `docs/spikes/windows-serial.md`, and the default COM backend is decided.
- [ ] 1.2 Keyboard-wedge spike: type `5901234123457` + Enter via `SendInput` virtual-key codes (Windows), `CGEventPost` (macOS) and XTest (X11) into a browser page that logs `key`, `code` and timestamps, plus one native text field per OS; compare with a real USB scanner or a recorded trace. Also check the Accessibility grant under Terminal and under `uv tool` installs. Findings go in `docs/spikes/keyboard-wedge.md`.
- [ ] 1.3 SNMP spike: capture (Wireshark) the SNMP requests a Windows 11 Standard TCP/IP port queue sends to a network printer, and which responses make it show online, offline, paper out and door open; confirm whether per-queue identification works when several queues point at 127.0.0.1. Findings (object list and value mapping) go in `docs/spikes/windows-snmp.md`.
- [ ] 1.4 Printer traffic capture: collect about 20 real ESC/POS jobs as hex (`nc -l 9100`) from python-escpos, escpos-php, node-thermal-printer, Odoo POS and one Windows "Generic / Text Only" queue, including Arabic receipts printed as images. Store them as initial `cases/` fixtures and list the commands used, to confirm the supported command set.
- [ ] 1.5 Update design.md Open Questions with the spike results, and adjust specs if a spike contradicts them.

## 2. Repository and tooling

- [x] 2.1 Rename the project to emupos in `README.md`; add `LICENSE` (Apache-2.0) and `NOTICE` (attribution for escpos-printer-db CC-BY-4.0 data and ReceiptPrinterEncoder MIT code-page mappings).
- [x] 2.2 Create `pyproject.toml`: hatchling build, `requires-python = ">=3.13"`, `emupos` console script, runtime dependencies with OS environment markers, and a wheel config that excludes `test_*.py` and fixture folders but includes built-in profiles.
- [x] 2.3 Configure ruff (format, lint, import sorting, `S` security rules) including the `banned-api` rule for `asyncio`, `socket`, `ctypes`, `termios` and `serial*`, with per-file ignores only for `transports/`, `api/` and `daemon.py`; verify a banned import outside those paths fails lint.
- [x] 2.4 Configure pyright strict and pytest (test discovery next to source, syrupy, Hypothesis as dev dependencies); `uv sync` then `uv run pytest` passes on an empty test.
- [x] 2.5 Create the D4 package layout with empty `__init__.py` files.
- [x] 2.6 Add `ci.yml`: Windows/macOS/Linux × Python 3.13/3.14 running ruff, pyright and pytest; a licence check that fails on GPL, LGPL or AGPL runtime dependencies; and a pull-request title check for Conventional Commits.
- [x] 2.7 Write `CONTRIBUTING.md`: setup with uv, the D15 code rules, how to add a device profile and a protocol, fixture formats (spaced hex, `>`/`<` dialogues), the dependency budget with a one-line justification per runtime dependency, and the Conventional Commits title format.

## 3. Configuration and events

- [x] 3.1 Pydantic models for `emupos.yaml` (schema, api, devices, connections, printer drawer settings, scanner options) that reject unknown keys and report errors with exact paths.
- [x] 3.2 Configuration discovery (`--config`, then `./emupos.yaml`), schema-version checks (newer schema fails with an upgrade message), defaults and relative-path resolution, and cross-field checks (duplicate ports and links, TCP port equal to the API port, keyboard scanner with connections).
- [x] 3.3 Device profile model and loader for built-in profiles and profile file paths; ship `epson-tm-t20iii`, `xprinter-xp80t` (Arabic code pages marked unverified), `rongta-rp326` and `toledo8217-15kg`.
- [x] 3.4 Built-in `--demo` configuration (printer on TCP 9100 and keyboard scanner everywhere; Toledo scale on a pty only on macOS/Linux).
- [x] 3.5 JSON Schema export from the models, and a test that the starter configuration and every built-in profile validate.
- [x] 3.6 Event types and in-process publish/subscribe (`events.py`) with the event names from the specs; each event carries type, device id, UTC timestamp and data.

## 4. Device connections

- [x] 4.1 TCP listener transport: bind (default 127.0.0.1), several simultaneous clients, replies routed to the requesting client, and a startup failure that names the port when it is unavailable.
- [x] 4.2 pty transport (macOS/Linux): raw pty pair, slave kept open for reconnects, private link directory, stale link replacement, and link removal on shutdown; wrap as asyncio streams.
- [x] 4.3 Serial framing observation: poll the host settings on the pty, emit `connection.framing-mismatch` once per distinct framing, and warn without blocking data (macOS: baud, data bits, parity; Linux: baud only).
- [x] 4.6 Existing serial device paths on macOS/Linux (`serial: { port: /dev/ttyUSB0 }`, tty0tty), opened raw with the profile's framing; and pty link ownership so a second `emupos run` cannot take over or delete a running simulator's link.
- [ ] 4.4 Existing-port serial transport (Windows COM and any tty path) using the backend chosen in 1.1; a missing port fails startup with a message naming com0com and `emupos doctor`.
- [x] 4.5 Connection events, clean shutdown on Ctrl+C that releases ports and links, and a binary transparency test sending all 256 byte values in both directions over TCP and pty.

## 5. Receipt printer

- [x] 5.1 Incremental ESC/POS tokenizer: commands split across reads, unknown bytes produce `printer.command.unknown`, real-time byte patterns inside other commands' data are not misread, and incomplete commands at connection close are dropped with an event; fuzz with Hypothesis.
- [x] 5.2 Printer state (paper, cover, online, drawer pin level, faults) and real-time handling: `DLE EOT 1–4` replies computed from state and answered even while printing is blocked.
- [x] 5.3 `GS r` and Automatic Status Back (`GS a`) per connection, pushing status on enable and on every change.
- [x] 5.4 Print model for the supported command set: text styles, alignment, sizes, feeds, line spacing, cuts, and initialization; each command cites its manual section and has a fixture.
- [x] 5.5 Bitmap fonts: choose open-licensed fonts for Font A (12×24) and Font B (9×17), record their licences in `NOTICE`, and generate glyph tables for the supported code pages.
- [x] 5.6 1-bit renderer at the profile's dot width: text layout and wrapping, raster images (`GS v 0`), bit images (`ESC *`), barcodes (`GS k`) and QR codes (`GS ( k`) scaled to requested module sizes.
- [x] 5.7 Code-page selection with vendor number mapping from the profile; code pages without glyph tables render placeholders, decode in the text dump where a mapping exists, and emit `printer.codepage.unsupported`.
- [x] 5.8 Job boundaries (cut, connection close, idle timeout), per-connection job settings with shared printer state, and receipt storage (unique id, PNG and text dump in `receipts_dir`) emitting `printer.job.completed`.
- [x] 5.9 Fault behaviour: `paper-out`, `cover-open` and `offline` hold print data until the last is cleared; `paper-near-end` still prints; faults emit `printer.status.changed`.
- [x] 5.10 Golden cases under `escpos/cases/` (from 1.4 plus hand-written ones) with PNG and text snapshots, and a raster benchmark case that fails CI if rendering a large image job regresses markedly.

- [ ] 5.11 Layout commands found in real traffic: HT with ESC D tab positions, ESC SP, GS L, GS W, ESC $, ESC \\, and buffered graphics (GS ( L / GS 8 L functions 112 and 50), each with a fixture.

## 6. Cash drawer

- [x] 6.1 `ESC p` on pin 2 or pin 5 opens the printer's drawer (waiting behind blocking faults), and `DLE DC4 fn 1` opens it immediately; `drawer.opened` is emitted only on a closed-to-open change.
- [x] 6.2 Drawer sensor level per `sensor_open_level` reflected in `DLE EOT 1`, `GS r 2` and Automatic Status Back; closing emits `drawer.closed`; the drawer never closes by itself.

## 7. Weight scale

- [x] 7.1 Scale state in integer grams (gross, tare, net, stable, capacity from the profile), settling from unstable to stable with an injected clock, and zero/tare rules (refused while in motion).
- [x] 7.2 Toledo 8217 protocol as a pure function: `W` weight replies formatted per profile, the status reply for motion, over capacity and under zero, bad-command status for unrecognised commands, ignored CR/LF, and the `Ehello` echo probe with `F`.
- [x] 7.3 Dialogue fixtures for every scenario in the weight-scale spec, plus Hypothesis fuzzing of the request parser.
- [ ] 7.4 Conformance check: run Odoo's public Toledo 8217 driver as a black-box client against the pty (local, documented script; no LGPL code copied into the repository); record the result in `docs/protocols/toledo8217.md`.

## 8. Weighed-item barcodes

- [x] 8.1 Layout pattern parser and validation (length, literal prefix, single final check position, weight or price field), with presets `weight-21` and `price-23`.
- [x] 8.2 Value encoding with field-overflow errors, the EAN-13 check digit, and tests against known valid EAN-13 codes.
- [x] 8.3 PNG barcode image output with human-readable digits.

## 9. Barcode scanner

- [x] 9.1 Scan request handling: validation, one scan at a time per scanner, countdown, delivery event with scan id, and serial-mode delivery (data bytes plus suffix).
- [ ] 9.2 Windows keyboard injector: `SendInput` with US-layout virtual-key codes, a Unicode mode, inter-key delay and suffix, plus a warning when Windows reports fewer keystrokes accepted than sent.
- [x] 9.3 macOS keyboard injector: `CGEventPost` with US-layout key codes and a Unicode mode, and an Accessibility trust check before every scan that fails with the settings path.
- [x] 9.4 Linux X11 keyboard injector via XTest, with clear failures when not on X11 (pointing to serial mode) or when libXtst is missing.
- [x] 9.5 Manual verification checklist per OS in `docs/`, since keystroke injection cannot run in CI.

## 10. Windows print queue

- [ ] 10.1 `emupos setup print-queue`: create the Standard TCP/IP port and `emupos-<device id>` queue with the Generic / Text Only driver via PowerShell; idempotent; clear failures for non-Windows, a missing TCP connection, missing administrator rights; roll back the port if queue creation fails.
- [ ] 10.2 `--remove`: delete the queue and port, succeeding when nothing exists and working without the simulator running.
- [ ] 10.3 Minimal SNMP v1/v2c GET/GETNEXT responder on 127.0.0.1:161 (Windows only, only when a printer has a TCP connection) answering the objects found in 1.3 from printer state, emitting `snmp.query.answered`.
- [ ] 10.4 Port 161 conflict handling: `emupos run` continues with an error naming the Windows SNMP Service, and doctor reports it according to whether a queue exists.
- [ ] 10.5 Verify on a Windows VM that bytes printed through the queue arrive unchanged and that faults change the queue status; document the one-way limitation in `docs/windows-print-queue.md`.

## 11. Control API

- [x] 11.1 FastAPI app under `/api/v1` bound per configuration, with the non-loopback warning, API port conflict handling, health and OpenAPI endpoints.
- [x] 11.2 Browser-request protection: refuse `Origin` headers, non-loopback `Host` headers and non-JSON bodies, with tests for each.
- [x] 11.3 Error body and status codes (404, 409 `wrong_device_type`, 415, 422, 500 without stack traces).
- [x] 11.4 Device listing and description with state fields per device type.
- [x] 11.5 Endpoints for faults, scale weight/zero/tare, scans (202 with id), drawer close, receipts (list, metadata, `latest`, image, text) and weighed barcodes.
- [x] 11.6 Event WebSocket streaming published events as JSON.
- [x] 11.7 CI check that the OpenAPI document does not remove or change existing `/api/v1` paths or fields compared with the last release.

## 12. CLI

- [x] 12.1 Typer app with Rich output: command groups from the cli spec, help text, plain output when not a TTY, `--json`, `NO_COLOR`, errors on stderr, and the exit codes.
- [x] 12.2 `--api` / `EMUPOS_API` handling, exit status 3 when the simulator is unreachable, and device selection when `--device` is omitted.
- [x] 12.3 `emupos run`: load configuration or `--demo`, start devices, connections and API, print the banner with every endpoint and link, stream colour-coded events, and shut down cleanly.
- [x] 12.4 `devices`, `receipt list`, `receipt show` (including `--save`), `scan` (waits for the matching delivery event), `scale set|zero|tare` (parsing `1.25kg` / `1250g`), `fault set|clear` and `drawer close`.
- [x] 12.5 `barcode weighed` (works without the simulator), `config init|validate|schema`.
- [ ] 12.6 `emupos doctor` with pass/warn/fail checks and fixes: Python version, ports free, configuration valid, macOS Accessibility, Linux X11/libXtst, Windows COM ports and com0com, and print-queue/SNMP checks; `--json` output.
- [x] 12.7 `--version` output and shell completion install.
- [x] 12.8 End-to-end test: run the demo configuration, print a fixture receipt over TCP, open the drawer, set a fault and read status bytes, and fetch the receipt through the CLI.

## 13. Documentation

- [x] 13.1 `README.md`: what emupos is, the two sides (a POS talks to emupos only through real device protocols; the CLI, and optionally the API for automated tests, replace the physical actions on hardware, with a "real hardware → emupos command" table), install methods (`uv tool install`, `uvx`, `pipx`, `pip`), a five-minute quickstart per OS, and the hard limits table (virtual serial on Windows, ports not listed in enumeration, USB not emulated, Wayland, macOS Accessibility, one-way print queue, approximate glyphs).
- [ ] 13.2 Setup guides: `docs/windows-serial.md` (com0com and Secure Boot), `docs/macos-accessibility.md`, `docs/linux-x11.md`, `docs/windows-print-queue.md`.
- [x] 13.3 Protocol notes in `docs/protocols/` for ESC/POS status bits and Toledo 8217, citing sources.
- [x] 13.4 `docs/configuration.md`: human-readable reference for every `emupos.yaml` key and the device profile format, with a complete example per device type and a pointer to `emupos config schema` for editor autocomplete.
- [x] 13.5 `docs/automation.md`: using the control API from automated tests (inject a fault, set a weight, trigger a scan, fetch the latest receipt), with `curl`, Node and Python examples and a GitHub Actions workflow that starts `emupos run` in the background and waits for `/api/v1/health`; restates that POS code never uses the API.
- [x] 13.6 `docs/cli.md` generated from the Typer app, plus a CI step that regenerates it and fails when the committed file is out of date.
- [x] 13.7 `docs/README.md` index linking every guide, and links to it from the main `README.md`.
- [x] 13.8 `SECURITY.md`: supported versions, private vulnerability reporting through GitHub security advisories, and the local API's threat model (localhost only, browser-request protection, no authentication).
- [ ] 13.9 `CODE_OF_CONDUCT.md` (Contributor Covenant) with the maintainer contact for reports.
- [x] 13.10 `.github/ISSUE_TEMPLATE/`: bug report (asks for `emupos doctor --json` output, OS, config and a hex capture if relevant), device or protocol request (model, manual link, transport), and profile correction (e.g. code-page numbers, with a self-test page photo); plus `config.yml` pointing security reports to `SECURITY.md`.
- [x] 13.11 `.github/pull_request_template.md`: Conventional Commit title reminder, linked issue, checklist for tests and fixtures added, manual section cited for new commands, and docs updated.

## 14. Release pipeline

- [x] 14.1 release-please configuration for a Python package on the `main` branch, generating `CHANGELOG.md` with a `⚠ BREAKING CHANGES` section and bumping the `pyproject.toml` version.
- [x] 14.2 `release.yml` on `v*` tags: fail if the tag and package version differ, `uv build`, install the built wheel on Windows/macOS/Linux and smoke-test (`emupos --version`, `emupos doctor --json` produces valid JSON, render a fixture receipt), then publish.
- [x] 14.3 Publish to PyPI with Trusted Publishing and attestations, and create the GitHub Release from the changelog entry.
- [ ] 14.4 Maintainer setup (manual): create the `emupos` GitHub organization and repository, and register the PyPI Trusted Publisher for the release workflow.
- [ ] 14.5 Cut the first release and verify `uvx emupos run --demo` works on Windows, macOS and Linux from PyPI.
