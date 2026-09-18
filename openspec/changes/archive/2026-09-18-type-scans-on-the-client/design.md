## Context

A keyboard-mode scan is typed by the process that runs `emupos run`:

```
  emupos run ──▶ Simulator.request_scan ──▶ keyboard.check_ready()
                                        ──▶ scanner.request(...)            (validate, plan_keys, busy)
                                        ──▶ deliver_scan(...)               (sleep, type_keys, finished)
```

`emupos scan` already does the human-facing half of this on its own machine (`src/emupos/cli/actions.py`):

- `_check_scan` builds a local `Scanner` from the device state and runs the server's own validation rules;
- `_count_down` runs the countdown locally, and `terminal_with_focus()` cancels the scan if the operator never left the terminal;
- it then posts with `countdown_seconds: 0`, so the server types at once.

Only `type_keys` is on the server's side. When emupos runs without a desktop of its own — in a container, or over SSH — that is the one piece in the wrong place, and every keyboard scan is refused with `keyboard_unavailable`.

Three properties of the existing code shape this design:

- **`Scanner` is pure and receives `now` on every call** (`src/emupos/scanner/scanner.py`). The daemon owns the clock and the tasks.
- **The simulator never schedules a timer for a scanner.** `_schedule_tick` returns early for `Scanner` (`src/emupos/daemon/simulator.py`); scanners are the one device with no `tick`.
- **A scanner's observable state is `mode`, `suffix` and `inter_key_delay_ms`** (`src/emupos/api/routes/devices.py`). There is no `busy` field, and `failed()` publishes no event, so *when* a stuck scan is cleaned up is not observable — only whether the next request is accepted.

## Goals / Non-Goals

**Goals:**

- The keystrokes happen on the machine that has the POS window, while validation, the key plan, the one-scan-at-a-time state and the delivery event stay on the server.
- Everything watching the event stream sees exactly what it sees today: one `scanner.scan.delivered` per scan, after the last keystroke.
- A client that never reports back cannot make a scanner refuse scans for the rest of the run.
- A configuration without `typed_by` behaves byte-for-byte as it does today.

**Non-Goals:**

- Changing serial mode, or the keys a scan presses.
- Supporting Wayland, on either side.
- Letting a request choose who types.
- Progress reporting during typing.

## Decisions

### D1. `typed_by` is per-scanner configuration, not auto-detected

Whether the server can type is really a property of the machine it runs on, so a server-wide setting would also fit. Per-device wins because every other scanner setting is already per-device, it needs no new configuration section, and a deployment file is per-machine anyway.

Auto-detection ("no display, so let the client type") was rejected: a scanner misconfigured as `typed_by: client` would then be silently accepted by a server that could have typed, and the scan would appear on whichever machine ran the CLI — or nowhere at all, with no error to explain it. A wrong `typed_by` must fail loudly.

Per-request (`{"typed_by": "client"}` in the body) was rejected for the same reason in reverse: a script could claim the typing for a scanner whose operator expects the server to type, and the scan would never appear.

`typed_by` on a `mode: serial` scanner is rejected in `config.py`, beside the existing check that a keyboard scanner has no connections.

### D2. The server returns the key plan; the client does not build it

The CLI could call `plan_keys` itself — it is one import away, and `_check_scan` already constructs a `Scanner` locally. The server returns the plan instead because:

- the response is then self-describing: a script that posts a scan and receives `typed_by: "client"` and `keys` can see that the scan is now its own to type, which is the trap `docs/automation.md` has to warn about;
- a CLI installed on the operator's machine and a server pinned as a container image drift in version by default, and the plan is the part where drift is silent — a key plan built against another version's `US_LAYOUT` types the wrong characters, where a validation rule that drifted merely accepts or refuses the request.

This does not remove the shared-code dependency: `_check_scan` still runs the local rules first, so a large version gap is still visible as a local refusal. It narrows what depends on it.

### D3. One response model; 202 for a server-typed scan, 200 for a client-typed one

202 promises "accepted, it will happen". For a client-typed scan nothing further happens on the server, so 200 is the honest code. Two response *models* were rejected — a union response is awkward in the OpenAPI document and in every generated client. Instead `ScanAccepted` gains `typed_by` and the optional `keys` and `inter_key_delay_ms`, and the route sets the status code on the injected `Response`.

**`deliver_at` stays required in both responses.** Making it nullable is a breaking change to `/api/v1` by the "Versioned and stable contract" requirement, and `scripts/check_api_compat.py` refuses it. It is also not the better API: a client-typed response's `deliver_at` is when the client is to *start* typing, so a script that posts `countdown_seconds: 5` still learns when to begin, and a scan's expiry counts from the same moment. Every new field is optional, so the contract stays additive.

A client that ignores the status and reads `id` keeps working either way.

### D4. A client-typed scan expires; there is no watchdog task

Without a deadline, a client that dies mid-scan leaves the scanner busy for the rest of the run, and every later scan gets 409 `scan_in_progress` with a fix that tells the user to wait for an event that will never arrive.

An `asyncio` task that sleeps and calls `scanner.failed()` would work, but it adds the daemon's only scanner timer and a cancellation race with the report arriving. Instead the accepted scan carries `expires_at`, and `Scanner.request` treats an expired scan as not in progress:

```
  accept ──▶ expires_at = now + len(keys) * inter_key_delay_ms + GRACE
  request ──▶ busy only while now < expires_at
  report  ──▶ finished(id) / failed(id), unchanged
```

This fits the two properties above: `Scanner` already receives `now` on every call, and the simulator deliberately has no scanner timer. It is also better on one axis — a slow client reporting after the deadline still publishes `scanner.scan.delivered`, where a timer would already have made the report a no-op. Since a scanner exposes no `busy` state and `failed()` publishes nothing, a lazily freed slot and a timer-freed slot are indistinguishable from outside.

**Server-typed scans keep `expires_at` unset.** `deliver_scan` is still responsible for them, and it may legitimately sit in `prepare_key` for seconds (the spec allows a scan to wait up to 2 s for a reused X11 key code). If a server-typed slot expired underneath it, a second scan would be accepted and two scans would type into the same window at once.

The grace period is chosen so the CLI always gives up first: `emupos scan` waits `CONFIRM_SECONDS` (10 s) after typing was due to finish and then raises `scan_not_confirmed`, so a grace of 15 s leaves about 5 s in which the operator has already been told the scan failed and the server has not yet handed the scanner to anyone else.

### D5. `typed_by` is a defaulted keyword on `Scanner`

`Scanner.request` needs it to decide whether to set `expires_at`, and `_state` reports it, so the scanner carries it rather than the simulator branching on `runtime.config`. It is added as a keyword argument defaulting to `"server"`, which keeps the CLI's existing positional construction in `_check_scan` working unchanged.

### D6. The report names an outcome, and a stale id is a no-op

`POST /devices/{id}/scans/{scan_id}/typed` takes `{"outcome": "delivered"}` or `{"outcome": "failed", "keys_accepted": <int>, "reason": <string>}`:

- `delivered` calls `scanner.finished(scan_id)`, which already publishes the one delivery event and already returns `NO_OUTPUT` for an id that is not the scan in progress — so "a stale or unknown id does nothing" needs no new code;
- `failed` calls `scanner.failed(scan_id)` and logs the warning that `deliver_scan` logs today, naming `keys_accepted` of the plan's length. The barcode-scanner spec requires that warning in the `emupos run` output, and reporting it back keeps it there.

A report for a `typed_by: server` scanner is a 409, and a client-typed scanner that is asked to deliver server-side is the same mistake seen from the other end; both are configuration errors worth naming rather than ignoring.

### D7. The client checks the keyboard before the countdown

Today `check_ready()` runs on the server when the request arrives — which, for a keyboard scanner, is *after* the CLI's countdown has already finished. Moving the check to the client also moves it earlier: `emupos scan` checks before counting down, as `_check_scan` already validates before counting down. A missing Accessibility permission is then reported in the first moment rather than after three seconds of "click your POS window".

The existing `KeyboardUnavailableError` carries `message` and `fix`, which map onto `CliError` unchanged, so the text the user sees is the text the API returns today.

### D8. The client still waits for the delivery event

After reporting, `emupos scan` waits for `scanner.scan.delivered` exactly as it does now, even though it already knows the outcome. The wait loop, the success line and the `scan_not_confirmed` error are then unchanged, and the event remains the single thing an automated test synchronises on.

The one message that does change is the failure text: when the client typed, it knows that the OS refused keystrokes, so it says so instead of telling the operator to read an `emupos run` output that may be a container's log.

### D9. The JSON form of a key

`{"usage": <int>, "shift": <bool>}` for `PhysicalKey` and `{"char": "<one code point>"}` for `UnicodeText`, discriminated by which field is present. `key_to_json` / `key_from_json` live in `scanner/keys.py` beside the types, and are the only new pure logic in the change.

## Risks / Trade-offs

- **A client reports `delivered` without typing** → the event lies. Accepted: the control API has no authentication and is loopback-bound by design (control-api "Local binding"); a client that wanted a false event could already request a scan it then ignores.
- **Version drift between a host CLI and a pinned server image** → narrowed by D2, not removed: `_check_scan` still runs local validation rules. Mitigation is documentation — install the CLI from the same version as the image.
- **A scan expires while a slow client is still typing, and a second scan is then accepted** → both type into the same window. The grace exceeds the CLI's own give-up time, and typing longer than the grace means the OS or the X11 key-code wait is far outside its documented bounds.
- **The client crashes between typing and reporting** → the keystrokes arrived but no event is published, and `emupos scan` exits with `scan_not_confirmed`. The same is true today when the server is killed mid-scan.
- **`typed_by: client` still cannot type on Wayland**, in a container, or over SSH without a display. The error now comes from the client's machine, which is the machine the user can do something about.

## Migration Plan

`typed_by` defaults to `server`. No configuration, response or script changes behaviour, and no migration step is needed. Rolling back is removing the field: a configuration that used `typed_by: client` then fails validation with an unknown-field error rather than silently typing in the wrong place.

## Open Questions

None.
