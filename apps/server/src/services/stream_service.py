from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

from apps.server.src.services.persistence import StreamStore


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

    def __init__(
        self,
        max_buffer: int = 2000,
        queue_size: int = 256,
        stream_store: StreamStore | None = None,
        max_persisted_sessions: int = 200,
    ) -> None:
        self._max_buffer = max_buffer
        self._queue_size = queue_size
        self._max_persisted_sessions = max(1, int(max_persisted_sessions))
        self._seq: dict[str, int] = defaultdict(int)
        self._buffers: dict[str, list[StreamMessage]] = defaultdict(list)
        self._subscribers: dict[str, dict[str, asyncio.Queue[dict]]] = defaultdict(dict)
        self._drop_counts: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._stream_store = stream_store
        self._load_from_store()

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
                dropped = self._offer_latest(queue, item.to_dict())
                if dropped:
                    self._drop_counts[session_id] += 1
            self._persist_stream_state()
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

    async def backpressure_stats(self, session_id: str) -> dict:
        async with self._lock:
            return {
                "subscriber_count": len(self._subscribers.get(session_id, {})),
                "drop_count": self._drop_counts.get(session_id, 0),
                "queue_size": self._queue_size,
            }

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
    def _offer_latest(queue: asyncio.Queue[dict], message: dict) -> bool:
        try:
            queue.put_nowait(message)
            return False
        except asyncio.QueueFull:
            pass
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            # If still full due to race, drop this message.
            return True

    def _persist_stream_state(self) -> None:
        if self._stream_store is None:
            return
        keep_sessions = self._session_ids_for_persistence()
        state = {
            "seq": {
                session_id: int(seq)
                for session_id, seq in self._seq.items()
                if session_id in keep_sessions
            },
            "buffers": {
                session_id: [message.to_dict() for message in buffer]
                for session_id, buffer in self._buffers.items()
                if session_id in keep_sessions
            },
            "drop_counts": {
                session_id: int(v)
                for session_id, v in self._drop_counts.items()
                if session_id in keep_sessions
            },
        }
        self._stream_store.save_stream_state(state)

    def _load_from_store(self) -> None:
        if self._stream_store is None:
            return
        state = self._stream_store.load_stream_state()
        seq_raw = state.get("seq", {})
        if isinstance(seq_raw, dict):
            for session_id, seq in seq_raw.items():
                try:
                    self._seq[str(session_id)] = int(seq)
                except Exception:
                    continue
        drop_raw = state.get("drop_counts", {})
        if isinstance(drop_raw, dict):
            for session_id, count in drop_raw.items():
                try:
                    self._drop_counts[str(session_id)] = int(count)
                except Exception:
                    continue
        buffers_raw = state.get("buffers", {})
        if isinstance(buffers_raw, dict):
            for session_id, items in buffers_raw.items():
                if not isinstance(items, list):
                    continue
                restored: list[StreamMessage] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        restored.append(
                            StreamMessage(
                                type=str(item.get("type", "event")),
                                seq=int(item.get("seq", 0)),
                                session_id=str(item.get("session_id", session_id)),
                                server_time_ms=int(item.get("server_time_ms", 0)),
                                payload=dict(item.get("payload", {})),
                            )
                        )
                    except Exception:
                        continue
                restored.sort(key=lambda msg: msg.seq)
                self._buffers[str(session_id)] = restored[-self._max_buffer :]

    def _session_ids_for_persistence(self) -> set[str]:
        sessions = set(self._buffers.keys()) | set(self._seq.keys())
        if len(sessions) <= self._max_persisted_sessions:
            return sessions
        ordered = sorted(
            sessions,
            key=lambda sid: (
                self._buffers[sid][-1].server_time_ms if self._buffers.get(sid) else 0,
                self._seq.get(sid, 0),
                sid,
            ),
            reverse=True,
        )
        return set(ordered[: self._max_persisted_sessions])
