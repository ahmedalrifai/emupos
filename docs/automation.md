# Automating tests with the control API

emupos has two sides:

```
 your POS code ── real device protocols ──▶  emupos  ◀── control API ── your test script
                  TCP 9100 ESC/POS,                    (HTTP + WebSocket
                  Toledo 8217 on serial,                on 127.0.0.1:8765)
                  scanner keystrokes or serial
```

- **The device side** is what your POS talks to. It is identical to real hardware. **Your POS code never calls the control API.** If it did, it would not work with a real printer, scale or scanner.
- **The control API** replaces the hands of a person standing at the counter: putting tomatoes on the scale, pulling the scanner trigger, letting the paper run out, pushing the cash drawer shut, looking at the printed receipt. The `emupos` CLI uses this API. Your automated tests can use it too.

This page is about that second side, for tests that run without a person, for example in CI.

## Why

A CI machine cannot put tomatoes on a scale or open a printer's cover. With emupos, a test can:

1. make something happen in the physical world (`PUT /api/v1/devices/deli/weight`);
2. drive your POS as usual (it talks to the simulated devices over their real protocols);
3. check what your POS did, and what the devices saw (the receipt text, the events).

## Start emupos in CI

Give CI its own configuration. A keyboard-mode scanner types into the focused window, which a CI machine does not have, so use a serial scanner there (see [Who types a keyboard scan](#who-types-a-keyboard-scan) if you cannot):

```yaml
# ci.yaml
schema: 1
devices:
  - id: front
    type: printer
    profile: epson-tm-t20iii
    connections:
      - tcp: { port: 9100 }
  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections:
      - serial: { pty: true }   # macOS and Linux only
  - id: lane2
    type: scanner
    mode: serial
    connections:
      - serial: { pty: true }   # macOS and Linux only
```

On Windows only the printer's TCP connection is available today; see the [hard limits](../README.md#hard-limits).

Start emupos in the background, wait until it answers, run your tests, then stop it:

```sh
emupos run --config ci.yaml > emupos.log 2>&1 &
EMUPOS_PID=$!

# wait up to 30 s for the API
curl --retry-connrefused --retry 30 --retry-delay 1 -sf http://127.0.0.1:8765/api/v1/health

# ... run your tests ...

kill -TERM "$EMUPOS_PID"   # clean shutdown: ports closed, serial links removed
```

The health check answers:

```json
{"status":"ok","version":"<emupos version>","api_version":1}
```

`emupos run` exits with status 1 and a message naming the port if a port is already taken, so a failed start shows up in `emupos.log`.

The serial links are `$TMPDIR/emupos/<device id>`, or `/tmp/emupos/<device id>` when `TMPDIR` is not set. `GET /api/v1/devices` returns them as `connections[].link_path`, so a test can hand the exact path to your POS configuration. Run one simulator per link name: a second `emupos run` that publishes the same link name takes the link over.

## Endpoints

All paths start with `/api/v1`. Request bodies are JSON and need `Content-Type: application/json`. The full OpenAPI document is served at `GET /api/v1/openapi.json`.

| Method | Path | Body | Success | What it does |
|---|---|---|---|---|
| `GET` | `/health` | — | 200 | `{"status": "ok", "version", "api_version": 1}` |
| `GET` | `/devices` | — | 200 | Every device with its connections and state |
| `GET` | `/devices/{id}` | — | 200 | One device |
| `PUT` | `/devices/{id}/faults/{fault}` | — | 204 | Printer: activate `paper-near-end`, `paper-out`, `cover-open` or `offline` |
| `DELETE` | `/devices/{id}/faults/{fault}` | — | 204 | Printer: clear that fault |
| `POST` | `/devices/{id}/drawer/close` | — | 204 | Printer: push its cash drawer shut |
| `GET` | `/devices/{id}/receipts` | — | 200 | Printer: completed receipts, newest first |
| `GET` | `/devices/{id}/receipts/{receipt_id}` | — | 200 | Printer: one receipt's metadata; `latest` is the newest |
| `GET` | `/devices/{id}/receipts/{receipt_id}/text` | — | 200 | Printer: the receipt as text (`text/plain; charset=utf-8`) |
| `GET` | `/devices/{id}/receipts/{receipt_id}/image` | — | 200 | Printer: the receipt as a PNG (`image/png`) |
| `PUT` | `/devices/{id}/weight` | `{"grams": 1250, "stable": true}` | 204 | Scale: set the gross weight; `stable` is optional (default `true`) |
| `POST` | `/devices/{id}/zero` | — | 204 | Scale: zero (weight 0 g, tare cleared) |
| `POST` | `/devices/{id}/tare` | — | 204 | Scale: the current weight becomes the tare |
| `POST` | `/devices/{id}/scans` | `{"data": "2112345012506", "countdown_seconds": 3, "unicode": false}` | 202 | Scanner: scan `data` after the countdown; returns `{"id", "typed_by", "deliver_at"}`. A `typed_by: client` scanner answers **200** and adds `keys` and `inter_key_delay_ms` for you to type — see [Who types a keyboard scan](#who-types-a-keyboard-scan) |
| `POST` | `/devices/{id}/scans/{scan_id}/typed` | `{"outcome": "delivered"}` or `{"outcome": "failed", "keys_accepted": 7}` | 204 | Scanner: report how your typing of a `typed_by: client` scan went. A scan id that is no longer in progress does nothing |
| `POST` | `/barcodes/weighed` | `{"layout": "21IIIIIWWWWWC", "item": 12345, "grams": 1250}` | 200 | Weighed-item EAN-13 digits: `{"digits": "2112345012506"}`; `price_minor` instead of `grams` for price layouts; needs no device |
| `WS` | `/events` | — | — | Event stream, see [Events](#events) |

Device descriptions look like this:

```json
{"id":"front","type":"printer","profile":"epson-tm-t20iii","connections":[{"kind":"tcp","endpoint":"127.0.0.1:9100","link_path":null,"device_path":null}],"state":{"faults":["paper-out"],"drawer":"closed"}}
```

| Type | `state` fields |
|---|---|
| printer | `faults`, `drawer` (`open` or `closed`) |
| scale | `grams`, `tare_grams`, `net_grams`, `stable`, `capacity_grams` |
| scanner | `mode`, `suffix`, `inter_key_delay_ms` |

Receipt metadata:

```json
{"id":"front-20260913T221525555Z-d8d2bea0","device_id":"front","completed_at":"2026-09-13T22:15:25.555Z","width_dots":576,"height_dots":24,"boundary":"cut"}
```

`boundary` says what ended the receipt: `cut`, `connection-closed` or `idle-timeout` (no bytes for `job_idle_timeout_ms`, 2 s by default).

Faults, the drawer and receipts are described byte by byte in [protocols/escpos-status.md](protocols/escpos-status.md); the scale in [protocols/toledo8217.md](protocols/toledo8217.md).

## Errors

Every error has the same JSON body:

```json
{"error": {"code": "device_not_found", "message": "no device `nope`", "fix": "list device ids with GET /api/v1/devices"}}
```

`code` is stable and meant for programs; `message` and `fix` are for people. `fix` is `null` when there is nothing to suggest.

| Status | When | Codes |
|---|---|---|
| 403 | The request came from a web page, or has a non-local `Host` header | `browser_request_refused`, `invalid_host` |
| 404 | Unknown device, receipt or path | `device_not_found`, `receipt_not_found`, `not_found` |
| 405 | The path exists but not with that method | `method_not_allowed` |
| 409 | The operation does not fit the device's type or current state | `wrong_device_type`, `scale_in_motion`, `scan_in_progress`, `keyboard_unavailable` |
| 415 | A body that is not JSON | `unsupported_media_type` |
| 422 | Invalid body or parameter, including an unknown fault name | `validation_error` |
| 500 | Unexpected failure; details are in the `emupos run` output | `internal_error` |

Examples:

```
PUT /api/v1/devices/front/faults/jammed
422 {"error":{"code":"validation_error","message":"unknown fault `jammed`; valid faults: paper-near-end, paper-out, cover-open, offline","fix":null}}

PUT /api/v1/devices/deli/weight  {"grams": 1.25}
422 {"error":{"code":"validation_error","message":"`grams`: an integer is required","fix":"check the request against /api/v1/openapi.json"}}

PUT /api/v1/devices/front/weight  {"grams": 1250}
409 {"error":{"code":"wrong_device_type","message":"`front` is a printer and this operation needs a scale","fix":null}}
```

## Who types a keyboard scan

A `mode: keyboard` scanner presses keys on a real keyboard, so someone has to be at a keyboard. The scanner's `typed_by` setting says who:

| `typed_by` | Who presses the keys | `POST /devices/{id}/scans` answers |
|---|---|---|
| `server` (default) | the machine running `emupos run` | **202** with `{"id", "typed_by": "server", "deliver_at"}`, and emupos types the scan for you |
| `client` | whoever posted the scan | **200** with `{"id", "typed_by": "client", "deliver_at", "inter_key_delay_ms", "keys"}` — **you** type those keys, then report back |

**The trap:** a script written against a `typed_by: server` scanner still gets a 2xx from a `typed_by: client` one, but nothing is ever typed and no `scanner.scan.delivered` event arrives, so the script waits until it times out. Branch on `typed_by` in the response, or keep your scripts on `mode: serial`, which needs no keyboard at all and is what CI should use.

Each entry of `keys` is either a physical key, `{"usage": 30, "shift": false}` — the HID usage ID on page `0x07`, as a USB scanner sends, with the active keyboard layout deciding which character appears — or one exact character, `{"char": "é"}`. Leave at least `inter_key_delay_ms` between keystrokes. When you are done:

```sh
curl -sf -X POST -H 'Content-Type: application/json' -d '{"outcome": "delivered"}' \
  $API/devices/lane1/scans/lane1-3/typed
```

That publishes the scan's `scanner.scan.delivered` event, exactly as an emupos-typed scan does. If the operating system refused some keystrokes, send `{"outcome": "failed", "keys_accepted": 7}` instead: the scanner is freed without an event, and `emupos run` logs the same warning it logs for its own refused keystrokes. Report either way — a scan nobody reports keeps the scanner busy until it expires.

## Events

Connect a WebSocket to `ws://127.0.0.1:8765/api/v1/events`. Every event is one JSON text message:

```json
{"type":"scale.weight.changed","device_id":"deli","at":"2026-09-13T22:11:10.244Z","data":{"grams":500,"tare_grams":0,"net_grams":500,"stable":true}}
```

`at` is UTC with milliseconds. You receive every event published after you connected, in order. **Past events are not replayed**, so subscribe before you trigger what you want to wait for. The stream only sends; you never need to send anything on it.

| Type | `data` |
|---|---|
| `connection.opened`, `connection.closed` | `kind`, `endpoint`, and `client` for TCP |
| `connection.framing-mismatch` | `endpoint`, `mismatches` (each with `setting`, `expected`, `observed`) |
| `printer.job.completed` | `receipt_id`, `boundary` |
| `printer.status.changed` | `faults` (the faults active after the change) |
| `printer.command.unknown` | `bytes` (spaced hex), and `command` when the command was recognised |
| `printer.codepage.unsupported` | `number`, and `code_page` when the profile names it. Published for a number missing from the profile's code-page map, or a code page emupos has no glyph table for |
| `drawer.opened` | `pin` (2 or 5), `on_time_ms` |
| `drawer.closed` | — |
| `scale.weight.changed` | `grams`, `tare_grams`, `net_grams`, `stable` |
| `scale.request.answered` | `request`, `reply` (spaced hex) |
| `scanner.scan.delivered` | `id`, `data`, `mode` |

Waiting for an event is the reliable way to know something finished. For example, a receipt exists only once `printer.job.completed` arrives, which is at the cut, when the connection closes, or `job_idle_timeout_ms` after the last byte.

## Examples

Each example does the four things tests need most: make the printer run out of paper, put weight on the scale, scan a barcode on a serial scanner, and read the latest receipt. They were run against `emupos run --config ci.yaml` from above.

In the Python and Node examples, small stand-in functions play the part of your POS. They talk to the printer over TCP port 9100, exactly as a POS does. In your own tests, call your application there instead.

### curl

```sh
API=http://127.0.0.1:8765/api/v1

# The paper runs out ...
curl -sf -X PUT $API/devices/front/faults/paper-out
# ... your POS asks the printer for its status and should warn the cashier ...
# ... and a new roll goes in.
curl -sf -X DELETE $API/devices/front/faults/paper-out

# 1.25 kg on the scale
curl -sf -X PUT -H 'Content-Type: application/json' -d '{"grams": 1250, "stable": true}' $API/devices/deli/weight

# Scan a barcode right away (countdown 0)
curl -sf -X POST -H 'Content-Type: application/json' -d '{"data": "2112345012506", "countdown_seconds": 0}' $API/devices/lane2/scans
# {"id":"lane2-2","deliver_at":"2026-09-13T22:15:27.606Z"}

# The newest receipt as text
curl -sf $API/devices/front/receipts/latest/text
# Hello from emupos
```

`-f` makes curl exit with an error on 4xx and 5xx responses.

### Python

Uses the standard library and [websockets](https://websockets.readthedocs.io/). Run with `pytest`, for example `uv run --with pytest --with websockets pytest tests/`.

```python
# tests/test_pos_with_emupos.py
import json
import socket
import urllib.request

from websockets.sync.client import connect

API = "http://127.0.0.1:8765/api/v1"
EVENTS = "ws://127.0.0.1:8765/api/v1/events"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the API is local: no proxy


def call(method, path, body=None):
    """One control API request; returns the response body as bytes."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(API + path, data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with _opener.open(request, timeout=10) as response:
        return response.read()


def wait_for(events, event_type, **match):
    """Read events until one of `event_type` whose data contains `match` arrives."""
    while True:
        event = json.loads(events.recv(timeout=10))
        if event["type"] == event_type and match.items() <= event["data"].items():
            return event


# --- Stand-ins for your POS. In your tests, call your own application instead. ----------------
# They talk to emupos the way a POS does: over the printer's TCP port, never through the API.


def pos_paper_status():
    with socket.create_connection(("127.0.0.1", 9100), timeout=5) as printer:
        printer.sendall(bytes.fromhex("10 04 04"))  # DLE EOT 4: roll paper sensor status
        return printer.recv(1)


def pos_print_receipt():
    with socket.create_connection(("127.0.0.1", 9100), timeout=5) as printer:
        printer.sendall(b"\x1b@TOTAL 12.50\n\x1dV\x00")  # ESC @, text, GS V 0 (cut)


# --- Tests -------------------------------------------------------------------------------------


def test_pos_notices_paper_out():
    call("PUT", "/devices/front/faults/paper-out")  # the paper roll runs out
    try:
        assert pos_paper_status() == bytes.fromhex("7e")  # paper not present
    finally:
        call("DELETE", "/devices/front/faults/paper-out")  # a new roll goes in


def test_weight_on_the_scale():
    call("PUT", "/devices/deli/weight", {"grams": 1250, "stable": True})  # tomatoes on the scale
    # Now drive your POS: it asks the scale over serial and should show 1.250 kg.
    state = json.loads(call("GET", "/devices/deli"))["state"]
    assert state["net_grams"] == 1250 and state["stable"]


def test_serial_scan():
    with connect(EVENTS) as events:  # subscribe first: past events are not replayed
        scan = json.loads(
            call("POST", "/devices/lane2/scans", {"data": "2112345012506", "countdown_seconds": 0})
        )
        wait_for(events, "scanner.scan.delivered", id=scan["id"])
    # Your POS has now read 2112345012506 and a CR from the scanner's serial port.


def test_receipt_text():
    with connect(EVENTS) as events:
        pos_print_receipt()
        job = wait_for(events, "printer.job.completed")
    text = call("GET", f"/devices/front/receipts/{job['data']['receipt_id']}/text").decode()
    assert "TOTAL 12.50" in text
```

```
....                                                                     [100%]
4 passed in 0.46s
```

### Node.js

Needs Node.js 22 or newer, for the built-in `fetch` and `WebSocket`; no packages. Run with `node --test tests/pos-with-emupos.test.mjs`.

```js
// tests/pos-with-emupos.test.mjs
import assert from "node:assert/strict";
import net from "node:net";
import { test } from "node:test";

const API = "http://127.0.0.1:8765/api/v1";
const EVENTS = "ws://127.0.0.1:8765/api/v1/events";

async function call(method, path, body) {
  const response = await fetch(API + path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${method} ${path}: ${await response.text()}`);
  return response;
}

// Subscribe to events. Past events are not replayed, so subscribe before acting.
async function subscribe() {
  const socket = new WebSocket(EVENTS);
  const received = [];
  const waiters = [];
  socket.onmessage = (message) => {
    received.push(JSON.parse(message.data));
    for (const waiter of [...waiters]) waiter();
  };
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });
  return {
    waitFor: (type, match = () => true) =>
      new Promise((resolve) => {
        const check = () => {
          const event = received.find((e) => e.type === type && match(e));
          if (event) {
            waiters.splice(waiters.indexOf(check), 1);
            resolve(event);
          }
        };
        waiters.push(check);
        check();
      }),
    close: () => socket.close(),
  };
}

// --- Stand-ins for your POS. In your tests, call your own application instead. ---------------
// They talk to emupos the way a POS does: over the printer's TCP port, never through the API.

function posPaperStatus() {
  return new Promise((resolve, reject) => {
    const printer = net.connect(9100, "127.0.0.1", () => printer.write(Buffer.from([0x10, 0x04, 0x04])));
    printer.once("data", (reply) => {
      printer.end();
      resolve(reply[0]);
    });
    printer.on("error", reject);
  });
}

function posPrintReceipt() {
  return new Promise((resolve, reject) => {
    const printer = net.connect(9100, "127.0.0.1", () =>
      printer.end(Buffer.concat([Buffer.from("\x1b@TOTAL 12.50\n"), Buffer.from([0x1d, 0x56, 0x00])]), resolve),
    );
    printer.on("error", reject);
  });
}

// --- Tests ------------------------------------------------------------------------------------

test("POS notices paper out", async () => {
  await call("PUT", "/devices/front/faults/paper-out"); // the paper roll runs out
  try {
    assert.equal(await posPaperStatus(), 0x7e); // paper not present
  } finally {
    await call("DELETE", "/devices/front/faults/paper-out"); // a new roll goes in
  }
});

test("weight on the scale", async () => {
  await call("PUT", "/devices/deli/weight", { grams: 1250, stable: true });
  // Now drive your POS: it asks the scale over serial and should show 1.250 kg.
  const { state } = await (await call("GET", "/devices/deli")).json();
  assert.equal(state.net_grams, 1250);
});

test("serial scan", async () => {
  const events = await subscribe();
  const response = await call("POST", "/devices/lane2/scans", { data: "2112345012506", countdown_seconds: 0 });
  const { id } = await response.json();
  await events.waitFor("scanner.scan.delivered", (e) => e.data.id === id);
  events.close();
  // Your POS has now read 2112345012506 and a CR from the scanner's serial port.
});

test("receipt text", async () => {
  const events = await subscribe();
  await posPrintReceipt();
  const job = await events.waitFor("printer.job.completed");
  events.close();
  const text = await (await call("GET", `/devices/front/receipts/${job.data.receipt_id}/text`)).text();
  assert.match(text, /TOTAL 12\.50/);
});
```

```
✔ POS notices paper out (31.86675ms)
✔ weight on the scale (6.046792ms)
✔ serial scan (6.174708ms)
✔ receipt text (6.543834ms)
ℹ tests 4
ℹ pass 4
```

## GitHub Actions

A job that starts emupos, runs the tests above, and keeps the log and receipts when something fails:

```yaml
name: POS integration tests
on: [push, pull_request]

jobs:
  pos-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10

      - name: Install emupos
        run: uv tool install emupos

      - name: Start emupos
        run: |
          emupos run --config ci.yaml > emupos.log 2>&1 &
          echo $! > emupos.pid
          curl --retry-connrefused --retry 30 --retry-delay 1 -sf http://127.0.0.1:8765/api/v1/health

      - name: Run tests
        run: uv run --with pytest --with websockets pytest tests/

      - name: Stop emupos
        if: always()
        run: kill -TERM "$(cat emupos.pid)"

      - name: Keep the emupos log and receipts
        if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: emupos
          path: |
            emupos.log
            receipts/
```

Receipts are written to `receipts/` next to `ci.yaml` unless the printer sets `receipts_dir`. For Node tests, replace the test step with `node --test tests/pos-with-emupos.test.mjs`.

## Security: local only, no web pages

The control API has no authentication and can type keystrokes when a keyboard-mode scanner is configured. So:

- It listens on `127.0.0.1` by default. Setting `api.host` to another address prints a warning at startup, because any machine that can reach that address could then control the devices.
- **Web pages are refused.** Any request with an `Origin` header gets 403 `browser_request_refused`, including WebSocket connections. Browsers add `Origin` when a web page sends a request to another site; curl, Python, Node's `fetch` and `WebSocket`, and the emupos CLI do not, so scripts and tests work unchanged.
- While the API is on a loopback address, a `Host` header other than `127.0.0.1`, `localhost` or `[::1]` gets 403 `invalid_host`. This blocks DNS rebinding.
- A request body that is not `application/json` gets 415 `unsupported_media_type`. This blocks HTML form posts.

This is also why a browser-based POS cannot call the API — and, as above, it never should: a POS reaches devices only through their real protocols. See [SECURITY.md](../SECURITY.md) for the threat model.
