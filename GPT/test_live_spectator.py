from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from viewer.live_runtime import run_live_seed, write_live_viewer_files


def test_write_live_viewer_files() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        index_path = write_live_viewer_files(tmp_dir)
        assert index_path.exists()
        html = index_path.read_text(encoding="utf-8")
        assert "GPT Live Spectator" in html
        assert "live_state.json" in html
        assert "/api/prompt-response" in html
        assert 'id="board-summary"' in html
        assert 'id="prompt-side"' in html
        assert "Player Panels" in html


def test_run_live_seed_writes_live_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        stream = run_live_seed(seed=42, out_dir=tmp_dir)
        summary = stream.summary()
        assert summary["total_events"] > 0

        events_path = Path(tmp_dir) / "events.jsonl"
        state_path = Path(tmp_dir) / "live_state.json"
        index_path = Path(tmp_dir) / "index.html"

        assert events_path.exists()
        assert state_path.exists()
        assert index_path.exists()

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["schema"] == "gpt.phase3.live_state.v1"
        assert state["status"] == "completed"
        assert state["summary"]["total_events"] == summary["total_events"]
        assert state["projection"]["session"]["turns"]
        assert state["latest_turn"] is not None
