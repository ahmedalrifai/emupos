"""TCP listeners: every accepted client becomes a (StreamReader, StreamWriter) pair (design D3)."""

import asyncio
import errno
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from emupos.events import ConnectionId
from emupos.transports.errors import EndpointUnavailableError

type ConnectionHandler = Callable[
    [ConnectionId, asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]
]

# Windows reports socket errors with WinSock codes rather than POSIX errno values.
_ADDRESS_IN_USE = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)}


@dataclass(frozen=True, slots=True)
class TcpListener:
    server: asyncio.Server

    @property
    def port(self) -> int:
        """The bound port; differs from the requested one only when port 0 was requested."""
        return self.server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        """Stop accepting and close every client connection."""
        self.server.close()
        self.server.close_clients()
        await self.server.wait_closed()


def connection_id(listening: tuple[str, int], client: tuple[str, int]) -> ConnectionId:
    """E.g. "tcp:127.0.0.1:9100<-127.0.0.1:53422": listening address, then the client's."""
    return f"tcp:{_address(*listening)}<-{_address(*client)}"


async def serve_tcp(host: str, port: int, on_connection: ConnectionHandler) -> TcpListener:
    """Listen on exactly `host`:`port` and run `on_connection` for each client, concurrently.

    Nothing is sent on connect. The client's connection is closed when its handler returns.
    Raises EndpointUnavailableError when the address cannot be bound.
    """

    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        sockname = writer.get_extra_info("sockname")
        peername = writer.get_extra_info("peername")
        try:
            # IPv6 addresses are 4-tuples; host and port are always the first two fields.
            await on_connection(connection_id(sockname[:2], peername[:2]), reader, writer)
        except ConnectionError:
            pass  # a client resetting its connection is normal client behaviour, not a fault
        finally:
            writer.close()

    # start_server's defaults are what we want: SO_REUSEADDR on POSIX so an immediate restart
    # can bind while old connections sit in TIME_WAIT, and never SO_REUSEPORT, which would let
    # two processes share the port silently.
    try:
        server = await asyncio.start_server(accept, host, port)
    except OSError as error:
        if error.errno in _ADDRESS_IN_USE:
            message = f"port {port} on {host} is already in use; stop the program using it or choose another port"
        else:
            message = f"cannot listen on {_address(host, port)}: {error.strerror or error}; check the connection's `host`"
        raise EndpointUnavailableError(message) from error
    return TcpListener(server)


def _address(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
