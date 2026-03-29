from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(slots=True)
class StreamMessage:
    type: str
    seq: int
    session_id: str
    server_time_ms: int
    payload: dict

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "seq": self.seq,
            "session_id": self.session_id,
            "server_time_ms": self.server_time_ms,
            "payload": self.payload,
        }


class StreamService:
    """In-memory per-session stream buffer with monotonic sequence ids."""

    def __init__(self, max_buffer: int = 2000, queue_size: int = 256) -> None:
        self._max_buffer = max_buffer
        self._queue_size = queue_size
        self._seq: dict[str, int] = defaultdict(int)
        self._buffers: dict[str, list[StreamMessage]] = defaultdict(list)
        self._subscribers: dict[str, dict[str, asyncio.Queue[dict]]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def publish(self, session_id: str, msg_type: str, payload: dict) -> StreamMessage:
        async with self._lock:
            self._seq[session_id] += 1
            item = StreamMessage(
                type=msg_type,
                seq=self._seq[session_id],
                session_id=session_id,
                server_time_ms=int(time.time() * 1000),
                payload=payload,
            )
            buf = self._buffers[session_id]
            buf.append(item)
            if len(buf) > self._max_buffer:
                del buf[: len(buf) - self._max_buffer]
            for queue in self._subscribers.get(session_id, {}).values():
                self._offer_latest(queue, item.to_dict())
            return item

    async def snapshot(self, session_id: str) -> list[StreamMessage]:
        async with self._lock:
            return list(self._buffers.get(session_id, []))

    async def replay_from(self, session_id: str, last_seq: int) -> list[StreamMessage]:
        async with self._lock:
            buf = self._buffers.get(session_id, [])
            return [item for item in buf if item.seq > last_seq]

    async def replay_window(self, session_id: str) -> tuple[int, int]:
        async with self._lock:
            buf = self._buffers.get(session_id, [])
            if not buf:
                return (0, 0)
            return (buf[0].seq, buf[-1].seq)

    async def latest_seq(self, session_id: str) -> int:
        async with self._lock:
            return self._seq.get(session_id, 0)

    async def subscribe(self, session_id: str, connection_id: str) -> asyncio.Queue[dict]:
        async with self._lock:
            queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._queue_size)
            self._subscribers[session_id][connection_id] = queue
            return queue

    async def unsubscribe(self, session_id: str, connection_id: str) -> None:
        async with self._lock:
            if session_id in self._subscribers:
                self._subscribers[session_id].pop(connection_id, None)
                if not self._subscribers[session_id]:
                    self._subscribers.pop(session_id, None)

    @staticmethod
    def _offer_latest(queue: asyncio.Queue[dict], message: dict) -> None:
        try:
            queue.put_nowait(message)
            return
        except asyncio.QueueFull:
            pass
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # If still full due to race, drop this message.
            pass
