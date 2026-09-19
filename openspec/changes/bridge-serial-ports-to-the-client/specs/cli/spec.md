## ADDED Requirements

### Requirement: Bridge command

`emupos bridge DEVICE [--tcp ADDRESS] [--port COM_PORT] [--link PATH]` SHALL relay a device's `tcp` connection to a serial port on the machine the command runs on, as defined by the device-connections capability, and SHALL keep running until stopped or until the simulator goes away.

On starting it SHALL print the path the POS is to open and the framing the device expects. When the simulator reports a framing mismatch it SHALL show the same warning in its own output. It SHALL exit with status 0 when stopped by the user, 1 when the simulator goes away or the port cannot be created, 2 for a usage error, and 3 when the control API cannot be reached, matching the exit codes of every other command.

#### Scenario: Announcing the port

- **WHEN** the user runs `emupos bridge deli` against a running simulator
- **THEN** it prints the link path to open and the expected framing, and keeps running

#### Scenario: Stopped by the user

- **WHEN** the user presses Ctrl+C
- **THEN** the port and its link are removed and it exits with status 0

#### Scenario: The simulator goes away

- **GIVEN** a running bridge
- **WHEN** the simulator stops answering
- **THEN** it removes the port, says the simulator is gone, and exits with status 1

#### Scenario: Unknown device

- **WHEN** the user runs `emupos bridge nope`
- **THEN** it exits with status 1 and prints the API's message and fix

## MODIFIED Requirements

### Requirement: Command set and help

The `emupos` command SHALL provide the commands `run`, `devices`, `receipt list`, `receipt show`, `scan`, `scale set`, `scale zero`, `scale tare`, `fault set`, `fault clear`, `drawer close`, `bridge`, `barcode weighed`, `config init`, `config validate`, `config schema`, `doctor` and `setup print-queue`, and the options `--version` and `--install-completion`. Every command and command group SHALL accept `--help`, which SHALL describe its arguments and options and exit with status 0.

#### Scenario: Help for a command

- **WHEN** the user runs `emupos scale set --help`
- **THEN** it exits with status 0 and describes the `VALUE` argument and the `--device` and `--unstable` options
