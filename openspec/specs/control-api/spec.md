# Control API

## Purpose

The local REST API and event stream used to observe devices and perform the physical-world actions on them (set weight, trigger scans, inject faults, close the drawer, fetch receipts). It is never part of a POS's integration code.
## Requirements
### Requirement: Local binding

`emupos run` SHALL serve the control API over HTTP at the `api.host` and `api.port` from the configuration, which default to `127.0.0.1` and `8765`. The API has no authentication, so when `api.host` is anything other than a loopback address the simulator SHALL show a warning at startup stating that any machine able to reach that address is able to control the devices. If the API port is not available, `emupos run` SHALL exit with status 1 and a message naming the port.

#### Scenario: Default address

- **GIVEN** a configuration without an `api` section
- **WHEN** `emupos run` starts
- **THEN** `GET http://127.0.0.1:8765/api/v1/health` answers with status 200
- **AND** port 8765 is not listening on any non-loopback address

#### Scenario: Non-loopback host warns

- **GIVEN** the configuration sets `api: { host: 0.0.0.0, port: 8765 }`
- **WHEN** `emupos run` starts
- **THEN** the startup output contains a warning that the unauthenticated API is reachable from other machines

#### Scenario: API port in use

- **GIVEN** another process is listening on `127.0.0.1:8765`
- **WHEN** `emupos run` starts with the default `api` settings
- **THEN** it exits with status 1 and the message names port 8765

### Requirement: Protection against browser-originated requests

Because the API has no authentication and can type keystrokes into the focused window, the simulator SHALL refuse requests that a web page could send from the user's browser. It SHALL respond with status 403 and error code `browser_request_refused` to any request, including a WebSocket upgrade, that carries an `Origin` header. While `api.host` is a loopback address, it SHALL respond with status 403 and error code `invalid_host` to any request whose `Host` header is not `127.0.0.1`, `localhost` or `[::1]`, with or without the port. It SHALL respond with status 415 and error code `unsupported_media_type` to any request with a body whose `Content-Type` is not `application/json`.

#### Scenario: Request from a web page

- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with the header `Origin: https://example.com`
- **THEN** the response status is 403 with error code `browser_request_refused`
- **AND** no scan is accepted

#### Scenario: DNS rebinding attempt

- **GIVEN** `api.host` is `127.0.0.1`
- **WHEN** a client sends `GET /api/v1/devices` with the header `Host: attacker.example:8765`
- **THEN** the response status is 403 with error code `invalid_host`

#### Scenario: Form-encoded body

- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with `Content-Type: application/x-www-form-urlencoded`
- **THEN** the response status is 415 with error code `unsupported_media_type`
- **AND** the weight is unchanged

#### Scenario: Command-line and CI clients are unaffected

- **WHEN** `emupos devices` or a script using a plain HTTP client sends `GET /api/v1/devices` to `127.0.0.1:8765` without an `Origin` header
- **THEN** the response status is 200

### Requirement: Versioned and stable contract

Every REST endpoint and the event stream SHALL be served under the base path `/api/v1`. Within `/api/v1`, a release SHALL NOT remove or rename an endpoint, request field, response field, error code or event type, SHALL NOT change the type or meaning of a field, and SHALL NOT make an optional request field required. Adding endpoints, optional request fields, response fields, error codes and event types SHALL be allowed. A change that breaks these rules SHALL be published under a new base path `/api/v2`. The API version SHALL be independent of the package version.

#### Scenario: Compatible release

- **GIVEN** the OpenAPI documents of two consecutive releases that both serve `/api/v1`
- **WHEN** they are compared
- **THEN** every path, request field and response field of the older document exists in the newer one with the same type

#### Scenario: Unknown path

- **WHEN** a client requests `GET /api/v1/printers`
- **THEN** the response status is 404 with error code `not_found`

### Requirement: Health endpoint

`GET /api/v1/health` SHALL return status 200 with the body `{ "status": "ok", "version": "<package version>", "api_version": 1 }`, where `version` is the installed emupos package version.

#### Scenario: Health reports versions

- **GIVEN** the simulator is running
- **WHEN** a client requests `GET /api/v1/health`
- **THEN** the response status is 200
- **AND** `status` is `"ok"`, `api_version` is `1`, and `version` equals the output of `emupos --version` without the program name

### Requirement: OpenAPI document

The simulator SHALL serve an OpenAPI document at `GET /api/v1/openapi.json` that describes every REST endpoint of `/api/v1`, their request and response bodies, and the error body.

#### Scenario: Document lists the endpoints

- **WHEN** a client requests `GET /api/v1/openapi.json`
- **THEN** the response is a valid OpenAPI document
- **AND** it describes `/api/v1/devices/{device_id}/weight` and `/api/v1/barcodes/weighed`, among every other endpoint

### Requirement: Error responses

Every response with a 4xx or 5xx status SHALL have the JSON body `{ "error": { "code": <string>, "message": <string>, "fix": <string or null> } }`. `code` SHALL be a stable machine-readable identifier, `message` SHALL describe the problem in plain language, and `fix` SHALL tell the user what to do when a fix is known. Status codes SHALL be used consistently: 404 when the device, receipt or path does not exist; 422 when a request body or parameter is invalid, including an unknown fault name or an invalid barcode layout; 409 when the operation does not apply to the device's type or is not possible in the device's current state or environment. Unexpected failures SHALL return status 500 with code `internal_error` and SHALL NOT include a stack trace.

#### Scenario: Unknown device

- **WHEN** a client requests `GET /api/v1/devices/nope`
- **THEN** the response status is 404
- **AND** the body is `{ "error": { "code": "device_not_found", "message": ..., "fix": ... } }` and `fix` suggests `GET /api/v1/devices` to list device ids

#### Scenario: Invalid input

- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with body `{ "grams": 1.25 }`
- **THEN** the response status is 422 with code `validation_error`
- **AND** the message names the field `grams` and states that an integer is required

#### Scenario: Operation for another device type

- **WHEN** a client sends `PUT /api/v1/devices/front/weight` with body `{ "grams": 1250 }` and `front` is a printer
- **THEN** the response status is 409 with code `wrong_device_type`
- **AND** the message states that `front` is a printer and the operation needs a scale

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

### Requirement: Printer fault injection

`PUT /api/v1/devices/{device_id}/faults/{fault}` SHALL activate a fault and `DELETE` on the same path SHALL clear it, both returning status 204. The valid faults SHALL be `paper-near-end`, `paper-out`, `cover-open` and `offline`, with the effects and events defined by the receipt-printer capability. Both operations SHALL be idempotent: activating an active fault or clearing an inactive one SHALL also return status 204. An unknown fault name SHALL return status 422 listing the valid faults, and a device that is not a printer SHALL return status 409 with code `wrong_device_type`.

#### Scenario: Activate and clear paper out

- **WHEN** a client sends `PUT /api/v1/devices/front/faults/paper-out` and then `DELETE /api/v1/devices/front/faults/paper-out`
- **THEN** both responses have status 204
- **AND** `GET /api/v1/devices/front` shows `paper-out` in `state.faults` after the first request and not after the second

#### Scenario: Activating twice

- **GIVEN** `paper-out` is already active on `front`
- **WHEN** a client sends `PUT /api/v1/devices/front/faults/paper-out`
- **THEN** the response status is 204

#### Scenario: Unknown fault

- **WHEN** a client sends `PUT /api/v1/devices/front/faults/jammed`
- **THEN** the response status is 422 and the message lists `paper-near-end`, `paper-out`, `cover-open` and `offline`

### Requirement: Scale control

`PUT /api/v1/devices/{device_id}/weight` SHALL accept the body `{ "grams": <integer>, "stable": <boolean> }`, where `stable` is optional and defaults to `true`, set the weight as defined by the weight-scale capability, and return status 204. `POST /api/v1/devices/{device_id}/zero` and `POST /api/v1/devices/{device_id}/tare` SHALL perform zero and tare as defined by the weight-scale capability and return status 204. When the scale refuses zero or tare in its current state, the response SHALL be status 409 with a message stating why. A device that is not a scale SHALL return status 409 with code `wrong_device_type`.

#### Scenario: Set a stable weight

- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with body `{ "grams": 1250, "stable": true }`
- **THEN** the response status is 204
- **AND** `GET /api/v1/devices/deli` shows `state.grams` 1250 and `state.stable` true

#### Scenario: Stable defaults to true

- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with body `{ "grams": 800 }`
- **THEN** the response status is 204
- **AND** `GET /api/v1/devices/deli` shows `state.grams` 800 and `state.stable` true

#### Scenario: Tare

- **GIVEN** scale `deli` shows a stable 200 grams
- **WHEN** a client sends `POST /api/v1/devices/deli/tare`
- **THEN** the response status is 204 and `GET /api/v1/devices/deli` shows `state.tare_grams` 200

#### Scenario: Zero on a scanner

- **WHEN** a client sends `POST /api/v1/devices/lane1/zero` and `lane1` is a scanner
- **THEN** the response status is 409 with code `wrong_device_type`

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

### Requirement: Drawer close

`POST /api/v1/devices/{device_id}/drawer/close` SHALL close the cash drawer attached to printer `device_id` as defined by the cash-drawer capability and return status 204, including when the drawer was already closed. A device that is not a printer SHALL return status 409 with code `wrong_device_type` and SHALL change no drawer.

#### Scenario: Close an open drawer

- **GIVEN** the drawer of `front` was opened by a drawer-kick command
- **WHEN** a client sends `POST /api/v1/devices/front/drawer/close`
- **THEN** the response status is 204 and `GET /api/v1/devices/front` shows `state.drawer` `closed`

#### Scenario: Close an already closed drawer

- **GIVEN** the drawer of `front` is closed
- **WHEN** a client sends `POST /api/v1/devices/front/drawer/close`
- **THEN** the response status is 204

#### Scenario: Close on a device that is not a printer

- **GIVEN** the configuration has a scale `deli`
- **WHEN** a client sends `POST /api/v1/devices/deli/drawer/close`
- **THEN** the response status is 409 with code `wrong_device_type`

### Requirement: Receipts

`GET /api/v1/devices/{device_id}/receipts` SHALL list the completed receipts of a printer, newest first, each with at least `id`, `device_id`, `completed_at`, `width_dots` and `height_dots`. `GET .../receipts/{receipt_id}` SHALL return that metadata for one receipt, `GET .../receipts/{receipt_id}/image` SHALL return the rendered receipt with content type `image/png`, and `GET .../receipts/{receipt_id}/text` SHALL return the text dump with content type `text/plain; charset=utf-8`. The receipt id `latest` SHALL refer to the most recently completed receipt on every one of these paths. An unknown receipt id, or `latest` when the printer has no receipts, SHALL return status 404 with code `receipt_not_found`. A printer with no receipts SHALL list an empty array. A device that is not a printer SHALL return status 409.

#### Scenario: Latest receipt image

- **GIVEN** printer `front` with profile `xprinter-xp80t` has completed a job that ended with a cut
- **WHEN** a client requests `GET /api/v1/devices/front/receipts/latest/image`
- **THEN** the response status is 200 with content type `image/png`
- **AND** the image is 576 pixels wide

#### Scenario: Latest alias matches the list

- **GIVEN** printer `front` has completed three receipts
- **WHEN** a client requests `GET /api/v1/devices/front/receipts` and `GET /api/v1/devices/front/receipts/latest`
- **THEN** the list has three entries and the `latest` metadata equals the first entry

#### Scenario: No receipts yet

- **GIVEN** printer `front` has completed no receipts
- **WHEN** a client requests `GET /api/v1/devices/front/receipts/latest/text`
- **THEN** the response status is 404 with code `receipt_not_found`
- **AND** `GET /api/v1/devices/front/receipts` returns `[]`

### Requirement: Weighed-item barcodes

`POST /api/v1/barcodes/weighed` SHALL accept the body `{ "layout": <string>, "item": <integer>, "grams": <integer>, "price_minor": <integer> }` and return status 200 with `{ "digits": <13-digit string> }` computed as defined by the weighed-item-barcodes capability. `grams` SHALL be required when the layout has a weight field and `price_minor` when it has a price field. Every rejection defined by the weighed-item-barcodes capability (an invalid layout, a missing or disallowed value, or a value that does not fit its field) SHALL return status 422 with `error.message` naming the problem and `error.fix` describing a valid input. The endpoint SHALL NOT require any configured device.

#### Scenario: Weight-embedded barcode

- **WHEN** a client sends `{ "layout": "21IIIIIWWWWWC", "item": 12345, "grams": 1250 }`
- **THEN** the response status is 200 with `{ "digits": "2112345012506" }`

#### Scenario: Weight does not fit

- **WHEN** a client sends `{ "layout": "21IIIIIWWWWWC", "item": 12345, "grams": 123456 }`
- **THEN** the response status is 422 and `error.message` states that the 5-digit weight field holds at most 99999 g
- **AND** `error.fix` is not null

#### Scenario: Missing value for the layout

- **WHEN** a client sends `{ "layout": "21IIIIIPPPPPC", "item": 12345 }`
- **THEN** the response status is 422 and the message states that `price_minor` is required by the layout

### Requirement: Event stream

The simulator SHALL publish events over a WebSocket at `/api/v1/events`. Each event SHALL be one JSON text message `{ "type": <event name>, "device_id": <string>, "at": <timestamp>, "data": <object> }`, where `at` is an RFC 3339 UTC timestamp with millisecond precision and `data` is defined by the capability that emits the event. The event types SHALL be `connection.opened`, `connection.closed`, `connection.framing-mismatch`, `printer.job.completed`, `printer.command.unknown`, `printer.codepage.unsupported`, `printer.status.changed`, `drawer.opened`, `drawer.closed`, `scale.weight.changed`, `scale.request.answered`, `scanner.scan.delivered` and `snmp.query.answered`. Every connected subscriber SHALL receive every event emitted after it connected, in the order the events were emitted. Past events SHALL NOT be replayed.

#### Scenario: Fault produces an event

- **GIVEN** a client is subscribed to `/api/v1/events`
- **WHEN** another client sends `PUT /api/v1/devices/front/faults/cover-open`
- **THEN** the subscriber receives a message with `type` `printer.status.changed`, `device_id` `front`, an `at` timestamp and a `data` object

#### Scenario: Several subscribers

- **GIVEN** two clients are subscribed to `/api/v1/events`
- **WHEN** `PUT /api/v1/devices/deli/weight` sets 500 grams
- **THEN** both clients receive the same `scale.weight.changed` event

#### Scenario: No replay

- **GIVEN** a `printer.job.completed` event was emitted for `front`
- **WHEN** a new client subscribes to `/api/v1/events` afterwards
- **THEN** that client does not receive the earlier event

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

