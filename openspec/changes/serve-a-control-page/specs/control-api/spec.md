## MODIFIED Requirements

### Requirement: Protection against browser-originated requests

Because the API has no authentication and can type keystrokes into the focused window, the simulator SHALL refuse requests that a web page could send from the user's browser. It SHALL respond with status 403 and error code `browser_request_refused` to any request, including a WebSocket upgrade, that carries an `Origin` header, with one exception for the control page:

- while `emupos run` serves the control page (`--ui`), a request SHALL NOT be refused for its `Origin` when that `Origin` equals `http://` followed by the request's `Host` header, compared case-insensitively, *and* the host name in that `Host` is `127.0.0.1`, `localhost` or `[::1]`;
- this exception SHALL apply whatever `api.host` is;
- while it is available, the `fix` of a `browser_request_refused` error SHALL tell the user to open the control page through `127.0.0.1`, `localhost` or `[::1]`.

A request accepted under this exception SHALL still be subject to every other check in this requirement.

While `api.host` is a loopback address, the simulator SHALL respond with status 403 and error code `invalid_host` to any request whose `Host` header is not `127.0.0.1`, `localhost` or `[::1]`, with or without the port. It SHALL respond with status 415 and error code `unsupported_media_type` to any request with a body whose `Content-Type` is not `application/json`.

Every HTTP response SHALL carry the header `X-Content-Type-Options: nosniff` and a `Content-Security-Policy` header that includes `frame-ancestors 'none'`, whether or not the control page is served.

#### Scenario: Request from a web page

- **WHEN** a client sends `POST /api/v1/devices/lane1/scans` with the header `Origin: https://example.com`
- **THEN** the response status is 403 with error code `browser_request_refused`
- **AND** no scan is accepted

#### Scenario: DNS rebinding attempt

- **GIVEN** `api.host` is `127.0.0.1`
- **WHEN** a client sends `GET /api/v1/devices` with the header `Host: attacker.example:8765`
- **THEN** the response status is 403 with error code `invalid_host`

#### Scenario: Form-encoded body

- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with `Content-Type: application/x-www-form-urlencoded`
- **THEN** the response status is 415 with error code `unsupported_media_type`
- **AND** the weight is unchanged

#### Scenario: Command-line and CI clients are unaffected

- **WHEN** `emupos devices` or a script using a plain HTTP client sends `GET /api/v1/devices` to `127.0.0.1:8765` without an `Origin` header
- **THEN** the response status is 200

#### Scenario: Request from the control page

- **GIVEN** `emupos run --ui` with the default `api` settings
- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with body `{ "grams": 500 }`, `Origin: http://127.0.0.1:8765` and `Host: 127.0.0.1:8765`
- **THEN** the response status is 204 and `deli` shows 500 grams

#### Scenario: Event stream from the control page

- **GIVEN** `emupos run --ui` with the default `api` settings
- **WHEN** a client opens `/api/v1/events` with `Origin: http://localhost:8765` and `Host: localhost:8765`
- **THEN** the WebSocket upgrade is accepted

#### Scenario: Same origin without the control page

- **GIVEN** `emupos run` without `--ui`
- **WHEN** a client sends `PUT /api/v1/devices/deli/weight` with `Origin: http://127.0.0.1:8765` and `Host: 127.0.0.1:8765`
- **THEN** the response status is 403 with error code `browser_request_refused`

#### Scenario: Another local origin while the control page is served

- **GIVEN** `emupos run --ui` with the default `api` settings
- **WHEN** a client sends `POST /api/v1/devices/deli/tare` with `Origin: http://localhost:8069` and `Host: 127.0.0.1:8765`
- **THEN** the response status is 403 with error code `browser_request_refused`
- **AND** the `fix` names `127.0.0.1`, `localhost` and `[::1]`

#### Scenario: DNS rebinding on a wildcard address

- **GIVEN** `emupos run --ui` with `api: { host: 0.0.0.0, port: 8765 }`
- **WHEN** a client sends `POST /api/v1/devices/deli/tare` with `Origin: http://attacker.example:8765` and `Host: attacker.example:8765`
- **THEN** the response status is 403 with error code `browser_request_refused`

#### Scenario: Responses forbid framing and sniffing

- **WHEN** a client requests `GET /api/v1/health`, with or without `--ui`
- **THEN** the response carries `X-Content-Type-Options: nosniff` and a `Content-Security-Policy` that includes `frame-ancestors 'none'`
