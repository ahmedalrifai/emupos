"""The control API and the running simulator together: real TCP and pty connections, in process."""

import asyncio
import json
import os
import socket
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import websockets

from emupos.api.app import create_app
from emupos.config import LoadedConfig, parse_config
from emupos.daemon.runtime import StartupError
from emupos.daemon.server import run
from emupos.daemon.simulator import Simulator
from emupos.events import PublishedEvent
from emupos.printer.printer import Printer
from emupos.scale.scale import Scale
from emupos.scanner.scanner import Scanner
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

POSIX = sys.platform != "win32"
BASE_URL = "http://127.0.0.1:8765"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def config(
    tmp_path: Path, printer_port: int, api_port: int = 8765, api_host: str = "127.0.0.1"
) -> LoadedConfig:
    # Link names carry this process's id: the `run` tests publish links in the default directory,
    # where an emupos the developer is running would otherwise own `deli` and refuse to start.
    links = f"test{os.getpid()}"
    serial_devices = f"""
  - {{ id: deli, type: scale, profile: toledo8217-15kg, connections: [ {{ serial: {{ pty: true, link: {links}-deli }} }} ] }}
  - {{ id: lane2, type: scanner, mode: serial, connections: [ {{ serial: {{ pty: true, link: {links}-lane2 }} }} ] }}
"""
    text = f"""
schema: 1
api: {{ host: {api_host}, port: {api_port} }}
devices:
  - {{ id: front, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: {printer_port} }} }} ], job_idle_timeout_ms: 200 }}
  - {{ id: lane1, type: scanner, mode: keyboard, typed_by: client }}
{serial_devices if POSIX else ""}
"""
    return parse_config(text, "test.yaml", tmp_path, sys.platform)


@pytest.fixture
async def simulator(tmp_path: Path) -> AsyncIterator[Simulator]:
    running = Simulator(config(tmp_path, free_port()), link_dir=tmp_path / "links")
    await running.start()
    yield running
    await running.stop()


@pytest.fixture
async def api(simulator: Simulator) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(simulator))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client


@pytest.fixture
async def page_api(simulator: Simulator) -> AsyncIterator[httpx.AsyncClient]:
    """The API as `emupos run --ui` serves it: with the control page and its origin accepted."""
    transport = httpx.ASGITransport(app=create_app(simulator, ui=True))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client


def printer_port(simulator: Simulator) -> int:
    return int(simulator.runtime("front").endpoints[0].endpoint.rsplit(":", 1)[1])


async def print_bytes(simulator: Simulator, data: bytes) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", printer_port(simulator))
    writer.write(data)
    await writer.drain()
    writer.close()
    await writer.wait_closed()
    del reader


def open_serial_client(simulator: Simulator, device_id: str) -> int:
    assert sys.platform != "win32"  # serial tests skip on Windows; this tells the type checker
    import tty

    link = simulator.runtime(device_id).endpoints[0].link_path
    assert link is not None
    fd = os.open(link, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    return fd


async def read_serial(
    fd: int, count: int, timeout: float = 2.0, *, allow_timeout: bool = False
) -> bytes:
    received = b""
    try:
        async with asyncio.timeout(timeout):
            while len(received) < count:
                try:
                    received += os.read(fd, count - len(received))
                except BlockingIOError:
                    await asyncio.sleep(0.01)
    except TimeoutError:
        if not allow_timeout:
            raise
    return received


async def wait_for(predicate: object, timeout: float = 2.0) -> None:
    assert callable(predicate)
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


# --- health, devices, errors ---------------------------------------------------------------


async def test_health_reports_versions(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["api_version"] == 1


async def test_devices_are_listed_with_endpoints_and_state(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    devices = {device["id"]: device for device in (await api.get("/api/v1/devices")).json()}

    assert devices["front"]["type"] == "printer"
    assert devices["front"]["state"] == {"faults": [], "drawer": "closed"}
    assert devices["front"]["connections"][0]["endpoint"] == f"127.0.0.1:{printer_port(simulator)}"
    if POSIX:
        assert devices["deli"]["state"]["capacity_grams"] == 15000
        # `deli` speaks Toledo 8217, which has no unit of measure to report.
        assert devices["deli"]["state"]["unit"] is None
        assert devices["deli"]["connections"][0]["link_path"].endswith(
            f"links/test{os.getpid()}-deli"
        )
        assert devices["lane2"]["profile"] is None


async def test_unknown_device_and_path(api: httpx.AsyncClient) -> None:
    unknown_device = await api.get("/api/v1/devices/nope")
    unknown_path = await api.get("/api/v1/printers")

    assert unknown_device.status_code == 404
    assert unknown_device.json()["error"]["code"] == "device_not_found"
    assert "GET /api/v1/devices" in unknown_device.json()["error"]["fix"]
    assert unknown_path.status_code == 404
    assert unknown_path.json()["error"]["code"] == "not_found"


async def test_openapi_describes_the_endpoints(api: httpx.AsyncClient) -> None:
    paths = (await api.get("/api/v1/openapi.json")).json()["paths"]

    assert "/api/v1/devices/{device_id}/weight" in paths
    assert "/api/v1/barcodes/weighed" in paths


# --- browser-request protection ------------------------------------------------------------


async def test_requests_from_web_pages_are_refused(api: httpx.AsyncClient) -> None:
    response = await api.put(
        "/api/v1/devices/front/faults/paper-out", headers={"Origin": "https://example.com"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "browser_request_refused"
    assert (await api.get("/api/v1/devices/front")).json()["state"]["faults"] == []


async def test_dns_rebinding_host_is_refused(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/devices", headers={"Host": "attacker.example:8765"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invalid_host"


async def test_form_bodies_are_refused(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/api/v1/barcodes/weighed",
        content="layout=weight-21",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


# --- the control page and its origin (control-page spec; design D2, D3, D4) -----------------

PAGE_ORIGIN = {"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"}


async def test_the_page_origin_is_accepted_only_while_the_page_is_served(
    api: httpx.AsyncClient, page_api: httpx.AsyncClient
) -> None:
    refused = await api.put("/api/v1/devices/front/faults/paper-out", headers=PAGE_ORIGIN)
    accepted = await page_api.put("/api/v1/devices/front/faults/paper-out", headers=PAGE_ORIGIN)

    assert refused.status_code == 403
    assert refused.json()["error"] == {
        "code": "browser_request_refused",
        "message": refused.json()["error"]["message"],
        "fix": None,
    }
    assert accepted.status_code == 204
    assert (await page_api.get("/api/v1/devices/front")).json()["state"]["faults"] == ["paper-out"]


@pytest.mark.parametrize(
    ("origin", "host"),
    [
        ("http://localhost:8069", "127.0.0.1:8765"),  # another local web app
        ("https://example.com", "127.0.0.1:8765"),
        ("null", "127.0.0.1:8765"),  # a sandboxed frame or a file:// page
        ("https://127.0.0.1:8765", "127.0.0.1:8765"),  # the API is never served over TLS
    ],
)
async def test_other_origins_stay_refused_while_the_page_is_served(
    page_api: httpx.AsyncClient, origin: str, host: str
) -> None:
    response = await page_api.post(
        "/api/v1/devices/front/drawer/close", headers={"Origin": origin, "Host": host}
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "browser_request_refused"
    assert all(name in error["fix"] for name in ("127.0.0.1", "localhost", "[::1]"))


async def test_the_page_origin_is_compared_case_insensitively(page_api: httpx.AsyncClient) -> None:
    headers = {"Origin": "HTTP://LocalHost:8765", "Host": "localhost:8765"}
    assert (await page_api.get("/api/v1/health", headers=headers)).status_code == 200


async def test_rebinding_is_refused_on_a_wildcard_address(tmp_path: Path) -> None:
    wildcard = Simulator(config(tmp_path, free_port(), api_host="0.0.0.0"), link_dir=tmp_path)  # noqa: S104
    transport = httpx.ASGITransport(app=create_app(wildcard, ui=True))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        rebinding = {"Origin": "http://attacker.example:8765", "Host": "attacker.example:8765"}
        refused = await client.get("/api/v1/health", headers=rebinding)
        mapped = {"Origin": "http://127.0.0.1:18765", "Host": "127.0.0.1:18765"}  # docker -p
        accepted = await client.get("/api/v1/health", headers=mapped)

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "browser_request_refused"
    assert accepted.status_code == 200


@pytest.mark.parametrize("ui", [False, True])
async def test_every_response_forbids_framing_and_sniffing(simulator: Simulator, ui: bool) -> None:
    transport = httpx.ASGITransport(app=create_app(simulator, ui=ui))
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        ok = await client.get("/api/v1/health")
        refused = await client.get("/api/v1/health", headers={"Origin": "https://example.com"})

    for response in (ok, refused):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize(
    ("path", "media_type"),
    [("/", "text/html"), ("/page.js", "text/javascript"), ("/page.css", "text/css")],
)
async def test_the_page_files_are_served_with_their_policy(
    page_api: httpx.AsyncClient, path: str, media_type: str
) -> None:
    response = await page_api.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )


async def test_no_page_without_the_flag(api: httpx.AsyncClient) -> None:
    response = await api.get("/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "emupos run --ui" in response.json()["error"]["fix"]


async def test_the_page_is_not_part_of_the_api_contract(page_api: httpx.AsyncClient) -> None:
    paths = (await page_api.get("/api/v1/openapi.json")).json()["paths"]
    assert all(path.startswith("/api/v1/") for path in paths)


# --- printer -------------------------------------------------------------------------------


async def test_fault_activation_is_idempotent_and_validated(api: httpx.AsyncClient) -> None:
    assert (await api.put("/api/v1/devices/front/faults/paper-out")).status_code == 204
    assert (await api.put("/api/v1/devices/front/faults/paper-out")).status_code == 204
    assert (await api.get("/api/v1/devices/front")).json()["state"]["faults"] == ["paper-out"]
    assert (await api.delete("/api/v1/devices/front/faults/paper-out")).status_code == 204

    unknown = await api.put("/api/v1/devices/front/faults/jammed")

    assert unknown.status_code == 422
    assert "paper-near-end" in unknown.json()["error"]["message"]


async def test_printed_receipt_is_stored_and_announced(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    events: list[PublishedEvent] = []
    simulator.bus.subscribe(events.append)
    assert (await api.get("/api/v1/devices/front/receipts/latest/text")).status_code == 404

    await print_bytes(simulator, bytes.fromhex("1b 40 48 69 0a 1d 56 00"))
    await wait_for(lambda: any(e.event.type == "printer.job.completed" for e in events))

    completed = next(e for e in events if e.event.type == "printer.job.completed")
    receipts = (await api.get("/api/v1/devices/front/receipts")).json()
    image = await api.get("/api/v1/devices/front/receipts/latest/image")
    assert completed.event.data["boundary"] == "cut"
    assert receipts[0]["id"] == completed.event.data["receipt_id"]
    assert (await api.get("/api/v1/devices/front/receipts/latest/text")).text.strip() == "Hi"
    assert image.headers["content-type"] == "image/png"
    assert receipts[0]["width_dots"] == 576


async def test_idle_timeout_is_driven_by_the_daemon_timer(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", printer_port(simulator))
    writer.write(bytes.fromhex("1b 40 48 69 0a"))  # no cut, connection stays open
    await writer.drain()

    store = simulator.runtime("front").receipts
    assert store is not None
    await wait_for(lambda: store.get("front", "latest") is not None)

    assert (await api.get("/api/v1/devices/front/receipts/latest")).json()[
        "boundary"
    ] == "idle-timeout"
    writer.close()
    del reader


async def test_drawer_kick_and_close(api: httpx.AsyncClient, simulator: Simulator) -> None:
    await print_bytes(simulator, bytes.fromhex("1b 70 00 19 fa"))
    printer = simulator.runtime("front").device
    assert isinstance(printer, Printer)
    await wait_for(lambda: printer.state().drawer == "open")

    assert (await api.post("/api/v1/devices/front/drawer/close")).status_code == 204
    assert (await api.post("/api/v1/devices/front/drawer/close")).status_code == 204
    assert (await api.get("/api/v1/devices/front")).json()["state"]["drawer"] == "closed"


async def test_status_query_is_answered_over_tcp(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    await api.put("/api/v1/devices/front/faults/cover-open")
    reader, writer = await asyncio.open_connection("127.0.0.1", printer_port(simulator))
    writer.write(bytes.fromhex("10 04 01"))
    await writer.drain()

    reply = await asyncio.wait_for(reader.readexactly(1), 2)

    assert reply == bytes.fromhex("1a")
    writer.close()


# --- scale and scanner (simulator-created serial ports) --------------------------------------


@pytest.mark.skipif(not POSIX, reason="simulator-created serial ports exist on macOS and Linux")
async def test_weight_set_through_the_api_is_read_over_serial(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    assert (await api.put("/api/v1/devices/deli/weight", json={"grams": 1250})).status_code == 204
    fd = open_serial_client(simulator, "deli")
    try:
        os.write(fd, b"W")
        reply = await read_serial(fd, 8)
    finally:
        os.close(fd)

    assert reply == bytes.fromhex("02 30 31 2e 32 35 30 0d")


@pytest.mark.skipif(not POSIX, reason="simulator-created serial ports exist on macOS and Linux")
async def test_scale_errors(api: httpx.AsyncClient) -> None:
    fractional = await api.put("/api/v1/devices/deli/weight", json={"grams": 1.25})
    wrong_type = await api.put("/api/v1/devices/front/weight", json={"grams": 1250})
    await api.put("/api/v1/devices/deli/weight", json={"grams": 200, "stable": False})
    in_motion = await api.post("/api/v1/devices/deli/tare")

    assert fractional.status_code == 422
    assert "integer" in fractional.json()["error"]["message"]
    assert wrong_type.status_code == 409
    assert wrong_type.json()["error"]["code"] == "wrong_device_type"
    assert in_motion.status_code == 409
    assert in_motion.json()["error"]["code"] == "scale_in_motion"


@pytest.mark.skipif(not POSIX, reason="simulator-created serial ports exist on macOS and Linux")
async def test_serial_scan_is_delivered_after_the_countdown(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    events: list[PublishedEvent] = []
    simulator.bus.subscribe(events.append)
    fd = open_serial_client(simulator, "lane2")
    try:
        accepted = await api.post(
            "/api/v1/devices/lane2/scans", json={"data": "123", "countdown_seconds": 1}
        )
        busy = await api.post("/api/v1/devices/lane2/scans", json={"data": "456"})
        early = await read_serial(fd, 1, timeout=0.5, allow_timeout=True)
        received = await read_serial(fd, 4, timeout=3)
    finally:
        os.close(fd)
    await wait_for(lambda: any(e.event.type == "scanner.scan.delivered" for e in events))

    assert accepted.status_code == 202
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "scan_in_progress"
    assert early == b""  # nothing before the countdown ends
    assert received == bytes.fromhex("31 32 33 0d")
    delivered = next(e for e in events if e.event.type == "scanner.scan.delivered")
    assert delivered.event.data["id"] == accepted.json()["id"]


async def test_weighed_barcode_needs_no_device(api: httpx.AsyncClient) -> None:
    ok = await api.post(
        "/api/v1/barcodes/weighed", json={"layout": "21IIIIIWWWWWC", "item": 12345, "grams": 1250}
    )
    overflow = await api.post(
        "/api/v1/barcodes/weighed", json={"layout": "21IIIIIWWWWWC", "item": 12345, "grams": 123456}
    )

    assert ok.json() == {"digits": "2112345012506"}
    assert overflow.status_code == 422
    assert overflow.json()["error"]["fix"] is not None


# --- the whole run: API server, event stream, startup failure, shutdown -----------------------


async def test_run_serves_events_and_shuts_down_cleanly(tmp_path: Path) -> None:
    api_port, device_port = free_port(), free_port()
    started: asyncio.Future[Simulator] = asyncio.get_running_loop().create_future()
    running = asyncio.create_task(run(config(tmp_path, device_port, api_port), started.set_result))
    await asyncio.wait_for(started, 5)
    base = f"http://127.0.0.1:{api_port}"

    async with websockets.connect(f"ws://127.0.0.1:{api_port}/api/v1/events") as events:
        async with httpx.AsyncClient(base_url=base) as client:
            await wait_for_http(client)
            await client.put("/api/v1/devices/front/faults/cover-open")
        message = json.loads(await asyncio.wait_for(events.recv(), 5))

    assert message["type"] == "printer.status.changed"
    assert message["device_id"] == "front"
    assert message["at"].endswith("Z")

    running.cancel()  # what Ctrl+C does
    await asyncio.gather(running, return_exceptions=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", device_port))  # the printer port is free again


async def test_browser_websocket_upgrade_is_refused(tmp_path: Path) -> None:
    api_port = free_port()
    started: asyncio.Future[Simulator] = asyncio.get_running_loop().create_future()
    running = asyncio.create_task(run(config(tmp_path, free_port(), api_port), started.set_result))
    await asyncio.wait_for(started, 5)
    try:
        with pytest.raises(websockets.InvalidStatus) as refused:
            async with websockets.connect(
                f"ws://127.0.0.1:{api_port}/api/v1/events",
                origin=websockets.Origin("https://example.com"),
            ):
                pass
        assert refused.value.response.status_code == 403
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)


async def test_run_with_the_page_serves_it_and_accepts_its_event_stream(tmp_path: Path) -> None:
    api_port = free_port()
    started: asyncio.Future[Simulator] = asyncio.get_running_loop().create_future()
    loaded = config(tmp_path, free_port(), api_port)
    running = asyncio.create_task(run(loaded, started.set_result, ui=True))
    await asyncio.wait_for(started, 5)
    events = f"ws://127.0.0.1:{api_port}/api/v1/events"
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{api_port}") as client:
            await wait_for_http(client)
            assert (await client.get("/")).status_code == 200
        async with websockets.connect(
            events, origin=websockets.Origin(f"http://127.0.0.1:{api_port}")
        ):
            pass  # the page's own origin opens the stream
        with pytest.raises(websockets.InvalidStatus) as refused:
            async with websockets.connect(
                events, origin=websockets.Origin("http://localhost:8069")
            ):
                pass
        assert refused.value.response.status_code == 403
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)


async def test_startup_failure_leaves_nothing_open(tmp_path: Path) -> None:
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    busy_port = taken.getsockname()[1]
    try:
        with pytest.raises(StartupError) as failure:
            await run(config(tmp_path, busy_port, free_port()), lambda _: None)
    finally:
        taken.close()

    assert "front" in str(failure.value)
    assert str(busy_port) in str(failure.value)


async def wait_for_http(client: httpx.AsyncClient) -> None:
    async with asyncio.timeout(5):
        while True:
            try:
                if (await client.get("/api/v1/health")).status_code == 200:
                    return
            except httpx.TransportError:
                await asyncio.sleep(0.05)


@pytest.mark.skipif(
    not POSIX, reason="existing serial device paths are supported on macOS and Linux"
)
async def test_scale_on_an_existing_serial_device_path(tmp_path: Path) -> None:
    assert sys.platform != "win32"  # skipped on Windows; this tells the type checker
    master, slave = os.openpty()  # stands in for a USB serial adapter such as /dev/ttyUSB0
    path = os.ttyname(slave)
    text = f"""
schema: 1
api: {{ port: {free_port()} }}
devices:
  - {{ id: deli, type: scale, profile: toledo8217-15kg, connections: [ {{ serial: {{ port: "{path}" }} }} ] }}
"""
    running = Simulator(parse_config(text, "test.yaml", tmp_path, sys.platform))
    await running.start()
    try:
        scale = running.runtime("deli").device
        assert isinstance(scale, Scale)
        assert running.runtime("deli").endpoints[0].endpoint == path
        running.set_weight(scale, 1250, stable=True)
        os.set_blocking(master, False)
        os.write(master, b"W")
        reply = await read_serial(master, 8)
    finally:
        await running.stop()
        os.close(master)
        os.close(slave)

    assert reply == bytes.fromhex("02 30 31 2e 32 35 30 0d")


# --- client-typed scans (barcode-scanner "Client-typed scans") -------------------------------


async def scan_plan(api: httpx.AsyncClient, **body: object) -> httpx.Response:
    return await api.post("/api/v1/devices/lane1/scans", json={"countdown_seconds": 0, **body})


async def test_client_typed_scan_returns_the_key_plan(api: httpx.AsyncClient) -> None:
    # No keyboard is touched on this machine: on a headless runner this would be a 409 otherwise.
    accepted = await scan_plan(api, data="Ab1")

    assert accepted.status_code == 200
    body = accepted.json()
    assert body["typed_by"] == "client"
    assert body["inter_key_delay_ms"] == 10
    assert body["keys"] == [
        {"usage": 4, "shift": True},
        {"usage": 5, "shift": False},
        {"usage": 30, "shift": False},
        {"usage": 40, "shift": False},
    ]
    assert body["deliver_at"].endswith("Z")


async def test_client_typed_unicode_scan_returns_characters(api: httpx.AsyncClient) -> None:
    body = (await scan_plan(api, data="كو", unicode=True)).json()

    assert body["keys"] == [{"char": "ك"}, {"char": "و"}, {"usage": 40, "shift": False}]


async def test_client_typed_scan_holds_the_scanner_until_reported(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    events: list[PublishedEvent] = []
    simulator.bus.subscribe(events.append)

    accepted = await scan_plan(api, data="123")
    busy = await scan_plan(api, data="456")
    reported = await api.post(
        f"/api/v1/devices/lane1/scans/{accepted.json()['id']}/typed",
        json={"outcome": "delivered"},
    )
    again = await scan_plan(api, data="456")

    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "scan_in_progress"
    assert reported.status_code == 204
    assert again.status_code == 200
    delivered = [e for e in events if e.event.type == "scanner.scan.delivered"]
    assert len(delivered) == 1
    assert delivered[0].event.data == {
        "id": accepted.json()["id"],
        "data": "123",
        "mode": "keyboard",
    }


async def test_failed_report_frees_the_scanner_without_an_event(
    api: httpx.AsyncClient, simulator: Simulator
) -> None:
    events: list[PublishedEvent] = []
    simulator.bus.subscribe(events.append)
    accepted = await scan_plan(api, data="1234567")

    reported = await api.post(
        f"/api/v1/devices/lane1/scans/{accepted.json()['id']}/typed",
        json={"outcome": "failed", "keys_accepted": 3, "reason": "the window went away"},
    )

    assert reported.status_code == 204
    assert not [e for e in events if e.event.type == "scanner.scan.delivered"]
    assert (await scan_plan(api, data="456")).status_code == 200


async def test_stale_report_does_nothing(api: httpx.AsyncClient, simulator: Simulator) -> None:
    events: list[PublishedEvent] = []
    simulator.bus.subscribe(events.append)

    stale = await api.post(
        "/api/v1/devices/lane1/scans/lane1-99/typed", json={"outcome": "delivered"}
    )

    assert stale.status_code == 204
    assert not events


@pytest.mark.skipif(not POSIX, reason="the serial scanner needs a simulator-created serial port")
async def test_report_for_a_server_typed_scanner_is_refused(api: httpx.AsyncClient) -> None:
    refused = await api.post(
        "/api/v1/devices/lane2/scans/lane2-1/typed", json={"outcome": "delivered"}
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "typed_by_mismatch"


async def test_report_on_a_printer_is_the_wrong_device_type(api: httpx.AsyncClient) -> None:
    refused = await api.post(
        "/api/v1/devices/front/scans/front-1/typed", json={"outcome": "delivered"}
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "wrong_device_type"


async def test_invalid_data_is_refused_before_a_plan(api: httpx.AsyncClient) -> None:
    refused = await scan_plan(api, data="كود42")

    assert refused.status_code == 422
    assert "unicode" in refused.json()["error"]["fix"]


async def test_scanner_state_reports_who_types(api: httpx.AsyncClient) -> None:
    lane1 = (await api.get("/api/v1/devices/lane1")).json()

    assert lane1["state"]["typed_by"] == "client"
    assert lane1["state"]["mode"] == "keyboard"


async def test_keyboard_unavailable_fix_names_client_typing(
    api: httpx.AsyncClient, simulator: Simulator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 409 a machine without a desktop returns is how a user finds `typed_by`."""

    class NoKeyboard:
        def check_ready(self) -> None:
            raise KeyboardUnavailableError(
                "keystrokes cannot be typed: no X11 display (DISPLAY is not set)",
                "log in to an X11 session, or set `mode: serial` for this scanner",
            )

    monkeypatch.setattr("emupos.daemon.simulator.system_keyboard", NoKeyboard)
    scanner = simulator.runtime("lane1").device
    assert isinstance(scanner, Scanner)
    monkeypatch.setattr(scanner, "typed_by", "server")

    refused = await scan_plan(api, data="123")

    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "keyboard_unavailable"
    assert "mode: serial" in error["fix"]
    assert "typed_by: client" in error["fix"]


@pytest.mark.skipif(not POSIX, reason="the serial scanner needs a simulator-created serial port")
async def test_server_typed_scan_answers_exactly_as_before(api: httpx.AsyncClient) -> None:
    """A scanner without `typed_by` must be indistinguishable from one before this feature."""
    accepted = await api.post(
        "/api/v1/devices/lane2/scans", json={"data": "123", "countdown_seconds": 0}
    )

    assert accepted.status_code == 202
    body = accepted.json()
    assert body["typed_by"] == "server"
    assert body["deliver_at"].endswith("Z")
    assert body["keys"] is None
    assert body["inter_key_delay_ms"] is None
    assert (await api.get("/api/v1/devices/lane2")).json()["state"]["typed_by"] == "server"
