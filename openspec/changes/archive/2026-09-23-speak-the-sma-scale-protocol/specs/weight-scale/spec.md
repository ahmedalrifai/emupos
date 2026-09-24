## ADDED Requirements

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

## MODIFIED Requirements

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
