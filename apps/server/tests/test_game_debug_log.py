from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from apps.server.src.app import app
from apps.server.src.infra.game_debug_log import debug_game_log_run_dir, write_game_debug_log


class GameDebugLogTests(unittest.TestCase):
    def test_disabled_by_default_does_not_create_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="0", log_dir=temp_dir):
            write_game_debug_log("backend", "runtime_started", session_id="sess_1")

            self.assertFalse((Path(temp_dir) / "backend.jsonl").exists())
            self.assertEqual(list(Path(temp_dir).glob("**/*.jsonl")), [])

    def test_enabled_writes_component_jsonl_inside_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="1", log_dir=temp_dir, run_id="20260502-123456-test"):
            write_game_debug_log("backend", "runtime_started", session_id="sess_1", seed=42)

            rows = (Path(temp_dir) / "20260502-123456-test" / "backend.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            parsed = json.loads(rows[0])
            self.assertEqual(parsed["component"], "backend")
            self.assertEqual(parsed["event"], "runtime_started")
            self.assertEqual(parsed["session_id"], "sess_1")
            self.assertEqual(parsed["seed"], 42)
            self.assertRegex(parsed["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}")
            self.assertIn("ts_ms", parsed)

    def test_frontend_log_endpoint_writes_frontend_jsonl_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="1", log_dir=temp_dir, run_id="frontend-run"):
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
            rows = (Path(temp_dir) / "frontend-run" / "frontend.jsonl").read_text(encoding="utf-8").splitlines()
            parsed = json.loads(rows[-1])
            self.assertEqual(parsed["component"], "frontend")
            self.assertEqual(parsed["event"], "stream_message")
            self.assertEqual(parsed["session_id"], "sess_front")
            self.assertEqual(parsed["seq"], 7)
            self.assertEqual(parsed["payload"], {"type": "event"})

    def test_enabled_without_run_id_creates_timestamped_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="1", log_dir=temp_dir):
            write_game_debug_log("backend", "runtime_started", session_id="sess_1")

            run_dir = debug_game_log_run_dir()
            self.assertEqual(run_dir.parent, Path(temp_dir))
            self.assertRegex(run_dir.name, r"^\d{8}-\d{6}-\d{6}-p\d+$")
            self.assertTrue((run_dir / "backend.jsonl").exists())
            self.assertEqual([path.name for path in Path(temp_dir).iterdir()], [run_dir.name])


class _temporary_debug_env:
    def __init__(self, *, enabled: str, log_dir: str, run_id: str | None = None) -> None:
        self._enabled = enabled
        self._log_dir = log_dir
        self._run_id = run_id
        self._before_enabled: str | None = None
        self._before_dir: str | None = None
        self._before_run_id: str | None = None

    def __enter__(self) -> None:
        self._before_enabled = os.environ.get("MRN_DEBUG_GAME_LOGS")
        self._before_dir = os.environ.get("MRN_DEBUG_GAME_LOG_DIR")
        self._before_run_id = os.environ.get("MRN_DEBUG_GAME_LOG_RUN_ID")
        os.environ["MRN_DEBUG_GAME_LOGS"] = self._enabled
        os.environ["MRN_DEBUG_GAME_LOG_DIR"] = self._log_dir
        if self._run_id is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_RUN_ID", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_RUN_ID"] = self._run_id

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._before_enabled is None:
            os.environ.pop("MRN_DEBUG_GAME_LOGS", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOGS"] = self._before_enabled
        if self._before_dir is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_DIR", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_DIR"] = self._before_dir
        if self._before_run_id is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_RUN_ID", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_RUN_ID"] = self._before_run_id


if __name__ == "__main__":
    unittest.main()
