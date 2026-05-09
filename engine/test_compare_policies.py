from __future__ import annotations

from compare_policies import _average_rank_from_games, _seat_metrics_from_games, build_policy_comparison, run_mixed_seat_comparison


def _summary(*, bankrupt_any_rate: float, avg_cash: float, games: int = 4) -> dict:
    return {
        "version": "test",
        "games": games,
        "bankrupt_any_rate": bankrupt_any_rate,
        "avg_total_turns": 10,
        "avg_rounds": 3,
        "avg_final_f_value": 12,
        "avg_final_shards_per_player": 1.5,
        "players": {
            "1": {"avg_cash": avg_cash, "avg_score": 4, "avg_placed": 2},
            "2": {"avg_cash": avg_cash + 1, "avg_score": 3, "avg_placed": 1},
        },
    }


def _games() -> list[dict]:
    return [
        {
            "player_summary": [
                {"player_id": 0, "score": 10, "placed_score_coins": 4, "cash": 8, "tiles_owned": 2},
                {"player_id": 1, "score": 8, "placed_score_coins": 4, "cash": 9, "tiles_owned": 2},
                {"player_id": 2, "score": 6, "placed_score_coins": 2, "cash": 7, "tiles_owned": 1},
                {"player_id": 3, "score": 1, "placed_score_coins": 0, "cash": 2, "tiles_owned": 0},
            ]
        }
    ]


def test_average_rank_from_games_orders_players_by_public_result_fields() -> None:
    assert _average_rank_from_games(_games()) == 2.5


def test_build_policy_comparison_accepts_candidate_within_thresholds() -> None:
    comparison = build_policy_comparison(
        baseline_policy="heuristic_v3_engine",
        candidate_policy="rl_v1",
        baseline_summary=_summary(bankrupt_any_rate=0.10, avg_cash=5),
        candidate_summary=_summary(bankrupt_any_rate=0.11, avg_cash=7),
        baseline_games=_games(),
        candidate_games=_games(),
        policy_eval={"illegal_predictions": 0},
        bankruptcy_tolerance=0.02,
    )

    assert comparison["acceptance"]["accepted"] is True
    assert comparison["deltas"]["avg_cash_per_player"] == 2.0
    assert comparison["acceptance"]["checks"]["bankruptcy_rate_not_regressed"] is True


def test_build_policy_comparison_rejects_illegal_predictions() -> None:
    comparison = build_policy_comparison(
        baseline_policy="heuristic_v3_engine",
        candidate_policy="rl_v1",
        baseline_summary=_summary(bankrupt_any_rate=0.10, avg_cash=5),
        candidate_summary=_summary(bankrupt_any_rate=0.10, avg_cash=7),
        baseline_games=_games(),
        candidate_games=_games(),
        policy_eval={"illegal_predictions": 1},
    )

    assert comparison["acceptance"]["accepted"] is False
    assert comparison["acceptance"]["checks"]["candidate_illegal_action_zero"] is False


def test_seat_metrics_track_rank_win_and_bankruptcy() -> None:
    metrics = _seat_metrics_from_games(
        [
            {
                "winner_ids": [2],
                "player_summary": [
                    {"player_id": 0, "score": 1, "placed_score_coins": 0, "cash": 10, "tiles_owned": 1, "alive": True},
                    {"player_id": 1, "score": 5, "placed_score_coins": 1, "cash": 20, "tiles_owned": 2, "alive": True},
                    {"player_id": 2, "score": 2, "placed_score_coins": 0, "cash": 0, "tiles_owned": 0, "alive": False},
                ],
            }
        ],
        seat=2,
    )

    assert metrics["games"] == 1
    assert metrics["average_rank"] == 1.0
    assert metrics["win_rate"] == 1.0
    assert metrics["bankruptcy_rate"] == 0.0


def test_mixed_seat_comparison_runs_candidate_one_seat_at_a_time(tmp_path, monkeypatch) -> None:
    import compare_policies

    runs = []

    def fake_run_policy(**kwargs):
        runs.append(kwargs)
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        modes = kwargs.get("player_character_policy_modes") or {}
        rl_seat = next((seat for seat, mode in modes.items() if mode == "rl_v1"), None)
        seat = rl_seat or 1
        player_summary = [
            {"player_id": 0, "score": 4 if seat == 1 else 1, "placed_score_coins": 0, "cash": 10, "tiles_owned": 1, "alive": True},
            {"player_id": 1, "score": 4 if seat == 2 else 1, "placed_score_coins": 0, "cash": 10, "tiles_owned": 1, "alive": True},
            {"player_id": 2, "score": 4 if seat == 3 else 1, "placed_score_coins": 0, "cash": 10, "tiles_owned": 1, "alive": True},
            {"player_id": 3, "score": 4 if seat == 4 else 1, "placed_score_coins": 0, "cash": 10, "tiles_owned": 1, "alive": True},
        ]
        (output_dir / "games.jsonl").write_text(
            compare_policies.json.dumps({"winner_ids": [seat], "player_summary": player_summary}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {
            "policy_mode": kwargs["policy_mode"],
            "output_dir": str(output_dir),
            "summary": {"games": 1, "bankrupt_any_rate": 0.0},
            "runtime_failed_count": 0,
            "error": None,
        }

    monkeypatch.setattr(compare_policies, "_run_policy", fake_run_policy)
    (tmp_path / "policy_model.json").write_text("{}", encoding="utf-8")

    comparison = run_mixed_seat_comparison(
        simulations_per_seat=1,
        seed=20260508,
        output_dir=tmp_path,
        baseline_policy="heuristic_v3_engine",
        candidate_policy="rl_v1",
        candidate_model_dir=tmp_path,
    )

    candidate_runs = [run for run in runs if run["output_dir"].name == "candidate"]
    assert [run["player_character_policy_modes"] for run in candidate_runs] == [
        {1: "rl_v1", 2: "heuristic_v3_engine", 3: "heuristic_v3_engine", 4: "heuristic_v3_engine"},
        {1: "heuristic_v3_engine", 2: "rl_v1", 3: "heuristic_v3_engine", 4: "heuristic_v3_engine"},
        {1: "heuristic_v3_engine", 2: "heuristic_v3_engine", 3: "rl_v1", 4: "heuristic_v3_engine"},
        {1: "heuristic_v3_engine", 2: "heuristic_v3_engine", 3: "heuristic_v3_engine", 4: "rl_v1"},
    ]
    assert comparison["acceptance"]["accepted"] is True
