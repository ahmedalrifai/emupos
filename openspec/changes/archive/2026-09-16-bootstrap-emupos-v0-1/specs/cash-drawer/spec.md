## ADDED Requirements

### Requirement: One drawer attached to each printer

Every simulated printer SHALL have exactly one cash drawer attached to it. The drawer SHALL NOT have its own device id; it SHALL be addressed through the id of its printer in the control API and the CLI. The drawer SHALL be closed when the simulator starts. The drawer's state (open or closed) SHALL be shared by all connections of its printer and SHALL be reported as `state.drawer` (`open` or `closed`) in the printer description returned by `GET /api/v1/devices/{device_id}` and shown by `emupos devices`.

#### Scenario: Drawer starts closed

- **GIVEN** a configuration with printer `front`
- **WHEN** the simulator starts
- **THEN** `GET /api/v1/devices/front` reports `state.drawer` as `closed`
- **AND** `GET /api/v1/devices` lists no separate device for the drawer

#### Scenario: Kick on one connection is visible on another

- **GIVEN** printer `front` has a closed drawer with `sensor_open_level: high`, a POS client on its serial link `front` and another on TCP port 9100
- **WHEN** the serial client sends `1b 70 00 19 fa`
- **THEN** `10 04 01` sent by the TCP client receives `16`

### Requirement: ESC p drawer kick opens the drawer

When the printer processes ESC p (`1b 70 m t1 t2`) with m = 0 or 48 (drawer kick-out connector pin 2) or m = 1 or 49 (pin 5), the drawer SHALL open. A pulse on either pin SHALL open the same single drawer. When the drawer changes from closed to open, the simulator SHALL emit one `drawer.opened` event whose data contains the printer's device id, the pin (2 or 5) and the pulse ON time of t1 × 2 ms. A kick received while the drawer is already open SHALL leave it open and SHALL NOT emit `drawer.opened`. ESC p is not a real-time command: it SHALL be processed in order with the print data, so while a blocking printer fault (`paper-out`, `cover-open` or `offline`) is active the drawer SHALL stay closed until the fault is cleared and the held data containing the kick is processed.

#### Scenario: Pulse on pin 2

- **GIVEN** printer `front` has a closed drawer
- **WHEN** the POS sends `1b 70 00 19 fa`
- **THEN** the drawer is open
- **AND** a `drawer.opened` event is emitted with device id `front`, pin 2 and an ON time of 50 ms

#### Scenario: Pulse on pin 5 with an ASCII pin parameter

- **GIVEN** printer `front` has a closed drawer
- **WHEN** the POS sends `1b 70 31 32 64`
- **THEN** the drawer is open
- **AND** a `drawer.opened` event is emitted with pin 5 and an ON time of 100 ms

#### Scenario: Kick while already open

- **GIVEN** the drawer of printer `front` is open
- **WHEN** the POS sends `1b 70 00 19 fa`
- **THEN** the drawer stays open
- **AND** no `drawer.opened` event is emitted

#### Scenario: Kick held behind paper out

- **GIVEN** printer `front` has a closed drawer and the `paper-out` fault is active
- **WHEN** the POS sends `1b 70 00 19 fa` and `paper-out` is later cleared
- **THEN** the drawer stays closed while `paper-out` is active
- **AND** the drawer opens and `drawer.opened` is emitted after `paper-out` is cleared

### Requirement: Real-time drawer pulse

When the printer receives DLE DC4 with function 1 (`10 14 01 m t`), with m = 0 (pin 2) or m = 1 (pin 5) and t from 1 to 8, as defined by the Epson ESC/POS reference, the drawer SHALL open immediately, including while a blocking printer fault is active, and the simulator SHALL emit `drawer.opened` under the same rules as for ESC p, with a pulse ON time of t × 100 ms.

#### Scenario: Real-time pulse opens the drawer while printing is blocked

- **GIVEN** printer `front` has a closed drawer and the `cover-open` fault is active
- **WHEN** the POS sends `10 14 01 00 01`
- **THEN** the drawer opens without waiting for `cover-open` to be cleared
- **AND** a `drawer.opened` event is emitted with pin 2 and an ON time of 100 ms

### Requirement: Drawer stays open until closed by the user

An open drawer SHALL stay open, however much time passes, until it is closed through `POST /api/v1/devices/{device_id}/drawer/close` or `emupos drawer close [--device ID]`. Closing an open drawer SHALL close it and emit one `drawer.closed` event whose data contains the printer's device id. Closing a drawer that is already closed SHALL succeed without emitting an event.

#### Scenario: Drawer left open

- **GIVEN** the drawer of printer `front` was opened by `1b 70 00 19 fa`
- **WHEN** 10 minutes pass without a close request
- **THEN** `GET /api/v1/devices/front` still reports `state.drawer` as `open`

#### Scenario: Closing through the API

- **GIVEN** the drawer of printer `front` is open
- **WHEN** `POST /api/v1/devices/front/drawer/close` is sent twice
- **THEN** both requests succeed and the drawer is closed
- **AND** exactly one `drawer.closed` event is emitted

### Requirement: Drawer sensor level

The drawer's open/closed state SHALL be reported as the level of drawer kick-out connector pin 3. The level SHALL equal `drawer.sensor_open_level` (`high` or `low`) from the printer's configuration, or the drawer sensor polarity defined by the printer's profile when the configuration omits it, while the drawer is open, and SHALL be the opposite level while the drawer is closed. Bit 2 of the DLE EOT n = 1 reply (`10 04 01`) SHALL be 1 when pin 3 is high and 0 when it is low, independent of any printer fault.

#### Scenario: Sensor high when open

- **GIVEN** printer `front` has no active faults and `drawer: { sensor_open_level: high }`
- **WHEN** the POS sends `10 04 01` with the drawer closed, then `1b 70 00 19 fa`, then `10 04 01`
- **THEN** the POS receives `12` and then `16`

#### Scenario: Sensor low when open

- **GIVEN** printer `front` has no active faults and `drawer: { sensor_open_level: low }`
- **WHEN** the POS sends `10 04 01` with the drawer closed, then `1b 70 00 19 fa`, then `10 04 01`
- **THEN** the POS receives `16` and then `12`

#### Scenario: Drawer level reported while the printer is offline

- **GIVEN** printer `front` has `sensor_open_level: high`, an open drawer and the `cover-open` fault active
- **WHEN** the POS sends `10 04 01`
- **THEN** the POS receives `1e`

### Requirement: Drawer state in GS r and Automatic Status Back

The drawer kick-out connector status reported by GS r with n = 2 or 50 (`1d 72 02`, `1d 72 32`) SHALL reflect the pin 3 level defined by the drawer sensor level requirement, with the bit layout defined by the Epson ESC/POS reference for GS r. A change of the drawer between open and closed SHALL count as a status change for Automatic Status Back, so every connection on which ASB is enabled for the drawer status SHALL receive a new 4-byte status when the drawer opens or closes.

#### Scenario: GS r reports the drawer

- **GIVEN** printer `front` has no active faults and `sensor_open_level: high`
- **WHEN** the POS sends `1d 72 02` with the drawer closed, then `1b 70 00 19 fa`, then `1d 72 02`
- **THEN** the first reply reports pin 3 low
- **AND** the second reply reports pin 3 high

#### Scenario: ASB pushes drawer changes

- **GIVEN** a POS connection to printer `front` enabled ASB with `1d 61 ff` and received the initial 4 status bytes
- **WHEN** the drawer is opened by `1b 70 00 19 fa` sent on another connection and then closed through `POST /api/v1/devices/front/drawer/close`
- **THEN** the ASB connection receives one 4-byte status when the drawer opens and another when it closes
