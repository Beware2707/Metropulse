"""``/ws/live`` — live train updates over WebSocket.

Protocol (all frames are JSON text):

  client -> server
    {"type": "subscribe", "last_seq": <int|null>}   must be the first frame
    {"type": "pong"}                                 optional heartbeat reply

  server -> client
    {"type": "snapshot", "seq": N, "trains": [...]}  full state on (re)connect
    {"type": "update",  "seq": N, "updated": [...], "removed": [...], "stale": [...]}
    {"type": "heartbeat", "ts": "..."}               liveness signal

Reconnect: a client that sends its last seen ``last_seq`` receives only the
missed updates when they are still buffered; otherwise it gets a fresh
snapshot. Only changed trains are ever broadcast (the realtime engine
publishes diffs, not full states).

Compression: permessage-deflate is negotiated by the ASGI server; run uvicorn
with ``--ws websockets`` (enabled by default in the provided Docker image).
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from metropulse.application.live_hub import LiveHub
from metropulse.application.train_service import TrainService
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore

logger = logging.getLogger(__name__)

router = APIRouter()

_SUBSCRIBE_TIMEOUT_SECONDS = 10.0


@router.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    """Stream live train diffs to the client (see module docstring)."""
    hub: LiveHub = websocket.app.state.live_hub
    train_service: TrainService = websocket.app.state.train_service
    store: RedisVehicleStore = websocket.app.state.vehicle_store

    await websocket.accept()
    try:
        last_seq = await _read_subscribe(websocket)
    except (TimeoutError, ValueError) as exc:
        await websocket.close(code=1003, reason=str(exc))
        return
    except WebSocketDisconnect:
        return

    replay = hub.buffer.since(last_seq) if last_seq is not None else None
    try:
        if replay is not None:
            for message in replay:
                await websocket.send_text(message)
        else:
            await websocket.send_text(await _snapshot_message(train_service, store))
    except WebSocketDisconnect:
        return

    await hub.manager.connect(websocket)
    try:
        # From here on the hub pushes updates; this loop only keeps the
        # connection alive and absorbs client frames (e.g. heartbeat pongs).
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.manager.disconnect(websocket)


async def _read_subscribe(websocket: WebSocket) -> int | None:
    """Read and validate the mandatory subscribe frame.

    Returns the client's last seen sequence (None for a fresh session).
    Raises ``TimeoutError`` or ``ValueError`` on protocol violations.
    """
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=_SUBSCRIBE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError("subscribe frame not received in time") from exc
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("subscribe frame must be JSON") from exc
    if not isinstance(frame, dict) or frame.get("type") != "subscribe":
        raise ValueError("first frame must be {'type': 'subscribe', ...}")
    last_seq = frame.get("last_seq")
    if last_seq is not None and not isinstance(last_seq, int):
        raise ValueError("'last_seq' must be an integer or null")
    return last_seq


async def _snapshot_message(train_service: TrainService, store: RedisVehicleStore) -> str:
    """Build a full-state snapshot frame."""
    states = await train_service.list_trains()
    sequence = await store.current_sequence()
    return json.dumps(
        {
            "type": "snapshot",
            "seq": sequence,
            "ts": utcnow().isoformat(),
            "trains": [state.to_dict() for state in states],
        }
    )


async def heartbeat_loop(hub: LiveHub, interval_seconds: float) -> None:
    """Broadcast a heartbeat frame forever at the configured interval.

    Sending doubles as liveness detection: connections whose sends fail are
    dropped by the connection manager.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        message = json.dumps({"type": "heartbeat", "ts": utcnow().isoformat()})
        await hub.manager.broadcast(message)
