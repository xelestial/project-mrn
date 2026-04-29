from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

from apps.server.src.domain.view_state import project_view_state
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
        stream_backend=None,
        game_state_store=None,
        command_store=None,
        max_persisted_sessions: int = 200,
        player_name_resolver=None,
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
        self._stream_backend = stream_backend
        self._game_state_store = game_state_store
        self._command_store = command_store
        self._player_name_resolver = player_name_resolver
        self._load_from_store()

    async def publish(self, session_id: str, msg_type: str, payload: dict) -> StreamMessage:
        async with self._lock:
            enriched_payload = dict(payload)
            self._inject_display_names(session_id, enriched_payload)
            history = self._history_records_no_lock(session_id)
            projected = project_view_state(
                [
                    *history,
                    {
                        "type": msg_type,
                        "seq": self._seq[session_id] + 1,
                        "session_id": session_id,
                        "server_time_ms": int(time.time() * 1000),
                        "payload": enriched_payload,
                    },
                ]
            )
            if projected:
                enriched_payload["view_state"] = projected
            server_time_ms = int(time.time() * 1000)
            if self._stream_backend is not None:
                backend_record = self._stream_backend.publish(
                    session_id,
                    msg_type,
                    enriched_payload,
                    server_time_ms=server_time_ms,
                    max_buffer=self._max_buffer,
                )
                item = StreamMessage(
                    type=str(backend_record["type"]),
                    seq=int(backend_record["seq"]),
                    session_id=str(backend_record["session_id"]),
                    server_time_ms=int(backend_record["server_time_ms"]),
                    payload=dict(backend_record["payload"]),
                )
            else:
                self._seq[session_id] += 1
                item = StreamMessage(
                    type=msg_type,
                    seq=self._seq[session_id],
                    session_id=session_id,
                    server_time_ms=server_time_ms,
                    payload=enriched_payload,
                )
                buf = self._buffers[session_id]
                buf.append(item)
                if len(buf) > self._max_buffer:
                    del buf[: len(buf) - self._max_buffer]
            for queue in self._subscribers.get(session_id, {}).values():
                dropped = self._offer_latest(queue, item.to_dict())
                if dropped:
                    if self._stream_backend is not None:
                        self._stream_backend.increment_drop_count(session_id, 1)
                    else:
                        self._drop_counts[session_id] += 1
            if self._stream_backend is None:
                self._persist_stream_state()
            if self._game_state_store is not None:
                self._game_state_store.apply_stream_message(item.to_dict())
            if self._command_store is not None:
                self._maybe_append_command(item)
            return item

    async def snapshot(self, session_id: str) -> list[StreamMessage]:
        async with self._lock:
            if self._stream_backend is not None:
                return [self._message_from_payload(message) for message in self._stream_backend.snapshot(session_id)]
            return list(self._buffers.get(session_id, []))

    async def replay_from(self, session_id: str, last_seq: int) -> list[StreamMessage]:
        async with self._lock:
            if self._stream_backend is not None:
                return [self._message_from_payload(message) for message in self._stream_backend.replay_from(session_id, last_seq)]
            buf = self._buffers.get(session_id, [])
            return [item for item in buf if item.seq > last_seq]

    async def replay_window(self, session_id: str) -> tuple[int, int]:
        async with self._lock:
            if self._stream_backend is not None:
                return self._stream_backend.replay_window(session_id)
            buf = self._buffers.get(session_id, [])
            if not buf:
                return (0, 0)
            return (buf[0].seq, buf[-1].seq)

    async def latest_seq(self, session_id: str) -> int:
        async with self._lock:
            if self._stream_backend is not None:
                return self._stream_backend.latest_seq(session_id)
            return self._seq.get(session_id, 0)

    async def delete_session_data(self, session_id: str) -> None:
        async with self._lock:
            self._seq.pop(session_id, None)
            self._buffers.pop(session_id, None)
            self._drop_counts.pop(session_id, None)
            self._subscribers.pop(session_id, None)
            if self._stream_backend is not None:
                self._stream_backend.delete_session_data(session_id)
                if self._game_state_store is not None:
                    self._game_state_store.delete_session_data(session_id)
                if self._command_store is not None:
                    self._command_store.delete_session_data(session_id)
            else:
                self._persist_stream_state()

    async def backpressure_stats(self, session_id: str) -> dict:
        async with self._lock:
            return {
                "subscriber_count": len(self._subscribers.get(session_id, {})),
                "drop_count": self._stream_backend.drop_count(session_id) if self._stream_backend is not None else self._drop_counts.get(session_id, 0),
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
        if self._stream_backend is not None:
            return
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

    @staticmethod
    def _message_from_payload(message: dict) -> StreamMessage:
        return StreamMessage(
            type=str(message.get("type", "event")),
            seq=int(message.get("seq", 0)),
            session_id=str(message.get("session_id", "")),
            server_time_ms=int(message.get("server_time_ms", 0)),
            payload=dict(message.get("payload", {})),
        )

    def _history_records_no_lock(self, session_id: str) -> list[dict]:
        if self._stream_backend is not None:
            return [message.to_dict() for message in self._messages_from_backend(session_id)]
        return [item.to_dict() for item in self._buffers.get(session_id, [])]

    def _messages_from_backend(self, session_id: str) -> list[StreamMessage]:
        return [self._message_from_payload(message) for message in self._stream_backend.snapshot(session_id)]

    def _maybe_append_command(self, item: StreamMessage) -> None:
        payload = item.payload
        if not isinstance(payload, dict):
            return
        if payload.get("event_type") != "decision_resolved":
            return
        if payload.get("resolution") != "accepted":
            return
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return
        self._command_store.append_command(
            item.session_id,
            "decision_resolved",
            {
                "request_id": request_id,
                "player_id": payload.get("player_id"),
                "choice_id": payload.get("choice_id"),
                "request_type": payload.get("request_type"),
                "provider": payload.get("provider"),
                "source_seq": item.seq,
            },
            request_id=request_id,
            server_time_ms=item.server_time_ms,
        )

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

    def _inject_display_names(self, session_id: str, payload: dict) -> None:
        if self._player_name_resolver is None:
            return
        try:
            names = dict(self._player_name_resolver(session_id) or {})
        except Exception:
            return
        if not names:
            return
        self._apply_names_to_player_list(payload.get("players"), names)
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            self._apply_names_to_player_list(snapshot.get("players"), names)

    @staticmethod
    def _apply_names_to_player_list(players: object, names: dict[int, str]) -> None:
        if not isinstance(players, list):
            return
        for item in players:
            if not isinstance(item, dict):
                continue
            player_id = item.get("player_id")
            if not isinstance(player_id, int):
                continue
            display_name = names.get(player_id)
            if display_name:
                item["display_name"] = display_name
