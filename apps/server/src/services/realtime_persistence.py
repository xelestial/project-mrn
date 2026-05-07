from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from apps.server.src.infra.redis_client import RedisConnection


@dataclass(frozen=True)
class RuntimeLeaseState:
    payload: dict[str, Any]
    recent_fallbacks: list[dict[str, Any]]


class ViewCommitSequenceConflict(RuntimeError):
    """Raised when an authoritative ViewCommit write is not the next cached commit."""


class RedisStreamStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection

    def publish(
        self,
        session_id: str,
        msg_type: str,
        payload: dict[str, Any],
        *,
        server_time_ms: int,
        max_buffer: int,
    ) -> dict[str, Any]:
        client = self._connection.client()
        seq = int(client.incr(self._seq_key(session_id)))
        fields = {
            "seq": str(seq),
            "type": msg_type,
            "session_id": session_id,
            "server_time_ms": str(server_time_ms),
            "payload": _json_dump(payload),
        }
        stream_id = client.xadd(self._stream_key(session_id), fields, maxlen=max(1, int(max_buffer)), approximate=False)
        if msg_type != "view_commit":
            client.xadd(
                self._source_stream_key(session_id),
                fields,
                maxlen=max(1, int(max_buffer)),
                approximate=False,
            )
        return {
            "stream_id": str(stream_id),
            "seq": seq,
            "type": msg_type,
            "session_id": session_id,
            "server_time_ms": server_time_ms,
            "payload": dict(payload),
        }

    def snapshot(self, session_id: str) -> list[dict[str, Any]]:
        return [self._decode_stream_entry(entry_id, fields) for entry_id, fields in self._connection.client().xrange(self._stream_key(session_id))]

    def source_snapshot(self, session_id: str, through_seq: int | None = None) -> list[dict[str, Any]]:
        client = self._connection.client()
        source_entries = client.xrange(self._source_stream_key(session_id))
        if source_entries:
            return [
                self._decode_stream_entry(entry_id, fields)
                for entry_id, fields in source_entries
                if through_seq is None or self._entry_seq(fields) <= int(through_seq)
            ]
        return [
            self._decode_stream_entry(entry_id, fields)
            for entry_id, fields in client.xrange(self._stream_key(session_id))
            if str(fields.get("type") or "") != "view_commit"
            and (through_seq is None or self._entry_seq(fields) <= int(through_seq))
        ]

    def replay_from(self, session_id: str, last_seq: int) -> list[dict[str, Any]]:
        return [message for message in self.snapshot(session_id) if int(message.get("seq", 0)) > int(last_seq)]

    def replay_window(self, session_id: str) -> tuple[int, int]:
        client = self._connection.client()
        oldest_raw = client.xrange(self._stream_key(session_id), count=1)
        latest_raw = client.xrevrange(self._stream_key(session_id), count=1)
        if not oldest_raw or not latest_raw:
            return (0, 0)
        oldest = self._decode_stream_entry(oldest_raw[0][0], oldest_raw[0][1])
        latest = self._decode_stream_entry(latest_raw[0][0], latest_raw[0][1])
        return (int(oldest.get("seq", 0)), int(latest.get("seq", 0)))

    def latest_seq(self, session_id: str) -> int:
        raw = self._connection.client().get(self._seq_key(session_id))
        return int(raw) if isinstance(raw, str) and raw.isdigit() else 0

    def increment_drop_count(self, session_id: str, amount: int = 1) -> None:
        self._connection.client().hincrby(self._drop_count_key(), session_id, max(0, int(amount)))

    def drop_count(self, session_id: str) -> int:
        raw = self._connection.client().hget(self._drop_count_key(), session_id)
        return int(raw) if isinstance(raw, str) and raw.lstrip("-").isdigit() else 0

    def delete_session_data(self, session_id: str) -> None:
        client = self._connection.client()
        client.delete(self._stream_key(session_id), self._source_stream_key(session_id), self._seq_key(session_id))
        client.hdel(self._drop_count_key(), session_id)

    def _stream_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "events")

    def _source_stream_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "source_events")

    def _seq_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "seq")

    def _drop_count_key(self) -> str:
        return self._connection.key("stream", "drop_counts")

    @staticmethod
    def _entry_seq(fields: dict[str, Any]) -> int:
        try:
            return int(fields.get("seq", 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _decode_stream_entry(entry_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = _json_load_dict(str(fields.get("payload", "{}"))) or {}
        return {
            "stream_id": str(entry_id),
            "type": str(fields.get("type", "event")),
            "seq": int(fields.get("seq", 0)),
            "session_id": str(fields.get("session_id", "")),
            "server_time_ms": int(fields.get("server_time_ms", 0)),
            "payload": payload,
        }


class RedisPromptStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection

    def get_pending(self, request_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().hget(self._pending_key(), request_id)
        return _json_load_dict(str(raw)) if raw is not None else None

    def list_pending(self) -> list[dict[str, Any]]:
        payloads = self._connection.client().hgetall(self._pending_key())
        items: list[dict[str, Any]] = []
        for request_id in sorted(payloads):
            parsed = _json_load_dict(payloads[request_id])
            if parsed is not None:
                items.append(parsed)
        return items

    def save_pending(self, request_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().hset(self._pending_key(), request_id, _json_dump(payload))

    def delete_pending(self, request_id: str) -> None:
        self._connection.client().hdel(self._pending_key(), request_id)

    def get_resolved(self, request_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().hget(self._resolved_key(), request_id)
        return _json_load_dict(str(raw)) if raw is not None else None

    def list_resolved(self) -> dict[str, dict[str, Any]]:
        payloads = self._connection.client().hgetall(self._resolved_key())
        result: dict[str, dict[str, Any]] = {}
        for request_id, raw in payloads.items():
            parsed = _json_load_dict(raw)
            if parsed is not None:
                result[str(request_id)] = parsed
        return result

    def save_resolved(self, request_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().hset(self._resolved_key(), request_id, _json_dump(payload))

    def delete_resolved(self, request_id: str) -> None:
        self._connection.client().hdel(self._resolved_key(), request_id)

    def save_decision(self, request_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().hset(self._decisions_key(), request_id, _json_dump(payload))

    def get_decision(self, request_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().hget(self._decisions_key(), request_id)
        return _json_load_dict(str(raw)) if raw is not None else None

    def pop_decision(self, request_id: str) -> dict[str, Any] | None:
        client = self._connection.client()
        raw = client.hget(self._decisions_key(), request_id)
        if raw is None:
            return None
        client.hdel(self._decisions_key(), request_id)
        return _json_load_dict(str(raw))

    def delete_decision(self, request_id: str) -> None:
        self._connection.client().hdel(self._decisions_key(), request_id)

    def accept_decision_with_command(
        self,
        *,
        session_id: str,
        request_id: str,
        decision_payload: dict[str, Any],
        resolved_payload: dict[str, Any],
        command_store: "RedisCommandStore",
        command_type: str,
        command_payload: dict[str, Any],
        server_time_ms: int,
    ) -> dict[str, Any] | None:
        normalized_request_id = str(request_id).strip()
        if not normalized_request_id:
            return None
        client = self._connection.client()
        decision_json = _json_dump(decision_payload)
        resolved_json = _json_dump(resolved_payload)
        command_json = _json_dump(command_payload)
        seen_key = f"{session_id}:{normalized_request_id}"
        if callable(getattr(client, "eval", None)):
            result = client.eval(
                _ACCEPT_PROMPT_DECISION_LUA,
                6,
                self._pending_key(),
                self._decisions_key(),
                self._resolved_key(),
                command_store._seen_key(),
                command_store._seq_key(session_id),
                command_store._stream_key(session_id),
                normalized_request_id,
                decision_json,
                resolved_json,
                seen_key,
                str(command_type),
                str(session_id),
                str(int(server_time_ms or 0)),
                command_json,
            )
            if not result:
                return None
            return {
                "stream_id": str(result[0]),
                "seq": int(result[1]),
                "type": str(command_type),
                "session_id": str(session_id),
                "server_time_ms": int(server_time_ms or 0),
                "payload": dict(command_payload),
            }
        if not bool(client.hsetnx(command_store._seen_key(), seen_key, "1")):
            return None
        seq = int(client.incr(command_store._seq_key(session_id)))
        fields = {
            "seq": str(seq),
            "type": str(command_type),
            "session_id": str(session_id),
            "server_time_ms": str(int(server_time_ms or 0)),
            "payload": command_json,
        }
        pipeline = client.pipeline(transaction=True)
        pipeline.hdel(self._pending_key(), normalized_request_id)
        pipeline.hset(self._decisions_key(), normalized_request_id, decision_json)
        pipeline.hset(self._resolved_key(), normalized_request_id, resolved_json)
        pipeline.xadd(command_store._stream_key(session_id), fields)
        results = pipeline.execute()
        stream_id = str(results[-1]) if results else ""
        return {
            "stream_id": stream_id,
            "seq": seq,
            "type": str(command_type),
            "session_id": str(session_id),
            "server_time_ms": int(server_time_ms or 0),
            "payload": dict(command_payload),
        }

    def delete_session_data(self, session_id: str) -> None:
        for pending in self.list_pending():
            if str(pending.get("session_id", "")) != str(session_id):
                continue
            request_id = str(pending.get("request_id", "")).strip()
            if request_id:
                self.delete_pending(request_id)
                self.delete_decision(request_id)

    def _pending_key(self) -> str:
        return self._connection.key("prompts", "pending")

    def _resolved_key(self) -> str:
        return self._connection.key("prompts", "resolved")

    def _decisions_key(self) -> str:
        return self._connection.key("prompts", "decisions")


class RedisCommandStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection

    def append_command(
        self,
        session_id: str,
        command_type: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        server_time_ms: int | None = None,
    ) -> dict[str, Any] | None:
        normalized_request_id = str(request_id or payload.get("request_id") or "").strip()
        client = self._connection.client()
        seen_key = f"{session_id}:{normalized_request_id}" if normalized_request_id else ""
        fields_payload = _json_dump(dict(payload))
        if callable(getattr(client, "eval", None)):
            result = client.eval(
                _APPEND_COMMAND_LUA,
                3,
                self._seen_key(),
                self._seq_key(session_id),
                self._stream_key(session_id),
                seen_key,
                str(command_type),
                str(session_id),
                str(int(server_time_ms or 0)),
                fields_payload,
            )
            if not result:
                return None
            stream_id = str(result[0])
            seq = int(result[1])
            return {
                "stream_id": stream_id,
                "seq": seq,
                "type": str(command_type),
                "session_id": str(session_id),
                "server_time_ms": int(server_time_ms or 0),
                "payload": dict(payload),
            }
        if normalized_request_id and not bool(client.hsetnx(self._seen_key(), seen_key, "1")):
            return None
        seq = int(client.incr(self._seq_key(session_id)))
        fields = {
            "seq": str(seq),
            "type": str(command_type),
            "session_id": str(session_id),
            "server_time_ms": str(int(server_time_ms or 0)),
            "payload": fields_payload,
        }
        stream_id = client.xadd(self._stream_key(session_id), fields)
        return {
            "stream_id": str(stream_id),
            "seq": seq,
            "type": str(command_type),
            "session_id": str(session_id),
            "server_time_ms": int(server_time_ms or 0),
            "payload": dict(payload),
        }

    def list_commands(self, session_id: str) -> list[dict[str, Any]]:
        return [self._decode_stream_entry(entry_id, fields) for entry_id, fields in self._connection.client().xrange(self._stream_key(session_id))]

    def load_consumer_offset(self, consumer_name: str, session_id: str) -> int:
        raw = self._connection.client().hget(self._offset_key(consumer_name), session_id)
        return int(raw) if isinstance(raw, str) and raw.lstrip("-").isdigit() else 0

    def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
        self._connection.client().hset(self._offset_key(consumer_name), session_id, str(max(0, int(seq))))

    def delete_session_data(self, session_id: str) -> None:
        client = self._connection.client()
        for seen_key in list(client.hgetall(self._seen_key()).keys()):
            if str(seen_key).startswith(f"{session_id}:"):
                client.hdel(self._seen_key(), seen_key)
        for offset_key in list(client.hgetall(self._offset_index_key()).keys()):
            client.hdel(str(offset_key), session_id)
        client.delete(self._stream_key(session_id), self._seq_key(session_id))

    def _stream_key(self, session_id: str) -> str:
        return self._connection.key("commands", session_id, "stream")

    def _seq_key(self, session_id: str) -> str:
        return self._connection.key("commands", session_id, "seq")

    def _seen_key(self) -> str:
        return self._connection.key("commands", "seen")

    def _offset_key(self, consumer_name: str) -> str:
        key = self._connection.key("commands", "offsets", str(consumer_name or "default"))
        self._connection.client().hset(self._offset_index_key(), key, "1")
        return key

    def _offset_index_key(self) -> str:
        return self._connection.key("commands", "offset_indexes")

    @staticmethod
    def _decode_stream_entry(entry_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "stream_id": str(entry_id),
            "seq": int(fields.get("seq", 0)),
            "type": str(fields.get("type", "")),
            "session_id": str(fields.get("session_id", "")),
            "server_time_ms": int(fields.get("server_time_ms", 0)),
            "payload": _json_load_dict(str(fields.get("payload", "{}"))) or {},
        }


class RedisRuntimeStateStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection

    def save_status(self, session_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().hset(self._status_key(), session_id, _json_dump(payload))

    def load_status(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().hget(self._status_key(), session_id)
        return _json_load_dict(str(raw)) if raw is not None else None

    def acquire_lease(self, session_id: str, worker_id: str, ttl_ms: int) -> bool:
        client = self._connection.client()
        lease_key = self._lease_key(session_id)
        acquired = client.set(lease_key, worker_id, nx=True, px=max(1, int(ttl_ms)))
        if bool(acquired):
            return True
        return client.get(lease_key) == worker_id

    def refresh_lease(self, session_id: str, worker_id: str, ttl_ms: int) -> bool:
        client = self._connection.client()
        lease_key = self._lease_key(session_id)
        if callable(getattr(client, "eval", None)):
            return bool(client.eval(_REFRESH_LEASE_LUA, 1, lease_key, worker_id, str(max(1, int(ttl_ms)))))
        if client.get(lease_key) != worker_id:
            return False
        client.set(lease_key, worker_id, px=max(1, int(ttl_ms)))
        return True

    def release_lease(self, session_id: str, worker_id: str) -> bool:
        client = self._connection.client()
        lease_key = self._lease_key(session_id)
        if callable(getattr(client, "eval", None)):
            return bool(client.eval(_RELEASE_LEASE_LUA, 1, lease_key, worker_id))
        if client.get(lease_key) != worker_id:
            return False
        client.delete(lease_key)
        return True

    def lease_owner(self, session_id: str) -> str | None:
        raw = self._connection.client().get(self._lease_key(session_id))
        return str(raw) if raw is not None else None

    def append_fallback(self, session_id: str, record: dict[str, Any], *, max_items: int = 20) -> None:
        client = self._connection.client()
        client.rpush(self._fallbacks_key(session_id), _json_dump(record))
        client.ltrim(self._fallbacks_key(session_id), -max(1, int(max_items)), -1)

    def recent_fallbacks(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        raw_items = self._connection.client().lrange(self._fallbacks_key(session_id), -max(1, int(limit)), -1)
        result: list[dict[str, Any]] = []
        for raw in raw_items:
            parsed = _json_load_dict(str(raw))
            if parsed is not None:
                result.append(parsed)
        return result

    def delete_session_data(self, session_id: str) -> None:
        client = self._connection.client()
        client.hdel(self._status_key(), session_id)
        client.delete(self._fallbacks_key(session_id), self._lease_key(session_id))

    def _status_key(self) -> str:
        return self._connection.key("runtime", "status")

    def _fallbacks_key(self, session_id: str) -> str:
        return self._connection.key("runtime", session_id, "fallbacks")

    def _lease_key(self, session_id: str) -> str:
        return self._connection.key("runtime", session_id, "lease")


class RedisGameStateStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection

    def apply_stream_message(self, message: dict[str, Any]) -> None:
        session_id = str(message.get("session_id", "")).strip()
        if not session_id:
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        seq = int(message.get("seq", 0))
        server_time_ms = int(message.get("server_time_ms", 0))
        message_type = str(message.get("type") or "").strip()
        previous = self.load_checkpoint(session_id) or {}
        if message_type == "view_commit":
            self._apply_view_commit_message(
                session_id,
                payload,
                seq=seq,
                server_time_ms=server_time_ms,
                previous=previous,
            )
            return
        event_type = str(payload.get("event_type") or message.get("type") or "").strip()
        round_index = payload.get("round_index", previous.get("round_index", 0))
        turn_index = payload.get("turn_index", previous.get("turn_index", 0))
        checkpoint = {
            "schema_version": 1,
            "session_id": session_id,
            "latest_seq": seq,
            "latest_event_type": event_type,
            "updated_at_ms": server_time_ms,
            "round_index": int(round_index or 0),
            "turn_index": int(turn_index or 0),
        }
        if previous.get("has_snapshot"):
            checkpoint["has_snapshot"] = bool(previous.get("has_snapshot"))
        if previous.get("has_view_state"):
            checkpoint["has_view_state"] = bool(previous.get("has_view_state"))
        for key in ("latest_commit_seq", "latest_source_event_seq", "has_view_commit"):
            if key in previous:
                checkpoint[key] = previous[key]
        snapshot = payload.get("engine_checkpoint")
        if not isinstance(snapshot, dict):
            snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            checkpoint["has_snapshot"] = True
            self.save_current_state(session_id, snapshot)
        view_state = payload.get("view_state")
        if isinstance(view_state, dict):
            checkpoint["has_view_state"] = True
            self.save_view_state(session_id, view_state)
        self.save_checkpoint(session_id, checkpoint)

    def _apply_view_commit_message(
        self,
        session_id: str,
        payload: dict[str, Any],
        *,
        seq: int,
        server_time_ms: int,
        previous: dict[str, Any],
    ) -> None:
        viewer_payload = payload.get("viewer")
        viewer_payload = viewer_payload if isinstance(viewer_payload, dict) else {}
        viewer_role = str(viewer_payload.get("role") or "spectator").strip().lower()
        player_id = _int_or_none(viewer_payload.get("player_id"))
        runtime = payload.get("runtime")
        runtime = runtime if isinstance(runtime, dict) else {}
        commit_seq = _int_or_default(payload.get("commit_seq"), seq)
        source_event_seq = _int_or_default(payload.get("source_event_seq"), previous.get("latest_source_event_seq", 0))
        round_index = _positive_or_previous(runtime.get("round_index"), previous.get("round_index", 0))
        turn_index = _positive_or_previous(runtime.get("turn_index"), previous.get("turn_index", 0))
        checkpoint = {
            "schema_version": 1,
            "session_id": session_id,
            "latest_seq": seq,
            "latest_event_type": "view_commit",
            "latest_commit_seq": commit_seq,
            "latest_source_event_seq": source_event_seq,
            "updated_at_ms": server_time_ms,
            "round_index": round_index,
            "turn_index": turn_index,
            "has_view_commit": True,
        }
        for key in (
            "has_snapshot",
            "has_view_state",
            "has_pending_actions",
            "has_scheduled_actions",
            "has_pending_turn_completion",
        ):
            if previous.get(key):
                checkpoint[key] = bool(previous.get(key))
        self.save_view_commit(session_id, payload, viewer=viewer_role, player_id=player_id)
        view_state = payload.get("view_state")
        if isinstance(view_state, dict):
            checkpoint["has_view_state"] = True
            if viewer_role in {"spectator", "public", "admin"}:
                self.save_view_state(session_id, view_state)
                if viewer_role != "public":
                    self.save_cached_view_state(session_id, viewer_role, view_state)
            elif viewer_role in {"seat", "player"} and player_id is not None:
                self.save_cached_view_state(session_id, "player", view_state, player_id=player_id)
        self.save_checkpoint(session_id, checkpoint)

    def save_checkpoint(self, session_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().set(self._checkpoint_key(session_id), _json_dump(payload))

    def load_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._checkpoint_key(session_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def save_current_state(self, session_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().set(self._current_state_key(session_id), _json_dump(payload))

    def load_current_state(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._current_state_key(session_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def save_view_state(self, session_id: str, payload: dict[str, Any]) -> None:
        self.save_cached_view_state(session_id, "public", payload)
        self._connection.client().set(self._view_state_key(session_id), _json_dump(payload))

    def load_view_state(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._view_state_key(session_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def save_view_commit(
        self,
        session_id: str,
        payload: dict[str, Any],
        *,
        viewer: str,
        player_id: int | None = None,
    ) -> None:
        normalized_viewer = "player" if str(viewer or "").strip().lower() == "seat" else str(viewer or "spectator").strip().lower()
        if normalized_viewer == "player" and player_id is None:
            return
        commit_seq = _int_or_default(payload.get("commit_seq"), 0)
        if commit_seq <= 0:
            raise ViewCommitSequenceConflict("view commits must have positive commit_seq")
        previous = self.load_view_commit(session_id, normalized_viewer, player_id=player_id) or {}
        index = self.load_view_commit_index(session_id) or {}
        checkpoint = self.load_checkpoint(session_id) or {}
        latest_existing_seq = max(
            _int_or_default(previous.get("commit_seq"), 0) if isinstance(previous, dict) else 0,
            _int_or_default(index.get("latest_commit_seq"), 0) if isinstance(index, dict) else 0,
            _int_or_default(checkpoint.get("latest_commit_seq"), 0) if isinstance(checkpoint, dict) else 0,
        )
        if commit_seq < latest_existing_seq:
            raise ViewCommitSequenceConflict(
                f"stale_view_commit_seq: attempted {commit_seq}, found {latest_existing_seq}"
            )
        self._connection.client().set(
            self._view_commit_key(session_id, normalized_viewer, player_id=player_id),
            _json_dump(payload),
        )
        self._remember_view_commit_viewer(
            session_id,
            normalized_viewer,
            player_id=player_id,
            commit_seq=commit_seq,
            source_event_seq=_int_or_default(payload.get("source_event_seq"), 0),
        )

    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict[str, Any] | None:
        normalized_viewer = "player" if str(viewer or "").strip().lower() == "seat" else str(viewer or "spectator").strip().lower()
        raw = self._connection.client().get(self._view_commit_key(session_id, normalized_viewer, player_id=player_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def save_cached_view_state(self, session_id: str, viewer: str, payload: dict[str, Any], *, player_id: int | None = None) -> None:
        self._connection.client().set(self._cached_view_state_key(session_id, viewer, player_id=player_id), _json_dump(payload))
        self._remember_cached_viewer(session_id, viewer, player_id=player_id)

    def load_cached_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._cached_view_state_key(session_id, viewer, player_id=player_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def save_view_commit_index(self, session_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().set(self._view_commit_index_key(session_id), _json_dump(payload))

    def load_view_commit_index(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._view_commit_index_key(session_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def commit_transition(
        self,
        session_id: str,
        *,
        current_state: dict[str, Any],
        checkpoint: dict[str, Any],
        view_state: dict[str, Any] | None = None,
        view_commits: dict[str, dict[str, Any]] | None = None,
        command_consumer_name: str | None = None,
        command_seq: int | None = None,
        runtime_event_payload: dict[str, Any] | None = None,
        runtime_event_type: str = "event",
        runtime_event_server_time_ms: int | None = None,
        runtime_event_max_buffer: int | None = None,
    ) -> None:
        client = self._connection.client()
        event_payload = dict(runtime_event_payload) if isinstance(runtime_event_payload, dict) else None
        event_server_time_ms = int(runtime_event_server_time_ms or 0)
        event_max_buffer = max(1, int(runtime_event_max_buffer or 0)) if runtime_event_max_buffer else 0
        checkpoint_payload_source = dict(checkpoint)
        event_fields_payload = _json_dump(event_payload) if event_payload is not None else ""
        event_stream_key = self._runtime_stream_key(session_id) if event_payload is not None else ""
        event_seq_key = self._runtime_stream_seq_key(session_id) if event_payload is not None else ""
        view_commit_entries = self._view_commit_entries(session_id, view_commits)
        view_commit_seq = self._view_commit_sequence(view_commit_entries)
        if view_commit_entries:
            checkpoint_payload_source["has_view_commit"] = True
            checkpoint_payload_source["latest_commit_seq"] = max(
                _int_or_default(payload.get("commit_seq"), 0) for _, _, payload in view_commit_entries
            )
            checkpoint_payload_source["latest_source_event_seq"] = max(
                _int_or_default(payload.get("source_event_seq"), 0) for _, _, payload in view_commit_entries
            )
        if command_seq is not None:
            checkpoint_payload_source["processed_command_seq"] = int(command_seq)
            if command_consumer_name:
                checkpoint_payload_source["processed_command_consumer"] = str(command_consumer_name)
        use_lua_commit = callable(getattr(client, "eval", None))
        if view_commit_entries and not use_lua_commit:
            self._assert_expected_previous_view_commit_seq(session_id, view_commit_seq)
        if event_payload is not None and not use_lua_commit:
            event_seq = int(client.incr(event_seq_key))
            checkpoint_payload_source["latest_seq"] = event_seq
            if event_server_time_ms:
                checkpoint_payload_source["updated_at_ms"] = event_server_time_ms
        current_payload = _json_dump(current_state)
        checkpoint_payload = _json_dump(checkpoint_payload_source)
        view_payload = _json_dump(view_state) if isinstance(view_state, dict) else ""
        offset_key = self._command_offset_key(command_consumer_name) if command_consumer_name else ""
        offset_index_key = self._command_offset_index_key() if command_consumer_name else ""
        offset_seq = str(max(0, int(command_seq))) if command_seq is not None else ""
        if use_lua_commit and view_commit_entries:
            view_commit_index_payload = self._view_commit_index_payload_for_entries(
                session_id,
                view_commit_entries,
                checkpoint_payload_source=checkpoint_payload_source,
            )
            keys = [
                self._current_state_key(session_id),
                self._checkpoint_key(session_id),
                self._view_state_key(session_id),
                self._cached_view_state_key(session_id, "public"),
                offset_key,
                offset_index_key,
                event_seq_key,
                event_stream_key,
                self._view_commit_index_key(session_id),
                *(key for _, key, _ in view_commit_entries),
            ]
            args = [
                current_payload,
                checkpoint_payload,
                view_payload,
                str(session_id),
                offset_seq,
                str(runtime_event_type or "event"),
                str(event_server_time_ms),
                event_fields_payload,
                str(event_max_buffer),
                str(max(0, int(view_commit_seq or 0) - 1)),
                str(view_commit_seq or 0),
                view_commit_index_payload,
                str(len(view_commit_entries)),
                *(_json_dump(payload) for _, _, payload in view_commit_entries),
            ]
            try:
                client.eval(
                    _COMMIT_GAME_TRANSITION_WITH_VIEW_COMMITS_LUA,
                    len(keys),
                    *keys,
                    *args,
                )
            except Exception as exc:
                if "view_commit_seq_conflict" in str(exc) or "invalid_view_commit_seq" in str(exc):
                    raise ViewCommitSequenceConflict(str(exc)) from exc
                raise
            return
        if use_lua_commit:
            client.eval(
                _COMMIT_GAME_TRANSITION_LUA,
                8,
                self._current_state_key(session_id),
                self._checkpoint_key(session_id),
                self._view_state_key(session_id),
                self._cached_view_state_key(session_id, "public"),
                offset_key,
                offset_index_key,
                event_seq_key,
                event_stream_key,
                current_payload,
                checkpoint_payload,
                view_payload,
                str(session_id),
                offset_seq,
                str(runtime_event_type or "event"),
                str(event_server_time_ms),
                event_fields_payload,
                str(event_max_buffer),
            )
            return
        pipeline = client.pipeline(transaction=True)
        pipeline.set(self._current_state_key(session_id), current_payload)
        pipeline.set(self._checkpoint_key(session_id), checkpoint_payload)
        if isinstance(view_state, dict):
            pipeline.set(self._view_state_key(session_id), view_payload)
            pipeline.set(self._cached_view_state_key(session_id, "public"), view_payload)
        for _, key, payload in view_commit_entries:
            pipeline.set(key, _json_dump(payload))
        if view_commit_entries:
            view_commit_index = _json_load_dict(
                self._view_commit_index_payload_for_entries(
                    session_id,
                    view_commit_entries,
                    checkpoint_payload_source=checkpoint_payload_source,
                )
            ) or {"schema_version": 1}
            pipeline.set(self._view_commit_index_key(session_id), _json_dump(view_commit_index))
        if offset_key and offset_seq:
            pipeline.hset(offset_index_key, offset_key, "1")
            pipeline.hset(offset_key, session_id, offset_seq)
        if event_payload is not None:
            fields = {
                "seq": str(checkpoint_payload_source["latest_seq"]),
                "type": str(runtime_event_type or "event"),
                "session_id": str(session_id),
                "server_time_ms": str(event_server_time_ms),
                "payload": event_fields_payload,
            }
            kwargs = {"maxlen": event_max_buffer, "approximate": False} if event_max_buffer else {}
            pipeline.xadd(event_stream_key, fields, **kwargs)
        pipeline.execute()

    def _view_commit_sequence(self, view_commit_entries: list[tuple[str, str, dict[str, Any]]]) -> int | None:
        if not view_commit_entries:
            return None
        sequences = {_int_or_default(payload.get("commit_seq"), 0) for _, _, payload in view_commit_entries}
        if len(sequences) != 1:
            raise ViewCommitSequenceConflict("view commits in one transition must share commit_seq")
        commit_seq = next(iter(sequences))
        if commit_seq <= 0:
            raise ViewCommitSequenceConflict("view commits must have positive commit_seq")
        return commit_seq

    def _assert_expected_previous_view_commit_seq(self, session_id: str, view_commit_seq: int | None) -> None:
        if view_commit_seq is None:
            return
        expected_previous = max(0, int(view_commit_seq) - 1)
        current_checkpoint = self.load_checkpoint(session_id) or {}
        current_index = self.load_view_commit_index(session_id) or {}
        current_seq = max(
            _int_or_default(current_checkpoint.get("latest_commit_seq"), 0),
            _int_or_default(current_index.get("latest_commit_seq"), 0),
        )
        if current_seq != expected_previous:
            raise ViewCommitSequenceConflict(
                f"view_commit_seq_conflict: expected previous {expected_previous}, found {current_seq}"
            )

    def _view_commit_index_payload_for_entries(
        self,
        session_id: str,
        view_commit_entries: list[tuple[str, str, dict[str, Any]]],
        *,
        checkpoint_payload_source: dict[str, Any],
    ) -> str:
        view_commit_index = self.load_view_commit_index(session_id) or {"schema_version": 1}
        viewers = view_commit_index.get("view_commit_viewers")
        existing = {str(item) for item in viewers} if isinstance(viewers, list) else set()
        existing.update(label for label, _, _ in view_commit_entries)
        view_commit_index["view_commit_viewers"] = sorted(existing)
        view_commit_index["latest_commit_seq"] = checkpoint_payload_source.get("latest_commit_seq")
        view_commit_index["latest_source_event_seq"] = checkpoint_payload_source.get("latest_source_event_seq")
        return _json_dump(view_commit_index)

    def _view_commit_entries(
        self,
        session_id: str,
        view_commits: dict[str, dict[str, Any]] | None,
    ) -> list[tuple[str, str, dict[str, Any]]]:
        if not isinstance(view_commits, dict):
            return []
        entries: list[tuple[str, str, dict[str, Any]]] = []
        seen: set[str] = set()
        for raw_label, raw_payload in view_commits.items():
            if not isinstance(raw_payload, dict):
                continue
            label = self._normalize_view_commit_label(raw_label, raw_payload)
            if label is None or label in seen:
                continue
            key = self._view_commit_key_from_label(session_id, label)
            if not key:
                continue
            entries.append((label, key, dict(raw_payload)))
            seen.add(label)
        return entries

    @staticmethod
    def _normalize_view_commit_label(raw_label: Any, payload: dict[str, Any]) -> str | None:
        label = str(raw_label or "").strip().lower()
        if label in {"public", "spectator", "admin"}:
            return label
        if label.startswith("seat:"):
            label = f"player:{label.split(':', 1)[1]}"
        if label.startswith("player:"):
            player_id = _int_or_none(label.split(":", 1)[1])
            return f"player:{player_id}" if player_id is not None else None
        viewer = payload.get("viewer")
        viewer = viewer if isinstance(viewer, dict) else {}
        role = str(viewer.get("role") or label or "spectator").strip().lower()
        if role == "seat":
            role = "player"
        if role in {"public", "spectator", "admin"}:
            return role
        if role == "player":
            player_id = _int_or_none(viewer.get("player_id") or viewer.get("seat") or payload.get("player_id"))
            return f"player:{player_id}" if player_id is not None else None
        return None

    def delete_session_data(self, session_id: str) -> None:
        view_commit_index = self.load_view_commit_index(session_id) or {}
        cached_view_state_keys = [
            self._cached_view_state_key(session_id, "public"),
            self._cached_view_state_key(session_id, "spectator"),
            self._cached_view_state_key(session_id, "admin"),
            self._view_commit_index_key(session_id),
        ]
        view_commit_keys = [
            self._view_commit_key(session_id, "public"),
            self._view_commit_key(session_id, "spectator"),
            self._view_commit_key(session_id, "admin"),
        ]
        cached_viewers = view_commit_index.get("cached_viewers")
        if isinstance(cached_viewers, list):
            for viewer in cached_viewers:
                key = self._cached_view_state_key_from_label(session_id, str(viewer))
                if key:
                    cached_view_state_keys.append(key)
        view_commit_viewers = view_commit_index.get("view_commit_viewers")
        if isinstance(view_commit_viewers, list):
            for viewer in view_commit_viewers:
                key = self._view_commit_key_from_label(session_id, str(viewer))
                if key:
                    view_commit_keys.append(key)
        self._connection.client().delete(
            self._checkpoint_key(session_id),
            self._current_state_key(session_id),
            self._view_state_key(session_id),
            *cached_view_state_keys,
            *view_commit_keys,
        )

    def _checkpoint_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "checkpoint")

    def _current_state_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "current_state")

    def _view_state_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "view_state")

    def _view_commit_key(self, session_id: str, viewer: str, *, player_id: int | None = None) -> str:
        normalized = str(viewer or "spectator").strip().lower()
        if normalized == "seat":
            normalized = "player"
        if normalized == "player":
            if player_id is None:
                raise ValueError("player_id is required for player view_commit")
            return self._connection.key("game", session_id, "view_commit", "player", str(int(player_id)))
        if normalized not in {"public", "spectator", "admin"}:
            raise ValueError(f"unsupported view_commit viewer: {viewer}")
        return self._connection.key("game", session_id, "view_commit", normalized)

    def _cached_view_state_key(self, session_id: str, viewer: str, *, player_id: int | None = None) -> str:
        normalized = str(viewer or "public").strip().lower()
        if normalized == "player":
            if player_id is None:
                raise ValueError("player_id is required for player cached view_state")
            return self._connection.key("game", session_id, "view_state", "player", str(int(player_id)))
        if normalized not in {"public", "spectator", "admin"}:
            raise ValueError(f"unsupported cached view_state viewer: {viewer}")
        return self._connection.key("game", session_id, "view_state", normalized)

    def _view_commit_index_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "view_commit_index")

    def _cached_view_state_key_from_label(self, session_id: str, label: str) -> str | None:
        normalized = str(label or "").strip().lower()
        if normalized in {"public", "spectator", "admin"}:
            return self._cached_view_state_key(session_id, normalized)
        if normalized.startswith("player:"):
            try:
                player_id = int(normalized.split(":", 1)[1])
            except Exception:
                return None
            return self._cached_view_state_key(session_id, "player", player_id=player_id)
        return None

    def _view_commit_key_from_label(self, session_id: str, label: str) -> str | None:
        normalized = str(label or "").strip().lower()
        if normalized in {"public", "spectator", "admin"}:
            return self._view_commit_key(session_id, normalized)
        if normalized.startswith("player:"):
            try:
                player_id = int(normalized.split(":", 1)[1])
            except Exception:
                return None
            return self._view_commit_key(session_id, "player", player_id=player_id)
        return None

    def _remember_view_commit_viewer(
        self,
        session_id: str,
        viewer: str,
        *,
        player_id: int | None = None,
        commit_seq: int | None = None,
        source_event_seq: int | None = None,
    ) -> None:
        label = self._viewer_label(viewer, player_id=player_id)
        if label is None:
            return
        checkpoint = self.load_view_commit_index(session_id) or {"schema_version": 1}
        viewers = checkpoint.get("view_commit_viewers")
        existing = {str(item) for item in viewers} if isinstance(viewers, list) else set()
        existing.add(label)
        checkpoint["view_commit_viewers"] = sorted(existing)
        if commit_seq is not None:
            checkpoint["latest_commit_seq"] = max(
                _int_or_default(checkpoint.get("latest_commit_seq"), 0),
                int(commit_seq),
            )
        if source_event_seq is not None:
            checkpoint["latest_source_event_seq"] = max(
                _int_or_default(checkpoint.get("latest_source_event_seq"), 0),
                int(source_event_seq),
            )
        self.save_view_commit_index(session_id, checkpoint)

    def _remember_cached_viewer(self, session_id: str, viewer: str, *, player_id: int | None = None) -> None:
        label = self._viewer_label(viewer, player_id=player_id)
        if label is None:
            return
        index = self.load_view_commit_index(session_id) or {"schema_version": 1}
        viewers = index.get("cached_viewers")
        existing = {str(item) for item in viewers} if isinstance(viewers, list) else set()
        existing.add(label)
        index["cached_viewers"] = sorted(existing)
        self.save_view_commit_index(session_id, index)

    @staticmethod
    def _viewer_label(viewer: str, *, player_id: int | None = None) -> str | None:
        normalized = str(viewer or "").strip().lower()
        if normalized == "seat":
            normalized = "player"
        if normalized in {"public", "spectator", "admin"}:
            return normalized
        if normalized == "player" and player_id is not None:
            return f"player:{int(player_id)}"
        return None

    def _command_offset_key(self, consumer_name: str | None) -> str:
        return self._connection.key("commands", "offsets", str(consumer_name or "default"))

    def _command_offset_index_key(self) -> str:
        return self._connection.key("commands", "offset_indexes")

    def _runtime_stream_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "events")

    def _runtime_stream_seq_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "seq")


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default or 0)


def _positive_or_previous(value: Any, previous: Any) -> int:
    parsed = _int_or_default(value, 0)
    previous_parsed = _int_or_default(previous, 0)
    if parsed > 0:
        return parsed
    if previous_parsed > 0:
        return previous_parsed
    return parsed


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _json_load_dict(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


_APPEND_COMMAND_LUA = """
local seen_key = ARGV[1]
if seen_key ~= "" then
  if redis.call("HSETNX", KEYS[1], seen_key, "1") == 0 then
    return false
  end
end
local seq = redis.call("INCR", KEYS[2])
local stream_id = redis.call(
  "XADD",
  KEYS[3],
  "*",
  "seq",
  tostring(seq),
  "type",
  ARGV[2],
  "session_id",
  ARGV[3],
  "server_time_ms",
  ARGV[4],
  "payload",
  ARGV[5]
)
return {stream_id, tostring(seq)}
"""

_REFRESH_LEASE_LUA = """
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
  return 0
end
redis.call("SET", KEYS[1], ARGV[1], "PX", tonumber(ARGV[2]))
return 1
"""

_RELEASE_LEASE_LUA = """
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
  return 0
end
redis.call("DEL", KEYS[1])
return 1
"""

_COMMIT_GAME_TRANSITION_LUA = """
local checkpoint_payload = ARGV[2]
if ARGV[8] ~= "" then
  local seq = redis.call("INCR", KEYS[7])
  local checkpoint = cjson.decode(ARGV[2])
  checkpoint["latest_seq"] = seq
  if ARGV[7] ~= "0" then
    checkpoint["updated_at_ms"] = tonumber(ARGV[7])
  end
  checkpoint_payload = cjson.encode(checkpoint)
  if ARGV[9] ~= "0" then
    redis.call(
      "XADD",
      KEYS[8],
      "MAXLEN",
      "=",
      tonumber(ARGV[9]),
      "*",
      "seq",
      tostring(seq),
      "type",
      ARGV[6],
      "session_id",
      ARGV[4],
      "server_time_ms",
      ARGV[7],
      "payload",
      ARGV[8]
    )
  else
    redis.call(
      "XADD",
      KEYS[8],
      "*",
      "seq",
      tostring(seq),
      "type",
      ARGV[6],
      "session_id",
      ARGV[4],
      "server_time_ms",
      ARGV[7],
      "payload",
      ARGV[8]
    )
  end
end
redis.call("SET", KEYS[1], ARGV[1])
redis.call("SET", KEYS[2], checkpoint_payload)
if ARGV[3] ~= "" then
  redis.call("SET", KEYS[3], ARGV[3])
  redis.call("SET", KEYS[4], ARGV[3])
end
if ARGV[5] ~= "" then
  redis.call("HSET", KEYS[6], KEYS[5], "1")
  redis.call("HSET", KEYS[5], ARGV[4], ARGV[5])
end
return 1
"""

_COMMIT_GAME_TRANSITION_WITH_VIEW_COMMITS_LUA = """
local expected_previous_commit_seq = tonumber(ARGV[10]) or 0
local new_commit_seq = tonumber(ARGV[11]) or 0
if new_commit_seq <= 0 then
  return redis.error_reply("invalid_view_commit_seq")
end

local current_commit_seq = 0
local current_checkpoint_payload = redis.call("GET", KEYS[2])
if current_checkpoint_payload then
  local ok, current_checkpoint = pcall(cjson.decode, current_checkpoint_payload)
  if ok and type(current_checkpoint) == "table" then
    current_commit_seq = tonumber(current_checkpoint["latest_commit_seq"] or 0) or 0
  end
end
local current_index_payload = redis.call("GET", KEYS[9])
if current_index_payload then
  local ok, current_index = pcall(cjson.decode, current_index_payload)
  if ok and type(current_index) == "table" then
    local indexed_commit_seq = tonumber(current_index["latest_commit_seq"] or 0) or 0
    if indexed_commit_seq > current_commit_seq then
      current_commit_seq = indexed_commit_seq
    end
  end
end
if current_commit_seq ~= expected_previous_commit_seq then
  return redis.error_reply("view_commit_seq_conflict")
end

local checkpoint_payload = ARGV[2]
if ARGV[8] ~= "" then
  local seq = redis.call("INCR", KEYS[7])
  local checkpoint = cjson.decode(ARGV[2])
  checkpoint["latest_seq"] = seq
  if ARGV[7] ~= "0" then
    checkpoint["updated_at_ms"] = tonumber(ARGV[7])
  end
  checkpoint_payload = cjson.encode(checkpoint)
  if ARGV[9] ~= "0" then
    redis.call(
      "XADD",
      KEYS[8],
      "MAXLEN",
      "=",
      tonumber(ARGV[9]),
      "*",
      "seq",
      tostring(seq),
      "type",
      ARGV[6],
      "session_id",
      ARGV[4],
      "server_time_ms",
      ARGV[7],
      "payload",
      ARGV[8]
    )
  else
    redis.call(
      "XADD",
      KEYS[8],
      "*",
      "seq",
      tostring(seq),
      "type",
      ARGV[6],
      "session_id",
      ARGV[4],
      "server_time_ms",
      ARGV[7],
      "payload",
      ARGV[8]
    )
  end
end
redis.call("SET", KEYS[1], ARGV[1])
redis.call("SET", KEYS[2], checkpoint_payload)
if ARGV[3] ~= "" then
  redis.call("SET", KEYS[3], ARGV[3])
  redis.call("SET", KEYS[4], ARGV[3])
end
if ARGV[5] ~= "" then
  redis.call("HSET", KEYS[6], KEYS[5], "1")
  redis.call("HSET", KEYS[5], ARGV[4], ARGV[5])
end
if ARGV[12] ~= "" then
  redis.call("SET", KEYS[9], ARGV[12])
end
local view_commit_count = tonumber(ARGV[13]) or 0
for i = 1, view_commit_count do
  redis.call("SET", KEYS[9 + i], ARGV[13 + i])
end
return 1
"""

_ACCEPT_PROMPT_DECISION_LUA = """
if redis.call("HEXISTS", KEYS[1], ARGV[1]) == 0 then
  return nil
end
if redis.call("HSETNX", KEYS[4], ARGV[4], "1") == 0 then
  return nil
end
redis.call("HDEL", KEYS[1], ARGV[1])
redis.call("HSET", KEYS[2], ARGV[1], ARGV[2])
redis.call("HSET", KEYS[3], ARGV[1], ARGV[3])
local seq = redis.call("INCR", KEYS[5])
local stream_id = redis.call(
  "XADD",
  KEYS[6],
  "*",
  "seq",
  tostring(seq),
  "type",
  ARGV[5],
  "session_id",
  ARGV[6],
  "server_time_ms",
  ARGV[7],
  "payload",
  ARGV[8]
)
return {stream_id, seq}
"""
