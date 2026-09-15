"""The simulator's SNMP responder over real UDP on a free port (Windows uses port 161)."""

import asyncio
import socket
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from emupos.config import parse_config
from emupos.daemon.simulator import Simulator
from emupos.events import PublishedEvent
from emupos.printer.printer import Printer, PrinterFault
from emupos.windows_queue.snmp import (
    GET,
    HR_DEVICE_STATUS,
    HR_PRINTER_DETECTED_ERROR_STATE,
    HR_PRINTER_STATUS,
    NULL,
    OCTET_STRING,
    SYS_DESCR,
    Message,
    decode_message,
    encode_message,
)


def free_port(kind: socket.SocketKind) -> int:
    with socket.socket(socket.AF_INET, kind) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def status_get(index: int, *, version: int = 1, pdu_type: int = GET) -> bytes:
    columns = (HR_DEVICE_STATUS, HR_PRINTER_STATUS, HR_PRINTER_DETECTED_ERROR_STATE)
    varbinds = tuple(((*column, index), NULL, b"") for column in columns)
    return encode_message(Message(version, b"public", pdu_type, 7, varbinds))


async def exchange(port: int, packet: bytes, timeout: float = 2.0) -> bytes | None:
    """Send one datagram and return the reply, or None when none arrives within `timeout`."""
    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.setblocking(False)
        client.connect(("127.0.0.1", port))
        await loop.sock_sendall(client, packet)
        try:
            return await asyncio.wait_for(loop.sock_recv(client, 2048), timeout)
        except TimeoutError:
            return None


@pytest.fixture
def ports() -> tuple[int, int]:
    return free_port(socket.SOCK_STREAM), free_port(socket.SOCK_DGRAM)


@pytest.fixture
async def simulator(tmp_path: Path, ports: tuple[int, int]) -> AsyncIterator[Simulator]:
    tcp_port, snmp_port = ports
    text = f"""
schema: 1
devices:
  - {{ id: front, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: {tcp_port} }} }} ] }}
"""
    loaded = parse_config(text, "test.yaml", tmp_path, sys.platform)
    running = Simulator(loaded, snmp_port=snmp_port)
    await running.start()
    yield running
    await running.stop()


def printer(simulator: Simulator) -> Printer:
    device = simulator.runtime("front").device
    assert isinstance(device, Printer)
    return device


async def test_status_follows_faults_and_emits_an_event(
    simulator: Simulator, ports: tuple[int, int]
) -> None:
    tcp_port, snmp_port = ports
    events: list[PublishedEvent] = []
    simulator.bus.subscribe(events.append)

    ready = await exchange(snmp_port, status_get(tcp_port))
    simulator.set_fault(printer(simulator), PrinterFault.PAPER_OUT, True)
    paper_out = await exchange(snmp_port, status_get(tcp_port))

    assert ready is not None
    assert paper_out is not None
    assert [value for _, _, value in decode_message(ready).varbinds] == [b"\x02", b"\x03", b"\x00"]
    assert [value for _, _, value in decode_message(paper_out).varbinds] == [
        b"\x05",
        b"\x01",
        b"\x40",
    ]
    answered = [e.to_json() for e in events if e.event.type == "snmp.query.answered"]
    assert len(answered) == 2
    assert answered[0]["device_id"] == "front"
    assert answered[0]["data"] == {
        "type": "get",
        "oids": [
            f"1.3.6.1.2.1.25.3.2.1.5.{tcp_port}",
            f"1.3.6.1.2.1.25.3.5.1.1.{tcp_port}",
            f"1.3.6.1.2.1.25.3.5.1.2.{tcp_port}",
        ],
    }


async def test_invalid_requests_change_nothing(
    simulator: Simulator, ports: tuple[int, int]
) -> None:
    tcp_port, snmp_port = ports
    set_request = encode_message(Message(1, b"public", 0xA3, 8, ((SYS_DESCR, OCTET_STRING, b"x"),)))

    assert await exchange(snmp_port, b"garbage", timeout=0.2) is None
    assert await exchange(snmp_port, set_request, timeout=0.2) is None
    assert await exchange(snmp_port, status_get(tcp_port)) is not None
    assert printer(simulator).state().faults == ()


async def test_port_in_use_keeps_devices_running(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tcp_port = free_port(socket.SOCK_STREAM)
    text = f"""
schema: 1
devices:
  - {{ id: front, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: {tcp_port} }} }} ] }}
"""
    loaded = parse_config(text, "test.yaml", tmp_path, sys.platform)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as taken:
        taken.bind(("127.0.0.1", 0))
        running = Simulator(loaded, snmp_port=taken.getsockname()[1])
        await running.start()
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
            writer.close()
        finally:
            await running.stop()

    assert (
        'UDP port 161 on 127.0.0.1 is in use, usually by the Windows "SNMP Service"' in caplog.text
    )
    assert "Stop-Service SNMP" in caplog.text
