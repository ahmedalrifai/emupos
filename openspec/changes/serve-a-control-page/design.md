## Context

The control API is unauthenticated, can type keystrokes into the focused window, and listens on a port any web page in the user's browser can reach. `BrowserRequestGuard` (`src/emupos/api/guard.py`) is its protection against those pages. It refuses:

- **any request with an `Origin` header**, because browsers attach one to cross-site fetches and WebSocket upgrades and command-line tools never do;
- **any request whose `Host` is not loopback**, while `api.host` is loopback (DNS rebinding);
- **any body that is not JSON** (HTML form posts).

A page the API serves itself falls foul of the first rule. Browsers also attach `Origin` to *same-origin* requests whose method is not `GET` or `HEAD`, and to every WebSocket upgrade. Checked in Chromium against 0.2.0, from a page at `http://127.0.0.1:<port>/api/v1/docs`:

```
  fetch GET  /api/v1/devices            ──▶ 200             (no Origin sent)
  fetch PUT  /api/v1/devices/x/weight   ──▶ 403 browser_request_refused
  fetch POST /api/v1/devices/x/tare     ──▶ 403 browser_request_refused
  new WebSocket(ws://…/api/v1/events)   ──▶ refused
  <img src=/api/v1/…/image>             ──▶ 200             (no Origin sent)
```

Other facts the design leans on:

- **`api.host` is `0.0.0.0` in the Docker image** (`docker/emupos.yaml`), so `check_host` is off there. The documented run publishes to the host's loopback with `-p 127.0.0.1:8765:8765`, and the host-side port may differ from `api.port`.
- **Events are not replayed.** A subscriber sees only events emitted after it connected ("Event stream" in the control-api spec).
- **Settling publishes `scale.weight.changed`** (`src/emupos/scale/scale.py`). Every change of device state is therefore followed by an event for that device.
- **`emupos scan` already runs a keyboard scan's countdown locally** and cancels when its own terminal still has focus at the end, then posts `countdown_seconds: 0` (`src/emupos/cli/actions.py`).
- **A `typed_by: client` scan is only planned by the server.** The requester types the keys. An abandoned scan frees the scanner only at its `expires_at`.
- **FastAPI serves the Swagger UI at `/api/v1/docs`** from `cdn.jsdelivr.net`, pinned to a major version and without subresource integrity.

## Goals / Non-Goals

**Goals:**

- Every physical action of the CLI is one click away on a page that updates live, for a developer with the POS in the next window.
- Without `--ui`, the API refuses exactly the requests it refuses today.
- With `--ui`, the page's own requests are accepted and every other request carrying an `Origin` is still refused, including DNS rebinding with `api.host: 0.0.0.0`.
- A malicious print job, scan or client cannot run script in the page's origin.
- No dependency, no build step, nothing fetched from outside the package.

**Non-Goals:**

- Writing from a page opened through a non-loopback address.
- Authentication of any kind.
- The CLI's readable event wording on the page.
- The page's visual design. This change fixes behaviour; the layout is settled separately before `page.css` is written.

## Decisions

### D1. One switch, `emupos run --ui`, turns on both the page and the exception

The page is useless without the exception, and the exception is pure risk without the page, so they share a single switch. `create_app(simulator, ui=…)` mounts the page routes and constructs the guard with `allow_page_origin=ui`.

A flag rather than a configuration key:

- `--demo` has no configuration file, and a demo is the first place the page is used;
- whether to serve a page is a decision about this run, not about the devices a configuration describes.

A key could be added later if a need appears. Having both now would mean two ways to say one thing.

Always-on was rejected. Issue #23 asks for the page to be off by default if it adds any risk to `emupos run`, and the exception does.

### D2. The accepted origin is the request's own `Host`, and only a loopback one

```
  Origin present?
    no  ──▶ unchanged checks (Host, JSON body)
    yes ──▶ allow_page_origin
            and Origin == "http://" + Host          (case-insensitive)
            and host name of Host ∈ {127.0.0.1, localhost, [::1]} ?
              yes ──▶ unchanged checks (Host, JSON body)
              no  ──▶ 403 browser_request_refused
```

| Caller | `Origin` | `Host` | Result with `--ui` |
|---|---|---|---|
| CLI, curl, CI | none | `127.0.0.1:8765` | allowed, as today |
| The page, opened at `127.0.0.1:8765` | `http://127.0.0.1:8765` | `127.0.0.1:8765` | allowed |
| A page on another site | `https://evil.example` | `127.0.0.1:8765` | refused |
| A POS dev server on another loopback port | `http://localhost:8069` | `127.0.0.1:8765` | refused |
| DNS rebinding, `api.host: 0.0.0.0` | `http://attacker.example:8765` | `attacker.example:8765` | refused: `Host` is not loopback |
| Docker, `-p 127.0.0.1:18765:8765` | `http://127.0.0.1:18765` | `127.0.0.1:18765` | allowed |
| Sandboxed frame or `file://` page | `null` | `127.0.0.1:8765` | refused |
| Opened through a LAN address | `http://192.168.1.5:8765` | `192.168.1.5:8765` | refused: the page loads but is read-only |

Comparing with `Host`, not with the configured address, is what makes the Docker row work. `api.host` there is `0.0.0.0`, which is no origin at all, and the port the browser uses is whatever `-p` maps.

The loopback condition is not a duplicate of `check_host`. `check_host` is off exactly when `api.host` is not loopback, which is the Docker case. Without this condition a rebinding page, whose `Origin` and `Host` agree with each other, would pass there.

Alternatives considered:

- **Compare with `api.host:api.port`.** Breaks with any port mapping, and means nothing for a wildcard address.
- **A per-run token in the page URL.** For this threat model it adds nothing over the same-origin check: no other page can share the page's scheme, host and port. It would also add plumbing, since a browser cannot set headers on a WebSocket.
- **`Sec-Fetch-Site: same-origin`.** Safari sends it only from 16.4. `Origin` is sent by every browser.

While `--ui` is on, the refusal's `fix` tells the user to open the page through `127.0.0.1`, `localhost` or `[::1]`. That is the one refusal the user can act on.

### D3. Two headers on every response, with or without `--ui`

Once the page's requests are accepted, a page on another site that frames it gets clicks sent from the accepted origin. Framing is how the same-origin check would be bypassed, so:

- **`Content-Security-Policy: frame-ancestors 'none'`** on every HTTP response. The page is not the only framing target: while `--ui` is on, the Swagger UI's "Try it out → Execute" writes too.
- **`X-Content-Type-Options: nosniff`** on every HTTP response. `/receipts/{id}/text` serves bytes chosen by whatever printed to the printer, and must never be read as HTML in the accepted origin.

The guard adds both by wrapping `send` on `http.response.start`. It leaves an existing `Content-Security-Policy` alone, because the page's own policy already includes `frame-ancestors 'none'`.

These headers are added whether or not `--ui` is on. They make the default stricter, not looser, and one code path is simpler than two.

### D4. The page is three packaged files behind three fixed routes

`src/emupos/api/page/` holds `index.html`, `page.js` and `page.css`. `api/routes/page.py` serves them at `/`, `/page.js` and `/page.css`:

- each route has a hard-coded file name and content type;
- `create_app` reads the files once when `--ui` is on, so a wheel missing them fails at startup rather than on the first request;
- the routes are `include_in_schema=False` and outside `/api/v1`, so neither the OpenAPI document nor `scripts/check_api_compat.py` sees them. The page is not part of the API contract and can change in any release.

The page's response carries:

```
Content-Security-Policy: default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

Alternatives considered:

- **`StaticFiles`.** A directory-backed mount brings path handling to reason about for three files. It also sets no per-response headers, so another middleware would be needed.
- **One self-contained HTML file.** Inline script and style would need `'unsafe-inline'` or hashes kept in step with every edit.

Without `--ui`, `GET /` answers 404 `not_found` with the fix "start the simulator with `emupos run --ui`". Every other unknown path keeps today's fix.

### D5. Live state is re-fetched, not derived from events

```
  load ──▶ open WS /api/v1/events ──▶ on open: GET /api/v1/devices   (full state)
  event for device X ──▶ GET /api/v1/devices/X  (at most one in flight per device, one queued)
  event printer.job.completed ──▶ receipt <img> src = …/receipts/{receipt_id}/image
  WS closed ──▶ show "not connected", retry every 2 s; on reopen GET /api/v1/devices again
```

Events carry partial data (`drawer.opened` has a pin, not a state), and keeping state from them would repeat the devices' logic in JavaScript. Re-fetching the one device an event names is always right, and the settle event keeps the scale's `stable` current.

The socket opens *before* the full `GET`. Events are not replayed, so fetching first would lose any change between the fetch and the subscription. Subscribing first means the fetched state already includes everything earlier.

The event list keeps the last 500 lines. It shows time, device, type and the data's `key=value` pairs, which is the fallback `EventLines.summary` already uses.

### D6. Scans behave like `emupos scan`

| Scanner | What the page does |
|---|---|
| keyboard, `typed_by: server` | counts down locally (3 s); if the page still has focus at the end, cancels and says to click the POS window during the countdown; otherwise `POST …/scans` with `countdown_seconds: 0` |
| serial | `POST …/scans` with `countdown_seconds: 0` at once: no window receives it |
| keyboard, `typed_by: client` | no scan control; says that `emupos scan` types these scans where the POS window is |

The focus check matters more on the page than in the terminal. The window that would receive the keystrokes is the page, and its scan field would get the barcode followed by Enter, which submits another scan.

The server's countdown cannot be cancelled once requested, which is why the page counts down itself. The remaining time is computed from the clock, not from counting ticks, because a background tab runs timers at most once a second.

The page does not repeat the scanner's validation rules. An invalid scan is refused with the API's 422 `message` and `fix`, after the countdown rather than before it as in the CLI. A checkbox requests exact-character delivery (`unicode: true`), the page's form of `--unicode`.

### D7. Device data only ever reaches the page as text

Receipt text, scan data, `printer.command.unknown` bytes and client addresses all come from whatever connects to a device port. If any of it were inserted as HTML, a print job could run script in the accepted origin and type keystrokes through `POST /scans`.

So:

- `page.js` builds the page with `textContent` and `createElement`, and never uses `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write`. A test reads `page.js` and fails on any of those names.
- Receipts are shown as the PNG the API renders.
- The CSP's `default-src 'self'` is the second line of defence: injected inline script does not run, and nothing can be sent elsewhere.
- Device data can be Arabic. Every element holding it gets `dir="auto"`, so right-to-left text does not reorder the columns around it.

### D8. Startup prints where the page can write

With `--ui`, the startup summary adds `control page http://<address>:<port>/`:

- **loopback `api.host`:** that address;
- **wildcard `0.0.0.0` or `::`:** `127.0.0.1`, the only kind of address through which the page can write;
- **specific non-loopback address:** that address, plus a warning that a page opened through it can show devices but not act on them.

## Risks / Trade-offs

- **Any page on the accepted origin can now write, including the Swagger UI and the jsdelivr scripts it loads.** → Exposure needs `--ui` on, `/api/v1/docs` open and a compromised CDN. `SECURITY.md` states it. The Swagger UI is left unchanged, as decided for this change.
- **A bug in `page.js` becomes keystroke injection.** → D7's text-only rule and the test that enforces it, plus the CSP.
- **`default-src 'self'` might not cover `ws:` in an older browser.** CSP Level 3 matches `'self'` against the same host and port over `ws:`. → Check the event stream under the policy in current Chrome, Firefox and Safari. If one refuses, add an explicit `connect-src` built from the validated `Host`.
- **`document.hasFocus()` is not a perfect signal.** For example, it is false while DevTools has focus. → The failure is a scan typed into whatever window has focus, which is the CLI's behaviour whenever focus cannot be determined.
- **An invalid scan is refused only after the countdown.** → Acceptable for an exploratory tool. The API's message and fix say what to change.
- **The page is read-only through a LAN address.** → Intended (proposal non-goals). The startup warning and the refusal's fix say how to open it.

## Migration Plan

None. `--ui` is off by default and nothing about `/api/v1` changes. Rolling back means removing the flag, the routes and the exception. The two response headers can stay.

## Open Questions

- The page's layout and visual design, settled before `page.css` and the markup are written. The behaviour above does not depend on them.
