from __future__ import annotations

from types import SimpleNamespace

from runtime_modules.legacy_metadata import legacy_runtime_module_for_event


def test_legacy_draft_event_maps_to_round_draft_module() -> None:
    state = SimpleNamespace(rounds_completed=0, turn_index=0)

    metadata = legacy_runtime_module_for_event(
        state,
        "draft_pick",
        "draft",
        2,
        {"acting_player_id": 2, "picked_card": "만신"},
        session_id="s1",
    )

    assert metadata["runner_kind"] == "legacy"
    assert metadata["frame_type"] == "round"
    assert metadata["module_type"] == "DraftModule"
    assert metadata["module_path"] == ["round:1", "legacy:round:1:draft"]


def test_legacy_trick_event_maps_to_sequence_module() -> None:
    state = SimpleNamespace(rounds_completed=1, turn_index=3)

    metadata = legacy_runtime_module_for_event(
        state,
        "trick_used",
        "turn",
        None,
        {"acting_player_id": 1, "card_name": "재뿌리기"},
        session_id="s1",
    )

    assert metadata["frame_type"] == "sequence"
    assert metadata["module_type"] == "TrickResolveModule"
    assert "seq:trick:2:p1:legacy" in metadata["module_path"]


def test_legacy_active_flip_event_maps_to_round_end_card_flip_module() -> None:
    state = SimpleNamespace(rounds_completed=2, turn_index=0)

    metadata = legacy_runtime_module_for_event(
        state,
        "active_flip",
        "round_end",
        None,
        {"card_index": 4},
        session_id="s1",
    )

    assert metadata["frame_type"] == "round"
    assert metadata["module_type"] == "RoundEndCardFlipModule"
    assert metadata["module_path"] == ["round:3", "legacy:round:3:card_flip"]


def test_legacy_idempotency_key_is_stable_for_same_payload() -> None:
    state = SimpleNamespace(rounds_completed=0, turn_index=1)
    payload = {"event_type": "dice_roll", "player_id": 0, "dice": [2, 3]}

    first = legacy_runtime_module_for_event(state, "dice_roll", "turn", 0, payload, session_id="s1")
    second = legacy_runtime_module_for_event(state, "dice_roll", "turn", 0, payload, session_id="s1")

    assert first["idempotency_key"] == second["idempotency_key"]
