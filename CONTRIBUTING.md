# Contributing to emupos

Thanks for helping. emupos pretends to be POS hardware on the wire, so most contributions are one of three kinds: a **device profile** (data), a **protocol or command** (small pure code), or a **platform fix** (OS-specific code in `transports/`).

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs the right Python for you.

```sh
git clone https://github.com/emupos/emupos.git
cd emupos
uv sync
uv run emupos --version
```

Run the same checks as CI before opening a pull request:

```sh
uv run ruff format      # format
uv run ruff check       # lint, import order, security rules, the I/O boundary
uv run pyright          # strict type checking
uv run pytest           # tests (they live next to the code)
```

## How the code is organised

```
src/emupos/
├── cli/          the `emupos` command (Typer)
├── daemon.py     the only wiring file: config → devices → transports → api
├── config.py     emupos.yaml and profile loading/validation
├── events.py     events, device Output, event bus
├── api/          local control API (FastAPI)
├── transports/   everything that touches the OS: TCP, pty, COM ports, SNMP, keystrokes
├── printer/      receipt printer; escpos/ holds the ESC/POS tokenizer, status and renderer
├── drawer/       cash drawer
├── scale/        scale state; one folder per protocol (toledo8217/)
├── barcodes/     weighed-item EAN-13 barcodes
├── scanner/      barcode scanner
└── profiles/     built-in device profiles (YAML)
```

The rule that keeps this readable: **device and protocol code is pure.** It receives state and bytes and returns an `Output` (bytes to write, events to publish). Only `transports/`, `api/` and `daemon.py` may do I/O. Ruff enforces this: importing `asyncio`, `socket`, `ctypes`, `termios` or a serial library anywhere else fails lint.

Pure code never reads the clock. Functions that depend on time take `now` as an argument, so tests are instant and deterministic.

## Adding a device profile

Profiles are data. Copy the closest file in `src/emupos/profiles/printers/` or `src/emupos/profiles/scales/`, rename it after the model (`vendor-model.yaml`), and edit the values. Every value needs a source: add a comment naming the manual or spec sheet, and mark anything unconfirmed with `# UNVERIFIED`.

Then add the profile to the built-in profile test in `src/emupos/test_config.py` and run `uv run pytest`.

Found a wrong value in an existing profile (for example a code-page number)? Open a "profile correction" issue with a photo of the printer's self-test page.

## Adding a protocol or an ESC/POS command

1. Put the code in the device's folder, e.g. `src/emupos/scale/<protocol>/<protocol>.py`, as pure functions or a small class.
2. Cite the source for every command you handle in a one-line comment: manual name and section.
3. Add a test next to it, with a fixture that exercises the command.
4. Register it with one line in the device's registry (a plain dict).

### Fixture formats

Protocol bytes are always written as spaced hex, never as escaped strings:

```python
request = bytes.fromhex("10 04 01")
```

Dialogue fixtures (`dialogues/*.txt`) list what the POS sends (`>`) and what the device replies (`<`):

```
# stable weight of 1.250 kg
> 57
< 02 30 31 2e 32 35 30 0d
```

ESC/POS rendering cases live in `printer/escpos/cases/<family>/<case>/` as `input.hex`, `expected.png`, `expected.txt` and `notes.md`.

## Code rules

- Python 3.13+. Modern type hints only: `list[str]`, `X | None`. Pyright runs in strict mode.
- `@dataclass(frozen=True, slots=True)` for state snapshots and events.
- Status bits are `enum.IntFlag`, named as in the manual.
- Weights and money are integers (grams, minor currency units) or `Decimal`. Never `float`.
- Unknown or broken input from a POS never raises: real devices skip it, so we emit an event and continue. Exceptions are for operator mistakes (bad config, missing driver), and their message names the fix.
- OS-specific files stay small, and every error message says what to do next.
- Keep `__init__.py` files empty. Import from the module where code lives.
- No plugin systems, abstract base classes or dependency-injection frameworks. Add an interface when a second real implementation exists.

## Dependency budget

emupos keeps a small set of runtime dependencies, all permissively licensed (CI fails on GPL, LGPL or AGPL). A new runtime dependency needs a line here explaining why a few lines of code cannot replace it.

| Dependency | Why |
|---|---|
| typer (with rich) | The CLI: commands, styled output, shell completion |
| fastapi, uvicorn | The local control API, with request validation and an OpenAPI document |
| pydantic | Validates configuration, profiles and API bodies; exports JSON Schema |
| pyyaml | Reads configuration and profiles (safe loader only) |
| pillow | Renders receipts as 1-bit PNG images |
| segno | QR code matrices for printed QR codes |
| python-barcode | Bar patterns for printed 1D barcodes |
| pyobjc-framework-Quartz (macOS only) | Posts keyboard-wedge keystrokes |
| serialx (Windows only) | Asynchronous access to COM ports |

## Pull requests

Pull requests are squash-merged, and the title becomes the commit message that drives the version number and changelog. Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(scale): add NCI protocol` → new feature (minor release)
- `fix(printer): wrap Font B at 64 columns` → bug fix (patch release)
- `feat(config)!: rename receipts_dir` → breaking change

A CI check rejects titles that don't follow the format.

## Licence

By contributing you agree that your contribution is licensed under the [Apache License 2.0](LICENSE).
