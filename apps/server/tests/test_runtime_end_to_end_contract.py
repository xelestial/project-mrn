from __future__ import annotations

import asyncio

import pytest

from apps.server.src.domain.view_state import project_view_state
from apps.server.src.services.stream_service import StreamService


def test_next_round_draft_does_not_pollute_previous_turn_stage() -> None:
    view_state = project_view_state(
        [
            {
                "type": "event",
                "seq": 10,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "turn_start",
                    "round_index": 1,
                    "turn_index": 4,
                    "acting_player_id": 2,
                    "character": "객주",
                    "runtime_module": {
                        "runner_kind": "module",
                        "frame_id": "turn:1:p2",
                        "frame_type": "turn",
                        "module_id": "mod:turn:1:p2:start",
                        "module_type": "TurnStartModule",
                        "module_path": ["round:1", "turn:1:p2", "mod:turn:1:p2:start"],
                    },
                },
            },
            {
                "type": "event",
                "seq": 11,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "turn_end_snapshot",
                    "round_index": 1,
                    "turn_index": 4,
                    "acting_player_id": 2,
                    "runtime_module": {
                        "runner_kind": "module",
                        "frame_id": "turn:1:p2",
                        "frame_type": "turn",
                        "module_id": "mod:turn:1:p2:end",
                        "module_type": "TurnEndSnapshotModule",
                        "module_path": ["round:1", "turn:1:p2", "mod:turn:1:p2:end"],
                    },
                },
            },
            {
                "type": "prompt",
                "seq": 12,
                "session_id": "s1",
                "server_time_ms": 3,
                "payload": {
                    "request_id": "r2:draft:p0",
                    "request_type": "draft_card",
                    "player_id": 0,
                    "runner_kind": "module",
                    "resume_token": "tok",
                    "frame_id": "round:2",
                    "frame_type": "round",
                    "module_id": "mod:round:2:draft",
                    "module_type": "DraftModule",
                    "module_path": ["round:2", "mod:round:2:draft"],
                    "public_context": {"round_index": 2, "draft_phase": 1},
                },
            },
        ]
    )

    assert view_state["runtime"]["draft_active"] is True
    assert view_state["runtime"]["round_stage"] == "draft"
    assert view_state["turn_stage"]["round_index"] == 1
    assert view_state["turn_stage"]["turn_index"] == 4
    assert view_state["turn_stage"]["current_beat_event_code"] == "turn_end_snapshot"
    assert "prompt_active" not in view_state["turn_stage"]["progress_codes"]


def test_stream_service_rejects_round_end_flip_from_turn_context() -> None:
    service = StreamService()

    async def _run() -> None:
        await service.publish(
            "s1",
            "event",
            {
                "event_type": "turn_start",
                "round_index": 1,
                "turn_index": 4,
                "acting_player_id": 2,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:1:p2",
                    "module_type": "TurnStartModule",
                    "module_id": "mod:turn:1:p2:start",
                },
            },
        )
        with pytest.raises(Exception, match="RoundEndCardFlipModule"):
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "marker_flip",
                    "round_index": 1,
                    "turn_index": 4,
                    "runtime_module": {
                        "frame_type": "round",
                        "frame_id": "round:1",
                        "module_type": "RoundEndCardFlipModule",
                        "module_id": "mod:round:1:flip",
                    },
                },
            )

    asyncio.run(_run())
