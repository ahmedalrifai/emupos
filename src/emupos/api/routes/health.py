"""`GET /api/v1/health`: is the simulator running, and which versions."""

from importlib.metadata import version

from fastapi import APIRouter

from emupos.api.schemas import Health

API_VERSION = 1

router = APIRouter()


@router.get("/health")
async def health() -> Health:
    return Health(status="ok", version=version("emupos"), api_version=API_VERSION)
