"""Simulator-created serial ports on macOS and Linux: a raw pty pair exposed as asyncio streams
(design D3), published under a stable link such as `$TMPDIR/emupos/deli`."""

import asyncio
import contextlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from emupos.config import SerialFraming
from emupos.events import ConnectionId
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.framing import apply_framing

if sys.platform != "win32":
    import tty


def default_link_dir() -> Path:
    # The spec fixes this location (not tempfile.gettempdir()) so users can predict the path.
    return Path(os.environ.get("TMPDIR") or "/tmp") / "emupos"  # noqa: S108


@dataclass(frozen=True, slots=True)
class PtyPort:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    device_path: str  # e.g. /dev/ttys003
    link_path: Path  # e.g. $TMPDIR/emupos/deli
    # Held open for the whole run. Clients may then close and reopen the port, and on Linux
    # reading the master would otherwise fail with EIO whenever no client has the port open.
    # Also the descriptor to observe the client's framing on (see framing.observe_framing).
    slave_fd: int
    _read_transport: asyncio.ReadTransport

    @property
    def connection_id(self) -> ConnectionId:
        return f"serial:{self.link_path}"

    async def close(self) -> None:
        """Remove the link and close the pty, once. Cancel any framing watcher first."""
        with contextlib.suppress(OSError):
            if os.readlink(self.link_path) == self.device_path:  # a later run may own it now
                self.link_path.unlink()
        if not self.writer.transport.is_closing():
            # abort, not close: a client that stopped reading must not keep replies pending forever.
            self.writer.transport.abort()
        self._read_transport.close()
        await asyncio.sleep(0)  # the transports close their descriptors on the next iteration
        os.close(self.slave_fd)


async def open_pty(link: str, framing: SerialFraming, link_dir: Path | None = None) -> PtyPort:
    """Create a raw pty pair set to `framing` and publish `<link_dir>/<link>` pointing at it.

    Raises EndpointUnavailableError on Windows or when the link cannot be published.
    """
    if sys.platform == "win32":
        raise EndpointUnavailableError(
            "`pty: true` is not supported on Windows; use `serial: { port: COMx }` "
            "with one end of a com0com virtual port pair"
        )
    master_fd, slave_fd = os.openpty()
    try:
        # Raw: no echo, no CR/LF translation, no XON/XOFF, no signal characters.
        tty.setraw(slave_fd)
        # Start at the expected framing so a mismatch is reported only when a client sets another.
        apply_framing(slave_fd, framing)
        device_path = os.ttyname(slave_fd)
    except BaseException:
        os.close(master_fd)
        os.close(slave_fd)
        raise

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    read_transport, _ = await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(master_fd, "rb", buffering=0)
    )
    # Writing uses its own duplicate descriptor because each pipe transport closes its file.
    # This protocol's reader stays unused; it is chosen because it makes writer.wait_closed() work.
    write_protocol = asyncio.StreamReaderProtocol(asyncio.StreamReader())
    write_transport, _ = await loop.connect_write_pipe(
        lambda: write_protocol, os.fdopen(os.dup(master_fd), "wb", buffering=0)
    )
    writer = asyncio.StreamWriter(write_transport, write_protocol, reader, loop)
    port = PtyPort(
        reader,
        writer,
        device_path,
        (link_dir or default_link_dir()) / link,
        slave_fd,
        read_transport,
    )
    try:
        _publish_link(port.link_path, device_path)
    except BaseException:
        await port.close()
        raise
    return port


def _publish_link(link_path: Path, device_path: str) -> None:
    # Unreachable on Windows (open_pty refuses first); the check lets type checkers see os.geteuid.
    if sys.platform == "win32":
        raise NotImplementedError
    link_dir = link_path.parent
    try:
        link_dir.mkdir(mode=0o700, exist_ok=True)
        info = link_dir.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            # Anyone could have created it first in a shared /tmp and would control our links.
            raise EndpointUnavailableError(
                f"{link_dir} is not a directory owned by you; remove it or set TMPDIR to a private directory"
            )
        if stat.S_IMODE(info.st_mode) & 0o077:
            link_dir.chmod(0o700)  # other users must not reach devices through our links
        if link_path.is_symlink():
            link_path.unlink()  # left behind by an earlier run
        link_path.symlink_to(device_path)
    except OSError as error:
        raise EndpointUnavailableError(
            f"cannot publish serial link {link_path}: {error.strerror or error}; "
            "remove it or choose another `link` name"
        ) from error
