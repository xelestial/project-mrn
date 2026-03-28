"""Phase 2-S — GPT Viewer Compatibility Validation.

Verifies that CLAUDE's VisEventStream emits field names that are
compatible with the GPT live viewer (live_html.py / play_html.py).

Checks:
1. player_move  : from_pos, to_pos, lapped
2. rent_paid    : payer_player_id, final_amount
3. lap_reward_chosen : amount
4. weather_reveal: weather_name
5. game_end     : winner_player_id, reason
6. mark_resolved: success, target_player_id, source_player_id
7. turn_end_snapshot.board : marker_owner_id
8. turn_end_snapshot.players : tiles_owned, score_coins_placed,
                                trick_cards_visible, is_marked, immune_to_marks
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import GameEngine
from config import DEFAULT_CONFIG
from ai_policy import HeuristicPolicy
from viewer.stream import VisEventStream


def _run(seed: int) -> list:
    stream = VisEventStream()
    policy = HeuristicPolicy(
        character_policy_mode="heuristic_v1",
        lap_policy_mode="heuristic_v1",
    )
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    return stream.events


def check_field(errors: list, event_type: str, event: dict, *fields: str) -> None:
    missing = [f for f in fields if f not in event]
    if missing:
        errors.append(f"{event_type}: missing fields {missing} (step={event.get('step_index')})")


def validate_seed(seed: int) -> list[str]:
    events = _run(seed)
    errors: list[str] = []
    dicts = [e.to_dict() for e in events]

    found: dict[str, bool] = {}

    for ev in dicts:
        t = ev["event_type"]

        if t == "player_move" and "player_move" not in found:
            found["player_move"] = True
            check_field(errors, t, ev, "from_pos", "to_pos", "lapped")

        elif t == "rent_paid" and "rent_paid" not in found:
            found["rent_paid"] = True
            check_field(errors, t, ev, "payer_player_id", "final_amount", "owner_player_id", "amount")

        elif t == "lap_reward_chosen" and "lap_reward_chosen" not in found:
            found["lap_reward_chosen"] = True
            check_field(errors, t, ev, "choice", "amount")

        elif t == "weather_reveal" and "weather_reveal" not in found:
            found["weather_reveal"] = True
            check_field(errors, t, ev, "weather_name")

        elif t == "game_end":
            found["game_end"] = True
            check_field(errors, t, ev, "winner_player_id", "reason")

        elif t == "mark_resolved" and "mark_resolved" not in found:
            found["mark_resolved"] = True
            check_field(errors, t, ev, "success", "source_player_id", "target_player_id")

        elif t == "turn_end_snapshot":
            snap = ev.get("snapshot", {})
            board = snap.get("board", {})
            players = snap.get("players", [])

            if "turn_end_snapshot" not in found:
                found["turn_end_snapshot"] = True
                if "marker_owner_id" not in board:
                    errors.append(f"turn_end_snapshot.board: missing marker_owner_id")
                for req in ("tiles", "f_value"):
                    if req not in board:
                        errors.append(f"turn_end_snapshot.board: missing {req}")

            if players and "turn_end_snapshot_player" not in found:
                found["turn_end_snapshot_player"] = True
                p0 = players[0]
                for req in ("tiles_owned", "score_coins_placed", "trick_cards_visible",
                            "is_marked", "immune_to_marks", "player_id", "cash", "shards",
                            "position", "alive", "character"):
                    if req not in p0:
                        errors.append(f"turn_end_snapshot.players[0]: missing {req}")

    # Check required types existed
    for required in ("player_move", "rent_paid", "lap_reward_chosen", "weather_reveal",
                     "game_end", "turn_end_snapshot"):
        if required not in found and required != "mark_resolved":
            if required == "rent_paid":
                # Possible no rent event in some seeds
                pass
            else:
                errors.append(f"No {required} event found in seed={seed}")

    return errors


def main() -> int:
    seeds = [42, 137, 999, 13]
    print("Phase 2-S GPT Viewer Compatibility Checks")
    print("=" * 45)

    all_passed = True
    for seed in seeds:
        errors = validate_seed(seed)
        if errors:
            all_passed = False
            print(f"  FAIL seed={seed}")
            for e in errors:
                print(f"    {e}")
        else:
            print(f"  OK   seed={seed}")

    if all_passed:
        print("\nPhase 2-S: ALL COMPATIBILITY CHECKS PASSED")
        return 0
    else:
        print("\nPhase 2-S: CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
