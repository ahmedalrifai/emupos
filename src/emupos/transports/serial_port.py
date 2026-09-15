"""Existing serial ports (`serial: { port: /dev/ttyUSB0 }` or `COM5`), opened raw with the device's
framing and exposed as asyncio streams (design D3). Windows COM ports go through serialx."""

import asyncio
import os
import sys
from dataclasses import dataclass

from emupos.config import SerialFraming
from emupos.events import ConnectionId
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.framing import apply_framing
from emupos.transports.pty import close_fd_streams, fd_streams

if sys.platform == "win32":
    import serialx
else:
    import fcntl
    import termios
    import tty


@dataclass(frozen=True, slots=True)
class SerialPort:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    path: str
    _read_transport: asyncio.ReadTransport

    @property
    def connection_id(self) -> ConnectionId:
        return f"serial:{self.path}"

    async def close(self) -> None:
        """Close the port. Safe to call more than once."""
        await close_fd_streams(self.writer, self._read_transport)


async def open_serial_port(path: str, framing: SerialFraming) -> SerialPort:
    """Open the serial device at `path` in raw mode with `framing`.

    Raises EndpointUnavailableError naming the path and the fix when it cannot be opened.
    """
    if sys.platform == "win32":
        return await _open_com_port(path, framing)
    try:
        # O_NONBLOCK: otherwise opening a port on macOS waits for carrier detect.
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except FileNotFoundError:
        raise EndpointUnavailableError(
            f"no serial device at `{path}`; check the device path and that the adapter is connected"
        ) from None
    except PermissionError:
        fix = (
            "add yourself to the `dialout` group and log in again"
            if sys.platform == "linux"
            else "check the device's permissions"
        )
        raise EndpointUnavailableError(
            f"no permission to open serial device `{path}`; {fix}"
        ) from None
    except OSError as error:
        raise EndpointUnavailableError(
            f"cannot open serial device `{path}`: {error.strerror or error}; check the device path"
        ) from None
    try:
        if not os.isatty(fd):
            raise EndpointUnavailableError(
                f"`{path}` is not a serial device; check the device path"
            )
        # Exclusive: a second program opening the same port would silently steal bytes.
        fcntl.ioctl(fd, termios.TIOCEXCL)
        tty.setraw(fd)
        apply_framing(fd, framing)
    except termios.error as error:
        os.close(fd)
        raise EndpointUnavailableError(
            f"cannot set `{path}` to {framing.baud} baud, {framing.data_bits} data bits, "
            f"{framing.parity} parity, {framing.stop_bits} stop bits: {error.args[-1]}; "
            "check that the device supports this framing"
        ) from None
    except BaseException:
        os.close(fd)
        raise
    reader, writer, read_transport = await fd_streams(fd)
    return SerialPort(reader, writer, path, read_transport)


async def _open_com_port(path: str, framing: SerialFraming) -> SerialPort:
    if sys.platform != "win32":
        raise EndpointUnavailableError(f"`{path}`: COM ports exist on Windows only")
    try:
        reader, writer = await serialx.open_serial_connection(
            path,
            baudrate=framing.baud,
            byte_size=framing.data_bits,
            parity={
                "none": serialx.Parity.NONE,
                "even": serialx.Parity.EVEN,
                "odd": serialx.Parity.ODD,
            }[framing.parity],
            stopbits=framing.stop_bits,
        )
    except FileNotFoundError:
        raise EndpointUnavailableError(
            f"no serial port named `{path}`; serial devices on Windows need an existing COM port, "
            "such as one end of a virtual port pair like com0com (see docs/windows-serial.md); "
            "run `emupos doctor` to check the COM ports"
        ) from None
    except PermissionError:
        raise EndpointUnavailableError(
            f"serial port `{path}` is in use by another program; close that program or choose another port"
        ) from None
    except (OSError, ValueError, serialx.SerialException) as error:
        raise EndpointUnavailableError(
            f"cannot open serial port `{path}` at {framing.baud} baud, {framing.data_bits} data bits, "
            f"{framing.parity} parity, {framing.stop_bits} stop bits: {error}; "
            "check the port name and that the port supports this framing"
        ) from None
    return SerialPort(reader, writer, path, writer.transport)
