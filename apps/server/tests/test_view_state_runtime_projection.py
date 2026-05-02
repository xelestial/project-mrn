from __future__ import annotations

import unittest

from apps.server.src.domain.view_state.runtime_selector import build_runtime_view_state


class RuntimeProjectionViewStateTests(unittest.TestCase):
    def test_draft_active_only_for_draft_module_or_prompt(self) -> None:
        draft = build_runtime_view_state([
            {
                "type": "event",
                "payload": {
                    "event_type": "draft_pick",
                    "runtime_module": {
                        "runner_kind": "legacy",
                        "frame_id": "round:1",
                        "frame_type": "round",
                        "module_id": "legacy:round:1:draft",
                        "module_type": "DraftModule",
                        "module_path": ["round:1", "legacy:round:1:draft"],
                    },
                },
            }
        ])
        turn = build_runtime_view_state([
            {
                "type": "event",
                "payload": {
                    "event_type": "turn_start",
                    "runtime_module": {
                        "runner_kind": "legacy",
                        "frame_id": "turn:1:p0",
                        "frame_type": "turn",
                        "module_id": "legacy:turn:1:p0:turn_start",
                        "module_type": "TurnStartModule",
                        "module_path": ["round:1", "turn:1:p0", "legacy:turn:1:p0:turn_start"],
                    },
                },
            }
        ])

        self.assertTrue(draft["draft_active"])
        self.assertFalse(turn["draft_active"])

    def test_later_turn_module_closes_old_draft_prompt(self) -> None:
        view_state = build_runtime_view_state([
            {
                "type": "prompt",
                "payload": {
                    "request_id": "req_draft_1",
                    "request_type": "draft_card",
                    "player_id": 1,
                },
            },
            {
                "type": "event",
                "payload": {
                    "event_type": "turn_start",
                    "runtime_module": {
                        "runner_kind": "legacy",
                        "frame_id": "turn:1:p0",
                        "frame_type": "turn",
                        "module_id": "legacy:turn:1:p0:turn_start",
                        "module_type": "TurnStartModule",
                        "module_path": ["round:1", "turn:1:p0", "legacy:turn:1:p0:turn_start"],
                    },
                },
            },
        ])

        self.assertFalse(view_state["draft_active"])
        self.assertEqual(view_state["active_prompt_request_id"], "")

    def test_trick_sequence_projects_from_sequence_metadata(self) -> None:
        view_state = build_runtime_view_state([
            {
                "type": "event",
                "payload": {
                    "event_type": "trick_used",
                    "runtime_module": {
                        "runner_kind": "legacy",
                        "frame_id": "seq:trick:1:p0:legacy",
                        "frame_type": "sequence",
                        "module_id": "legacy:seq:trick:1:p0:trick_resolve",
                        "module_type": "TrickResolveModule",
                        "module_path": [
                            "round:1",
                            "turn:1:p0",
                            "seq:trick:1:p0:legacy",
                            "legacy:seq:trick:1:p0:trick_resolve",
                        ],
                    },
                },
            }
        ])

        self.assertEqual(view_state["active_sequence"], "trick")
        self.assertTrue(view_state["trick_sequence_active"])

    def test_card_flip_legal_requires_round_end_card_flip_module(self) -> None:
        marker_transfer = build_runtime_view_state([
            {
                "type": "event",
                "payload": {
                    "runtime_module": {
                        "frame_type": "turn",
                        "module_type": "ImmediateMarkerTransferModule",
                        "module_path": ["round:1", "turn:1:p0", "legacy:turn:1:p0:marker_transfer"],
                    },
                },
            }
        ])
        round_end = build_runtime_view_state([
            {
                "type": "event",
                "payload": {
                    "runtime_module": {
                        "frame_type": "round",
                        "module_type": "RoundEndCardFlipModule",
                        "module_path": ["round:1", "legacy:round:1:card_flip"],
                    },
                },
            }
        ])

        self.assertFalse(marker_transfer["card_flip_legal"])
        self.assertTrue(round_end["card_flip_legal"])

    def test_projection_prefers_checkpoint_active_module_over_old_event(self) -> None:
        view_state = build_runtime_view_state([
            {
                "type": "event",
                "payload": {
                    "event_type": "draft_pick",
                    "runtime_module": {
                        "runner_kind": "legacy",
                        "frame_id": "round:1",
                        "frame_type": "round",
                        "module_type": "DraftModule",
                        "module_path": ["round:1", "legacy:round:1:draft"],
                    },
                },
            },
            {
                "type": "event",
                "payload": {
                    "event_type": "turn_end_snapshot",
                    "engine_checkpoint": {
                        "runtime_runner_kind": "module",
                        "runtime_frame_stack": [
                            {
                                "frame_id": "turn:1:p2",
                                "frame_type": "turn",
                                "owner_player_id": 2,
                                "parent_frame_id": "round:1",
                                "active_module_id": "mod:turn:1:p2:dice",
                                "module_queue": [
                                    {
                                        "module_id": "mod:turn:1:p2:dice",
                                        "module_type": "DiceRollModule",
                                        "phase": "turn",
                                        "owner_player_id": 2,
                                        "status": "running",
                                    }
                                ],
                                "status": "running",
                            }
                        ],
                    },
                },
            },
        ])

        self.assertEqual(view_state["runner_kind"], "module")
        self.assertEqual(view_state["turn_stage"], "dice")
        self.assertFalse(view_state["draft_active"])
