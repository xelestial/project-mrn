"""Phase 1-V validation: verify VisEventStream correctness against SHARED_VISUAL_RUNTIME_CONTRACT.

Checks:
1. All required event types are present
2. Every player move has a matching dice_roll (same turn_index + acting_player_id)
3. Every turn has a turn_end_snapshot
4. step_index is strictly monotonically increasing
5. session_id is consistent across all events
6. No event is missing required envelope fields
"""
from __future__ import annotations

import sys
import random
sys.path.insert(0, ".")

from viewer.stream import VisEventStream
from engine import GameEngine
from config import DEFAULT_CONFIG
from ai_policy import HeuristicPolicy


REQUIRED_EVENT_TYPES = {
    "session_start", "round_start", "weather_reveal",
    "draft_pick", "final_character_choice",
    "turn_start", "trick_window_open", "trick_window_closed",
    "dice_roll", "player_move", "landing_resolved",
    "rent_paid", "tile_purchased",
    "fortune_drawn", "fortune_resolved",
    "mark_resolved", "marker_transferred",
    "lap_reward_chosen", "f_value_change",
    "bankruptcy", "turn_end_snapshot", "game_end",
}

REQUIRED_ENVELOPE_FIELDS = {
    "event_type", "session_id", "round_index", "turn_index",
    "step_index", "acting_player_id", "public_phase",
}


def run_game(seed: int) -> VisEventStream:
    config = DEFAULT_CONFIG
    stream = VisEventStream()
    policy = HeuristicPolicy(character_policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1")
    engine = GameEngine(config, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    return stream


def validate(stream: VisEventStream, seed: int) -> list[str]:
    errors: list[str] = []
    events = stream.to_list()

    if not events:
        return ["FATAL: stream is empty"]

    # 1. Envelope completeness
    for i, e in enumerate(events):
        missing = REQUIRED_ENVELOPE_FIELDS - e.keys()
        if missing:
            errors.append(f"[{i}] {e.get('event_type','?')} missing envelope fields: {missing}")

    # 2. step_index monotonically increasing
    prev_step = -1
    for e in events:
        s = e.get("step_index", -1)
        if s <= prev_step:
            errors.append(f"step_index not monotonic: {prev_step} -> {s} at event {e.get('event_type')}")
        prev_step = s

    # 3. session_id consistent
    session_ids = {e.get("session_id") for e in events}
    if len(session_ids) != 1:
        errors.append(f"Multiple session_ids found: {session_ids}")

    # 4. Required event types coverage
    present = {e["event_type"] for e in events}
    # Only check types that can appear (bankruptcy/mark_resolved may not occur in every game)
    optional = {"bankruptcy", "mark_resolved", "marker_transferred", "fortune_drawn",
                "fortune_resolved", "rent_paid", "tile_purchased", "lap_reward_chosen", "f_value_change"}
    for etype in REQUIRED_EVENT_TYPES - optional:
        if etype not in present:
            errors.append(f"Required event type missing: {etype}")

    # 5. dice_roll + player_move pairing per (turn_index, acting_player_id)
    dice_keys = {(e["turn_index"], e["acting_player_id"])
                 for e in events if e["event_type"] == "dice_roll"}
    move_keys = {(e["turn_index"], e["acting_player_id"])
                 for e in events if e["event_type"] == "player_move"}
    unpaired_dice = dice_keys - move_keys
    unpaired_move = move_keys - dice_keys
    if unpaired_dice:
        errors.append(f"dice_roll without player_move for keys: {unpaired_dice}")
    if unpaired_move:
        errors.append(f"player_move without dice_roll for keys: {unpaired_move}")

    # 6. Every turn_start has a matching turn_end_snapshot
    start_keys = {(e["turn_index"], e["acting_player_id"])
                  for e in events if e["event_type"] == "turn_start" and not e.get("skipped")}
    end_keys = {(e["turn_index"], e["acting_player_id"])
                for e in events if e["event_type"] == "turn_end_snapshot"}
    missing_ends = start_keys - end_keys
    if missing_ends:
        errors.append(f"turn_start without turn_end_snapshot for keys: {missing_ends}")

    # 7. session_start is first, game_end is last
    if events[0]["event_type"] != "session_start":
        errors.append(f"First event is not session_start: {events[0]['event_type']}")
    if events[-1]["event_type"] != "game_end":
        errors.append(f"Last event is not game_end: {events[-1]['event_type']}")

    return errors


def main():
    seeds = [42, 137, 999]
    all_passed = True
    for seed in seeds:
        print(f"Running seed={seed}...", end=" ")
        stream = run_game(seed)
        summary = stream.summary()
        errors = validate(stream, seed)
        if errors:
            all_passed = False
            print(f"FAIL ({summary['total_events']} events)")
            for e in errors:
                print(f"  ERROR: {e}")
        else:
            print(f"OK ({summary['total_events']} events, {len(summary['by_type'])} types)")

    if all_passed:
        print("\nPhase 1-V: ALL CHECKS PASSED")
        return 0
    else:
        print("\nPhase 1-V: VALIDATION FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
