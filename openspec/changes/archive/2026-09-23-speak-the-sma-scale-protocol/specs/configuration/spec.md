## MODIFIED Requirements

### Requirement: Device profiles

Printers and scales SHALL take their hardware characteristics from a device profile. emupos SHALL ship the built-in printer profiles `epson-tm-t20iii`, `xprinter-xp80t` and `rongta-rp326`, and the built-in scale profiles `toledo8217-15kg` and `sma-15kg`. A printer profile SHALL define the printable width in dots, the character cell size and columns of each font, the code-page number map, the default code page and the drawer sensor polarity. A printer profile MAY also define the printer-ID values GS I reports: the printer model ID, whether an autocutter is installed, whether the model answers the column emulation mode request, the maker name and the model name. A printer profile without those values SHALL be valid, and the printers using it SHALL send no reply to GS I. The profile of a device reachable over serial SHALL define its serial framing. A scale profile SHALL define its capacity, its resolution, the settle time of an unstable reading, and the protocol it speaks; and SHALL define the settings of that protocol and no other, so that a setting belonging to a different protocol is a validation error naming the key. A `toledo8217` scale profile SHALL define the integer digits and decimals of its weight replies. An `sma` scale profile SHALL define the units the model offers, in the order its unit key cycles them, each with its three-character abbreviation, decimal places and count-by; the maker, model, revision and serial number it reports in its About dialogue; and the interval between repeats of a continuous weight. The `profile` value SHALL name a built-in profile or give the path of a user-provided YAML profile file (any value containing a path separator or ending in `.yaml` or `.yml`). A user-provided profile SHALL be validated against the same rules as built-in profiles, and its errors SHALL name the profile file and the path within it. An unknown profile name SHALL be a validation error that lists the built-in profiles of the device's type.

#### Scenario: Unknown profile name

- **GIVEN** device `front` has `type: printer` and `profile: epson-tm-t88`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[0].profile` listing `epson-tm-t20iii`, `xprinter-xp80t` and `rongta-rp326`

#### Scenario: User-provided profile

- **GIVEN** `/work/pos/emupos.yaml` has a printer with `profile: ./profiles/my-80mm.yaml` and that file is a valid printer profile
- **WHEN** `emupos run --config /work/pos/emupos.yaml` starts
- **THEN** the printer uses the characteristics in `/work/pos/profiles/my-80mm.yaml`

#### Scenario: Invalid user-provided profile

- **GIVEN** `./profiles/my-80mm.yaml` has no paper width
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error naming `./profiles/my-80mm.yaml` and the missing key

#### Scenario: User-provided profile with printer-ID values

- **GIVEN** `./profiles/my-80mm.yaml` is a valid printer profile that defines a printer model ID, an installed autocutter, a maker name and a model name
- **WHEN** the configuration is loaded and a POS asks that printer for its model ID
- **THEN** the printer replies with the model ID from the profile

#### Scenario: Printer-ID values are optional

- **GIVEN** `./profiles/my-80mm.yaml` is a valid printer profile that defines no printer-ID values
- **WHEN** the configuration is loaded
- **THEN** validation succeeds

#### Scenario: Scale profile settings belong to its protocol

- **GIVEN** `./profiles/my-scale.yaml` names the protocol `sma` and defines the reply formatting of a `toledo8217` profile
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error naming `./profiles/my-scale.yaml` and the key that does not belong to `sma`

#### Scenario: Built-in SMA profile

- **WHEN** the built-in profile `sma-15kg` is loaded
- **THEN** its protocol is `sma`, its capacity is 15000 g, and it lists at least one unit with an abbreviation, decimal places and a count-by
- **AND** it defines the maker, model, revision and serial number reported in the About dialogue
