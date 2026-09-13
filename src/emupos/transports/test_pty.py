import asyncio
import os
import stat
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from emupos.config import SerialFraming
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.pty import PtyPort, open_pty

if sys.platform != "win32":
    import tty

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="ptys exist on macOS and Linux only"
)

TIMEOUT = 2
ALL_BYTES = bytes(range(256))
EIGHT_N_ONE = SerialFraming(baud=9600, data_bits=8, parity="none", stop_bits=1)


@pytest.fixture
async def port(tmp_path: Path) -> AsyncIterator[PtyPort]:
    port = await open_pty("deli", EIGHT_N_ONE, tmp_path / "emupos")
    yield port
    await port.close()


def open_client(path: Path) -> int:
    """Open the port as a POS would."""
    if sys.platform == "win32":  # skipped there; lets type checkers see the POSIX-only names
        raise NotImplementedError
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    return fd


async def client_read(fd: int, count: int) -> bytes:
    data = b""
    async with asyncio.timeout(TIMEOUT):
        while len(data) < count:
            try:
                data += os.read(fd, count - len(data))
            except BlockingIOError:
                await asyncio.sleep(0.01)
    return data


async def device_read(port: PtyPort, count: int) -> bytes:
    return await asyncio.wait_for(port.reader.readexactly(count), TIMEOUT)


async def reply(port: PtyPort, data: bytes) -> None:
    port.writer.write(data)
    await asyncio.wait_for(port.writer.drain(), TIMEOUT)


async def test_link_points_to_the_device_in_a_private_dir(port: PtyPort) -> None:
    assert port.link_path.name == "deli"
    assert os.readlink(port.link_path) == port.device_path
    assert stat.S_IMODE(port.link_path.parent.stat().st_mode) & 0o077 == 0
    assert port.connection_id == f"serial:{port.link_path}"


async def test_no_echo_and_no_translation(port: PtyPort) -> None:
    client = open_client(port.link_path)
    try:
        os.write(client, bytes.fromhex("1b 40 0a"))
        assert await device_read(port, 3) == bytes.fromhex("1b 40 0a")
        await asyncio.sleep(0.1)
        with pytest.raises(BlockingIOError):
            os.read(client, 16)

        weight = bytes.fromhex("02 30 31 2e 32 35 30 0d")
        await reply(port, weight)
        assert await client_read(client, len(weight)) == weight
        await asyncio.sleep(0.1)
        with pytest.raises(BlockingIOError):
            os.read(client, 16)  # no 0a appended
        with pytest.raises(TimeoutError):  # the device does not read its own reply back
            await asyncio.wait_for(port.reader.read(1), 0.1)
    finally:
        os.close(client)


async def test_client_can_close_and_reopen(port: PtyPort) -> None:
    for _ in range(2):
        client = open_client(port.link_path)
        try:
            os.write(client, bytes.fromhex("57"))
            assert await device_read(port, 1) == bytes.fromhex("57")
            await reply(port, bytes.fromhex("02 3f 0d"))
            assert await client_read(client, 3) == bytes.fromhex("02 3f 0d")
        finally:
            os.close(client)


async def test_writer_closes_like_any_stream_writer(port: PtyPort) -> None:
    port.writer.close()
    await asyncio.wait_for(port.writer.wait_closed(), TIMEOUT)


async def test_all_byte_values_both_ways(port: PtyPort) -> None:
    client = open_client(port.link_path)
    try:
        os.write(client, ALL_BYTES)
        assert await device_read(port, 256) == ALL_BYTES
        await reply(port, ALL_BYTES[::-1])
        assert await client_read(client, 256) == ALL_BYTES[::-1]
    finally:
        os.close(client)


async def test_stale_link_is_replaced_and_dir_made_private(tmp_path: Path) -> None:
    link_dir = tmp_path / "emupos"
    link_dir.mkdir(mode=0o755)
    link_dir.chmod(0o755)
    (link_dir / "deli").symlink_to("/dev/emupos-no-such-tty")

    port = await open_pty("deli", EIGHT_N_ONE, link_dir)
    try:
        assert os.readlink(port.link_path) == port.device_path
        assert stat.S_IMODE(link_dir.stat().st_mode) == 0o700
    finally:
        await port.close()


async def test_regular_file_is_not_replaced(tmp_path: Path) -> None:
    link_dir = tmp_path / "emupos"
    link_dir.mkdir(mode=0o700)
    (link_dir / "deli").write_text("mine")
    with pytest.raises(EndpointUnavailableError, match="deli"):
        await open_pty("deli", EIGHT_N_ONE, link_dir)
    assert (link_dir / "deli").read_text() == "mine"


async def test_close_removes_the_link(tmp_path: Path) -> None:
    port = await open_pty("deli", EIGHT_N_ONE, tmp_path / "emupos")
    await port.close()
    assert not port.link_path.is_symlink()
