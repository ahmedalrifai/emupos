## 1. Keys on the wire

- [x] 1.1 In `scanner/keys.py`, add `key_to_json(key)` and `key_from_json(value)` for `PhysicalKey` (`{"usage", "shift"}`) and `UnicodeText` (`{"char"}`), discriminated by which field is present (design D9). `key_from_json` raises `ValueError` for anything else, including a `char` that is not exactly one code point.
- [x] 1.2 In `test_keys.py`, round-trip both key kinds, including a shifted key and a non-ASCII character, and test that a malformed value is refused.

## 2. The scanner carries who types

- [x] 2.1 In `scanner/scanner.py`, add `typed_by: TypedBy = "server"` as a keyword argument of `Scanner.__init__` with `type TypedBy = Literal["server", "client"]`, so the CLI's existing positional construction keeps working (design D5).
- [x] 2.2 Add `expires_at: float | None` to `AcceptedScan`. `request` sets it to `now + len(keys) * inter_key_delay_ms / 1000 + CLIENT_TYPING_GRACE_S` for a client-typed scan and `None` otherwise, with `CLIENT_TYPING_GRACE_S = 15` and a comment naming the CLI's 10-second confirmation wait (design D4).
- [x] 2.3 In `request`, treat an in-progress scan whose `expires_at` has passed as not in progress, so the new scan is accepted. Leave `finished` and `failed` unchanged.
- [x] 2.4 In `test_scanner.py`, test that a client-typed request returns a scan whose keys are the plan and leaves the scanner busy; that `finished` frees it and emits one event; that a second request before the deadline is refused and after it is accepted; and that a server-typed scan never expires.

## 3. Configuration

- [x] 3.1 In `config.py`, add `typed_by: Literal["server", "client"] = "server"` to `ScannerDevice`, and reject it on a `mode: serial` scanner in the validator beside the connections check, with a message stating that a serial scanner types no keys.
- [x] 3.2 In `test_config.py`, test the default, the serial rejection with its path, and the rejection of an unknown value.
- [x] 3.3 Regenerate nothing by hand: confirm `emupos config schema` includes `typed_by` with both values and the default.

## 4. Simulator

- [x] 4.1 In `daemon/runtime.py`, pass `config.typed_by` when building the `Scanner`.
- [x] 4.2 In `daemon/simulator.py`, make `request_scan` skip `check_ready()` and skip spawning `deliver_scan` when the scanner is client-typed, and return the accepted scan as before.
- [x] 4.3 Add `report_typed(scanner, scan_id, outcome, keys_accepted, reason)` to the simulator: `delivered` applies `scanner.finished(scan_id)`; `failed` calls `scanner.failed(scan_id)` and logs the warning.
- [x] 4.4 In `daemon/scans.py`, factor out the warning `deliver_scan` logs today so both paths log the same text, and give the client path the reported `keys_accepted` and plan length.
- [x] 4.5 Test through the simulator that a client-typed request types nothing, that a delivered report publishes exactly one event, that a failed report publishes none and frees the scanner, and that a stale id does nothing.

## 5. Control API

- [x] 5.1 In `api/schemas.py`, add the key models and extend `ScanAccepted` with `typed_by`, optional `deliver_at`, `keys` and `inter_key_delay_ms` (design D3). Add `ScanTypedReport` with `outcome`, optional `keys_accepted` and `reason`.
- [x] 5.2 In `api/routes/scanners.py`, return 200 with the key plan for a client-typed scanner and 202 with `deliver_at` otherwise, by setting the status on the injected `Response`.
- [x] 5.3 Add `POST /devices/{device_id}/scans/{scan_id}/typed`, answering 204, and 409 `typed_by_mismatch` when the scanner's `typed_by` does not match the report.
- [x] 5.4 When mapping `KeyboardUnavailableError` to its 409, add `typed_by: client` to the fix text, so the error a server without a display returns names the setting that solves it.
- [x] 5.5 In `api/routes/devices.py`, add `typed_by` to a scanner's state.
- [x] 5.6 In `test_api.py`, test the 200 shape and its keys for both `unicode` values, the 202 shape for a server-typed scanner, 409 on a mismatched report, 204 on a stale id, `wrong_device_type` on a printer, and `typed_by` in the device description.
- [x] 5.7 Regenerate `docs/api/openapi-v1.json`.

## 6. CLI

- [x] 6.1 In `cli/actions.py`, branch `scan` on `state["typed_by"]`: for a client-typed scanner call `system_keyboard().check_ready()` before the countdown, mapping `KeyboardUnavailableError` to a `CliError` with its message and fix (design D7).
- [x] 6.2 After the POST, type the returned plan with `asyncio.run(type_keys(keyboard, keys, inter_key_delay_ms))`, then POST the outcome: `delivered` when every key was accepted, `failed` with `keys_accepted` otherwise.
- [x] 6.3 Keep the existing wait for `scanner.scan.delivered`, the success line and the `scan_not_confirmed` error (design D8); when the client itself saw keys refused, raise instead with a message naming the accepted count and the privilege-level limitation.
- [x] 6.4 In `cli/devices.py`, show `typed by the client` in a keyboard scanner's summary when `typed_by` is `client`.
- [x] 6.5 In `cli/doctor.py`, count only `typed_by: server` keyboard scanners when deciding whether a missing keyboard prerequisite is a failure rather than a warning.
- [x] 6.6 In `test_commands.py` (or beside it), with a fake keyboard and a fake API: the plan is typed and reported as delivered; a refused key reports `failed` and the error names the count; the focus check still cancels before the POST; a not-ready keyboard exits before the countdown.

## 7. Documentation

- [x] 7.1 `docs/configuration.md`: the `typed_by` row, its default, and that it is keyboard-only.
- [x] 7.2 `docs/linux-x11.md` and `docs/macos-accessibility.md`: the display and the Accessibility permission are needed on the machine that types — the simulator's for `server`, the one running `emupos scan` for `client`.
- [x] 7.3 `docs/automation.md`: a script that posts a scan to a client-typed scanner must type the plan itself or use serial mode; `typed_by` in the response says which it got.
- [x] 7.4 `README.md`: the two-sides diagram notes that with `typed_by: client` the keystrokes come from the operator's side.
- [ ] 7.5 `CHANGELOG.md` is generated by release-please: check that the commit message describes the feature as `feat(scanner):`.

## 8. Checks

- [x] 8.1 Run the full test suite, the type checker and the linter on macOS.
- [x] 8.2 Run `emupos scan` by hand against a simulator started with `typed_by: client` and confirm the keystrokes arrive in another window and the success line is unchanged. Done on macOS: `uv run emupos run` with `lane1` set to `typed_by: client`, then `uv run emupos scan 182398712983` from a second terminal with TextEdit focused; the barcode and its Enter arrived in TextEdit.
- [x] 8.3 Confirm a configuration without `typed_by` behaves exactly as before: 202, `deliver_at`, and the simulator types.
