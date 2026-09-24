# Weight Scale

## Purpose

Scale state (weight, motion, zero, tare, capacity, unit) and the serial protocols a scale speaks: Mettler Toledo 8217 and SMA SCP-0499.
## Requirements
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

`POST /api/v1/devices/{device_id}/zero` SHALL set the gross weight to 0 g and clear the tare. `POST /api/v1/devices/{device_id}/tare` SHALL set the tare to the current gross weight when it is above 0 g, and SHALL clear the tare when the gross weight is 0 g or below. A scale protocol MAY zero the scale, set or clear the tare, and set the tare to a value the host gives. Zero and tare SHALL be refused while the reading is in motion, as on a real scale, however they were asked for: over the control API the response SHALL have status 409 with a `fix` stating to wait for the reading to settle, and over a protocol the refusal SHALL be reported as that protocol defines. In every case the state SHALL be unchanged.

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

#### Scenario: A protocol taring the scale publishes the same event

- **GIVEN** scale `deli` with a stable weight of 200 g and no tare
- **WHEN** a connected host tares the scale through its protocol
- **THEN** the state reports `tare_grams` 200
- **AND** a `scale.weight.changed` event is published, as for a tare through the control API

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

### Requirement: SMA serial framing

A scale profile whose `protocol` is `sma` SHALL speak the Scale Manufacturers Association protocol SMA SCP-0499, Levels #1 and #2. A host command SHALL be LF (`0a`), one command character, optional command data, and CR (`0d`); the abort character ESC (`1b`) SHALL be the only exception. A reply SHALL begin with LF and end with CR. Bytes received outside a frame, and a frame that is empty, SHALL be discarded without a reply. A command whose bytes arrive across several reads SHALL be answered exactly as if it had arrived in one read. emupos SHALL ship the built-in scale profile `sma-15kg` with serial framing of 9600 baud, 8 data bits, no parity and 1 stop bit.

#### Scenario: Command split across reads

- **GIVEN** scale `deli` using profile `sma-15kg` with a stable weight of 1000 g
- **WHEN** a client sends `0a`, then `57`, then `0d`
- **THEN** the reply is the same as for the three bytes sent together

#### Scenario: Bytes outside a frame

- **WHEN** a client sends `57 0d` without a leading LF
- **THEN** no reply is sent

### Requirement: SMA weight requests

The scale SHALL answer `W` (`57`) with LF, the scale status character, the range character `1`, the gross or net character, the motion character, the reserved character (a space), the weight field of exactly 10 characters, the three-character unit of the scale's current unit, and CR. The weight field SHALL be the reported weight converted to the current unit, rounded to that unit's count-by with halves away from zero, written with that unit's decimal places and right-justified in the 10 characters. The gross or net character SHALL be `N` (`4e`) while a tare is set and `G` (`47`) otherwise. The motion character SHALL be `M` (`4d`) while the reading is in motion and a space otherwise. The scale status character SHALL be `O` (`4f`) when the gross weight is above capacity, `U` (`55`) when the reported weight is below zero, `Z` (`5a`) when the gross weight is exactly 0 g, and a space otherwise. `H` (`48`) SHALL answer the same way at ten times the resolution, with the gross or net character in lower case. `P` (`50`) and `Q` (`51`) SHALL answer as `W` and `H` do, because the simulator displays what it reports.

#### Scenario: Stable gross weight in kilograms

- **GIVEN** scale `deli` using a profile whose first unit is kilograms with 3 decimals, with a stable weight of 1250 g and no tare
- **WHEN** a client sends `0a 57 0d`
- **THEN** the reply is `0a`, a space, `31`, `47`, a space, a space, `     1.250` and `kg_`, then `0d`

#### Scenario: Net weight in pounds

- **GIVEN** scale `deli` whose current unit is pounds with 2 decimals, with a tare of 200 g and a stable gross weight of 1450 g
- **WHEN** a client sends `0a 57 0d`
- **THEN** the gross or net character is `N` and the weight field holds `2.76`, right-justified in 10 characters
- **AND** the unit field is `lb_`

#### Scenario: In motion and over capacity

- **GIVEN** scale `deli` with a capacity of 15000 g and an unsettled weight of 15001 g
- **WHEN** a client sends `0a 57 0d`
- **THEN** the scale status character is `O` and the motion character is `M`

#### Scenario: High resolution

- **GIVEN** scale `deli` whose current unit is kilograms with 3 decimals, with a stable weight of 1250 g
- **WHEN** a client sends `0a 48 0d`
- **THEN** the gross or net character is `g` (`67`) and the weight field holds the weight with one more decimal place

### Requirement: SMA zero and tare

The scale SHALL answer `Z` (`5a`) by zeroing the scale as the zero operation defines, and `T` (`54`) by taring the current gross weight. `T` followed by a weight value SHALL set the tare to that value, converted from the current unit to grams. `M` (`4d`) SHALL report the tare weight with the gross or net character `T` and without changing anything. `C` (`43`) SHALL clear the tare. Each SHALL answer with the standard reply, formed after the operation has been applied, so that the weight reported is the weight that results. When the reading is in motion the scale SHALL refuse the operation and leave its state unchanged: `Z` SHALL report the scale status character `E` (`45`) until the reading settles, and `T` SHALL report `T` (`54`) once, cleared after that reply. In every refusal the weight field SHALL be ten centre dashes instead of a number.

#### Scenario: Zero reports the zeroed weight

- **GIVEN** scale `deli` with a stable gross weight of 350 g and a tare of 200 g
- **WHEN** a client sends `0a 5a 0d`
- **THEN** the state reports `grams` 0, `tare_grams` 0 and `net_grams` 0
- **AND** the reply reports the scale status character `Z`, the gross character `G` and a weight of zero

#### Scenario: Tare refused while in motion

- **GIVEN** scale `deli` with an unsettled weight of 200 g
- **WHEN** a client sends `0a 54 0d`
- **THEN** the scale status character is `T` and the weight field is ten `-` characters
- **AND** the state reports `tare_grams` 0
- **AND** a second `0a 54 0d` sent before the reading settles no longer reports `T` as the scale status character

#### Scenario: Zero refused while in motion clears when it settles

- **GIVEN** scale `deli` whose profile defines a settle time of 500 ms and an unsettled weight of 350 g
- **WHEN** a client sends `0a 5a 0d`
- **THEN** the scale status character is `E` and the state still reports `grams` 350
- **AND** the same command sent after the reading settles zeroes the scale and no longer reports `E`

#### Scenario: Preset tare

- **GIVEN** scale `deli` whose current unit is kilograms, with a stable gross weight of 1450 g
- **WHEN** a client sends `T` followed by `0.200` in the frame
- **THEN** the state reports `tare_grams` 200 and the reply reports the net weight

#### Scenario: Report and clear the tare

- **GIVEN** scale `deli` with a tare of 200 g
- **WHEN** a client sends `0a 4d 0d` and then `0a 43 0d`
- **THEN** the first reply reports the gross or net character `T` and the tare weight, and the state is unchanged
- **AND** after the second the state reports `tare_grams` 0 and the reply reports the gross character `G`

### Requirement: SMA unit of measure

A scale profile for the SMA protocol SHALL list the units the model offers, in the order its unit key cycles them, each with its three-character abbreviation, its decimal places and its count-by. The scale SHALL start in the first listed unit, and the current unit SHALL be device state shared by every connection. `U` (`55`) SHALL move to the next listed unit and wrap to the first. `U` followed by a three-character unit SHALL select that unit when the profile lists it, and SHALL leave the unit unchanged otherwise. Both SHALL answer with the standard reply in the resulting unit. The state returned by `GET /api/v1/devices/{device_id}` SHALL report the current unit.

#### Scenario: Cycle to the next unit

- **GIVEN** scale `deli` whose profile lists kilograms then pounds, with a stable weight of 1000 g
- **WHEN** a client sends `0a 55 0d`
- **THEN** the reply's unit field is `lb_` and the weight is the same mass expressed in pounds
- **AND** a following `0a 57 0d` also reports `lb_`
- **AND** `GET /api/v1/devices/deli` reports the unit `lb_`

#### Scenario: Select a unit the profile does not list

- **GIVEN** scale `deli` whose profile lists kilograms and pounds, with kilograms current
- **WHEN** a client sends `U` followed by `ozt` in the frame
- **THEN** the unit is unchanged and the reply's unit field is `kg_`

### Requirement: SMA continuous weight

`R` (`52`) SHALL make the scale repeat the standard reply, and `S` (`53`) the high-resolution reply, to the connection that asked, until that connection sends another command. Repeats SHALL be written at the interval defined by the device profile. Any further command from that connection SHALL stop the repeats, including a command the scale does not recognise and the abort character. A repeat SHALL be sent only to the connection that asked for it.

#### Scenario: Repeats continue until the next command

- **GIVEN** scale `deli` whose profile defines a repeat interval of 200 ms
- **WHEN** a client sends `0a 52 0d` and waits 500 ms
- **THEN** it receives the first reply and then a further reply every 200 ms
- **AND** the replies follow the weight as it changes
- **WHEN** the client then sends `0a 57 0d`
- **THEN** it receives one weight reply and no further repeats

#### Scenario: Repeats go to one connection

- **GIVEN** connections A and B are open to scale `deli`
- **WHEN** A sends `0a 52 0d`
- **THEN** repeats are written to A and nothing is written to B

### Requirement: SMA diagnostics, About and Information

`D` (`44`) SHALL answer LF, four indicator characters and CR, each indicator a space because the simulator has no hardware to fail. `A` (`41`) SHALL answer the SMA compliance field `SMA:2/1.0` and reset the About pointer of that connection; each following `B` (`42`) SHALL answer the next About field — the maker, the model, the revision and the serial number from the device profile — and then `END:`. `I` (`49`) SHALL answer the same compliance field and reset the Information pointer of that connection; each following `N` (`4e`) SHALL answer the scale type `S`, the capacity line for the current unit, the list of supported commands, and then `END:`. A field descriptor SHALL be three characters followed by `:`. `B` or `N` after the last field SHALL be answered as an unrecognised command. Each pointer SHALL belong to one connection.

#### Scenario: About dialogue

- **GIVEN** scale `deli` whose profile names the maker, model, revision and serial number
- **WHEN** a client sends `0a 41 0d` and then `0a 42 0d` repeatedly
- **THEN** the first reply is `SMA:2/1.0`
- **AND** the following replies are the maker, the model, the revision, the serial number and then `END:`, each as `xxx:` followed by its value
- **AND** one more `0a 42 0d` is answered as an unrecognised command

#### Scenario: Capacity line reports the scale

- **GIVEN** scale `deli` with a capacity of 15000 g, current unit kilograms with 3 decimals and a count-by of 5
- **WHEN** a client reads the Information dialogue
- **THEN** one field is `CAP:` followed by the unit, the capacity in that unit, the count-by and the decimal position, separated by `:`

#### Scenario: Pointers are per connection

- **GIVEN** connections A and B are open to scale `deli`
- **WHEN** A sends `0a 41 0d` and `0a 42 0d`, and B then sends `0a 42 0d`
- **THEN** B's reply is an unrecognised command reply, because B has not started an About dialogue

### Requirement: SMA unrecognised commands and abort

A command the scale does not recognise, and the manufacturer extension `X` (`58`), SHALL be answered with LF, `?` (`3f`) and CR. ESC (`1b`) SHALL be acted on wherever it appears in the received bytes, without waiting for a frame: it SHALL discard a partly received frame, stop any repeat, reset the About and Information pointers of that connection, and produce no reply. ESC SHALL NOT change the weight, the tare or the unit, because a host giving up does not change what is on the platter.

#### Scenario: Unrecognised command

- **WHEN** a client sends `0a 4b 0d`
- **THEN** the reply is `0a 3f 0d`

#### Scenario: Abort during a repeat

- **GIVEN** scale `deli` is repeating the weight after `R`
- **WHEN** a client sends `1b`
- **THEN** no reply is sent and no further repeats are written
- **AND** the weight, tare and unit are unchanged

#### Scenario: Abort discards a partial frame

- **WHEN** a client sends `0a 57` and then `1b 0a 57 0d`
- **THEN** exactly one weight reply is sent

