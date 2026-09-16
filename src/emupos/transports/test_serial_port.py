import asyncio
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from emupos.config import SerialFraming
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.serial_port import SerialPort, open_serial_port

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX device paths")

TIMEOUT = 2
ALL_BYTES = bytes(range(256))
# 7E1 also exercises the Linux pty retry in apply_framing.
TOLEDO = SerialFraming(baud=9600, data_bits=7, parity="even", stop_bits=1)
type Device = tuple[SerialPort, int]


@pytest.fixture
async def device() -> AsyncIterator[Device]:
    """An "existing device": the slave end of a pty, with the test on the master end."""
    if sys.platform == "win32":  # also lets type checkers see os.openpty
        pytest.skip("a pty stands in for the device on macOS and Linux")
    master, slave = os.openpty()
    try:
        port = await open_serial_port(os.ttyname(slave), TOLEDO)
    finally:
        os.close(slave)
    os.set_blocking(master, False)
    yield port, master
    await port.close()
    os.close(master)


async def far_end_read(fd: int, count: int) -> bytes:
    data = b""
    async with asyncio.timeout(TIMEOUT):
        while len(data) < count:
            try:
                data += os.read(fd, count - len(data))
            except BlockingIOError:
                await asyncio.sleep(0.01)
    return data


async def assert_far_end_silent(fd: int) -> None:
    await asyncio.sleep(0.1)
    with pytest.raises(BlockingIOError):
        os.read(fd, 16)


async def test_connection_id_names_the_path(device: Device) -> None:
    port, _ = device
    assert port.connection_id == f"serial:{port.path}"


async def test_raw_no_echo_and_no_translation(device: Device) -> None:
    port, far_end = device
    os.write(far_end, bytes.fromhex("1b 40 0d 0a 11 13 03"))
    received = await asyncio.wait_for(port.reader.readexactly(7), TIMEOUT)
    assert received == bytes.fromhex("1b 40 0d 0a 11 13 03")
    await assert_far_end_silent(far_end)

    weight = bytes.fromhex("02 30 31 2e 32 35 30 0d")
    port.writer.write(weight)
    await port.writer.drain()
    assert await far_end_read(far_end, len(weight)) == weight
    await assert_far_end_silent(far_end)  # no 0a appended


async def test_all_byte_values_both_ways(device: Device) -> None:
    port, far_end = device
    os.write(far_end, ALL_BYTES)
    assert await asyncio.wait_for(port.reader.readexactly(256), TIMEOUT) == ALL_BYTES
    port.writer.write(ALL_BYTES[::-1])
    await port.writer.drain()
    assert await far_end_read(far_end, 256) == ALL_BYTES[::-1]


async def test_close_ends_the_streams(device: Device) -> None:
    port, _ = device
    await port.close()
    assert port.writer.is_closing()
    assert await asyncio.wait_for(port.reader.read(), TIMEOUT) == b""


@posix_only
async def test_missing_path_names_the_path(tmp_path: Path) -> None:
    missing = str(tmp_path / "ttyUSB9")
    with pytest.raises(EndpointUnavailableError, match=r"ttyUSB9.*check the device path"):
        await open_serial_port(missing, TOLEDO)


@posix_only
async def test_regular_file_is_not_a_serial_device(tmp_path: Path) -> None:
    (tmp_path / "notes").write_text("")
    with pytest.raises(EndpointUnavailableError, match="not a serial device"):
        await open_serial_port(str(tmp_path / "notes"), TOLEDO)


@pytest.mark.skipif(sys.platform != "win32", reason="COM ports exist on Windows only")
async def test_missing_com_port_names_the_fix() -> None:
    with pytest.raises(EndpointUnavailableError) as caught:
        await open_serial_port("COM99", TOLEDO)

    message = str(caught.value)
    assert "`COM99`" in message
    assert "com0com" in message
    assert "emupos doctor" in message
