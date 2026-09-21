## MODIFIED Requirements

### Requirement: Run command

`emupos run [--config PATH] [--demo] [--ui]` SHALL load the configuration, open every device connection, start the control API, and then print a startup summary. The summary SHALL list each device's id, type and profile, each resolved connection endpoint (including serial link paths), and the API URL. It SHALL keep running and stream every event live, one line per event with the local time, device id, event type and a short human-readable summary, colour-coded by event family in a terminal. Warnings, such as a serial framing mismatch or an API bound to a non-loopback address, SHALL be shown distinctly from ordinary events. Ctrl+C SHALL stop the simulator as defined by the clean shutdown requirement of the device-connections capability.

With `--ui`, the command SHALL also serve the control page, as defined by the control-page capability, and the startup summary SHALL include the page's URL on the API port:

- when `api.host` is a loopback address, the URL SHALL use that address;
- when `api.host` is `0.0.0.0` or `::`, the URL SHALL use `127.0.0.1`;
- for any other address, the URL SHALL use that address, and the summary SHALL show a warning that a page opened through it can show the devices but cannot act on them.

`--ui` SHALL be accepted together with `--demo` and with `--config`.

#### Scenario: Startup summary

- **GIVEN** a configuration with printer `front` on `tcp: { port: 9100 }` and scale `deli` on `serial: { pty: true, link: deli }`
- **WHEN** the user runs `emupos run` on Linux
- **THEN** the output lists `front` with `127.0.0.1:9100`, `deli` with its link path under `$TMPDIR/emupos/`, and `http://127.0.0.1:8765`

#### Scenario: Live events

- **GIVEN** `emupos run` is running with printer `front`
- **WHEN** another terminal runs `emupos fault set front cover-open`
- **THEN** the `emupos run` output shows a line with the time, `front` and `printer.status.changed`

#### Scenario: Piped event stream

- **WHEN** the output of `emupos run` is redirected to a file and a scan is delivered on `lane1`
- **THEN** the file contains a plain-text line with `lane1` and `scanner.scan.delivered` and no ANSI escape sequences

#### Scenario: Startup with the control page

- **WHEN** the user runs `emupos run --demo --ui`
- **THEN** the startup summary includes `http://127.0.0.1:8765/` as the control page URL
- **AND** `GET http://127.0.0.1:8765/` answers with the page

#### Scenario: Control page on a wildcard address

- **GIVEN** a configuration with `api: { host: 0.0.0.0, port: 8765 }`
- **WHEN** the user runs `emupos run --ui`
- **THEN** the control page URL in the startup summary is `http://127.0.0.1:8765/`

#### Scenario: Control page on a non-loopback address

- **GIVEN** a configuration with `api: { host: 192.168.1.5, port: 8765 }`
- **WHEN** the user runs `emupos run --ui`
- **THEN** the control page URL in the startup summary is `http://192.168.1.5:8765/`
- **AND** a warning states that a page opened through that address cannot act on the devices
