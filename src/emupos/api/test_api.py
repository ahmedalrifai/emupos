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

POSIX = sys.platform != "win32"
BASE_URL = "http://127.0.0.1:8765"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def config(tmp_path: Path, printer_port: int, api_port: int = 8765) -> LoadedConfig:
    serial_devices = """
  - { id: deli, type: scale, profile: toledo8217-15kg, connections: [ { serial: { pty: true } } ] }
  - { id: lane2, type: scanner, mode: serial, connections: [ { serial: { pty: true } } ] }
"""
    text = f"""
schema: 1
api: {{ port: {api_port} }}
devices:
  - {{ id: front, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: {printer_port} }} }} ], job_idle_timeout_ms: 200 }}
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
        assert devices["deli"]["connections"][0]["link_path"].endswith("links/deli")
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
