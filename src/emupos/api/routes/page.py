"""The control page (control-page spec): three fixed files, served only by `emupos run --ui`.

The files are read once when the app is built, so an installation missing them fails at startup
rather than on the first request. The routes sit outside `/api/v1` and out of the OpenAPI
document: the page is not part of the API contract (design D4).
"""

from collections.abc import Awaitable, Callable
from importlib import resources

from fastapi import APIRouter, Response

from emupos.api.errors import ApiError

POLICY = "default-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/page.js": ("page.js", "text/javascript; charset=utf-8"),
    "/page.css": ("page.css", "text/css; charset=utf-8"),
}


def router() -> APIRouter:
    page = resources.files("emupos.api").joinpath("page")
    routes = APIRouter(include_in_schema=False)
    for path, (name, media_type) in FILES.items():
        routes.add_api_route(path, _serve(page.joinpath(name).read_bytes(), media_type))
    return routes


def _serve(body: bytes, media_type: str) -> Callable[[], Awaitable[Response]]:
    async def serve() -> Response:
        return Response(body, media_type=media_type, headers={"Content-Security-Policy": POLICY})

    return serve


MISSING = APIRouter(include_in_schema=False)


@MISSING.get("/")
async def no_page() -> Response:
    raise ApiError(
        404,
        "not_found",
        "the control page is not being served",
        "start the simulator with `emupos run --ui`",
    )
