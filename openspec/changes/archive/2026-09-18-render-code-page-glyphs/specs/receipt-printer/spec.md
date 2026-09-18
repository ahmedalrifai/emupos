## MODIFIED Requirements

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
