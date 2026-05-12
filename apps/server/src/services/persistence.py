from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from apps.server.src.infra.redis_client import RedisConnection


class SessionStore(Protocol):
    def load_sessions(self) -> list[dict]:
        ...

    def save_sessions(self, sessions: list[dict]) -> None:
        ...


class RoomStore(Protocol):
    def load_room_state(self) -> dict:
        ...

    def save_room_state(self, state: dict[str, Any]) -> None:
        ...


class StreamStore(Protocol):
    def load_stream_state(self) -> dict[str, Any]:
        ...

    def save_stream_state(self, state: dict[str, Any]) -> None:
        ...


class JsonFileSessionStore:
    """Simple JSON file session store for restart persistence baseline."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load_sessions(self) -> list[dict]:
        payload = self._read_json()
        sessions = payload.get("sessions", [])
        if isinstance(sessions, list):
            return [item for item in sessions if isinstance(item, dict)]
        return []

    def save_sessions(self, sessions: list[dict]) -> None:
        payload = self._read_json()
        payload["sessions"] = sessions
        self._write_json(payload)

    def save_session(self, session: dict) -> None:
        session_id = str(session.get("session_id", "")).strip()
        if not session_id:
            return
        payload = self._read_json()
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        updated = False
        next_sessions: list[dict] = []
        for existing in sessions:
            if not isinstance(existing, dict):
                continue
            if str(existing.get("session_id", "")).strip() == session_id:
                next_sessions.append(session)
                updated = True
            else:
                next_sessions.append(existing)
        if not updated:
            next_sessions.append(session)
        payload["sessions"] = next_sessions
        self._write_json(payload)

    def delete_session(self, session_id: str) -> None:
        target = str(session_id).strip()
        if not target:
            return
        payload = self._read_json()
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            return
        payload["sessions"] = [
            session
            for session in sessions
            if isinstance(session, dict)
            and str(session.get("session_id", "")).strip() != target
        ]
        self._write_json(payload)

    def load_room_state(self) -> dict:
        payload = self._read_json()
        room_state = payload.get("room_state")
        if isinstance(room_state, dict):
            return room_state
        rooms = payload.get("rooms")
        next_room_no = payload.get("next_room_no")
        migrated: dict[str, Any] = {}
        if isinstance(rooms, list):
            migrated["rooms"] = rooms
        if isinstance(next_room_no, int):
            migrated["next_room_no"] = next_room_no
        return migrated

    def save_room_state(self, state: dict[str, Any]) -> None:
        payload = self._read_json()
        payload["room_state"] = state
        self._write_json(payload)

    def _read_json(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            raw = self._path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _write_json(self, payload: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


class RedisSessionStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection
        self._hash_key = connection.key("sessions", "payloads")

    def load_sessions(self) -> list[dict]:
        payloads = self._connection.client().hgetall(self._hash_key)
        sessions: list[dict] = []
        for session_id in sorted(payloads):
            parsed = _json_load_dict(payloads[session_id])
            if parsed is None:
                continue
            sessions.append(parsed)
        return sessions

    def save_sessions(self, sessions: list[dict]) -> None:
        mapping: dict[str, str] = {}
        for session in sessions:
            session_id = str(session.get("session_id", "")).strip()
            if not session_id:
                continue
            mapping[session_id] = _json_dump(session)
        pipeline = self._connection.client().pipeline(transaction=True)
        pipeline.delete(self._hash_key)
        if mapping:
            pipeline.hset(self._hash_key, mapping=mapping)
        pipeline.execute()

    def save_session(self, session: dict) -> None:
        session_id = str(session.get("session_id", "")).strip()
        if not session_id:
            return
        self._connection.client().hset(self._hash_key, session_id, _json_dump(session))

    def delete_session(self, session_id: str) -> None:
        target = str(session_id).strip()
        if not target:
            return
        self._connection.client().hdel(self._hash_key, target)


class RedisRoomStore:
    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection
        self._rooms_hash_key = connection.key("rooms", "payloads")
        self._next_room_no_key = connection.key("rooms", "next_room_no")

    def load_room_state(self) -> dict[str, Any]:
        payloads = self._connection.client().hgetall(self._rooms_hash_key)
        rooms: list[dict] = []
        highest_room_no = 0
        for room_no in sorted(payloads, key=lambda raw: int(raw)):
            parsed = _json_load_dict(payloads[room_no])
            if parsed is None:
                continue
            rooms.append(parsed)
            try:
                highest_room_no = max(highest_room_no, int(room_no))
            except ValueError:
                continue
        next_room_no_raw = self._connection.client().get(self._next_room_no_key)
        next_room_no = int(next_room_no_raw) if isinstance(next_room_no_raw, str) and next_room_no_raw.isdigit() else 0
        if next_room_no < 1:
            next_room_no = highest_room_no + 1 if highest_room_no >= 1 else 1
        return {
            "next_room_no": next_room_no,
            "rooms": rooms,
        }

    def save_room_state(self, state: dict[str, Any]) -> None:
        rooms_raw = state.get("rooms", [])
        next_room_no_raw = state.get("next_room_no", 1)
        try:
            next_room_no = max(1, int(next_room_no_raw))
        except (TypeError, ValueError):
            next_room_no = 1
        mapping: dict[str, str] = {}
        for room in rooms_raw:
            if not isinstance(room, dict):
                continue
            room_no = room.get("room_no")
            if room_no is None:
                continue
            mapping[str(room_no)] = _json_dump(room)
        pipeline = self._connection.client().pipeline(transaction=True)
        pipeline.delete(self._rooms_hash_key)
        pipeline.delete(self._next_room_no_key)
        if mapping:
            pipeline.hset(self._rooms_hash_key, mapping=mapping)
        pipeline.set(self._next_room_no_key, str(next_room_no))
        pipeline.execute()


class JsonFileStreamStore:
    """Simple JSON file stream store for restart persistence baseline."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load_stream_state(self) -> dict[str, Any]:
        payload = self._read_json()
        state = payload.get("stream_state")
        if isinstance(state, dict):
            return state
        return {}

    def save_stream_state(self, state: dict[str, Any]) -> None:
        payload = self._read_json()
        payload["stream_state"] = state
        self._write_json(payload)

    def _read_json(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            raw = self._path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    def _write_json(self, payload: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


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
