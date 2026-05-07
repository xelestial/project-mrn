from pathlib import Path

from rl.action_space import normalize_decision_action_space
from rl.batch import run_replay_batch
from rl.env import ReplayLearningEnv
from rl.evaluation_report import build_policy_evaluation_report
from rl.replay import build_replay_rows_from_game, iter_replay_rows, write_replay_row
from rl.reward import compute_reward_from_event
from rl.train_baseline import train_behavior_baseline
from simulate_with_logs import run as simulate_run


def test_replay_round_trip_jsonl(tmp_path: Path):
    path = tmp_path / "replay.jsonl"
    row = {
        "game_id": "g1",
        "step": 1,
        "player_id": 2,
        "observation": {"cash": 20},
        "legal_actions": [{"action_id": "a", "legal": True}],
        "chosen_action_id": "a",
        "reward": {"total": 1.0, "components": {"cash_delta": 5.0}},
        "done": False,
    }
    write_replay_row(path, row)
    assert list(iter_replay_rows(path)) == [row]


def test_build_replay_rows_pairs_decisions_with_turn_rewards():
    game = {
        "game_id": 7,
        "global_game_index": 11,
        "game_seed": 20260507,
        "policy_mode": "heuristic_v3_engine",
        "winner_ids": [2],
        "end_reason": "SCORE",
        "ai_decision_log": [
            {
                "decision_key": "purchase_decision",
                "player_id": 2,
                "round_index": 1,
                "turn_index": 2,
                "position": 4,
                "f_value": 3,
                "payload": {
                    "options": [
                        {"action_id": "buy", "legal": True, "label": "BUY"},
                        {"action_id": "skip", "legal": True, "label": "SKIP"},
                    ],
                    "cash": 20,
                },
                "result": {"action_id": "buy", "purchased": True},
            }
        ],
        "action_log": [
            {
                "event": "turn",
                "player": 2,
                "round_index": 1,
                "turn_index_global": 2,
                "cash_before": 20,
                "cash_after": 16,
                "landing": {"type": "PURCHASE", "cost": 4},
            }
        ],
    }

    rows = build_replay_rows_from_game(game)

    assert len(rows) == 1
    assert rows[0]["game_id"] == 11
    assert rows[0]["seed"] == 20260507
    assert rows[0]["player_id"] == 2
    assert rows[0]["decision_key"] == "purchase_decision"
    assert rows[0]["legal_actions"] == [
        {"action_id": "buy", "legal": True, "label": "BUY"},
        {"action_id": "skip", "legal": True, "label": "SKIP"},
    ]
    assert rows[0]["chosen_action_id"] == "buy"
    assert rows[0]["reward"]["components"]["cash_delta"] == -4.0
    assert rows[0]["done"] is True


def test_build_replay_rows_does_not_assign_turn_reward_to_draft_decisions():
    game = {
        "game_id": 1,
        "ai_decision_log": [
            {
                "decision_key": "draft_card",
                "player_id": 1,
                "round_index": 1,
                "turn_index": 1,
                "turn_index_for_player": 0,
                "payload": {"offered_cards": [2, 5]},
                "result": {"picked_card": 5},
            }
        ],
        "action_log": [
            {
                "event": "turn",
                "player": 1,
                "round_index": 1,
                "turn_index_global": 1,
                "cash_before": 20,
                "cash_after": 12,
                "landing": {"type": "RENT", "rent": 8},
            }
        ],
    }

    rows = build_replay_rows_from_game(game)

    assert rows[0]["reward"]["total"] == 0.0
    assert rows[0]["reward"]["components"]["cash_delta"] == 0.0
    assert rows[0]["legal_actions"] == [
        {"action_id": "2", "legal": True, "label": "2"},
        {"action_id": "5", "legal": True, "label": "5"},
    ]
    assert rows[0]["chosen_action_id"] == "5"


def test_reward_breakdown_includes_shards_score_and_end_time_delta():
    reward = compute_reward_from_event(
        {
            "event": "turn",
            "cash_before": 10,
            "cash_after": 14,
            "shards_before": 1,
            "shards_after": 3,
            "score_before": 2,
            "score_after": 5,
            "f_value_before": 7,
            "f_value_after": 5,
        }
    )

    assert reward.components["cash_delta"] == 4.0
    assert reward.components["shard_delta"] == 2.0
    assert reward.components["score_delta"] == 3.0
    assert reward.components["end_time_delta"] == -2.0
    assert reward.total > 0


def test_simulator_emits_rl_replay_jsonl(tmp_path: Path):
    replay_path = tmp_path / "rl-replay.jsonl"

    simulate_run(
        simulations=1,
        seed=20260507,
        output_dir=str(tmp_path / "sim"),
        log_level="summary",
        policy_mode="heuristic_v3_engine",
        emit_summary=False,
        emit_rl_replay=True,
        rl_replay_path=str(replay_path),
    )

    rows = list(iter_replay_rows(replay_path))
    assert rows
    assert {"game_id", "step", "player_id", "observation", "legal_actions", "chosen_action_id", "reward", "done"} <= set(rows[0])


def test_action_space_normalizes_known_decisions_without_payload_options():
    purchase_actions = normalize_decision_action_space(
        {"decision_key": "purchase_decision", "payload": {}, "result": {"purchased": False}}
    )
    lap_actions = normalize_decision_action_space(
        {"decision_key": "lap_reward", "payload": {}, "result": {"choice": "shards"}}
    )

    assert purchase_actions.legal_actions == [
        {"action_id": "buy", "legal": True, "label": "BUY"},
        {"action_id": "skip", "legal": True, "label": "SKIP"},
    ]
    assert purchase_actions.chosen_action_id == "skip"
    assert [a["action_id"] for a in lap_actions.legal_actions] == ["cash", "shards", "coins"]
    assert lap_actions.chosen_action_id == "shards"


def test_replay_env_steps_over_rows_and_exposes_action_mask():
    env = ReplayLearningEnv(
        [
            {
                "observation": {"cash": 20},
                "legal_actions": [{"action_id": "buy", "legal": True}, {"action_id": "skip", "legal": False}],
                "chosen_action_id": "buy",
                "reward": {"total": 0.5, "components": {"cash_delta": 2}},
                "done": False,
            },
            {
                "observation": {"cash": 22},
                "legal_actions": [{"action_id": "cash", "legal": True}],
                "chosen_action_id": "cash",
                "reward": {"total": 1.0, "components": {"cash_delta": 5}},
                "done": True,
            },
        ]
    )

    observation = env.reset()
    assert observation == {"cash": 20}
    assert env.legal_actions() == [{"action_id": "buy", "legal": True}, {"action_id": "skip", "legal": False}]
    next_observation, reward, done, info = env.step("buy")
    assert next_observation == {"cash": 22}
    assert reward == 0.5
    assert done is False
    assert info["expert_action_id"] == "buy"


def test_replay_batch_and_baseline_training_write_artifacts(tmp_path: Path):
    batch_dir = tmp_path / "batch"
    summary = run_replay_batch(
        simulations=2,
        seed=20260507,
        output_dir=batch_dir,
        policy_mode="heuristic_v3_engine",
    )

    replay_path = batch_dir / "rl_replay.jsonl"
    assert replay_path.exists()
    assert summary["replay_rows"] > 0
    assert summary["failed_games"] == 0
    assert (batch_dir / "rl_manifest.json").exists()
    rows = list(iter_replay_rows(replay_path))
    assert [row["decision_key"] for row in rows if not row.get("legal_actions")] == []

    train_result = train_behavior_baseline(
        replay_path=replay_path,
        output_dir=tmp_path / "model",
    )

    assert train_result["rows"] == summary["replay_rows"]
    assert train_result["decision_count"] > 0
    assert 0.0 <= train_result["behavior_accuracy"] <= 1.0
    assert (tmp_path / "model" / "policy_baseline.json").exists()


def test_policy_evaluation_report_compares_numeric_metrics():
    report = build_policy_evaluation_report(
        baseline_summary={"avg_turns": 10, "by_player_id": {"1": {"avg_cash": 5}}},
        candidate_summary={"avg_turns": 8, "by_player_id": {"1": {"avg_cash": 7}}},
        policy_eval={"rows": 12, "illegal_predictions": 0},
        seed_matrix={"policy_mode": "rl_v1", "seed_count": 2, "total_games": 2, "total_failed_games": 0},
    )

    assert report["metric_deltas"]["avg_turns"]["delta"] == -2.0
    assert report["metric_deltas"]["by_player_id.1.avg_cash"]["delta"] == 2.0
    assert report["policy_eval"]["illegal_predictions"] == 0
    assert report["seed_matrix"]["total_failed_games"] == 0
