"""The local control API (control-api spec): builds the FastAPI app from the routers.

The API performs the physical-world actions on simulated devices (set a weight, trigger a
scan, inject a fault, close the drawer) and reports what devices did. A POS never uses it:
POS code talks to devices only through their real protocols.

Route handlers are `async def` on purpose: FastAPI runs plain `def` handlers in a thread pool,
and device state must only be touched from the event loop (see daemon.py).
"""

import ipaddress
from importlib.metadata import version

from fastapi import APIRouter, FastAPI

from emupos.api import barcodes, devices, events, health, printers, scales, scanners
from emupos.api.errors import install_error_handlers
from emupos.api.guard import BrowserRequestGuard
from emupos.api.schemas import ErrorResponse
from emupos.daemon import Simulator

PREFIX = "/api/v1"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (403, 404, 409, 415, 422, 500)
}


def create_app(simulator: Simulator) -> FastAPI:
    app = FastAPI(
        title="emupos control API",
        version=version("emupos"),
        openapi_url=f"{PREFIX}/openapi.json",
        docs_url=f"{PREFIX}/docs",
        redoc_url=None,
    )
    app.state.simulator = simulator
    app.add_middleware(
        BrowserRequestGuard, check_host=_is_loopback(simulator.loaded.config.api.host)
    )
    install_error_handlers(app)

    api = APIRouter(prefix=PREFIX, responses=ERROR_RESPONSES)
    for module in (health, devices, printers, scales, scanners, barcodes, events):
        api.include_router(module.router)
    app.include_router(api)
    return app


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False
