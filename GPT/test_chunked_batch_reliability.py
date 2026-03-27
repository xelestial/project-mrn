from __future__ import annotations

import json
from pathlib import Path

from run_chunked_batch import _merge_chunks
from simulate_with_logs import RunningSummary


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _stub_game(game_id: int, game_seed: int, global_game_index: int) -> dict:
    return {
        "version": "0.7.61",
        "doc_integrity_ok": True,
        "checked_pairs": [],
        "winner_ids": [1],
        "end_reason": "ALIVE_THRESHOLD",
        "total_turns": 10,
        "rounds_completed": 3,
        "alive_count": 2,
        "bankrupt_players": 2,
        "final_f_value": 5,
        "total_placed_coins": 1,
        "player_summary": [
            {"player_id": 0, "cash": 10, "tiles_owned": 1, "placed_score_coins": 0, "hand_coins": 0, "score": 1, "turns_taken": 3, "shards": 1, "character": "박수"},
            {"player_id": 1, "cash": 8, "tiles_owned": 0, "placed_score_coins": 0, "hand_coins": 0, "score": 0, "turns_taken": 3, "shards": 0, "character": "만신"},
        ],
        "strategy_summary": [
            {"player_id": 0, "character": "박수", "last_selected_character": "박수", "character_choice_counts": {"박수": 1}, "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0, "shard_income_cash": 0, "tricks_used": 0},
            {"player_id": 1, "character": "만신", "last_selected_character": "만신", "character_choice_counts": {"만신": 1}, "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0, "shard_income_cash": 0, "tricks_used": 0},
        ],
        "weather_history": [],
        "bankruptcy_events": [],
        "game_id": game_id,
        "chunk_game_id": game_id,
        "global_game_index": global_game_index,
        "run_id": "test_run",
        "root_seed": 42,
        "chunk_seed": 100 + game_id,
        "chunk_id": None,
        "game_seed": game_seed,
        "policy_mode": "arena",
        "lap_policy_mode": "heuristic_v1",
        "player_lap_policy_modes": {"1": "heuristic_v1", "2": "heuristic_v1"},
        "player_character_policy_modes": {"1": "heuristic_v1", "2": "heuristic_v1"},
    }


def test_merge_chunks_reassigns_global_index_and_chunk_id(tmp_path: Path) -> None:
    root = tmp_path / "merged"
    c1 = root / "chunk_001"
    c2 = root / "chunk_002"
    _write_rows(c1 / "games.jsonl", [_stub_game(0, 111, 0), _stub_game(1, 222, 1)])
    _write_rows(c2 / "games.jsonl", [_stub_game(0, 333, 0), _stub_game(1, 444, 1)])
    (c1 / "errors.jsonl").write_text("", encoding="utf-8")
    (c2 / "errors.jsonl").write_text("", encoding="utf-8")

    running = RunningSummary(policy_mode="arena")
    summary = _merge_chunks(root, running, [c1, c2])
    rows = [json.loads(line) for line in (root / "games.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["global_game_index"] for row in rows] == [0, 1, 2, 3]
    assert [row["chunk_id"] for row in rows] == [1, 1, 2, 2]
    assert [row["original_global_game_index"] for row in rows] == [0, 1, 0, 1]
    assert summary["reliability"]["duplicate_global_game_index_count"] == 0


def test_running_summary_reports_duplicate_game_seeds() -> None:
    running = RunningSummary(policy_mode="arena")
    running.update(_stub_game(0, 999, 0))
    running.update(_stub_game(1, 999, 1))
    summary = running.to_dict()
    assert summary["reliability"]["unique_game_seed_count"] == 1
    assert summary["reliability"]["duplicate_game_seed_count"] == 1
    assert summary["reliability"]["duplicate_game_seed_instances"] == 1
