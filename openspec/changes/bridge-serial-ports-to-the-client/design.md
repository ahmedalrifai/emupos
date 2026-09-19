## Context

The simulator opens four kinds of thing today, all in `src/emupos/daemon/connections.py`:

```
Connections.open ──▶ _open_tcp          (connections.py:72)  serve_tcp → _pump per client
                 ──▶ _open_pty          (connections.py:87)  open_pty → _pump + watch_framing
                 ──▶ _open_serial_port  (connections.py:98)  open_serial_port → _pump
```

Facts that shape this design, each verified in the tree or by running it:

- **`_pump` (`connections.py:108`) is the one place a connection lives.** It registers the writer in `runtime.writers`, publishes `connection.opened`, calls `device.open_connection`, loops on `reader.read(65536)`, and in its `finally` pops the writer, calls `device.close_connection` and publishes `connection.closed`. A TCP client of the device gets all of that for free.
- **Framing observation is spawned only for a pty** (`connections.py:96`). `watch_framing` (`transports/framing.py:94`) polls `observe_framing` on `PtyPort.slave_fd` every 0.2 s and calls back once per *distinct* observed framing. That "once per distinct framing" behaviour is what satisfies the spec's "once per distinct observed framing, not per read" with no state anywhere else.
- **`watch_framing`'s callback receives `tuple[Mismatch, ...]`, never the raw observation.** The comparison happens inside the loop, at `framing.py:107`. Anything that wants the raw `ObservedFraming` needs the loop split.
- **`open_pty` (`transports/pty.py:54`) already does everything a bridge needs**: `tty.setraw`, `apply_framing` at the expected framing so a correctly-set POS reports no mismatch, the held-open slave fd, the `$TMPDIR/emupos/<link>` symlink, the pid file, the stale-link replacement and the "in use by another emupos (pid N)" refusal.
- **`_publish_link` (`pty.py:145`) hardens its directory.** It `mkdir`s with mode 0700, refuses a directory it does not own, and **`chmod(0o700)`s one whose group/other bits are set**. Handing it a user-chosen directory such as `/dev` would lock that directory to the owner and drop a `.pid` file in it. Nothing in this change ever passes it a path the user chose.
- **`PtyPort.close()` (`pty.py:42`) is the teardown.** Measured on macOS by opening the published link as a POS would and then calling it: `read()` → `b''`, `write()` → `OSError EIO`, the symlink is gone, and reopening it → `ENOENT`. (Every one of the four candidate designs and the brief itself said "read fails with EIO". It does not; the *write* fails and the *reopen* fails. The spec scenario is worded from the measurement.)
- **`asyncio.StreamWriter` sets `TCP_NODELAY`** on a selector socket transport, so a two-byte `W\r` crosses a loopback or compose-bridge hop in well under a millisecond and the Toledo 8217's 100 ms reply budget is not at risk.
- **`ConnectionInfo.kind` is `Literal["tcp", "serial"]`** (`api/schemas.py:53`), and `scripts/check_api_compat.py` compares property shapes, so widening that enum would fail CI. New optional fields would not.
- **`Endpoint` (`daemon/runtime.py:21`) is `frozen=True, slots=True`** and `describe()` builds `ConnectionInfo(**asdict(endpoint))` (`api/routes/devices.py:35`). Adding fields to it would churn `emupos run`'s startup table, `emupos devices` and the API at once.
- **`runtime.writers` is `dict[ConnectionId, asyncio.StreamWriter]`** and `daemon/scans.py:28-30` does `writer.write(...)` then `await writer.drain()` for every writer when a serial scanner delivers a scan. Anything that is not a `StreamWriter` in that dict must have all three of `write`, `is_closing` and `drain`.
- **Ruff bans `asyncio`, `socket`, `termios`, `serial` and `serialx` outside `transports/`, `api/` and `daemon/`** (`pyproject.toml:83-95`). The CLI may not import asyncio; `type_keys_now()` lives in `transports/keyboard/keyboard.py` for exactly this reason.
- **The architectural precedent is `typed_by: client`** (`openspec/changes/type-scans-on-the-client/`, shipped in `scanner/scanner.py`, `daemon/simulator.py`, `api/routes/scanners.py`, `cli/actions.py`): the server keeps validation, state and events; the client performs the OS-touching part and reports back; a deadline stops an absent client wedging the device.
- **Every shipped profile defines `serial:`** — all three printers and the scale — so "this device could be bridged" cannot be inferred from the profile.
- **`docs/windows-serial.md` records that com0com 3.0.0.0 installs as Code 52 under Secure Boot on current Windows 11**, with no COM ports appearing. This is the repo's own finding and it constrains what any Windows story may promise.

## Goals / Non-Goals

**Goals:**

- A POS opens a real serial port, on the machine where the POS is, backed by a device whose protocol and state live in the simulator.
- The `connection.framing-mismatch` warning survives the boundary: it is emupos's one diagnostic for the most common serial misconfiguration.
- When the simulator goes away the POS finds out loudly, with the same ENOENT and EIO a killed native `emupos run` produces.
- `emupos.yaml` is unchanged, so nothing new has to be learned to use a bridge and nothing is invalidated by not using one.

**Non-Goals:**

- A new connection kind, reconnection, buffering, authentication, or a supervisor built into the command.
- Teaching the simulator where a bridge published its link.

## Decisions

### D1. A bridged device is a `tcp` connection, not a new kind of connection

`emupos.yaml` is untouched. A device that will be bridged is a device with `tcp: { host: 0.0.0.0, port: 9200 }`, which is valid today on all three operating systems:

```yaml
devices:
  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections:
      - tcp: { host: 0.0.0.0, port: 9200 }   # `emupos bridge deli` makes the serial port where the POS is
```

The TCP listener already carries device bytes with full binary transparency, already accepts several clients, already publishes `connection.opened`/`connection.closed`, and is exactly the path the socat experiment proved. Everything a bridge needs beyond that comes from `GET /devices/{id}`.

This is the real-world architecture, not a workaround: a serial device server (a Moxa NPort and its RealCOM driver, a Digi PortServer) puts the device on a TCP socket and has a driver create the COM port on the PC. The server side genuinely is a socket. emupos reporting `kind: tcp` is honest, not a leak.

**Rejected: `serial: { bridge: true }`** (three of the four candidate designs). It costs a `config.py` variant, a rewritten `_one_kind`, a new `_semantic_issues` branch, a JSON-schema regeneration, `test_config.py` churn, a `docs/configuration.md` edit and a MODIFIED "Connection entries" requirement in the `configuration` spec — and buys nothing the bridge cannot read from the device description. It also has two costs that are not just size:

- It makes `bridge: true` validate on Windows where `pty: true` is refused. That is sold as a feature, but it converts today's honest load-time refusal into a configuration the simulator accepts and can never serve: `emupos run` starts, the row says "waiting for a bridge" forever, and nothing says why.
- It removes the direct-TCP fallback. With a plain `tcp:` listener, a POS that can open a socket points at 9200 and skips the bridge entirely. On Windows, where this repo's own docs record com0com as Code 52 under Secure Boot, that fallback is the only native path that works.

**Rejected: a `bridge:` marker anywhere in the config**, including a hint line in `emupos run`'s startup table. Every shipped profile defines `serial:`, so a "you could bridge this" hint would fire for the network printer too. The honest discoverability signal is `serial_framing` in the device description and `emupos devices`: it says this device speaks serial. `docs/serial-bridge.md` and `emupos bridge --help` carry the rest. If users get lost anyway, the cheap fix later is four lines in `cli/run.py` — still no schema change, still no new concept.

### D2. The wire protocol is the device's own bytes on the device's own TCP listener

No envelope, no handshake, no new endpoint, no length prefix, no message framing. The device protocol *is* the framing (`W\r` in, `\x0202.455\r` out). The bridge does `asyncio.open_connection(host, port)` and copies `reader.read(65536)` ↔ `writer.write(); await writer.drain()` in both directions. Any envelope would break the "Binary transparency" requirement and force a second parser on both ends.

**Which address.** The host comes from the `--api` URL (`urllib.parse.urlsplit(base_url).hostname`), which is right in all three positions: `emupos` in the compose sidecar, `127.0.0.1` on a host, `127.0.0.1` inside a POS container that publishes the port. The port comes from the device's `tcp` connection in `GET /devices/{id}` — `endpoint.rsplit(":", 1)[1]`, so `[::]:9200` parses; the bind address in that string is ignored. A host taken from `--tcp` is `.strip("[]")`ed, as `_is_loopback` already does in `cli/app.py` and `cli/run.py`, so `--tcp [::1]:9200` resolves. `--tcp` overrides either half when the publish remapped the port (`--tcp 19200`) or the simulator is somewhere else entirely (`--tcp scales.local:9200`).

**Rejected: a WebSocket on the control API carrying binary frames** (the shape three candidate designs chose). It is a real design and its arguments are real — one published port, ping/pong liveness, text frames for control beside binary frames for data. It was rejected because the price is paid in the server's hot path for all four connection kinds: `runtime.writers` must widen from `asyncio.StreamWriter` to a Protocol under pyright strict; `Endpoint` (frozen, slots) must grow fields that `emupos run`, `emupos devices` and the API all read; `Simulator` needs a new public hook because `_connections` is private and the API reaches it only through `SimulatorDep`/`RuntimeDep`; and a new route, a new message schema and a new refusal shape appear, because a WebSocket route cannot use `ApiError` — `install_error_handlers` covers HTTP, and raising before `accept()` yields a bodyless close. The three things that buys — one port instead of two, ping liveness, and a channel for the framing report — are bought here for a `GET`, a `POST`, a poll task and three lines of `setsockopt`.

**Rejected: a dedicated raw-TCP bridge listener** (a port per bridged device, configured). It needs a config field, a second listener, a second published port and a second bind-address warning, and it is strictly worse than the device's own listener, which already exists.

**Latency.** Both ends are asyncio stream transports with `TCP_NODELAY`, so there is no Nagle/delayed-ACK stall. Over loopback or a compose bridge network the added round trip is well under a millisecond, inside the Toledo 8217's 100 ms. `transports/test_bridge.py` asserts the bound rather than claiming it.

### D3. The bridge learns the expected framing from `GET /devices/{id}`

`DeviceInfo` gains one additive field:

```python
class SerialFramingOut(BaseModel):
    baud: int
    data_bits: int
    parity: Literal["none", "even", "odd"]
    stop_bits: int

class DeviceInfo(BaseModel):
    ...
    serial_framing: SerialFramingOut | None = None
```

filled in `routes/devices.py:describe()` from a function lifted out of `Connections._framing` to module level in `daemon/connections.py`:

```python
def expected_framing(loaded: LoadedConfig, config: DeviceConfig) -> SerialFraming | None:
    if isinstance(config, ScannerDevice):
        return SCANNER_FRAMING if config.mode == "serial" else None
    return loaded.profiles[config.id].serial
```

`Connections._framing` becomes a two-line wrapper that keeps its `EndpointUnavailableError` raise for the null case. Lifting it rather than duplicating it is what keeps the one trap right in both places: a **serial-mode scanner has no profile** and its framing is the hardcoded `SCANNER_FRAMING` at `connections.py:26` (9600 8N1); a **keyboard scanner** has no serial framing at all and reports `null`.

The bridge needs this for two things: `open_pty(link, framing)` runs `apply_framing(slave_fd, framing)`, so the pty starts at 9600 7E1 and a mismatch is reported only when the POS sets something else, exactly as a native pty does; and on Windows `open_serial_port(port, framing)` cannot open COM5 without it.

**Rejected: the CLI computing the framing from the profile itself.** It would need the config file, which is in the container, not where the bridge runs.

### D4. The bridge observes; the server judges, publishes and warns

The same split as `typed_by: client`, in the direction it actually runs: the OS-touching read (`tcgetattr`) belongs to the machine holding the terminal, the comparison belongs with the profile that defines the expectation.

**The watcher splits into an async generator.** `transports/framing.py`:

```python
async def observed_framing_changes(fd: int, interval: float = 0.2) -> AsyncIterator[ObservedFraming]:
    """Yield the framing on `fd` each time it changes. Cancel this before closing `fd`."""
    last: ObservedFraming | None = None
    while True:
        if (observed := observe_framing(fd)) != last:
            last = observed
            yield observed
        await asyncio.sleep(interval)


async def watch_framing(fd, expected, on_mismatch, interval=0.2) -> None:
    async for observed in observed_framing_changes(fd, interval):
        if mismatches := framing_mismatches(expected, observed):
            on_mismatch(mismatches)
```

Behaviour-identical: the `if observed != last` dedup that gives the spec's "once per distinct observed framing, not per read" moves into the generator, and `watch_framing` keeps its signature so `_open_pty` is untouched. A generator rather than a second callback is what removes a bug the callback shape invites: the bridge's report is a *blocking* HTTP POST, and `asyncio.to_thread(post, observed)` from a synchronous callback returns an un-awaited coroutine that never runs — written literally, the 10-second urllib call executes on the event loop and stalls the byte pump. With a generator the bridge writes `await asyncio.to_thread(report, observed)` inside its own `async for`, on its own task, off the data path, where a slow POST only delays the next poll.

**The report.** `POST /api/v1/devices/{device_id}/observed-framing`:

```
{"endpoint": "/tmp/emupos/ttyScale", "baud": 19200, "data_bits": 8, "parity": "none"}
→ 200 {"mismatches": [{"setting": "baud", "expected": 9600, "observed": 19200},
                      {"setting": "data_bits", "expected": 7, "observed": 8},
                      {"setting": "parity", "expected": "even", "observed": "none"}]}
```

`data_bits` and `parity` are nullable, because a Linux pty exposes neither — the bridge sends the `ObservedFraming` it got, nulls included, and `framing_mismatches` already skips `None` (`framing.py:45`). The macOS/Linux asymmetry the spec documents is preserved with no platform branch on the server, and a Linux bridge against a macOS simulator, or the reverse, is correct without either knowing the other's OS.

The route calls `Simulator.report_observed_framing(runtime, endpoint, observed) -> tuple[Mismatch, ...]`, which looks up `expected_framing` and calls the pure `framing_mismatches`; a non-empty result goes through a second module-level function lifted out of `Connections._framing_reporter`:

```python
def report_framing(publish, device_id: str, endpoint: str, mismatches: tuple[Mismatch, ...]) -> None:
```

Both `_open_pty` and the new route go through that one body, so the event payload and the `emupos run` warning line are identical whether the pty is the simulator's or a bridge's. A device with no serial framing answers 409 `no_serial_framing`.

**The `endpoint` in the event is the path the POS actually opened** — the alias when `--alias` was given, the published link otherwise — which is the path the person needs to see, and it deliberately differs from the `connection.opened` event's `0.0.0.0:9200`. Those are two true statements at two granularities: a TCP client connected to the device, and a POS at `/tmp/emupos/ttyScale` set its port to 19200. The bridge also prints the mismatch in its own terminal, from the 200 body — which in a container is the only terminal the developer has, and is the piece that was dead behind socat.

**Rejected: the bridge computing the mismatch and posting the verdict.** It inverts the `typed_by: client` split, lets a drifted bridge decide what counts as a mismatch against its own copy of the rules, and puts client-supplied strings straight into an event.

**Rejected: no report at all, with the bridge printing the mismatch locally.** The spec requires a `connection.framing-mismatch` event and a warning in the `emupos run` output; a test watching `/api/v1/events` expects it.

### D5. There is no ownership rule and no deadline, because a connection cannot be wedged

`typed_by: client` needs `expires_at` because a scanner has exclusive one-scan-at-a-time state that an absent client leaves stuck. A connection has no such state: `runtime.writers` is a dict of N clients and `_pump`'s `finally` pops the entry on every exit path, so a device with no bridge attached is just a device with one fewer client. Nothing is held, nothing is refused, nothing expires.

Adding a lease here would *create* the wedge it is meant to prevent: a bridge killed without a clean close would lock out its own replacement for the grace period — which is the crash-and-restart case people actually hit. So there is no server-side registry, no `_BridgeSlot`, no `expires_at`, no watchdog task and no new event type.

The one genuinely exclusive resource is the link path on the bridge's own machine, and `_publish_link`'s pid file already arbitrates it, including the stale and recycled-pid cases (`pty.py:130-166`): a second bridge with the same link name is refused with "serial link /tmp/emupos/ttyScale is in use by another emupos (pid 412); stop it or choose another `link` name". On Windows `open_serial_port`'s exclusive open gives "serial port `COM5` is in use by another program". Both messages already exist and are already the right words.

Two bridges for one device on **different** link names or different machines both work, and both are correct: "Multiple connections and clients per device" already guarantees one device state and replies going only to the connection whose bytes caused them.

### D6. The port lives exactly as long as the connection to the simulator; the bridge never reconnects

This is the whole robustness story in one invariant, and it makes the silent-healthy-port state unrepresentable rather than merely detectable.

**Ordering.** The TCP connection is opened **first**; only then is the local port created. A refused connect therefore never leaves a port behind, matching "Startup fails when an endpoint is unavailable". On any exit the framing watcher is cancelled **before** `port.close()` — the same ordering `Connections.close` enforces at `connections.py:61` — because `observe_framing` on a closed fd raises.

**What the POS sees, measured rather than assumed.** After `PtyPort.close()`, with the POS holding the fd it opened through the link:

| | POSIX (measured on macOS; Linux behaves the same way) |
|---|---|
| held fd, `write()` | fails, `OSError EIO` |
| held fd, `read()` | returns `b''` |
| reopen the link | fails, `ENOENT` (the symlink is gone) |
| pyserial | raises `SerialException` on the write, and on the read through its select-then-empty-read disconnect check |

The write and the reopen are the loud signals; the empty read is not, on its own. A POS with a hand-rolled read loop and no write sees silence until it next writes or reopens. The spec scenario is worded from that measurement, not from the "read fails with EIO" that every earlier draft of this design asserted.

| Failure | What happens |
|---|---|
| simulator stopped, container removed, `compose down` | socket reader hits EOF; watcher cancelled, `local.close()`, exit 1 with "lost the connection to device `deli` at emupos:9200" / fix "`emupos run` stopped or the container restarted; start it again and the bridge will follow" |
| **simulator frozen, paused, or partitioned** (no FIN, kernel still ACKs) | the liveness poll (D7) fails twice and tears the port down the same way |
| Ctrl+C | relay tasks cancelled, `finally` closes the port and removes the link, exit 0 |
| SIGTERM | `loop.add_signal_handler(signal.SIGTERM, stopping.set)` on non-Windows, mirroring `daemon/server.py`; same clean path, exit 0 |
| SIGKILL of the bridge | the kernel closes master and slave, so the POS still gets EIO; a stale symlink remains and `_publish_link`'s `_live_owner` check replaces it on the next start ("Stale link is replaced") |
| bridge stops for any reason | the simulator's `_pump` `finally` drops the writer, calls `device.close_connection` and publishes `connection.closed`; a printer's part-finished job closes exactly as a vanished TCP client's does |
| start before the simulator listens | `ConnectionRefusedError` → exit 3 (API) or 1 (device port) before any port is created; the supervisor retries |
| unknown device / no tcp connection / no serial framing / several tcp connections | refused after the `GET`, before `open_pty` (see D8) |
| POS stops reading | `close_fd_streams` already aborts rather than closes, so replies never sit pending forever |

**No reconnection, deliberately.** A bridge that reconnected would have to hold the pty open across the gap, which is precisely the verified failure dressed as resilience. Exit 1 is the signal to a supervisor, and every position already has one: a shell loop in the POS container, compose `restart:`, systemd, or the developer's terminal. This deletes a whole subsystem — backoff, buffering-while-down, "is it up yet" state — and it is the one place this design is deliberately less clever than it could be.

**The compose recipe, with the start-order race closed by the shell, not by code:**

```yaml
services:
  emupos:
    image: ghcr.io/ahmedalrifai/emupos:0.2
    ports: ["127.0.0.1:8765:8765"]        # only for `emupos scan` / `emupos fault` from the host
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health')"]

  pos:
    build: .                               # its image adds one line: RUN pip install emupos
    depends_on: { emupos: { condition: service_healthy } }
    environment: { EMUPOS_API: "http://emupos:8765" }
    command: >
      sh -c 'while :; do emupos bridge deli --link ttyScale; sleep 1; done &
             until [ -e /tmp/emupos/ttyScale ]; do sleep 0.1; done;
             exec ./run-pos --scale /tmp/emupos/ttyScale --printer emupos:9100'
```

Three lines, three jobs: the `while` loop is the supervisor, the `until` closes the race where the POS opens the port before the bridge has made it, and the healthcheck removes the first-start refusal churn. **The bridge is a process in the POS's service, not a sibling container** — a pty in its own container is as invisible to the POS container as one on the host, which is the verified fact one level down. No `network_mode: service:`, no shared `/tmp` volume, no `/dev/pts` bind mount makes that work; a shared `/tmp` is worse than nothing, because the symlink resolves against the *POS* container's devpts and may land on an unrelated tty.

### D7. Liveness: a `/health` poll on the control channel, with `SO_KEEPALIVE` as the kernel backstop

TCP EOF covers the common case (the process died, the container was removed) and nothing else. A peer that freezes while its kernel keeps ACKing — `docker pause`, a suspended VM, SIGSTOP, a partition — sends no FIN and no RST, and the bridge's two-byte writes keep succeeding. That is the silent healthy-looking port, and it is the one thing the brief says must be designed in.

**`SO_KEEPALIVE` alone is not enough**, and it is worth being precise about why: keepalive probes fire only on an *idle* connection. A POS polling `W\r` at 10 Hz against a frozen peer keeps the connection non-idle forever, and the probes never fire.

So the primary mechanism is application-level, on the channel the bridge already has: one task polling `GET /api/v1/health` every 2 s with a 3 s timeout, tearing the port down after **two consecutive** failures — a dead simulator is noticed within about eight seconds, and a single blip on a loaded machine does not kill a working bridge. It works against a frozen peer because the HTTP response times out even when the kernel ACKs, and against a vanished machine because the connect times out. It costs `asyncio.to_thread(client.get, "/health", timeout=3)` in a loop, and the only change it needs elsewhere is an optional `timeout` keyword on `Client.get`/`Client.send` beside the existing `TIMEOUT_SECONDS = 10`.

`SO_KEEPALIVE` stays on the data socket as the cheap kernel backstop for the case the poll cannot see: the control API is fine but *this* socket is wedged, for instance a dropped NAT/conntrack entry on the compose network. Three lines in `transports/bridge.py`, portable by `getattr`:

```python
sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
idle = getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)
for option, value in ((idle, 5), (getattr(socket, "TCP_KEEPINTVL", None), 2),
                      (getattr(socket, "TCP_KEEPCNT", None), 3)):
    if option is not None:
        sock.setsockopt(socket.IPPROTO_TCP, option, value)
```

Confirmed on this machine: darwin exposes `TCP_KEEPALIVE` (16) as the idle option and no `TCP_KEEPIDLE`, plus `TCP_KEEPINTVL` and `TCP_KEEPCNT`; Linux and Python 3.13 on Windows expose `TCP_KEEPIDLE`. `socket` is importable in `transports/` by the per-file ignore at `pyproject.toml:93`.

### D8. `emupos bridge DEVICE`, and what it refuses before it creates anything

```
emupos bridge DEVICE [--link NAME] [--alias PATH] [--port NAME] [--tcp PORT|HOST:PORT]
```

- `DEVICE` — required. No `pick_device` default: any device with a TCP connection can be bridged, so "the only one" is not well defined.
- `--link NAME` — the link to publish under the emupos link directory (`$TMPDIR/emupos`, or `/tmp/emupos`). Default: the device id. Validated against the config's own `LinkName` pattern with a `TypeAdapter(LinkName)`, so `--link ../../root/x` is a usage error rather than a path escape.
- `--alias PATH` — an **extra plain symlink** at a path of your choosing, for a POS that insists on `/dev/ttyScale`. Repeatable is not needed; one is enough.
- `--port NAME` — open this existing serial port instead of creating one: `COM5` on Windows, `/dev/ttyUSB0` elsewhere. Required on Windows. Rejected together with `--link` or `--alias`.
- `--tcp PORT|HOST:PORT` — override the device endpoint to relay. Needed when the device has more than one TCP connection, when a publish remapped the port, or when the simulator is not at the `--api` host.
- Global `--api` / `EMUPOS_API`, as every other command.

```
$ emupos bridge deli --link ttyScale
emupos bridge 0.2.0 · deli on emupos:9200
serial port  /tmp/emupos/ttyScale -> /dev/pts/4
framing      9600 baud, 7 data bits, even parity, 1 stop bit (toledo8217-15kg)
Relaying bytes. Press Ctrl+C to stop.
```

The POS is configured with `/tmp/emupos/ttyScale`, exactly as it is configured with `$TMPDIR/emupos/deli` for a native run: the "Stable serial link paths" rule, unchanged, satisfied by the bridge instead of the simulator because it is the same `open_pty`.

**`--alias` never lets a user-chosen directory reach `_publish_link`.** The link is always published under the hardened default directory; the alias is a plain `os.symlink(device_path, alias)`, with three rules: a **dangling** symlink at that path is replaced; a symlink that still resolves is refused with "`/dev/ttyScale` already points at `/dev/pts/3`; remove it or choose another alias", so a second bridge cannot steal a working alias from the first; anything that is not a symlink is refused, so a real device node is never unlinked; on close it is removed only when `os.readlink(alias) == device_path`, the same ownership check `PtyPort.close` already makes. That is `_publish_link`'s own rule (`pty.py:162`) applied to the alias, and it still recovers after a SIGKILL, because the killed bridge's pty is gone and its alias therefore dangles. No pid file beside it. There is no `--link-dir` option at all — `_publish_link` would `chmod 0700` whatever directory it is given, and `--link-dir /dev` would lock `/dev` to the owner and break every other process in the container.

| Situation | Message | Exit |
|---|---|---|
| control API unreachable | the existing `SimulatorUnreachableError`, which already names the URL and suggests `emupos run` | 3 |
| unknown device | the API's own 404 `device_not_found` | 1 |
| no `tcp` connection | ``device `deli` has no tcp connection to relay`` · fix ``add `tcp: { host: 0.0.0.0, port: 9200 }` to it in emupos.yaml and restart `emupos run` `` | 1 |
| several `tcp` connections | ``device `deli` has tcp connections on 9200 and 9201`` · fix `choose one with --tcp 9200` | 1 |
| no serial framing | ``device `lane1` has no serial framing`` · fix `bridge a device whose profile defines serial framing, or a scanner in serial mode` | 1 |
| device port unreachable | ``cannot reach device `deli` at emupos:9200`` · fix `check that the simulator publishes that port; a connection that binds 127.0.0.1 is not reachable from another container, so set host: 0.0.0.0 for it` | 1 |
| Windows without `--port` | `emupos cannot create serial ports on Windows` · fix ``run `emupos bridge deli --port COM5` with one end of a com0com virtual port pair, and point your POS at the other end (docs/windows-serial.md)`` | 2 |
| `--link` or `--alias` with `--port` | ``--port opens an existing port, so --link and --alias do not apply`` | 2 |
| bad `--link` name | the `LinkName` pattern message | 2 |
| link in use | `_publish_link`'s existing "in use by another emupos (pid N)" | 1 |

Exit **3 is reserved for `SimulatorUnreachableError`**, which is what the cli spec requires ("the message SHALL name the API URL that was tried and suggest starting the simulator with `emupos run`"). An unreachable *device port* is an operation that failed, which is exit 1 — a distinction one candidate design got wrong.

### D9. Windows: `--port COM5`, and one honest sentence about what actually works

There is no pty, so the bridge does on Windows exactly what the simulator does there today, with the same code: `open_serial_port("COM5", framing)` through `serialx`, with the framing from `GET /devices/deli`, the same exclusive open and the same existing error messages for a missing port and a port in use, both already pointing at `emupos doctor`. The POS opens `COM6`. Byte pumping, liveness, teardown and exit codes are identical to the POSIX path. Framing is not observed (`observe_framing` raises `NotImplementedError` on Windows and the spec already says so), so the bridge posts nothing, no mismatch event fires, and `docs/windows-serial.md`'s "set the POS to the profile's settings yourself" stays true and now covers the bridged case. SIGTERM handling is skipped there exactly as `daemon/server.py` skips it; Ctrl+C is the clean path. The `~15 ms` gap-wait `serialx` costs is documented and stays well inside the Toledo 100 ms.

Two things are stated plainly rather than glossed:

- **Closing COM5 does not make COM6 vanish.** On POSIX the port disappears and the POS fails loudly; on Windows COM6 stays present and quiet, which is the silent failure. emupos cannot close a port it does not own. com0com's `ExclusiveMode=yes` (`setupc.exe change CNCA0 ExclusiveMode=yes`) is documented to hide the partner port whenever its pair end is closed, which would reproduce the POSIX behaviour. **This is unverified from a Mac.** The implementation task verifies it on Windows before the documentation promises it; if it does not behave as described, the doc says so, and the signals are the bridge's own terminal and the simulator's `connection.closed` event.
- **com0com is Code 52 under Secure Boot on current Windows 11**, per this repo's own `docs/windows-serial.md`. So the two Windows paths that actually work are named in the docs: the POS in a Linux container on Docker Desktop with the bridge beside it — the motivating case, and unaffected — and a POS that opens the TCP socket directly, which needs no bridge, no com0com and no configuration change, because the device already *is* a TCP listener (D1).

### D10. Where the code lives, given the banned imports

- **`src/emupos/transports/bridge.py`** — the only new module that touches the OS. It may import `asyncio` and `socket` (per-file ignore, `pyproject.toml:93`). It exports `relay(host, port, framing, *, link, alias, serial_port, on_open, on_observed, alive)` as a sync wrapper over `asyncio.run(_relay(...))`, plus `BridgeLost`. `_relay` also takes `link_dir: Path | None = None`, a test-only keyword the CLI never passes, exactly as `Connections` takes one today. `_relay` opens the TCP connection, sets keepalive, creates the local port, runs two pumps plus the framing watcher plus the liveness poll under `asyncio.wait(..., return_when=FIRST_COMPLETED)`, cancels the watcher before closing the port, and raises `BridgeLost` when the cause was EOF or a failed liveness check.
- **`src/emupos/cli/bridge.py`** — the Typer command. It imports no asyncio; it does the blocking `GET /devices/{id}` through the existing `Client`, validates the options, prints the announce block, and calls `emupos.transports.bridge.relay` imported lazily inside the command body, the way `cli/run.py` imports `daemon.server` and for the same reason `type_keys_now()` lives in `transports/keyboard/keyboard.py`. The callbacks it passes are closures over `Client`: `on_observed(observed) -> list[Mismatch]` posts the report and returns the mismatches to print; `alive() -> bool` does the `/health` poll.

`transports/bridge.py` imports nothing from `cli/` — the layering runs one way. The blocking HTTP calls reach it as callbacks and are invoked with `asyncio.to_thread`, on tasks that are not the data path.

## Risks / Trade-offs

- **A frozen peer is noticed in ~8 s, not instantly.** → Two consecutive `/health` failures at a 2 s interval with a 3 s timeout. Tighter would kill working bridges on a loaded CI machine; looser would leave a dead port looking alive. Both numbers are constants in `transports/bridge.py` and are the knob if it ever proves wrong.
- **Keepalive covers only the idle case.** → Stated in D7 rather than papered over: the `/health` poll is the mechanism, keepalive is a three-line backstop for a wedged data socket while the API is fine. Neither is claimed to do the other's job.
- **Nothing in `emupos run`'s output says a TCP port is meant to be bridged.** → The price of deleting the config concept, and the risk to revisit first. `serial_framing` in the device description and in `emupos devices` says the device speaks serial; `docs/serial-bridge.md` and `--help` say the rest. A hint in `cli/run.py` would misfire, because every shipped profile defines `serial:`.
- **The device's byte port must be reachable from wherever the bridge runs.** → In compose (the motivating case) it is, over the service network, with nothing published. From a host against a container it needs one more `ports:` line, and the refusal names that cause and the `host: 0.0.0.0` fix directly.
- **A "sidecar" must be a process in the POS's service, not a sibling container.** → Documented as the reason, not as a rule: a pty lives in its creator's devpts. The compose recipe puts the bridge in the POS service, and `docs/serial-bridge.md` says plainly that a shared `/tmp` volume plus `network_mode: service:` does *not* work and is worse than not working, because the symlink then resolves against the wrong devpts.
- **The link directory is 0700, so the bridge and the POS must run as the same user.** → The same constraint applies to native emupos on a host, so it is not new, but in a container whose entrypoint is root and whose POS runs as `node` it will bite. One line in `docs/serial-bridge.md`.
- **A restart allocates a new pty.** → The link path is stable but the device path behind it changes, so a POS that caches a resolved `/dev/pts/N` instead of reopening the link does not recover. Real hardware behaves the same way when unplugged and replugged, so this is the honest simulation; it belongs in the docs.
- **`while :; do emupos bridge deli; sleep 1; done` spins forever on a configuration error.** → Loud rather than silent: every refusal prints its message and fix once per second. One sentence in `docs/serial-bridge.md` telling the developer to watch the first start.
- **Version drift between a bridge installed in the POS image and a pinned simulator image.** → The coupling is `serial_framing` and the `/observed-framing` body, both additive with defaults. Same mitigation as `typed_by: client`: install matching versions, documented.
- **`/observed-framing` is unauthenticated**, like everything else on the control API, so anything local can make a mismatch warning appear. → The API is loopback-bound and this is a testing tool; the same is already true of `POST /scans/{id}/typed`.
- **Windows loud death depends on an unverified com0com setting.** → D9: verify `ExclusiveMode` on Windows before the doc promises it; otherwise the doc states the gap.
- **The acceptance gate.** One runnable check decides whether this design is real (task 7.1). If `test_bridge.py` passes, the three central claims hold: bytes go through inside 100 ms, the framing the POS set is observed, and the port dies loudly with the simulator. If it cannot be made to pass, the design is wrong and no amount of the rest matters.

## Open Questions

**Does `emupos doctor` need a bridge check?** `doctor` already enumerates COM ports from the *configuration*, and a bridge's `--port COM5` is a command-line value the simulator's configuration never mentions — so nothing today can check it. Options: leave `doctor` alone (this change's assumption); add `emupos doctor --bridge-port COM5`; or have `emupos bridge` run the same COM-port check itself before opening. Deferred deliberately, because the answer depends on task 7.7: if com0com is unusable under Secure Boot on the machines people actually have, the useful Windows guidance is the direct-TCP path, and a `doctor` check for COM ports a bridge might use is diagnosing the wrong thing.
