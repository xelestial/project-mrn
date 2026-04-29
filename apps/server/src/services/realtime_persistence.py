from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from apps.server.src.infra.redis_client import RedisConnection


@dataclass(frozen=True)
class RuntimeLeaseState:
    payload: dict[str, Any]
    recent_fallbacks: list[dict[str, Any]]


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
        client.delete(self._stream_key(session_id), self._seq_key(session_id))
        client.hdel(self._drop_count_key(), session_id)

    def _stream_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "events")

    def _seq_key(self, session_id: str) -> str:
        return self._connection.key("stream", session_id, "seq")

    def _drop_count_key(self) -> str:
        return self._connection.key("stream", "drop_counts")

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

    def pop_decision(self, request_id: str) -> dict[str, Any] | None:
        client = self._connection.client()
        raw = client.hget(self._decisions_key(), request_id)
        if raw is None:
            return None
        client.hdel(self._decisions_key(), request_id)
        return _json_load_dict(str(raw))

    def delete_decision(self, request_id: str) -> None:
        self._connection.client().hdel(self._decisions_key(), request_id)

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
        event_type = str(payload.get("event_type") or message.get("type") or "").strip()
        previous = self.load_checkpoint(session_id) or {}
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
        self._connection.client().set(self._view_state_key(session_id), _json_dump(payload))

    def load_view_state(self, session_id: str) -> dict[str, Any] | None:
        raw = self._connection.client().get(self._view_state_key(session_id))
        return _json_load_dict(str(raw)) if raw is not None else None

    def delete_session_data(self, session_id: str) -> None:
        self._connection.client().delete(
            self._checkpoint_key(session_id),
            self._current_state_key(session_id),
            self._view_state_key(session_id),
        )

    def _checkpoint_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "checkpoint")

    def _current_state_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "current_state")

    def _view_state_key(self, session_id: str) -> str:
        return self._connection.key("game", session_id, "view_state")


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


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
