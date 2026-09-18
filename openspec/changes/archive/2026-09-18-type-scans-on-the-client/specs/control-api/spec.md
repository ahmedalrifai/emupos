## ADDED Requirements

### Requirement: Scan typing report

`POST /api/v1/devices/{device_id}/scans/{scan_id}/typed` SHALL accept the body `{ "outcome": "delivered" }` or `{ "outcome": "failed", "keys_accepted": <integer>, "reason": <string> }`, where `keys_accepted` and `reason` are optional. The response SHALL be status 204 with no body.

A `delivered` report SHALL publish the scan's `scanner.scan.delivered` event; a `failed` report SHALL free the scanner without publishing it, as defined by the barcode-scanner capability. A `scan_id` that is not the scan in progress on that scanner SHALL be accepted and do nothing, so that a retried report is safe.

A report for a scanner whose `typed_by` is `server` SHALL return status 409 with code `typed_by_mismatch` and a fix naming the scanner's `typed_by` setting. A device that is not a scanner SHALL return status 409 with code `wrong_device_type`, and an unknown `device_id` SHALL return status 404.

#### Scenario: Delivered report

- **GIVEN** scanner `lane1` with `typed_by: client` and an accepted scan with id `lane1-1`
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans/lane1-1/typed` with body `{ "outcome": "delivered" }`
- **THEN** the response status is 204
- **AND** a `scanner.scan.delivered` event with `id` `lane1-1` is published

#### Scenario: Failed report

- **GIVEN** scanner `lane1` with `typed_by: client` and an accepted scan with id `lane1-1`
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans/lane1-1/typed` with body `{ "outcome": "failed", "keys_accepted": 7 }`
- **THEN** the response status is 204 and no `scanner.scan.delivered` event is published
- **AND** a new scan on `lane1` is accepted

#### Scenario: Stale scan id

- **GIVEN** scanner `lane1` with `typed_by: client` and no scan in progress
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans/lane1-9/typed` with body `{ "outcome": "delivered" }`
- **THEN** the response status is 204 and no event is published

#### Scenario: Report for a server-typed scanner

- **GIVEN** scanner `lane1` with `typed_by: server`
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans/lane1-1/typed` with body `{ "outcome": "delivered" }`
- **THEN** the response status is 409 with code `typed_by_mismatch`

#### Scenario: Report on a printer

- **WHEN** a client sends `POST /api/v1/devices/front/scans/front-1/typed` and `front` is a printer
- **THEN** the response status is 409 with code `wrong_device_type`

## MODIFIED Requirements

### Requirement: Scan triggering

`POST /api/v1/devices/{device_id}/scans` SHALL accept the body `{ "data": <string>, "countdown_seconds": <integer>, "unicode": <boolean> }`, where `countdown_seconds` is optional and defaults to `3` and `unicode` is optional and defaults to `false`.

When the barcode-scanner capability accepts the scan for a scanner the simulator types itself, the response SHALL be status 202, sent before the countdown ends, with the body `{ "id": <string>, "typed_by": "server", "deliver_at": <timestamp> }`, where `id` identifies the scan in its `scanner.scan.delivered` event and `deliver_at` is the RFC 3339 UTC time at which delivery starts.

When the scanner's `typed_by` is `client`, the response SHALL be status 200 with the body `{ "id": <string>, "typed_by": "client", "deliver_at": <timestamp>, "inter_key_delay_ms": <integer>, "keys": [ <key>, ... ] }`, where `deliver_at` is the time the client is to start typing. Each `<key>` SHALL be either `{ "usage": <integer>, "shift": <boolean> }` for a physical key, naming its HID usage ID on page `0x07` and whether Shift is held, or `{ "char": <string> }` for one exact character. The keys SHALL be those the simulator would have typed, including the suffix key.

A request that the barcode-scanner capability rejects as invalid SHALL return status 422 with code `validation_error`. A request rejected because a scan is already in progress, or because an operating-system prerequisite is not met, SHALL return status 409 with a `fix` when one is known. A device that is not a scanner SHALL return status 409 with code `wrong_device_type`.

#### Scenario: Scan with default countdown

- **GIVEN** keyboard scanner `lane1` whose prerequisites are met
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with body `{ "data": "6291041500213" }`
- **THEN** the response status is 202 before the 3-second countdown ends
- **AND** the body contains an `id`, `typed_by` `server` and a `deliver_at` time 3 seconds after the request was accepted

#### Scenario: Scan on a printer

- **WHEN** a client sends `POST /api/v1/devices/front/scans` with body `{ "data": "123" }` and `front` is a printer
- **THEN** the response status is 409 with code `wrong_device_type`

#### Scenario: Client-typed scan returns the key plan

- **GIVEN** keyboard scanner `lane1` with `typed_by: client`, suffix `enter` and `inter_key_delay_ms` 10
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with body `{ "data": "Ab1", "countdown_seconds": 0 }`
- **THEN** the response status is 200 with `typed_by` `client`, `inter_key_delay_ms` 10 and a `deliver_at` equal to the time of the request
- **AND** `keys` is `[ { "usage": 4, "shift": true }, { "usage": 5, "shift": false }, { "usage": 30, "shift": false }, { "usage": 40, "shift": false } ]`

#### Scenario: Client-typed scan with exact characters

- **GIVEN** keyboard scanner `lane1` with `typed_by: client` and suffix `enter`
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with body `{ "data": "كود", "unicode": true }`
- **THEN** `keys` is the three characters as `{ "char": … }` entries followed by `{ "usage": 40, "shift": false }`

### Requirement: Device listing and description

`GET /api/v1/devices` SHALL return every configured device, and `GET /api/v1/devices/{device_id}` SHALL return one device. Each device description SHALL include `id`, `type`, `profile` (null for a scanner), `connections` (each with its `kind`, `tcp` or `serial`, and its resolved endpoint, including the link path and pseudo-terminal device path for simulator-created serial ports) and `state`. A printer's `state` SHALL contain `faults` (the names of its active faults) and `drawer` (`open` or `closed`). A scale's `state` SHALL contain `grams`, `tare_grams`, `net_grams`, `stable` and `capacity_grams` as defined by the weight-scale capability. A scanner's `state` SHALL contain `mode`, `suffix`, `inter_key_delay_ms` and `typed_by`.

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
