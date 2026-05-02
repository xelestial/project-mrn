from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from apps.server.src.app import app
from apps.server.src.infra.game_debug_log import write_game_debug_log


class GameDebugLogTests(unittest.TestCase):
    def test_disabled_by_default_does_not_create_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="0", log_dir=temp_dir):
            write_game_debug_log("backend", "runtime_started", session_id="sess_1")

            self.assertFalse((Path(temp_dir) / "backend.jsonl").exists())

    def test_enabled_writes_component_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="1", log_dir=temp_dir):
            write_game_debug_log("backend", "runtime_started", session_id="sess_1", seed=42)

            rows = (Path(temp_dir) / "backend.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            parsed = json.loads(rows[0])
            self.assertEqual(parsed["component"], "backend")
            self.assertEqual(parsed["event"], "runtime_started")
            self.assertEqual(parsed["session_id"], "sess_1")
            self.assertEqual(parsed["seed"], 42)
            self.assertIn("ts_ms", parsed)

    def test_frontend_log_endpoint_writes_frontend_jsonl_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="1", log_dir=temp_dir):
            client = TestClient(app)
            response = client.post(
                "/api/v1/debug/frontend-log",
                json={
                    "event": "stream_message",
                    "session_id": "sess_front",
                    "seq": 7,
                    "payload": {"type": "event"},
                },
            )

            self.assertEqual(response.status_code, 202)
            rows = (Path(temp_dir) / "frontend.jsonl").read_text(encoding="utf-8").splitlines()
            parsed = json.loads(rows[-1])
            self.assertEqual(parsed["component"], "frontend")
            self.assertEqual(parsed["event"], "stream_message")
            self.assertEqual(parsed["session_id"], "sess_front")
            self.assertEqual(parsed["seq"], 7)
            self.assertEqual(parsed["payload"], {"type": "event"})


class _temporary_debug_env:
    def __init__(self, *, enabled: str, log_dir: str) -> None:
        self._enabled = enabled
        self._log_dir = log_dir
        self._before_enabled: str | None = None
        self._before_dir: str | None = None

    def __enter__(self) -> None:
        self._before_enabled = os.environ.get("MRN_DEBUG_GAME_LOGS")
        self._before_dir = os.environ.get("MRN_DEBUG_GAME_LOG_DIR")
        os.environ["MRN_DEBUG_GAME_LOGS"] = self._enabled
        os.environ["MRN_DEBUG_GAME_LOG_DIR"] = self._log_dir

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._before_enabled is None:
            os.environ.pop("MRN_DEBUG_GAME_LOGS", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOGS"] = self._before_enabled
        if self._before_dir is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_DIR", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_DIR"] = self._before_dir


if __name__ == "__main__":
    unittest.main()
