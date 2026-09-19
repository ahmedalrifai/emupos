## Status

**Parked, not started.** The design is complete and validates; no task is implemented.

This change serves a POS that runs *inside* a container. The motivating case turned out not to
be one: that POS is an Electron app on the developer's machine, so it opens the printer's TCP
port on loopback and the scale's pty under `$TMPDIR/emupos/`, exactly as emupos already
supports, and it needs no bridge. Verified on macOS against `emupos run` 0.2.0: `isatty` true,
`tcsetattr` 9600 7E1, `W\r` answered `\x0202.455\r`, and an ESC/POS job over 127.0.0.1:9100
cut a receipt.

What would unpark it: a team whose POS process itself runs in a container and needs a serial
device. `docker/emupos.yaml` and `docs/docker.md` currently tell those users to run emupos on
the host, which costs them the container — that is the gap this change closes.

## Why

A serial device in a container is unreachable. A pseudo-terminal lives in the devpts of the mount namespace that created it, so `$TMPDIR/emupos/deli` inside the container points at a device node the host does not have — and on macOS and Windows the container is inside Docker Desktop's Linux VM, one more boundary down. No flag changes this. `docker/emupos.yaml` says so today, and tells people to run emupos on the host for serial devices. That answer costs them the container.

What does work, and was verified: a process running **where the POS can see it** creates the port and relays the bytes. A second container ran `socat PTY,link=/dev/ttyScale,raw tcp:emupos-svc:9200`, and a Python POS in that container opened `/dev/ttyScale`, got `isatty` true, ran `tcsetattr` for 9600 7E1, wrote `W\r` and read back `\x02 02.455 \r` from the emupos service — byte-identical Toledo 8217. The pty never crossed the VM boundary, so it works on all three operating systems.

Two things go wrong when that relay is `socat` rather than emupos:

- **The framing warning dies silently.** A POS set to 19200 8N1 against a 9600 7E1 scale got a clean valid weight and zero warnings. `watch_framing` is spawned only in `Connections._open_pty` (`src/emupos/daemon/connections.py:96`); `_open_tcp` never observes framing, and with socat holding the pty nothing on either side reads its termios. emupos's one diagnostic for the single most common serial misconfiguration is gone.
- **Death stops being loud.** Kill the container and the POS holds a port that is open, `isatty` true, writable, and silently never answers: writes succeed, reads return empty. Native emupos dying gives ENOENT and EIO instead. A testing tool that fails silently is worse than no tool.

This change makes emupos itself the relay, so both come back. `emupos bridge deli` runs wherever the POS is, creates the pty (or drives a com0com port on Windows), relays bytes to the device's existing TCP listener, reports the framing the POS set, and destroys the port the moment the simulator goes away.

## What Changes

- **A new command, `emupos bridge DEVICE`.** It asks the running simulator what the device is, creates a serial port on the machine it runs on, and relays every byte between that port and one `tcp` connection of the device, unchanged and in order, both ways. It runs on the developer's host, inside the POS's container, or as a process beside the POS in a compose service — the position is a property of where you run it, not of anything in `emupos.yaml`.
- **`emupos.yaml` does not change.** A bridged device is a device with a `tcp` connection, which is already valid on every operating system. No `bridge:` key, no third `SerialEndpoint` variant, no new validator, no JSON-schema change, no `configuration` spec change. A POS that speaks raw sockets can keep pointing straight at the port and skip the bridge.
- **`GET /devices/{id}` reports `serial_framing`** — the device's expected baud, data bits, parity and stop bits, or `null` for a device that has none (a keyboard scanner). The bridge needs it to set the pty's framing, and Windows needs it to open the COM port at all. Additive field; `emupos devices` shows it too.
- **`POST /devices/{id}/observed-framing`** takes the framing the bridge read off its pty and answers with the mismatches against the device's expected framing. When there are any, the simulator emits the same one `connection.framing-mismatch` event and logs the same `emupos run` warning it logs for a local pty, and the bridge prints the warning in its own terminal — which in the container case is the only terminal the developer has.
- **The port exists if and only if the connection to the simulator is up.** When the connection ends — the container stopped, `emupos run` was killed, the simulator stopped answering — the bridge closes the pty, removes the link it published and exits 1. The POS's next write fails with EIO, its next read returns nothing, and reopening the link fails with ENOENT: the same three failures as killing a native `emupos run`, because it is the same `PtyPort.close()`.
- **The bridge never reconnects.** A bridge that held its pty open across an outage would be exactly the silent healthy-looking port this change exists to kill. Restarting is a supervisor's job: a shell loop, compose `restart:`, systemd, or the developer's terminal.
- **Liveness is checked, not assumed.** The bridge polls `GET /health` on the control API and tears the port down when the simulator stops answering, so a frozen or paused peer that still ACKs at the TCP level is caught within about ten seconds rather than in fifteen minutes. `SO_KEEPALIVE` on the data socket is the kernel-level backstop for an idle connection.
- **Windows drives one end of a com0com pair.** `emupos bridge deli --port COM5`; the POS opens `COM6`. Without `--port` the command refuses with the com0com pointer, never a silent fallback.
- **`transports/framing.py` grows one extraction.** `observed_framing_changes(fd, interval)` is an async generator yielding each distinct `ObservedFraming`; `watch_framing` becomes a four-line wrapper over it with unchanged behaviour and signature.
- **Documentation:** a new `docs/serial-bridge.md` (what the bridge is, the three positions, the compose recipe, what happens when the simulator stops); `docs/windows-serial.md` gains the bridge case and the honest note that a POS able to open a TCP socket needs no com0com at all; `docs/automation.md` and `README.md` get a line each.
- Nothing is BREAKING. A configuration without a bridge behaves byte for byte as it does today, and the two API additions are new fields and a new endpoint inside `/api/v1`.

## Non-goals

- **No new connection kind in `emupos.yaml`.** No `serial: { bridge: true }`. "Bridged" is how you run emupos, not what is in the file. That keeps `configuration` untouched, keeps a bridged device's config valid on Windows without claiming something the server cannot do, and leaves the direct-TCP path open.
- **No reconnection, buffering, or backoff in the bridge.** No "is it up yet" state, no holding the port across a gap. The supervisor restarts it.
- **The simulator does not learn the bridge's link path.** `connection.opened` for a bridge is an ordinary `kind: tcp` event with the bridge's address, because that is what the simulator has. The link path is printed by the bridge and named in the framing-mismatch event; it is not added to `ConnectionInfo`.
- **No changes to the in-flight `publish-a-docker-image` change.** `docker/emupos.yaml`'s "a serial device is deliberately absent" comment becomes answerable once this lands, and `Dockerfile`'s `EXPOSE` may want the device port. Both are a one-line follow-up after that change lands, not files this change touches.
- **No second listener, no dedicated bridge port, no WebSocket byte channel.** The device's own TCP listener already carries device bytes with full binary transparency and is the path the experiment proved.
- **No authentication.** emupos stays a testing tool bound to loopback by default; a bridge on another machine needs the same non-loopback bind the control API already warns about at startup.
- **No `emupos bridge` supervisor mode** (`-- CHILD`, restart policies, PID-1 signal forwarding). One `until [ -e /tmp/emupos/ttyScale ]; do sleep 0.1; done` in the POS's own command does the same job with no code.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- **`device-connections`** — ADDED *"Bridged serial ports"*: what `emupos bridge` creates and relays, what it refuses before creating any port, and that the port is destroyed when the connection to the simulator ends, with no reconnection. MODIFIED *"Serial framing observation"*: framing is observed on the machine holding the pty — the simulator's for `pty: true`, the bridge's for a bridged port — and a bridge reports each distinct observed framing to the simulator, which emits the same one event and the same warning. The existing "Stable serial link paths", "Binary transparency", "Connection events", "Multiple connections and clients per device", "Clean shutdown" and "Startup fails when an endpoint is unavailable" requirements are **not modified**: a bridge publishes links through the same `open_pty` code and its TCP connection produces `connection.opened`/`connection.closed` like any other client.
- **`cli`** — ADDED *"Bridge command"*: the argument and options, the link path and framing it prints, that it shows each framing mismatch the simulator returns in its own output, the refusals with their fixes, and exit codes 0/1/2/3. MODIFIED *"Command set and help"*: `bridge` joins the command list.
- **`control-api`** — MODIFIED *"Device listing and description"*: the description includes the device's expected serial framing, or null when it has none. ADDED *"Observed framing reports"*: `POST /devices/{id}/observed-framing` takes an observed baud rate and optionally data bits and parity, answers with the mismatches against the expected framing, emits `connection.framing-mismatch` when there are any, and answers 409 for a device with no serial framing. The capability's Purpose sentence — "It is never part of a POS's integration code" — stays true and is not edited: device bytes ride the device's own TCP port, and only emupos's own processes use the API.

**Not modified: `configuration`.** That is the headline of this change.

## Impact

**New files**

- `src/emupos/transports/bridge.py` — the relay: the TCP connection, the local port, the two pumps, the framing watcher, the liveness poll, the teardown.
- `src/emupos/transports/test_bridge.py` — the acceptance test: the round trip, the framing observation, and the loud death.
- `src/emupos/cli/bridge.py` — the Typer command: discovery, validation, the announce block, the framing report, the error table.
- `docs/serial-bridge.md`.

**Changed files**

- `src/emupos/transports/framing.py` — extract `observed_framing_changes`; `watch_framing` becomes a wrapper. `src/emupos/transports/test_framing.py` gains the generator's tests.
- `src/emupos/daemon/connections.py` — lift `expected_framing(loaded, config)` and `report_framing(publish, device_id, endpoint, mismatches)` to module level; `_framing` and `_framing_reporter` become wrappers.
- `src/emupos/daemon/simulator.py` — `report_observed_framing(runtime, endpoint, observed)`.
- `src/emupos/api/schemas.py` — `SerialFramingOut`, `ObservedFramingReport`, `MismatchOut`, `FramingReport`; `serial_framing` on `DeviceInfo`.
- `src/emupos/api/routes/devices.py` — fill `serial_framing` in `describe()`; the `POST /devices/{device_id}/observed-framing` route (kept in this router so `api/app.py` needs no new entry).
- `src/emupos/cli/app.py` — one line registering the command.
- `src/emupos/cli/client.py` — an optional `timeout` on `Client.get`/`send`, for the liveness poll.
- `src/emupos/cli/devices.py` — show the expected framing in a device summary.
- `docs/windows-serial.md`, `docs/automation.md`, `README.md`.
- Generated: `docs/cli.md`, `docs/api/openapi-v1.json`.
- Specs: `openspec/specs/device-connections/spec.md`, `openspec/specs/cli/spec.md`, `openspec/specs/control-api/spec.md`, via `openspec/changes/bridge-serial-ports-to-the-client/specs/`.

**Dependencies:** none. `asyncio.open_connection` and `socket` are stdlib; `open_pty`, `open_serial_port`, `apply_framing`, `observe_framing`, `Client` and `CliError` are already in the tree. On Windows the bridge is a second caller of `serialx`, already justified in CONTRIBUTING.md's table as "Asynchronous access to COM ports". No `socat` in any image, no `pyserial`, no supervisor library. The dependency table is unchanged and the GPL/LGPL/AGPL licence gate has nothing new to check.

**Compatibility:** additive everywhere. `serial_framing` is a new optional response field and `/observed-framing` is a new endpoint, so `scripts/check_api_compat.py` passes and `/api/v1` stays. `watch_framing` keeps its signature and behaviour. A `feat(serial):` commit.
