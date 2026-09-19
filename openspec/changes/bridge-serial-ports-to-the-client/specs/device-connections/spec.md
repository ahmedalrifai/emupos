## ADDED Requirements

### Requirement: Bridged serial ports

`emupos bridge DEVICE` SHALL create a serial port on the machine it runs on and relay every byte, in order and unchanged, between that port and one `tcp` connection of `DEVICE` on the running simulator. The command SHALL work wherever it is run — the machine running the simulator, the machine running the POS, or a container beside the POS — and SHALL require no configuration change: a bridged device is a device with a `tcp` connection.

On macOS and Linux the bridge SHALL create a pseudo-terminal and publish it at the same stable link path a simulator-created port uses. On Windows it SHALL open an existing COM port given with `--port`, and SHALL refuse without one rather than fall back silently.

Before creating any port the bridge SHALL refuse, naming the reason and a fix: an unknown device; a device with no `tcp` connection; a device that speaks no serial protocol; and a simulator it cannot reach.

The port SHALL exist for exactly as long as the bridge's connection to the simulator. When that connection ends, or the simulator stops answering, the bridge SHALL close the port, remove any link it published, and exit non-zero, so that the POS sees the same failures a killed simulator produces locally. The bridge SHALL NOT reconnect and SHALL NOT hold the port open across an outage.

#### Scenario: A POS reads a weight through a bridge

- **GIVEN** scale `deli` has a `tcp` connection and the simulator is running
- **WHEN** `emupos bridge deli` runs on the machine with the POS, and the POS opens the printed link, configures the scale's framing and sends `57`
- **THEN** the POS receives the same bytes the device would have written to a simulator-created serial port

#### Scenario: The port dies with the simulator

- **GIVEN** a bridge relaying `deli`, and a POS holding its port open
- **WHEN** the simulator stops
- **THEN** the bridge closes the port, removes its link and exits non-zero
- **AND** the POS's next write fails and reopening the link fails, rather than the port staying open and silent

#### Scenario: Refused before anything is created

- **WHEN** `emupos bridge front` runs and `front` has no `tcp` connection
- **THEN** no serial port is created, and the message names the device and what it would need

#### Scenario: Windows needs a port to drive

- **GIVEN** Windows
- **WHEN** `emupos bridge deli` runs without `--port`
- **THEN** it refuses, and the fix names com0com and `--port`

## MODIFIED Requirements

### Requirement: Serial framing observation

Every serial device SHALL have an expected framing (baud rate, data bits, parity and stop bits), defined by its device profile or, for a serial-mode scanner, which has no profile, 9600 baud, 8 data bits, no parity and 1 stop bit. Framing SHALL be observed by whichever emupos process holds the pseudo-terminal: the simulator for a `pty: true` connection, and the bridge for a bridged serial port. That process SHALL observe the framing the client configures as far as the operating system exposes it: baud rate, data bits and parity on macOS, and baud rate only on Linux. Framing SHALL NOT be observed on Windows COM ports. A bridge SHALL report each distinct observed framing to the simulator, which SHALL compare it against the expected framing exactly as it does for a local pseudo-terminal. When an observed value differs from the expected value, the simulator SHALL emit one `connection.framing-mismatch` event listing each mismatched setting with its expected and observed values, and SHALL show a warning in the `emupos run` output. For a bridged port the simulator SHALL also return the mismatches to the bridge, which SHALL show the same warning in its own output, because that is the only output the operator of a containerised simulator can see. The event SHALL be emitted once per distinct observed framing, not per read. A framing mismatch SHALL NOT block, alter or delay any data.

#### Scenario: Data bits and parity mismatch on macOS

- **GIVEN** scale `deli` uses profile `toledo8217-15kg` on a simulator-created serial port on macOS
- **WHEN** a client configures the port for 9600 baud, 8 data bits and no parity, and sends `57`
- **THEN** one `connection.framing-mismatch` event for `deli` reports data bits expected 7 observed 8, and parity expected even observed none
- **AND** a warning is shown in the `emupos run` output
- **AND** the client still receives the weight reply

#### Scenario: Linux compares baud rate only

- **GIVEN** scale `deli` is on a simulator-created serial port on Linux
- **WHEN** a client configures 9600 baud with 8 data bits and no parity, and sends `57`
- **THEN** no `connection.framing-mismatch` event is emitted

#### Scenario: Baud rate mismatch on Linux

- **GIVEN** scale `deli` is on a simulator-created serial port on Linux
- **WHEN** a client configures 19200 baud and sends `57`
- **THEN** one `connection.framing-mismatch` event reports baud rate expected 9600 observed 19200
- **AND** the client receives the weight reply

#### Scenario: Unchanged framing is reported once

- **GIVEN** a framing mismatch has been reported for the client's current framing
- **WHEN** the client sends ten more requests without changing its framing
- **THEN** no further `connection.framing-mismatch` event is emitted

#### Scenario: Mismatch observed by a bridge

- **GIVEN** scale `deli` has a `tcp` connection and a bridge is relaying it on macOS
- **WHEN** a client opens the bridge's serial port, configures 9600 baud with 8 data bits and no parity, and sends `57`
- **THEN** one `connection.framing-mismatch` event for `deli` reports data bits expected 7 observed 8, and parity expected even observed none
- **AND** a warning is shown in the `emupos run` output and in the bridge's own output
- **AND** the client still receives the weight reply
