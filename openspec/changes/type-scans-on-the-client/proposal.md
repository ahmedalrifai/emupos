## Why

Keyboard-mode scans are typed by the process that runs `emupos run`. That process needs a desktop of its own, which it does not always have:

- **emupos in a container**, the common case: `docker compose up` beside the POS, with the operator on the host. On a macOS or Windows host, Docker runs a Linux VM, so a container can never reach the host's window server, whatever flags it is given. On a Linux host it can, but only by bind-mounting `/tmp/.X11-unix`, passing `DISPLAY` and the `XAUTHORITY` cookie, matching the uid, and installing libXtst in the image.
- **emupos over SSH or on a headless box**, where there is no display at all.

Either way every keyboard-mode scan is refused with `keyboard_unavailable`, and the only advice the error gives today is `mode: serial` — which a POS that reads its scanner as a keyboard wedge cannot use.

This is not about reaching emupos across a network: the control API stays loopback-bound and unauthenticated, and a container publishes its ports to `127.0.0.1`. It is about the keystrokes happening in the session that has the POS window, rather than in the one that runs the simulator.

The split already exists in the code: `emupos scan` validates the data with the scanner's own rules, runs the countdown and checks keyboard focus, all locally, and then posts with `countdown_seconds: 0`. Only the keystrokes themselves are on the wrong side.

## What Changes

- **A keyboard scanner gains `typed_by`: `server` (the default, today's behaviour) or `client`.**
  - Serial mode has no keystrokes, so `typed_by` on a `mode: serial` scanner is a configuration error.
  - No auto-detection. "This machine has no display, so let the client type" would turn a misconfiguration into a scan that silently appears somewhere else.
- **With `typed_by: client`, the server keeps everything except the typing.** Validation, the US-layout rules, the suffix key, the one-scan-at-a-time state and the `scanner.scan.delivered` event stay exactly where they are.
  - `POST /devices/{id}/scans` answers **200** with the key plan instead of 202 with `deliver_at`: `{ "id", "typed_by", "inter_key_delay_ms", "keys": [ { "usage": 30, "shift": false }, { "char": "é" } ] }`. The keys come straight from `plan_keys`, as `PhysicalKey` (`usage`/`shift`) or `UnicodeText` (`char`).
  - **`POST /devices/{id}/scans/{scan_id}/typed`** reports the outcome: `{ "outcome": "delivered" }` publishes the event exactly as the server-side path does; `{ "outcome": "failed", "keys_accepted": 7, "reason": "…" }` frees the scanner and logs the same `emupos run` warning that a partly-typed scan logs today. A stale or unknown `scan_id` is a no-op, matching `finished()`.
  - A report for a `typed_by: server` scanner is a 409, and vice versa.
- **A client-typed scan expires.** If the client never reports back — its terminal was closed, the machine slept — the scanner would stay busy for the rest of the run and refuse every later scan with 409. A client-typed scan therefore carries a deadline of its typing time plus a grace period, after which the scanner is free again. Server-typed scans keep no deadline: `deliver_scan` is still in charge of them, and an expiring one would let two scans type at once.
- **The keyboard prerequisite moves to whoever types.** For a `typed_by: client` scanner the server no longer calls `check_ready()`; `emupos scan` calls it locally before the countdown and reports the same message and fix, so a missing Accessibility permission or a Wayland session is refused on the machine it is actually about — and refused before the countdown rather than after it.
- **`emupos scan` gains one branch.** For a `typed_by: client` scanner it checks the keyboard, counts down, checks focus (all unchanged and already local), posts the scan, types the returned plan with `type_keys`, posts the outcome, and then waits for `scanner.scan.delivered` as it does today, so the success line and the `scan_not_confirmed` error are unchanged. When the OS refused keystrokes, it says so instead of pointing at the `emupos run` output, which for a container is `docker logs` rather than a terminal in front of the operator.
- **`GET /devices/{id}` reports `typed_by`**, so the CLI can branch and `emupos devices` can show "keyboard mode, typed by the client".
- **`emupos doctor`'s keyboard check follows `typed_by`.** A keyboard scanner the server does not type for no longer makes the check fail on the server's machine.
- **The `keyboard_unavailable` fix text names `typed_by: client`** alongside `mode: serial`. That error is how a user in this situation finds the setting.
- **Documentation:**
  - `docs/configuration.md`: the `typed_by` row.
  - `docs/linux-x11.md` and `docs/macos-accessibility.md`: the display and the Accessibility permission are needed on the machine that types — the server's for `server`, the one running `emupos scan` for `client`.
  - `docs/automation.md`: a script that posts a client-typed scan must type the plan itself or use serial mode; `typed_by` in the response says which it got.
  - `README.md`: the two-sides diagram notes that with `typed_by: client` the keystrokes come from the operator's side.

## Non-goals

- **A Docker image and its release.** Separate change: the image, the `0.0.0.0` bind its config needs, and publishing it.
- **Wayland.** Keyboard mode still refuses a Wayland session wherever the typing happens. `typed_by: client` does not change that; a uinput/evdev backend would, and is not part of this change.
- **Per-request choice.** `typed_by` is configuration, not a field on `POST /scans`: a script must not be able to claim the typing for a scanner whose operator expects the server to do it.
- **Serial mode.** Unchanged in every respect.
- **Reporting progress while typing.** The client reports once, at the end.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `barcode-scanner`: a new "Client-typed scans" requirement (the plan, the report, the expiry); "Scan requests", "macOS Accessibility permission" and "Linux keyboard mode requires X11" gain the client-typed case, where the prerequisite is the client's and the server does not check it.
- `control-api`: "Scan triggering" gains the 200 response with the key plan; a new requirement for `POST /devices/{id}/scans/{scan_id}/typed`; "Device descriptions" adds `typed_by` to a scanner's state.
- `configuration`: the scanner's `typed_by` field, its default, and its rejection in serial mode.
- `cli`: "Scan command" types the plan itself for a client-typed scanner, checks the keyboard locally before the countdown, and names a refused-keystrokes failure; `emupos devices` shows `typed_by`; `emupos doctor`'s keyboard check follows it.

## Impact

- `src/emupos/scanner/keys.py`: the JSON form of `PhysicalKey` and `UnicodeText`.
- `src/emupos/scanner/scanner.py`: `typed_by` on the scanner, the scan's deadline, and expiry in `request`. The state machine is otherwise unchanged.
- `src/emupos/daemon/simulator.py`: `request_scan` skips `check_ready` and `deliver_scan` for a client-typed scanner; a `report_typed` path.
- `src/emupos/daemon/scans.py`: the warning a failed report logs, beside the one `deliver_scan` logs.
- `src/emupos/api/routes/scanners.py`, `src/emupos/api/routes/devices.py`, `src/emupos/api/schemas.py`: the response, the `/typed` endpoint, `typed_by` in the device state.
- `src/emupos/cli/actions.py`: the client-typing branch. `src/emupos/cli/devices.py`, `src/emupos/cli/doctor.py`: `typed_by`.
- `src/emupos/config.py` and the JSON schema: `typed_by`.
- `docs/configuration.md`, `docs/linux-x11.md`, `docs/macos-accessibility.md`, `docs/automation.md`, `README.md`, `docs/api/openapi-v1.json`.
- **Dependencies:** none. No new Python dependency, and no change to what a server-typed scan does.
- **Compatibility:** `typed_by` defaults to `server`, so every existing configuration, API response and script behaves exactly as before. A `feat` commit.
