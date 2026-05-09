from __future__ import annotations

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.domain.view_state.projector import project_replay_view_state


def event(seq: int, event_type: str, **payload: object) -> dict:
    return {
        "type": "event",
        "seq": seq,
        "session_id": "s1",
        "server_time_ms": seq,
        "payload": {"event_type": event_type, **payload},
    }


def test_turn_history_groups_public_events_by_turn_and_marks_local_relevance() -> None:
    payload = project_replay_view_state(
        [
            event(1, "turn_start", round_index=1, turn_index=3, acting_player_id=2),
            event(2, "dice_roll", round_index=1, turn_index=3, acting_player_id=2, die=4),
            event(
                3,
                "fortune_move",
                round_index=1,
                turn_index=3,
                acting_player_id=2,
                from_tile_index=4,
                to_tile_index=7,
            ),
            event(
                4,
                "rent_paid",
                round_index=1,
                turn_index=3,
                payer_player_id=2,
                owner_player_id=1,
                final_amount=3,
                tile_index=7,
                modifiers={"rent_context": {"owner_player_id": 0, "base_rent": 3}},
            ),
            event(
                5,
                "lap_reward_chosen",
                round_index=1,
                turn_index=3,
                acting_player_id=2,
                amount={"cash": 2, "shards": 1, "coins": 0},
            ),
            event(6, "turn_start", round_index=1, turn_index=4, acting_player_id=1),
            event(
                7,
                "mark_resolved",
                round_index=1,
                turn_index=4,
                source_player_id=1,
                target_player_id=2,
            ),
            event(8, "f_value_change", round_index=1, turn_index=4, before=9, delta=1, after=10),
        ],
        ViewerContext(role="seat", session_id="s1", player_id=1),
    )

    history = payload["turn_history"]

    assert history["current_key"] == "r1:t4"
    assert [turn["key"] for turn in history["turns"]] == ["r1:t3", "r1:t4"]
    assert history["turns"][0]["actor_player_id"] == 2
    assert history["turns"][0]["event_count"] == 5
    assert history["turns"][0]["important_count"] >= 3

    rent_event = next(item for item in history["turns"][0]["events"] if item["event_code"] == "rent_paid")
    assert rent_event["scope"] == "player"
    assert rent_event["relevance"] == "mine-critical"
    assert rent_event["participants"] == {"payer_player_id": 2, "owner_player_id": 1}
    assert rent_event["focus_tile_indices"] == [7]
    assert rent_event["payload"]["modifiers"]["rent_context"]["owner_player_id"] == 1

    reward_event = next(item for item in history["turns"][0]["events"] if item["event_code"] == "lap_reward_chosen")
    assert reward_event["relevance"] == "important"
    assert reward_event["resource_delta"] == {"cash": 2, "shards": 1}

    mark_event = next(item for item in history["turns"][1]["events"] if item["event_code"] == "mark_resolved")
    assert mark_event["relevance"] == "mine-critical"
    assert mark_event["participants"] == {"source_player_id": 1, "target_player_id": 2}

    f_value_event = next(item for item in history["turns"][1]["events"] if item["event_code"] == "f_value_change")
    assert f_value_event["scope"] == "common"
    assert f_value_event["end_time_delta"] == {"before": 9, "delta": 1, "after": 10}


def test_turn_history_uses_viewer_projected_payload() -> None:
    payload = project_replay_view_state(
        [
            event(1, "turn_start", round_index=1, turn_index=1, acting_player_id=1),
            event(
                2,
                "draft_pick",
                round_index=1,
                turn_index=1,
                player_id=2,
                picked_card="secret",
                choice_id="private-choice",
                public_note="visible",
            ),
        ],
        ViewerContext(role="spectator", session_id="s1"),
    )

    draft_event = payload["turn_history"]["turns"][0]["events"][1]
    assert draft_event["payload"]["public_note"] == "visible"
    assert "picked_card" not in draft_event["payload"]
    assert "choice_id" not in draft_event["payload"]
