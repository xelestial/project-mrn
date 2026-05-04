from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.domain.view_state.prompt_selector import build_prompt_feedback_view_state, build_prompt_view_state
from apps.server.src.services.stream_service import StreamService


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_selector_prompt_fixture(name: str) -> dict:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _selector_prompt_surface_fixture_names() -> list[str]:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples"
    return sorted(item.name for item in path.glob("selector.prompt.*_surface.json"))


class ViewStatePromptSelectorTests(unittest.TestCase):
    def test_build_prompt_view_state_projects_active_prompt(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_turn7_move",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "legal_choices": [
                            {"choice_id": "roll", "title": "Roll dice", "description": "Normal move."},
                            {"choice_id": "no", "title": "Skip", "description": "Do not move.", "priority": "secondary"},
                        ],
                        "public_context": {"round_index": 2, "turn_index": 7},
                    },
                }
            ]
        )

        self.assertEqual(
            view_state,
            {
                "active": {
                    "request_id": "req_turn7_move",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 30000,
                    "choices": [
                        {
                            "choice_id": "roll",
                            "title": "Roll dice",
                            "description": "Normal move.",
                            "value": None,
                            "secondary": False,
                        },
                        {
                            "choice_id": "no",
                            "title": "Skip",
                            "description": "Do not move.",
                            "value": None,
                            "secondary": True,
                        },
                    ],
                    "public_context": {"round_index": 2, "turn_index": 7},
                    "behavior": {
                        "normalized_request_type": "movement",
                        "single_surface": False,
                        "auto_continue": False,
                    },
                    "surface": {
                        "kind": "movement",
                        "blocks_public_events": True,
                        "movement": {
                            "roll_choice_id": "roll",
                            "card_pool": [],
                            "can_use_two_cards": False,
                            "card_choices": [],
                        },
                    },
                }
            },
        )

    def test_character_pick_surface_exposes_draft_phase_and_choice_count(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_draft_phase_2",
                        "request_type": "draft_card",
                        "player_id": 3,
                        "timeout_ms": 300000,
                        "legal_choices": [
                            {
                                "choice_id": "card_8",
                                "title": "만신",
                                "description": "pick",
                                "value": {"inactive_character_name": "박수"},
                            }
                        ],
                        "public_context": {
                            "draft_phase": 2,
                            "draft_phase_label": "draft_phase_2",
                            "offered_count": 1,
                        },
                    },
                }
            ]
        )

        self.assertEqual(
            view_state["active"]["surface"]["character_pick"],
            {
                "phase": "draft",
                "draft_phase": 2,
                "draft_phase_label": "draft_phase_2",
                "choice_count": 1,
                "options": [{"choice_id": "card_8", "name": "만신", "description": "pick", "inactive_name": "박수"}],
            },
        )

    def test_build_prompt_view_state_preserves_module_continuation_contract(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_move_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "runner_kind": "module",
                        "resume_token": "tok_move_1",
                        "frame_id": "turn:1:p1",
                        "module_id": "mod:move",
                        "module_type": "MapMoveModule",
                        "module_cursor": "movement:await_choice",
                        "batch_id": "batch_move_1",
                        "legal_choices": [{"choice_id": "roll", "title": "Roll"}],
                        "public_context": {"round_index": 1},
                    },
                }
            ]
        )

        active = view_state["active"]
        self.assertEqual(active["resume_token"], "tok_move_1")
        self.assertEqual(active["frame_id"], "turn:1:p1")
        self.assertEqual(active["module_id"], "mod:move")
        self.assertEqual(active["module_type"], "MapMoveModule")
        self.assertEqual(active["module_cursor"], "movement:await_choice")
        self.assertEqual(active["batch_id"], "batch_move_1")

    def test_build_prompt_view_state_projects_effect_context(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_mark_1",
                        "request_type": "mark_target",
                        "player_id": 2,
                        "timeout_ms": 30000,
                        "legal_choices": [{"choice_id": "none", "title": "None"}],
                        "public_context": {
                            "actor_name": "자객",
                            "effect_context": {
                                "label": "자객",
                                "detail": "자객의 지목 효과로 다음 대상을 고릅니다.",
                                "attribution": "인물 지목",
                                "tone": "effect",
                                "source": "character",
                                "intent": "mark",
                                "enhanced": True,
                                "source_player_id": 2,
                                "source_family": "character",
                                "source_name": "자객",
                                "resource_delta": {"cash": -3},
                            },
                        },
                    },
                }
            ]
        )

        self.assertEqual(
            view_state["active"]["effect_context"],
            {
                "label": "자객",
                "detail": "자객의 지목 효과로 다음 대상을 고릅니다.",
                "attribution": "인물 지목",
                "tone": "effect",
                "source": "character",
                "intent": "mark",
                "enhanced": True,
                "source_player_id": 2,
                "source_family": "character",
                "source_name": "자객",
                "resource_delta": {"cash": -3},
            },
        )

    def test_build_prompt_view_state_keeps_accepted_feedback_after_prompt_closes(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_turn7_move",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "legal_choices": [{"choice_id": "roll", "title": "Roll dice"}],
                    },
                },
                {
                    "type": "decision_ack",
                    "seq": 2,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {"request_id": "req_turn7_move", "status": "accepted", "player_id": 1},
                },
            ]
        )

        self.assertEqual(
            view_state,
            {
                "last_feedback": {
                    "request_id": "req_turn7_move",
                    "status": "accepted",
                    "reason": "",
                }
            },
        )

    def test_build_prompt_view_state_closes_trick_prompt_after_trick_used(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 50,
                    "session_id": "s1",
                    "server_time_ms": 50,
                    "payload": {
                        "request_id": "req_trick_1",
                        "request_type": "trick_to_use",
                        "player_id": 1,
                        "timeout_ms": 300000,
                        "legal_choices": [{"choice_id": "42", "title": "긴장감 조성", "description": "rent double"}],
                    },
                },
                {
                    "type": "event",
                    "seq": 51,
                    "session_id": "s1",
                    "server_time_ms": 51,
                    "payload": {
                        "event_type": "trick_used",
                        "acting_player_id": 1,
                        "card_name": "긴장감 조성",
                    },
                },
            ]
        )

        self.assertIsNone(view_state)

    def test_stream_service_projects_prompt_view_state_for_target_viewer(self) -> None:
        stream = StreamService()

        async def _publish() -> tuple[dict, dict | None]:
            prompt = await stream.publish(
                "sess_1",
                "prompt",
                {
                    "request_id": "req_turn7_move",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 30000,
                    "legal_choices": [{"choice_id": "roll", "title": "Roll dice", "description": "Normal move."}],
                    "public_context": {"round_index": 2, "turn_index": 7},
                },
            )
            snapshot = await stream.snapshot("sess_1")
            projected = await stream.project_message_for_viewer(
                prompt.to_dict(),
                ViewerContext(role="seat", session_id="sess_1", player_id=1),
            )
            return [message.to_dict() for message in snapshot][-1], projected

        stored_message, projected_message = asyncio.run(_publish())
        latest_payload = stored_message["payload"]

        self.assertIn("view_state", latest_payload)
        self.assertNotIn("prompt", latest_payload["view_state"])
        self.assertIsNotNone(projected_message)
        self.assertEqual(
            projected_message["payload"]["view_state"]["prompt"]["active"]["request_id"],
            "req_turn7_move",
        )

    def test_build_prompt_feedback_view_state_projects_latest_terminal_feedback(self) -> None:
        feedback = build_prompt_feedback_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_turn7_move",
                        "request_type": "movement",
                        "player_id": 1,
                    },
                },
                {
                    "type": "decision_ack",
                    "seq": 2,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {
                        "request_id": "req_turn7_move",
                        "status": "rejected",
                        "reason": "invalid_choice",
                    },
                },
            ]
        )

        self.assertEqual(
            feedback,
            {
                "request_id": "req_turn7_move",
                "status": "rejected",
                "reason": "invalid_choice",
            },
        )

    def test_build_prompt_view_state_marks_burden_exchange_as_single_surface_chain(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_burden_1",
                        "request_type": "burden_exchange",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "legal_choices": [
                            {"choice_id": "yes", "title": "Pay 2 to remove"},
                            {"choice_id": "no", "title": "Keep burden"},
                        ],
                        "public_context": {
                            "card_deck_index": 91,
                            "burden_card_count": 3,
                            "current_f_value": 3,
                        },
                    },
                }
            ]
        )

        self.assertEqual(
            view_state["active"]["behavior"],
            {
                "normalized_request_type": "burden_exchange_batch",
                "single_surface": True,
                "auto_continue": True,
                "chain_key": "burden_exchange:1:3",
                "chain_item_count": 3,
                "current_item_deck_index": 91,
            },
        )

    def test_build_prompt_view_state_keeps_last_feedback_even_after_prompt_closes(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_turn7_move",
                        "request_type": "movement",
                        "player_id": 1,
                    },
                },
                {
                    "type": "decision_ack",
                    "seq": 2,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {
                        "request_id": "req_turn7_move",
                        "status": "stale",
                        "reason": "request_superseded",
                    },
                },
            ]
        )

        self.assertEqual(
            view_state,
            {
                "last_feedback": {
                    "request_id": "req_turn7_move",
                    "status": "stale",
                    "reason": "request_superseded",
                }
            },
        )

    def test_build_prompt_view_state_matches_every_shared_surface_fixture(self) -> None:
        for name in _selector_prompt_surface_fixture_names():
            with self.subTest(name=name):
                fixture = _load_selector_prompt_fixture(name)
                view_state = build_prompt_view_state(fixture["messages"])
                self.assertEqual(
                    view_state["active"]["surface"],
                    fixture["expected"]["prompt"]["active"]["surface"],
                )
                expected_effect_context = fixture["expected"]["prompt"]["active"].get("effect_context")
                if expected_effect_context is not None:
                    self.assertEqual(view_state["active"]["effect_context"], expected_effect_context)

    def test_build_prompt_view_state_matches_shared_lap_reward_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.lap_reward_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])
        self.assertEqual(view_state["active"]["surface"], fixture["expected"]["prompt"]["active"]["surface"])

    def test_build_prompt_view_state_matches_shared_burden_exchange_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.burden_exchange_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])
        self.assertEqual(view_state["active"]["surface"], fixture["expected"]["prompt"]["active"]["surface"])

    def test_build_prompt_view_state_matches_shared_mark_target_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.mark_target_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])
        self.assertEqual(view_state["active"]["surface"], fixture["expected"]["prompt"]["active"]["surface"])

    def test_build_prompt_view_state_matches_shared_active_flip_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.active_flip_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])
        self.assertEqual(view_state["active"]["surface"], fixture["expected"]["prompt"]["active"]["surface"])

    def test_build_prompt_view_state_matches_shared_coin_placement_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.coin_placement_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])
        self.assertEqual(view_state["active"]["surface"], fixture["expected"]["prompt"]["active"]["surface"])

    def test_build_prompt_view_state_matches_shared_geo_bonus_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.geo_bonus_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])
        self.assertEqual(view_state["active"]["surface"], fixture["expected"]["prompt"]["active"]["surface"])

    def test_build_prompt_view_state_projects_doctrine_relief_surface(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_doctrine_1",
                        "request_type": "doctrine_relief",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "legal_choices": [
                            {
                                "choice_id": "2",
                                "title": "P2",
                                "description": "Remove 1 burden from P2.",
                                "value": {"target_player_id": 2, "burden_count": 1},
                            }
                        ],
                        "public_context": {"candidate_count": 1},
                    },
                }
            ]
        )

        self.assertEqual(
            view_state["active"]["surface"]["doctrine_relief"],
            {
                "candidate_count": 1,
                "options": [
                    {
                        "choice_id": "2",
                        "target_player_id": 2,
                        "burden_count": 1,
                        "title": "P2",
                        "description": "Remove 1 burden from P2.",
                    }
                ],
            },
        )

    def test_build_prompt_view_state_projects_specific_trick_reward_surface(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_reward_1",
                        "request_type": "specific_trick_reward",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "legal_choices": [
                            {
                                "choice_id": "17",
                                "title": "월리권 #17",
                                "description": "Draw one more time.",
                                "value": {"deck_index": 17, "card_description": "Draw one more time."},
                            }
                        ],
                        "public_context": {"reward_count": 1},
                    },
                }
            ]
        )

        self.assertEqual(
            view_state["active"]["surface"]["specific_trick_reward"],
            {
                "reward_count": 1,
                "options": [
                    {
                        "choice_id": "17",
                        "deck_index": 17,
                        "name": "월리권 #17",
                        "description": "Draw one more time.",
                    }
                ],
            },
        )

    def test_build_prompt_view_state_projects_pabal_dice_mode_surface(self) -> None:
        view_state = build_prompt_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_pabal_1",
                        "request_type": "pabal_dice_mode",
                        "player_id": 1,
                        "timeout_ms": 30000,
                        "legal_choices": [
                            {
                                "choice_id": "plus_one",
                                "title": "Roll three dice",
                                "description": "Use the default three-die roll this turn.",
                                "value": {"dice_mode": "plus_one"},
                            },
                            {
                                "choice_id": "minus_one",
                                "title": "Roll one die",
                                "description": "Reduce the roll to one die this turn.",
                                "value": {"dice_mode": "minus_one"},
                            },
                        ],
                    },
                }
            ]
        )

        self.assertEqual(
            view_state["active"]["surface"]["pabal_dice_mode"],
            {
                "options": [
                    {
                        "choice_id": "plus_one",
                        "dice_mode": "plus_one",
                        "title": "Roll three dice",
                        "description": "Use the default three-die roll this turn.",
                    },
                    {
                        "choice_id": "minus_one",
                        "dice_mode": "minus_one",
                        "title": "Roll one die",
                        "description": "Reduce the roll to one die this turn.",
                    },
                ]
            },
        )

    def test_build_prompt_view_state_matches_shared_movement_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.movement_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_hand_choice_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.hand_choice_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_draft_character_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.draft_character_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_final_character_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.final_character_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_purchase_tile_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.purchase_tile_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_trick_tile_target_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.trick_tile_target_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_doctrine_relief_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.doctrine_relief_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_specific_trick_reward_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.specific_trick_reward_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_pabal_dice_mode_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.pabal_dice_mode_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )

    def test_build_prompt_view_state_matches_shared_runaway_step_surface_fixture(self) -> None:
        fixture = _load_selector_prompt_fixture("selector.prompt.runaway_step_surface.json")
        view_state = build_prompt_view_state(fixture["messages"])

        self.assertEqual(
            view_state["active"]["surface"],
            fixture["expected"]["prompt"]["active"]["surface"],
        )
