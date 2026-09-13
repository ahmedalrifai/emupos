## ADDED Requirements

### Requirement: Create a print queue for a simulated printer

On Windows, `emupos setup print-queue [--device ID]` SHALL create a Standard TCP/IP printer port that sends raw data to `127.0.0.1` at the port of the printer's TCP connection, with SNMP status enabled, and a printer queue named `emupos-<device id>` that uses the built-in "Generic / Text Only" driver on that port. The command SHALL read the printer and its TCP port from the running simulator. `--device` SHALL be optional when exactly one printer is configured. On success the command SHALL print the queue name, the target address and port, and the one-way limitation defined by the one-way printing requirement, and SHALL exit with status 0. Running the command again for the same printer SHALL leave exactly one queue and one port for it, targeting the printer's current TCP port. When the printer has no TCP connection, the command SHALL exit with status 1 and a message stating that a `tcp` connection must be added to the printer in `emupos.yaml`, and SHALL create nothing. When the simulator is not running, the command SHALL exit with status 3 and SHALL create nothing.

#### Scenario: Queue created for the only printer

- **GIVEN** Windows, and a running simulator whose only printer is `front` with `tcp: { port: 9100 }`
- **WHEN** the user runs `emupos setup print-queue` from an administrator terminal
- **THEN** a printer queue `emupos-front` exists using the "Generic / Text Only" driver
- **AND** its port is a Standard TCP/IP port sending raw data to `127.0.0.1:9100` with SNMP status enabled
- **AND** the output names `emupos-front` and `127.0.0.1:9100` and states the one-way limitation, and the command exits with status 0

#### Scenario: Re-running after the TCP port changed

- **GIVEN** queue `emupos-front` was created while `front` listened on port 9100, and the simulator now runs with `front` on port 9101
- **WHEN** the user runs `emupos setup print-queue --device front`
- **THEN** exactly one queue `emupos-front` exists
- **AND** its port sends raw data to `127.0.0.1:9101`

#### Scenario: Printer without a TCP connection

- **GIVEN** a running simulator whose printer `front` has only `serial: { port: COM5 }`
- **WHEN** the user runs `emupos setup print-queue --device front`
- **THEN** the command exits with status 1 and its message states that a `tcp` connection must be added to `front` in `emupos.yaml`
- **AND** no printer queue or printer port is created

#### Scenario: Simulator not running

- **GIVEN** Windows and no running simulator
- **WHEN** the user runs `emupos setup print-queue --device front`
- **THEN** the command exits with status 3
- **AND** no printer queue or printer port is created

### Requirement: Remove a print queue

On Windows, `emupos setup print-queue --remove [--device ID]` SHALL delete the queue `emupos-<device id>` and the printer port that setup created for it, and SHALL exit with status 0. When neither exists, the command SHALL state that there is nothing to remove and SHALL exit with status 0. When `--device` is given, removal SHALL NOT require the simulator to be running.

#### Scenario: Removing an existing queue

- **GIVEN** queue `emupos-front` and its port were created by `emupos setup print-queue`
- **WHEN** the user runs `emupos setup print-queue --device front --remove` from an administrator terminal
- **THEN** neither the queue `emupos-front` nor its port exists
- **AND** the command exits with status 0

#### Scenario: Nothing to remove

- **GIVEN** no queue `emupos-front` exists
- **WHEN** the user runs `emupos setup print-queue --device front --remove`
- **THEN** the output states that there is nothing to remove
- **AND** the command exits with status 0

#### Scenario: Removing while the simulator is stopped

- **GIVEN** queue `emupos-front` exists and the simulator is not running
- **WHEN** the user runs `emupos setup print-queue --device front --remove` from an administrator terminal
- **THEN** the queue and its port are deleted and the command exits with status 0

### Requirement: Windows only

On macOS and Linux, `emupos setup print-queue` SHALL exit with status 1 and a message stating that print queues are only supported on Windows and that on this operating system the POS connects to the printer's TCP port or serial connection directly. It SHALL NOT change any system configuration.

#### Scenario: Running on macOS

- **GIVEN** macOS
- **WHEN** the user runs `emupos setup print-queue --device front`
- **THEN** the command exits with status 1
- **AND** the message states that print queues are only supported on Windows and that the POS connects to the printer's TCP port or serial connection directly

### Requirement: Administrator rights and partial setup

When Windows refuses to create or remove the printer port or queue because the user lacks the required rights, `emupos setup print-queue` SHALL exit with status 1 and a message telling the user to run the command again from a terminal opened with "Run as administrator". Setup SHALL NOT leave a partial result: when the queue cannot be created after the port was created, the command SHALL delete that port before exiting.

#### Scenario: Standard user without administrator rights

- **GIVEN** Windows, a running simulator with printer `front`, and a terminal without administrator rights where Windows refuses to create the printer port
- **WHEN** the user runs `emupos setup print-queue --device front`
- **THEN** the command exits with status 1 and the message tells the user to re-run it from a terminal opened with "Run as administrator"
- **AND** no printer queue or printer port is created

#### Scenario: Queue creation fails after the port was created

- **GIVEN** Windows accepts creation of the printer port for `front` but refuses creation of the queue `emupos-front`
- **WHEN** the user runs `emupos setup print-queue --device front`
- **THEN** the command exits with status 1 with a message describing the failure
- **AND** the printer port created for `front` no longer exists

### Requirement: Print data passes through the queue unchanged

Bytes that an application sends to the queue `emupos-<device id>` as a raw print job SHALL reach the simulated printer unchanged, over a TCP connection to the printer's TCP port. Each Windows print job SHALL be processed by the printer exactly as the same bytes sent directly to the printer's TCP port on one connection that closes at the end of the job, including receipt rendering, job boundaries and drawer kicks.

#### Scenario: Receipt printed through the queue

- **GIVEN** queue `emupos-front` targets printer `front` on `127.0.0.1:9100`
- **WHEN** an application submits `1b 40 48 69 0a 1d 56 00` to `emupos-front` as a raw print job
- **THEN** a receipt with text `Hi` is completed for `front`
- **AND** its PNG image is identical to the image produced when the same bytes are sent directly to `127.0.0.1:9100`

#### Scenario: Drawer kick through the queue

- **GIVEN** queue `emupos-front` targets printer `front`, whose drawer is closed
- **WHEN** an application submits `1b 70 00 19 fa` to `emupos-front` as a raw print job
- **THEN** the drawer of `front` opens and `drawer.opened` is emitted
- **AND** no receipt is completed

### Requirement: One-way printing limitation

Printing through a Windows print queue SHALL be documented and reported as one-way: a POS printing through the queue SHALL NOT receive any reply from the printer, including DLE EOT and GS r replies and Automatic Status Back. The success output of `emupos setup print-queue` and the output of `emupos doctor` on Windows, when a queue named `emupos-<device id>` exists, SHALL state that status replies are not delivered through a print queue and that status testing requires connecting to the printer's TCP port or serial connection directly.

#### Scenario: Status query sent through the queue

- **GIVEN** queue `emupos-front` targets printer `front`
- **WHEN** a POS submits `10 04 01` to `emupos-front` as a raw print job
- **THEN** the POS receives no status reply through the queue
- **AND** no receipt is completed

#### Scenario: Doctor reports the limitation

- **GIVEN** Windows and an existing queue `emupos-front`
- **WHEN** the user runs `emupos doctor`
- **THEN** the output states that `emupos-front` cannot deliver status replies and that status testing requires the printer's TCP port or serial connection

### Requirement: SNMP status responder

On Windows, while `emupos run` is running with at least one printer that has a TCP connection, the simulator SHALL answer SNMP v1 and v2c GET and GETNEXT requests on UDP port 161, bound to `127.0.0.1` only, for the printer status objects that the Windows Standard TCP/IP port monitor queries, with values computed from printer state at the time of each request. Each answered request SHALL emit an `snmp.query.answered` event for the printer whose status was reported, whose data contains the request type (`get` or `getnext`) and the requested object identifiers. SET requests SHALL NOT change any state. Malformed packets and requests in other SNMP versions SHALL be ignored without a reply, and the responder SHALL keep answering later valid requests. On macOS and Linux the simulator SHALL NOT open UDP port 161.

#### Scenario: Responder answers on Windows

- **GIVEN** Windows and a configuration with printer `front` on `tcp: { port: 9100 }`
- **WHEN** the user runs `emupos run` and an SNMP v2c GET for a printer status object is sent to `127.0.0.1:161`
- **THEN** a response is returned
- **AND** an `snmp.query.answered` event is emitted

#### Scenario: Responder only listens on loopback

- **GIVEN** the simulator is running on Windows with printer `front`
- **WHEN** an SNMP v2c GET is sent to the machine's LAN address on UDP port 161
- **THEN** the simulator sends no response

#### Scenario: Invalid requests change nothing

- **GIVEN** the simulator is running on Windows with printer `front`
- **WHEN** a malformed UDP packet and an SNMP SET request are sent to `127.0.0.1:161`, followed by a valid SNMP v2c GET
- **THEN** printer `front` has the same faults as before
- **AND** the valid GET receives a response

#### Scenario: No responder on macOS or Linux

- **GIVEN** macOS or Linux and a configuration with printer `front` on `tcp: { port: 9100 }`
- **WHEN** the user runs `emupos run`
- **THEN** the simulator does not open UDP port 161

### Requirement: Queue status reflects printer state

The status that the SNMP responder reports for a printer SHALL make its Windows queue show the printer as ready when no fault is active. While `paper-out`, `cover-open` or `offline` is active, the reported status SHALL put the queue in an error state and SHALL identify the condition as no paper, door open or offline respectively. `paper-near-end` SHALL be reported as a low-paper warning and SHALL NOT put the queue in an error state. A fault change SHALL be reflected in the next response. When several printers have queues, the SNMP settings that `emupos setup print-queue` configures on each queue's port SHALL identify its printer, and the status reported for one printer's queue SHALL NOT depend on the faults of another printer.

#### Scenario: Ready with no faults

- **GIVEN** queue `emupos-front` targets printer `front`, which has no active faults
- **WHEN** Windows polls the printer status
- **THEN** Windows shows `emupos-front` as ready, not offline and not in error

#### Scenario: Blocking faults are reported distinctly

- **GIVEN** queue `emupos-front` targets printer `front`
- **WHEN** `paper-out`, `cover-open` and `offline` are each activated on their own and then cleared
- **THEN** while each fault is active, the SNMP status for `front` reports an error state identifying no paper, door open or offline respectively
- **AND** after each fault is cleared, the SNMP status for `front` reports ready again

#### Scenario: Paper near end is not an error

- **GIVEN** queue `emupos-front` targets printer `front`
- **WHEN** only the `paper-near-end` fault is activated
- **THEN** the SNMP status for `front` reports low paper
- **AND** Windows does not show `emupos-front` in an error state

#### Scenario: Each queue reports its own printer

- **GIVEN** queues `emupos-front` and `emupos-back` were created for printers `front` on port 9100 and `back` on port 9101
- **WHEN** the `paper-out` fault is activated on `front` only
- **THEN** the SNMP status for `emupos-front` reports no paper
- **AND** the SNMP status for `emupos-back` reports ready

### Requirement: SNMP port conflict

When UDP port 161 on `127.0.0.1` is already in use as `emupos run` starts on Windows, the simulator SHALL keep running all devices and SHALL print an error stating that UDP port 161 is in use, that the Windows "SNMP Service" is the usual cause and how to stop it, and that print queues will not receive printer status until the port is free. `emupos doctor` on Windows SHALL report the same conflict, naming the same fix, as a failed check when a queue named `emupos-<device id>` exists and as a warning otherwise.

#### Scenario: Port 161 taken at startup

- **GIVEN** Windows with the "SNMP Service" running and bound to UDP port 161, and a configuration with printer `front` on `tcp: { port: 9100 }`
- **WHEN** the user runs `emupos run`
- **THEN** the output contains an error naming UDP port 161 and the Windows "SNMP Service", with instructions to stop it
- **AND** printer `front` still accepts connections on TCP port 9100

#### Scenario: Doctor reports the conflict

- **GIVEN** Windows with UDP port 161 in use by another program and an existing queue `emupos-front`
- **WHEN** the user runs `emupos doctor`
- **THEN** the output contains a failed check for UDP port 161 that names the Windows "SNMP Service" and how to stop it
- **AND** the command exits with status 1

#### Scenario: Conflict without a queue is a warning

- **GIVEN** Windows with UDP port 161 in use by another program and no queue named `emupos-<device id>`
- **WHEN** the user runs `emupos doctor`
- **THEN** the UDP port 161 check is a warning that names the Windows "SNMP Service"
- **AND** the command exits with status 0 when no other check failed
