from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from log_pipeline import (
    extract_turn_feature_rows,
    train_logistic_model,
    annotate_rows_with_probability,
    compute_pivotal_turns,
)


def _sample_game():
    return {
        "global_game_index": 1,
        "game_id": 0,
        "winner_ids": [1],
        "end_reason": "ALIVE_THRESHOLD",
        "total_turns": 2,
        "action_log": [
            {
                "event": "turn",
                "round_index": 1,
                "turn_index_global": 1,
                "player": 1,
                "character": "객주",
                "end_pos": 5,
                "cell": "T3",
                "laps_gained": 0,
                "lap_events": [],
                "movement": {"mode": "card_pair_fixed", "used_cards": [1, 4]},
                "landing": {"type": "PURCHASE", "cost": 4},
                "cash_after": 16,
                "hand_coins_after": 0,
                "shards_after": 4,
                "tiles_after": 1,
                "alive_after": True,
                "f_after": 0.0,
            },
            {
                "event": "turn",
                "round_index": 1,
                "turn_index_global": 2,
                "player": 2,
                "character": "파발꾼",
                "end_pos": 4,
                "cell": "T2",
                "laps_gained": 0,
                "lap_events": [],
                "movement": {"mode": "card_pair_fixed", "used_cards": [1, 3]},
                "landing": {"type": "PURCHASE_SKIP_POLICY", "cost": 3},
                "cash_after": 20,
                "hand_coins_after": 0,
                "shards_after": 4,
                "tiles_after": 0,
                "alive_after": True,
                "f_after": 0.0,
            },
        ],
    }


def test_extract_turn_feature_rows_emits_rows_and_labels():
    rows = extract_turn_feature_rows([_sample_game()])
    assert len(rows) == 2
    assert rows[0]["won"] == 1
    assert rows[1]["won"] == 0
    assert rows[0]["landing_purchase"] == 1.0
    assert rows[0]["used_pair_move"] == 1.0


def test_train_and_annotate_probability_range():
    rows = extract_turn_feature_rows([_sample_game()])
    model = train_logistic_model(rows, epochs=20)
    annotated = annotate_rows_with_probability(rows, model)
    assert all(0.0 <= row["predicted_win_prob"] <= 1.0 for row in annotated)


def test_compute_pivotal_turns_returns_one_per_player():
    rows = extract_turn_feature_rows([_sample_game()])
    model = train_logistic_model(rows, epochs=20)
    annotated = annotate_rows_with_probability(rows, model)
    pivotal = compute_pivotal_turns(annotated)
    assert len(pivotal) == 2
    assert {row["player_id"] for row in pivotal} == {1, 2}
