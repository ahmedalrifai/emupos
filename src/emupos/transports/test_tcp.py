import asyncio
import socket
import struct
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest

from emupos.events import ConnectionId
from emupos.transports.errors import EndpointUnavailableError
from emupos.transports.tcp import TcpListener, serve_tcp

TIMEOUT = 2
ALL_BYTES = bytes(range(256))
type Client = tuple[asyncio.StreamReader, asyncio.StreamWriter]
type Connect = Callable[[TcpListener], Awaitable[Client]]


async def echo(_: ConnectionId, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(4096):
        writer.write(data)
        await writer.drain()


@pytest.fixture
async def listener() -> AsyncIterator[TcpListener]:
    listener = await serve_tcp("127.0.0.1", 0, echo)
    yield listener
    await listener.close()


@pytest.fixture
async def connect() -> AsyncIterator[Connect]:
    writers: list[asyncio.StreamWriter] = []

    async def open_client(listener: TcpListener) -> Client:
        client = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", listener.port), TIMEOUT
        )
        writers.append(client[1])
        return client

    yield open_client
    for writer in writers:
        writer.close()


async def exchange(client: Client, data: bytes) -> bytes:
    reader, writer = client
    writer.write(data)
    await writer.drain()
    return await asyncio.wait_for(reader.readexactly(len(data)), TIMEOUT)


async def assert_silent(client: Client) -> None:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(client[0].read(1), 0.2)


async def test_binds_only_the_given_host(listener: TcpListener) -> None:
    assert [s.getsockname()[0] for s in listener.server.sockets] == ["127.0.0.1"]


async def test_nothing_is_sent_on_connect(listener: TcpListener, connect: Connect) -> None:
    await assert_silent(await connect(listener))


async def test_replies_go_only_to_the_requesting_client(
    listener: TcpListener, connect: Connect
) -> None:
    a, b = await connect(listener), await connect(listener)
    assert await exchange(a, bytes.fromhex("10 04 01")) == bytes.fromhex("10 04 01")
    await assert_silent(b)
    assert await exchange(b, b"b") == b"b"


async def test_connection_id_names_listening_port_and_client(connect: Connect) -> None:
    ids: asyncio.Queue[ConnectionId] = asyncio.Queue()

    async def record(connection: ConnectionId, *_: object) -> None:
        await ids.put(connection)

    listener = await serve_tcp("127.0.0.1", 0, record)
    try:
        _, writer = await connect(listener)
        client_port = writer.get_extra_info("sockname")[1]
        connection = await asyncio.wait_for(ids.get(), TIMEOUT)
        assert connection == f"tcp:127.0.0.1:{listener.port}<-127.0.0.1:{client_port}"
    finally:
        await listener.close()


async def test_client_reset_does_not_affect_others(listener: TcpListener, connect: Connect) -> None:
    loop = asyncio.get_running_loop()
    unhandled: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: unhandled.append(context))
    survivor = await connect(listener)

    resetter = socket.create_connection(("127.0.0.1", listener.port), timeout=TIMEOUT)
    resetter.sendall(bytes.fromhex("1b 40 1b 61 01"))  # half a job
    resetter.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    resetter.close()  # linger 0: the peer gets RST, not FIN
    await asyncio.sleep(0.1)

    assert await exchange(survivor, b"still here") == b"still here"
    assert await exchange(await connect(listener), b"new client") == b"new client"
    assert unhandled == []


async def test_all_byte_values_both_ways(connect: Connect) -> None:
    received: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

    async def device(
        _: ConnectionId, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        received.set_result(await reader.readexactly(256))
        writer.write(ALL_BYTES[::-1])
        await writer.drain()

    listener = await serve_tcp("127.0.0.1", 0, device)
    try:
        reader, writer = await connect(listener)
        writer.write(ALL_BYTES)
        assert await asyncio.wait_for(received, TIMEOUT) == ALL_BYTES
        assert await asyncio.wait_for(reader.readexactly(256), TIMEOUT) == ALL_BYTES[::-1]
    finally:
        await listener.close()


async def test_port_in_use_names_the_port() -> None:
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        with pytest.raises(EndpointUnavailableError, match=f"port {port} .*already in use"):
            await serve_tcp("127.0.0.1", port, echo)


async def test_close_disconnects_clients_and_frees_the_port(
    listener: TcpListener, connect: Connect
) -> None:
    client = await connect(listener)
    assert await exchange(client, b"x") == b"x"
    port = listener.port

    await asyncio.wait_for(listener.close(), TIMEOUT)

    assert await asyncio.wait_for(client[0].read(), TIMEOUT) == b""
    again = await serve_tcp("127.0.0.1", port, echo)
    await again.close()
