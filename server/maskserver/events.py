"""Fan-out of job events to Server-Sent-Event subscribers."""
from __future__ import annotations

import asyncio
from typing import Optional, Set


class EventBroker:
    """publish() may be called from any thread; subscribers are asyncio queues on the server loop."""

    def __init__(self, queue_size: int = 1000) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queues: Set[asyncio.Queue] = set()
        self._queue_size = queue_size

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    def publish(self, event: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._deliver, event)
        except RuntimeError:  # loop shutting down
            pass

    def _deliver(self, event: dict) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # a stalled client; it resyncs from GET /api/jobs
                pass
