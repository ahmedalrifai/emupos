# Receipt Printer

## Purpose

ESC/POS decoding, receipt rendering, job boundaries, real-time status, automatic status back, and fault injection.
## Requirements
### Requirement: Incremental ESC/POS decoding

The printer SHALL decode the bytes received on each connection as one continuous ESC/POS stream, independent of how those bytes are split into reads. A command whose bytes arrive across several reads SHALL produce exactly the same result as if it had arrived in a single read. Bytes that do not form a recognised command SHALL be skipped, SHALL produce a `printer.command.unknown` event whose data contains the skipped bytes as spaced hex, and SHALL NOT change how the following bytes are processed. An incomplete command still pending when the connection closes SHALL be discarded with a `printer.command.unknown` event. No byte sequence SHALL make the printer stop processing, close the connection or stop the simulator.

#### Scenario: Command split across reads

- **GIVEN** a printer `front` with a TCP connection on port 9100
- **WHEN** the POS writes `48 69 0a 1d` and, in a later write, `56 00`
- **THEN** exactly one receipt is completed and its text is `Hi`
- **AND** no `printer.command.unknown` event is emitted

#### Scenario: Unknown command is skipped

- **WHEN** the POS sends `1b 40 1b fe 48 69 0a 1d 56 00`
- **THEN** a `printer.command.unknown` event is emitted whose data contains the bytes `1b fe`
- **AND** the completed receipt's text is `Hi`

#### Scenario: Truncated command at connection close

- **WHEN** the POS sends `48 69 0a 1d 76 30 00` and closes the connection
- **THEN** a receipt is completed whose text is `Hi`
- **AND** a `printer.command.unknown` event is emitted whose data contains the bytes `1d 76 30 00`

#### Scenario: Random bytes do not stop the printer

- **WHEN** the POS sends 10000 random bytes on one connection and then closes it
- **THEN** the simulator keeps running
- **AND** a new connection that sends `10 04 01` receives a one-byte reply

### Requirement: Real-time commands

The printer SHALL process the real-time commands DLE EOT (`10 04 n`), DLE ENQ (`10 05 n`) and DLE DC4 (`10 14 fn …`) as soon as they are received, ahead of any print data that was received earlier and is still waiting to be processed. Real-time commands SHALL be processed while a fault blocks printing, SHALL NOT be stored with the print data and SHALL NOT appear on any receipt. Bytes that belong to the parameters or data of another command, such as the image data of `GS v 0`, SHALL be treated as part of that command and SHALL NOT be processed as real-time commands. A real-time command for which neither this capability nor the cash-drawer capability defines an effect SHALL be consumed and SHALL produce a `printer.command.unknown` event.

#### Scenario: Status query inside a line of text

- **WHEN** the POS sends `48 65 10 04 01 6c 6c 6f 0a 1d 56 00`
- **THEN** the POS receives exactly one status byte
- **AND** the completed receipt's text is `Hello`

#### Scenario: Status query answered while printing is blocked

- **GIVEN** the `paper-out` fault is active on printer `front`
- **AND** the POS has sent `48 69 0a 1d 56 00`, which is being held unprinted
- **WHEN** the POS sends `10 04 04`
- **THEN** the POS receives a one-byte reply without waiting for the fault to be cleared
- **AND** no receipt is completed

#### Scenario: Real-time byte values inside image data

- **WHEN** the POS sends a `GS v 0` raster image whose image data contains the bytes `10 04 01`
- **THEN** the POS receives no status byte
- **AND** the rendered image contains the dots encoded by those bytes

### Requirement: DLE EOT status replies computed from printer state

For DLE EOT (`10 04 n`) with n from 1 to 4, the printer SHALL reply with exactly one byte computed from its state at the moment the command is processed. In every reply bit 0 and bit 7 SHALL be 0 and bit 1 and bit 4 SHALL be 1, as defined by the Epson ESC/POS reference, and every other bit SHALL be 0 unless one of the following rules sets it:

- n = 1 (printer status): bit 2 SHALL equal the drawer kick-out connector pin 3 level (1 = high) defined by the cash-drawer capability; bit 3 (offline) SHALL be 1 while any of the `offline`, `cover-open` or `paper-out` faults is active.
- n = 2 (offline cause): bit 2 SHALL be 1 while `cover-open` is active; bit 5 (printing stopped by paper end) SHALL be 1 while `paper-out` is active.
- n = 3 (error status): no bit is set by any simulated state, so the reply SHALL be `12`.
- n = 4 (roll paper sensor): bits 2 and 3 SHALL both be 1 while `paper-near-end` or `paper-out` is active; bits 5 and 6 SHALL both be 1 while `paper-out` is active.

For any other value of n the printer SHALL send no reply and SHALL treat the bytes as a real-time command without a defined effect.

#### Scenario: Printer with no faults

- **GIVEN** printer `front` has no active faults and a closed drawer with `sensor_open_level: high`
- **WHEN** the POS sends `10 04 01`, `10 04 02`, `10 04 03` and `10 04 04` in that order
- **THEN** the POS receives `12`, `12`, `12` and `12` in that order

#### Scenario: Cover open

- **GIVEN** the `cover-open` fault is active and the drawer is closed with `sensor_open_level: high`
- **WHEN** the POS sends `10 04 01` and then `10 04 02`
- **THEN** the POS receives `1a` and then `16`

#### Scenario: Paper out

- **GIVEN** the `paper-out` fault is active and the drawer is closed with `sensor_open_level: high`
- **WHEN** the POS sends `10 04 01`, `10 04 02` and `10 04 04` in that order
- **THEN** the POS receives `1a`, `32` and `7e` in that order

#### Scenario: Out-of-range request

- **WHEN** the POS sends `10 04 05` followed by `10 04 01`
- **THEN** the POS receives exactly one byte, which is the reply to `10 04 01`
- **AND** a `printer.command.unknown` event is emitted whose data contains the bytes `10 04 05`

### Requirement: Automatic Status Back

When the printer processes GS a (`1d 61 n`) with n other than 0, it SHALL enable Automatic Status Back (ASB) for the connection that sent it: it SHALL immediately send a 4-byte status to that connection and SHALL send a new 4-byte status to that connection each time a status category enabled by n changes. The layout of the 4 bytes and the meaning of the bits of n SHALL follow the Epson ESC/POS reference for GS a, with every status bit computed from the same printer state as the DLE EOT replies. `1d 61 00` SHALL disable ASB for that connection. ASB SHALL be disabled when a connection opens and SHALL end when it closes.

#### Scenario: Enabling ASB sends the current status

- **WHEN** the POS sends `1d 61 ff`
- **THEN** the POS receives 4 status bytes without sending any further command

#### Scenario: Fault changes push a new status

- **GIVEN** the POS enabled ASB with `1d 61 ff` and received the initial 4 status bytes
- **WHEN** the `paper-out` fault is activated through the control API and later cleared
- **THEN** on activation the POS receives 4 status bytes that differ from the initial status
- **AND** on clearing the POS receives 4 status bytes equal to the initial status

#### Scenario: Disabling ASB

- **GIVEN** the POS enabled ASB with `1d 61 ff`
- **WHEN** the POS sends `1d 61 00` and the `cover-open` fault is then activated
- **THEN** the POS receives no further status bytes

#### Scenario: ASB is per connection

- **GIVEN** connection A to printer `front` enabled ASB with `1d 61 ff` and connection B to the same printer did not
- **WHEN** the `offline` fault is activated
- **THEN** connection A receives 4 status bytes
- **AND** connection B receives no bytes

### Requirement: GS r transmit status

When the printer processes GS r (`1d 72 n`), it SHALL reply with one byte computed from its current state: for n = 1 or 49 the byte SHALL report the roll paper near-end and paper-end sensor status, and for n = 2 or 50 it SHALL report the drawer kick-out connector status, in both cases with the bit layout defined by the Epson ESC/POS reference for GS r. GS r is not a real-time command: it SHALL be processed in order with the print data, so while a fault blocks printing its reply SHALL be sent only after the blocking faults are cleared and the data received before it has been processed. The obsolete status requests ESC v (`1b 76`) and ESC u (`1b 75 n`) SHALL be processed the same way: ESC v SHALL be answered with the byte GS r 1 sends, and ESC u with n = 0 or 48 with the byte GS r 2 sends. ESC u with any other n SHALL get no reply and SHALL produce a `printer.command.unknown` event.

#### Scenario: Paper sensor status follows paper state

- **GIVEN** printer `front` has no active faults
- **WHEN** the POS sends `1d 72 01`, the `paper-near-end` fault is then activated, and the POS sends `1d 72 31`
- **THEN** the first reply reports paper present and not near end
- **AND** the second reply reports paper near end

#### Scenario: GS r waits behind a blocking fault

- **GIVEN** the `cover-open` fault is active
- **WHEN** the POS sends `1d 72 01`
- **THEN** the POS receives no reply while `cover-open` remains active
- **AND** after `cover-open` is cleared the POS receives one reply byte

#### Scenario: Obsolete status requests reply like GS r

- **GIVEN** the `paper-near-end` fault is active and the drawer is open with drawer kick-out connector pin 3 high
- **WHEN** the POS sends `1b 76 1b 75 00 1b 75 30 1b 75 01`
- **THEN** the POS receives `03 01 01`
- **AND** a `printer.command.unknown` event is emitted whose data contains the bytes `1b 75 01`

### Requirement: Supported print commands

The printer SHALL process and render the following ESC/POS commands as defined by the Epson ESC/POS reference: initialise (ESC @, `1b 40`), which SHALL reset print settings to the profile defaults; printable text; line feed and paper feeds (LF `0a`, ESC d, ESC J) and line spacing (ESC 2, ESC 3); emphasis (ESC E) and underline (ESC -); font selection (ESC M); character size (GS !); justification (ESC a); cuts (GS V, and the obsolete partial cuts ESC i and ESC m); return to the beginning of the line (GS T), which SHALL be ignored at the beginning of a line and otherwise SHALL print the line like LF for n = 1 or 49 and discard it for n = 0 or 48; print colour (ESC r), which SHALL NOT produce a `printer.command.unknown` event and, because the built-in profiles are single-colour, SHALL leave text black; the drawer kick (ESC p) with the effects defined by the cash-drawer capability; raster images (GS v 0); bit images (ESC *); barcodes (GS k); QR codes (GS ( k); horizontal tabs (HT `09`) with tab positions (ESC D); right-side character spacing (ESC SP); left margin (GS L) and print area width (GS W); absolute and relative print positions (ESC $, ESC \\); and buffered graphics (GS ( L and GS 8 L functions 112 store raster graphics data and 50 print it). Page mode (ESC L), NV graphics stored in non-volatile memory (the other GS ( L functions) and PDF417 symbols (GS ( k with cn = 48) SHALL NOT be rendered: each such command SHALL be consumed in full, using its declared length where it has one, SHALL produce a `printer.command.unknown` event, and SHALL leave the printer in standard mode so that following commands render normally.

#### Scenario: Initialise resets character size

- **WHEN** the POS sends `1d 21 11 41 0a 1b 40 41 0a 1d 56 00`
- **THEN** in the receipt image the first `A` occupies a 24 × 48 dot cell
- **AND** the second `A` occupies a 12 × 24 dot cell

#### Scenario: PDF417 is consumed without breaking following commands

- **WHEN** the POS sends `1d 28 6b 03 00 30 41 00` followed by `4f 4b 0a 1d 56 00`
- **THEN** a `printer.command.unknown` event is emitted whose data contains the bytes `1d 28 6b 03 00 30 41 00`
- **AND** the completed receipt's text is `OK`

#### Scenario: Tabs align columns

- **WHEN** the POS sends `1b 40 1b 44 0a 00 41 09 42 0a 1d 56 00`
- **THEN** in the receipt image the cell of `B` starts at dot column 120 (tab position 10 × the 12-dot Font A cell)
- **AND** no `printer.command.unknown` event is emitted

#### Scenario: Buffered graphics print

- **WHEN** the POS stores a 16 × 8 dot raster image with GS ( L function 112 and prints it with GS ( L function 50, then sends `1d 56 00`
- **THEN** the receipt image contains the 16 × 8 dot image
- **AND** no `printer.command.unknown` event is emitted

#### Scenario: Page mode is not entered

- **WHEN** the POS sends `1b 4c 48 69 0a 1d 56 00`
- **THEN** a `printer.command.unknown` event is emitted whose data contains the bytes `1b 4c`
- **AND** the completed receipt contains the text `Hi` rendered in standard mode

#### Scenario: GS T prints or discards the current line

- **WHEN** the POS sends `1d 54 31 41 1d 54 31 42 1d 54 30 43 0a 1d 56 00`
- **THEN** the completed receipt's text is `A` and `C` on two lines
- **AND** no `printer.command.unknown` event is emitted

#### Scenario: Print colour prints in black

- **GIVEN** printer `front` uses a built-in profile
- **WHEN** the POS sends `1b 40 1b 72 31 4e 4f 20 4f 4e 49 4f 4e 53 0a 1b 72 30 1d 56 00`
- **THEN** the completed receipt's text is `NO ONIONS`, printed in black
- **AND** no `printer.command.unknown` event is emitted

### Requirement: Paper geometry from the device profile

The printer SHALL render every receipt on a canvas whose width in dots equals the printable width defined by its profile; the built-in 80 mm profiles (`epson-tm-t20iii`, `xprinter-xp80t`, `rongta-rp326`) SHALL use 576 dots at 203 dpi. Each character SHALL occupy the cell size defined by the profile for the selected font (12 × 24 dots for Font A and 9 × 17 dots for Font B on the built-in profiles, giving 48 and 64 columns on a 576-dot line), multiplied by the width and height factors selected with GS !. Text that does not fit on the current line SHALL continue on the next line starting with the first character that does not fit, identically in the receipt image and the text dump. Justification SHALL position each line within the printable width in whole dots. Geometry SHALL be dot-accurate; glyph shapes SHALL approximate the printer's fonts.

#### Scenario: Font A wraps at 48 columns

- **GIVEN** printer `front` uses profile `xprinter-xp80t`
- **WHEN** the POS sends `1b 40`, 60 bytes of `41`, `0a` and `1d 56 00`
- **THEN** the receipt image is 576 dots wide
- **AND** the text dump contains a line of 48 `A` characters followed by a line of 12 `A` characters

#### Scenario: Font B wraps at 64 columns

- **WHEN** the POS sends `1b 40 1b 4d 01`, 70 bytes of `41`, `0a` and `1d 56 00` to a printer using a built-in 80 mm profile
- **THEN** the text dump contains a line of 64 `A` characters followed by a line of 6 `A` characters

#### Scenario: Double width halves the columns

- **WHEN** the POS sends `1b 40 1d 21 10`, 30 bytes of `41`, `0a` and `1d 56 00` to a printer using a built-in 80 mm profile
- **THEN** the text dump contains a line of 24 `A` characters followed by a line of 6 `A` characters

#### Scenario: Centred text position in dots

- **WHEN** the POS sends `1b 40 1b 61 01 48 45 4c 4c 4f 0a 1d 56 00` to a printer using a built-in 80 mm profile
- **THEN** the character cells of `HELLO` occupy dot columns 258 to 317 of the receipt image

### Requirement: Raster and bit images

The printer SHALL render raster images (GS v 0) and bit images (ESC *) dot for dot: every 1 bit SHALL print a black dot and every 0 bit SHALL leave the dot white. In GS v 0 data each byte SHALL be 8 horizontal dots of a row, with the most significant bit as the leftmost dot. In ESC * data each byte (or each group of 3 bytes in the 24-dot modes) SHALL be one vertical column of dots, with the most significant bit as the top dot. GS v 0 SHALL apply the scaling selected by its mode byte (normal, double width, double height or quadruple), and ESC * SHALL apply the dot density selected by its mode byte as defined by the Epson ESC/POS reference. Dots that fall outside the printable width SHALL NOT be rendered and SHALL NOT widen the receipt image.

#### Scenario: Full-width raster image

- **WHEN** the POS sends `1d 76 30 00 48 00 20 00` followed by 2304 bytes of image data (72 bytes per row, 32 rows), then `1d 56 00`
- **THEN** the receipt image contains a 576 × 32 dot region whose dots match the image data bit for bit

#### Scenario: Quadruple scaling

- **WHEN** the POS sends `1d 76 30 03 02 00 08 00` followed by 16 bytes of image data, then `1d 56 00`
- **THEN** the receipt image contains a 32 × 16 dot region in which each source bit is rendered as a 2 × 2 block of dots

#### Scenario: Image wider than the paper is clipped

- **WHEN** the POS sends `1d 76 30 00 50 00 01 00` followed by 80 bytes of `ff` (640 dots wide), then `1d 56 00`, to a printer with a 576-dot profile
- **THEN** the receipt image is 576 dots wide
- **AND** the image row contains 576 black dots

#### Scenario: Bit image columns

- **WHEN** the POS sends `1b 2a 00 01 00 80` followed by `0a 1d 56 00`
- **THEN** the receipt image contains a bit image of one data column in which only the dots of the column's top bit are black, sized by the dot density that the Epson ESC/POS reference defines for mode 0

### Requirement: Barcodes and QR codes

The printer SHALL render GS k (`1d 6b`) barcodes in the EAN-13, EAN-8, UPC-A, CODE39, ITF and CODE128 symbologies, using the module width set by GS w (`1d 77 n`) in dots, the bar height set by GS h (`1d 68 n`) in dots, and the human-readable interpretation position set by GS H (`1d 48 n`). It SHALL render GS ( k QR codes (cn = 49) from the data stored with function 180 when function 181 is received, using the module size in dots set by function 167 and the error correction level set by function 169, as defined by the Epson ESC/POS reference. Every rendered symbol SHALL decode to the data the POS sent. A GS k barcode in any other symbology SHALL be consumed without drawing a symbol and SHALL produce a `printer.command.unknown` event naming the symbology.

#### Scenario: EAN-13 module width and height

- **WHEN** the POS sends `1d 77 02 1d 68 50` followed by `1d 6b 43 0d 34 30 30 36 33 38 31 33 33 33 39 33 31` and `1d 56 00`
- **THEN** the receipt image contains an EAN-13 barcode whose bars span 190 dots (95 modules × 2 dots) and are 80 dots tall
- **AND** the barcode decodes to `4006381333931`

#### Scenario: QR code module size

- **WHEN** the POS sets the QR module size with `1d 28 6b 03 00 31 43 04`, stores the data `https://example.com` with function 180, prints it with `1d 28 6b 03 00 31 51 30` and sends `1d 56 00`
- **THEN** the receipt image contains a QR code in which every module is 4 × 4 dots
- **AND** the QR code decodes to `https://example.com`

#### Scenario: Unsupported symbology

- **WHEN** the POS sends a GS k CODE93 barcode (m = 72) followed by `4f 4b 0a 1d 56 00`
- **THEN** a `printer.command.unknown` event is emitted naming CODE93
- **AND** the completed receipt contains no barcode and its text is `OK`

### Requirement: Code page selection

The printer SHALL select a code page with ESC t (`1b 74 n`) by looking up n in the code-page map of its profile, because vendors number the same code page differently: on `epson-tm-t20iii` n = 37 selects PC864, on `rongta-rp326` n = 22 selects PC864, and on `xprinter-xp80t` the numbers are as defined by that profile. After ESC @ the profile's default code page SHALL be selected, and that code page SHALL have a glyph table. Bytes `20` to `7e` SHALL always print as ASCII characters. The simulator SHALL carry a glyph table for every code page named by a built-in profile: PC437, PC850, PC852, PC858, PC860, PC863, PC865, PC866, WPC1252, PC720, PC864 and WPC1256. Each printed byte SHALL occupy one character cell of the current font and SHALL be placed after the byte before it, in the order the bytes are received; the printer SHALL NOT reorder bytes and SHALL NOT join characters for any code page, matching ESC/POS printers, which print each byte they receive into the next cell from left to right. Shaping and right-to-left reordering of Arabic or any other script are therefore the POS's work, done before the bytes are sent. When the selected code page has no glyph table, or n is not in the profile's map, the printer SHALL emit a `printer.codepage.unsupported` event naming n and, when known, the code page, and SHALL render each byte from `80` to `ff` as a visible placeholder that occupies one character cell of the current font. When the selected code page has a glyph table but the simulator has no glyph for a byte, including a byte the code page leaves undefined, the printer SHALL render that byte as the same placeholder and SHALL NOT emit an event. For a code page for which the simulator has a character mapping (PC720, PC864 and WPC1256 among them), the text dump SHALL contain the characters that code page assigns to those bytes; otherwise the text dump SHALL contain U+FFFD for each such byte.

#### Scenario: Arabic code page on an Epson profile

- **GIVEN** printer `front` uses profile `epson-tm-t20iii`
- **WHEN** the POS sends `1b 40 1b 74 25 54 4f 54 41 4c c7 0a 1d 56 00`
- **THEN** no `printer.codepage.unsupported` event is emitted
- **AND** the receipt image shows `TOTAL` followed by the glyph of U+FE8D ARABIC LETTER ALEF ISOLATED FORM in one 12 × 24 dot cell, not a placeholder
- **AND** the text dump line is `TOTAL` followed by U+FE8D ARABIC LETTER ALEF ISOLATED FORM

#### Scenario: Arabic and Latin on one line stay in the order received

- **GIVEN** printer `front` uses profile `epson-tm-t20iii` with PC864 selected
- **WHEN** the POS sends the bytes `34 2e 37 35 20 df e8 e5 cc e5 e4 c7` followed by `0a 1d 56 00`
- **THEN** the receipt image holds twelve character cells in that byte order, `4.75` in the leftmost four
- **AND** the text dump line holds the twelve characters PC864 assigns to those bytes, in the same order

#### Scenario: Same code page under a different number

- **GIVEN** printer `front` uses profile `rongta-rp326`
- **WHEN** the POS sends `1b 74 16 c7 0a 1d 56 00`
- **THEN** no `printer.codepage.unsupported` event is emitted
- **AND** the receipt image shows the glyph of U+FE8D ARABIC LETTER ALEF ISOLATED FORM

#### Scenario: Byte without a glyph in a code page that has a table

- **GIVEN** printer `front` uses profile `epson-tm-t20iii` with PC864 selected
- **WHEN** the POS sends the byte `ff`, which PC864 leaves undefined, and ends the job
- **THEN** no `printer.codepage.unsupported` event is emitted
- **AND** the receipt image shows one placeholder occupying one 12 × 24 dot cell
- **AND** the text dump line is U+FFFD

#### Scenario: Number missing from the profile map

- **WHEN** the POS selects a code page number that is not in the printer profile's code-page map and then sends `41 c7 0a 1d 56 00`
- **THEN** a `printer.codepage.unsupported` event is emitted naming that number
- **AND** the text dump line is `A` followed by U+FFFD
- **AND** the receipt image shows `A` followed by one placeholder occupying one character cell

### Requirement: Job boundaries

The printer SHALL group the print data of each connection into jobs. A job SHALL end when a cut command (GS V, ESC i or ESC m) is processed, when the connection closes, or when no byte has been received on that connection for `job_idle_timeout_ms` milliseconds (2000 by default) after the last byte. Print data processed after a job ends SHALL start a new job. A job that contains no text, image, barcode or QR code (for example one holding only status queries, initialisation, feeds, cuts or drawer kicks) SHALL NOT produce a receipt or a `printer.job.completed` event.

#### Scenario: Cuts separate receipts on one connection

- **WHEN** the POS sends `41 0a 1d 56 00 42 0a 1d 56 00` on one connection
- **THEN** two receipts are completed in order, the first with text `A` and the second with text `B`

#### Scenario: Partial cuts end the job

- **WHEN** the POS sends `41 0a 1b 69 42 0a 1b 6d` on one connection
- **THEN** two receipts are completed in order, the first with text `A` and the second with text `B`, each ended by a cut

#### Scenario: Connection close ends the job

- **WHEN** the POS sends `1b 40 48 69 0a` and closes the connection without a cut
- **THEN** a receipt with text `Hi` is completed

#### Scenario: Idle timeout ends the job

- **GIVEN** printer `front` has `job_idle_timeout_ms: 2000`
- **WHEN** the POS sends `1b 40 48 69 0a` and then sends nothing while keeping the connection open
- **THEN** no receipt is completed before 2000 ms have passed since the last byte
- **AND** a receipt with text `Hi` is completed once 2000 ms have passed

#### Scenario: Status polling produces no receipt

- **WHEN** the POS connects, sends `1b 40 10 04 01 1b 70 00 19 fa`, reads the status reply and closes the connection
- **THEN** no receipt is stored
- **AND** no `printer.job.completed` event is emitted

### Requirement: Receipt output

For every completed job the printer SHALL store a PNG image and a UTF-8 text dump in the directory configured by `receipts_dir`, and SHALL emit a `printer.job.completed` event whose data contains the receipt id and the boundary that ended the job (`cut`, `connection-closed` or `idle-timeout`). The PNG image SHALL be black on white, exactly as wide as the profile's printable width, and as tall as the printed content. The text dump SHALL contain the printed text with the same line breaks as the image, and one line at the position of each image, barcode or QR code naming its kind, with the encoded data for barcodes and QR codes. Receipt ids SHALL be unique, and receipts of different printers that share a `receipts_dir` SHALL NOT overwrite each other. Stored receipts SHALL be retrievable through the control API by device id and receipt id.

#### Scenario: Completed job is stored

- **GIVEN** printer `front` has `receipts_dir: ./receipts`
- **WHEN** the POS sends `1b 40 48 69 0a 1d 56 00`
- **THEN** the receipts directory contains a new 576-dot-wide PNG image and a new text dump whose only text line is `Hi`
- **AND** a `printer.job.completed` event is emitted with device id `front`, the new receipt id and the boundary `cut`

#### Scenario: Text dump marks a barcode

- **WHEN** the POS prints `TOTAL`, an EAN-13 barcode with data `4006381333931` and a cut
- **THEN** the text dump contains the line `TOTAL` followed by a line naming EAN-13 and `4006381333931`

#### Scenario: Two printers share a receipts directory

- **GIVEN** printers `front` and `back` both have `receipts_dir: ./receipts`
- **WHEN** both printers complete a receipt at the same time
- **THEN** both receipts' PNG images and text dumps exist in the directory
- **AND** each receipt is retrievable through the control API under its own device id

### Requirement: Printer faults

The printer SHALL support the faults `paper-near-end`, `paper-out`, `cover-open` and `offline`, activated and cleared through the control API and the CLI. Faults SHALL be independent of each other, SHALL start inactive when the simulator starts, and SHALL stay active until cleared. Each activation or clearing that changes the printer's state SHALL emit one `printer.status.changed` event whose data contains `faults`, the names of the faults active after the change; activating an active fault or clearing an inactive one SHALL NOT emit an event. While `paper-out`, `cover-open` or `offline` is active (a blocking fault), the printer SHALL keep accepting connections and bytes, SHALL hold received print data and non-real-time commands unprocessed in the order received, and SHALL NOT complete any job, including by idle timeout or connection close. When the last blocking fault is cleared, the printer SHALL process the held data in order, applying the job boundaries it contains, and SHALL complete any job whose connection closed while it was held. `paper-near-end` SHALL NOT block printing.

#### Scenario: Paper out holds a receipt until cleared

- **GIVEN** the `paper-out` fault is active on printer `front`
- **WHEN** the POS sends `1b 40 48 69 0a 1d 56 00` and closes the connection, and `paper-out` is later cleared
- **THEN** no receipt is completed while `paper-out` is active
- **AND** after clearing, one receipt with text `Hi` is completed and `printer.job.completed` is emitted

#### Scenario: Offline printer holds data

- **GIVEN** the `offline` fault is active and the drawer is closed with `sensor_open_level: high`
- **WHEN** the POS sends `48 69 0a 1d 56 00` followed by `10 04 01`
- **THEN** the POS receives `1a`
- **AND** no receipt is completed while `offline` is active

#### Scenario: Paper near end still prints

- **GIVEN** the `paper-near-end` fault is active and the drawer is closed with `sensor_open_level: high`
- **WHEN** the POS sends `48 69 0a 1d 56 00`, then `10 04 01` and `10 04 04`
- **THEN** a receipt with text `Hi` is completed
- **AND** the POS receives `12` and then `1e`

#### Scenario: Status change events

- **GIVEN** printer `front` has no active faults
- **WHEN** `PUT /api/v1/devices/front/faults/cover-open` is sent twice
- **THEN** exactly one `printer.status.changed` event is emitted for printer `front`, with data `faults` equal to `["cover-open"]`

### Requirement: Multiple simultaneous connections

A printer SHALL accept several simultaneous connections, over one connection type or across all of its configured connections (for example TCP port 9100 and the serial link `front` at the same time). Faults, paper, cover and online state, and the cash drawer SHALL be shared by all connections of the printer. Pending undecoded bytes, print settings, the current job and ASB SHALL be separate for each connection, and each new connection SHALL start with the print settings in effect after ESC @. Replies SHALL be sent only on the connection that sent the request, and bytes from different connections SHALL never be combined into one receipt.

#### Scenario: Interleaved jobs stay separate

- **GIVEN** connections A and B are open to printer `front`
- **WHEN** A sends `41 41 0a`, B sends `42 42 0a`, A sends `1d 56 00` and B sends `1d 56 00`
- **THEN** two receipts are completed, one with text `AA` and one with text `BB`

#### Scenario: TCP and serial share printer state

- **GIVEN** printer `front` has a TCP connection on port 9100 and a serial connection with link `front`, and a POS client is connected on each
- **WHEN** the `paper-out` fault is activated
- **THEN** `10 04 04` sent on either connection receives `7e`

#### Scenario: Replies return to the requesting connection

- **GIVEN** connections A and B are open to printer `front`
- **WHEN** A sends `10 04 01`
- **THEN** A receives one status byte
- **AND** B receives no bytes

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

