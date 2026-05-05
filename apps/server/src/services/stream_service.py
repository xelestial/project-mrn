from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass

from apps.server.src.domain.runtime_semantic_guard import validate_stream_payload
from apps.server.src.domain.visibility import ViewerContext, project_stream_message_for_viewer
from apps.server.src.domain.view_state import project_view_state
from apps.server.src.services.persistence import StreamStore


_PROJECTION_SCHEMA_VERSION = 1


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
            validate_stream_payload(history=history, msg_type=msg_type, payload=enriched_payload)
            duplicate = self._duplicate_request_message_no_lock(history, msg_type, enriched_payload)
            if duplicate is None:
                duplicate = self._duplicate_idempotency_key_message_no_lock(history, msg_type, enriched_payload)
            if duplicate is None:
                duplicate = self._duplicate_round_setup_event_no_lock(history, msg_type, enriched_payload)
            if duplicate is not None:
                return duplicate
            pending_record = {
                "type": msg_type,
                "seq": self._seq[session_id] + 1,
                "session_id": session_id,
                "server_time_ms": int(time.time() * 1000),
                "payload": enriched_payload,
            }
            projected = project_view_state([*history, pending_record], viewer=ViewerContext(role="spectator", session_id=session_id))
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
                if projected:
                    self._cache_projected_view_state_no_lock(
                        session_id,
                        ViewerContext(role="spectator", session_id=session_id),
                        projected,
                        latest_seq=item.seq,
                        server_time_ms=item.server_time_ms,
                    )
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

    async def project_message_for_viewer(self, message: dict, viewer: ViewerContext) -> dict | None:
        async with self._lock:
            filtered = project_stream_message_for_viewer(message, viewer)
            if filtered is None:
                return None
            session_id = str(message.get("session_id") or viewer.session_id or "").strip()
            records = self._history_records_no_lock(session_id) if session_id else [message]
            seq = self._message_seq(message)
            if seq > 0:
                records = [record for record in records if 0 < self._message_seq(record) <= seq]
            if not any(self._message_seq(record) == seq and seq > 0 for record in records):
                records.append(message)
            projected = project_view_state(records, viewer=viewer)
            if projected:
                filtered_payload = filtered.get("payload")
                if isinstance(filtered_payload, dict):
                    filtered_payload["view_state"] = projected
                if self._game_state_store is not None:
                    self._cache_projected_view_state_no_lock(
                        session_id,
                        viewer,
                        projected,
                        latest_seq=seq,
                        server_time_ms=int(message.get("server_time_ms", 0) or 0),
                    )
            return filtered

    async def latest_seq(self, session_id: str) -> int:
        async with self._lock:
            return self._latest_seq_no_lock(session_id)

    async def latest_view_state_for_viewer(self, session_id: str, viewer: ViewerContext) -> dict:
        async with self._lock:
            cached = self._load_cached_projected_view_state_no_lock(
                session_id,
                viewer,
                latest_seq=self._latest_seq_no_lock(session_id),
            )
            if isinstance(cached, dict):
                return cached
            projected = project_view_state(self._history_records_no_lock(session_id), viewer=viewer)
            if projected:
                self._cache_projected_view_state_no_lock(
                    session_id,
                    viewer,
                    projected,
                    latest_seq=self._latest_seq_no_lock(session_id),
                    server_time_ms=int(time.time() * 1000),
                )
            return projected or {}

    async def rebuild_latest_view_state_for_viewer(self, session_id: str, viewer: ViewerContext) -> dict:
        async with self._lock:
            latest_seq = self._latest_seq_no_lock(session_id)
            projected = project_view_state(self._history_records_no_lock(session_id), viewer=viewer)
            if projected:
                self._cache_projected_view_state_no_lock(
                    session_id,
                    viewer,
                    projected,
                    latest_seq=latest_seq,
                    server_time_ms=int(time.time() * 1000),
                )
            return projected or {}

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

    def _cache_projected_view_state_no_lock(
        self,
        session_id: str,
        viewer: ViewerContext,
        view_state: dict,
        *,
        latest_seq: int,
        server_time_ms: int,
    ) -> None:
        if not session_id or not isinstance(view_state, dict) or not view_state:
            return
        save_projected = getattr(self._game_state_store, "save_projected_view_state", None)
        save_checkpoint = getattr(self._game_state_store, "save_projection_checkpoint", None)
        load_checkpoint = getattr(self._game_state_store, "load_projection_checkpoint", None)
        if not callable(save_projected):
            return
        viewer_label = self._projection_viewer_label(viewer)
        if not viewer_label:
            return
        try:
            if viewer_label.startswith("player:"):
                save_projected(session_id, "player", view_state, player_id=viewer.player_id)
            else:
                save_projected(session_id, viewer_label, view_state)
        except Exception:
            return
        if not callable(save_checkpoint):
            return
        previous = load_checkpoint(session_id) if callable(load_checkpoint) else None
        projected_viewers = set()
        projected_viewer_seqs: dict[str, int] = {}
        if isinstance(previous, dict) and isinstance(previous.get("projected_viewers"), list):
            projected_viewers.update(str(item) for item in previous["projected_viewers"])
        if isinstance(previous, dict) and isinstance(previous.get("projected_viewer_seqs"), dict):
            for key, value in previous["projected_viewer_seqs"].items():
                try:
                    projected_viewer_seqs[str(key)] = int(value)
                except Exception:
                    continue
        projected_viewers.add(viewer_label)
        projected_viewer_seqs[viewer_label] = int(latest_seq or 0)
        checkpoint = {
            "schema_version": 1,
            "session_id": session_id,
            "latest_seq": int(latest_seq or 0),
            "generated_at_ms": int(server_time_ms or 0),
            "projection_schema_version": _PROJECTION_SCHEMA_VERSION,
            "projected_viewers": sorted(projected_viewers),
            "projected_viewer_seqs": projected_viewer_seqs,
        }
        try:
            save_checkpoint(session_id, checkpoint)
        except Exception:
            return

    def _load_cached_projected_view_state_no_lock(
        self,
        session_id: str,
        viewer: ViewerContext,
        *,
        latest_seq: int,
    ) -> dict | None:
        if not session_id:
            return None
        load_projected = getattr(self._game_state_store, "load_projected_view_state", None)
        load_checkpoint = getattr(self._game_state_store, "load_projection_checkpoint", None)
        if not callable(load_projected):
            return None
        viewer_label = self._projection_viewer_label(viewer)
        if not viewer_label:
            return None
        if callable(load_checkpoint):
            checkpoint = load_checkpoint(session_id)
            if not self._projection_cache_is_fresh(checkpoint, viewer_label, latest_seq):
                return None
        try:
            if viewer_label.startswith("player:"):
                cached = load_projected(session_id, "player", player_id=viewer.player_id)
            else:
                cached = load_projected(session_id, viewer_label)
        except Exception:
            return None
        return cached if isinstance(cached, dict) else None

    @staticmethod
    def _projection_cache_is_fresh(checkpoint: object, viewer_label: str, latest_seq: int) -> bool:
        if not isinstance(checkpoint, dict):
            return False
        viewer_seqs = checkpoint.get("projected_viewer_seqs")
        if isinstance(viewer_seqs, dict):
            try:
                return int(viewer_seqs.get(viewer_label, -1)) >= int(latest_seq or 0)
            except Exception:
                return False
        if int(latest_seq or 0) == 0 and isinstance(checkpoint.get("projected_viewers"), list):
            return viewer_label in {str(item) for item in checkpoint["projected_viewers"]}
        return False

    @staticmethod
    def _projection_viewer_label(viewer: ViewerContext) -> str | None:
        if viewer.is_admin:
            return "admin"
        if viewer.is_seat and viewer.player_id is not None:
            return f"player:{int(viewer.player_id)}"
        if viewer.is_spectator:
            return "spectator"
        return None

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
