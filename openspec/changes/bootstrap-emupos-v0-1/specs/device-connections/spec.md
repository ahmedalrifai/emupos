## ADDED Requirements

### Requirement: TCP listeners

Each `tcp` connection entry of a device SHALL open a TCP listener on the configured `port`. When `host` is omitted the listener SHALL bind to `127.0.0.1` only; when `host` is given it SHALL bind to that address. A connected client SHALL exchange bytes directly with the device: the simulator SHALL NOT add any handshake, banner or framing.

#### Scenario: Default host is loopback only

- **GIVEN** device `front` has the connection `tcp: { port: 9100 }`
- **WHEN** `emupos run` starts
- **THEN** a client connecting to `127.0.0.1:9100` is accepted
- **AND** port 9100 is not listening on any non-loopback address

#### Scenario: Explicit host

- **GIVEN** device `front` has the connection `tcp: { host: 0.0.0.0, port: 9100 }`
- **WHEN** `emupos run` starts
- **THEN** port 9100 accepts clients on every IPv4 interface of the machine

#### Scenario: Nothing is sent on connect

- **WHEN** a client connects to `127.0.0.1:9100` and sends no bytes
- **THEN** the client receives no bytes from the simulator

### Requirement: Startup fails when an endpoint is unavailable

If any configured connection is not able to be opened, `emupos run` SHALL exit with status 1 before any device becomes reachable. It SHALL first close every listener, serial port and link it had already opened, and SHALL print a message naming the device id and the unavailable endpoint.

#### Scenario: TCP port already in use

- **GIVEN** another process is listening on `127.0.0.1:9100`
- **AND** device `front` has the connection `tcp: { port: 9100 }`
- **WHEN** `emupos run` starts
- **THEN** it exits with status 1
- **AND** the message names device `front` and states that port `9100` is already in use

#### Scenario: Already opened endpoints are released

- **GIVEN** device `front` has `tcp: { port: 9100 }`, device `kitchen` has `tcp: { port: 9101 }`, and another process is listening on port 9101
- **WHEN** `emupos run` exits because of the conflict
- **THEN** nothing is left listening on port 9100

### Requirement: Multiple connections and clients per device

A device with several connection entries SHALL be reachable on all of them at the same time, and every connection SHALL act on the same device state. A TCP listener SHALL accept several simultaneous clients and SHALL keep accepting new clients after earlier ones disconnect. Reply bytes SHALL be written only to the connection whose bytes caused them. A client disconnecting or resetting its connection SHALL NOT affect the device's other connections.

#### Scenario: TCP and serial act on the same device

- **GIVEN** device `front` has the connections `tcp: { port: 9100 }` and `serial: { pty: true, link: front }`
- **WHEN** the `paper-out` fault is activated through the control API
- **THEN** a real-time paper status query sent over TCP and the same query sent over the serial link both report paper out

#### Scenario: Replies go to the requesting client

- **GIVEN** clients A and B are both connected to `127.0.0.1:9100`
- **WHEN** client A sends a real-time status query
- **THEN** client A receives the status reply
- **AND** client B receives no bytes

#### Scenario: Abrupt disconnect is isolated

- **GIVEN** two clients are connected to `127.0.0.1:9100`
- **WHEN** one client resets its connection in the middle of sending a job
- **THEN** the other client keeps exchanging bytes with the device
- **AND** a new client connecting to `127.0.0.1:9100` is accepted

### Requirement: Simulator-created serial ports on macOS and Linux

On macOS and Linux, a `serial` connection entry with `pty: true` SHALL make the simulator create a pseudo-terminal pair itself, without any external driver or tool. The port SHALL be in raw mode: the simulator SHALL NOT echo bytes back, and SHALL NOT apply line-ending, flow-control or signal-character translation in either direction. The simulator SHALL keep its own side of the pair open for its whole run, so that a client that closes the port and opens it again reaches the same device.

#### Scenario: Port exists without external tools

- **GIVEN** device `deli` has the connection `serial: { pty: true, link: deli }`
- **WHEN** `emupos run` starts on macOS
- **THEN** the serial port for `deli` exists and a client opens it successfully

#### Scenario: No echo

- **GIVEN** printer `front` has the connection `serial: { pty: true, link: front }`
- **WHEN** a client opens that port and writes `1b 40 0a`
- **THEN** the client reads no bytes back

#### Scenario: No translation of replies

- **GIVEN** scale `deli` is on a simulator-created serial port
- **WHEN** a client sends `57`
- **THEN** the reply ends with the byte `0d`, not `0a` and not `0d 0a`

#### Scenario: Client reconnects

- **GIVEN** a client has opened the `deli` port, exchanged data and closed the port
- **WHEN** the client opens the same path again and sends `57`
- **THEN** it receives a weight reply from scale `deli`

### Requirement: Stable serial link paths

For every `pty: true` connection the simulator SHALL publish a symbolic link, named by the entry's `link`, inside an `emupos` directory in the user's temporary directory (`$TMPDIR`, or `/tmp` when `TMPDIR` is unset), for example `$TMPDIR/emupos/deli`, pointing to the pseudo-terminal device. The link path SHALL be the same on every run with the same configuration. The `emupos` link directory SHALL grant no access to other users. A link left behind by an earlier run SHALL be replaced. The link path and the device path it points to SHALL be shown in the `emupos run` startup output and in the device description returned by the control API.

#### Scenario: Link path survives a restart

- **GIVEN** `emupos run` published `$TMPDIR/emupos/deli` and was then stopped
- **WHEN** `emupos run` starts again with the same configuration
- **THEN** `$TMPDIR/emupos/deli` exists again and a client opening it reaches scale `deli`

#### Scenario: Stale link is replaced

- **GIVEN** `$TMPDIR/emupos/deli` exists and points to a pseudo-terminal that no longer exists
- **WHEN** `emupos run` starts with device `deli` using `link: deli`
- **THEN** startup succeeds and the link points to the newly created port

#### Scenario: Link directory is private

- **WHEN** `emupos run` creates the `emupos` link directory
- **THEN** the directory's permissions grant nothing to group or other users

#### Scenario: Paths are reported

- **WHEN** `emupos run` starts with device `deli` using `link: deli`
- **THEN** the startup output shows the expanded link path and the pseudo-terminal device path it points to
- **AND** `GET /api/v1/devices/deli` includes the same link path

### Requirement: Existing serial ports

A `serial` connection entry with `port` SHALL open that existing serial port: a COM port name such as `COM5` on Windows (typically one end of a user-installed com0com pair), or a device path such as `/dev/ttyUSB0` on macOS and Linux. The simulator SHALL open the port with the device's expected serial framing. On Windows, a `pty: true` entry SHALL fail startup with status 1 and a message directing the user to use `port` with a com0com pair.

#### Scenario: COM port on Windows

- **GIVEN** com0com provides the pair `COM5` and `COM6`, and scale `deli` has `serial: { port: COM5 }`
- **WHEN** `emupos run` starts and a POS opens `COM6` and sends `57`
- **THEN** the POS receives a weight reply from scale `deli`

#### Scenario: Missing COM port

- **GIVEN** no port named `COM5` exists and scale `deli` has `serial: { port: COM5 }`
- **WHEN** `emupos run` starts on Windows
- **THEN** it exits with status 1
- **AND** the message names `COM5` and device `deli`, states that serial devices on Windows need a virtual port pair such as com0com, and suggests running `emupos doctor`

#### Scenario: pty requested on Windows

- **GIVEN** scale `deli` has `serial: { pty: true, link: deli }`
- **WHEN** `emupos run` starts on Windows
- **THEN** it exits with status 1
- **AND** the message names device `deli` and tells the user to use `serial: { port: COMx }` with a com0com pair

### Requirement: Serial framing observation

Every serial device SHALL have an expected framing (baud rate, data bits, parity and stop bits), defined by its device profile or, for a serial-mode scanner, which has no profile, 9600 baud, 8 data bits, no parity and 1 stop bit. For `pty: true` connections the simulator SHALL observe the framing the client configures as far as the operating system exposes it: baud rate, data bits and parity on macOS, and baud rate only on Linux. Framing SHALL NOT be observed on Windows COM ports. When an observed value differs from the expected value, the simulator SHALL emit one `connection.framing-mismatch` event listing each mismatched setting with its expected and observed values, and SHALL show a warning in the `emupos run` output. The event SHALL be emitted once per distinct observed framing, not per read. A framing mismatch SHALL NOT block, alter or delay any data.

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

### Requirement: Binary transparency

Every connection type SHALL carry all byte values from `00` to `ff` unchanged and in order, in both directions. The connection layer SHALL NOT interpret any byte as a line ending, flow-control, end-of-file or interrupt character.

#### Scenario: All byte values reach the device

- **WHEN** a client sends the 256 bytes `00 01 02 … fe ff` over a TCP connection, and again over a serial connection
- **THEN** the device receives exactly those 256 bytes in that order each time

#### Scenario: Control bytes in replies are preserved

- **WHEN** a device reply contains the bytes `02 11 13 1a 0d`
- **THEN** the client receives `02 11 13 1a 0d` unchanged

### Requirement: Connection events

The simulator SHALL emit `connection.opened` when a TCP client connects and when a serial port is opened at startup, and `connection.closed` when a TCP client disconnects and when a serial port is closed. The event data SHALL include the connection kind (`tcp` or `serial`) and the endpoint: the client's address and the listening port for TCP, or the link path or port name for serial.

#### Scenario: TCP client lifecycle

- **WHEN** a client connects to port 9100 of device `front` and then disconnects
- **THEN** a `connection.opened` event with `device_id` `front` and kind `tcp` is emitted
- **AND** a `connection.closed` event for the same client address follows it

#### Scenario: Serial port opened at startup

- **WHEN** `emupos run` starts with device `deli` using `serial: { pty: true, link: deli }`
- **THEN** a `connection.opened` event with `device_id` `deli`, kind `serial` and the link path is emitted

### Requirement: Clean shutdown

When `emupos run` is stopped with Ctrl+C, or with SIGTERM on macOS and Linux, the simulator SHALL emit `connection.closed` for each open connection, close every TCP listener and client connection, close every serial port, remove every link it created, and exit with status 0. Every TCP port it used SHALL be free to bind again immediately after it exits.

#### Scenario: Immediate restart

- **GIVEN** `emupos run` is running with device `front` on port 9100 and a client is connected
- **WHEN** the user presses Ctrl+C and immediately runs `emupos run` again with the same configuration
- **THEN** the second run binds port 9100 without an "already in use" error

#### Scenario: Links are removed

- **GIVEN** `emupos run` has published `$TMPDIR/emupos/deli` on Linux
- **WHEN** it receives SIGTERM
- **THEN** it exits with status 0
- **AND** `$TMPDIR/emupos/deli` no longer exists
