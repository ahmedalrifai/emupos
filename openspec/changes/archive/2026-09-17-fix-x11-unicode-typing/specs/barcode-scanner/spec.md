## MODIFIED Requirements

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
