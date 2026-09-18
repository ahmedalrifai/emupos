## ADDED Requirements

### Requirement: Client-typed scans

A keyboard-mode scanner SHALL have a `typed_by` setting of `server` or `client`, defaulting to `server`. With `server` the simulator types the scan itself, as it does today. With `client` the machine that requested the scan types it, and the simulator SHALL keep everything else: validating the request, planning the keys, holding the scanner busy and publishing the delivery event.

For a `typed_by: client` scanner the simulator SHALL, on accepting a scan, answer with the scan's key plan — the same keys it would have typed, each identified as a physical key (its HID usage ID and whether Shift is held) or as one exact character — together with the scan id and the scanner's `inter_key_delay_ms`. It SHALL NOT type anything, and SHALL NOT check any operating-system keyboard prerequisite.

The client SHALL report the outcome of its typing. A `delivered` report SHALL publish the scan's `scanner.scan.delivered` event exactly as a server-typed scan does. A `failed` report SHALL free the scanner without publishing the event, and SHALL name how many keys the operating system accepted. A report naming a scan that is not the scan in progress SHALL do nothing.

A client-typed scan SHALL stop holding the scanner busy once its typing time, plus a grace period of at least 15 seconds, has passed without a report, so that a client that never reports back cannot make the scanner refuse every later scan. A `typed_by: server` scan SHALL NOT expire while the simulator is still delivering it.

#### Scenario: Key plan instead of delivery

- **GIVEN** keyboard scanner `lane1` with `typed_by: client` and no scan in progress
- **WHEN** a client requests a scan of `Ab1` with suffix `enter`
- **THEN** the response contains the scan id and the keys Shift+A, B, 1 and Enter as US-layout physical keys, with the scanner's inter-key delay
- **AND** nothing is typed by the simulator
- **AND** no `scanner.scan.delivered` event is published

#### Scenario: Scanner stays busy until the client reports

- **GIVEN** a client-typed scan accepted on `lane1` and not yet reported
- **WHEN** a client requests a second scan on `lane1`
- **THEN** the request is rejected because a scan is already in progress

#### Scenario: Delivered report publishes the event

- **GIVEN** a client-typed scan of `2112345012506` accepted on `lane1`
- **WHEN** the client reports it as delivered
- **THEN** exactly one `scanner.scan.delivered` event is published with that scan's `id`, `data` and mode `keyboard`
- **AND** a new scan on `lane1` is accepted

#### Scenario: Failed report frees the scanner without an event

- **GIVEN** a client-typed scan of `2112345012506` accepted on `lane1`
- **WHEN** the client reports it as failed after 7 of 14 keys were accepted
- **THEN** no `scanner.scan.delivered` event is published for that scan
- **AND** a new scan on `lane1` is accepted

#### Scenario: Stale report does nothing

- **GIVEN** a client-typed scan on `lane1` that has already been reported as delivered
- **WHEN** the client reports the same scan id again
- **THEN** no further event is published and the scanner stays free

#### Scenario: Client never reports back

- **GIVEN** a client-typed scan accepted on `lane1` whose client was killed before reporting
- **WHEN** the grace period after the scan's typing time has passed and a client requests a new scan on `lane1`
- **THEN** the new scan is accepted
- **AND** no `scanner.scan.delivered` event was published for the abandoned scan

#### Scenario: Unicode keys in the plan

- **GIVEN** keyboard scanner `lane1` with `typed_by: client`
- **WHEN** a client requests a scan of `كود` with `unicode` true
- **THEN** the plan's keys are the three exact characters followed by the Enter key

## MODIFIED Requirements

### Requirement: Scan requests

Scans SHALL be requested through `POST /api/v1/devices/{device_id}/scans` or `emupos scan`. The simulator SHALL validate each request and check every delivery prerequisite it is itself responsible for before accepting it, and SHALL then deliver the scan in the background. For a `typed_by: client` scanner the simulator SHALL NOT deliver the scan and SHALL NOT check the operating-system keyboard prerequisites, which belong to the client that types; it SHALL answer with the scan's key plan instead. `data` MUST be a non-empty string and `countdown_seconds` MUST be a non-negative integer. A rejected request SHALL deliver nothing and publish no `scanner.scan.delivered` event.

#### Scenario: Scan accepted before delivery

- **GIVEN** keyboard-mode scanner `lane1` with no scan in progress
- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with body `{ "data": "2112345012506" }`
- **THEN** the response has status 202 before the 3-second countdown ends
- **AND** no keystrokes are typed before the countdown ends

#### Scenario: Empty data rejected

- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with body `{ "data": "" }`
- **THEN** the response has status 422 and the standard error body

#### Scenario: Negative countdown rejected

- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with body `{ "data": "123", "countdown_seconds": -1 }`
- **THEN** the response has status 422 and nothing is typed

#### Scenario: Invalid data rejected for a client-typed scanner

- **GIVEN** keyboard scanner `lane1` with `typed_by: client`
- **WHEN** a client requests a scan of `كود42` without `unicode`
- **THEN** the response has status 422 and no key plan is returned

### Requirement: macOS Accessibility permission

On macOS, before accepting every keyboard-mode scan it types itself, the simulator SHALL check that it is trusted for Accessibility. When it is not trusted, the request SHALL be rejected with status 409 and the standard error body, whose message states that keystrokes cannot be posted and whose fix names System Settings > Privacy & Security > Accessibility and the application to allow, and names `typed_by: client` for a simulator that has no desktop of its own; nothing SHALL be typed and no `scanner.scan.delivered` event SHALL be published.

For a `typed_by: client` scanner the simulator SHALL NOT make this check. The client SHALL make it on its own machine before requesting the scan, and SHALL refuse the scan with the same message and fix.

#### Scenario: Not trusted for Accessibility

- **GIVEN** macOS and a simulator process not trusted for Accessibility
- **WHEN** a client requests a keyboard-mode scan on `lane1`
- **THEN** the response has status 409 and `error.fix` names System Settings > Privacy & Security > Accessibility
- **AND** nothing is typed and no `scanner.scan.delivered` event is published

#### Scenario: Permission granted while running

- **GIVEN** a scan on macOS was rejected for missing Accessibility trust
- **WHEN** the user grants the permission and a client requests the scan again without restarting the simulator
- **THEN** the response has status 202

#### Scenario: Client-typed scanner on a simulator without the permission

- **GIVEN** macOS, scanner `lane1` with `typed_by: client`, and a simulator process not trusted for Accessibility
- **WHEN** a client whose own process is trusted requests a scan on `lane1`
- **THEN** the scan is accepted with its key plan
- **AND** the scan is delivered and its `scanner.scan.delivered` event is published

### Requirement: Linux keyboard mode requires X11

On Linux, keyboard mode SHALL type through X11 only. Before accepting a keyboard-mode scan it types itself, the simulator SHALL reject the request with status 409 and the standard error body when no X11 display is available or the session is a Wayland session, with a fix stating that keyboard mode requires X11 and pointing to `mode: serial` and to `typed_by: client`; and when the X11 test extension library (libXtst) is missing, with a fix naming libXtst. Nothing SHALL be typed in either case.

For a `typed_by: client` scanner the simulator SHALL NOT make these checks. The client SHALL make them on its own machine before requesting the scan, and SHALL refuse the scan with the same messages and, for the session and display checks, a fix pointing to `mode: serial`.

#### Scenario: Wayland session

- **GIVEN** Linux with `XDG_SESSION_TYPE` set to `wayland`
- **WHEN** a client requests a keyboard-mode scan on `lane1`
- **THEN** the response has status 409 and `error.fix` mentions `mode: serial`

#### Scenario: No display

- **GIVEN** Linux with no `DISPLAY` environment variable
- **WHEN** a client requests a keyboard-mode scan on `lane1`
- **THEN** the response has status 409 and `error.fix` mentions `mode: serial`

#### Scenario: libXtst missing

- **GIVEN** an X11 session on Linux without libXtst installed
- **WHEN** a client requests a keyboard-mode scan on `lane1`
- **THEN** the response has status 409 and `error.fix` names libXtst

#### Scenario: The fix names the client-typing setting

- **GIVEN** Linux with no `DISPLAY` environment variable
- **WHEN** a client requests a keyboard-mode scan on a `typed_by: server` scanner
- **THEN** `error.fix` names `typed_by: client` as well as `mode: serial`

### Requirement: Windows privilege limitation

Windows discards keystrokes injected into a window running at a higher privilege level than the sending process, and still reports those keystrokes as accepted. The Windows documentation SHALL state that keyboard-mode scans do not reach such a window, that the process that types and the POS MUST run at the same privilege level, and that the simulator is not able to detect such discarded scans. When Windows reports that fewer keystrokes were accepted than were sent, the simulator SHALL print a warning in the `emupos run` output naming this limitation and SHALL NOT publish `scanner.scan.delivered` for that scan. When a client typed the scan, the same warning SHALL be printed in the `emupos run` output on receiving the client's failed report, and the client SHALL also name the limitation itself.

#### Scenario: Documented limitation

- **WHEN** a user reads the Windows setup guide
- **THEN** it states that keyboard-mode scans do not reach a POS running as administrator unless the process that types also runs as administrator

#### Scenario: Keystrokes refused by Windows

- **GIVEN** Windows reports that fewer keystrokes were accepted than were sent for a scan
- **WHEN** the scan finishes
- **THEN** the `emupos run` output shows a warning naming the privilege-level limitation
- **AND** no `scanner.scan.delivered` event is published for that scan

#### Scenario: Keystrokes refused on the client

- **GIVEN** scanner `lane1` with `typed_by: client`, and Windows reports on the client that 7 of 14 keystrokes were accepted
- **WHEN** the client reports the scan as failed
- **THEN** the `emupos run` output shows a warning naming the privilege-level limitation and the 7 of 14 keystrokes
- **AND** no `scanner.scan.delivered` event is published for that scan
