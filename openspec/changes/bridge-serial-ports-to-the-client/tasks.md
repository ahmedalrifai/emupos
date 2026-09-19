## 1. Framing observation splits from framing comparison

- [ ] 1.1 In `transports/framing.py`, add `observed_framing_changes(fd, interval=0.2) -> AsyncIterator[ObservedFraming]`: today's poll loop with its `if observed != last` dedup, yielding each distinct observation. Rewrite `watch_framing` as an `async for` over it that applies `framing_mismatches` and calls `on_mismatch`, keeping its current signature and docstring promise.
- [ ] 1.2 In `transports/test_framing.py`, test the generator directly on a pty pair: setting the same framing twice yields once, changing it yields again, and the existing `watch_framing` tests still pass unchanged.

## 2. Expected framing and the mismatch report become reusable

- [ ] 2.1 In `daemon/connections.py`, lift `expected_framing(loaded: LoadedConfig, config: DeviceConfig) -> SerialFraming | None` to module level: `SCANNER_FRAMING` for a `mode: serial` scanner, `None` for a keyboard scanner, the profile's `serial` otherwise. Make `Connections._framing` a wrapper that keeps its `EndpointUnavailableError` raise for the `None` case.
- [ ] 2.2 Lift `report_framing(publish, device_id, endpoint, mismatches)` to module level with the current event data and `logger.warning` text unchanged, and make `Connections._framing_reporter` return a closure over it.
- [ ] 2.3 In `daemon/simulator.py`, add `report_observed_framing(runtime, endpoint, observed) -> tuple[Mismatch, ...]`: look up `expected_framing`, call `framing_mismatches`, and on a non-empty result call `report_framing(self.bus.publish, ...)`. Raise `ValueError` when the device has no serial framing, for the route to map.
- [ ] 2.4 Test through the simulator that a mismatching observation publishes exactly one `connection.framing-mismatch` with the same payload shape a local pty produces, that a matching one publishes none, and that a keyboard scanner raises.

## 3. Control API

- [ ] 3.1 In `api/schemas.py`, add `SerialFramingOut`, `MismatchOut`, `FramingReport` (the 200 body) and `ObservedFramingReport(RequestBody)` with `endpoint: str`, `baud: int`, `data_bits: int | None = None`, `parity: Literal["none","even","odd"] | None = None`. Add `serial_framing: SerialFramingOut | None = None` to `DeviceInfo`.
- [ ] 3.2 In `api/routes/devices.py`, give `describe` the loaded configuration — `describe(runtime, now, loaded)`, passed from `list_devices` and `get_device`, which both already hold `SimulatorDep` — and fill `serial_framing` from `expected_framing(loaded, runtime.config)`.
- [ ] 3.3 In the same router, add `POST /devices/{device_id}/observed-framing` calling `Simulator.report_observed_framing`, answering 200 with the mismatches and 409 `no_serial_framing` (with a fix naming which devices have framing) when it raises. Keep it here so `api/app.py` needs no new router.
- [ ] 3.4 In `api/test_api.py`: `serial_framing` for a scale, for a serial scanner (9600 8N1) and `null` for a keyboard scanner; the report's 200 body for a full macOS-shaped observation and for a Linux-shaped one with nulls; 409 for a keyboard scanner; 404 for an unknown device.
- [ ] 3.5 Regenerate `docs/api/openapi-v1.json` with `uv run python scripts/check_api_compat.py --update` and confirm the compatibility check passes.

## 4. The relay

- [ ] 4.1 Create `src/emupos/transports/bridge.py` with `BridgeLost(Exception)` and `_relay(host, port, framing, *, link, alias, serial_port, on_open, on_observed, alive, link_dir=None)` — `link_dir` is for tests only and the CLI never passes it. Open the TCP connection **first**, then the local port, so a refused connect leaves nothing behind.
- [ ] 4.2 Add `_keepalive(sock)`: `SO_KEEPALIVE`, then the idle option as `getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)` at 5 s, `TCP_KEEPINTVL` 2 s and `TCP_KEEPCNT` 3, each skipped when absent.
- [ ] 4.3 Add the two pumps (`local.reader` → socket writer, socket reader → `local.writer`, `read(65536)` with `drain()`), the framing watcher (`async for observed in observed_framing_changes(local.slave_fd): await asyncio.to_thread(on_observed, observed)`, pty branch only, skipped on Windows and for `--port`), and the liveness task (`await asyncio.to_thread(alive)` every 2 s, finishing after two consecutive `False`).
- [ ] 4.4 Run all four under `asyncio.wait(return_when=FIRST_COMPLETED)`. On any completion: cancel the framing watcher **first**, then the rest, then `await local.close()`, then remove the alias when `os.readlink(alias) == device_path`. Raise `BridgeLost` when the cause was EOF or the liveness task.
- [ ] 4.5 Add `_link_alias(device_path, alias) -> None`: replace a dangling symlink, refuse one that still resolves and refuse anything that is not a symlink, both with an `EndpointUnavailableError` naming the path and what it points at, and never write a pid file beside it. `open_pty` is called with no `link_dir`, so `_publish_link` never sees a path the user chose.
- [ ] 4.6 Add `relay(...)`, the synchronous `asyncio.run` wrapper, and install `loop.add_signal_handler(signal.SIGTERM, ...)` on non-Windows as `daemon/server.py` does.

## 5. The command

- [ ] 5.1 In `cli/client.py`, add an optional `timeout: float = TIMEOUT_SECONDS` to `Client.send` and `Client.get`, passed to `_opener.open`.
- [ ] 5.2 Create `src/emupos/cli/bridge.py` with `bridge(ctx, device, link, alias, port, tcp)`. Do the `GET /devices/{id}`, pick the `tcp` connection (`endpoint.rsplit(":", 1)`), apply `--tcp` as an override of the port or of `host:port`, and read `serial_framing`. Import `emupos.transports.bridge` lazily inside the body.
- [ ] 5.3 Implement every refusal in the D8 table with its message, fix and exit code, all **before** `relay` is called: no tcp connection, several without `--tcp`, no serial framing, Windows without `--port`, `--link`/`--alias` with `--port`, and `--link` validated with `TypeAdapter(LinkName)`.
- [ ] 5.4 Implement `on_open` (the announce block: device and address, link path `-> /dev/pts/N` or the COM port, the expected framing with its profile name), `on_observed` (POST the observation, print each returned mismatch with `cli.output.warning`), and `alive` (`client.get("/health", timeout=3)` in a `try`, returning a bool).
- [ ] 5.5 Map `BridgeLost` to exit 1 with "lost the connection to device `deli` at emupos:9200" and its fix, `EndpointUnavailableError` to exit 1, and `ConnectionRefusedError`/`OSError` on the device port to the exit-1 message naming the `host: 0.0.0.0` fix. Ctrl+C and SIGTERM exit 0.
- [ ] 5.6 Register the command in `cli/app.py`: `app.command("bridge")(bridge.bridge)`.
- [ ] 5.7 In `cli/devices.py`, show a device's expected framing in its summary line, so `emupos devices` says which devices speak serial.

## 6. Documentation

- [ ] 6.1 Write `docs/serial-bridge.md`: what the bridge is; the three positions; the compose recipe with the `until [ -e ... ]` readiness line, the `restart` loop and the healthcheck; that a sibling container cannot work and why a shared `/tmp` is worse than not working; that the bridge and the POS must run as the same user; that a restart allocates a new pty so the POS must reopen the link; and that the first start is worth watching because a refusal loops.
- [ ] 6.2 `docs/windows-serial.md`: the `emupos bridge --port COM5` case; that closing COM5 does not remove COM6 and what `ExclusiveMode=yes` is for; and the plain note that a POS able to open a TCP socket needs no com0com at all, which matters because com0com is Code 52 under Secure Boot on Windows 11.
- [ ] 6.3 `docs/automation.md` and `README.md`: one line each — the serial port can be created where the POS is, by `emupos bridge`.
- [ ] 6.4 Regenerate `docs/cli.md` with the `typer ... utils docs` command from CONTRIBUTING.md.

## 7. Checks

- [ ] 7.1 Write `src/emupos/transports/test_bridge.py`, the acceptance gate. Start a throwaway `asyncio.start_server` that answers `W\r` with `b"\x0202.455\r"`; run `_relay` as a task with a `tmp_path` link dir; open the published link from the test, `tcsetattr` it to 19200 8N1, write `W\r`; assert the exact reply bytes, an elapsed round trip **under 0.1 s**, and that `on_observed` fired with baud 19200. Then close the fake server and assert, in this order: the POS's `write()` raises `OSError` with `EIO`, its `read()` returns `b""`, `link_path.exists()` is `False`, reopening the link raises `FileNotFoundError`, and `_relay` raised `BridgeLost`.
- [ ] 7.2 Add a case to `test_bridge.py` for `--alias`: the alias points at the device path, is removed on close, a dangling symlink at that path is replaced, and both a symlink that still resolves and a plain file are refused.
- [ ] 7.3 Add a liveness case: with the fake server still accepting but `alive()` returning `False` twice, the port is closed and `BridgeLost` is raised.
- [ ] 7.4 In `cli/test_end_to_end.py`, run `emupos bridge` against a real `emupos run` with a scale on a TCP port: the weight comes back through the published link, and one `connection.framing-mismatch` event with baud 9600 vs 19200 appears on `/api/v1/events` — the case that died silently behind socat.
- [ ] 7.5 Run the full test suite, pyright strict and ruff on macOS, and confirm a configuration without a bridge produces byte-identical `emupos run` output.
- [ ] 7.6 Run it by hand in Docker: `docker compose` with emupos in one service and a Python POS plus `emupos bridge` in another, open the link, read a weight, then `docker compose stop emupos` and confirm the POS's next write fails and the link is gone.
- [ ] 7.7 On Windows, verify `emupos bridge deli --port COM5` against a com0com pair, and verify whether `ExclusiveMode=yes` makes COM6 disappear when the bridge stops. Write down what actually happened in `docs/windows-serial.md`; if it does not work, say so there instead of promising it.
