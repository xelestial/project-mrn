from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass

from apps.server.src.domain.protocol_ids import new_event_id
from apps.server.src.domain.runtime_semantic_guard import validate_stream_payload
from apps.server.src.domain.visibility import ViewerContext, project_stream_message_for_viewer
from apps.server.src.infra.structured_log import log_event
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
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._subscriber_locks: dict[str, asyncio.Lock] = {}
        self._stream_store = stream_store
        self._stream_backend = stream_backend
        self._game_state_store = game_state_store
        self._command_store = command_store
        self._player_name_resolver = player_name_resolver
        self._view_commit_cache: OrderedDict[tuple[str, str], dict] = OrderedDict()
        self._view_commit_cache_lock = threading.RLock()
        self._view_commit_cache_max_entries = max(256, self._max_persisted_sessions * 8)
        self._load_from_store()

    async def publish(self, session_id: str, msg_type: str, payload: dict) -> StreamMessage:
        async with self._lock_for_session(session_id):
            enriched_payload = dict(payload)
            self._inject_display_names(session_id, enriched_payload)
            if self._stream_backend is not None:
                item = await asyncio.to_thread(
                    self._publish_with_backend_no_lock_sync,
                    session_id,
                    msg_type,
                    enriched_payload,
                )
                await self._broadcast(session_id, item)
                return item
            history = self._source_history_records_no_lock(session_id)
            validate_stream_payload(history=history, msg_type=msg_type, payload=enriched_payload)
            duplicate = self._duplicate_request_message_no_lock(history, msg_type, enriched_payload)
            if duplicate is None:
                duplicate = self._duplicate_idempotency_key_message_no_lock(history, msg_type, enriched_payload)
            if duplicate is None:
                duplicate = self._duplicate_round_setup_event_no_lock(history, msg_type, enriched_payload)
            if duplicate is not None:
                return duplicate
            enriched_payload = self._with_source_event_id(msg_type, enriched_payload)
            server_time_ms = int(time.time() * 1000)
            item = self._append_stream_message_no_lock(
                session_id,
                msg_type,
                enriched_payload,
                server_time_ms=server_time_ms,
            )
            await self._broadcast(session_id, item)
            if self._command_store is not None:
                self._maybe_append_command(item)
            if self._stream_backend is None:
                self._persist_stream_state()
            return item

    async def publish_decision_ack(self, session_id: str, payload: dict) -> StreamMessage:
        """Publish client feedback without scanning authoritative source history."""
        if self._stream_backend is not None:
            enriched_payload = self._with_source_event_id("decision_ack", dict(payload))
            self._inject_display_names(session_id, enriched_payload)
            item = await asyncio.to_thread(
                self._append_stream_message_no_lock,
                session_id,
                "decision_ack",
                enriched_payload,
                server_time_ms=int(time.time() * 1000),
            )
            await self._broadcast(session_id, item)
            return item

        async with self._lock_for_session(session_id):
            enriched_payload = self._with_source_event_id("decision_ack", dict(payload))
            self._inject_display_names(session_id, enriched_payload)
            item = self._append_stream_message_no_lock(
                session_id,
                "decision_ack",
                enriched_payload,
                server_time_ms=int(time.time() * 1000),
            )
            await self._broadcast(session_id, item)
            if self._stream_backend is None:
                self._persist_stream_state()
            return item

    async def publish_view_commit(self, session_id: str, payload: dict) -> StreamMessage:
        async with self._lock_for_session(session_id):
            server_time_ms = int(time.time() * 1000)
            if self._stream_backend is not None:
                item = await asyncio.to_thread(
                    self._publish_view_commit_with_backend_no_lock_sync,
                    session_id,
                    dict(payload),
                    server_time_ms,
                )
                await self._broadcast(session_id, item)
                return item
            item = self._append_stream_message_no_lock(
                session_id,
                "view_commit",
                dict(payload),
                server_time_ms=server_time_ms,
            )
            await self._broadcast(session_id, item)
            if self._stream_backend is None:
                self._persist_stream_state()
            return item

    def _lock_for_session(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def _subscriber_lock_for_session(self, session_id: str) -> asyncio.Lock:
        lock = self._subscriber_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._subscriber_locks[session_id] = lock
        return lock

    def _publish_with_backend_no_lock_sync(
        self,
        session_id: str,
        msg_type: str,
        enriched_payload: dict,
    ) -> StreamMessage:
        history = self._source_history_records_no_lock(session_id)
        validate_stream_payload(history=history, msg_type=msg_type, payload=enriched_payload)
        duplicate = self._duplicate_request_message_no_lock(history, msg_type, enriched_payload)
        if duplicate is None:
            duplicate = self._duplicate_idempotency_key_message_no_lock(history, msg_type, enriched_payload)
        if duplicate is None:
            duplicate = self._duplicate_round_setup_event_no_lock(history, msg_type, enriched_payload)
        if duplicate is not None:
            return duplicate
        payload = self._with_source_event_id(msg_type, enriched_payload)
        item = self._append_stream_message_no_lock(
            session_id,
            msg_type,
            payload,
            server_time_ms=int(time.time() * 1000),
        )
        if self._command_store is not None:
            self._maybe_append_command(item)
        return item

    def _publish_view_commit_with_backend_no_lock_sync(
        self,
        session_id: str,
        payload: dict,
        server_time_ms: int,
    ) -> StreamMessage:
        return self._append_stream_message_no_lock(
            session_id,
            "view_commit",
            payload,
            server_time_ms=server_time_ms,
        )

    async def emit_snapshot_pulse(
        self,
        session_id: str,
        *,
        reason: str,
        target_player_id: int | None = None,
    ) -> StreamMessage | None:
        async with self._lock_for_session(session_id):
            viewer = (
                ViewerContext(role="seat", session_id=session_id, player_id=target_player_id)
                if target_player_id is not None
                else ViewerContext(role="spectator", session_id=session_id)
            )
            if self._load_cached_view_commit_no_lock(session_id, viewer) is None:
                return None
            payload = {
                "reason": str(reason or "snapshot_guardrail"),
                "scope": "player" if target_player_id is not None else "all",
            }
            if target_player_id is not None:
                payload["target_player_id"] = int(target_player_id)
            item = self._append_stream_message_no_lock(
                session_id,
                "snapshot_pulse",
                payload,
                server_time_ms=int(time.time() * 1000),
            )
            await self._broadcast(session_id, item)
            if self._stream_backend is None:
                self._persist_stream_state()
            return item

    async def snapshot(self, session_id: str) -> list[StreamMessage]:
        if self._stream_backend is not None:
            return await asyncio.to_thread(
                lambda: [self._message_from_payload(message) for message in self._stream_backend.snapshot(session_id)]
            )
        async with self._lock_for_session(session_id):
            return list(self._buffers.get(session_id, []))

    async def replay_from(self, session_id: str, last_seq: int) -> list[StreamMessage]:
        if self._stream_backend is not None:
            return await asyncio.to_thread(
                lambda: [
                    self._message_from_payload(message)
                    for message in self._stream_backend.replay_from(session_id, last_seq)
                ]
            )
        async with self._lock_for_session(session_id):
            buf = self._buffers.get(session_id, [])
            return [item for item in buf if item.seq > last_seq]

    async def source_snapshot(self, session_id: str, through_seq: int | None = None) -> list[dict]:
        if self._stream_backend is not None:
            return await asyncio.to_thread(self._source_history_records_no_lock, session_id, through_seq=through_seq)
        async with self._lock_for_session(session_id):
            return self._source_history_records_no_lock(session_id, through_seq=through_seq)

    async def replay_window(self, session_id: str) -> tuple[int, int]:
        if self._stream_backend is not None:
            return await asyncio.to_thread(self._stream_backend.replay_window, session_id)
        async with self._lock_for_session(session_id):
            buf = self._buffers.get(session_id, [])
            if not buf:
                return (0, 0)
            return (buf[0].seq, buf[-1].seq)

    async def project_message_for_viewer(self, message: dict, viewer: ViewerContext) -> dict | None:
        session_id = str(message.get("session_id") or viewer.session_id)
        if self._stream_backend is not None:
            return await asyncio.to_thread(self._project_message_for_viewer_no_lock, message, viewer)
        async with self._lock_for_session(session_id):
            return self._project_message_for_viewer_no_lock(message, viewer)

    async def latest_seq(self, session_id: str) -> int:
        if self._stream_backend is not None:
            return await asyncio.to_thread(self._latest_seq_no_lock, session_id)
        async with self._lock_for_session(session_id):
            return self._latest_seq_no_lock(session_id)

    async def latest_view_commit_message_for_viewer(self, session_id: str, viewer: ViewerContext) -> dict | None:
        if self._stream_backend is not None:
            return await asyncio.to_thread(self._latest_view_commit_message_for_viewer_no_lock, session_id, viewer)
        async with self._lock_for_session(session_id):
            return self._latest_view_commit_message_for_viewer_no_lock(session_id, viewer)

    async def emit_latest_view_commit(self, session_id: str) -> StreamMessage | None:
        async with self._lock_for_session(session_id):
            cached = self._load_cached_view_commit_no_lock(
                session_id,
                ViewerContext(role="spectator", session_id=session_id),
            )
            if cached is None:
                log_event(
                    "stream_emit_latest_view_commit",
                    session_id=session_id,
                    action="no_cached_commit",
                    subscriber_count=len(self._subscribers.get(session_id, {})),
                )
                return None
            payload = cached.get("payload")
            if not isinstance(payload, dict):
                log_event(
                    "stream_emit_latest_view_commit",
                    session_id=session_id,
                    action="invalid_cached_payload",
                    subscriber_count=len(self._subscribers.get(session_id, {})),
                )
                return None
            emitted_payload = dict(payload)
            outbox_scopes = self._view_commit_outbox_scopes_no_lock(session_id)
            if outbox_scopes:
                emitted_payload["viewer_outbox_scopes"] = outbox_scopes
            item = self._append_stream_message_no_lock(
                session_id,
                "view_commit",
                emitted_payload,
                server_time_ms=int(time.time() * 1000),
            )
            await self._broadcast(session_id, item)
            if self._stream_backend is None:
                self._persist_stream_state()
            log_event(
                "stream_emit_latest_view_commit",
                session_id=session_id,
                action="broadcast_pointer",
                stream_seq=item.seq,
                commit_seq=self._commit_seq_from_payload(emitted_payload),
                source_event_seq=emitted_payload.get("source_event_seq"),
                subscriber_count=len(self._subscribers.get(session_id, {})),
                outbox_scope_count=len(outbox_scopes),
            )
            return item

    async def delete_session_data(self, session_id: str) -> None:
        async with self._lock_for_session(session_id):
            self._seq.pop(session_id, None)
            self._buffers.pop(session_id, None)
            self._drop_counts.pop(session_id, None)
            if self._stream_backend is not None:
                self._stream_backend.delete_session_data(session_id)
                if self._game_state_store is not None:
                    self._game_state_store.delete_session_data(session_id)
                if self._command_store is not None:
                    self._command_store.delete_session_data(session_id)
            else:
                self._persist_stream_state()
            self._forget_view_commit_cache(session_id)
        async with self._subscriber_lock_for_session(session_id):
            self._subscribers.pop(session_id, None)

    async def backpressure_stats(self, session_id: str) -> dict:
        if self._stream_backend is not None:
            drop_count = await asyncio.to_thread(self._stream_backend.drop_count, session_id)
            async with self._subscriber_lock_for_session(session_id):
                subscriber_count = len(self._subscribers.get(session_id, {}))
            return {"subscriber_count": subscriber_count, "drop_count": drop_count, "queue_size": self._queue_size}
        async with self._lock_for_session(session_id):
            drop_count = self._stream_backend.drop_count(session_id) if self._stream_backend is not None else self._drop_counts.get(session_id, 0)
        async with self._subscriber_lock_for_session(session_id):
            subscriber_count = len(self._subscribers.get(session_id, {}))
            return {
                "subscriber_count": subscriber_count,
                "drop_count": drop_count,
                "queue_size": self._queue_size,
            }

    async def subscribe(self, session_id: str, connection_id: str) -> asyncio.Queue[dict]:
        async with self._subscriber_lock_for_session(session_id):
            queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._queue_size)
            self._subscribers[session_id][connection_id] = queue
            return queue

    async def unsubscribe(self, session_id: str, connection_id: str) -> None:
        async with self._subscriber_lock_for_session(session_id):
            if session_id in self._subscribers:
                self._subscribers[session_id].pop(connection_id, None)
                if not self._subscribers[session_id]:
                    self._subscribers.pop(session_id, None)

    async def _broadcast(self, session_id: str, item: StreamMessage) -> None:
        async with self._subscriber_lock_for_session(session_id):
            self._broadcast_no_lock(session_id, item)

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
    def _with_source_event_id(msg_type: str, payload: dict) -> dict:
        if msg_type in {"view_commit", "snapshot_pulse"}:
            return payload
        if payload.get("event_id"):
            return payload
        next_payload = dict(payload)
        next_payload["event_id"] = new_event_id()
        return next_payload

    @staticmethod
    def _message_from_payload(message: dict) -> StreamMessage:
        return StreamMessage(
            type=str(message.get("type", "event")),
            seq=int(message.get("seq", 0)),
            session_id=str(message.get("session_id", "")),
            server_time_ms=int(message.get("server_time_ms", 0)),
            payload=dict(message.get("payload", {})),
        )

    def _append_stream_message_no_lock(
        self,
        session_id: str,
        msg_type: str,
        payload: dict,
        *,
        server_time_ms: int,
    ) -> StreamMessage:
        if self._stream_backend is not None:
            backend_record = self._stream_backend.publish(
                session_id,
                msg_type,
                payload,
                server_time_ms=server_time_ms,
                max_buffer=self._max_buffer,
            )
            return self._message_from_payload(backend_record)
        self._seq[session_id] += 1
        item = StreamMessage(
            type=msg_type,
            seq=self._seq[session_id],
            session_id=session_id,
            server_time_ms=server_time_ms,
            payload=payload,
        )
        buf = self._buffers[session_id]
        buf.append(item)
        if len(buf) > self._max_buffer:
            del buf[: len(buf) - self._max_buffer]
        return item

    def _broadcast_no_lock(self, session_id: str, item: StreamMessage) -> None:
        subscribers = self._subscribers.get(session_id, {})
        dropped_count = 0
        full_before_count = 0
        max_depth_before = 0
        min_depth_before: int | None = None
        message = item.to_dict()
        for queue in subscribers.values():
            depth_before = queue.qsize()
            max_depth_before = max(max_depth_before, depth_before)
            min_depth_before = depth_before if min_depth_before is None else min(min_depth_before, depth_before)
            if queue.full():
                full_before_count += 1
            dropped = self._offer_latest(queue, message)
            if not dropped:
                continue
            dropped_count += 1
            if self._stream_backend is not None:
                self._stream_backend.increment_drop_count(session_id, 1)
            else:
                self._drop_counts[session_id] += 1
        if item.type == "view_commit":
            log_event(
                "stream_broadcast_delivery",
                session_id=session_id,
                action="offered",
                stream_seq=item.seq,
                commit_seq=self._commit_seq_from_payload(item.payload),
                subscriber_count=len(subscribers),
                dropped_count=dropped_count,
                full_before_count=full_before_count,
                min_depth_before=0 if min_depth_before is None else min_depth_before,
                max_depth_before=max_depth_before,
            )

    def _history_records_no_lock(self, session_id: str) -> list[dict]:
        if self._stream_backend is not None:
            return [message.to_dict() for message in self._messages_from_backend(session_id)]
        return [item.to_dict() for item in self._buffers.get(session_id, [])]

    def _source_history_records_no_lock(self, session_id: str, *, through_seq: int | None = None) -> list[dict]:
        if self._stream_backend is not None and callable(getattr(self._stream_backend, "source_snapshot", None)):
            return list(self._stream_backend.source_snapshot(session_id, through_seq=through_seq))
        records = [
            record
            for record in self._history_records_no_lock(session_id)
            if str(record.get("type") or "") not in {"view_commit", "snapshot_pulse"}
        ]
        if through_seq is None:
            return records
        return [record for record in records if 0 < self._message_seq(record) <= through_seq]

    def _messages_from_backend(self, session_id: str) -> list[StreamMessage]:
        return [self._message_from_payload(message) for message in self._stream_backend.snapshot(session_id)]

    def _project_message_for_viewer_no_lock(self, message: dict, viewer: ViewerContext) -> dict | None:
        msg_type = str(message.get("type") or "")
        if msg_type == "view_commit":
            return self._view_commit_message_for_viewer_no_lock(message, viewer)
        if msg_type == "snapshot_pulse":
            return self._snapshot_pulse_message_for_viewer_no_lock(message, viewer)
        filtered = project_stream_message_for_viewer(message, viewer)
        if filtered is None:
            return None
        return filtered

    def _duplicate_request_message_no_lock(
        self,
        history: list[dict],
        msg_type: str,
        payload: dict,
    ) -> StreamMessage | None:
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return None
        event_type = str(payload.get("event_type") or "").strip()
        if msg_type == "prompt":
            expected_type = "prompt"
            expected_event_type = ""
        elif msg_type == "event" and event_type in {
            "decision_requested",
            "decision_resolved",
            "decision_timeout_fallback",
            "prompt_required",
        }:
            expected_type = "event"
            expected_event_type = event_type
        else:
            return None
        for message in reversed(history):
            if str(message.get("type", "")) != expected_type:
                continue
            message_payload = message.get("payload")
            if not isinstance(message_payload, dict):
                continue
            if str(message_payload.get("request_id") or "").strip() != request_id:
                continue
            if expected_event_type and str(message_payload.get("event_type") or "").strip() != expected_event_type:
                continue
            return self._message_from_payload(message)
        return None

    def _duplicate_idempotency_key_message_no_lock(
        self,
        history: list[dict],
        msg_type: str,
        payload: dict,
    ) -> StreamMessage | None:
        if self._is_request_scoped_message(msg_type, payload):
            return None
        key = self._idempotency_key_from_payload(payload)
        if not key:
            return None
        for message in reversed(history):
            message_payload = message.get("payload")
            if not isinstance(message_payload, dict):
                continue
            if self._idempotency_key_from_payload(message_payload) == key:
                return self._message_from_payload(message)
        return None

    @staticmethod
    def _is_request_scoped_message(msg_type: str, payload: dict) -> bool:
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return False
        if msg_type == "prompt":
            return True
        if msg_type == "event":
            return str(payload.get("event_type") or "").strip() in {
                "decision_requested",
                "decision_resolved",
                "decision_timeout_fallback",
                "prompt_required",
            }
        return False

    @staticmethod
    def _idempotency_key_from_payload(payload: dict) -> str:
        key = str(payload.get("idempotency_key") or "").strip()
        if key:
            return key
        runtime_module = payload.get("runtime_module")
        if isinstance(runtime_module, dict):
            return str(runtime_module.get("idempotency_key") or "").strip()
        return ""

    def _duplicate_round_setup_event_no_lock(
        self,
        history: list[dict],
        msg_type: str,
        payload: dict,
    ) -> StreamMessage | None:
        if msg_type != "event":
            return None
        event_type = str(payload.get("event_type") or "").strip()
        if event_type not in {
            "round_start",
            "weather_reveal",
            "draft_pick",
            "final_character_choice",
            "round_order",
        }:
            return None
        signature = self._round_setup_event_signature(payload)
        for message in reversed(history):
            if str(message.get("type", "")) != "event":
                continue
            message_payload = message.get("payload")
            if not isinstance(message_payload, dict):
                continue
            if str(message_payload.get("event_type") or "").strip() != event_type:
                continue
            if self._round_setup_event_signature(message_payload) == signature:
                return self._message_from_payload(message)
        return None

    @staticmethod
    def _round_setup_event_signature(payload: dict) -> str:
        def normalize(value):
            if isinstance(value, dict):
                return {
                    str(key): normalize(item)
                    for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                    if key not in {"session_id", "step_index", "view_state"}
                }
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        return json.dumps(normalize(payload), ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _message_seq(message: dict) -> int:
        try:
            return int(message.get("seq", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _commit_seq_from_payload(payload: dict) -> int:
        try:
            return int(payload.get("commit_seq", 0) or 0)
        except Exception:
            return 0

    def _latest_view_commit_record_no_lock(self, session_id: str, *, commit_seq: int) -> dict | None:
        if commit_seq <= 0:
            return None
        for message in reversed(self._history_records_no_lock(session_id)):
            if str(message.get("type") or "") != "view_commit":
                continue
            payload = message.get("payload")
            if not isinstance(payload, dict):
                continue
            if self._commit_seq_from_payload(payload) == commit_seq:
                return message
        return None

    def _view_commit_message_for_viewer_no_lock(self, message: dict, viewer: ViewerContext) -> dict | None:
        session_id = str(message.get("session_id") or viewer.session_id or "").strip()
        payload = message.get("payload")
        if not session_id or not isinstance(payload, dict):
            return None
        cached = self._load_cached_view_commit_no_lock(
            session_id,
            viewer,
            expected_commit_seq=self._commit_seq_from_payload(payload),
        )
        if cached is not None:
            cached["seq"] = self._message_seq(message)
            cached["server_time_ms"] = int(message.get("server_time_ms", 0) or cached.get("server_time_ms") or 0)
            return cached
        return None

    def _latest_view_commit_message_for_viewer_no_lock(self, session_id: str, viewer: ViewerContext) -> dict | None:
        cached = self._load_cached_view_commit_no_lock(session_id, viewer)
        if cached is None:
            return None
        payload = cached.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        emitted = self._latest_view_commit_record_no_lock(
            session_id,
            commit_seq=self._commit_seq_from_payload(payload),
        )
        if emitted is not None:
            cached["seq"] = self._message_seq(emitted)
            cached["server_time_ms"] = int(emitted.get("server_time_ms", 0) or cached.get("server_time_ms") or 0)
        return cached

    def _snapshot_pulse_message_for_viewer_no_lock(self, message: dict, viewer: ViewerContext) -> dict | None:
        session_id = str(message.get("session_id") or viewer.session_id or "").strip()
        pulse_payload = message.get("payload")
        if not session_id or not isinstance(pulse_payload, dict):
            return None
        target_player_id = self._optional_int(pulse_payload.get("target_player_id"))
        if target_player_id is not None and not (
            viewer.is_admin or viewer.is_backend or (viewer.is_seat and viewer.player_id == target_player_id)
        ):
            return None
        cached = self._load_cached_view_commit_no_lock(session_id, viewer)
        if cached is None:
            return None
        payload = cached.get("payload")
        if not isinstance(payload, dict):
            return None
        payload = dict(payload)
        pulse = {
            "reason": str(pulse_payload.get("reason") or "snapshot_guardrail"),
            "scope": "player" if target_player_id is not None else "all",
        }
        if target_player_id is not None:
            pulse["target_player_id"] = target_player_id
        payload["snapshot_pulse"] = pulse
        return {
            "type": "snapshot_pulse",
            "seq": self._message_seq(message),
            "session_id": session_id,
            "server_time_ms": int(message.get("server_time_ms", 0) or cached.get("server_time_ms") or 0),
            "payload": payload,
        }

    def _load_cached_view_commit_no_lock(
        self,
        session_id: str,
        viewer: ViewerContext,
        *,
        expected_commit_seq: int | None = None,
    ) -> dict | None:
        if self._game_state_store is None or not callable(getattr(self._game_state_store, "load_view_commit", None)):
            return None
        expected_commit_seq = max(0, int(expected_commit_seq or 0))
        if expected_commit_seq <= 0 and callable(getattr(self._game_state_store, "load_view_commit_index", None)):
            index = self._game_state_store.load_view_commit_index(session_id)
            if isinstance(index, dict):
                expected_commit_seq = self._commit_seq_from_payload({"commit_seq": index.get("latest_commit_seq")})
        candidates: list[tuple[str, int | None]] = []
        if viewer.is_seat and viewer.player_id is not None:
            candidates.append(("player", viewer.player_id))
            candidates.append(("spectator", None))
        elif viewer.is_admin:
            candidates.append(("admin", None))
            candidates.append(("spectator", None))
        else:
            candidates.append(("spectator", None))
            candidates.append(("public", None))
        payload = None
        skipped_stale: list[dict[str, int | str | None]] = []
        missing_candidates: list[str] = []
        for candidate_viewer, candidate_player_id in candidates:
            candidate_label = self._view_commit_candidate_label(candidate_viewer, candidate_player_id)
            cached_payload = self._cached_view_commit_payload(session_id, candidate_label, expected_commit_seq)
            if cached_payload is not None:
                payload = cached_payload
                break
            candidate = self._game_state_store.load_view_commit(
                session_id,
                candidate_viewer,
                player_id=candidate_player_id,
            )
            if not isinstance(candidate, dict):
                missing_candidates.append(candidate_label)
                continue
            candidate_commit_seq = self._commit_seq_from_payload(candidate)
            if expected_commit_seq > 0 and candidate_commit_seq < expected_commit_seq:
                skipped_stale.append(
                    {
                        "viewer": candidate_label,
                        "commit_seq": candidate_commit_seq,
                    }
                )
                continue
            payload = candidate
            self._remember_view_commit_payload(session_id, candidate_label, payload)
            break
        if not isinstance(payload, dict):
            if expected_commit_seq > 0:
                log_event(
                    "stream_cached_view_commit_lookup",
                    session_id=session_id,
                    action="no_usable_candidate",
                    viewer=self._viewer_label(viewer),
                    expected_commit_seq=expected_commit_seq,
                    missing_candidates=missing_candidates,
                    skipped_stale=skipped_stale,
                )
            return None
        return {
            "type": "view_commit",
            "seq": int(payload.get("commit_seq") or 0),
            "session_id": session_id,
            "server_time_ms": int(time.time() * 1000),
            "payload": payload,
        }

    def _cached_view_commit_payload(self, session_id: str, viewer_label: str, expected_commit_seq: int) -> dict | None:
        key = (session_id, viewer_label)
        with self._view_commit_cache_lock:
            payload = self._view_commit_cache.get(key)
            if not isinstance(payload, dict):
                return None
            commit_seq = self._commit_seq_from_payload(payload)
            if expected_commit_seq > 0 and commit_seq < expected_commit_seq:
                self._view_commit_cache.pop(key, None)
                return None
            self._view_commit_cache.move_to_end(key)
            return payload

    def _remember_view_commit_payload(self, session_id: str, viewer_label: str, payload: dict) -> None:
        with self._view_commit_cache_lock:
            self._view_commit_cache[(session_id, viewer_label)] = payload
            self._view_commit_cache.move_to_end((session_id, viewer_label))
            while len(self._view_commit_cache) > self._view_commit_cache_max_entries:
                self._view_commit_cache.popitem(last=False)

    def _forget_view_commit_cache(self, session_id: str) -> None:
        with self._view_commit_cache_lock:
            for key in [key for key in self._view_commit_cache if key[0] == session_id]:
                self._view_commit_cache.pop(key, None)

    @staticmethod
    def _view_commit_candidate_label(viewer: str, player_id: int | None) -> str:
        if viewer == "player":
            return f"player:{player_id}" if player_id is not None else "player"
        return viewer

    @staticmethod
    def _viewer_label(viewer: ViewerContext) -> str:
        if viewer.is_seat:
            return f"player:{viewer.player_id}" if viewer.player_id is not None else "seat"
        if viewer.is_admin:
            return "admin"
        if viewer.is_backend:
            return "backend"
        return viewer.role or "spectator"

    def _view_commit_outbox_scopes_no_lock(self, session_id: str) -> list[str]:
        if self._game_state_store is None or not callable(getattr(self._game_state_store, "load_view_commit_index", None)):
            return []
        index = self._game_state_store.load_view_commit_index(session_id)
        if not isinstance(index, dict):
            return []
        viewers = index.get("view_commit_viewers")
        if not isinstance(viewers, list):
            return []
        scopes = [self._normalize_view_commit_scope(viewer) for viewer in viewers]
        return sorted({scope for scope in scopes if scope})

    @staticmethod
    def _normalize_view_commit_scope(value: object) -> str | None:
        raw = str(value or "").strip().lower()
        if not raw:
            return None
        if raw in {"spectator", "admin", "public"}:
            return raw
        if raw.startswith("player:"):
            player_id = StreamService._optional_int(raw.split(":", 1)[1])
            return f"player:{player_id}" if player_id is not None and player_id > 0 else None
        if raw.isdigit():
            return f"player:{int(raw)}"
        return None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

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

    def _latest_seq_no_lock(self, session_id: str) -> int:
        if self._stream_backend is not None:
            return self._stream_backend.latest_seq(session_id)
        return self._seq.get(session_id, 0)

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
