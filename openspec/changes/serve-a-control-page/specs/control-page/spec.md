## ADDED Requirements

### Requirement: Serving the control page

While `emupos run` runs with `--ui`, the simulator SHALL serve the control page at `GET /` on the control API's address and port, with content type `text/html`. The page SHALL use only resources served by the simulator itself: no script, stylesheet, font, image or connection SHALL come from another origin, so the page works without internet access.

The page's HTML response SHALL carry the header `Content-Security-Policy: default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. The page SHALL NOT be part of the `/api/v1` contract and SHALL NOT appear in the OpenAPI document.

Without `--ui`, `GET /` SHALL answer status 404 with error code `not_found` and a `fix` naming `emupos run --ui`.

#### Scenario: Page served

- **GIVEN** `emupos run --demo --ui`
- **WHEN** a browser opens `http://127.0.0.1:8765/`
- **THEN** the response status is 200 with content type `text/html`
- **AND** the response carries the page's `Content-Security-Policy`

#### Scenario: No page without the flag

- **GIVEN** `emupos run --demo` without `--ui`
- **WHEN** a client requests `GET /`
- **THEN** the response status is 404 with error code `not_found` and the `fix` names `emupos run --ui`

#### Scenario: Self-contained

- **GIVEN** `emupos run --demo --ui` on a machine without internet access
- **WHEN** a browser opens the page
- **THEN** every resource the page loads comes from `http://127.0.0.1:8765`, and the page shows the devices

#### Scenario: Not in the API contract

- **GIVEN** `emupos run --ui`
- **WHEN** a client requests `GET /api/v1/openapi.json`
- **THEN** the document describes no path outside `/api/v1`

### Requirement: Devices and live state

The page SHALL show every configured device with its `id`, `type`, `profile` and `connections`, and its `state` as reported by `GET /api/v1/devices`. It SHALL keep that state current without being reloaded: after an event for a device, the page SHALL show that device's state as the API reports it. When the event stream is not connected, because `emupos run` stopped or the connection was lost, the page SHALL show that it is not connected. It SHALL keep trying to reconnect, and when it reconnects it SHALL refresh every device.

#### Scenario: Change made from the CLI

- **GIVEN** the page is open for `emupos run --demo --ui`
- **WHEN** another terminal runs `emupos scale set 1.25kg`
- **THEN** the page shows `deli` at 1.25 kg and stable, without being reloaded

#### Scenario: Reading settles

- **GIVEN** the page is open and `deli` was set to 800 grams with `stable: false`
- **WHEN** the scale's settle time passes
- **THEN** the page shows `deli` as stable

#### Scenario: Simulator stops and restarts

- **GIVEN** the page is open
- **WHEN** `emupos run` is stopped and started again on the same address
- **THEN** the page shows that it is not connected while the simulator is down
- **AND** it shows the devices' current state once the simulator is back, without being reloaded

### Requirement: Event list

The page SHALL show every event published after it connected, one line per event with the local time, device id, event type and the event's `data` as `key=value` pairs. It SHALL keep at least the 500 most recent events.

#### Scenario: Fault event

- **GIVEN** the page is open
- **WHEN** `PUT /api/v1/devices/front/faults/cover-open` is sent by any client
- **THEN** the page shows a line with the time, `front`, `printer.status.changed` and the active faults

### Requirement: Latest receipts

The page SHALL show, for each printer, the image of its most recently completed receipt, as rendered by the control API. When a `printer.job.completed` event arrives for a printer, the page SHALL show that job's receipt in its place. A printer with no completed receipt SHALL be shown as having none.

#### Scenario: New receipt

- **GIVEN** the page is open for `emupos run --demo --ui`
- **WHEN** a POS prints a job ending with a cut to `127.0.0.1:9100`
- **THEN** the page shows that receipt's image for `front` without being reloaded

#### Scenario: No receipt yet

- **GIVEN** printer `front` has completed no receipt
- **WHEN** the page is opened
- **THEN** the page shows that `front` has no receipt yet

### Requirement: Physical actions

The page SHALL offer, for each scale, setting a weight in grams as stable or moving, zero, and tare. It SHALL offer, for each printer, setting and clearing each of the faults `paper-near-end`, `paper-out`, `cover-open` and `offline`, and closing the drawer. Each action SHALL be performed through the `/api/v1` endpoint defined for it by the control-api capability. When the API refuses an action, the page SHALL show the error's `message` and, when it is not null, its `fix`.

#### Scenario: Set a fault

- **GIVEN** the page is open
- **WHEN** the user sets `paper-out` on `front`
- **THEN** `GET /api/v1/devices/front` shows `paper-out` in `state.faults`
- **AND** the page shows it as active

#### Scenario: Tare refused while the reading moves

- **GIVEN** `deli` shows a reading that has not settled
- **WHEN** the user presses tare for `deli`
- **THEN** the page shows the API's message stating that the reading is in motion, and its fix

#### Scenario: Opened through a non-loopback address

- **GIVEN** `emupos run --ui` with `api: { host: 0.0.0.0, port: 8765 }`, and the page opened through `http://192.168.1.5:8765/`
- **WHEN** the user closes the drawer of `front`
- **THEN** the drawer's state is unchanged
- **AND** the page shows the refusal's message and a fix naming `127.0.0.1`, `localhost` and `[::1]`

### Requirement: Scans from the page

The page SHALL offer a scan with a data field and a choice of exact-character delivery, requested as `unicode: true`. What happens when the user asks for a scan SHALL depend on the scanner:

- **keyboard mode, typed by the server:** the page SHALL run a countdown of 3 seconds itself. When the countdown ends:
  - if the page still has keyboard focus, it SHALL NOT request the scan, and SHALL tell the user to click the POS window during the countdown;
  - otherwise it SHALL request the scan with `countdown_seconds: 0`.
- **serial mode:** the page SHALL request the scan at once with `countdown_seconds: 0`.
- **keyboard mode, `typed_by: client`:** the page SHALL NOT offer a scan, and SHALL state that `emupos scan` types this scanner's scans on the machine with the POS window.

A refused scan SHALL be shown as defined for physical actions.

#### Scenario: Page still focused

- **GIVEN** keyboard scanner `lane1` typed by the server
- **WHEN** the user asks for a scan of `6291041500213` and the page still has keyboard focus when the countdown ends
- **THEN** no scan is requested
- **AND** the page tells the user to click the POS window during the countdown

#### Scenario: User switched to the POS

- **GIVEN** keyboard scanner `lane1` typed by the server
- **WHEN** the user asks for a scan of `6291041500213` and clicks the POS window before the countdown ends
- **THEN** the page requests the scan with `countdown_seconds: 0`
- **AND** the page shows the `scanner.scan.delivered` event once the keys are typed

#### Scenario: Serial scanner

- **GIVEN** serial scanner `lane2`
- **WHEN** the user asks for a scan of `6291041500213`
- **THEN** the page requests it at once with `countdown_seconds: 0`, with no countdown

#### Scenario: Client-typed scanner

- **GIVEN** keyboard scanner `lane1` with `typed_by: client`
- **WHEN** the page is opened
- **THEN** it offers no scan for `lane1` and names `emupos scan`

### Requirement: Device data shown as text

Event data and every other value that originates from a device connection or an API client SHALL be shown on the page as text and SHALL NOT be interpreted as HTML. Receipts SHALL be shown as the image the control API renders. Text that can be right-to-left SHALL be shown in its own direction without reordering the rest of the line around it.

#### Scenario: Markup in scan data

- **GIVEN** the page is open and serial scanner `lane2` exists
- **WHEN** a client requests a scan of `<img src=x onerror=alert(1)>` on `lane2`
- **THEN** the event line shows those characters literally
- **AND** no script runs

#### Scenario: Arabic scan data

- **GIVEN** the page is open and serial scanner `lane2` exists
- **WHEN** a client requests a scan of `كود42` on `lane2`
- **THEN** the event line shows the data as one right-to-left run, with the time, device id and event type in their usual order
