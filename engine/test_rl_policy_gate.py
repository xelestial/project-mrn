import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rl.replay import iter_replay_rows, write_replay_row


torch = pytest.importorskip("torch")


def test_behavior_clone_empty_dataset_writes_zero_model(tmp_path: Path):
    from rl.train_policy import train_behavior_clone

    replay = tmp_path / "empty.jsonl"
    replay.write_text("", encoding="utf-8")
    model_dir = tmp_path / "model"

    result = train_behavior_clone(replay_path=replay, output_dir=model_dir, seed=20260507)

    assert result["rows"] == 0
    assert result["validation_accuracy"] == 0.0
    assert (model_dir / "policy_model.json").exists()
    assert result["model_type"] == "empty"


def test_behavior_clone_trains_torch_model_and_predicts_legal_action(tmp_path: Path):
    from rl.evaluate_policy import evaluate_policy
    from rl.train_policy import predict_action, train_behavior_clone

    replay = tmp_path / "replay.jsonl"
    for step, action_id in enumerate(["buy", "skip", "buy", "buy", "skip", "buy"], start=1):
        write_replay_row(
            replay,
            {
                "game_id": 1,
                "step": step,
                "player_id": 1,
                "decision_key": "purchase_decision",
                "observation": {
                    "round_index": 1,
                    "turn_index": step,
                    "cash": 20 - step,
                    "position": step,
                    "f_value": 10,
                },
                "legal_actions": [
                    {"action_id": "buy", "legal": True},
                    {"action_id": "skip", "legal": True},
                ],
                "chosen_action_id": action_id,
                "reward": {"total": 1.0 if action_id == "buy" else -0.2, "components": {}},
                "done": step == 6,
            },
        )

    result = train_behavior_clone(
        replay_path=replay,
        output_dir=tmp_path / "model",
        seed=20260507,
        epochs=3,
        hidden_size=16,
    )
    row = next(iter_replay_rows(replay))
    prediction = predict_action(model_dir=tmp_path / "model", row=row)
    evaluation = evaluate_policy(model_dir=tmp_path / "model", replay_path=replay)

    assert result["model_type"] == "torch_behavior_clone"
    assert result["rows"] == 6
    assert result["train_examples"] == 12
    assert 0.0 <= result["validation_accuracy"] <= 1.0
    assert (tmp_path / "model" / "policy_model.pt").exists()
    assert prediction["action_id"] in {"buy", "skip"}
    assert prediction["scores"]
    assert evaluation["rows"] == 6
    assert evaluation["illegal_predictions"] == 0
    assert 0.0 <= evaluation["action_accuracy"] <= 1.0


def test_behavior_clone_weights_protocol_final_rank_and_high_impact_rewards(tmp_path: Path):
    from rl.train_policy import train_behavior_clone

    replay = tmp_path / "replay.jsonl"
    write_replay_row(
        replay,
        {
            "game_id": "protocol",
            "step": 1,
            "player_id": 4,
            "decision_key": "lap_reward",
            "observation": {"cash": 3, "shards": 1, "score": 2, "round_index": 4, "turn_index": 15},
            "legal_actions": [
                {"action_id": "cash", "legal": True, "label": "돈"},
                {"action_id": "shards", "legal": True, "label": "조각"},
                {"action_id": "score", "legal": True, "label": "승점"},
            ],
            "chosen_action_id": "cash",
            "reward": {
                "total": -2.0,
                "components": {"cash_delta": -4, "rent_paid": -3, "f_value_change": -1},
            },
            "outcome": {"final_rank": 4, "alive": False},
            "done": True,
        },
    )

    result = train_behavior_clone(replay_path=replay, output_dir=tmp_path / "model", seed=20260508, epochs=1, hidden_size=16)

    assert result["feature_schema"]["version"] == 2
    assert result["sample_weight"]["max"] > 1.5


def test_runtime_adapter_builds_purchase_row_and_predicts_legal_action(tmp_path: Path):
    from rl.runtime_adapter import build_purchase_replay_row, predict_runtime_action
    from rl.train_policy import train_behavior_clone

    replay = tmp_path / "replay.jsonl"
    for step, action_id in enumerate(["buy", "buy", "skip", "buy"], start=1):
        write_replay_row(
            replay,
            {
                "game_id": 1,
                "step": step,
                "player_id": 2,
                "decision_key": "purchase_decision",
                "observation": {"cash": 25 - step, "cost": 8, "position": step, "round_index": 1},
                "legal_actions": [
                    {"action_id": "buy", "legal": True},
                    {"action_id": "skip", "legal": True},
                ],
                "chosen_action_id": action_id,
                "reward": {"total": 1.0 if action_id == "buy" else -0.1, "components": {}},
                "done": False,
            },
        )
    train_behavior_clone(replay_path=replay, output_dir=tmp_path / "model", seed=20260507, epochs=2, hidden_size=16)

    state = SimpleNamespace(round_index=2, turn_index=7, f_value=12)
    player = SimpleNamespace(player_id=2, cash=18, shards=3, score=4, position=9, current_character="박수")
    row = build_purchase_replay_row(state, player, tile_index=9, cost=8, source="landing")
    prediction = predict_runtime_action(model_dir=tmp_path / "model", row=row)

    assert row["decision_key"] == "purchase_decision"
    assert row["player_id"] == 2
    assert row["observation"]["cost"] == 8
    assert prediction["action_id"] in {"buy", "skip"}


def test_runtime_adapter_converts_resource_actions_with_rules_budget():
    from rl.runtime_adapter import resource_reward_decision_from_action

    rules = SimpleNamespace(
        cash_pool=30,
        shards_pool=18,
        coins_pool=18,
        points_budget=20,
        cash_point_cost=1,
        shards_point_cost=4,
        coins_point_cost=7,
    )
    state = SimpleNamespace(
        config=SimpleNamespace(rules=SimpleNamespace(lap_reward=rules, start_reward=rules)),
        lap_reward_cash_pool_remaining=30,
        lap_reward_shards_pool_remaining=18,
        lap_reward_coins_pool_remaining=18,
        start_reward_cash_pool_remaining=30,
        start_reward_shards_pool_remaining=18,
        start_reward_coins_pool_remaining=18,
    )

    cash = resource_reward_decision_from_action("cash", state, rule_name="lap_reward")
    shards = resource_reward_decision_from_action("shards", state, rule_name="start_reward")
    coins = resource_reward_decision_from_action("coins", state, rule_name="lap_reward")

    assert cash.choice == "cash"
    assert cash.cash_units > 0
    assert cash.shard_units == 0
    assert shards.choice == "shards"
    assert shards.shard_units > 0
    assert coins.choice == "coins"
    assert coins.coin_units > 0


def test_runtime_adapter_builds_movement_row_and_converts_actions():
    from rl.runtime_adapter import build_movement_replay_row, movement_decision_from_action

    state = SimpleNamespace(round_index=2, turn_index=8, f_value=11, board=[None] * 32)
    player = SimpleNamespace(
        player_id=3,
        cash=17,
        shards=2,
        score=5,
        position=14,
        current_character="교리 연구관",
        used_dice_cards={2, 5},
    )

    row = build_movement_replay_row(state, player)
    legal_ids = [action["action_id"] for action in row["legal_actions"]]

    assert row["decision_key"] == "movement_decision"
    assert legal_ids == ["no_cards", "1", "3", "4", "6", "1+3", "1+4", "1+6", "3+4", "3+6", "4+6"]
    assert "2" not in legal_ids
    assert "2+5" not in legal_ids
    assert row["observation"]["remaining_cards"] == [1, 3, 4, 6]
    assert row["observation"]["board_len"] == 32
    assert movement_decision_from_action("no_cards").card_values == ()
    assert movement_decision_from_action("3").card_values == (3,)
    assert movement_decision_from_action("1+4").card_values == (1, 4)
    with pytest.raises(ValueError, match="out of range"):
        movement_decision_from_action("7")
    with pytest.raises(ValueError, match="repeat"):
        movement_decision_from_action("4+4")


def test_policy_factory_requires_rl_model_path(monkeypatch):
    from policy.factory import PolicyFactory

    monkeypatch.delenv("MRN_RL_POLICY_MODEL", raising=False)

    with pytest.raises(ValueError, match="MRN_RL_POLICY_MODEL"):
        PolicyFactory.create_runtime_policy(policy_mode="rl_v1")


def test_policy_factory_supports_mixed_arena_rl_seat(tmp_path: Path, monkeypatch):
    from policy.factory import PolicyFactory
    from policy.rl_policy import RlRuntimePolicy

    (tmp_path / "policy_model.json").write_text('{"model_type":"empty"}', encoding="utf-8")
    monkeypatch.setenv("MRN_RL_POLICY_MODEL", str(tmp_path))

    policy = PolicyFactory.create_runtime_policy(
        policy_mode="arena",
        player_character_policy_modes={
            1: "heuristic_v3_engine",
            2: "rl_v1",
            3: "heuristic_v3_engine",
            4: "heuristic_v3_engine",
        },
    )

    assert policy.runtime_policy_mode == "mixed"
    assert policy.character_mode_for_player(1) == "rl_v1"
    assert isinstance(policy._policy_for_player(SimpleNamespace(player_id=1)), RlRuntimePolicy)
    assert policy.character_mode_for_player(0) == "heuristic_v3_engine"


def test_rl_runtime_policy_uses_model_for_supported_decisions(tmp_path: Path, monkeypatch):
    from policy.factory import PolicyFactory
    from rl.train_policy import train_behavior_clone

    replay = tmp_path / "replay.jsonl"
    rows = [
        ("purchase_decision", "buy"),
        ("purchase_decision", "buy"),
        ("purchase_decision", "skip"),
        ("movement_decision", "no_cards"),
        ("movement_decision", "1+4"),
        ("lap_reward", "cash"),
        ("lap_reward", "cash"),
        ("start_reward", "shards"),
        ("start_reward", "shards"),
    ]
    for step, (decision_key, action_id) in enumerate(rows, start=1):
        if decision_key == "purchase_decision":
            legal_actions = [{"action_id": "buy", "legal": True}, {"action_id": "skip", "legal": True}]
        elif decision_key == "movement_decision":
            legal_actions = [
                {"action_id": "no_cards", "legal": True},
                {"action_id": "1", "legal": True},
                {"action_id": "4", "legal": True},
                {"action_id": "1+4", "legal": True},
            ]
        else:
            legal_actions = [
                {"action_id": "cash", "legal": True},
                {"action_id": "shards", "legal": True},
                {"action_id": "coins", "legal": True},
            ]
        write_replay_row(
            replay,
            {
                "game_id": 1,
                "step": step,
                "player_id": 1,
                "decision_key": decision_key,
                "observation": {"cash": 20, "shards": 2, "score": 1, "round_index": 1, "turn_index": step},
                "legal_actions": legal_actions,
                "chosen_action_id": action_id,
                "reward": {"total": 1.0, "components": {}},
                "done": False,
            },
        )
    train_behavior_clone(replay_path=replay, output_dir=tmp_path / "model", seed=20260507, epochs=2, hidden_size=16)
    monkeypatch.setenv("MRN_RL_POLICY_MODEL", str(tmp_path / "model"))

    policy = PolicyFactory.create_runtime_policy(policy_mode="rl_v1")
    rules = SimpleNamespace(
        cash_pool=30,
        shards_pool=18,
        coins_pool=18,
        points_budget=20,
        cash_point_cost=1,
        shards_point_cost=4,
        coins_point_cost=7,
    )
    state = SimpleNamespace(
        round_index=1,
        turn_index=1,
        f_value=9,
        config=SimpleNamespace(rules=SimpleNamespace(lap_reward=rules, start_reward=rules)),
        lap_reward_cash_pool_remaining=30,
        lap_reward_shards_pool_remaining=18,
        lap_reward_coins_pool_remaining=18,
        start_reward_cash_pool_remaining=30,
        start_reward_shards_pool_remaining=18,
        start_reward_coins_pool_remaining=18,
        board=[None] * 32,
    )
    player = SimpleNamespace(
        player_id=1,
        cash=20,
        shards=2,
        score=1,
        position=4,
        current_character="박수",
        used_dice_cards=set(),
    )

    purchase = policy.choose_purchase_tile(state, player, 4, "T2", 8)
    movement = policy.choose_movement(state, player)
    lap = policy.choose_lap_reward(state, player)
    start = policy.choose_start_reward(state, player)

    assert policy.runtime_policy_mode == "rl_v1"
    assert "movement_decision" in policy.supported_decisions
    assert purchase in {True, False}
    assert movement.use_cards in {True, False}
    assert all(1 <= card <= 6 for card in movement.card_values)
    assert lap.choice in {"cash", "shards", "coins", "blocked"}
    assert start.choice in {"cash", "shards", "coins", "blocked"}


def test_seed_matrix_runs_rl_v1_without_runtime_failures(tmp_path: Path):
    from rl.seed_matrix import run_seed_matrix
    from rl.train_policy import train_behavior_clone

    replay = tmp_path / "replay.jsonl"
    rows = [
        (
            "purchase_decision",
            "buy",
            [{"action_id": "buy", "legal": True}, {"action_id": "skip", "legal": True}],
        ),
        (
            "movement_decision",
            "no_cards",
            [
                {"action_id": "no_cards", "legal": True},
                {"action_id": "1", "legal": True},
                {"action_id": "1+2", "legal": True},
            ],
        ),
        (
            "lap_reward",
            "cash",
            [{"action_id": "cash", "legal": True}, {"action_id": "shards", "legal": True}, {"action_id": "coins", "legal": True}],
        ),
        (
            "start_reward",
            "shards",
            [{"action_id": "cash", "legal": True}, {"action_id": "shards", "legal": True}, {"action_id": "coins", "legal": True}],
        ),
    ]
    for step, (decision_key, action_id, legal_actions) in enumerate(rows, start=1):
        write_replay_row(
            replay,
            {
                "game_id": 1,
                "step": step,
                "player_id": 1,
                "decision_key": decision_key,
                "observation": {"cash": 20, "shards": 2, "score": 1, "round_index": 1, "turn_index": step},
                "legal_actions": legal_actions,
                "chosen_action_id": action_id,
                "reward": {"total": 1.0, "components": {}},
                "done": False,
            },
        )
    train_behavior_clone(replay_path=replay, output_dir=tmp_path / "model", seed=20260507, epochs=1, hidden_size=16)

    matrix = run_seed_matrix(
        seeds=[20260508, 20260509],
        simulations_per_seed=1,
        output_dir=tmp_path / "matrix",
        policy_mode="rl_v1",
        model_dir=tmp_path / "model",
    )

    assert matrix["seed_count"] == 2
    assert matrix["total_games"] == 2
    assert matrix["total_failed_games"] == 0
    assert (tmp_path / "matrix" / "seed_matrix.json").exists()


def test_gate_pipeline_writes_summary_and_learning_diagnostics(tmp_path: Path, monkeypatch):
    import rl.gate_pipeline as gate_pipeline

    def fake_simulate_run(**kwargs):
        replay_path = Path(kwargs["rl_replay_path"])
        write_replay_row(
            replay_path,
            {
                "game_id": 1,
                "seed": kwargs["seed"],
                "step": 1,
                "player_id": 1,
                "decision_key": "purchase_decision",
                "observation": {"cash": 2, "round_index": 1, "turn_index": 1},
                "legal_actions": [{"action_id": "buy", "legal": True}, {"action_id": "skip", "legal": True}],
                "chosen_action_id": "buy",
                "reward": {"total": -1.5, "components": {"low_cash_risk": -0.6}},
                "sample_weight": 2.0,
                "outcome": {"rank": 4, "won": False},
                "done": True,
            },
        )
        return {"games": kwargs["simulations"], "runtime_failed_count": 0}

    def fake_train_behavior_clone(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "policy_model.json").write_text('{"model_type":"empty"}', encoding="utf-8")
        return {"model_type": "empty", "rows": 1, "validation_accuracy": 0.0}

    def fake_run_policy_comparison(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        comparison = {
            "acceptance": {"accepted": False, "checks": {"mixed_seat_accepted": False}},
            "metrics": {"candidate": {"runtime_failed_count": 0}},
            "mixed_seat": {
                "rotations": [
                    {
                        "seat": 1,
                        "seed": kwargs["seed"],
                        "accepted": False,
                        "deltas": {"average_rank": 0.7, "bankruptcy_rate": 0.25, "win_rate": -0.1},
                    }
                ]
            },
        }
        (output_dir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False), encoding="utf-8")
        return comparison

    monkeypatch.setattr(gate_pipeline, "simulate_run", fake_simulate_run)
    monkeypatch.setattr(gate_pipeline, "train_behavior_clone", fake_train_behavior_clone)
    monkeypatch.setattr(gate_pipeline, "run_policy_comparison", fake_run_policy_comparison)

    summary = gate_pipeline.run_gate_pipeline(
        output_dir=tmp_path / "gate",
        train_games=1,
        eval_games=1,
        mixed_seat_games=1,
        seed=20260508,
        epochs=1,
        hidden_size=16,
    )

    assert summary["comparison"]["accepted"] is False
    assert summary["diagnostics"]["rows"] == 1
    assert summary["diagnostics"]["negative_reward_rate"] == 1.0
    assert summary["diagnostics"]["comparison_findings"]["failing_checks"] == [
        "acceptance.checks.mixed_seat_accepted"
    ]
    assert (tmp_path / "gate" / "pipeline_summary.json").exists()
    assert (tmp_path / "gate" / "learning_diagnostics.json").exists()
