# Weighed-Item Barcodes

## Purpose

Generating weight- and price-embedded EAN-13 barcodes from configurable layouts.

## Requirements

### Requirement: Layout patterns

The system SHALL generate weighed-item EAN-13 barcodes from a layout, which is either a 13-character pattern or the name of a built-in preset. A pattern SHALL consist of: one or more literal digits at the start (the prefix, copied into the barcode unchanged); one contiguous run of `I` (item code); one contiguous run of either `W` (weight in grams) or `P` (price in minor currency units); and a single `C` as the last character (the EAN-13 check digit). Pattern letters SHALL be uppercase.

#### Scenario: Weight layout accepted

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWC`, item 12345 and 1250 g
- **THEN** the generated digits are the prefix `21`, the item field `12345`, the weight field `01250` and the check digit `6`

#### Scenario: Custom field widths accepted

- **WHEN** a barcode is requested with layout `28IIIIWWWWWWC`, item 1234 and 12500 g
- **THEN** the generated digits are `2812340125002`

### Requirement: Layout validation

A layout that is not a preset name and not a valid pattern SHALL be rejected without producing digits, with an error message that names the specific problem and a fix that shows a valid pattern and lists the preset names. The problems detected SHALL include: a length other than 13 characters; a character other than a digit, `I`, `W`, `P` or `C`; a missing `C`, a `C` in any position other than the last, or more than one `C`; no literal digit prefix; digits after the prefix; no `I` field; neither a `W` nor a `P` field; both a `W` and a `P` field; and a field whose letters are not contiguous.

#### Scenario: Wrong length

- **WHEN** a barcode is requested with layout `21IIIIIWWWWC`
- **THEN** the request is rejected with a message stating that the layout has 12 characters and 13 are required

#### Scenario: Check position missing or misplaced

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWW` or `21CIIIIIWWWWW`
- **THEN** the request is rejected with a message stating that the check digit `C` must be the last character

#### Scenario: Both weight and price fields

- **WHEN** a barcode is requested with layout `21IIIIIWWPPPC`
- **THEN** the request is rejected with a message stating that a layout contains either a `W` field or a `P` field, not both

#### Scenario: Split field

- **WHEN** a barcode is requested with layout `21IIIIWWWWWIC`
- **THEN** the request is rejected with a message stating that the `I` field is not contiguous

### Requirement: Built-in presets

The system SHALL provide the built-in presets `weight-21` (pattern `21IIIIIWWWWWC`) and `price-23` (pattern `23IIIIIPPPPPC`). A preset name SHALL be accepted anywhere a layout pattern is accepted and SHALL behave exactly as its pattern. An unknown name SHALL be rejected as an invalid layout.

#### Scenario: Weight preset

- **WHEN** a barcode is requested with layout `weight-21`, item 12345 and 1250 g
- **THEN** the generated digits are `2112345012506`

#### Scenario: Price preset

- **WHEN** a barcode is requested with layout `price-23`, item 12345 and price 1299
- **THEN** the generated digits are `2312345012999`

#### Scenario: Unknown preset

- **WHEN** a barcode is requested with layout `weight-99`
- **THEN** the request is rejected and the fix lists `weight-21` and `price-23`

### Requirement: Field values

The item code SHALL be a non-negative integer written into the `I` field left-padded with zeros. A weight SHALL be a non-negative integer number of grams written into the `W` field left-padded with zeros. A price SHALL be a non-negative integer number of minor currency units written into the `P` field left-padded with zeros. No value SHALL be rounded or truncated.

#### Scenario: Zero padding

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWC`, item 42 and 750 g
- **THEN** the generated digits are `2100042007505`

#### Scenario: Price in minor units

- **WHEN** a barcode is requested with layout `23IIIIIPPPPPC`, item 12345 and price 1299
- **THEN** positions 8 to 12 of the generated digits are `01299`

### Requirement: Value kind matches the layout

A layout with a `W` field SHALL require a weight and SHALL reject a price. A layout with a `P` field SHALL require a price and SHALL reject a weight. A request that supplies both a weight and a price, or no item code, SHALL be rejected. Each rejection message SHALL name the value that is missing or not allowed.

#### Scenario: Price given for a weight layout

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWC`, item 12345 and price 1299
- **THEN** the request is rejected with a message stating that this layout requires a weight

#### Scenario: Weight missing

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWC` and item 12345 only
- **THEN** the request is rejected with a message stating that a weight is required

### Requirement: Values that do not fit their field

A value with more digits than its field, or a negative value, SHALL be rejected without producing digits, with a message naming the field, its width and the largest value it holds.

#### Scenario: Weight overflow

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWC`, item 12345 and 100000 g
- **THEN** the request is rejected with a message stating that the weight field holds at most 99999 g

#### Scenario: Item code overflow

- **WHEN** a barcode is requested with layout `21IIIIIWWWWWC`, item 123456 and 1250 g
- **THEN** the request is rejected with a message stating that the item field holds at most 5 digits

#### Scenario: Negative price

- **WHEN** a barcode is requested with layout `23IIIIIPPPPPC`, item 12345 and price -5
- **THEN** the request is rejected

### Requirement: EAN-13 check digit

The final digit SHALL be the EAN-13 check digit of the first 12 digits: each digit is multiplied by 1 or 3, alternating and starting with 1 at the leftmost digit; the check digit is the amount that raises the sum to the next multiple of 10, or 0 when the sum is already a multiple of 10.

#### Scenario: Check digit computed

- **WHEN** the first 12 digits are `211234501250`
- **THEN** the weighted sum is 44 and the check digit is 6, giving `2112345012506`

#### Scenario: Sum already a multiple of 10

- **WHEN** the first 12 digits are `211234500080`
- **THEN** the weighted sum is 40 and the check digit is 0, giving `2112345000800`

#### Scenario: Every generated barcode validates

- **WHEN** any accepted request generates digits
- **THEN** the 13 digits pass EAN-13 check-digit validation

### Requirement: Barcode generation in the CLI

`emupos barcode weighed --layout PATTERN --item N (--weight VALUE | --price MINOR) [--save PATH]` SHALL print the 13 generated digits and exit with status 0. `PATTERN` SHALL accept a pattern or a preset name. `VALUE` SHALL use the same forms as `emupos scale set` (`1.25kg` or `1250g`) and MUST convert to a whole number of grams, and `MINOR` SHALL be an integer number of minor currency units. The command SHALL generate barcodes without a running simulator and SHALL produce the same digits as `POST /api/v1/barcodes/weighed` for the same input. Supplying both `--weight` and `--price`, or any input rejected by this capability, SHALL exit with status 2 and print the error message and fix; no file SHALL be written.

#### Scenario: Weight barcode from the CLI

- **WHEN** a user runs `emupos barcode weighed --layout weight-21 --item 12345 --weight 1.25kg`
- **THEN** the output contains `2112345012506` and the command exits with status 0

#### Scenario: Works without the simulator

- **GIVEN** no simulator is running
- **WHEN** a user runs `emupos barcode weighed --layout 23IIIIIPPPPPC --item 12345 --price 1299`
- **THEN** the output contains `2312345012999` and the command exits with status 0

#### Scenario: Plain output for scripts

- **WHEN** a user runs `emupos barcode weighed --layout weight-21 --item 12345 --weight 1250g` with output redirected to a file
- **THEN** the file contains exactly `2112345012506` followed by a newline

#### Scenario: Weight and price together

- **WHEN** a user runs `emupos barcode weighed --layout weight-21 --item 12345 --weight 1250g --price 1299`
- **THEN** the command exits with status 2 and states that `--weight` and `--price` are mutually exclusive

### Requirement: Barcode image output

When `--save PATH` is given, `emupos barcode weighed` SHALL write a PNG image to PATH containing the EAN-13 symbol for the generated digits with the digits printed as human-readable text beneath it, in addition to printing the digits. Decoding the image with a barcode reader SHALL yield exactly the generated 13 digits. When the file cannot be written, the command SHALL exit with status 1 and name the path.

#### Scenario: Save a label image

- **WHEN** a user runs `emupos barcode weighed --layout weight-21 --item 12345 --weight 1.25kg --save label.png`
- **THEN** `label.png` is a valid PNG image
- **AND** decoding it as an EAN-13 barcode yields `2112345012506`

#### Scenario: Unwritable path

- **WHEN** a user runs the same command with `--save` pointing into a directory that does not exist
- **THEN** the command exits with status 1 and the message names that path
