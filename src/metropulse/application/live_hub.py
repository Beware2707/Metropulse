"""Live update hub: connection registry, replay buffer, and broadcast queue.

The hub decouples the Redis subscriber from WebSocket connections:
messages are submitted (thread-safely) into an asyncio queue, recorded in a
bounded replay buffer keyed by sequence number, then fanned out to every
connected client. Reconnecting clients send their last seen sequence and
receive only what they missed — or a signal that a fresh snapshot is needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Protocol

logger = logging.getLogger(__name__)


class WsConnection(Protocol):
    """Minimal sender interface implemented by WebSocket adapters."""

    async def send_text(self, data: str) -> None:
        """Send a text frame to the client."""
        ...


class ReplayBuffer:
    """Bounded in-memory buffer of recent diff messages keyed by sequence."""

    def __init__(self, max_size: int = 512) -> None:
        self._buffer: deque[tuple[int, str]] = deque(maxlen=max_size)

    def add(self, sequence: int, message: str) -> None:
        """Record a published diff."""
        self._buffer.append((sequence, message))

    @property
    def latest_sequence(self) -> int | None:
        """Sequence of the newest buffered message, or None when empty."""
        return self._buffer[-1][0] if self._buffer else None

    def since(self, last_sequence: int) -> list[str] | None:
        """Messages after ``last_sequence``, or None if the gap is unbridgeable.

        Returns an empty list when the client is already up to date. Returns
        None when messages the client needs have been evicted, meaning the
        client must take a fresh snapshot instead.
        """
        if not self._buffer:
            return None
        newest = self._buffer[-1][0]
        if last_sequence >= newest:
            return []
        oldest = self._buffer[0][0]
        if last_sequence < oldest - 1:
            return None
        return [msg for seq, msg in self._buffer if seq > last_sequence]


class ConnectionManager:
    """Tracks live WebSocket connections and broadcasts to all of them."""

    def __init__(self) -> None:
        self._connections: set[WsConnection] = set()
        self._lock = asyncio.Lock()

    async def connect(self, connection: WsConnection) -> None:
        """Register a connection for broadcasts."""
        async with self._lock:
            self._connections.add(connection)

    async def disconnect(self, connection: WsConnection) -> None:
        """Remove a connection (idempotent)."""
        async with self._lock:
            self._connections.discard(connection)

    @property
    def count(self) -> int:
        """Number of currently registered connections."""
        return len(self._connections)

    async def broadcast(self, message: str) -> None:
        """Send a message to every connection, dropping any that fail."""
        async with self._lock:
            targets = list(self._connections)
        dead: list[WsConnection] = []
        for connection in targets:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            await self.disconnect(connection)
        if dead:
            logger.info("dropped %d dead websocket connection(s)", len(dead))


class LiveHub:
    """Bridges published diff messages to connected WebSocket clients."""

    def __init__(self, manager: ConnectionManager, buffer: ReplayBuffer) -> None:
        self.manager = manager
        self.buffer = buffer
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    def submit(self, message: str) -> None:
        """Enqueue a diff message from any thread or task."""
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.warning("live hub not running; dropping message")
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._queue.put_nowait(message)
        else:
            loop.call_soon_threadsafe(self._queue.put_nowait, message)

    async def run(self) -> None:
        """Consume the queue forever: buffer each diff then broadcast it."""
        self._loop = asyncio.get_running_loop()
        while True:
            message = await self._queue.get()
            sequence = _extract_sequence(message)
            if sequence is not None:
                self.buffer.add(sequence, message)
            await self.manager.broadcast(message)


def _extract_sequence(message: str) -> int | None:
    """Pull the ``seq`` field out of a diff message, if present and valid."""
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        logger.warning("unparseable diff message; not buffering")
        return None
    sequence = payload.get("seq")
    return sequence if isinstance(sequence, int) else None
