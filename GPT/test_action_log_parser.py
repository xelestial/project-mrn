from __future__ import annotations

from action_log_parser import bundles_for_player, decision_rows, parse_action_log
from turn_advantage import build_advantage_snapshots


def test_parse_action_log_builds_turn_bundle():
    action_log = [
        {"event": "ai_decision_before", "decision": "choose_movement", "player": 1, "round_index": 1},
        {"event": "tile.purchase.attempt", "event_kind": "semantic_event", "turn_index": 0},
        {
            "event": "turn",
            "turn_index_global": 0,
            "round_index": 1,
            "player": 1,
            "character": "객주",
            "cell": "T2",
            "movement": {"roll": 4},
            "landing": {"type": "PURCHASE"},
            "cash_before": 20,
            "cash_after": 16,
            "tiles_before": 0,
            "tiles_after": 1,
            "hand_coins_before": 0,
            "hand_coins_after": 0,
            "shards_before": 4,
            "shards_after": 4,
            "f_before": 0,
            "f_after": 0,
            "alive_after": True,
        },
    ]
    bundles = parse_action_log(action_log)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.player == 1
    assert bundle.character == "객주"
    assert bundle.move_roll == 4
    assert bundle.landing_type == "PURCHASE"
    assert bundle.resource_deltas["cash"] == -4.0
    assert len(bundle.semantic_events) == 1
    assert len(decision_rows(bundle, "choose_movement")) == 1


def test_bundles_for_player_filters():
    action_log = [
        {"event": "turn", "turn_index_global": 0, "round_index": 1, "player": 1, "character": "객주", "cash_before": 20, "cash_after": 20},
        {"event": "turn", "turn_index_global": 1, "round_index": 1, "player": 2, "character": "박수", "cash_before": 20, "cash_after": 18},
    ]
    bundles = parse_action_log(action_log)
    assert len(bundles_for_player(bundles, 2)) == 1
    assert bundles_for_player(bundles, 2)[0].character == "박수"


def test_build_advantage_snapshots_ranks_leader():
    action_log = [
        {
            "event": "turn",
            "turn_index_global": 0,
            "round_index": 1,
            "player": 1,
            "character": "객주",
            "cash_before": 20,
            "cash_after": 20,
            "tiles_before": 0,
            "tiles_after": 1,
            "placed_score_coins_after": 0,
            "hand_coins_before": 0,
            "hand_coins_after": 0,
            "shards_before": 4,
            "shards_after": 4,
            "alive_after": True,
        },
        {
            "event": "turn",
            "turn_index_global": 1,
            "round_index": 1,
            "player": 2,
            "character": "박수",
            "cash_before": 20,
            "cash_after": 25,
            "tiles_before": 0,
            "tiles_after": 0,
            "placed_score_coins_after": 0,
            "hand_coins_before": 0,
            "hand_coins_after": 0,
            "shards_before": 4,
            "shards_after": 4,
            "alive_after": True,
        },
    ]
    bundles = parse_action_log(action_log)
    snapshots = build_advantage_snapshots(bundles, player_count=2)
    last_turn = [snap for snap in snapshots if snap.turn_index == 1]
    assert len(last_turn) == 2
    leader = min(last_turn, key=lambda snap: snap.rank)
    assert leader.player in {1, 2}
