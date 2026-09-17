# Barcode Scanner

## Purpose

Delivering scans as keyboard-wedge keystrokes or serial data, with suffix and timing options.
## Requirements
### Requirement: Scanner modes

A scanner device SHALL deliver each scan in the mode set by its `mode` configuration: in `keyboard` mode it SHALL type the scan into the window that has keyboard focus, as a keyboard-wedge scanner does; in `serial` mode it SHALL write the scan as bytes to its configured connections. Every scan SHALL end with the configured `suffix` (`enter`, `tab` or `none`), which SHALL default to `enter`. In keyboard mode, `inter_key_delay_ms` SHALL default to 10.

#### Scenario: Keyboard-mode defaults

- **GIVEN** a scanner `lane1` configured with `type: scanner` and `mode: keyboard` and no `suffix` or `inter_key_delay_ms`
- **WHEN** the simulator starts and a client requests `GET /api/v1/devices/lane1`
- **THEN** the device reports mode `keyboard`, suffix `enter` and an inter-key delay of 10 ms

#### Scenario: Serial-mode scanner

- **GIVEN** a scanner `lane2` configured with `mode: serial` and `connections: [ { serial: { pty: true, link: lane2 } } ]`
- **WHEN** a scan of `123` is delivered
- **THEN** a client that has opened the `lane2` pty reads `31 32 33 0d`
- **AND** no keystrokes are typed

### Requirement: Scan requests

Scans SHALL be requested through `POST /api/v1/devices/{device_id}/scans` or `emupos scan`. The simulator SHALL validate each request and check every delivery prerequisite defined by this capability before accepting it, and SHALL then deliver the scan in the background. `data` MUST be a non-empty string and `countdown_seconds` MUST be a non-negative integer. A rejected request SHALL deliver nothing and publish no `scanner.scan.delivered` event.

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

### Requirement: One scan at a time per scanner

While a scan is in progress on a scanner, from acceptance until its delivery has finished or failed, another scan request for the same scanner SHALL be rejected with status 409 and the standard error body, and the scan in progress SHALL continue unaffected. Scans for a different scanner SHALL NOT be affected.

#### Scenario: Second scan during the countdown

- **GIVEN** a scan of `111` accepted on `lane1` whose countdown has not ended
- **WHEN** a client requests a scan of `222` on `lane1`
- **THEN** the response has status 409 with an error message stating that a scan is already in progress on `lane1`
- **AND** only `111` and its suffix are delivered

#### Scenario: Scan after delivery finishes

- **GIVEN** a scan on `lane1` whose `scanner.scan.delivered` event has been published
- **WHEN** a client requests a new scan on `lane1`
- **THEN** the response has status 202

#### Scenario: Different scanner is independent

- **GIVEN** a scan in progress on `lane1`
- **WHEN** a client requests a scan on serial-mode scanner `lane2`
- **THEN** the response has status 202

### Requirement: Delivery event

After the last keystroke or byte of a scan, including its suffix, has been delivered, the simulator SHALL publish exactly one `scanner.scan.delivered` event whose data contains `id` (the scan id returned with the 202 response), `data` (the scanned string) and `mode`. A scan that is not delivered SHALL NOT publish this event.

#### Scenario: Event follows the suffix

- **GIVEN** a client subscribed to `WS /api/v1/events`
- **WHEN** a scan of `2112345012506` accepted on `lane1` is delivered with suffix `enter`
- **THEN** the client receives a message with `type` `scanner.scan.delivered`, `device_id` `lane1`, and data `id` equal to the id from the 202 response, `data` `2112345012506` and `mode` `keyboard`
- **AND** the message arrives after the Enter keystroke was typed

### Requirement: Scan countdown

Delivery of a scan SHALL begin no earlier than `countdown_seconds` seconds after the scan is accepted, giving the user time to focus the POS window in keyboard mode. A countdown of 0 SHALL start delivery immediately. The countdown SHALL apply in both keyboard and serial mode.

#### Scenario: Default countdown

- **WHEN** a keyboard-mode scan is accepted without `countdown_seconds`
- **THEN** the first keystroke is typed no earlier than 3 seconds after acceptance

#### Scenario: No countdown

- **WHEN** a keyboard-mode scan is accepted with `countdown_seconds` 0
- **THEN** typing starts without waiting

### Requirement: US-layout key codes by default

In keyboard mode with `unicode` false, each character SHALL be typed as the physical key that produces it on a US keyboard layout, pressing Shift where the US layout requires it, as a real USB keyboard-wedge scanner does. The characters produced in the focused window SHALL therefore depend on the operating system's active keyboard layout exactly as they do for a real scanner. With `unicode` false, `data` MUST contain only printable ASCII characters (`20` to `7e`); other characters SHALL be rejected with status 422 and an error whose fix says to use `unicode: true` (or `--unicode` in the CLI).

#### Scenario: Key codes for mixed characters

- **WHEN** a keyboard-mode scan of `Ab1-` is delivered with `unicode` false
- **THEN** the keystrokes are Shift+A, B, 1 and the minus key, identified by their US-layout physical keys, followed by Enter

#### Scenario: Non-US layout garbles letters

- **GIVEN** the operating system's active keyboard layout is Arabic
- **WHEN** a keyboard-mode scan of `ABC123` is delivered with `unicode` false
- **THEN** the focused window receives the characters the Arabic layout assigns to the physical keys A, B, C, 1, 2 and 3, not `ABC123`

#### Scenario: Non-ASCII data without unicode

- **WHEN** a client requests a keyboard-mode scan of `كود42` without `unicode`
- **THEN** the response has status 422 and `error.fix` mentions `unicode`
- **AND** nothing is typed

### Requirement: Exact-character typing

In keyboard mode with `unicode` true, the simulator SHALL type each character of `data` exactly, including the case of letters, independent of the active keyboard layout and of Caps Lock. The suffix SHALL still be typed as its key.

On Windows and macOS, characters typed this way carry no physical key, so an application that reads the key position (for example `KeyboardEvent.code` in a browser) does not see the keys a scanner would press. On Linux, a character that the active keyboard layout has on a key's first or Shift level SHALL be typed with that key, with Shift where needed, and carries that key's position; other characters carry no physical key. The documentation SHALL state this.

The characters SHALL arrive exactly at any `inter_key_delay_ms`, including 0, and when the focused application handles the keystrokes later than the simulator types them. After the scan, Caps Lock SHALL be in the state it had before the scan. After the simulator stops normally (Ctrl+C or SIGTERM), typing exact characters SHALL NOT have left the operating system's keyboard configuration changed.

On Linux, each different character of a scan that the active layout does not have uses one unused X11 key code. When a scan has more such characters than the X server has unused key codes, the simulator SHALL reuse the key code of the least recently typed character. Before reusing it, the simulator SHALL wait until the focused application has read the keyboard map since the simulator last changed it. When that cannot be observed, the simulator SHALL instead wait until that character was typed 2 seconds earlier. A scan SHALL wait at most 2 seconds in total; an application still behind after that can read the new character. The Linux documentation SHALL state this limit.

Key codes that a killed simulator left bound SHALL be cleared by the next simulator when it opens the keyboard, unless they no longer hold the characters the killed simulator bound.

#### Scenario: Arabic characters typed exactly

- **GIVEN** the operating system's active keyboard layout is US
- **WHEN** a keyboard-mode scan of `كود-42` is delivered with `unicode` true
- **THEN** the focused window receives exactly `كود-42` followed by an Enter keystroke

#### Scenario: Capital letters keep their case

- **GIVEN** the operating system's active keyboard layout is Arabic
- **WHEN** a keyboard-mode scan of `AaZz!9` is delivered with `unicode` true
- **THEN** the focused window receives exactly `AaZz!9` followed by an Enter keystroke

#### Scenario: Caps Lock is on

- **GIVEN** Caps Lock is on
- **WHEN** a keyboard-mode scan of `abc123` is delivered with `unicode` true
- **THEN** the focused window receives exactly `abc123` followed by an Enter keystroke
- **AND** Caps Lock is on after the scan

#### Scenario: Characters on the active layout use its keys

- **GIVEN** Linux, and the active keyboard layout is Arabic
- **WHEN** a keyboard-mode scan of `كود-42` is delivered with `unicode` true
- **THEN** the focused window receives exactly `كود-42` followed by an Enter keystroke
- **AND** each keystroke is the Arabic layout's key for its character, and the keyboard map is not changed

#### Scenario: No inter-key delay

- **GIVEN** scanner `lane1` with `inter_key_delay_ms: 0`
- **WHEN** a keyboard-mode scan of `كود-42` is delivered with `unicode` true
- **THEN** the focused window receives exactly `كود-42` followed by an Enter keystroke

#### Scenario: Application handles the keystrokes late

- **GIVEN** the focused application does not handle any keystroke until the whole scan has been typed
- **WHEN** a keyboard-mode scan of `كود-42` is delivered with `unicode` true
- **THEN** the application receives exactly `كود-42` followed by an Enter keystroke once it handles them

#### Scenario: Long scan on the active layout, handled late

- **GIVEN** Linux, the active keyboard layout is US, and the focused application does not handle any keystroke until the whole scan has been typed
- **WHEN** a keyboard-mode scan of the 26 lowercase letters, the 26 capital letters and the 10 digits is delivered with `unicode` true
- **THEN** the application receives exactly that text followed by an Enter keystroke once it handles them

#### Scenario: More missing characters than unused key codes

- **GIVEN** Linux, the active keyboard layout is US, the X server has 19 unused key codes, and the focused application handles each keystroke as it arrives
- **WHEN** a keyboard-mode scan of the 28 Arabic letters `ابتثجحخدذرزسشصضطظعغفقكلمنهوي` is delivered with `unicode` true
- **THEN** the application receives exactly those letters followed by an Enter keystroke

#### Scenario: More missing characters than unused key codes, handled late

- **GIVEN** Linux, the active keyboard layout is US, the X server has 19 unused key codes, and the focused application handles no keystroke during the first second of the scan
- **WHEN** a keyboard-mode scan of the 28 Arabic letters `ابتثجحخدذرزسشصضطظعغفقكلمنهوي` is delivered with `unicode` true
- **THEN** the application receives exactly those letters followed by an Enter keystroke once it handles them

#### Scenario: No keyboard changes left after stopping

- **GIVEN** Linux, and a simulator that delivered a keyboard-mode scan of `كود-42` with `unicode` true while the active layout was US
- **WHEN** the simulator stops on Ctrl+C or SIGTERM
- **THEN** the X server has the same unused key codes as before the simulator started

#### Scenario: Key codes left by a killed simulator

- **GIVEN** Linux, and a simulator that was killed with SIGKILL after a keyboard-mode scan of `كود-42` with `unicode` true while the active layout was US
- **WHEN** another simulator delivers its first keyboard-mode scan
- **THEN** the key codes the killed simulator bound are unused again
- **AND** a key code that another program changed after the kill keeps that program's keysyms

### Requirement: Keyboard suffix and inter-key delay

In keyboard mode, suffix `enter` SHALL be typed as the Enter key, `tab` as the Tab key, and `none` SHALL type nothing after the data. At least `inter_key_delay_ms` milliseconds SHALL elapse between consecutive keystrokes, including between the last data keystroke and the suffix.

#### Scenario: Tab suffix

- **GIVEN** scanner `lane1` with `suffix: tab`
- **WHEN** a keyboard-mode scan of `123` is delivered
- **THEN** the keystrokes are 1, 2, 3 and Tab

#### Scenario: No suffix

- **GIVEN** scanner `lane1` with `suffix: none`
- **WHEN** a keyboard-mode scan of `123` is delivered
- **THEN** the keystrokes are 1, 2 and 3 only

#### Scenario: Inter-key delay honoured

- **GIVEN** scanner `lane1` with `inter_key_delay_ms: 25`
- **WHEN** a keyboard-mode scan of `123` is delivered with suffix `enter`
- **THEN** each of the four keystrokes starts at least 25 ms after the previous one

### Requirement: macOS Accessibility permission

On macOS, before accepting every keyboard-mode scan, the simulator SHALL check that it is trusted for Accessibility. When it is not trusted, the request SHALL be rejected with status 409 and the standard error body, whose message states that keystrokes cannot be posted and whose fix names System Settings > Privacy & Security > Accessibility and the application to allow; nothing SHALL be typed and no `scanner.scan.delivered` event SHALL be published.

#### Scenario: Not trusted for Accessibility

- **GIVEN** macOS and a simulator process not trusted for Accessibility
- **WHEN** a client requests a keyboard-mode scan on `lane1`
- **THEN** the response has status 409 and `error.fix` names System Settings > Privacy & Security > Accessibility
- **AND** nothing is typed and no `scanner.scan.delivered` event is published

#### Scenario: Permission granted while running

- **GIVEN** a scan on macOS was rejected for missing Accessibility trust
- **WHEN** the user grants the permission and a client requests the scan again without restarting the simulator
- **THEN** the response has status 202

### Requirement: Linux keyboard mode requires X11

On Linux, keyboard mode SHALL type through X11 only. Before accepting a keyboard-mode scan, the simulator SHALL reject the request with status 409 and the standard error body when no X11 display is available or the session is a Wayland session, with a fix stating that keyboard mode requires X11 and pointing to `mode: serial`; and when the X11 test extension library (libXtst) is missing, with a fix naming libXtst. Nothing SHALL be typed in either case.

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

### Requirement: Windows privilege limitation

Windows discards keystrokes injected into a window running at a higher privilege level than the sending process, and still reports those keystrokes as accepted. The Windows documentation SHALL state that keyboard-mode scans do not reach such a window, that the simulator and the POS MUST run at the same privilege level, and that the simulator is not able to detect such discarded scans. When Windows reports that fewer keystrokes were accepted than were sent, the simulator SHALL print a warning in the `emupos run` output naming this limitation and SHALL NOT publish `scanner.scan.delivered` for that scan.

#### Scenario: Documented limitation

- **WHEN** a user reads the Windows setup guide
- **THEN** it states that keyboard-mode scans do not reach a POS running as administrator unless emupos also runs as administrator

#### Scenario: Keystrokes refused by Windows

- **GIVEN** Windows reports that fewer keystrokes were accepted than were sent for a scan
- **WHEN** the scan finishes
- **THEN** the `emupos run` output shows a warning naming the privilege-level limitation
- **AND** no `scanner.scan.delivered` event is published for that scan

### Requirement: Serial-mode delivery

In serial mode, a scan SHALL be written to the scanner's connections as the UTF-8 bytes of `data` followed by the suffix bytes: `0d` for `enter`, `09` for `tab`, and no bytes for `none`. `unicode` SHALL have no effect in serial mode, and no keyboard permission checks SHALL apply.

#### Scenario: Enter suffix

- **GIVEN** serial-mode scanner `lane2` with `suffix: enter` and a client reading its pty
- **WHEN** a client requests a scan of `2112345012506`
- **THEN** the client reads exactly `32 31 31 32 33 34 35 30 31 32 35 30 36 0d`
- **AND** a `scanner.scan.delivered` event with data `mode` `serial` follows

#### Scenario: Tab suffix

- **GIVEN** serial-mode scanner `lane2` with `suffix: tab`
- **WHEN** a client requests a scan of `ABC-123`
- **THEN** the client reads exactly `41 42 43 2d 31 32 33 09`

#### Scenario: Countdown in serial mode

- **WHEN** a client requests a serial-mode scan of `123` with `countdown_seconds` 2
- **THEN** no bytes are written before 2 seconds have passed
- **AND** `31 32 33 0d` is written after the countdown ends

