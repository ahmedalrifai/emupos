## ADDED Requirements

### Requirement: Transmit printer ID

When the printer processes GS I (`1d 49 n`) and its profile carries printer-ID values, it SHALL reply with the bytes the profile's model sends, with the framing defined by the Epson ESC/POS reference for GS I: for n = 1 or 49 the one-byte printer model ID; for n = 2 or 50 the one-byte type ID, whose bit 1 SHALL be set when the profile says an autocutter is installed and whose other bits SHALL be 0; for n = 35, when the profile says the model answers it, the printer information A block `3d 23 30 00`, reporting the standard column mode, which is the mode emupos renders; for n = 66 and 67 the printer information B blocks `5f` + the maker name + `00` and `5f` + the model name + `00`; and for n = 65, 68 and 69 the two bytes `5f 00`, which is what a printer sends when it has no firmware version, serial number or language font prepared. GS I with any other n, and every GS I sent to a printer whose profile carries no printer-ID values, SHALL get no reply and SHALL produce a `printer.command.unknown` event. GS I is not a real-time command: it SHALL be processed in order with the print data, so while a fault blocks printing its reply SHALL be sent only after the blocking faults are cleared and the data received before it has been processed. The reply SHALL be sent only on the connection that sent the request.

#### Scenario: Model and type ID of a profile with values

- **GIVEN** printer `front` uses profile `epson-tm-t20iii`, which has an autocutter
- **WHEN** the POS sends `1d 49 01`
- **THEN** the printer replies with the byte `63`
- **AND** no `printer.command.unknown` event is emitted
- **WHEN** the POS then sends `1d 49 32`
- **THEN** the printer replies with the byte `02`

#### Scenario: Maker and model name

- **GIVEN** printer `front` uses profile `epson-tm-t20iii`
- **WHEN** the POS sends `1d 49 42`
- **THEN** the printer replies with the bytes `5f 45 50 53 4f 4e 00`
- **WHEN** the POS then sends `1d 49 43`
- **THEN** the printer replies with the bytes `5f 54 4d 2d 54 32 30 49 49 49 00`

#### Scenario: Column emulation mode

- **GIVEN** printer `front` uses profile `epson-tm-t20iii`, whose model answers n = 35
- **WHEN** the POS sends `1d 49 23`
- **THEN** the printer replies with the bytes `3d 23 30 00`

#### Scenario: Value the simulator does not have

- **GIVEN** printer `front` uses profile `epson-tm-t20iii`
- **WHEN** the POS sends `1d 49 44`, asking for the serial number
- **THEN** the printer replies with the bytes `5f 00`
- **AND** no `printer.command.unknown` event is emitted

#### Scenario: n the model does not accept

- **GIVEN** printer `front` uses profile `epson-tm-t20iii`, which does not accept n = 3
- **WHEN** the POS sends `1d 49 03`
- **THEN** the printer sends no reply
- **AND** a `printer.command.unknown` event is emitted whose data contains the bytes `1d 49 03`

#### Scenario: Profile without printer-ID values

- **GIVEN** printer `front` uses a printer profile that carries no printer-ID values
- **WHEN** the POS sends `1d 49 01`
- **THEN** the printer sends no reply
- **AND** a `printer.command.unknown` event is emitted whose data contains the bytes `1d 49 01`

#### Scenario: Reply waits for a blocking fault to clear

- **GIVEN** printer `front` uses profile `epson-tm-t20iii` and is out of paper
- **WHEN** the POS sends `1d 49 01`
- **THEN** no reply is sent
- **WHEN** the paper-out fault is cleared
- **THEN** the printer replies with the byte `63`
