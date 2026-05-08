import json
from pathlib import Path

import pytest

from rl.replay import write_replay_row


torch = pytest.importorskip("torch")


def test_protocol_policy_request_builds_compact_replay_row():
    from rl.protocol_policy_server import build_protocol_replay_row_from_policy_request

    payload = {
        "protocol_version": 1,
        "session_id": "sess_protocol",
        "player_id": 2,
        "commit_seq": 42,
        "runtime": {
            "status": "waiting_input",
            "round_index": 3,
            "turn_index": 11,
            "active_module_type": "PurchaseModule",
        },
        "prompt": {
            "request_id": "req_buy",
            "request_type": "purchase_tile",
            "prompt_instance_id": 9,
            "module_type": "PurchaseModule",
        },
        "legal_choices": [
            {"choice_id": "buy", "title": "BUY", "description": "Buy tile", "secondary": False, "value": {"x": 1}},
            {"choice_id": "pass", "title": "PASS", "description": "Skip", "secondary": True, "value": None},
        ],
        "player_summary": {
            "player_id": 2,
            "cash": 18,
            "score": 4,
            "total_score": 6,
            "shards": 2,
            "owned_tile_count": 3,
            "position": 15,
            "alive": True,
            "character": "박수",
        },
    }

    row = build_protocol_replay_row_from_policy_request(payload)

    assert row["game_id"] == "sess_protocol"
    assert row["player_id"] == 2
    assert row["decision_key"] == "purchase_tile"
    assert row["observation"] == {
        "commit_seq": 42,
        "round_index": 3,
        "turn_index": 11,
        "player_id": 2,
        "cash": 18,
        "score": 4,
        "total_score": 6,
        "shards": 2,
        "owned_tile_count": 3,
        "position": 15,
        "alive": True,
        "character": "박수",
    }
    assert row["legal_actions"] == [
        {"action_id": "buy", "legal": True, "label": "BUY"},
        {"action_id": "pass", "legal": True, "label": "PASS"},
    ]
    assert row["action_space_source"] == "full_stack_protocol_http"
    assert row["chosen_action_id"] == ""


def test_protocol_policy_decider_returns_only_legal_choice(tmp_path: Path):
    from rl.protocol_policy_server import decide_protocol_policy
    from rl.train_policy import train_behavior_clone

    replay = tmp_path / "replay.jsonl"
    for step, choice_id in enumerate(["buy", "buy", "pass", "buy"], start=1):
        write_replay_row(
            replay,
            {
                "game_id": "train",
                "step": step,
                "player_id": 1,
                "decision_key": "purchase_tile",
                "observation": {
                    "commit_seq": step,
                    "round_index": 1,
                    "turn_index": step,
                    "player_id": 1,
                    "cash": 20 - step,
                    "score": 1,
                    "total_score": 1,
                    "shards": 1,
                    "owned_tile_count": step,
                    "position": step,
                    "alive": True,
                    "character": "박수",
                },
                "legal_actions": [
                    {"action_id": "buy", "legal": True, "label": "BUY"},
                    {"action_id": "pass", "legal": True, "label": "PASS"},
                ],
                "chosen_action_id": choice_id,
                "reward": {"total": 1.0, "components": {}},
                "sample_weight": 1.0,
                "done": step == 4,
                "outcome": {},
            },
        )
    model_dir = tmp_path / "model"
    train_behavior_clone(replay_path=replay, output_dir=model_dir, seed=20260508, epochs=2, hidden_size=16)

    result = decide_protocol_policy(
        model_dir=model_dir,
        payload={
            "protocol_version": 1,
            "session_id": "sess_eval",
            "player_id": 1,
            "commit_seq": 7,
            "runtime": {"round_index": 1, "turn_index": 7},
            "prompt": {"request_id": "req_eval", "request_type": "purchase_tile"},
            "legal_choices": [{"choice_id": "pass", "title": "PASS"}],
            "player_summary": {"player_id": 1, "cash": 10, "alive": True, "character": "박수"},
        },
    )

    assert result["choice_id"] == "pass"
    assert json.dumps(result, ensure_ascii=False)


def test_protocol_policy_decider_preserves_active_flip_finish_payload(tmp_path: Path):
    from rl.protocol_policy_server import decide_protocol_policy

    (tmp_path / "model" / "policy_model.json").parent.mkdir(parents=True)
    (tmp_path / "model" / "policy_model.json").write_text(
        json.dumps({"model_type": "empty"}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = decide_protocol_policy(
        model_dir=tmp_path / "model",
        payload={
            "protocol_version": 1,
            "session_id": "sess_flip",
            "player_id": 1,
            "commit_seq": 3,
            "runtime": {"round_index": 1, "turn_index": 1},
            "prompt": {"request_id": "req_flip", "request_type": "active_flip"},
            "legal_choices": [
                {"choice_id": "none", "title": "완료"},
                {"choice_id": "burden_1", "title": "짐 1"},
                {"choice_id": "burden_2", "title": "짐 2"},
            ],
            "player_summary": {"player_id": 1, "cash": 20, "alive": True},
        },
    )

    assert result["choice_id"] == "none"
    assert result["choice_payload"] == {
        "selected_choice_ids": ["burden_1", "burden_2"],
        "finish_after_selection": True,
    }


def test_protocol_policy_decider_finishes_active_flip_after_prior_selection(tmp_path: Path, monkeypatch):
    from rl import protocol_policy_server

    (tmp_path / "model" / "policy_model.json").parent.mkdir(parents=True)
    (tmp_path / "model" / "policy_model.json").write_text(
        json.dumps({"model_type": "empty"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        protocol_policy_server,
        "predict_action",
        lambda *, model_dir, row: {"action_id": "burden_1", "scores": [{"action_id": "burden_1", "score": 1.0}]},
    )

    result = protocol_policy_server.decide_protocol_policy(
        model_dir=tmp_path / "model",
        payload={
            "protocol_version": 1,
            "session_id": "sess_flip",
            "player_id": 1,
            "commit_seq": 4,
            "runtime": {"round_index": 1, "turn_index": 1},
            "prompt": {
                "request_id": "req_flip",
                "request_type": "active_flip",
                "public_context": {
                    "already_flipped_count": 1,
                    "already_flipped_cards": ["burden_2"],
                    "flip_submit_mode": "finish_once",
                },
            },
            "legal_choices": [
                {"choice_id": "none", "title": "완료"},
                {"choice_id": "burden_1", "title": "짐 1"},
                {"choice_id": "burden_2", "title": "짐 2"},
            ],
            "player_summary": {"player_id": 1, "cash": 20, "alive": True},
        },
    )

    assert result["choice_id"] == "none"
    assert "choice_payload" not in result
