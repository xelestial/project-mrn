from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/scripts/game_debug_log_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("game_debug_log_audit", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(component: str, event: str, **fields):
    return {
        "component": component,
        "event": event,
        "ts": "2026-05-04T12:00:00.000+09:00",
        "ts_ms": 1777873200000,
        **fields,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_debug_log_audit_accepts_clean_draft_to_final_flow(tmp_path: Path) -> None:
    script = _load_script()
    run_dir = tmp_path / "20260504-120000-000001-p123"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "frontend.jsonl",
        [
            _row(
                "frontend",
                "stream_message",
                session_id="sess_1",
                payload={
                    "type": "prompt",
                    "payload": {
                        "request_id": "draft_1",
                        "request_type": "draft_card",
                        "player_id": 1,
                        "choices": [{"id": "6"}, {"id": "2"}],
                    },
                },
            ),
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={"request_id": "draft_1", "player_id": 1, "choice_id": "6"},
            ),
            _row(
                "frontend",
                "stream_message",
                session_id="sess_1",
                payload={
                    "type": "prompt",
                    "payload": {
                        "request_id": "final_1",
                        "request_type": "final_character",
                        "player_id": 1,
                        "choices": [{"id": "6"}, {"id": "8"}],
                    },
                },
            ),
        ],
    )
    _write_jsonl(
        run_dir / "backend.jsonl",
        [_row("backend", "decision_received", session_id="sess_1", request_id="draft_1", player_id=1, status="accepted")],
    )
    _write_jsonl(
        run_dir / "engine.jsonl",
        [_row("engine", "marker_flip", session_id="sess_1", module_type="RoundEndCardFlipModule")],
    )

    report = script.audit_debug_log_run(run_dir)

    assert report["ok"] is True
    assert report["violations"] == []


def test_debug_log_audit_reads_final_prompt_legal_choices(tmp_path: Path) -> None:
    script = _load_script()
    run_dir = tmp_path / "20260504-120000-000001-p123"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "frontend.jsonl",
        [
            _row(
                "frontend",
                "stream_message",
                session_id="sess_1",
                payload={
                    "type": "prompt",
                    "payload": {
                        "request_id": "draft_1",
                        "request_type": "draft_card",
                        "player_id": 1,
                        "legal_choices": [{"choice_id": "6"}, {"choice_id": "2"}],
                    },
                },
            ),
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={"request_id": "draft_1", "player_id": 1, "choice_id": "6"},
            ),
            _row(
                "frontend",
                "stream_message",
                session_id="sess_1",
                payload={
                    "type": "prompt",
                    "payload": {
                        "request_id": "final_1",
                        "request_type": "final_character",
                        "player_id": 1,
                        "legal_choices": [{"choice_id": "6"}, {"choice_id": "8"}],
                    },
                },
            ),
        ],
    )
    _write_jsonl(
        run_dir / "backend.jsonl",
        [_row("backend", "decision_received", session_id="sess_1", request_id="draft_1", player_id=1, status="accepted")],
    )
    _write_jsonl(
        run_dir / "engine.jsonl",
        [_row("engine", "marker_flip", session_id="sess_1", module_type="RoundEndCardFlipModule")],
    )

    report = script.audit_debug_log_run(run_dir)

    assert report["ok"] is True
    assert report["violations"] == []


def test_debug_log_audit_reports_known_turn_flow_violations(tmp_path: Path) -> None:
    script = _load_script()
    run_dir = tmp_path / "20260504-120000-000001-p123"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "frontend.jsonl",
        [
            _row(
                "frontend",
                "stream_message",
                session_id="sess_1",
                payload={
                    "type": "prompt",
                    "payload": {
                        "request_id": "draft_1",
                        "request_type": "draft_card",
                        "player_id": 1,
                        "choices": [{"id": "6"}, {"id": "2"}],
                    },
                },
            ),
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={"request_id": "draft_1", "player_id": 1, "choice_id": "6"},
            ),
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={"request_id": "draft_1", "player_id": 1, "choice_id": "6"},
            ),
            _row(
                "frontend",
                "stream_message",
                session_id="sess_1",
                payload={
                    "type": "prompt",
                    "payload": {
                        "request_id": "final_1",
                        "request_type": "final_character",
                        "player_id": 1,
                        "choices": [{"id": "8"}],
                    },
                },
            ),
        ],
    )
    _write_jsonl(
        run_dir / "backend.jsonl",
        [
            _row("backend", "decision_received", session_id="sess_1", request_id="draft_1", player_id=1, status="accepted"),
            _row("backend", "decision_received", session_id="sess_1", request_id="draft_1", player_id=1, status="accepted"),
            _row(
                "backend",
                "runtime_failed",
                session_id="sess_1",
                error="RoundEndCardFlipModule cannot be emitted from active turn context",
            ),
        ],
    )
    _write_jsonl(
        run_dir / "engine.jsonl",
        [
            _row("engine", "marker_flip", session_id="sess_1", module_type="PlayerTurnModule"),
            _row(
                "engine",
                "transition",
                session_id="sess_1",
                module_type="".join(("Leg", "acy", "ActionAdapterModule")),
            ),
        ],
    )

    report = script.audit_debug_log_run(run_dir)
    codes = {issue["code"] for issue in report["violations"]}

    assert report["ok"] is False
    assert {
        "frontend_duplicate_decision_sent",
        "backend_duplicate_decision_accept",
        "draft_choice_missing_from_final_prompt",
        "round_end_flip_active_turn_violation",
        "card_flip_wrong_module",
        "forbidden_action_adapter_signal",
    }.issubset(codes)


def test_debug_log_audit_groups_duplicate_decisions_by_public_identity(tmp_path: Path) -> None:
    script = _load_script()
    run_dir = tmp_path / "20260504-120000-000001-p123"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "frontend.jsonl",
        [
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={"request_id": "simultaneous_1", "primary_player_id": "player_public_1", "choice_id": "a"},
            ),
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={"request_id": "simultaneous_1", "primary_player_id": "player_public_2", "choice_id": "b"},
            ),
        ],
    )
    _write_jsonl(
        run_dir / "backend.jsonl",
        [
            _row(
                "backend",
                "decision_received",
                session_id="sess_1",
                request_id="simultaneous_1",
                primary_player_id="player_public_1",
                status="accepted",
            ),
            _row(
                "backend",
                "decision_received",
                session_id="sess_1",
                request_id="simultaneous_1",
                primary_player_id="player_public_2",
                status="accepted",
            ),
        ],
    )

    report = script.audit_debug_log_run(run_dir)

    assert report["ok"] is True
    assert report["violations"] == []


def test_debug_log_audit_prefers_nested_primary_identity_over_numeric_alias(tmp_path: Path) -> None:
    script = _load_script()
    run_dir = tmp_path / "20260504-120000-000001-p123"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "frontend.jsonl",
        [
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={
                    "request_id": "simultaneous_1",
                    "player_id": 1,
                    "identity": {"primary_player_id": "player_public_1"},
                    "choice_id": "a",
                },
            ),
            _row(
                "frontend",
                "decision_sent",
                session_id="sess_1",
                payload={
                    "request_id": "simultaneous_1",
                    "player_id": 1,
                    "identity": {"primary_player_id": "player_public_2"},
                    "choice_id": "b",
                },
            ),
        ],
    )

    report = script.audit_debug_log_run(run_dir)

    assert report["ok"] is True
    assert report["violations"] == []


def test_debug_log_audit_uses_latest_child_run_from_parent(tmp_path: Path) -> None:
    script = _load_script()
    older = tmp_path / "20260504-120000-000001-p123"
    newer = tmp_path / "20260504-120001-000001-p123"
    older.mkdir()
    newer.mkdir()
    _write_jsonl(older / "backend.jsonl", [_row("backend", "runtime_failed", error="older")])
    _write_jsonl(newer / "backend.jsonl", [_row("backend", "runtime_started")])

    report = script.audit_debug_log_run(tmp_path)

    assert report["run_dir"] == str(newer)


def test_debug_log_audit_prefers_child_run_when_parent_has__component_logs(tmp_path: Path) -> None:
    script = _load_script()
    child = tmp_path / "20260504-120001-000001-p123"
    child.mkdir()
    _write_jsonl(tmp_path / "backend.jsonl", [_row("backend", "runtime_failed", error="invalid root")])
    _write_jsonl(child / "backend.jsonl", [_row("backend", "runtime_started")])

    report = script.audit_debug_log_run(tmp_path)

    assert report["run_dir"] == str(child)
