## Why

Testing a POS by hand against emupos means a second terminal and a command per physical action: `emupos scale set 1.25kg`, `emupos fault set front paper-out`, `emupos drawer close`, `emupos receipt show`. For demos and exploratory testing, a page showing the devices with a button for each action is quicker (issue #23).

The control API already has everything the page needs, except that a page cannot use it. The API refuses any request carrying an `Origin` header, and browsers attach one to every same-origin `POST`, `PUT` and `DELETE` and to every WebSocket upgrade. This was checked in Chromium against `emupos run` 0.2.0, from a page served by the API itself:

| Request from the page | Result |
|---|---|
| `GET /api/v1/devices` | 200 |
| `PUT /api/v1/devices/{id}/weight` | 403 `browser_request_refused`, weight unchanged |
| `POST /api/v1/devices/{id}/tare` | 403 `browser_request_refused` |
| `WS /api/v1/events` | refused |

A page served by the API can therefore show devices and receipt images, but none of its buttons or its live events can work. The same rule is why "Try it out" in the Swagger UI at `/api/v1/docs` fails on every write today.

## What Changes

- **`emupos run --ui` serves a control page at `/`.** Without `--ui` there is no page, and the API refuses exactly the requests it refuses today. `emupos run --demo --ui` works because the flag needs no configuration file. In Docker the flag is appended to the command: `docker run … emupos run --ui`.
- **What the page shows:**
  - the configured devices, their endpoints and their live state;
  - every event as it happens, one line each: time, device, event type and the event's data;
  - the latest receipt image of each printer.
- **What the page can do:** set a weight (stable or moving), zero and tare, scan, set and clear each printer fault, and close the drawer. It performs each action through the existing `/api/v1` endpoints and shows an error's `message` and `fix` exactly as the API returns them.
- **Keyboard scans guard against typing into the page itself.** For a keyboard scanner the simulator types, the page counts down itself and requests the scan only if the page has lost focus by the end, as `emupos scan` does for its terminal. Otherwise the barcode and its Enter would be typed into the page's own scan field. The page offers no scan for a `typed_by: client` scanner: a browser cannot type into another window, and `emupos scan` is how those scans are made.
- **The browser-request guard accepts the page's own origin, and only while `--ui` is on.** A request carrying `Origin` is accepted when that `Origin` is exactly `http://` followed by the request's `Host` header, *and* that `Host` names `127.0.0.1`, `localhost` or `[::1]`. Every other request with an `Origin` header is still refused with `browser_request_refused`. The loopback requirement holds even when `api.host` is not a loopback address, so DNS rebinding stays refused in the Docker configuration (`api.host: 0.0.0.0`).
- **Every HTTP response forbids framing and MIME sniffing** (`Content-Security-Policy: frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`), with or without `--ui`. The page's own response also carries a `default-src 'self'` policy.
- **Device data is untrusted, so it is shown as text only.** Receipt text, scan data, unknown command bytes and client addresses come from whatever connects to a device port. The page never inserts them as HTML, and shows receipts as the PNG the API renders.
- **Startup names the page.** With `--ui`, the startup summary prints the page URL next to the API URL. `GET /` without `--ui` still answers 404 `not_found`, with a fix naming `--ui`.
- **Documentation:**
  - `SECURITY.md`: the same-origin exception, what it relies on, and that Swagger's "Try it out" can write while `--ui` is on.
  - `docs/automation.md`: its "Security: local only, no web pages" section.
  - `README.md` and `docs/README.md`: the "Two sides" section.
  - `docs/docker.md` and the regenerated `docs/cli.md`.

## Non-goals

- **A page that works from another machine.** Opened through a non-loopback address, the page loads but cannot write or receive events. Remote control stays with the CLI and scripts.
- **Authentication, tokens or sessions.** The same-origin check is the whole protection, and the loopback-only rule is what makes it enough.
- **A page a POS uses.** The page is an operator tool. A POS still reaches emupos only through the device protocols.
- **The CLI's readable event summaries.** The page shows each event's type and raw data. Matching the wording of `emupos run` would mean copying it into the page or adding a field to every event, and neither is part of this change.
- **Controlling the simulator.** Starting, stopping and reloading the configuration stay with `emupos run`.
- **Changing the Swagger UI.** It stays where it is. With `--ui` on, its "Try it out" writes start working, and `SECURITY.md` says so.
- **Turning the page on in the published Docker image.** The image's default command is unchanged.

## Capabilities

### New Capabilities

- `control-page`: the page served by `emupos run --ui`. What it shows, which actions it offers, how keyboard scans avoid typing into the page, how it renders untrusted device data, and its response headers.

### Modified Capabilities

- `control-api`: "Protection against browser-originated requests" gains the same-origin exception while the control page is enabled, and the framing and sniffing headers on every response.
- `cli`: "Run command" gains `--ui` and prints the page URL at startup.

## Impact

- `src/emupos/api/guard.py`: the same-origin exception and the two response headers.
- `src/emupos/api/app.py`: `create_app` gains a `ui` switch that mounts the page routes and passes it to the guard.
- New `src/emupos/api/page/` (`index.html`, `page.js`, `page.css`), served from a fixed list of files, and a route module for `/`.
- `src/emupos/daemon/server.py` and `src/emupos/cli/run.py`: the `--ui` flag reaching `create_app`, and the URL in the startup summary.
- `src/emupos/api/test_api.py` (the guard and the page routes), `src/emupos/cli/test_commands.py` or beside it (the flag and the URL), and `.github/scripts/smoke_test.py` (the page is served from the installed wheel).
- `SECURITY.md`, `README.md`, `docs/README.md`, `docs/automation.md`, `docs/docker.md`, `docs/cli.md`.
- **Dependencies:** none. The page is plain HTML, CSS and JavaScript with no build step. It loads nothing from outside the package and works offline.
- **Compatibility:** without `--ui`, every request the API refuses today is still refused. The only difference is the two added response headers. `/api/v1` gains no endpoint, field or event, so `scripts/check_api_compat.py` is unaffected. A `feat` commit.
