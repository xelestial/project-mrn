from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from apps.server.src.infra.redis_client import RedisConnection

DEBUG_REDIS_RETENTION_SECONDS = 3600
DEBUG_REDIS_RECORD_LIMIT = 20


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
        persisted_payload = self._persisted_stream_payload(msg_type, payload)
        fields = {
            "seq": str(seq),
            "type": msg_type,
            "session_id": session_id,
            "server_time_ms": str(server_time_ms),
            "payload": _json_dump(persisted_payload),
        }
        stream_id = client.xadd(self._stream_key(session_id), fields, maxlen=max(1, int(max_buffer)), approximate=False)
        if msg_type not in {"view_commit", "snapshot_pulse"}:
            client.xadd(
                self._source_stream_key(session_id),
                fields,
                maxlen=max(1, int(max_buffer)),
                approximate=False,
            )
            self._remember_event_mapping(
                session_id,
                seq=seq,
                msg_type=msg_type,
                payload=payload,
                server_time_ms=server_time_ms,
            )
        self._remember_viewer_outbox(
            session_id,
            seq=seq,
            msg_type=msg_type,
            payload=payload,
            server_time_ms=server_time_ms,
        )
        return {
            "stream_id": str(stream_id),
            "seq": seq,
            "type": msg_type,
            "session_id": session_id,
            "server_time_ms": server_time_ms,
            "payload": dict(payload),
        }

    @staticmethod
    def _persisted_stream_payload(msg_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if msg_type != "view_commit":
            return payload
        viewer = payload.get("viewer") if isinstance(payload.get("viewer"), dict) else {}
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        prompt = runtime.get("active_prompt") if isinstance(runtime.get("active_prompt"), dict) else {}
        compact_runtime = {
            key: runtime.get(key)
            for key in (
                "status",
                "round_index",
                "turn_index",
                "turn_label",
                "current_player_id",
                "active_frame_id",
                "active_module_id",
                "active_module_type",
                "active_module_cursor",
            )
            if runtime.get(key) is not None
        }
        if prompt:
            compact_runtime["active_prompt"] = {
                key: prompt.get(key)
                for key in (
                    "request_id",
                    "prompt_instance_id",
                    "player_id",
                    "request_type",
                    "view_commit_seq",
                    "resume_token",
                )
                if prompt.get(key) is not None
            }
        return {
            "schema_version": 1,
            "compact": True,
            "storage": "view_commit_pointer",
            "commit_seq": payload.get("commit_seq"),
            "source_event_seq": payload.get("source_event_seq"),
            "round_index": payload.get("round_index") or runtime.get("round_index"),
            "turn_index": payload.get("turn_index") or runtime.get("turn_index"),
            "turn_label": payload.get("turn_label") or runtime.get("turn_label"),
            "viewer": {
                key: viewer.get(key)
                for key in ("role", "player_id", "seat", "viewer_id")
                if viewer.get(key) is not None
            },
            "runtime": compact_runtime,
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
            if str(fields.get("type") or "") not in {"view_commit", "snapshot_pulse"}
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

    def load_event_index(self, session_id: str, event_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().hget(self._event_index_key(session_id), str(event_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def load_viewer_outbox_index(self, session_id: str) -> list[dict[str, Any]]:
        payloads = self._connection.client().hgetall(self._viewer_outbox_index_key(session_id))
        rows: list[dict[str, Any]] = []
        for key in sorted(payloads, key=lambda item: str(item)):
            parsed = _json_load_dict(str(payloads[key]))
            if parsed is not None:
                rows.append(parsed)
        return rows

    def increment_drop_count(self, session_id: str, amount: int = 1) -> None:
        self._connection.client().hincrby(self._drop_count_key(), session_id, max(0, int(amount)))

    def drop_count(self, session_id: str) -> int:
        raw = self._connection.client().hget(self._drop_count_key(), session_id)
        return int(raw) if isinstance(raw, str) and raw.lstrip("-").isdigit() else 0

    def delete_session_data(self, session_id: str) -> None:
        client = self._connection.client()
        client.delete(
            self._stream_key(session_id),
            self._source_stream_key(session_id),
            self._seq_key(session_id),
            self._event_index_key(session_id),
            self._viewer_outbox_index_key(session_id),
        )
        client.hdel(self._drop_count_key(), session_id)

    def _remember_event_mapping(
        self,
        session_id: str,
        *,
        seq: int,
        msg_type: str,
        payload: dict[str, Any],
        server_time_ms: int,
    ) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            return
        mapping = {
            "session_id": session_id,
            "event_id": event_id,
            "stream_seq": int(seq),
            "message_type": str(msg_type),
            "event_type": str(payload.get("event_type") or payload.get("type") or ""),
            "request_id": str(payload.get("request_id") or ""),
            "player_id": payload.get("player_id"),
            "target_player_id": payload.get("target_player_id"),
            "commit_seq": payload.get("commit_seq"),
            "server_time_ms": int(server_time_ms),
        }
        client = self._connection.client()
        key = self._event_index_key(session_id)
        client.hset(key, event_id, _json_dump(mapping))
        _expire_key(client, key, DEBUG_REDIS_RETENTION_SECONDS)

    def _remember_viewer_outbox(
        self,
        session_id: str,
        *,
        seq: int,
        msg_type: str,
        payload: dict[str, Any],
        server_time_ms: int,
    ) -> None:
        scopes = _viewer_outbox_scopes(str(msg_type), payload)
        if not scopes:
            return
        client = self._connection.client()
        key = self._viewer_outbox_index_key(session_id)
        for scope in sorted(set(scopes)):
            record = {
                "session_id": session_id,
                "viewer_scope": scope,
                "stream_seq": int(seq),
                "message_type": str(msg_type),
                "event_id": str(payload.get("event_id") or ""),
                "request_id": str(payload.get("request_id") or ""),
                "player_id": payload.get("player_id"),
                "target_player_id": payload.get("target_player_id"),
                "commit_seq": payload.get("commit_seq"),
                "server_time_ms": int(server_time_ms),
            }
            client.hset(key, f"{int(seq):020d}:{scope}", _json_dump(record))
        _expire_key(client, key, DEBUG_REDIS_RETENTION_SECONDS)

    def _stream_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "events")

    def _source_stream_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "source_events")

    def _seq_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "seq")

    def _event_index_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "event_index")

    def _viewer_outbox_index_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "viewer_outbox")

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

    def get_pending(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        field = self._resolve_prompt_field(self._pending_key(), request_id, session_id=session_id)
        if field is None:
            return None
        raw = self._connection.client().hget(self._pending_key(), field)
        return _json_load_dict(str(raw)) if raw is not None else None

    def list_pending(self) -> list[dict[str, Any]]:
        payloads = self._connection.client().hgetall(self._pending_key())
        items: list[dict[str, Any]] = []
        for request_id in sorted(payloads):
            parsed = _json_load_dict(payloads[request_id])
            if parsed is not None:
                items.append(parsed)
        return items

    def save_pending(self, request_id: str, payload: dict[str, Any], session_id: str | None = None) -> None:
        field = self._prompt_field(request_id, session_id=session_id or str(payload.get("session_id") or ""))
        self._connection.client().hset(
            self._pending_key(),
            field,
            _json_dump(payload),
        )
        self._upsert_debug_record("pending", field, payload, session_id=session_id)

    def delete_pending(self, request_id: str, session_id: str | None = None) -> bool:
        field = self._resolve_prompt_field(self._pending_key(), request_id, session_id=session_id)
        if field is None:
            return False
        raw = self._connection.client().hget(self._pending_key(), field)
        removed = int(self._connection.client().hdel(self._pending_key(), field) or 0)
        if removed > 0:
            self._delete_debug_record("pending", field, raw, session_id=session_id)
            return True
        return False

    def get_resolved(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        field = self._resolve_prompt_field(self._resolved_key(), request_id, session_id=session_id)
        if field is None:
            return None
        raw = self._connection.client().hget(self._resolved_key(), field)
        return _json_load_dict(str(raw)) if raw is not None else None

    def list_resolved(self) -> dict[str, dict[str, Any]]:
        payloads = self._connection.client().hgetall(self._resolved_key())
        result: dict[str, dict[str, Any]] = {}
        for request_id, raw in payloads.items():
            parsed = _json_load_dict(raw)
            if parsed is not None:
                result[str(request_id)] = parsed
        return result

    def save_resolved(self, request_id: str, payload: dict[str, Any], session_id: str | None = None) -> None:
        field = self._prompt_field(request_id, session_id=session_id or str(payload.get("session_id") or ""))
        self._connection.client().hset(
            self._resolved_key(),
            field,
            _json_dump(payload),
        )
        self._upsert_debug_record("resolved", field, payload, session_id=session_id)

    def delete_resolved(self, request_id: str, session_id: str | None = None) -> None:
        field = self._resolve_prompt_field(self._resolved_key(), request_id, session_id=session_id)
        if field is not None:
            raw = self._connection.client().hget(self._resolved_key(), field)
            self._connection.client().hdel(self._resolved_key(), field)
            self._delete_debug_record("resolved", field, raw, session_id=session_id)

    def save_decision(self, request_id: str, payload: dict[str, Any], session_id: str | None = None) -> None:
        field = self._prompt_field(request_id, session_id=session_id or str(payload.get("session_id") or ""))
        self._connection.client().hset(
            self._decisions_key(),
            field,
            _json_dump(payload),
        )
        self._upsert_debug_record("decisions", field, payload, session_id=session_id)

    def get_decision(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        field = self._resolve_prompt_field(self._decisions_key(), request_id, session_id=session_id)
        if field is None:
            return None
        raw = self._connection.client().hget(self._decisions_key(), field)
        return _json_load_dict(str(raw)) if raw is not None else None

    def pop_decision(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        client = self._connection.client()
        field = self._resolve_prompt_field(self._decisions_key(), request_id, session_id=session_id)
        if field is None:
            return None
        raw = client.hget(self._decisions_key(), field)
        if raw is None:
            return None
        client.hdel(self._decisions_key(), field)
        self._delete_debug_record("decisions", field, raw, session_id=session_id)
        return _json_load_dict(str(raw))

    def delete_decision(self, request_id: str, session_id: str | None = None) -> None:
        field = self._resolve_prompt_field(self._decisions_key(), request_id, session_id=session_id)
        if field is not None:
            raw = self._connection.client().hget(self._decisions_key(), field)
            self._connection.client().hdel(self._decisions_key(), field)
            self._delete_debug_record("decisions", field, raw, session_id=session_id)

    def get_lifecycle(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        field = self._resolve_prompt_field(self._lifecycle_key(), request_id, session_id=session_id)
        if field is None:
            return None
        raw = self._connection.client().hget(self._lifecycle_key(), field)
        return _json_load_dict(str(raw)) if raw is not None else None

    def list_lifecycle(self, session_id: str | None = None) -> list[dict[str, Any]]:
        payloads = self._connection.client().hgetall(self._lifecycle_key())
        items: list[dict[str, Any]] = []
        for request_id in sorted(payloads):
            parsed = _json_load_dict(payloads[request_id])
            if parsed is None:
                continue
            if session_id is not None and str(parsed.get("session_id") or "") != str(session_id):
                continue
            items.append(parsed)
        return items

    def save_lifecycle(self, request_id: str, payload: dict[str, Any], session_id: str | None = None) -> None:
        field = self._prompt_field(request_id, session_id=session_id or str(payload.get("session_id") or ""))
        self._connection.client().hset(
            self._lifecycle_key(),
            field,
            _json_dump(payload),
        )
        self._upsert_debug_record("lifecycle", field, payload, session_id=session_id)

    def delete_lifecycle(self, request_id: str, session_id: str | None = None) -> None:
        field = self._resolve_prompt_field(self._lifecycle_key(), request_id, session_id=session_id)
        if field is not None:
            raw = self._connection.client().hget(self._lifecycle_key(), field)
            self._connection.client().hdel(self._lifecycle_key(), field)
            self._delete_debug_record("lifecycle", field, raw, session_id=session_id)

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
        storage_request_id = self._prompt_field(normalized_request_id, session_id=session_id)
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
                storage_request_id,
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
            self._delete_debug_record("pending", storage_request_id, None, session_id=session_id, refresh=False)
            self._upsert_debug_record("decisions", storage_request_id, decision_payload, session_id=session_id, refresh=False)
            self._upsert_debug_record("resolved", storage_request_id, resolved_payload, session_id=session_id, refresh=False)
            self._refresh_debug_index(session_id)
            return {
                "stream_id": str(result[0]),
                "seq": int(result[1]),
                "type": str(command_type),
                "session_id": str(session_id),
                "server_time_ms": int(server_time_ms or 0),
                "payload": dict(command_payload),
            }
        if client.hget(self._pending_key(), storage_request_id) is None:
            return None
        if not bool(client.hsetnx(command_store._seen_key(), seen_key, "1")):
            return None
        seq = command_store._next_seq(session_id)
        fields = {
            "seq": str(seq),
            "type": str(command_type),
            "session_id": str(session_id),
            "server_time_ms": str(int(server_time_ms or 0)),
            "payload": command_json,
        }
        pipeline = client.pipeline(transaction=True)
        pipeline.hdel(self._pending_key(), storage_request_id)
        pipeline.hset(self._decisions_key(), storage_request_id, decision_json)
        pipeline.hset(self._resolved_key(), storage_request_id, resolved_json)
        pipeline.xadd(command_store._stream_key(session_id), fields)
        results = pipeline.execute()
        self._delete_debug_record("pending", storage_request_id, None, session_id=session_id, refresh=False)
        self._upsert_debug_record("decisions", storage_request_id, decision_payload, session_id=session_id, refresh=False)
        self._upsert_debug_record("resolved", storage_request_id, resolved_payload, session_id=session_id, refresh=False)
        self._refresh_debug_index(session_id)
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
                self.delete_pending(request_id, session_id=session_id)
                self.delete_decision(request_id, session_id=session_id)
                self.delete_resolved(request_id, session_id=session_id)
        for lifecycle in self.list_lifecycle(session_id):
            request_id = str(lifecycle.get("request_id", "")).strip()
            if request_id:
                self.delete_lifecycle(request_id, session_id=session_id)
        client = self._connection.client()
        for bucket_name in ("pending", "resolved", "decisions", "lifecycle"):
            client.delete(_prompt_debug_bucket_key(self._connection, session_id, bucket_name))
        client.delete(_prompt_debug_marker_key(self._connection, session_id))
        self._connection.client().delete(self._debug_index_key(session_id))

    def load_debug_index(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._debug_index_key(session_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def _upsert_debug_record(
        self,
        bucket_name: str,
        field: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        refresh: bool = True,
    ) -> None:
        resolved_session_id = _prompt_session_id_from_field_or_payload(field, payload, session_id=session_id)
        if resolved_session_id:
            client = self._connection.client()
            bucket_key = _prompt_debug_bucket_key(self._connection, resolved_session_id, bucket_name)
            client.hset(bucket_key, field, _json_dump(_compact_prompt_debug_record(bucket_name, field, payload)))
            _expire_key(client, bucket_key, DEBUG_REDIS_RETENTION_SECONDS)
            self._touch_debug_index_marker(resolved_session_id)
            if refresh:
                self._refresh_debug_index(resolved_session_id)

    def _delete_debug_record(
        self,
        bucket_name: str,
        field: str,
        raw: str | None,
        *,
        session_id: str | None = None,
        refresh: bool = True,
    ) -> None:
        payload = _json_load_dict(str(raw)) if raw is not None else None
        resolved_session_id = _prompt_session_id_from_field_or_payload(field, payload, session_id=session_id)
        if resolved_session_id:
            client = self._connection.client()
            bucket_key = _prompt_debug_bucket_key(self._connection, resolved_session_id, bucket_name)
            client.hdel(bucket_key, field)
            _expire_key(client, bucket_key, DEBUG_REDIS_RETENTION_SECONDS)
            self._touch_debug_index_marker(resolved_session_id)
            if refresh:
                self._refresh_debug_index(resolved_session_id)

    def _touch_debug_index_marker(self, session_id: str) -> None:
        client = self._connection.client()
        client.set(_prompt_debug_marker_key(self._connection, session_id), "1", px=DEBUG_REDIS_RETENTION_SECONDS * 1000)

    def _refresh_debug_index(self, session_id: str) -> None:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        try:
            self._connection.client().set(
                self._debug_index_key(normalized_session_id),
                _json_dump(_build_prompt_debug_summary(self._connection, normalized_session_id)),
                px=DEBUG_REDIS_RETENTION_SECONDS * 1000,
            )
        except Exception:
            return

    @staticmethod
    def _prompt_field(request_id: str, session_id: str | None = None) -> str:
        normalized_request_id = str(request_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id or "\x1f" in normalized_request_id:
            return normalized_request_id
        return f"{normalized_session_id}\x1f{normalized_request_id}"

    def _resolve_prompt_field(self, hash_key: str, request_id: str, *, session_id: str | None = None) -> str | None:
        normalized_request_id = str(request_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        if not normalized_request_id:
            return None
        client = self._connection.client()
        if "\x1f" in normalized_request_id and client.hget(hash_key, normalized_request_id) is not None:
            return normalized_request_id
        if normalized_session_id:
            scoped = self._prompt_field(normalized_request_id, session_id=normalized_session_id)
            if client.hget(hash_key, scoped) is not None:
                return scoped
        if client.hget(hash_key, normalized_request_id) is not None:
            return normalized_request_id
        if normalized_session_id:
            return None
        matches: list[str] = []
        for field, raw in client.hgetall(hash_key).items():
            parsed = _json_load_dict(raw)
            if parsed is None:
                continue
            if str(parsed.get("request_id") or "").strip() != normalized_request_id:
                continue
            if normalized_session_id and str(parsed.get("session_id") or "").strip() != normalized_session_id:
                continue
            matches.append(str(field))
        if len(matches) == 1:
            return matches[0]
        return None

    def _pending_key(self) -> str:
        return self._connection.key("prompts", "pending")

    def _resolved_key(self) -> str:
        return self._connection.key("prompts", "resolved")

    def _decisions_key(self) -> str:
        return self._connection.key("prompts", "decisions")

    def _lifecycle_key(self) -> str:
        return self._connection.key("prompts", "lifecycle")

    def _debug_index_key(self, session_id: str) -> str:
        return self._connection.key("prompts", session_id, "debug_index")


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
        seq = self._next_seq(session_id)
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
        client = self._connection.client()
        offset_key = self._offset_key(consumer_name)
        offset_seq = max(0, int(seq))
        if callable(getattr(client, "eval", None)):
            client.eval(
                _SAVE_CONSUMER_OFFSET_LUA,
                2,
                offset_key,
                self._offset_index_key(),
                str(session_id),
                str(offset_seq),
            )
            return
        current = self.load_consumer_offset(consumer_name, session_id)
        if offset_seq > current:
            client.hset(offset_key, session_id, str(offset_seq))

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

    def _next_seq(self, session_id: str) -> int:
        client = self._connection.client()
        seq_key = self._seq_key(session_id)
        current_seq = _int_or_default(_redis_text(client.get(seq_key)), 0)
        latest_stream_seq = self._latest_stream_seq(session_id)
        if current_seq < latest_stream_seq:
            client.set(seq_key, str(latest_stream_seq))
        return int(client.incr(seq_key))

    def _latest_stream_seq(self, session_id: str) -> int:
        entries = self._connection.client().xrevrange(self._stream_key(session_id), count=1)
        if not entries:
            return 0
        fields = entries[0][1]
        if not isinstance(fields, dict):
            return 0
        return _int_or_default(_redis_text(fields.get("seq")), 0)

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
        if message_type == "snapshot_pulse":
            return
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
        self._refresh_debug_snapshot(session_id, checkpoint=payload)

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

    def save_debug_snapshot(self, session_id: str, payload: dict[str, Any]) -> None:
        self._connection.client().set(
            self._debug_snapshot_key(session_id),
            _json_dump(payload),
            px=DEBUG_REDIS_RETENTION_SECONDS * 1000,
        )

    def load_debug_snapshot(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._debug_snapshot_key(session_id))
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
        expected_previous_commit_seq: int | None = None,
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
        expected_previous_seq = (
            max(0, int(expected_previous_commit_seq))
            if expected_previous_commit_seq is not None
            else max(0, int(view_commit_seq or 0) - 1)
        )
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
            self._assert_expected_previous_view_commit_seq(
                session_id,
                view_commit_seq,
                expected_previous_commit_seq=expected_previous_seq,
            )
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
        if offset_key and offset_seq and not use_lua_commit:
            current_offset_raw = client.hget(offset_key, session_id)
            current_offset = _int_or_default(current_offset_raw, 0)
            offset_seq = str(max(current_offset, int(offset_seq)))
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
                str(expected_previous_seq),
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
            self._refresh_debug_snapshot(session_id)
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
            self._refresh_debug_snapshot(session_id)
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
        self._refresh_debug_snapshot(session_id)

    def _refresh_debug_snapshot(
        self,
        session_id: str,
        *,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.save_debug_snapshot(
                session_id,
                self._build_debug_snapshot(session_id, checkpoint=checkpoint),
            )
        except Exception:
            return

    def _build_debug_snapshot(
        self,
        session_id: str,
        *,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkpoint_payload = checkpoint if isinstance(checkpoint, dict) else self.load_checkpoint(session_id) or {}
        current_state = self.load_current_state(session_id) or {}
        view_state = self.load_view_state(session_id) or {}
        view_commit_index = self.load_view_commit_index(session_id) or {}
        runtime = self._latest_runtime_payload(view_commit_index, session_id)
        frame_stack = self._list_from(current_state.get("runtime_frame_stack"))
        active_prompt = self._dict_from(
            current_state.get("runtime_active_prompt")
            or checkpoint_payload.get("runtime_active_prompt")
            or runtime.get("active_prompt")
        )
        summary = {
            "status": runtime.get("status") or checkpoint_payload.get("runtime_status") or checkpoint_payload.get("latest_event_type"),
            "round_index": _int_or_default(
                runtime.get("round_index"),
                _int_or_default(checkpoint_payload.get("round_index"), _int_or_default(current_state.get("round_index"), 0)),
            ),
            "turn_index": _int_or_default(
                runtime.get("turn_index"),
                _int_or_default(checkpoint_payload.get("turn_index"), _int_or_default(current_state.get("turn_index"), 0)),
            ),
            "current_player_id": _int_or_none(
                runtime.get("current_player_id")
                or current_state.get("current_player_id")
                or current_state.get("acting_player_id")
                or active_prompt.get("player_id")
            ),
            "latest_seq": _int_or_default(checkpoint_payload.get("latest_seq"), 0),
            "latest_commit_seq": _int_or_default(
                checkpoint_payload.get("latest_commit_seq"),
                _int_or_default(view_commit_index.get("latest_commit_seq"), 0),
            ),
            "latest_source_event_seq": _int_or_default(
                checkpoint_payload.get("latest_source_event_seq"),
                _int_or_default(view_commit_index.get("latest_source_event_seq"), 0),
            ),
            "latest_event_type": checkpoint_payload.get("latest_event_type"),
            "active_frame_id": checkpoint_payload.get("frame_id") or runtime.get("active_frame_id"),
            "active_module_id": checkpoint_payload.get("module_id") or runtime.get("active_module_id"),
            "active_module_type": checkpoint_payload.get("module_type") or runtime.get("active_module_type"),
            "active_module_cursor": checkpoint_payload.get("module_cursor") or runtime.get("active_module_cursor"),
            "waiting_prompt_request_id": checkpoint_payload.get("waiting_prompt_request_id") or active_prompt.get("request_id"),
        }
        players = self._compact_players(current_state, view_state)
        pending_actions = self._compact_actions(self._list_from(current_state.get("pending_actions")), limit=20)
        scheduled_actions = self._compact_actions(self._list_from(current_state.get("scheduled_actions")), limit=20)
        return {
            "schema_version": 1,
            "session_id": session_id,
            "updated_at_ms": int(time.time() * 1000),
            "purpose": "redis_debug_snapshot",
            "summary": summary,
            "redis_keys": self._debug_key_map(session_id),
            "checkpoint_flags": {
                "has_snapshot": bool(checkpoint_payload.get("has_snapshot")),
                "has_view_state": bool(checkpoint_payload.get("has_view_state")),
                "has_view_commit": bool(checkpoint_payload.get("has_view_commit")),
                "has_pending_actions": bool(checkpoint_payload.get("has_pending_actions")),
                "has_scheduled_actions": bool(checkpoint_payload.get("has_scheduled_actions")),
                "has_pending_turn_completion": bool(checkpoint_payload.get("has_pending_turn_completion")),
            },
            "runtime": {
                "runner_kind": checkpoint_payload.get("runner_kind") or current_state.get("runtime_runner_kind"),
                "active_prompt": self._compact_prompt(active_prompt),
                "frame_stack": self._compact_frame_stack(frame_stack),
                "module_path": runtime.get("module_path") if isinstance(runtime.get("module_path"), list) else [],
            },
            "players": players,
            "board": self._compact_board(current_state, view_state),
            "pending": {
                "pending_action_count": len(pending_actions),
                "pending_actions": pending_actions,
                "scheduled_action_count": len(scheduled_actions),
                "scheduled_actions": scheduled_actions,
                "pending_turn_completion": self._compact_mapping(
                    self._dict_from(current_state.get("pending_turn_completion")),
                    ("player_id", "round_index", "turn_index", "reason", "module_id", "status"),
                ),
            },
            "view_commits": {
                "latest_commit_seq": view_commit_index.get("latest_commit_seq"),
                "latest_source_event_seq": view_commit_index.get("latest_source_event_seq"),
                "viewers": sorted(str(item) for item in self._list_from(view_commit_index.get("view_commit_viewers"))),
                "cached_viewers": sorted(str(item) for item in self._list_from(view_commit_index.get("cached_viewers"))),
            },
            "prompts": _build_prompt_debug_summary(self._connection, session_id),
            "commands": self._debug_command_summary(session_id),
            "stream": self._debug_stream_summary(session_id),
            "checkpoint": checkpoint_payload,
        }

    def _latest_runtime_payload(self, view_commit_index: dict[str, Any], session_id: str) -> dict[str, Any]:
        viewers = self._list_from(view_commit_index.get("view_commit_viewers"))
        for label in ("spectator", "public", "admin", *[str(item) for item in viewers]):
            key = self._view_commit_key_from_label(session_id, str(label))
            if not key:
                continue
            raw = self._connection.client().get(key)
            payload = _json_load_dict(str(raw)) if raw is not None else None
            if isinstance(payload, dict):
                runtime = payload.get("runtime")
                if isinstance(runtime, dict):
                    return runtime
        return {}

    def _debug_key_map(self, session_id: str) -> dict[str, str]:
        return {
            "checkpoint": self._checkpoint_key(session_id),
            "current_state": self._current_state_key(session_id),
            "view_state_public": self._view_state_key(session_id),
            "view_commit_index": self._view_commit_index_key(session_id),
            "debug_snapshot": self._debug_snapshot_key(session_id),
            "stream_events": self._runtime_stream_key(session_id),
            "stream_source_events": self._connection.key("stream", session_id, "source_events"),
            "stream_seq": self._runtime_stream_seq_key(session_id),
            "stream_event_index": self._connection.key("stream", session_id, "event_index"),
            "stream_viewer_outbox": self._connection.key("stream", session_id, "viewer_outbox"),
            "commands_stream": self._connection.key("commands", session_id, "stream"),
            "commands_seq": self._connection.key("commands", session_id, "seq"),
            "commands_seen": self._connection.key("commands", "seen"),
            "commands_offset_indexes": self._connection.key("commands", "offset_indexes"),
            "prompts_pending_hash": self._connection.key("prompts", "pending"),
            "prompts_resolved_hash": self._connection.key("prompts", "resolved"),
            "prompts_decisions_hash": self._connection.key("prompts", "decisions"),
            "prompts_lifecycle_hash": self._connection.key("prompts", "lifecycle"),
            "prompts_debug_index": self._connection.key("prompts", session_id, "debug_index"),
            "runtime_status_hash": self._connection.key("runtime", "status"),
            "runtime_fallbacks": self._connection.key("runtime", session_id, "fallbacks"),
            "runtime_lease": self._connection.key("runtime", session_id, "lease"),
        }

    def _debug_stream_summary(self, session_id: str) -> dict[str, Any]:
        client = self._connection.client()
        event_index_key = self._connection.key("stream", session_id, "event_index")
        viewer_outbox_key = self._connection.key("stream", session_id, "viewer_outbox")
        event_index_rows = self._latest_hash_records(event_index_key, limit=20)
        viewer_outbox_rows = self._latest_hash_records(viewer_outbox_key, limit=40)
        return {
            "stream_seq": _int_or_default(client.get(self._runtime_stream_seq_key(session_id)), 0),
            "event_index_count": len(client.hgetall(event_index_key)),
            "viewer_outbox_count": len(client.hgetall(viewer_outbox_key)),
            "event_index_ttl_seconds": DEBUG_REDIS_RETENTION_SECONDS,
            "viewer_outbox_ttl_seconds": DEBUG_REDIS_RETENTION_SECONDS,
            "latest_event_index": event_index_rows,
            "latest_viewer_outbox": viewer_outbox_rows,
        }

    def _debug_command_summary(self, session_id: str) -> dict[str, Any]:
        client = self._connection.client()
        stream_key = self._connection.key("commands", session_id, "stream")
        command_rows = [
            self._compact_command_record(entry_id, fields)
            for entry_id, fields in client.xrange(stream_key)
            if isinstance(fields, dict)
        ]
        offset_rows = []
        for offset_key in sorted(str(key) for key in client.hgetall(self._command_offset_index_key()).keys()):
            raw_offset = client.hget(offset_key, session_id)
            if raw_offset is None:
                continue
            offset_rows.append(
                {
                    "consumer": self._consumer_name_from_offset_key(offset_key),
                    "offset_key": offset_key,
                    "seq": _int_or_default(raw_offset, 0),
                }
            )
        seen_prefix = f"{session_id}:"
        return {
            "command_seq": _int_or_default(client.get(self._connection.key("commands", session_id, "seq")), 0),
            "command_count": len(command_rows),
            "seen_count": len(
                [key for key in client.hgetall(self._connection.key("commands", "seen")).keys() if str(key).startswith(seen_prefix)]
            ),
            "consumer_offsets": offset_rows,
            "latest_commands": command_rows[-DEBUG_REDIS_RECORD_LIMIT:],
        }

    def _compact_command_record(self, entry_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = _json_load_dict(str(fields.get("payload", "{}"))) or {}
        return {
            "stream_id": str(entry_id),
            "seq": _int_or_default(fields.get("seq"), 0),
            "type": str(fields.get("type") or ""),
            "session_id": str(fields.get("session_id") or ""),
            "server_time_ms": _int_or_default(fields.get("server_time_ms"), 0),
            "request_id": str(payload.get("request_id") or ""),
            "player_id": payload.get("player_id"),
            "choice_id": payload.get("choice_id"),
            "view_commit_seq_seen": payload.get("view_commit_seq_seen"),
        }

    def _consumer_name_from_offset_key(self, key: str) -> str:
        marker = f"{self._connection.key('commands', 'offsets')}:"
        if str(key).startswith(marker):
            return str(key)[len(marker) :]
        return str(key).rsplit(":", 1)[-1]

    def _latest_hash_records(self, key: str, *, limit: int) -> list[dict[str, Any]]:
        rows = []
        for field, raw in self._connection.client().hgetall(key).items():
            parsed = _json_load_dict(str(raw))
            if not isinstance(parsed, dict):
                continue
            parsed["_field"] = str(field)
            rows.append(parsed)
        rows.sort(
            key=lambda item: (
                _int_or_default(item.get("stream_seq"), 0),
                str(item.get("_field") or ""),
            )
        )
        return [self._compact_stream_record(item) for item in rows[-max(1, int(limit)):]]

    def _compact_stream_record(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._compact_mapping(
            item,
            (
                "_field",
                "session_id",
                "viewer_scope",
                "stream_seq",
                "message_type",
                "event_type",
                "event_id",
                "request_id",
                "player_id",
                "target_player_id",
                "commit_seq",
                "server_time_ms",
            ),
        )

    def _compact_players(self, current_state: dict[str, Any], view_state: dict[str, Any]) -> list[dict[str, Any]]:
        players = self._list_from(current_state.get("players"))
        if not players:
            players = self._list_from(view_state.get("players"))
        return [
            self._compact_mapping(
                self._dict_from(player),
                (
                    "player_id",
                    "id",
                    "seat",
                    "name",
                    "character",
                    "character_id",
                    "alive",
                    "position",
                    "tile_index",
                    "money",
                    "cash",
                    "coins",
                    "points",
                    "score",
                    "shards",
                    "lap_count",
                    "rank",
                    "bankrupt",
                ),
            )
            for player in players
            if isinstance(player, dict)
        ]

    def _compact_board(self, current_state: dict[str, Any], view_state: dict[str, Any]) -> dict[str, Any]:
        board = self._dict_from(current_state.get("board") or view_state.get("board"))
        compact = self._compact_mapping(
            board,
            ("round_index", "turn_index", "f_value", "end_time", "weather", "lap", "tile_count"),
        )
        tiles = self._list_from(board.get("tiles"))
        if tiles:
            compact["tile_count"] = len(tiles)
        return compact

    def _compact_prompt(self, prompt: dict[str, Any]) -> dict[str, Any]:
        compact = self._compact_mapping(
            prompt,
            (
                "request_id",
                "prompt_instance_id",
                "player_id",
                "request_type",
                "frame_id",
                "module_id",
                "module_type",
                "module_cursor",
                "resume_token",
                "timeout_ms",
            ),
        )
        legal_choices = self._list_from(prompt.get("legal_choices"))
        if legal_choices:
            compact["legal_choice_count"] = len(legal_choices)
            compact["legal_choice_ids"] = [
                str(self._dict_from(choice).get("choice_id") or self._dict_from(choice).get("id") or "")
                for choice in legal_choices[:20]
            ]
        return compact

    def _compact_frame_stack(self, frames: list[Any]) -> list[dict[str, Any]]:
        return [
            self._compact_mapping(
                self._dict_from(frame),
                (
                    "frame_id",
                    "frame_type",
                    "status",
                    "player_id",
                    "round_index",
                    "turn_index",
                    "active_module_id",
                    "active_module_type",
                    "active_module_cursor",
                    "parent_frame_id",
                ),
            )
            for frame in frames[-12:]
            if isinstance(frame, dict)
        ]

    def _compact_actions(self, actions: list[Any], *, limit: int) -> list[dict[str, Any]]:
        return [
            self._compact_mapping(
                self._dict_from(action),
                (
                    "action_id",
                    "id",
                    "type",
                    "action_type",
                    "status",
                    "player_id",
                    "source_player_id",
                    "target_player_id",
                    "owner_player_id",
                    "payer_player_id",
                    "round_index",
                    "turn_index",
                    "tile_index",
                    "module_id",
                    "request_id",
                    "created_at_seq",
                    "resolve_at_turn_start_player_id",
                ),
            )
            for action in actions[:limit]
            if isinstance(action, dict)
        ]

    @staticmethod
    def _compact_mapping(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: payload[key] for key in keys if key in payload and payload[key] is not None}

    @staticmethod
    def _dict_from(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list_from(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

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

    def _assert_expected_previous_view_commit_seq(
        self,
        session_id: str,
        view_commit_seq: int | None,
        *,
        expected_previous_commit_seq: int | None = None,
    ) -> None:
        if view_commit_seq is None:
            return
        expected_previous = (
            max(0, int(expected_previous_commit_seq))
            if expected_previous_commit_seq is not None
            else max(0, int(view_commit_seq) - 1)
        )
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
            self._debug_snapshot_key(session_id),
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

    def _debug_snapshot_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "debug_snapshot")

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


def _build_prompt_debug_summary(connection: RedisConnection, session_id: str) -> dict[str, Any]:
    normalized_session_id = str(session_id or "").strip()
    use_session_buckets = connection.client().get(_prompt_debug_marker_key(connection, normalized_session_id)) is not None
    buckets: dict[str, dict[str, Any]] = {}
    all_rows: list[dict[str, Any]] = []
    for bucket_name, hash_key in (
        ("pending", connection.key("prompts", "pending")),
        ("resolved", connection.key("prompts", "resolved")),
        ("decisions", connection.key("prompts", "decisions")),
        ("lifecycle", connection.key("prompts", "lifecycle")),
    ):
        rows: list[dict[str, Any]] = []
        if use_session_buckets:
            debug_bucket_key = _prompt_debug_bucket_key(connection, normalized_session_id, bucket_name)
            for raw in connection.client().hgetall(debug_bucket_key).values():
                compact = _json_load_dict(str(raw))
                if compact is not None:
                    rows.append(compact)
        else:
            for field, raw in connection.client().hgetall(hash_key).items():
                payload = _json_load_dict(str(raw))
                if payload is None:
                    continue
                if _prompt_session_id_from_field_or_payload(str(field), payload) != normalized_session_id:
                    continue
                rows.append(_compact_prompt_debug_record(bucket_name, str(field), payload))
        rows.sort(key=_prompt_debug_sort_key)
        buckets[bucket_name] = {
            "count": len(rows),
            "latest": rows[-DEBUG_REDIS_RECORD_LIMIT:],
        }
        all_rows.extend(rows)
    all_rows.sort(key=_prompt_debug_sort_key)
    active_prompts = buckets.get("pending", {}).get("latest", [])
    return {
        "schema_version": 1,
        "session_id": normalized_session_id,
        "retention_seconds": DEBUG_REDIS_RETENTION_SECONDS,
        "redis_keys": {
            "pending": connection.key("prompts", "pending"),
            "resolved": connection.key("prompts", "resolved"),
            "decisions": connection.key("prompts", "decisions"),
            "lifecycle": connection.key("prompts", "lifecycle"),
            "debug_index": connection.key("prompts", normalized_session_id, "debug_index"),
            "debug_marker": _prompt_debug_marker_key(connection, normalized_session_id),
        },
        "counts": {name: int(summary.get("count") or 0) for name, summary in buckets.items()},
        "active_prompt": active_prompts[-1] if active_prompts else {},
        "latest": all_rows[-DEBUG_REDIS_RECORD_LIMIT:],
        "buckets": buckets,
    }


def _prompt_debug_bucket_key(connection: RedisConnection, session_id: str, bucket_name: str) -> str:
    return connection.key("prompts", str(session_id or "").strip(), "debug", str(bucket_name or "").strip())


def _prompt_debug_marker_key(connection: RedisConnection, session_id: str) -> str:
    return connection.key("prompts", str(session_id or "").strip(), "debug", "marker")


def _compact_prompt_debug_record(bucket_name: str, field: str, payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: payload[key]
        for key in (
            "request_id",
            "prompt_instance_id",
            "state",
            "status",
            "player_id",
            "request_type",
            "choice_id",
            "accepted",
            "reason",
            "error_code",
            "view_commit_seq",
            "view_commit_seq_seen",
            "commit_seq",
            "round_index",
            "turn_index",
            "frame_id",
            "module_id",
            "module_type",
            "module_cursor",
            "created_at_ms",
            "updated_at_ms",
            "server_time_ms",
            "expires_at_ms",
        )
        if key in payload and payload[key] is not None
    }
    compact["bucket"] = bucket_name
    compact["field"] = field
    compact["session_id"] = _prompt_session_id_from_field_or_payload(field, payload)
    if "request_id" not in compact:
        compact["request_id"] = _prompt_request_id_from_field(field)
    if payload.get("resume_token") is not None:
        compact["resume_token_present"] = True
    legal_choices = payload.get("legal_choices")
    if isinstance(legal_choices, list):
        compact["legal_choice_count"] = len(legal_choices)
    return compact


def _prompt_debug_sort_key(record: dict[str, Any]) -> tuple[int, str, str]:
    return (
        max(
            _int_or_default(record.get("updated_at_ms"), 0),
            _int_or_default(record.get("server_time_ms"), 0),
            _int_or_default(record.get("created_at_ms"), 0),
            _int_or_default(record.get("view_commit_seq"), 0),
            _int_or_default(record.get("commit_seq"), 0),
        ),
        str(record.get("field") or ""),
        str(record.get("bucket") or ""),
    )


def _prompt_session_id_from_field_or_payload(
    field: str,
    payload: dict[str, Any] | None,
    *,
    session_id: str | None = None,
) -> str:
    explicit = str(session_id or "").strip()
    if explicit:
        return explicit
    if isinstance(payload, dict):
        payload_session_id = str(payload.get("session_id") or "").strip()
        if payload_session_id:
            return payload_session_id
    normalized_field = str(field or "")
    if "\x1f" in normalized_field:
        return normalized_field.split("\x1f", 1)[0]
    return ""


def _prompt_request_id_from_field(field: str) -> str:
    normalized_field = str(field or "")
    if "\x1f" in normalized_field:
        return normalized_field.split("\x1f", 1)[1]
    return normalized_field


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


def _viewer_outbox_scopes(msg_type: str, payload: dict[str, Any]) -> list[str]:
    explicit_scopes = payload.get("viewer_outbox_scopes")
    if isinstance(explicit_scopes, list):
        normalized = [_normalize_viewer_scope(scope) for scope in explicit_scopes]
        scopes = sorted({scope for scope in normalized if scope})
        if scopes:
            return scopes
    if msg_type in {"prompt", "decision_ack"}:
        player_id = _int_or_default(payload.get("player_id") or payload.get("target_player_id"), 0)
        return [f"player:{player_id}"] if player_id > 0 else []
    if msg_type == "view_commit":
        viewer = payload.get("viewer") if isinstance(payload.get("viewer"), dict) else {}
        role = str(viewer.get("role") or payload.get("viewer_role") or "").strip().lower()
        if role in {"seat", "player"}:
            player_id = _int_or_default(viewer.get("player_id") or payload.get("player_id"), 0)
            return [f"player:{player_id}"] if player_id > 0 else []
        if role in {"spectator", "admin", "public"}:
            return [role]
        return ["public"]
    if msg_type == "snapshot_pulse":
        target_player_id = _int_or_default(payload.get("target_player_id"), 0)
        return [f"player:{target_player_id}"] if target_player_id > 0 else ["public"]
    return ["public"]


def _normalize_viewer_scope(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"spectator", "admin", "public"}:
        return raw
    if raw.startswith("player:"):
        player_id = _int_or_default(raw.split(":", 1)[1], 0)
        return f"player:{player_id}" if player_id > 0 else None
    if raw.isdigit():
        return f"player:{int(raw)}"
    return None


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default or 0)


def _redis_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode()
        except Exception:
            return None
    return str(value)


def _expire_key(client: Any, key: str, seconds: int) -> None:
    expire = getattr(client, "expire", None)
    if not callable(expire):
        return
    try:
        expire(key, max(1, int(seconds)))
    except Exception:
        return


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
local current_seq = tonumber(redis.call("GET", KEYS[2]) or "0") or 0
local latest_stream_seq = 0
local latest_entries = redis.call("XREVRANGE", KEYS[3], "+", "-", "COUNT", 1)
if latest_entries and latest_entries[1] then
  local fields = latest_entries[1][2]
  for i = 1, #fields, 2 do
    if fields[i] == "seq" then
      latest_stream_seq = tonumber(fields[i + 1]) or 0
      break
    end
  end
end
if current_seq < latest_stream_seq then
  redis.call("SET", KEYS[2], tostring(latest_stream_seq))
end
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
  local next_offset = tonumber(ARGV[5]) or 0
  local current_offset = tonumber(redis.call("HGET", KEYS[5], ARGV[4]) or "0") or 0
  if next_offset > current_offset then
    redis.call("HSET", KEYS[5], ARGV[4], tostring(next_offset))
  end
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
  local next_offset = tonumber(ARGV[5]) or 0
  local current_offset = tonumber(redis.call("HGET", KEYS[5], ARGV[4]) or "0") or 0
  if next_offset > current_offset then
    redis.call("HSET", KEYS[5], ARGV[4], tostring(next_offset))
  end
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

_SAVE_CONSUMER_OFFSET_LUA = """
local next_offset = tonumber(ARGV[2]) or 0
redis.call("HSET", KEYS[2], KEYS[1], "1")
local current_offset = tonumber(redis.call("HGET", KEYS[1], ARGV[1]) or "0") or 0
if next_offset > current_offset then
  redis.call("HSET", KEYS[1], ARGV[1], tostring(next_offset))
  return next_offset
end
return current_offset
"""

_ACCEPT_PROMPT_DECISION_LUA = """
if redis.call("HEXISTS", KEYS[1], ARGV[1]) == 0 then
  return nil
end
if redis.call("HSETNX", KEYS[4], ARGV[4], "1") == 0 then
  return nil
end
local current_seq = tonumber(redis.call("GET", KEYS[5]) or "0") or 0
local latest_stream_seq = 0
local latest_entries = redis.call("XREVRANGE", KEYS[6], "+", "-", "COUNT", 1)
if latest_entries and latest_entries[1] then
  local fields = latest_entries[1][2]
  for i = 1, #fields, 2 do
    if fields[i] == "seq" then
      latest_stream_seq = tonumber(fields[i + 1]) or 0
      break
    end
  end
end
if current_seq < latest_stream_seq then
  redis.call("SET", KEYS[5], tostring(latest_stream_seq))
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
