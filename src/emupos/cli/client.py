"""A small client for the control API (control-api spec), used by commands that act on devices.

It never sends an `Origin` header (the API refuses those) and never goes through a proxy from the
environment: the API is a local service.
"""

import contextlib
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Generator
from typing import Annotated, Any

import typer

from emupos.cli.output import CliError

DEFAULT_API = "http://127.0.0.1:8765"
TIMEOUT_SECONDS = 10

type Json = Any  # a decoded JSON document from the API
DeviceOption = Annotated[
    str | None,
    typer.Option(
        "--device", metavar="ID", help="Device id. Optional when only one device of the type runs."
    ),
]
type ReceiveEvent = Callable[[float], dict[str, Any] | None]

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SimulatorUnreachableError(CliError):
    def __init__(self, url: str) -> None:
        super().__init__(
            f"cannot reach the emupos simulator at {url}",
            "start the simulator with `emupos run`, or point --api or EMUPOS_API at it",
            code="simulator_unreachable",
            exit_code=3,
        )
        self.url = url


class ApiRequestError(CliError):
    def __init__(self, status: int, code: str, message: str, fix: str | None) -> None:
        super().__init__(message, fix, code=code, exit_code=1)
        self.status = status


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get(self, path: str) -> Json:
        return json.loads(self.send("GET", path))

    def post(self, path: str, body: dict[str, object] | None = None) -> Json:
        answer = self.send("POST", path, body)
        return json.loads(answer) if answer else None

    def send(self, method: str, path: str, body: dict[str, object] | None = None) -> bytes:
        """Send one request to `/api/v1<path>` and return the response body."""
        data = None if body is None else json.dumps(body).encode()
        url = f"{self.base_url}/api/v1{path}"  # base_url is http(s): checked by --api (app.py)
        request = urllib.request.Request(url, data, method=method)  # noqa: S310
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise _api_error(error) from None
        except (OSError, http.client.HTTPException):
            raise SimulatorUnreachableError(self.base_url) from None

    @contextlib.contextmanager
    def events(self) -> Generator[ReceiveEvent]:
        """Subscribe to `/api/v1/events`; yields `receive(timeout)`, which returns None on timeout."""
        from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
        from websockets.sync.client import connect

        url = "ws" + self.base_url.removeprefix("http") + "/api/v1/events"
        try:
            connection = connect(url, proxy=None, open_timeout=TIMEOUT_SECONDS)
        except (OSError, InvalidHandshake, InvalidURI):
            raise SimulatorUnreachableError(self.base_url) from None

        def receive(timeout: float) -> dict[str, Any] | None:
            try:
                return json.loads(connection.recv(timeout))
            except TimeoutError:
                return None
            except ConnectionClosed:
                raise CliError(
                    "the simulator closed its event stream",
                    "check the `emupos run` output",
                ) from None

        with connection:
            yield receive


def api(ctx: typer.Context) -> Client:
    """The client for the API address chosen with --api or EMUPOS_API (see app.py)."""
    return Client(str(ctx.find_root().obj))


def device_path(device_id: str, *rest: str) -> str:
    """`/devices/<id>/...` with every segment escaped, so an id can never change the path."""
    return "/".join(
        ["/devices", *(urllib.parse.quote(part, safe="") for part in (device_id, *rest))]
    )


def pick_device(client: Client, kind: str, device_id: str | None) -> str:
    """The device given with --device, or the only running device of `kind` (cli spec, "Device selection")."""
    if device_id is not None:
        return device_id
    candidates = [device["id"] for device in client.get("/devices") if device["type"] == kind]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise CliError(
            f"the running simulator has no {kind}",
            f"add a {kind} to emupos.yaml and restart `emupos run`",
            code="no_device",
            exit_code=2,
        )
    raise CliError(
        f"the running simulator has several {kind}s: {', '.join(candidates)}",
        f"choose one with --device, e.g. --device {candidates[0]}",
        code="ambiguous_device",
        exit_code=2,
    )


def _api_error(error: urllib.error.HTTPError) -> ApiRequestError:
    try:
        detail = json.loads(error.read())["error"]
        return ApiRequestError(error.code, detail["code"], detail["message"], detail["fix"])
    except (ValueError, KeyError, TypeError):
        return ApiRequestError(
            error.code,
            "http_error",
            f"{error.url} answered with HTTP status {error.code}",
            "check that --api or EMUPOS_API points at an emupos simulator",
        )
