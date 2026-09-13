"""Error responses of the control API: `{ "error": { "code", "message", "fix" } }` (control-api spec)."""

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fix: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fix = fix


def error_body(code: str, message: str, fix: str | None = None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "fix": fix}}


def error_response(status: int, code: str, message: str, fix: str | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message, fix), status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, error: ApiError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return error_response(error.status, error.code, error.message, error.fix)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        problems = [_describe(detail) for detail in error.errors()]
        return error_response(
            422,
            "validation_error",
            "; ".join(problems),
            "check the request against /api/v1/openapi.json",
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        if error.status_code == 404:
            return error_response(
                404, "not_found", "no such endpoint", "see /api/v1/openapi.json for the endpoints"
            )
        if error.status_code == 405:
            return error_response(
                405, "method_not_allowed", "this endpoint does not accept that method"
            )
        return error_response(error.status_code, "http_error", str(error.detail))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, error: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        # The server logs the traceback itself; logging it here too would print it twice.
        return error_response(
            500,
            "internal_error",
            "the simulator hit an unexpected error; see the `emupos run` output",
        )


def _describe(detail: Mapping[str, Any]) -> str:
    location: Sequence[object] = detail.get("loc", ())
    field = ".".join(str(part) for part in location if part != "body") or "request"
    kind = str(detail.get("type", ""))
    if kind in {"int_type", "int_parsing", "int_from_float"}:
        return f"`{field}`: an integer is required"
    if kind == "missing":
        return f"`{field}` is required"
    return f"`{field}`: {detail.get('msg', 'invalid value')}"
