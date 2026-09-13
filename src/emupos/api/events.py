"""`WS /api/v1/events`: every event emitted after the subscriber connected, in order."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from emupos.api.dependencies import SimulatorDep
from emupos.events import PublishedEvent

QUEUE_LIMIT = 10_000

router = APIRouter()


@router.websocket("/events")
async def events(websocket: WebSocket, simulator: SimulatorDep) -> None:
    await websocket.accept()
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(QUEUE_LIMIT)

    def forward(event: PublishedEvent) -> None:
        # ponytail: a subscriber that stops reading misses events; it never stalls the devices.
        if not queue.full():
            queue.put_nowait(event.to_json())

    unsubscribe = simulator.bus.subscribe(forward)
    sending = asyncio.create_task(_send_events(websocket, queue))
    try:
        # Subscribers send nothing; receiving is how a disconnect is noticed while no event flows.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass
    finally:
        unsubscribe()
        sending.cancel()


async def _send_events(websocket: WebSocket, queue: asyncio.Queue[dict[str, object]]) -> None:
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await websocket.send_json(await queue.get())
