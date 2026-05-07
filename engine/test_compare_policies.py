from __future__ import annotations

from compare_policies import _average_rank_from_games, build_policy_comparison


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
