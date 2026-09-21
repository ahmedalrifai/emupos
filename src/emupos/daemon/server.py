"""Running the simulator with its control API until Ctrl+C or SIGTERM (`emupos run`)."""

import asyncio
import contextlib
import signal
import socket
import sys
from collections.abc import Callable, Generator

import uvicorn

from emupos.config import LoadedConfig
from emupos.daemon.runtime import StartupError
from emupos.daemon.simulator import Simulator


def serve(
    loaded: LoadedConfig, on_started: Callable[[Simulator], None], *, ui: bool = False
) -> None:
    """Blocking entry point for `emupos run`; returns after a clean shutdown.

    Raises StartupError when the control API port or a device endpoint is unavailable.
    """
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(loaded, on_started, ui=ui))


async def run(
    loaded: LoadedConfig, on_started: Callable[[Simulator], None], *, ui: bool = False
) -> None:
    """Run the simulator and its control API until cancelled (Ctrl+C) or SIGTERM, then stop cleanly.

    Raises StartupError, with nothing left open, when the API port or a device endpoint is unavailable.
    """
    api = loaded.config.api
    api_socket = bind_api_socket(api.host, api.port)
    simulator = Simulator(loaded)
    try:
        await simulator.start()
    except BaseException:
        api_socket.close()
        raise
    from emupos.api.app import create_app  # imported here: the API modules import the daemon

    config = uvicorn.Config(
        create_app(simulator, ui=ui),
        log_level="warning",
        access_log=False,
        lifespan="off",
        timeout_graceful_shutdown=2,  # never let a stuck client block Ctrl+C
    )
    server = _ApiServer(config)
    serving = asyncio.create_task(server.serve(sockets=[api_socket]))
    stopping = asyncio.Event()
    if sys.platform != "win32":
        # Ctrl+C cancels this coroutine (asyncio.run); SIGTERM gets the same clean shutdown.
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stopping.set)
    try:
        on_started(simulator)
        waiting = asyncio.create_task(stopping.wait())
        await asyncio.wait({serving, waiting}, return_when=asyncio.FIRST_COMPLETED)
        waiting.cancel()
    finally:
        server.should_exit = True
        await asyncio.gather(serving, return_exceptions=True)
        await simulator.stop()
        api_socket.close()


def bind_api_socket(host: str, port: int) -> socket.socket:
    """Bind the control API port before any device opens, so a conflict opens nothing."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    if sys.platform != "win32":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as error:
        sock.close()
        raise StartupError(
            f"control API port {port} on {host} is not available: {error.strerror or error}"
        ) from None
    sock.listen(128)
    sock.setblocking(False)
    return sock


class _ApiServer(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield  # `run` handles Ctrl+C and SIGTERM itself so devices shut down cleanly
