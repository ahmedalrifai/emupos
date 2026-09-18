# Configuration

## Purpose

The YAML configuration file, device profiles, schema versioning and JSON Schema export.
## Requirements
### Requirement: Configuration file discovery

`emupos run` SHALL read its configuration from the file given by `--config`, and otherwise from `emupos.yaml` in the current working directory. `emupos config validate` SHALL apply the same rule, using its `PATH` argument in place of `--config`. When no configuration file is found, the command SHALL exit with status 2 and a message naming the path it looked for and suggesting `emupos config init`. `emupos run --demo` SHALL read no file, and giving both `--demo` and `--config` SHALL be a usage error that exits with status 2.

#### Scenario: Explicit path

- **GIVEN** `/work/pos/lane1.yaml` is a valid configuration
- **WHEN** the user runs `emupos run --config /work/pos/lane1.yaml` from any directory
- **THEN** the simulator starts the devices defined in `/work/pos/lane1.yaml`

#### Scenario: Default file in the working directory

- **GIVEN** the current directory contains a valid `emupos.yaml`
- **WHEN** the user runs `emupos run` without `--config`
- **THEN** the simulator starts the devices defined in `./emupos.yaml`

#### Scenario: No configuration found

- **GIVEN** the current directory contains no `emupos.yaml`
- **WHEN** the user runs `emupos run`
- **THEN** it exits with status 2
- **AND** the message names `emupos.yaml` in the current directory and suggests `emupos config init`

#### Scenario: Demo and config together

- **WHEN** the user runs `emupos run --demo --config emupos.yaml`
- **THEN** it exits with status 2 and states that `--demo` and `--config` are mutually exclusive

### Requirement: Schema version

Every configuration file SHALL declare a top-level integer `schema`. This change defines schema version `1`. A missing `schema`, or a value that is not a positive integer, SHALL be a validation error. A `schema` higher than the highest version the installed emupos supports SHALL fail with a message stating the file's schema version, the highest supported version, and that emupos needs to be upgraded to read the file.

#### Scenario: Newer schema than supported

- **GIVEN** `emupos.yaml` starts with `schema: 2`
- **WHEN** the user runs `emupos config validate`
- **THEN** it exits with status 1
- **AND** the message states that the file uses schema 2, this emupos supports up to schema 1, and emupos needs to be upgraded

#### Scenario: Missing schema

- **GIVEN** `emupos.yaml` has no `schema` key
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at path `schema`

#### Scenario: Schema given as text

- **GIVEN** `emupos.yaml` contains `schema: "1"`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at path `schema` stating that an integer is required

### Requirement: Validation with exact paths

The configuration SHALL be fully validated when it is loaded, before any device, connection or the control API starts. Validation SHALL report every problem found, not only the first. Each error SHALL name its exact location using keys and zero-based list indexes, such as `devices[1].connections[0].tcp.port`, and SHALL state what was expected. An invalid configuration SHALL make `emupos run` exit with status 1 without opening any port or link. A file that is not well-formed YAML SHALL be reported with the line and column of the problem. Configuration and profile files SHALL be read as plain data: language-specific object tags such as `!!python/object` SHALL be rejected as errors and SHALL NOT construct objects or run code.

#### Scenario: Out-of-range port

- **GIVEN** the second device's first connection is `tcp: { port: 70000 }`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[1].connections[0].tcp.port` stating that a port from 1 to 65535 is expected

#### Scenario: All errors are reported together

- **GIVEN** a configuration where `devices[0].type` is `drawer` and `devices[1].connections[0].tcp.port` is `0`
- **WHEN** the user runs `emupos config validate`
- **THEN** both errors are printed in the same run

#### Scenario: Invalid configuration opens nothing

- **GIVEN** a configuration with a printer on `tcp: { port: 9100 }` and an invalid scale entry
- **WHEN** the user runs `emupos run`
- **THEN** it exits with status 1
- **AND** nothing was listening on port 9100 at any time during the run

#### Scenario: Malformed YAML

- **GIVEN** line 7 of `emupos.yaml` has inconsistent indentation
- **WHEN** the configuration is loaded
- **THEN** the error names line 7 and the column of the problem

#### Scenario: Object tags are rejected

- **GIVEN** `emupos.yaml` contains a value tagged `!!python/object/apply:os.system`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error naming the tag
- **AND** no command is executed

### Requirement: Unknown keys are rejected

A key that the schema does not define SHALL be a validation error at every level of the configuration file and of profile files, reported with its full path.

#### Scenario: Misspelled device key

- **GIVEN** the first device contains `conections:` instead of `connections:`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an unknown-key error at `devices[0].conections`

#### Scenario: Misspelled nested key

- **GIVEN** the configuration contains `api: { hots: 127.0.0.1 }`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an unknown-key error at `api.hots`

### Requirement: Device definitions

Each entry of `devices` SHALL have an `id` and a `type` of `printer`, `scale` or `scanner`. Device ids SHALL be unique and SHALL consist of lowercase ASCII letters, digits and hyphens, starting with a letter or digit. A `printer` or `scale` SHALL require a `profile` for its own device type and at least one connection. A `scanner` SHALL require `mode` `keyboard` or `serial`; a `serial` scanner SHALL require at least one connection, and a `keyboard` scanner SHALL NOT have connections. A scanner `suffix` SHALL be one of `enter`, `tab` or `none`, and `drawer.sensor_open_level` SHALL be `high` or `low`. A keyboard scanner MAY set `typed_by` to `server` or `client`, defaulting to `server`; `typed_by` on a `serial` scanner SHALL be rejected, because a serial scan presses no keys. The cash drawer SHALL NOT be declared as a device; it SHALL be configured through the `drawer` key of its printer.

#### Scenario: Duplicate device id

- **GIVEN** two devices both have `id: front`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[1].id` stating that `front` is already used by `devices[0]`

#### Scenario: Drawer declared as a device

- **GIVEN** a device has `type: drawer`
- **WHEN** the configuration is loaded
- **THEN** validation fails, lists `printer`, `scale` and `scanner` as the valid types, and states that a drawer is configured on its printer

#### Scenario: Profile of the wrong device type

- **GIVEN** device `front` has `type: printer` and `profile: toledo8217-15kg`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[0].profile` stating that `toledo8217-15kg` is a scale profile

#### Scenario: Keyboard scanner with connections

- **GIVEN** device `lane1` has `mode: keyboard` and a `tcp` connection
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at the `connections` key of `lane1`

#### Scenario: Client typing on a serial scanner

- **GIVEN** device `lane2` has `mode: serial` and `typed_by: client`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at the `typed_by` key of `lane2` stating that a serial scanner types no keys

#### Scenario: Keyboard scanner defaults to server typing

- **GIVEN** device `lane1` has `mode: keyboard` and no `typed_by`
- **WHEN** the configuration is loaded
- **THEN** its `typed_by` is `server`

#### Scenario: Unknown typed_by value

- **GIVEN** device `lane1` has `mode: keyboard` and `typed_by: cli`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at the `typed_by` key of `lane1` naming `server` and `client`

### Requirement: Connection entries

Each item of a device's `connections` list SHALL contain exactly one of `tcp` or `serial`. A `tcp` entry SHALL require `port` between 1 and 65535 and SHALL accept an optional `host`. A `serial` entry SHALL contain exactly one of `pty: true` or `port` (a port name such as `COM5` or a device path such as `/dev/ttyUSB0`). `link` SHALL be accepted only together with `pty: true` and SHALL default to the device id. Across the whole configuration, no two TCP listeners SHALL use the same port on the same host, no TCP listener SHALL use the control API port, and no two `pty: true` connections SHALL use the same `link`.

#### Scenario: Both kinds in one entry

- **GIVEN** a connection entry contains both `tcp: { port: 9100 }` and `serial: { pty: true }`
- **WHEN** the configuration is loaded
- **THEN** validation fails stating that each connection entry needs exactly one of `tcp` or `serial`

#### Scenario: Link defaults to the device id

- **GIVEN** scale `deli` has the connection `serial: { pty: true }`
- **WHEN** `emupos run` starts on macOS
- **THEN** the serial link is published as `$TMPDIR/emupos/deli`

#### Scenario: Duplicate TCP port

- **GIVEN** devices `front` and `kitchen` both have `tcp: { port: 9100 }`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error naming both connection paths and port 9100

#### Scenario: TCP port equals the API port

- **GIVEN** `api: { port: 8765 }` and device `front` has `tcp: { port: 8765 }`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error naming port 8765

### Requirement: Defaults and relative paths

Omitted optional settings SHALL take these defaults: `api.host` `127.0.0.1`; `api.port` `8765`; a `tcp` connection's `host` `127.0.0.1`; a printer's `job_idle_timeout_ms` `2000`, `receipts_dir` `./receipts`, and `drawer.sensor_open_level` as defined by the printer's profile; a scanner's `suffix` `enter` and `inter_key_delay_ms` `10`. Relative paths in a configuration file, such as `receipts_dir` or a profile file path, SHALL be resolved against the directory that contains the configuration file, not the current working directory.

#### Scenario: Minimal configuration

- **GIVEN** a configuration containing only `schema: 1` and one printer `front` with `profile: epson-tm-t20iii` and `tcp: { port: 9100 }`
- **WHEN** `emupos run` starts
- **THEN** the control API is served at `http://127.0.0.1:8765`
- **AND** printer `front` listens on `127.0.0.1:9100`

#### Scenario: Receipts directory relative to the file

- **GIVEN** `/work/pos/emupos.yaml` sets `receipts_dir: ./receipts`
- **WHEN** the user runs `emupos run --config /work/pos/emupos.yaml` from their home directory and a receipt completes
- **THEN** the receipt files are written under `/work/pos/receipts`

### Requirement: Device profiles

Printers and scales SHALL take their hardware characteristics from a device profile. emupos SHALL ship the built-in printer profiles `epson-tm-t20iii`, `xprinter-xp80t` and `rongta-rp326`, and the built-in scale profile `toledo8217-15kg`. A printer profile SHALL define the printable width in dots, the character cell size and columns of each font, the code-page number map, the default code page and the drawer sensor polarity. The profile of a device reachable over serial SHALL define its serial framing. A scale profile SHALL define its capacity, the resolution and formatting of its weight replies, and the settle time of an unstable reading. The `profile` value SHALL name a built-in profile or give the path of a user-provided YAML profile file (any value containing a path separator or ending in `.yaml` or `.yml`). A user-provided profile SHALL be validated against the same rules as built-in profiles, and its errors SHALL name the profile file and the path within it. An unknown profile name SHALL be a validation error that lists the built-in profiles of the device's type.

#### Scenario: Unknown profile name

- **GIVEN** device `front` has `type: printer` and `profile: epson-tm-t88`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[0].profile` listing `epson-tm-t20iii`, `xprinter-xp80t` and `rongta-rp326`

#### Scenario: User-provided profile

- **GIVEN** `/work/pos/emupos.yaml` has a printer with `profile: ./profiles/my-80mm.yaml` and that file is a valid printer profile
- **WHEN** `emupos run --config /work/pos/emupos.yaml` starts
- **THEN** the printer uses the characteristics in `/work/pos/profiles/my-80mm.yaml`

#### Scenario: Invalid user-provided profile

- **GIVEN** `./profiles/my-80mm.yaml` has no paper width
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error naming `./profiles/my-80mm.yaml` and the missing key

### Requirement: Starter configuration

`emupos config init [PATH]` SHALL write a commented starter configuration to `PATH`, or to `./emupos.yaml` when `PATH` is omitted. The starter SHALL pass `emupos config validate` and SHALL start with `emupos run` on the current operating system without external prerequisites. It SHALL define a printer on TCP port 9100 and SHALL include commented-out examples of a scale, a keyboard scanner, a serial scanner, and serial connections for macOS and Linux (`pty: true`) and for Windows (`port: COM5`). It SHALL NOT overwrite an existing file: in that case it SHALL exit with status 1 and name the file.

#### Scenario: Starter is valid and runs

- **GIVEN** an empty directory
- **WHEN** the user runs `emupos config init` and then `emupos config validate` and `emupos run`
- **THEN** `emupos.yaml` exists, validation exits with status 0, and the printer listens on `127.0.0.1:9100`

#### Scenario: Existing file is kept

- **GIVEN** `./emupos.yaml` already exists
- **WHEN** the user runs `emupos config init`
- **THEN** it exits with status 1, names `emupos.yaml`, and the file content is unchanged

### Requirement: Configuration validation command

`emupos config validate [PATH]` SHALL load and validate a configuration without starting devices, opening ports or links, or contacting a running simulator. Besides the schema rules it SHALL report settings that are unsupported on the current operating system, such as `pty: true` on Windows. When the configuration is valid it SHALL print a summary of the devices and exit with status 0; otherwise it SHALL print every error and exit with status 1.

#### Scenario: Valid file

- **GIVEN** a valid configuration with devices `front`, `deli` and `lane1`
- **WHEN** the user runs `emupos config validate`
- **THEN** it exits with status 0 and lists `front`, `deli` and `lane1` with their types

#### Scenario: Validation does not need free ports

- **GIVEN** `emupos run` is already running with the same configuration
- **WHEN** the user runs `emupos config validate`
- **THEN** it exits with status 0

#### Scenario: Unsupported on this operating system

- **GIVEN** scale `deli` has `serial: { pty: true }`
- **WHEN** the user runs `emupos config validate` on Windows
- **THEN** it exits with status 1 with an error at `deli`'s serial connection recommending `port` with a com0com pair

### Requirement: JSON Schema export

`emupos config schema` SHALL print to standard output a JSON Schema document describing the configuration file format of the highest supported schema version, for use by editors for completion and validation. The JSON Schema SHALL disallow unknown keys, and every document that emupos accepts SHALL be valid against it. Checks that span several fields or depend on the environment (duplicate ports or links, profile existence, operating-system support) SHALL be enforced by emupos even where the JSON Schema is not able to express them.

#### Scenario: Output is a JSON Schema

- **WHEN** the user runs `emupos config schema > emupos.schema.json`
- **THEN** it exits with status 0 and the file is a valid JSON Schema document

#### Scenario: Starter validates against the schema

- **GIVEN** a starter file written by `emupos config init`
- **WHEN** it is checked with a standard JSON Schema validator against the output of `emupos config schema`
- **THEN** the check passes

#### Scenario: Unknown key fails the schema

- **GIVEN** a configuration containing `devices[0].conections`
- **WHEN** it is checked against the output of `emupos config schema`
- **THEN** the check fails at `devices[0].conections`

### Requirement: Built-in demo configuration

`emupos run --demo` SHALL start a built-in configuration that runs on every supported operating system without external prerequisites. The demo SHALL include a printer on `127.0.0.1:9100` with its cash drawer and a keyboard-mode scanner, and on macOS and Linux it SHALL also include a scale using profile `toledo8217-15kg` on a simulator-created serial port. The startup output SHALL make clear that the demo configuration is in use.

#### Scenario: Demo on Windows without com0com

- **GIVEN** a Windows machine without com0com
- **WHEN** the user runs `emupos run --demo`
- **THEN** the simulator starts and a printer listens on `127.0.0.1:9100`

#### Scenario: Demo scale on macOS

- **WHEN** the user runs `emupos run --demo` on macOS
- **THEN** `emupos devices` lists a printer, a scanner and a scale whose connection is a link under `$TMPDIR/emupos/`

