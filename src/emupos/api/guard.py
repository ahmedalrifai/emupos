"""Refuse requests a web page could send (control-api spec, "Protection against browser-originated requests").

The API has no authentication and can type keystrokes, and a localhost port is reachable from
any web page open in the user's browser. Browsers always attach `Origin` to cross-site fetches
and WebSocket upgrades; command-line tools and test scripts never do. Checking `Host` defeats
DNS rebinding, and accepting only JSON bodies blocks HTML form posts.
"""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})


class BrowserRequestGuard:
    def __init__(self, app: ASGIApp, *, check_host: bool) -> None:
        self.app = app
        self.check_host = check_host  # only while the API is bound to a loopback address

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
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

    def _refusal(self, scope: Scope, headers: dict[str, str]) -> tuple[int, str, str] | None:
        if "origin" in headers:
            return (
                403,
                "browser_request_refused",
                "requests from web pages are refused; call the API from a script or the emupos CLI",
            )
        if self.check_host and _host_name(headers.get("host", "")) not in LOOPBACK_HOSTS:
            return 403, "invalid_host", "the Host header must be 127.0.0.1, localhost or [::1]"
        has_body = headers.get("content-length", "0") != "0" or "transfer-encoding" in headers
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if scope["type"] == "http" and has_body and content_type != "application/json":
            return (
                415,
                "unsupported_media_type",
                "request bodies must be JSON (Content-Type: application/json)",
            )
        return None


def _host_name(host: str) -> str:
    if host.startswith("["):  # [::1]:8765
        return host[: host.find("]") + 1]
    return host.rsplit(":", 1)[0] if ":" in host else host


def _body(code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "fix": None}}).encode()


async def _send_json(send: Send, status: int, code: str, message: str) -> None:
    body = _body(code, message)
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _deny_websocket(scope: Scope, send: Send, status: int, code: str, message: str) -> None:
    if "websocket.http.response" in scope.get("extensions", {}):
        body = _body(code, message)
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
