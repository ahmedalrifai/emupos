# Security policy

## Supported versions

emupos is before 1.0. Security fixes are made in the latest release only.

| Version | Supported |
|---|---|
| latest 0.x release | ✅ |
| older releases | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. You will get a response within 7 days. Once a fix is released, the report is published as a GitHub security advisory, crediting you unless you prefer otherwise.

## Threat model of the local API

`emupos run` serves a control API (by default `http://127.0.0.1:8765`) that can change device state and **type keystrokes into the focused window** when a keyboard-mode scanner is configured. Its protections:

- **Local only by default.** The API binds to `127.0.0.1`. Binding to another address requires changing `api.host` and prints a warning, because the API has no authentication.
- **No requests from web pages.** Any request carrying an `Origin` header is refused, so a website open in your browser cannot call the API. The one exception is emupos's own control page: while `emupos run --ui` serves it, a request is accepted when its `Origin` is exactly `http://` followed by its own `Host`, and that `Host` is `127.0.0.1`, `localhost` or `[::1]`. No other site can send that origin, and DNS rebinding cannot produce it, because the `Host` must be a loopback name even when the API listens on `0.0.0.0`.
- **No framing.** Every response forbids being framed (`Content-Security-Policy: frame-ancestors 'none'`) and MIME sniffing (`X-Content-Type-Options: nosniff`), so another site cannot put the control page in a frame and click on it, and receipt text is never read as HTML.
- **Device data is text.** Receipt text, scan data and client addresses come from whatever connects to a device port. The control page shows them as text only, never as HTML, and loads nothing from another origin.
- **What `--ui` opens.** While the control page is served, any page on the API's own address can call the API. Besides the control page, that is the interactive API documentation at `/api/v1/docs`, which loads its scripts from cdn.jsdelivr.net: its "Try it out" can then change device state. Leave `--ui` off when you do not use the page.
- **No DNS rebinding.** While bound to a loopback address, requests whose `Host` header is not `127.0.0.1`, `localhost` or `[::1]` are refused.
- **JSON bodies only.** Requests with a non-JSON body are refused, which blocks HTML form submissions.
- **Configuration is plain data.** `emupos.yaml` and profile files are parsed with a safe YAML loader; object tags are rejected and never executed.

emupos is a development and testing tool. Do not expose its API to untrusted networks, and do not run it on machines that handle real payment card data.

In scope: bypasses of the protections above, code execution through configuration or device input, and path traversal through configuration values. Out of scope: behaviour that requires already having local access as the user running emupos.
