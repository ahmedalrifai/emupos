## ADDED Requirements

### Requirement: Command set and help

The `emupos` command SHALL provide the commands `run`, `devices`, `receipt list`, `receipt show`, `scan`, `scale set`, `scale zero`, `scale tare`, `fault set`, `fault clear`, `drawer close`, `barcode weighed`, `config init`, `config validate`, `config schema`, `doctor` and `setup print-queue`, and the options `--version` and `--install-completion`. Every command and command group SHALL accept `--help`, which SHALL describe its arguments and options and exit with status 0.

#### Scenario: Help for a command

- **WHEN** the user runs `emupos scale set --help`
- **THEN** it exits with status 0 and describes the `VALUE` argument and the `--device` and `--unstable` options

### Requirement: Output modes

When standard output is an interactive terminal, commands SHALL use styled output: colour, tables, panels, and colour-coded events. When standard output is not a terminal, commands SHALL write plain text with no ANSI escape sequences. When the `NO_COLOR` environment variable is set to a non-empty value, commands SHALL NOT use colour even in a terminal. The read commands `devices`, `receipt list`, `receipt show` and `doctor` SHALL accept `--json`, which SHALL write exactly one JSON document to standard output and nothing else. Error messages SHALL be written to standard error; with `--json` the error SHALL be written as the error body `{ "error": { "code", "message", "fix" } }`.

#### Scenario: Piped output is plain

- **GIVEN** the simulator is running
- **WHEN** the user runs `emupos devices | cat`
- **THEN** the output contains the device ids and no ANSI escape sequences

#### Scenario: NO_COLOR in a terminal

- **GIVEN** `NO_COLOR=1` is set
- **WHEN** the user runs `emupos devices` in an interactive terminal
- **THEN** the output contains no colour escape sequences

#### Scenario: JSON output

- **GIVEN** the simulator is running with devices `front`, `deli` and `lane1`
- **WHEN** the user runs `emupos devices --json`
- **THEN** standard output parses as one JSON document listing `front`, `deli` and `lane1`
- **AND** standard output contains nothing besides that document

### Requirement: Exit codes

Every command SHALL exit with status 0 on success, 1 when the requested operation failed (including an error returned by the control API or a check that failed), 2 for a usage error (unknown command or option, missing argument, or an argument value that is invalid on its face), and 3 when a command that needs the simulator is not able to reach the control API. For exit status 3 the message SHALL name the API URL that was tried and suggest starting the simulator with `emupos run`. For exit status 1 caused by an API error, the command SHALL print the error's `message` and, when present, its `fix`.

#### Scenario: Simulator not running

- **GIVEN** nothing is listening on `127.0.0.1:8765`
- **WHEN** the user runs `emupos devices`
- **THEN** it exits with status 3
- **AND** the message names `http://127.0.0.1:8765` and suggests `emupos run`

#### Scenario: Usage error

- **WHEN** the user runs `emupos scale set heavy`
- **THEN** it exits with status 2 and explains the accepted forms such as `1.25kg` and `1250g`

#### Scenario: API error

- **GIVEN** the simulator is running without a device named `nope`
- **WHEN** the user runs `emupos fault set nope paper-out`
- **THEN** it exits with status 1 and prints the API's message and fix for the unknown device

### Requirement: Control API address

Commands that talk to the simulator SHALL use the API base URL from the global `--api` option when given, otherwise from the `EMUPOS_API` environment variable when set, and otherwise `http://127.0.0.1:8765`. A value that is not an `http` or `https` URL SHALL be a usage error.

#### Scenario: Option overrides environment

- **GIVEN** `EMUPOS_API=http://127.0.0.1:9000` is set
- **WHEN** the user runs `emupos --api http://127.0.0.1:9001 devices`
- **THEN** the command sends its request to `http://127.0.0.1:9001`

#### Scenario: Environment variable

- **GIVEN** `EMUPOS_API=http://127.0.0.1:9000` is set and the simulator's API listens on port 9000
- **WHEN** the user runs `emupos devices`
- **THEN** it lists the devices from the simulator on port 9000

### Requirement: Device selection

Commands that act on a device of a specific type (`receipt list`, `receipt show`, `scan`, `scale set`, `scale zero`, `scale tare`, `drawer close` and `setup print-queue`) SHALL use the device given by `--device`. When `--device` is omitted and the running simulator has exactly one device of the needed type, the command SHALL use that device. When it has none, or more than one, the command SHALL exit with status 2 and list the ids of the devices of that type, or state that there are none.

#### Scenario: Single scale inferred

- **GIVEN** the simulator runs one scale `deli`
- **WHEN** the user runs `emupos scale set 1.25kg`
- **THEN** the weight of `deli` becomes 1250 grams

#### Scenario: Ambiguous printer

- **GIVEN** the simulator runs printers `front` and `kitchen`
- **WHEN** the user runs `emupos drawer close`
- **THEN** it exits with status 2 and lists `front` and `kitchen` as candidates for `--device`

### Requirement: Run command

`emupos run [--config PATH] [--demo]` SHALL load the configuration, open every device connection, start the control API, and then print a startup summary listing each device's id, type and profile, each resolved connection endpoint (including serial link paths), and the API URL. It SHALL keep running and stream every event live, one line per event with the local time, device id, event type and a short human-readable summary, colour-coded by event family in a terminal. Warnings, such as a serial framing mismatch or an API bound to a non-loopback address, SHALL be shown distinctly from ordinary events. Ctrl+C SHALL stop the simulator as defined by the clean shutdown requirement of the device-connections capability.

#### Scenario: Startup summary

- **GIVEN** a configuration with printer `front` on `tcp: { port: 9100 }` and scale `deli` on `serial: { pty: true, link: deli }`
- **WHEN** the user runs `emupos run` on Linux
- **THEN** the output lists `front` with `127.0.0.1:9100`, `deli` with its link path under `$TMPDIR/emupos/`, and `http://127.0.0.1:8765`

#### Scenario: Live events

- **GIVEN** `emupos run` is running with printer `front`
- **WHEN** another terminal runs `emupos fault set front cover-open`
- **THEN** the `emupos run` output shows a line with the time, `front` and `printer.status.changed`

#### Scenario: Piped event stream

- **WHEN** the output of `emupos run` is redirected to a file and a scan is delivered on `lane1`
- **THEN** the file contains a plain-text line with `lane1` and `scanner.scan.delivered` and no ANSI escape sequences

### Requirement: Devices and receipts commands

`emupos devices` SHALL show every device with its id, type, profile, connection endpoints and a summary of its state. `emupos receipt list` SHALL show a printer's receipts newest first with their ids and completion times. `emupos receipt show [RECEIPT_ID]` SHALL default to `latest`, SHALL print the receipt's text dump, and with `--save PATH` SHALL write the receipt's PNG image to `PATH`. With `--json`, `receipt show` SHALL output the receipt metadata together with its text dump.

#### Scenario: Save latest receipt image

- **GIVEN** printer `front` has completed a receipt
- **WHEN** the user runs `emupos receipt show --save receipt.png`
- **THEN** `receipt.png` is written with the same bytes as `GET /api/v1/devices/front/receipts/latest/image`
- **AND** it exits with status 0

#### Scenario: No receipts yet

- **GIVEN** printer `front` has completed no receipts
- **WHEN** the user runs `emupos receipt show`
- **THEN** it exits with status 1 and states that `front` has no receipts yet

### Requirement: Scan command

`emupos scan DATA [--device ID] [--countdown N] [--unicode]` SHALL request a scan of `DATA`, with a countdown of `N` seconds that defaults to 3. In an interactive terminal it SHALL display the remaining countdown so the user is able to focus the POS window. After the request is accepted it SHALL wait for the `scanner.scan.delivered` event whose `id` matches the accepted scan, and exit with status 0 when it arrives. It SHALL exit with status 1 when the scan is refused, printing the error's message and fix, or when the delivery event has not arrived 10 seconds after typing was due to finish (the countdown plus `inter_key_delay_ms` for each keystroke), in which case the message SHALL tell the user to check the `emupos run` output. `--unicode` SHALL request exact-character delivery.

#### Scenario: Scan with countdown

- **GIVEN** the simulator runs one scanner `lane1`
- **WHEN** the user runs `emupos scan 6291041500213`
- **THEN** a countdown from 3 is displayed, the scan is delivered, and the command exits with status 0

#### Scenario: Delivery not confirmed

- **GIVEN** keyboard scanner `lane1` on Windows, where Windows reports that the injected keystrokes were not accepted
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 0`
- **THEN** no `scanner.scan.delivered` event arrives for the scan
- **AND** the command exits with status 1 once 10 seconds have passed after typing was due to finish, and tells the user to check the `emupos run` output

#### Scenario: Scan refused

- **GIVEN** keyboard scanner `lane1` runs on a Linux Wayland session
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 0`
- **THEN** it exits with status 1 and the message points to serial scanner mode

### Requirement: Scale commands

`emupos scale set VALUE` SHALL set the scale weight, where `VALUE` is a decimal number followed by the unit `kg` or `g` (for example `1.25kg` or `1250g`), converted exactly to integer grams without floating-point rounding. The reading SHALL be stable unless `--unstable` is given. A value that is not a whole number of grams, or that has another unit or no unit, SHALL be a usage error. `emupos scale zero` and `emupos scale tare` SHALL zero and tare the scale.

#### Scenario: Kilograms

- **WHEN** the user runs `emupos scale set 1.25kg --device deli`
- **THEN** scale `deli` shows 1250 grams, stable

#### Scenario: Unstable grams

- **WHEN** the user runs `emupos scale set 800g --unstable --device deli`
- **THEN** scale `deli` shows 800 grams, not stable

#### Scenario: Sub-gram precision

- **WHEN** the user runs `emupos scale set 1.2505kg`
- **THEN** it exits with status 2 and states that weights are whole grams

#### Scenario: Tare refused

- **GIVEN** scale `deli` refuses tare in its current state
- **WHEN** the user runs `emupos scale tare --device deli`
- **THEN** it exits with status 1 and prints the reason given by the simulator

### Requirement: Fault and drawer commands

`emupos fault set DEVICE FAULT` SHALL activate and `emupos fault clear DEVICE FAULT` SHALL clear a printer fault, where `FAULT` is one of `paper-near-end`, `paper-out`, `cover-open` or `offline`; any other fault name SHALL be a usage error that lists the valid names. `emupos drawer close [--device ID]` SHALL close the printer's cash drawer.

#### Scenario: Set and clear a fault

- **WHEN** the user runs `emupos fault set front paper-out` and then `emupos fault clear front paper-out`
- **THEN** both commands exit with status 0 and `emupos devices` shows no active faults on `front`

#### Scenario: Unknown fault name

- **WHEN** the user runs `emupos fault set front jammed`
- **THEN** it exits with status 2 and lists `paper-near-end`, `paper-out`, `cover-open` and `offline`

#### Scenario: Close drawer

- **GIVEN** the drawer of printer `front` is open
- **WHEN** the user runs `emupos drawer close`
- **THEN** it exits with status 0 and the `emupos run` output shows `drawer.closed` for `front`

### Requirement: Commands that do not need the simulator

`config init`, `config validate`, `config schema`, `doctor`, `barcode weighed`, `--version` and `--install-completion` SHALL work without a running simulator and SHALL never exit with status 3. The `config` commands SHALL behave as defined by the configuration capability.

#### Scenario: Validate while stopped

- **GIVEN** the simulator is not running and `emupos.yaml` is valid
- **WHEN** the user runs `emupos config validate`
- **THEN** it exits with status 0

### Requirement: Doctor diagnostics

`emupos doctor [--json]` SHALL run environment checks and print a checklist in which each check is shown as passed (✓), a warning (!) or failed (✗), and every warning or failure names its fix: a command to run, a settings path, a package to install, or a documentation page. The checks SHALL include: the Python version is 3.13 or newer; the configuration file, when one is found, is valid; the control API port and every configured TCP port are free or held by the running simulator; on macOS, the terminal running emupos has Accessibility permission; on Linux, an X11 display is available (a Wayland-only session fails with a fix pointing to serial scanner mode) and the libXtst library is loadable; on Windows, com0com is installed and working (including detection of a driver blocked by Secure Boot), every configured COM port exists, and the print-queue checks defined by the windows-print-queue capability. A missing prerequisite for a feature the configuration does not use SHALL be a warning, not a failure. The command SHALL exit with status 1 when any check failed and 0 otherwise. With `--json` it SHALL output `{ "ok": <boolean>, "checks": [ { "id", "status": "pass" | "warn" | "fail", "message", "fix" } ] }`.

#### Scenario: macOS without Accessibility permission

- **GIVEN** the configuration contains keyboard scanner `lane1` and the terminal lacks Accessibility permission on macOS
- **WHEN** the user runs `emupos doctor`
- **THEN** the Accessibility check is marked ✗ with the fix System Settings > Privacy & Security > Accessibility
- **AND** it exits with status 1

#### Scenario: Unused prerequisite is a warning

- **GIVEN** the configuration contains no keyboard scanner and libXtst is missing on Linux
- **WHEN** the user runs `emupos doctor`
- **THEN** the libXtst check is marked as a warning naming the package to install
- **AND** it exits with status 0 when no other check failed

#### Scenario: Port in use by another program

- **GIVEN** a process other than emupos listens on port 9100 and printer `front` is configured on port 9100
- **WHEN** the user runs `emupos doctor`
- **THEN** the ports check fails and names port 9100

#### Scenario: JSON report

- **WHEN** the user runs `emupos doctor --json`
- **THEN** standard output is one JSON document with `ok` and a `checks` array whose entries have `id`, `status`, `message` and `fix`

### Requirement: Version and shell completion

`emupos --version` SHALL print `emupos` followed by the installed package version and exit with status 0. `emupos --install-completion` SHALL install tab completion for the current shell (bash, zsh, fish or PowerShell), completing command names, option names and fault names.

#### Scenario: Version

- **WHEN** the user runs `emupos --version`
- **THEN** it prints `emupos X.Y.Z`, where `X.Y.Z` is the installed package version, and exits with status 0

#### Scenario: Completion in zsh

- **GIVEN** the user has run `emupos --install-completion` in zsh and opened a new shell
- **WHEN** the user types `emupos fault set front pa` and presses Tab
- **THEN** the shell offers `paper-near-end` and `paper-out`
