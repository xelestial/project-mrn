from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any

from apps.server.src.infra.redis_client import RedisConnection
from apps.server.src.services.realtime_persistence import (
    REDIS_LUA_REQUIRED_ERROR,
    RedisCommandStore,
    _ensure_non_lua_fallback_allowed,
)


@dataclass(frozen=True, slots=True)
class BatchCollectorResult:
    status: str
    remaining_player_ids: list[int]
    command: dict[str, Any] | None = None


class BatchCollector:
    """Atomic simultaneous-prompt response collector.

    The production path uses one Redis Lua script so response insertion, remaining
    calculation, and batch completion command creation share the same atomic unit.
    """

    def __init__(self, connection: RedisConnection, command_store: RedisCommandStore) -> None:
        self._connection = connection
        self._command_store = command_store
        self._fallback_lock = threading.RLock()

    def record_response(
        self,
        *,
        session_id: str,
        batch_id: str,
        player_id: int,
        response: dict[str, Any],
        expected_player_ids: list[int],
        server_time_ms: int,
    ) -> BatchCollectorResult:
        normalized_session_id = str(session_id).strip()
        normalized_batch_id = str(batch_id).strip()
        if not normalized_session_id:
            raise ValueError("missing_session_id")
        if not normalized_batch_id:
            raise ValueError("missing_batch_id")
        expected = sorted({int(item) for item in expected_player_ids})
        if not expected:
            raise ValueError("missing_expected_player_ids")
        normalized_player_id = int(player_id)
        if normalized_player_id not in expected:
            raise ValueError("unexpected_batch_player_id")
        payload = dict(response)
        payload.setdefault("player_id", normalized_player_id)
        payload.setdefault("batch_id", normalized_batch_id)

        client = self._connection.client()
        if callable(getattr(client, "eval", None)):
            return self._record_response_lua(
                client,
                session_id=normalized_session_id,
                batch_id=normalized_batch_id,
                player_id=normalized_player_id,
                response=payload,
                expected_player_ids=expected,
                server_time_ms=int(server_time_ms or 0),
            )
        _ensure_non_lua_fallback_allowed(self._connection)
        return self._record_response_fallback(
            session_id=normalized_session_id,
            batch_id=normalized_batch_id,
            player_id=normalized_player_id,
            response=payload,
            expected_player_ids=expected,
            server_time_ms=int(server_time_ms or 0),
        )

    def _record_response_lua(
        self,
        client: Any,
        *,
        session_id: str,
        batch_id: str,
        player_id: int,
        response: dict[str, Any],
        expected_player_ids: list[int],
        server_time_ms: int,
    ) -> BatchCollectorResult:
        request_id = self._completion_request_id(batch_id)
        base_command_payload = {
            "batch_id": batch_id,
            "request_id": request_id,
            "expected_player_ids": expected_player_ids,
            "source": "batch_collector",
        }
        result = client.eval(
            _RECORD_BATCH_RESPONSE_LUA,
            7,
            self._responses_key(session_id, batch_id),
            self._completed_key(session_id),
            self._command_store._seen_key(),
            self._command_store._session_seen_key(session_id),
            self._command_store._seq_key(session_id),
            self._command_store._stream_key(session_id),
            self._command_store._state_key(session_id),
            str(player_id),
            _json_dump(response),
            _json_dump(expected_player_ids),
            f"{session_id}:{request_id}",
            "batch_complete",
            session_id,
            str(server_time_ms),
            _json_dump(base_command_payload),
            batch_id,
            request_id,
        )
        status = str(result[0])
        remaining = _int_list(_json_load(result[1]) or [])
        command = None
        if len(result) >= 5 and str(result[2] or "") and int(result[3] or 0) > 0:
            command_payload = _json_load_dict(str(result[4] or "{}")) or dict(base_command_payload)
            command = {
                "stream_id": str(result[2]),
                "seq": int(result[3]),
                "type": "batch_complete",
                "session_id": session_id,
                "server_time_ms": server_time_ms,
                "payload": command_payload,
            }
        return BatchCollectorResult(status=status, remaining_player_ids=remaining, command=command)

    def _record_response_fallback(
        self,
        *,
        session_id: str,
        batch_id: str,
        player_id: int,
        response: dict[str, Any],
        expected_player_ids: list[int],
        server_time_ms: int,
    ) -> BatchCollectorResult:
        with self._fallback_lock:
            client = self._connection.client()
            responses_key = self._responses_key(session_id, batch_id)
            inserted = bool(client.hsetnx(responses_key, str(player_id), _json_dump(response)))
            remaining = [
                expected_player_id
                for expected_player_id in expected_player_ids
                if client.hget(responses_key, str(expected_player_id)) is None
            ]
            if remaining:
                return BatchCollectorResult(
                    status="pending" if inserted else "duplicate_pending",
                    remaining_player_ids=remaining,
                )
            completed_key = self._completed_key(session_id)
            if not bool(client.hsetnx(completed_key, batch_id, "1")):
                return BatchCollectorResult(status="duplicate_completed", remaining_player_ids=[])
            request_id = self._completion_request_id(batch_id)
            command_payload = {
                "batch_id": batch_id,
                "request_id": request_id,
                "expected_player_ids": expected_player_ids,
                "responses_by_player_id": self._responses_by_player_id(session_id, batch_id, expected_player_ids),
                "completed_at_ms": server_time_ms,
                "source": "batch_collector",
            }
            public_responses = _responses_by_public_player_id(command_payload["responses_by_player_id"])
            if public_responses:
                command_payload["responses_by_public_player_id"] = public_responses
            command = self._command_store.append_command(
                session_id,
                "batch_complete",
                command_payload,
                request_id=request_id,
                server_time_ms=server_time_ms,
            )
            if command is None:
                raise RuntimeError(REDIS_LUA_REQUIRED_ERROR)
            return BatchCollectorResult(status="completed" if inserted else "duplicate_completed", remaining_player_ids=[], command=command)

    def _responses_by_player_id(self, session_id: str, batch_id: str, expected_player_ids: list[int]) -> dict[str, Any]:
        client = self._connection.client()
        responses: dict[str, Any] = {}
        for expected_player_id in expected_player_ids:
            raw = client.hget(self._responses_key(session_id, batch_id), str(expected_player_id))
            if raw is not None:
                responses[str(expected_player_id)] = _json_load_dict(str(raw)) or {}
        return responses

    def _responses_key(self, session_id: str, batch_id: str) -> str:
        return self._connection.key("batches", session_id, batch_id, "responses")

    def _completed_key(self, session_id: str) -> str:
        return self._connection.key("batches", session_id, "completed")

    @staticmethod
    def _completion_request_id(batch_id: str) -> str:
        return f"batch_complete:{batch_id}"


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(raw: object) -> Any:
    try:
        return json.loads(str(raw))
    except Exception:
        return None


def _json_load_dict(raw: str) -> dict[str, Any] | None:
    parsed = _json_load(raw)
    return parsed if isinstance(parsed, dict) else None


def _int_list(items: object) -> list[int]:
    if not isinstance(items, list):
        return []
    result: list[int] = []
    for item in items:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _responses_by_public_player_id(responses_by_player_id: dict[str, Any]) -> dict[str, Any]:
    responses: dict[str, Any] = {}
    for response in responses_by_player_id.values():
        if not isinstance(response, dict):
            continue
        public_player_id = str(response.get("public_player_id") or "").strip()
        if public_player_id:
            responses[public_player_id] = response
    return responses


_RECORD_BATCH_RESPONSE_LUA = """
local inserted = redis.call("HSETNX", KEYS[1], ARGV[1], ARGV[2])
local expected = cjson.decode(ARGV[3])
local remaining = {}
for i = 1, #expected do
  local player_id = tostring(expected[i])
  if redis.call("HEXISTS", KEYS[1], player_id) == 0 then
    table.insert(remaining, tonumber(player_id) or player_id)
  end
end
if #remaining > 0 then
  if inserted == 0 then
    return {"duplicate_pending", cjson.encode(remaining), "", "0", ""}
  end
  return {"pending", cjson.encode(remaining), "", "0", ""}
end
if redis.call("HSETNX", KEYS[2], ARGV[9], "1") == 0 then
  return {"duplicate_completed", cjson.encode(remaining), "", "0", ""}
end
if redis.call("HSETNX", KEYS[3], ARGV[4], "1") == 0 then
  return {"duplicate_completed", cjson.encode(remaining), "", "0", ""}
end
redis.call("HSET", KEYS[4], ARGV[4], "1")
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
local command_payload = cjson.decode(ARGV[8])
local responses = {}
local public_responses = {}
for i = 1, #expected do
  local player_id = tostring(expected[i])
  local raw_response = redis.call("HGET", KEYS[1], player_id)
  if raw_response then
    local response = cjson.decode(raw_response)
    responses[player_id] = response
    local public_player_id = response["public_player_id"]
    if public_player_id ~= nil and tostring(public_player_id) ~= "" then
      public_responses[tostring(public_player_id)] = response
    end
  end
end
command_payload["responses_by_player_id"] = responses
if next(public_responses) ~= nil then
  command_payload["responses_by_public_player_id"] = public_responses
end
command_payload["completed_at_ms"] = tonumber(ARGV[7]) or 0
local command_payload_json = cjson.encode(command_payload)
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
  command_payload_json
)
redis.call(
  "HSET",
  KEYS[7],
  tostring(seq),
  cjson.encode({
    seq = seq,
    session_id = ARGV[6],
    status = "accepted",
    type = ARGV[5],
    request_id = ARGV[10],
    updated_at_ms = tonumber(ARGV[7]) or 0
  })
)
if inserted == 0 then
  return {"duplicate_completed", cjson.encode(remaining), stream_id, tostring(seq), command_payload_json}
end
return {"completed", cjson.encode(remaining), stream_id, tostring(seq), command_payload_json}
"""
