from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class SessionStore(Protocol):
    def load_sessions(self) -> list[dict]:
        ...

    def save_sessions(self, sessions: list[dict]) -> None:
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
