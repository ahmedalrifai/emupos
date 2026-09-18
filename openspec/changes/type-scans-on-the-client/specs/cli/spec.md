## MODIFIED Requirements

### Requirement: Scan command

`emupos scan DATA [--device ID] [--countdown N] [--unicode]` SHALL request a scan of `DATA`, with a countdown of `N` seconds that defaults to 3. It SHALL validate `DATA` with the scanner's rules before any countdown starts. In an interactive terminal it SHALL display the remaining countdown so the user is able to focus the POS window. For a keyboard-mode scanner the countdown SHALL run in the command itself; when it ends, if keyboard focus is on the terminal application that runs the command (detected on macOS and on Linux X11, including through tmux), the command SHALL cancel the scan without requesting it, exit with status 1 and tell the user to click the POS window during the countdown, because the barcode and its Enter would otherwise run as a shell command. When focus cannot be determined the scan SHALL proceed. After the request is accepted the command SHALL wait for the `scanner.scan.delivered` event whose `id` matches the accepted scan, and exit with status 0 when it arrives. It SHALL exit with status 1 when the scan is refused, printing the error's message and fix, or when the delivery event has not arrived 10 seconds after typing was due to finish (the countdown plus `inter_key_delay_ms` for each keystroke), in which case the message SHALL tell the user to check the `emupos run` output. `--unicode` SHALL request exact-character delivery.

For a scanner whose `typed_by` is `client`, the command SHALL type the scan itself on the machine it runs on:

1. it SHALL check that this machine's keyboard is ready **before** the countdown, and exit with status 1 printing that check's message and fix when it is not;
2. it SHALL run the countdown and the focus check as above, so a cancelled scan is still never requested;
3. it SHALL request the scan, press the keys of the returned plan in order with the returned inter-key delay, and then report the outcome to the simulator;
4. it SHALL wait for the `scanner.scan.delivered` event as above.

When the operating system accepted fewer keys than the plan contains, the command SHALL report the scan as failed with the number of keys accepted, and its own error message SHALL name that number instead of telling the user to check the `emupos run` output.

#### Scenario: Scan with countdown

- **GIVEN** the simulator runs one scanner `lane1`
- **WHEN** the user runs `emupos scan 6291041500213`
- **THEN** a countdown from 3 is displayed, the scan is delivered, and the command exits with status 0

#### Scenario: Terminal still focused

- **GIVEN** keyboard scanner `lane1` on macOS, and the terminal running the command still has keyboard focus when the countdown ends
- **WHEN** the user runs `emupos scan 6291041500213`
- **THEN** no scan is requested and nothing is typed
- **AND** the command exits with status 1, names the terminal and tells the user to click the POS window during the countdown

#### Scenario: Invalid data is refused before the countdown

- **GIVEN** keyboard scanner `lane1`
- **WHEN** the user runs `emupos scan كود42 --countdown 30` without `--unicode`
- **THEN** the command exits with status 1 at once, and the fix mentions `--unicode`

#### Scenario: Delivery not confirmed

- **GIVEN** keyboard scanner `lane1` on Windows, where Windows reports that the injected keystrokes were not accepted
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 0`
- **THEN** no `scanner.scan.delivered` event arrives for the scan
- **AND** the command exits with status 1 once 10 seconds have passed after typing was due to finish, and tells the user to check the `emupos run` output

#### Scenario: Scan refused

- **GIVEN** keyboard scanner `lane1` runs on a Linux Wayland session
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 0`
- **THEN** it exits with status 1 and the message points to serial scanner mode

#### Scenario: Client types the scan

- **GIVEN** scanner `lane1` with `typed_by: client`, and a simulator that cannot type
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 0` on a machine whose keyboard is ready
- **THEN** the keys of the returned plan are pressed on this machine in order
- **AND** the scan is reported as delivered, its `scanner.scan.delivered` event arrives, and the command exits with status 0

#### Scenario: Client keyboard not ready

- **GIVEN** scanner `lane1` with `typed_by: client`, and this machine has no Accessibility permission on macOS
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 30`
- **THEN** the command exits with status 1 at once, before any countdown, naming System Settings > Privacy & Security > Accessibility
- **AND** no scan is requested

#### Scenario: Focus check still cancels before the request

- **GIVEN** scanner `lane1` with `typed_by: client`, and the terminal running the command still has keyboard focus when the countdown ends
- **WHEN** the user runs `emupos scan 6291041500213`
- **THEN** no scan is requested and nothing is typed

#### Scenario: Client names refused keystrokes

- **GIVEN** scanner `lane1` with `typed_by: client` on Windows, where Windows reports that 7 of 14 keystrokes were accepted
- **WHEN** the user runs `emupos scan 6291041500213 --countdown 0`
- **THEN** the scan is reported as failed with 7 keys accepted
- **AND** the command exits with status 1 and its message names the 7 of 14 keystrokes and the privilege-level limitation

### Requirement: Devices and receipts commands

`emupos devices` SHALL show every device with its id, type, profile, connection endpoints and a summary of its state. For a keyboard scanner the summary SHALL state who types its scans. `emupos receipt list` SHALL show a printer's receipts newest first with their ids and completion times. `emupos receipt show [RECEIPT_ID]` SHALL default to `latest`, SHALL print the receipt's text dump, and with `--save PATH` SHALL write the receipt's PNG image to `PATH`. With `--json`, `receipt show` SHALL output the receipt metadata together with its text dump.

#### Scenario: Save latest receipt image

- **GIVEN** printer `front` has completed a receipt
- **WHEN** the user runs `emupos receipt show --save receipt.png`
- **THEN** `receipt.png` is written with the same bytes as `GET /api/v1/devices/front/receipts/latest/image`
- **AND** it exits with status 0

#### Scenario: No receipts yet

- **GIVEN** printer `front` has completed no receipts
- **WHEN** the user runs `emupos receipt show`
- **THEN** it exits with status 1 and states that `front` has no receipts yet

#### Scenario: Client-typed scanner is shown as such

- **GIVEN** scanner `lane1` with `mode: keyboard` and `typed_by: client`
- **WHEN** the user runs `emupos devices`
- **THEN** the summary for `lane1` states that its scans are typed by the client

### Requirement: Doctor diagnostics

`emupos doctor [--json]` SHALL run environment checks and print a checklist in which each check is shown as passed (✓), a warning (!) or failed (✗), and every warning or failure names its fix: a command to run, a settings path, a package to install, or a documentation page. The checks SHALL include: the Python version is 3.13 or newer; the configuration file, when one is found, is valid; the control API port and every configured TCP port are free or held by the running simulator; on macOS, the terminal running emupos has Accessibility permission; on Linux, an X11 display is available (a Wayland-only session fails with a fix pointing to serial scanner mode) and the libXtst library is loadable; on Windows, com0com is installed and working (including detection of a driver blocked by Secure Boot), every configured COM port exists, and the print-queue checks defined by the windows-print-queue capability. A missing prerequisite for a feature the configuration does not use SHALL be a warning, not a failure; a keyboard scanner with `typed_by: client` SHALL NOT by itself make the keyboard checks a failure, because that machine's keyboard is used only when `emupos scan` runs there. The command SHALL exit with status 1 when any check failed and 0 otherwise. With `--json` it SHALL output `{ "ok": <boolean>, "checks": [ { "id", "status": "pass" | "warn" | "fail", "message", "fix" } ] }`.

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

#### Scenario: Client-typed scanner on a machine that never types

- **GIVEN** the configuration contains only keyboard scanner `lane1` with `typed_by: client`, and libXtst is missing on Linux
- **WHEN** the user runs `emupos doctor`
- **THEN** the libXtst check is marked as a warning, not a failure
- **AND** it exits with status 0 when no other check failed

#### Scenario: Port in use by another program

- **GIVEN** a process other than emupos listens on port 9100 and printer `front` is configured on port 9100
- **WHEN** the user runs `emupos doctor`
- **THEN** the ports check fails and names port 9100

#### Scenario: JSON report

- **WHEN** the user runs `emupos doctor --json`
- **THEN** standard output is one JSON document with `ok` and a `checks` array whose entries have `id`, `status`, `message` and `fix`
