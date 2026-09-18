## MODIFIED Requirements

### Requirement: Device definitions

Each entry of `devices` SHALL have an `id` and a `type` of `printer`, `scale` or `scanner`. Device ids SHALL be unique and SHALL consist of lowercase ASCII letters, digits and hyphens, starting with a letter or digit. A `printer` or `scale` SHALL require a `profile` for its own device type and at least one connection. A `scanner` SHALL require `mode` `keyboard` or `serial`; a `serial` scanner SHALL require at least one connection, and a `keyboard` scanner SHALL NOT have connections. A scanner `suffix` SHALL be one of `enter`, `tab` or `none`, and `drawer.sensor_open_level` SHALL be `high` or `low`. A keyboard scanner MAY set `typed_by` to `server` or `client`, defaulting to `server`; `typed_by` on a `serial` scanner SHALL be rejected, because a serial scan presses no keys. The cash drawer SHALL NOT be declared as a device; it SHALL be configured through the `drawer` key of its printer.

#### Scenario: Duplicate device id

- **GIVEN** two devices both have `id: front`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[1].id` stating that `front` is already used by `devices[0]`

#### Scenario: Drawer declared as a device

- **GIVEN** a device has `type: drawer`
- **WHEN** the configuration is loaded
- **THEN** validation fails, lists `printer`, `scale` and `scanner` as the valid types, and states that a drawer is configured on its printer

#### Scenario: Profile of the wrong device type

- **GIVEN** device `front` has `type: printer` and `profile: toledo8217-15kg`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at `devices[0].profile` stating that `toledo8217-15kg` is a scale profile

#### Scenario: Keyboard scanner with connections

- **GIVEN** device `lane1` has `mode: keyboard` and a `tcp` connection
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at the `connections` key of `lane1`

#### Scenario: Client typing on a serial scanner

- **GIVEN** device `lane2` has `mode: serial` and `typed_by: client`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at the `typed_by` key of `lane2` stating that a serial scanner types no keys

#### Scenario: Keyboard scanner defaults to server typing

- **GIVEN** device `lane1` has `mode: keyboard` and no `typed_by`
- **WHEN** the configuration is loaded
- **THEN** its `typed_by` is `server`

#### Scenario: Unknown typed_by value

- **GIVEN** device `lane1` has `mode: keyboard` and `typed_by: cli`
- **WHEN** the configuration is loaded
- **THEN** validation fails with an error at the `typed_by` key of `lane1` naming `server` and `client`
