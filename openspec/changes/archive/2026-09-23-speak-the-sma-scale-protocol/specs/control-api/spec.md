## MODIFIED Requirements

### Requirement: Device listing and description

`GET /api/v1/devices` SHALL return every configured device, and `GET /api/v1/devices/{device_id}` SHALL return one device. Each device description SHALL include `id`, `type`, `profile` (null for a scanner), `connections` (each with its `kind`, `tcp` or `serial`, and its resolved endpoint, including the link path and pseudo-terminal device path for simulator-created serial ports) and `state`. A printer's `state` SHALL contain `faults` (the names of its active faults) and `drawer` (`open` or `closed`). A scale's `state` SHALL contain `grams`, `tare_grams`, `net_grams`, `stable`, `capacity_grams` and `unit` as defined by the weight-scale capability, where `unit` is the three-character abbreviation the scale currently reports weights in, and is null for a scale whose protocol has no unit of measure. A scanner's `state` SHALL contain `mode`, `suffix`, `inter_key_delay_ms` and `typed_by`.

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

#### Scenario: Scale description reports the unit

- **GIVEN** scale `deli` uses profile `sma-15kg`, whose first unit is kilograms
- **WHEN** a client requests `GET /api/v1/devices/deli`
- **THEN** `state.unit` is `kg_`
- **AND** a scale using profile `toledo8217-15kg` reports `state.unit` null
