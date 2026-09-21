# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

The control page (issue #23) is plain HTML and vanilla JavaScript: no build step, no framework and no new runtime dependency. Its files ship inside the Python wheel and the control API serves them. The rest of emupos is Python 3.13 (FastAPI and uvicorn for the API, typer for the CLI); the documentation site is Zensical, built from `docs/`.

## Users

The primary user is a developer integrating their own POS with a receipt printer, cash drawer, weight scale and barcode scanner. They sit at their desk with the POS app open in one window and emupos beside it, testing by hand: running the printer out of paper, putting an item on the scale, pulling the scanner trigger, pushing the drawer shut, reading the receipt. Issue #23 also names demos, where the same developer shows their POS working with the devices.

Test scripts and CI use the control API directly; they are not users of the web surface.

## Product Purpose

emupos simulates point-of-sale hardware at the wire-protocol level, so a POS talks to it exactly as it talks to real devices. Success means the integration code tested against emupos is the code that runs with real hardware: moving to real devices changes the POS's device settings, not its code.

emupos has two sides that never mix. The device side is the real protocols. The operator side replaces the user's hands: the CLI, the control API, and the proposed control page.

## Positioning

Wire-level fidelity: the same bytes, the same behaviour and the same transport where possible. Printers answer real ESC/POS status requests and report real faults, the scale speaks Mettler Toledo 8217 on a real serial port, and keyboard scans arrive as real keystrokes in the focused window. It is not a mock inside the POS code. It runs first-class on Windows, macOS and Linux, on a laptop or in CI.

## Operating Context

- `emupos run` in one terminal starts the devices and prints every event live; `emupos` commands in a second terminal perform the physical actions (the table in `docs/README.md`). The control page is meant to replace that second terminal for demos and exploratory testing.
- The page sits beside the POS app, often in a narrow window, not full-screen.
- Keyboard-mode scans type into whichever window has focus. When a scan lands, the focused window should be the POS, not the page, which is why scans have a countdown.
- In the Docker image the scanner is `typed_by: client`: `emupos scan` types the keys on the user's machine. A browser cannot type into another window, so the page cannot perform those scans.
- The control API listens on `127.0.0.1:8765`, has no authentication, and today refuses any request carrying an `Origin` header. A page served by the API can read (GET) but cannot write or open the event stream until that rule changes (explored 2026-09-21; not yet decided).

## Capabilities and Constraints

- Devices: receipt printer (profiles Epson TM-T20III, Xprinter XP-80T, Rongta RP326) with faults `paper-near-end`, `paper-out`, `cover-open` and `offline`; one cash drawer per printer; Mettler Toledo 8217 scale; barcode scanner in keyboard or serial mode; weighed-item EAN-13 barcodes.
- Physical actions on the control API: set a weight (stable or moving), zero, tare, trigger a scan with a countdown, set and clear faults, close the drawer, fetch receipts as PNG and text (`latest` alias), and the event stream at `/api/v1/events` (13 event types).
- The CLI stays the primary interface. The page is optional and off by default if it adds any risk to `emupos run` (issue #23).
- The page is an operator tool. A POS never uses it.
- It must not weaken the local-only posture described in `SECURITY.md`.
- Offline and self-contained: no CDN scripts, web fonts or analytics. Everything ships in the wheel and works without internet.
- The interface copy is English. Device data can be Arabic or right-to-left (Arabic code pages 720, 864 and 1256, Unicode scans, Arabic receipts) and must render correctly.
- The page uses the same words as the CLI and docs: device ids, fault names, event type names and the "physical actions" vocabulary.
- Event data and receipt text originate from whatever connects to the device ports, so they are untrusted input and are only ever rendered as text.
- Undecided, from the 2026-09-21 exploration of issue #23: how the page is enabled (leaning towards an `emupos run --ui` flag), the exact guard rule for same-origin requests, whether event lines show raw data or the CLI's readable summary, and the page's path.

## Brand Commitments

- The name is `emupos`, lowercase, which is also the CLI command and the PyPI package.
- No logo, colour palette or typeface exists.
- The existing docs set the voice: plain, exact, second person, framed in physical-world actions ("replaces your hands", "put 1.25 kg of tomatoes on the scale"). Errors state the problem and a fix.

## Evidence on Hand

- `emupos run --demo`: printer `front`, scale `deli` and scanner `lane1`, which is real data for any surface.
- Real receipt jobs captured from python-escpos, escpos-php, node-thermal-printer, receipt-printer-encoder, the Epson TM macOS driver and the Windows Generic / Text Only driver, including Arabic receipts: `src/emupos/printer/escpos/cases/captured/`.
- Documentation at https://emupos.readthedocs.io/ and the recorded API contract `docs/api/openapi-v1.json`.
- There are no screenshots, users, testimonials or adoption numbers. Do not invent them.

## Product Principles

1. **Two sides never mix.** The POS reaches emupos only through device protocols. Every operator surface replaces the user's hands, never the POS.
2. **Behave like the device.** That includes its refusals: a scale in motion refuses tare. Always say why and how to fix it.
3. **The CLI leads.** Other operator surfaces are optional and use its words.
4. **Local and safe by default.** Nothing new widens what a web page or another machine can do.
5. **Small on purpose.** Every runtime dependency is justified. A few lines of code beat a library.
