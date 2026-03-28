from __future__ import annotations

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
    validation = validate_vis_stream(events)
    event_types = {event["event_type"] for event in events}

    assert result.total_turns > 0
    assert len(events) > 0
    assert validation["ok"] is True
    assert events[0]["event_type"] == "session_start"
    assert events[-1]["event_type"] == "game_end"
    assert {"round_start", "weather_reveal", "draft_pick", "final_character_choice"} <= event_types
    assert {"turn_start", "trick_window_open", "trick_window_closed", "dice_roll", "player_move", "turn_end_snapshot"} <= event_types
