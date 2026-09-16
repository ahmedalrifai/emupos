## ADDED Requirements

### Requirement: Scale weight state

A scale device SHALL hold its weight state as integers in grams, never as fractional numbers. The state SHALL consist of the gross weight (`grams`), the tare (`tare_grams`, 0 when no tare is set), the net weight (`net_grams`, gross minus tare), whether the reading is stable (`stable`), and the capacity defined by the device profile (`capacity_grams`). A scale SHALL start with a gross weight of 0 g, no tare and a stable reading. The scale `state` returned by `GET /api/v1/devices/{device_id}` SHALL include these five values. The weight reported on the wire SHALL be the net weight while a tare is set and the gross weight otherwise.

#### Scenario: Initial state after start

- **GIVEN** a configuration with a scale `deli` using profile `toledo8217-15kg`
- **WHEN** the simulator starts and a client requests `GET /api/v1/devices/deli`
- **THEN** the state reports `grams` 0, `tare_grams` 0, `net_grams` 0 and `stable` true
- **AND** `capacity_grams` is 15000, as defined by the profile

### Requirement: Setting the weight

Setting the weight through `PUT /api/v1/devices/{device_id}/weight` or `emupos scale set` SHALL set the gross weight to the given whole number of grams and the stability to the given value. A negative value SHALL be accepted so that an under-zero reading is testable, and a value above the profile capacity SHALL be accepted so that over-capacity behaviour is testable. Setting the weight SHALL NOT change the tare. Every accepted set, zero or tare operation, and every settling of an unstable reading, SHALL publish one `scale.weight.changed` event whose data contains `grams`, `tare_grams`, `net_grams` and `stable` after the change.

#### Scenario: Set a stable weight

- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with body `{ "grams": 1250, "stable": true }`
- **THEN** the request succeeds and the state reports `grams` 1250 and `stable` true
- **AND** a `scale.weight.changed` event is published with `device_id` `deli` and data `grams` 1250, `tare_grams` 0, `net_grams` 1250, `stable` true

#### Scenario: Weight above capacity accepted

- **GIVEN** scale `deli` with a capacity of 15000 g
- **WHEN** a client sets the weight to `{ "grams": 15001, "stable": true }`
- **THEN** the request succeeds and the state reports `grams` 15001

#### Scenario: Negative weight accepted

- **WHEN** a client sets the weight to `{ "grams": -100, "stable": true }`
- **THEN** the request succeeds and the state reports `grams` -100 and `net_grams` -100

### Requirement: Unstable readings settle

A weight set with `stable` false SHALL be reported as in motion until the settle time defined by the device profile has elapsed since that weight was set, after which the reading SHALL become stable at the same weight and a `scale.weight.changed` event with `stable` true SHALL be published. Setting the weight again before the reading settles SHALL restart the settle time.

#### Scenario: Reading settles after the settle time

- **GIVEN** scale `deli` whose profile defines a settle time of 500 ms
- **WHEN** a client sets the weight to `{ "grams": 1250, "stable": false }`
- **THEN** a weight request received 100 ms later is answered with a status reply whose motion bit is set
- **AND** a weight request received 600 ms after the weight was set is answered with the weight 1.250 kg
- **AND** a `scale.weight.changed` event with `stable` true is published once the settle time has elapsed

#### Scenario: New unstable weight restarts settling

- **GIVEN** scale `deli` whose profile defines a settle time of 500 ms
- **WHEN** a client sets `{ "grams": 1000, "stable": false }` and, 400 ms later, sets `{ "grams": 1250, "stable": false }`
- **THEN** a weight request received 800 ms after the first set is answered with a status reply whose motion bit is set

### Requirement: Zero and tare

`POST /api/v1/devices/{device_id}/zero` SHALL set the gross weight to 0 g and clear the tare. `POST /api/v1/devices/{device_id}/tare` SHALL set the tare to the current gross weight when it is above 0 g, and SHALL clear the tare when the gross weight is 0 g or below. Zero and tare SHALL be refused while the reading is in motion, as on a real scale: the response SHALL have status 409 with a `fix` stating to wait for the reading to settle, and the state SHALL be unchanged.

#### Scenario: Tare a container then weigh the item

- **GIVEN** scale `deli` with a stable weight of 200 g and no tare
- **WHEN** a client sends `POST /api/v1/devices/deli/tare` and then sets the weight to `{ "grams": 1450, "stable": true }`
- **THEN** the state reports `grams` 1450, `tare_grams` 200 and `net_grams` 1250

#### Scenario: Tare on an empty scale clears the tare

- **GIVEN** scale `deli` with a tare of 200 g and a stable gross weight of 0 g
- **WHEN** a client sends `POST /api/v1/devices/deli/tare`
- **THEN** the state reports `tare_grams` 0

#### Scenario: Zero clears weight and tare

- **GIVEN** scale `deli` with a tare of 200 g and a stable gross weight of 350 g
- **WHEN** a client sends `POST /api/v1/devices/deli/zero`
- **THEN** the state reports `grams` 0, `tare_grams` 0 and `net_grams` 0
- **AND** a `scale.weight.changed` event is published

#### Scenario: Tare refused in motion

- **GIVEN** scale `deli` with an unstable weight of 200 g that has not settled
- **WHEN** a client sends `POST /api/v1/devices/deli/tare`
- **THEN** the response has status 409 and the state reports `tare_grams` 0

### Requirement: Toledo 8217 serial framing

The built-in scale profile `toledo8217-15kg` SHALL define serial framing of 9600 baud, 7 data bits, even parity and 1 stop bit, and SHALL define its capacity as 15000 g.

#### Scenario: Profile framing

- **WHEN** the built-in profile `toledo8217-15kg` is loaded
- **THEN** its serial framing is 9600 baud, 7 data bits, even parity and 1 stop bit
- **AND** its capacity is 15000 g

### Requirement: Weight request with a reportable weight

When the scale receives `W` (`57`) and the reading is stable, the gross weight does not exceed the capacity, and the reported weight is not below 0 g, the scale SHALL reply with STX (`02`), the reported weight in kilograms with a decimal point formatted as defined by the device profile, `N` (`4e`) when a tare is set, and CR (`0d`). The weight SHALL be given at the resolution defined by the device profile. Every reply byte SHALL have bit 7 clear. The reply SHALL be written within 100 ms of receiving the request.

#### Scenario: Stable gross weight

- **GIVEN** scale `deli` with a stable weight of 1250 g and no tare
- **WHEN** a client sends `57`
- **THEN** the reply matches the regular expression `\x02\s*([0-9.]+)N?\r` and contains no `N`
- **AND** the captured number parses to 1.250 kilograms

#### Scenario: Stable net weight

- **GIVEN** scale `deli` with a tare of 200 g and a stable gross weight of 1450 g
- **WHEN** a client sends `57`
- **THEN** the reply matches `\x02\s*([0-9.]+)N\r`
- **AND** the captured number parses to 1.250 kilograms

#### Scenario: Weight exactly at capacity

- **GIVEN** scale `deli` with a capacity of 15000 g and a stable weight of 15000 g
- **WHEN** a client sends `57`
- **THEN** the reply is a weight reply whose captured number parses to 15.000 kilograms

### Requirement: Status reply when the weight cannot be reported

When the scale receives `W` (`57`) and the reading is in motion, the gross weight is above capacity, or the reported weight is below 0 g, the scale SHALL reply with STX (`02`), `?` (`3f`), one status byte and CR (`0d`). The status byte SHALL set every bit that applies: bit 0 when in motion, bit 1 when over capacity, bit 2 when the reported weight is below 0 g (under zero), bit 4 when the gross weight is exactly 0 g (center of zero), and bit 5 when a tare is set (net weight). Bit 3 and bit 7 SHALL always be clear, and bit 6 SHALL be set only in replies to unrecognised commands.

#### Scenario: Weight in motion

- **GIVEN** scale `deli` with an unstable weight of 1250 g that has not settled
- **WHEN** a client sends `57`
- **THEN** the reply is four bytes starting `02 3f` and ending `0d`
- **AND** bit 0 of the status byte is set and bits 1, 2 and 6 are clear

#### Scenario: Over capacity

- **GIVEN** scale `deli` with a capacity of 15000 g and a stable weight of 15001 g
- **WHEN** a client sends `57`
- **THEN** the reply is a status reply whose bit 1 is set and bit 0 is clear

#### Scenario: Under zero

- **GIVEN** scale `deli` with no tare and a stable weight of -100 g
- **WHEN** a client sends `57`
- **THEN** the reply is a status reply whose bit 2 is set

#### Scenario: Net weight below zero

- **GIVEN** scale `deli` with a tare of 200 g and a stable gross weight of 100 g
- **WHEN** a client sends `57`
- **THEN** the reply is a status reply whose bits 2 and 5 are set

#### Scenario: Several conditions at once

- **GIVEN** scale `deli` with a tare of 200 g and an unstable gross weight of 16000 g
- **WHEN** a client sends `57`
- **THEN** the status byte has bits 0, 1 and 5 set

### Requirement: Unrecognised commands

When the scale receives a byte that is not a command it recognises, it SHALL reply with a status reply whose bit 6 (bad command) is set, with the other bits reflecting the current state, and SHALL leave the weight state unchanged. CR (`0d`) and LF (`0a`) received between commands SHALL be ignored and SHALL NOT produce a reply.

#### Scenario: Unknown command byte

- **GIVEN** scale `deli` with a stable weight of 1250 g and no tare
- **WHEN** a client sends `58` (`X`)
- **THEN** the reply is four bytes starting `02 3f` and ending `0d` with bit 6 of the status byte set
- **AND** a following `57` is answered with the weight 1.250 kilograms

#### Scenario: Line terminators after a request

- **GIVEN** scale `deli` with a stable weight of 1250 g
- **WHEN** a client sends `57 0d 0a`
- **THEN** exactly one reply is sent, and it is the weight reply

### Requirement: Echo probe

The scale SHALL answer the echo probe that POS clients use to detect a Toledo 8217 scale. On receiving `E` (`45`) the scale SHALL reply `02 45 0d` and echo back unchanged the bytes that follow, until it receives `F` (`46`), the byte POS clients send to end the probe; the scale SHALL then stop echoing and SHALL send no reply to `F`. After the echo ends, requests SHALL be answered normally.

#### Scenario: Probe dialogue

- **WHEN** a client sends `45 68 65 6c 6c 6f` (`Ehello`)
- **THEN** the scale replies with exactly `02 45 0d 68 65 6c 6c 6f`

#### Scenario: Weighing after a completed probe

- **GIVEN** scale `deli` with a stable weight of 1250 g
- **WHEN** a client sends `45 68 65 6c 6c 6f`, reads the 8-byte reply, sends `46` and then sends `57`
- **THEN** no bytes are sent in response to `46`
- **AND** the reply to `57` is the weight reply for 1.250 kilograms

### Requirement: Request events

Every reply the scale sends to a `W` request, an `E` probe or an unrecognised command SHALL publish a `scale.request.answered` event whose data contains the request bytes (`request`) and the complete reply bytes (`reply`), both as spaced lowercase hex. Bytes echoed during an echo probe SHALL NOT publish additional events.

#### Scenario: Weight request event

- **GIVEN** a client subscribed to `WS /api/v1/events`
- **WHEN** a POS sends `57` to scale `deli`
- **THEN** the client receives a message with `type` `scale.request.answered`, `device_id` `deli`, data `request` `57`, and data `reply` equal to the bytes written to the POS
