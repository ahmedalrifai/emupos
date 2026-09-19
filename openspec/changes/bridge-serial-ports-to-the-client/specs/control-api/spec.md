## ADDED Requirements

### Requirement: Observed framing reports

`POST /api/v1/devices/{device_id}/observed-framing` SHALL accept the body `{ "baud": <integer>, "data_bits": <integer|null>, "parity": <string|null> }`, where `data_bits` and `parity` are optional because an operating system does not always expose them. It SHALL compare them against the device's expected framing and answer status 200 with `{ "mismatches": [ { "setting", "expected", "observed" } ] }`, empty when the framing agrees.

When there is at least one mismatch the simulator SHALL emit one `connection.framing-mismatch` event and show the warning in the `emupos run` output, exactly as it does for a simulator-created serial port, and SHALL NOT repeat either for an unchanged observed framing. A device that speaks no serial protocol SHALL return status 409, and an unknown device SHALL return status 404.

#### Scenario: Mismatch reported

- **GIVEN** scale `deli` expects 9600 baud, 7 data bits and even parity
- **WHEN** a client sends `POST /api/v1/devices/deli/observed-framing` with `{ "baud": 9600, "data_bits": 8, "parity": "none" }`
- **THEN** the response lists a data-bits and a parity mismatch
- **AND** one `connection.framing-mismatch` event for `deli` is published

#### Scenario: Framing agrees

- **WHEN** the reported framing matches the expected framing
- **THEN** the response lists no mismatches and no event is published

#### Scenario: Device with no serial framing

- **WHEN** a client reports framing for a keyboard-mode scanner
- **THEN** the response has status 409

## MODIFIED Requirements

### Requirement: Device listing and description

`GET /api/v1/devices` SHALL return every configured device, and `GET /api/v1/devices/{device_id}` SHALL return one device. Each device description SHALL include `id`, `type`, `profile` (null for a scanner), `connections` (each with its `kind`, `tcp` or `serial`, and its resolved endpoint, including the link path and pseudo-terminal device path for simulator-created serial ports) and `state`. A printer's `state` SHALL contain `faults` (the names of its active faults) and `drawer` (`open` or `closed`). A scale's `state` SHALL contain `grams`, `tare_grams`, `net_grams`, `stable` and `capacity_grams` as defined by the weight-scale capability. A scanner's `state` SHALL contain `mode`, `suffix`, `inter_key_delay_ms` and `typed_by`. Each device description SHALL also include `serial_framing`: the baud rate, data bits, parity and stop bits the device expects on a serial connection, or null for a device that speaks no serial protocol.

#### Scenario: List devices

- **GIVEN** the configuration defines printer `front`, scale `deli` and scanner `lane1`
- **WHEN** a client requests `GET /api/v1/devices`
- **THEN** the response lists `front`, `deli` and `lane1` with types `printer`, `scale` and `scanner`

#### Scenario: Printer description reflects faults

- **GIVEN** the `cover-open` fault is active on `front`
- **WHEN** a client requests `GET /api/v1/devices/front`
- **THEN** `state.faults` contains `cover-open` and `state.drawer` is `closed`
- **AND** `connections` includes kind `tcp` with endpoint `127.0.0.1:9100`

#### Scenario: Scanner description reports who types

- **GIVEN** scanner `lane1` configured with `mode: keyboard` and `typed_by: client`
- **WHEN** a client requests `GET /api/v1/devices/lane1`
- **THEN** `state.typed_by` is `client`
- **AND** a scanner configured without `typed_by` reports `server`

#### Scenario: Expected serial framing is reported

- **GIVEN** scale `deli` uses profile `toledo8217-15kg` and scanner `lane1` is in keyboard mode
- **WHEN** a client requests `GET /api/v1/devices`
- **THEN** `deli` reports `serial_framing` of 9600 baud, 7 data bits, even parity and 1 stop bit
- **AND** `lane1` reports `serial_framing` null
