from __future__ import annotations

import pytest

from apps.server.src.domain.runtime_semantic_guard import (
    RuntimeSemanticViolation,
    validate_checkpoint_payload,
    validate_stream_payload,
)


def test_rejects_draft_module_in_turn_frame_stream_payload() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="DraftModule"):
        validate_stream_payload(
            history=[],
            msg_type="event",
            payload={
                "event_type": "draft_pick",
                "round_index": 2,
                "turn_index": 4,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:2:p0",
                    "module_type": "DraftModule",
                    "module_id": "mod:draft",
                },
            },
        )


def test_rejects_marker_flip_in_active_turn_context() -> None:
    history = [
        {
            "type": "event",
            "seq": 10,
            "payload": {
                "event_type": "turn_start",
                "round_index": 1,
                "turn_index": 3,
                "acting_player_id": 0,
            },
        }
    ]

    with pytest.raises(RuntimeSemanticViolation, match="RoundEndCardFlipModule"):
        validate_stream_payload(
            history=history,
            msg_type="event",
            payload={
                "event_type": "marker_flip",
                "round_index": 1,
                "turn_index": 3,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:1:p0",
                    "module_type": "RoundEndCardFlipModule",
                    "module_id": "mod:flip",
                },
            },
        )


def test_allows_round_end_marker_flip_after_turn_end_snapshot() -> None:
    history = [
        {
            "type": "event",
            "seq": 10,
            "payload": {
                "event_type": "turn_start",
                "round_index": 1,
                "turn_index": 4,
                "acting_player_id": 4,
            },
        },
        {
            "type": "event",
            "seq": 20,
            "payload": {
                "event_type": "turn_end_snapshot",
                "round_index": 1,
                "turn_index": 4,
                "acting_player_id": 4,
            },
        },
    ]

    validate_stream_payload(
        history=history,
        msg_type="event",
        payload={
            "event_type": "marker_flip",
            "round_index": 1,
            "turn_index": 4,
            "runtime_module": {
                "frame_type": "round",
                "frame_id": "round:1",
                "module_type": "RoundEndCardFlipModule",
                "module_id": "mod:flip",
            },
        },
    )


def test_checkpoint_rejects_round_card_flip_with_suspended_player_turn() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="card flip"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "round:1",
                        "frame_type": "round",
                        "status": "running",
                        "active_module_id": "mod:flip",
                        "module_queue": [
                            {"module_id": "mod:p0", "module_type": "PlayerTurnModule", "status": "suspended"},
                            {"module_id": "mod:flip", "module_type": "RoundEndCardFlipModule", "status": "running"},
                        ],
                    }
                ],
            }
        )
