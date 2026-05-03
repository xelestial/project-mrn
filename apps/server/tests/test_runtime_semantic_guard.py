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


def test_rejects_trick_used_from_turn_window_context() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="trick_used"):
        validate_stream_payload(
            history=[],
            msg_type="event",
            payload={
                "event_type": "trick_used",
                "round_index": 1,
                "turn_index": 0,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:1:p0",
                    "module_type": "TrickWindowModule",
                    "module_id": "mod:turn:1:p0:trickwindow",
                },
            },
        )


def test_allows_trick_used_from_trick_resolve_sequence_context() -> None:
    validate_stream_payload(
        history=[],
        msg_type="event",
        payload={
            "event_type": "trick_used",
            "round_index": 1,
            "turn_index": 0,
            "runtime_module": {
                "frame_type": "sequence",
                "frame_id": "seq:trick:1:p0:0",
                "module_type": "TrickResolveModule",
                "module_id": "mod:seq:trick:1:p0:0:TrickResolve",
            },
        },
    )


def test_allows_round_end_marker_flip_when_checkpoint_proves_round_module_after_stale_turn_start() -> None:
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
        }
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
            "engine_checkpoint": {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "round:1",
                        "frame_type": "round",
                        "status": "running",
                        "active_module_id": "mod:flip",
                        "module_queue": [
                            {"module_id": "mod:p0", "module_type": "PlayerTurnModule", "status": "completed"},
                            {"module_id": "mod:p1", "module_type": "PlayerTurnModule", "status": "completed"},
                            {"module_id": "mod:flip", "module_type": "RoundEndCardFlipModule", "status": "running"},
                        ],
                    }
                ],
            },
        },
    )


def test_rejects_module_prompt_without_module_cursor() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="module_cursor"):
        validate_stream_payload(
            history=[],
            msg_type="prompt",
            payload={
                "runner_kind": "module",
                "request_id": "req_1",
                "player_id": 1,
                "request_type": "movement",
                "resume_token": "token_1",
                "frame_id": "turn:1:p0",
                "module_id": "mod:turn:1:p0:movement",
                "module_type": "MapMoveModule",
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
