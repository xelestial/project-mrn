from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


import random

from ai_policy import HeuristicPolicy
from config import DEFAULT_CONFIG
from engine import GameEngine
from validate_vis_stream import validate_vis_stream
from viewer.stream import VisEventStream


def test_validate_vis_stream_accepts_partial_known_event_stream() -> None:
    events = [
        {
            "event_type": "session_start",
            "session_id": "s1",
            "round_index": 1,
            "turn_index": 1,
            "step_index": 0,
            "acting_player_id": None,
            "public_phase": "session_start",
        },
        {
            "event_type": "turn_start",
            "session_id": "s1",
            "round_index": 1,
            "turn_index": 1,
            "step_index": 1,
            "acting_player_id": 1,
            "public_phase": "turn_start",
        },
        {
            "event_type": "dice_roll",
            "session_id": "s1",
            "round_index": 1,
            "turn_index": 1,
            "step_index": 2,
            "acting_player_id": 1,
            "public_phase": "movement",
        },
        {
            "event_type": "player_move",
            "session_id": "s1",
            "round_index": 1,
            "turn_index": 1,
            "step_index": 3,
            "acting_player_id": 1,
            "public_phase": "movement",
        },
        {
            "event_type": "turn_end_snapshot",
            "session_id": "s1",
            "round_index": 1,
            "turn_index": 1,
            "step_index": 4,
            "acting_player_id": 1,
            "public_phase": "turn_end",
        },
        {
            "event_type": "game_end",
            "session_id": "s1",
            "round_index": 1,
            "turn_index": 1,
            "step_index": 5,
            "acting_player_id": None,
            "public_phase": "game_end",
        },
    ]

    result = validate_vis_stream(events)

    assert result["ok"] is True
    assert "draft_pick" in result["missing_known_event_types"]
    assert result["counts"]["turn_start"] == 1


def test_game_engine_emits_visual_stream_that_validates() -> None:
    stream = VisEventStream()
    policy = HeuristicPolicy("heuristic_v3_gpt", "heuristic_v3_gpt", rng=random.Random(777))
    engine = GameEngine(
        DEFAULT_CONFIG,
        policy,
        rng=random.Random(777),
        enable_logging=False,
        event_stream=stream,
    )

    result = engine.run()
    events = stream.to_list()
    validation = validate_vis_stream(events, strict_payload=True)
    event_types = {event["event_type"] for event in events}

    assert result.total_turns > 0
    assert len(events) > 0
    assert validation["ok"] is True
    assert events[0]["event_type"] == "session_start"
    assert events[-1]["event_type"] == "game_end"
    assert {"round_start", "weather_reveal", "draft_pick", "final_character_choice"} <= event_types
    assert {"turn_start", "trick_window_open", "trick_window_closed", "dice_roll", "player_move", "turn_end_snapshot"} <= event_types
    # trick_used is optional per run; the validator already enforces payload shape when emitted.


def test_round_boundary_visual_events_carry_active_faces() -> None:
    stream = VisEventStream()
    policy = HeuristicPolicy("heuristic_v3_gpt", "heuristic_v3_gpt", rng=random.Random(123))
    engine = GameEngine(
        DEFAULT_CONFIG,
        policy,
        rng=random.Random(123),
        enable_logging=False,
        event_stream=stream,
    )

    engine.run()
    events = stream.to_list()

    round_start = next(event for event in events if event["event_type"] == "round_start")
    weather_reveal = next(event for event in events if event["event_type"] == "weather_reveal")
    round_order = next(event for event in events if event["event_type"] == "round_order")
    turn_end = next(event for event in events if event["event_type"] == "turn_end_snapshot")

    assert len(round_start["active_by_card"]) == 8
    assert len(weather_reveal["active_by_card"]) == 8
    assert len(round_order["active_by_card"]) == 8
    assert len(turn_end["snapshot"]["active_by_card"]) == 8
