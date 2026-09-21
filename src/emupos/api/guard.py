"""Refuse requests a web page could send (control-api spec, "Protection against browser-originated requests").

The API has no authentication and can type keystrokes, and a localhost port is reachable from
any web page open in the user's browser. Browsers always attach `Origin` to cross-site fetches
and WebSocket upgrades; command-line tools and test scripts never do. Checking `Host` defeats
DNS rebinding, and accepting only JSON bodies blocks HTML form posts.

While `emupos run --ui` serves the control page, the page's own requests carry its origin; they
are accepted when that origin is `http://` + the request's own loopback `Host` (design D2). Every
response forbids framing, which would otherwise let another site click on that page (design D3).
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
PAGE_FIX = (
    "open the control page through 127.0.0.1, localhost or [::1] on the machine running emupos"
)


class BrowserRequestGuard:
    def __init__(self, app: ASGIApp, *, check_host: bool, allow_page_origin: bool = False) -> None:
        self.app = app
        self.check_host = check_host  # only while the API is bound to a loopback address
        self.allow_page_origin = allow_page_origin  # only while the control page is served

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        send = _with_protective_headers(send)
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope["headers"]
        }
        refusal = self._refusal(scope, headers)
        if refusal is None:
            await self.app(scope, receive, send)
        elif scope["type"] == "http":
            await _send_json(send, *refusal)
        else:
            await _deny_websocket(scope, send, *refusal)

    def _refusal(
        self, scope: Scope, headers: dict[str, str]
    ) -> tuple[int, str, str, str | None] | None:
        origin = headers.get("origin")
        if origin is not None and not (
            self.allow_page_origin and _is_page_origin(origin, headers.get("host", ""))
        ):
            return (
                403,
                "browser_request_refused",
                "requests from web pages are refused; call the API from a script or the emupos CLI",
                PAGE_FIX if self.allow_page_origin else None,
            )
        if self.check_host and _host_name(headers.get("host", "")) not in LOOPBACK_HOSTS:
            return (
                403,
                "invalid_host",
                "the Host header must be 127.0.0.1, localhost or [::1]",
                None,
            )
        has_body = headers.get("content-length", "0") != "0" or "transfer-encoding" in headers
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if scope["type"] == "http" and has_body and content_type != "application/json":
            return (
                415,
                "unsupported_media_type",
                "request bodies must be JSON (Content-Type: application/json)",
                None,
            )
        return None


def _is_page_origin(origin: str, host: str) -> bool:
    """The control page's own origin: `http://` + this request's Host, and that Host is loopback.

    Requiring loopback even when `check_host` is off keeps DNS rebinding out while the API listens
    on 0.0.0.0, where a rebinding page's Origin and Host agree with each other.
    """
    host = host.lower()
    return origin.lower() == f"http://{host}" and _host_name(host) in LOOPBACK_HOSTS


def _host_name(host: str) -> str:
    if host.startswith("["):  # [::1]:8765
        return host[: host.find("]") + 1]
    return host.rsplit(":", 1)[0] if ":" in host else host


def _with_protective_headers(send: Send) -> Send:
    async def sending(message: Message) -> None:
        if message["type"] in {"http.response.start", "websocket.http.response.start"}:
            headers = list(message.get("headers", []))
            names = {name.lower() for name, _ in headers}
            headers.append((b"x-content-type-options", b"nosniff"))
            if b"content-security-policy" not in names:  # the page's own policy forbids framing too
                headers.append((b"content-security-policy", b"frame-ancestors 'none'"))
            message = {**message, "headers": headers}
        await send(message)

    return sending


def _body(code: str, message: str, fix: str | None) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "fix": fix}}).encode()


async def _send_json(send: Send, status: int, code: str, message: str, fix: str | None) -> None:
    body = _body(code, message, fix)
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _deny_websocket(
    scope: Scope, send: Send, status: int, code: str, message: str, fix: str | None
) -> None:
    if "websocket.http.response" in scope.get("extensions", {}):
        body = _body(code, message, fix)
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        await send({"type": "websocket.http.response.start", "status": status, "headers": headers})
        await send({"type": "websocket.http.response.body", "body": body})
    else:
        await send(
            {"type": "websocket.close", "code": 1008}
        )  # servers answer 403 to a refused upgrade
