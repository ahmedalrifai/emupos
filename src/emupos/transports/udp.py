"""UDP for the Windows SNMP responder (design D7): answering datagrams, and one request for doctor."""

import asyncio
import socket
from collections.abc import Callable
from typing import cast

type Answer = Callable[[bytes], bytes | None]


class _Responder(asyncio.DatagramProtocol):
    def __init__(self, answer: Answer) -> None:
        self._answer = answer
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = cast(asyncio.DatagramTransport, transport)  # a datagram endpoint's

    def datagram_received(self, data: bytes, addr: tuple[str | int, ...]) -> None:
        if (reply := self._answer(data)) is not None and self._transport is not None:
            self._transport.sendto(reply, addr)

    def error_received(self, exc: Exception) -> None:
        pass  # Windows reports an ICMP "port unreachable" for an earlier reply here; keep serving


async def serve_udp(host: str, port: int, answer: Answer) -> asyncio.DatagramTransport:
    """Answer datagrams on exactly `host`:`port` until the transport is closed. Raises OSError."""
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Responder(answer), local_addr=(host, port)
    )
    return transport


def exchange(host: str, port: int, packet: bytes, timeout: float) -> bytes | None:
    """Send one datagram and wait for one reply (blocking); None when none arrives in time."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout)
        try:
            client.sendto(packet, (host, port))
            return client.recv(65535)
        except OSError:  # a timeout, or Windows reporting that nothing listens
            return None
