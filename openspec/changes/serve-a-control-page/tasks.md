## 1. Browser-request guard

- [x] 1.1 In `api/guard.py`, add the keyword argument `allow_page_origin: bool` to `BrowserRequestGuard`. When it is true, a request passes the `Origin` check if its `Origin` equals `http://` + its `Host` (case-insensitive) and `_host_name(Host)` is in `LOOPBACK_HOSTS`, whatever `check_host` is (design D2). The `Host` and JSON-body checks still run afterwards.
- [x] 1.2 While `allow_page_origin` is true, give the `browser_request_refused` error a `fix` telling the user to open the control page through `127.0.0.1`, `localhost` or `[::1]`. It stays `null` otherwise.
- [x] 1.3 Wrap `send` so every `http.response.start` carries `X-Content-Type-Options: nosniff`, plus `Content-Security-Policy: frame-ancestors 'none'` unless the response already has a `Content-Security-Policy` (design D3). Do this whether or not the page is enabled.
- [x] 1.4 In `api/test_api.py`, test every row of the D2 table, both over HTTP and over a WebSocket upgrade:
  - own origin allowed with the page and refused without it;
  - another loopback port refused;
  - rebinding refused with `api.host: 0.0.0.0`;
  - `Origin: null` refused;
  - a mixed-case origin allowed.
- [x] 1.5 In the same file, test the refusal's `fix` with and without the page, and the two headers on `GET /api/v1/health` with and without the page. Confirm every existing guard test passes unchanged.

## 2. Serving the page

- [x] 2.1 Create `src/emupos/api/page/` with placeholder `index.html`, `page.js` and `page.css`, so the routes and tests can land before the page itself.
- [x] 2.2 Add `api/routes/page.py` with three fixed routes, each `include_in_schema=False` and each with its own content type, serving bytes it is given (design D4):
  - `GET /` → `index.html`;
  - `GET /page.js` → `page.js`;
  - `GET /page.css` → `page.css`.

  The HTML response carries `Content-Security-Policy: default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
- [x] 2.3 Change `create_app(simulator)` to `create_app(simulator, *, ui: bool = False)`. With `ui`, read the three files once through `importlib.resources`, mount the page routes and pass `allow_page_origin=True` to the guard. Without `ui`, `GET /` answers 404 `not_found` with the fix "start the simulator with `emupos run --ui`".
- [x] 2.4 In `api/test_api.py`, test:
  - status, content type and CSP of each page route with `ui`;
  - the 404 and its fix without `ui`;
  - that `GET /api/v1/openapi.json` lists no path outside `/api/v1`.
- [x] 2.5 Add a test that reads the packaged page files. It fails if `page.js` contains `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write` (design D7), or if any of the three files contains an `http://` or `https://` URL.

## 3. CLI and server

- [x] 3.1 In `cli/run.py`, add the `--ui` option (help: "Also serve the control page, a web page for the physical actions."). Pass it through `daemon/server.serve` to `create_app`.
- [x] 3.2 In `_started`, print `control page http://<address>:<port>/` after the API URL when `--ui` is on. Use `127.0.0.1` for `0.0.0.0` and `::`. For any other non-loopback address, add a `warning` that a page opened through it can show the devices but cannot act on them (design D8).
- [x] 3.3 Beside the existing `emupos run` tests, test the three URL cases and the warning, and that `--ui` combines with `--demo` and with `--config`.
- [x] 3.4 Regenerate `docs/cli.md` with the command in `CONTRIBUTING.md`.

## 4. The page

- [x] 4.1 Settle the page's layout and visual design (design, open question) before writing the markup and styles. Record the outcome where the project keeps its design decisions.
- [x] 4.2 Write `index.html` and `page.css` to that layout. Load `page.js` from `/page.js` and nothing from outside the package.
- [x] 4.3 In `page.js`, the connection (design D5):
  - open `/api/v1/events` first, and on open `GET /api/v1/devices`;
  - on an event, re-fetch that device, with at most one request in flight per device and one queued;
  - show a not-connected state, retry every 2 s, and refresh every device on reconnect.
- [x] 4.4 In `page.js`, the devices and the physical actions:
  - scale: weight in grams, stable or moving, plus zero and tare;
  - printer: set and clear each of the four faults, and close the drawer.

  Every refusal shows the API's `message` and `fix`. Build every element with `createElement` and `textContent` (design D7).
- [x] 4.5 In `page.js`, the event list: local time, device id, event type and `key=value` data, keeping the last 500 lines. Put device data in elements with `dir="auto"`.
- [x] 4.6 In `page.js`, the receipts: each printer's `receipts/latest/image`, a "no receipt yet" state when it answers 404, and the image of `receipt_id` when `printer.job.completed` arrives.
- [x] 4.7 In `page.js`, scans per design D6:
  - keyboard scanner the server types: a local countdown computed from the clock; cancel with the "click your POS window" message if `document.hasFocus()` is still true at the end, otherwise post with `countdown_seconds: 0`;
  - serial: post at once;
  - `typed_by: client`: no scan control, and text naming `emupos scan`;
  - an exact-characters checkbox sending `unicode: true`.

## 5. Release smoke test

- [x] 5.1 In `.github/scripts/smoke_test.py`, start the installed wheel's `emupos run --ui` and check that `GET /` and `GET /page.js` answer 200. This catches the page files missing from the wheel.

## 6. Documentation

- [x] 6.1 `SECURITY.md`, threat model of the local API:
  - the same-origin exception exists only with `--ui`, and its `Host` must be loopback;
  - every response forbids framing and sniffing;
  - device data is only ever shown as text;
  - while `--ui` is on, the Swagger UI at `/api/v1/docs`, whose scripts come from `cdn.jsdelivr.net`, can also write.
- [x] 6.2 `README.md` and `docs/README.md`: in "Two sides", the operator side names the control page (`emupos run --ui`) beside the `emupos` commands. The two copies of that section say the same.
- [x] 6.3 `docs/automation.md`, "Security: local only, no web pages":
  - web pages are still refused, except the control page's own requests while `--ui` is on;
  - a browser-based POS on another origin still cannot call the API.
- [x] 6.4 `docs/docker.md`:
  - `docker run -p 127.0.0.1:8765:8765 … emupos run --ui`;
  - the page writes only through the host's loopback address;
  - the page cannot scan for the image's `typed_by: client` scanner, where `emupos scan` does.
- [x] 6.5 `CHANGELOG.md` is generated by release-please: check that the commit message describes the feature as `feat:`.

## 7. Checks

- [x] 7.1 Run the full test suite, the type checker and the linter. Confirm `scripts/check_api_compat.py` passes without `--update`.
- [ ] 7.2 In current Chrome, Firefox and Safari, run `emupos run --demo --ui` and confirm on the page:
  - the event stream connects under the page's CSP (design risk);
  - every action works;
  - a receipt printed to `127.0.0.1:9100` appears without a reload;
  - stopping and restarting `emupos run` shows the not-connected state, then recovers.
- [ ] 7.3 With a keyboard scanner the server types:
  - a scan with the page still focused is cancelled and nothing is typed;
  - clicking TextEdit (or another editor) during the countdown types the barcode there.
- [x] 7.4 With a serial scanner, confirm:
  - a scan of `<img src=x onerror=alert(1)>` shows literally in the event list and runs nothing;
  - a scan of `كود42` shows as one right-to-left run.
- [ ] 7.5 Run the Docker image with `-p 127.0.0.1:18765:8765 … emupos run --ui` and confirm the page acts on the devices at `http://127.0.0.1:18765/`. Opened through the machine's LAN address, the page should show devices but refuse actions, with the fix naming the loopback addresses.
