from __future__ import annotations

import asyncio
import copy
import socket
import threading
import time
import unittest
import warnings
from unittest.mock import patch

import pytest

from apps.server.src.services.decision_gateway import (
    build_decision_invocation,
    build_decision_invocation_from_request,
    build_canonical_decision_request,
    build_routed_decision_call,
    build_public_context,
    decision_request_type_for_method,
    serialize_ai_choice_id,
)
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.runtime_service import _LocalHumanDecisionClient
from apps.server.src.services.runtime_service import resolve_runtime_runner_kind, runtime_checkpoint_schema_version_for_runner
from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.prompt_service import PromptService


pytestmark = [
    pytest.mark.filterwarnings("ignore:websockets\\.legacy is deprecated.*:DeprecationWarning"),
    pytest.mark.filterwarnings(
        "ignore:websockets\\.server\\.WebSocketServerProtocol is deprecated:DeprecationWarning"
    ),
]

warnings.filterwarnings(
    "ignore",
    message="websockets\\.legacy is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="websockets\\.server\\.WebSocketServerProtocol is deprecated",
    category=DeprecationWarning,
)


class RuntimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_service = SessionService()
        self.stream_service = StreamService()
        self.prompt_service = PromptService()
        self.runtime_service = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
        )

    def test_runtime_runner_defaults_to_legacy_until_all_module_flags_enabled(self) -> None:
        self.assertEqual(resolve_runtime_runner_kind({}, RuntimeSettings()), "legacy")
        self.assertEqual(
            resolve_runtime_runner_kind(
                {"flags": {"module_metadata_v1": True}},
                RuntimeSettings(),
            ),
            "legacy",
        )

    def test_runtime_runner_uses_module_when_all_settings_flags_enabled(self) -> None:
        settings = RuntimeSettings(
            runtime_module_metadata_v1=True,
            runtime_checkpoint_v3=True,
            runtime_prompt_continuation_v1=True,
            runtime_simultaneous_resolution_v1=True,
            runtime_module_runner_round_v1=True,
            runtime_module_runner_turn_v1=True,
            runtime_module_runner_sequence_v1=True,
            runtime_stream_idempotency_v1=True,
            runtime_frontend_projection_v1=True,
        )

        self.assertEqual(resolve_runtime_runner_kind({}, settings), "module")
        self.assertEqual(runtime_checkpoint_schema_version_for_runner("module"), 3)

    def test_runtime_runner_explicit_session_kind_wins(self) -> None:
        self.assertEqual(resolve_runtime_runner_kind({"runner_kind": "module"}, RuntimeSettings()), "module")
        self.assertEqual(resolve_runtime_runner_kind({"runner_kind": "legacy"}, RuntimeSettings()), "legacy")

    def test_public_runtime_status_does_not_expose_canonical_current_state(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=_RecoveryGameStateStoreStub(),
        )

        internal = runtime.recovery_checkpoint(session.session_id)
        public = runtime.public_runtime_status(session.session_id)

        self.assertTrue(internal["available"])
        self.assertIn("current_state", internal)
        self.assertTrue(public["recovery_checkpoint"]["available"])
        self.assertNotIn("current_state", public["recovery_checkpoint"])
        self.assertTrue(public["recovery_checkpoint"]["current_state_available"])
        self.assertEqual(public["recovery_checkpoint"]["view_state"], {"players": {"items": []}})

    def test_redis_backed_runtime_status_does_not_fall_back_to_stale_process_cache(self) -> None:
        store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=store,
        )
        runtime._status["sess_deleted"] = {  # type: ignore[attr-defined]
            "status": "waiting_input",
            "request_id": "stale_request",
            "player_id": 1,
        }

        status = runtime.runtime_status("sess_deleted")

        self.assertEqual(status["status"], "idle")
        self.assertNotIn("request_id", status)

    def test_execute_prompt_fallback_records_recent_history(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        result = asyncio.run(
            self.runtime_service.execute_prompt_fallback(
                session_id=session.session_id,
                request_id="req_timeout_1",
                player_id=2,
                fallback_policy="timeout_fallback",
                prompt_payload={"fallback_choice_id": "choice_default"},
            )
        )

        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["choice_id"], "choice_default")
        status = self.runtime_service.runtime_status(session.session_id)
        recent = status.get("recent_fallbacks", [])
        self.assertGreaterEqual(len(recent), 1)
        self.assertEqual(recent[-1]["request_id"], "req_timeout_1")
        self.assertEqual(recent[-1]["choice_id"], "choice_default")

    def test_execute_prompt_fallback_uses_first_legal_choice_when_no_explicit_default(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        result = asyncio.run(
            self.runtime_service.execute_prompt_fallback(
                session_id=session.session_id,
                request_id="req_timeout_movement",
                player_id=2,
                fallback_policy="timeout_fallback",
                prompt_payload={
                    "request_type": "movement",
                    "legal_choices": [
                        {"choice_id": "dice", "title": "Roll dice"},
                        {"choice_id": "card_1", "title": "Use card 1"},
                    ],
                },
            )
        )

        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["choice_id"], "dice")
        recent = self.runtime_service.runtime_status(session.session_id).get("recent_fallbacks", [])
        self.assertEqual(recent[-1]["choice_id"], "dice")

    def test_process_command_once_continues_after_command_transition_until_prompt(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        calls: list[tuple[str | None, int | None]] = []

        def _transition_once(
            _loop,
            _session_id: str,
            _seed: int,
            _policy_mode: str | None,
            _require_checkpoint: bool,
            command_consumer_name: str | None,
            command_seq: int | None,
        ) -> dict:
            calls.append((command_consumer_name, command_seq))
            if len(calls) == 1:
                return {"status": "committed", "pending_actions": 1}
            return {"status": "waiting_input", "request_type": "purchase_tile", "player_id": 1}

        with patch.object(self.runtime_service, "_run_engine_transition_once_sync", side_effect=_transition_once):
            result = asyncio.run(
                self.runtime_service.process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "waiting_input")
        self.assertEqual(result["transitions"], 2)
        self.assertEqual(calls, [("runtime_wakeup", 7), (None, None)])
        self.assertEqual(self.runtime_service.runtime_status(session.session_id)["status"], "waiting_input")

    def test_decision_request_type_for_method_uses_canonical_mapping(self) -> None:
        self.assertEqual(decision_request_type_for_method("choose_purchase_tile"), "purchase_tile")
        self.assertEqual(decision_request_type_for_method("choose_mark_target"), "mark_target")
        self.assertEqual(decision_request_type_for_method("choose_pabal_dice_mode"), "pabal_dice_mode")
        self.assertEqual(decision_request_type_for_method("choose_custom_branch"), "custom_branch")

    def test_purchase_tile_method_spec_keeps_request_context_and_choice_in_sync(self) -> None:
        state = type("State", (), {"rounds_completed": 1, "turn_index": 3})()
        player = type("Player", (), {"cash": 15, "position": 8, "shards": 2})()

        self.assertEqual(decision_request_type_for_method("choose_purchase_tile"), "purchase_tile")
        self.assertEqual(serialize_ai_choice_id("choose_purchase_tile", False), "no")
        self.assertEqual(
            build_public_context(
                "choose_purchase_tile",
                (state, player, 9, "T2", 4),
                {"source": "landing"},
            ),
            {
                "round_index": 2,
                "turn_index": 4,
                "player_cash": 15,
                "player_position": 8,
                "player_shards": 2,
                "player_total_score": 0,
                "tile_index": 9,
                "cost": 4,
                "source": "landing",
                "landing_tile_index": 8,
            },
        )

    def test_specific_reward_and_runaway_specs_keep_specialized_contracts(self) -> None:
        reward = type("Reward", (), {"deck_index": 102, "name": "Lucky Break"})()
        state = type("State", (), {"rounds_completed": 5, "turn_index": 0})()
        player = type("Player", (), {"cash": 9, "position": 22, "shards": 5})()

        self.assertEqual(decision_request_type_for_method("choose_specific_trick_reward"), "specific_trick_reward")
        self.assertEqual(serialize_ai_choice_id("choose_specific_trick_reward", reward), "102")
        self.assertEqual(decision_request_type_for_method("choose_runaway_slave_step"), "runaway_step_choice")
        self.assertEqual(serialize_ai_choice_id("choose_runaway_slave_step", True), "yes")
        self.assertEqual(
            build_public_context(
                "choose_runaway_slave_step",
                (state, player, 25, 26, "S"),
                {},
            ),
            {
                "round_index": 6,
                "turn_index": 1,
                "player_cash": 9,
                "player_position": 22,
                "player_shards": 5,
                "player_total_score": 0,
                "one_short_pos": 25,
                "bonus_target_pos": 26,
                "bonus_target_kind": "S",
            },
        )

    def test_burden_exchange_context_exposes_supply_trigger_details(self) -> None:
        card = type(
            "Card",
            (),
            {
                "name": "무거운 짐",
                "description": "가진 채 보급 단계에 들어가면 비용을 내고 제거할 수 있습니다.",
                "burden_cost": 4,
                "is_burden": True,
            },
        )()
        state = type("State", (), {"rounds_completed": 1, "turn_index": 2, "next_supply_f_threshold": 6, "f_value": 3.5})()
        player = type(
            "Player",
            (),
            {
                "cash": 11,
                "position": 14,
                "shards": 3,
                "hand_coins": 1,
                "trick_hand": [card],
            },
        )()

        self.assertEqual(
            build_public_context(
                "choose_burden_exchange_on_supply",
                (state, player, card),
                {},
            ),
            {
                "round_index": 2,
                "turn_index": 3,
                "player_cash": 11,
                "player_position": 14,
                "player_shards": 3,
                "card_name": "무거운 짐",
                "card_description": "가진 채 보급 단계에 들어가면 비용을 내고 제거할 수 있습니다.",
                "burden_cost": 4,
                "player_hand_coins": 1,
                "player_total_score": 1,
                "burden_card_count": 1,
                "burden_cards": [
                    {
                        "deck_index": None,
                        "name": "무거운 짐",
                        "card_description": "가진 채 보급 단계에 들어가면 비용을 내고 제거할 수 있습니다.",
                        "burden_cost": 4,
                        "is_current_target": True,
                    }
                ],
                "decision_phase": "trick_supply",
                "decision_reason": "supply_threshold",
                "supply_threshold": 3,
                "current_f_value": 3.5,
            },
        )

    def test_trick_hand_context_exposes_stable_deck_indexes_for_use_and_hidden_selection(self) -> None:
        card_a = type("Card", (), {"deck_index": 41, "name": "마당발", "description": "desc-a"})()
        card_b = type("Card", (), {"deck_index": 42, "name": "마당발", "description": "desc-b"})()
        state = type("State", (), {"rounds_completed": 1, "turn_index": 2})()
        player = type(
            "Player",
            (),
            {
                "cash": 11,
                "position": 14,
                "shards": 3,
                "hidden_trick_deck_index": 42,
                "trick_hand": [card_a, card_b],
            },
        )()

        trick_context = build_public_context("choose_trick_to_use", (state, player, [card_a]), {})
        hidden_context = build_public_context("choose_hidden_trick_card", (state, player, [card_a, card_b]), {})

        self.assertEqual(trick_context["usable_hand_count"], 1)
        self.assertEqual(trick_context["total_hand_count"], 2)
        self.assertEqual(trick_context["hidden_trick_deck_index"], 42)
        self.assertEqual(
            trick_context["full_hand"],
            [
                {"deck_index": 41, "name": "마당발", "card_description": "desc-a", "is_hidden": False, "is_usable": True},
                {"deck_index": 42, "name": "마당발", "card_description": "desc-b", "is_hidden": True, "is_usable": False},
            ],
        )
        self.assertEqual(hidden_context["hidden_trick_deck_index"], 42)
        self.assertEqual(len(hidden_context["full_hand"]), 2)
        self.assertTrue(hidden_context["selection_required"])

    def test_specific_trick_reward_context_and_choices_keep_deck_index_identity(self) -> None:
        reward_a = type("Reward", (), {"deck_index": 101, "name": "보상 카드", "description": "desc-a"})()
        reward_b = type("Reward", (), {"deck_index": 102, "name": "보상 카드", "description": "desc-b"})()
        state = type("State", (), {"rounds_completed": 5, "turn_index": 0})()
        player = type("Player", (), {"cash": 9, "position": 22, "shards": 5})()

        context = build_public_context("choose_specific_trick_reward", (state, player, [reward_a, reward_b]), {})
        invocation = build_decision_invocation("choose_specific_trick_reward", (state, player, [reward_a, reward_b]), {})
        routed = build_routed_decision_call(invocation, fallback_policy="required")

        self.assertEqual(context["reward_count"], 2)
        self.assertEqual(
            context["reward_cards"],
            [
                {"deck_index": 101, "name": "보상 카드", "card_description": "desc-a"},
                {"deck_index": 102, "name": "보상 카드", "card_description": "desc-b"},
            ],
        )
        self.assertEqual([choice["choice_id"] for choice in routed.legal_choices], ["101", "102"])
        self.assertEqual([choice["title"] for choice in routed.legal_choices], ["보상 카드 #101", "보상 카드 #102"])
        self.assertEqual(routed.choice_parser("102", invocation.args, invocation.kwargs, invocation.state, invocation.player), reward_b)
    def test_draft_context_exposes_phase_and_offered_candidates(self) -> None:
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0, "active_by_card": {1: "산적", 2: "건설업자"}})()
        card_a = type("Card", (), {"deck_index": 41, "name": "가벼운 짐", "description": "desc-a"})()
        card_b = type("Card", (), {"deck_index": 42, "name": "건강 검진", "description": "desc-b"})()
        player = type(
            "Player",
            (),
            {
                "cash": 10,
                "position": 3,
                "drafted_cards": [7],
                "hidden_trick_deck_index": 42,
                "trick_hand": [card_a, card_b],
            },
        )()

        context = build_public_context("choose_draft_card", (state, player, [1, 2]), {})

        self.assertEqual(context["offered_count"], 2)
        self.assertTrue(isinstance(context["offered_names"], list))
        self.assertLessEqual(len(context["offered_names"]), context["offered_count"] * 2)
        self.assertEqual(context["draft_phase"], 2)
        self.assertEqual(context["draft_phase_label"], "draft_phase_2")
        self.assertEqual(context["active_by_card"], {1: "산적", 2: "건설업자"})
        self.assertEqual(context["total_hand_count"], 2)
        self.assertEqual(context["hidden_trick_count"], 1)
        self.assertEqual([card["name"] for card in context["full_hand"]], ["가벼운 짐", "건강 검진"])

    def test_final_character_context_keeps_trick_hand_for_bottom_tray(self) -> None:
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0, "active_by_card": {1: "산적", 2: "건설업자"}})()
        card_a = type("Card", (), {"deck_index": 51, "name": "긴장감 조성", "description": "desc-a"})()
        card_b = type("Card", (), {"deck_index": 52, "name": "극심한 분리불안", "description": "desc-b"})()
        player = type(
            "Player",
            (),
            {
                "cash": 10,
                "position": 3,
                "hidden_trick_deck_index": 51,
                "trick_hand": [card_a, card_b],
            },
        )()

        context = build_public_context("choose_final_character", (state, player, [1, 2]), {})

        self.assertTrue(context["final_choice"])
        self.assertEqual(context["total_hand_count"], 2)
        self.assertEqual(context["hidden_trick_deck_index"], 51)
        self.assertEqual([card["name"] for card in context["full_hand"]], ["긴장감 조성", "극심한 분리불안"])

    def test_local_human_prompt_merges_gateway_public_context_for_hidden_trick(self) -> None:
        class _Gateway:
            def __init__(self) -> None:
                self.prompt = None

            def resolve_human_prompt(self, prompt, parser, fallback_fn):
                del parser, fallback_fn
                self.prompt = dict(prompt)
                return None

        class _DummyAi:
            def choose_hidden_trick_card(self, state, player, hand):
                del state, player, hand
                return None

        weather = type("Weather", (), {"name": "긴고 긴 겨울", "effect": "종료를 1칸 앞당깁니다."})()
        state = type(
            "State",
            (),
            {
                "rounds_completed": 0,
                "turn_index": 0,
                "active_by_card": {1: "탐관오리", 2: "중매꾼", 3: "산적", 4: "꼬리 감독관"},
                "current_weather": weather,
            },
        )()
        card_a = type("Card", (), {"deck_index": 41, "name": "가벼운 짐", "description": "desc-a"})()
        card_b = type("Card", (), {"deck_index": 42, "name": "건강 검진", "description": "desc-b"})()
        player = type(
            "Player",
            (),
            {
                "player_id": 0,
                "cash": 11,
                "position": 14,
                "shards": 3,
                "hidden_trick_deck_index": 42,
                "trick_hand": [card_a, card_b],
            },
        )()

        gateway = _Gateway()
        client = _LocalHumanDecisionClient(human_seats=[0], ai_fallback=_DummyAi(), gateway=gateway)
        invocation = build_decision_invocation("choose_hidden_trick_card", (state, player, [card_a, card_b]), {})
        call = build_routed_decision_call(invocation, fallback_policy="required")

        client.resolve(call)

        self.assertIsNotNone(gateway.prompt)
        prompt = gateway.prompt
        public_context = prompt.get("public_context", {})
        self.assertEqual(public_context.get("active_by_card"), {1: "탐관오리", 2: "중매꾼", 3: "산적", 4: "꼬리 감독관"})
        self.assertEqual(public_context.get("weather_name"), "긴고 긴 겨울")
        self.assertEqual(public_context.get("weather_effect"), "종료를 1칸 앞당깁니다.")
        self.assertEqual(public_context.get("hidden_trick_deck_index"), 42)
        self.assertEqual(len(public_context.get("full_hand", [])), 2)

    def test_local_human_prompt_merges_gateway_public_context_for_draft(self) -> None:
        class _Gateway:
            def __init__(self) -> None:
                self.prompt = None

            def resolve_human_prompt(self, prompt, parser, fallback_fn):
                del parser, fallback_fn
                self.prompt = dict(prompt)
                return 1

        class _DummyAi:
            def choose_draft_card(self, state, player, offered_cards):
                del state, player, offered_cards
                return 1

        weather = type("Weather", (), {"name": "술선 수법", "effect": "징표를 가진 참가자는 3냥을 은행에 지불합니다."})()
        state = type(
            "State",
            (),
            {
                "rounds_completed": 0,
                "turn_index": 0,
                "active_by_card": {
                    1: "탐관오리",
                    2: "중매꾼",
                    3: "산적",
                    4: "꼬리 감독관",
                    5: "교리 연구관",
                    6: "만신",
                    7: "객주",
                    8: "건설업자",
                },
                "current_weather": weather,
            },
        )()
        trick_card = type("Card", (), {"deck_index": 61, "name": "월척회", "description": "desc-trick"})()
        player = type(
            "Player",
            (),
            {
                "player_id": 0,
                "cash": 20,
                "position": 5,
                "shards": 4,
                "drafted_cards": [],
                "hidden_trick_deck_index": None,
                "trick_hand": [trick_card],
            },
        )()

        gateway = _Gateway()
        client = _LocalHumanDecisionClient(human_seats=[0], ai_fallback=_DummyAi(), gateway=gateway)
        invocation = build_decision_invocation("choose_draft_card", (state, player, [1, 2, 3, 4]), {})
        call = build_routed_decision_call(invocation, fallback_policy="required")

        client.resolve(call)

        self.assertIsNotNone(gateway.prompt)
        public_context = gateway.prompt.get("public_context", {})
        self.assertEqual(public_context.get("active_by_card", {}).get(6), "만신")
        self.assertEqual(public_context.get("weather_name"), "술선 수법")
        self.assertEqual(public_context.get("weather_effect"), "징표를 가진 참가자는 3냥을 은행에 지불합니다.")
        self.assertEqual(public_context.get("draft_phase"), 1)
        self.assertEqual(public_context.get("offered_count"), 4)
        self.assertEqual(public_context.get("total_hand_count"), 1)
        self.assertEqual([card.get("name") for card in public_context.get("full_hand", [])], ["월척회"])

    def test_mark_target_context_uses_public_active_faces_for_future_slots(self) -> None:
        state = type(
            "State",
            (),
            {
                "rounds_completed": 1,
                "turn_index": 2,
                "current_round_order": [0, 1, 2],
                "active_by_card": {
                    2: "자객",
                    3: "탈출 노비",
                    4: "아전",
                    5: "교리 감독관",
                    6: "박수",
                    7: "중매꾼",
                    8: "사기꾼",
                },
                "players": [
                    type("Player", (), {"player_id": 0, "alive": True, "current_character": "자객", "revealed_this_round": False})(),
                    type("Player", (), {"player_id": 1, "alive": True, "current_character": "객주", "revealed_this_round": False})(),
                    type("Player", (), {"player_id": 2, "alive": True, "current_character": "건설업자", "revealed_this_round": False})(),
                ],
            },
        )()
        player = type("Player", (), {"player_id": 0, "cash": 11, "position": 6, "shards": 2, "current_character": "자객"})()

        context = build_public_context("choose_mark_target", (state, player, "자객"), {})
        invocation = build_decision_invocation("choose_mark_target", (state, player, "자객"), {})
        routed = build_routed_decision_call(invocation, fallback_policy="required")

        self.assertEqual(context["target_count"], 6)
        self.assertEqual(
            context["target_pairs"],
            [
                {"target_character": "탈출 노비", "target_card_no": 3},
                {"target_character": "아전", "target_card_no": 4},
                {"target_character": "교리 감독관", "target_card_no": 5},
                {"target_character": "박수", "target_card_no": 6},
                {"target_character": "중매꾼", "target_card_no": 7},
                {"target_character": "사기꾼", "target_card_no": 8},
            ],
        )
        self.assertEqual(
            [choice["choice_id"] for choice in routed.legal_choices],
            ["none", "탈출 노비", "아전", "교리 감독관", "박수", "중매꾼", "사기꾼"],
        )

    def test_final_character_choices_follow_active_face_names(self) -> None:
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0, "active_by_card": {7: "중매꾼", 8: "사기꾼"}})()
        player = type("Player", (), {"cash": 10, "position": 3, "drafted_cards": [7, 8]})()

        context = build_public_context("choose_final_character", (state, player, [7, 8]), {})
        invocation = build_decision_invocation("choose_final_character", (state, player, [7, 8]), {})
        routed = build_routed_decision_call(invocation, fallback_policy="required")

        self.assertEqual(context["choice_names"], ["중매꾼", "사기꾼"])
        self.assertEqual([choice["title"] for choice in routed.legal_choices], ["중매꾼", "사기꾼"])
        self.assertEqual(routed.choice_parser("7", invocation.args, invocation.kwargs, invocation.state, invocation.player), "중매꾼")

    def test_public_context_includes_weather_fields_when_state_has_current_weather(self) -> None:
        weather = type("Weather", (), {"name": "긴급 피난", "effect": "모든 짐 제거 비용이 2배가 됩니다."})()
        state = type("State", (), {"rounds_completed": 1, "turn_index": 2, "current_weather": weather})()
        player = type("Player", (), {"cash": 9, "position": 4, "shards": 1})()

        context = build_public_context("choose_purchase_tile", (state, player, 9, "T2", 4), {})

        self.assertEqual(context["weather_name"], "긴급 피난")
        self.assertEqual(context["weather_effect"], "모든 짐 제거 비용이 2배가 됩니다.")

    def test_lap_reward_context_exposes_budget_bundles_and_player_status(self) -> None:
        rules = type(
            "LapRules",
            (),
            {
                "points_budget": 10,
                "cash_pool": 5,
                "shards_pool": 3,
                "coins_pool": 3,
                "cash_point_cost": 2,
                "shards_point_cost": 3,
                "coins_point_cost": 3,
            },
        )()
        state = type(
            "State",
            (),
            {
                "rounds_completed": 1,
                "turn_index": 4,
                "lap_reward_cash_pool_remaining": 4,
                "lap_reward_shards_pool_remaining": 2,
                "lap_reward_coins_pool_remaining": 3,
                "config": type("Config", (), {"rules": type("Rules", (), {"lap_reward": rules})()})(),
            },
        )()
        player = type(
            "Player",
            (),
            {"cash": 18, "position": 9, "shards": 4, "hand_coins": 2, "score_coins_placed": 3, "tiles_owned": 5},
        )()

        context = build_public_context("choose_lap_reward", (state, player), {})

        self.assertEqual(context["budget"], 10)
        self.assertEqual(context["pools"], {"cash": 4, "shards": 2, "coins": 3})
        self.assertEqual(context["player_cash"], 18)
        self.assertEqual(context["player_shards"], 4)
        self.assertEqual(context["player_hand_coins"], 2)
        self.assertEqual(context["player_placed_coins"], 3)
        self.assertEqual(context["player_total_score"], 5)
        self.assertEqual(context["player_owned_tile_count"], 5)

    def test_trick_tile_target_context_exposes_candidates(self) -> None:
        state = type("State", (), {"rounds_completed": 2, "turn_index": 1})()
        player = type("Player", (), {"cash": 9, "position": 11, "shards": 1})()

        context = build_public_context(
            "choose_trick_tile_target",
            (state, player, "재뿌리기", [4, 9, 12], "other_owned_highest"),
            {},
        )

        self.assertEqual(context["card_name"], "재뿌리기")
        self.assertEqual(context["candidate_count"], 3)
        self.assertEqual(context["candidate_tiles"], [4, 9, 12])
        self.assertEqual(context["target_scope"], "other_owned_highest")

    def test_matchmaker_purchase_context_exposes_tile_metadata_and_adjacent_candidates(self) -> None:
        Tile = lambda zone, cost, rent, score: type(
            "Tile",
            (),
            {
                "zone_color": zone,
                "purchase_cost": cost,
                "rent_cost": rent,
                "score_coins": score,
                "kind": type("Kind", (), {"name": "T3"})(),
            },
        )()
        state = type(
            "State",
            (),
            {
                "rounds_completed": 2,
                "turn_index": 1,
                "tiles": [Tile("red", 3, 3, 1), Tile("red", 3, 3, 1), Tile("red", 3, 3, 1)],
                "block_ids": [1, 1, 1],
                "board": [type("Kind", (), {"name": "T3"})(), type("Kind", (), {"name": "T3"})(), type("Kind", (), {"name": "T3"})()],
                "tile_owner": [None, None, None],
            },
        )()
        player = type("Player", (), {"cash": 14, "position": 1, "shards": 2})()

        context = build_public_context(
            "choose_purchase_tile",
            (state, player, 0, state.board[0], 6),
            {"source": "matchmaker_adjacent"},
        )

        self.assertEqual(context["tile_index"], 0)
        self.assertEqual(context["landing_tile_index"], 1)
        self.assertEqual(context["tile_zone"], "red")
        self.assertEqual(context["tile_kind"], "T3")
        self.assertEqual(context["tile_purchase_cost"], 3)
        self.assertEqual(context["tile_rent_cost"], 3)
        self.assertEqual(context["tile_score_coins"], 1)
        self.assertEqual(context["candidate_tiles"], [0, 2])

    def test_decision_client_router_prefers_human_policy_attributes_and_human_seats(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionClientRouter

        class _FakeHumanClient:
            def __init__(self) -> None:
                self.policy = type("HumanPolicy", (), {"human_only_attr": "human"})()

            def resolve(self, call):  # noqa: ANN001
                return ("human", call.invocation.method_name, call.invocation.args, call.invocation.kwargs)

        class _FakeAiPolicy:
            ai_only_attr = "ai"

        class _FakeAiClient:
            def __init__(self) -> None:
                self.policy = _FakeAiPolicy()

            def resolve(self, call):  # noqa: ANN001
                return ("ai", call.invocation.method_name, call.invocation.args, call.invocation.kwargs)

        router = _ServerDecisionClientRouter(
            human_seats=[0],
            human_client=_FakeHumanClient(),
            ai_client=_FakeAiClient(),
        )

        human_player = type("Player", (), {"player_id": 0})()
        ai_player = type("Player", (), {"player_id": 1})()
        human_call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (object(), human_player), {}),
            fallback_policy="human_timeout",
        )
        ai_call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (object(), ai_player), {}),
            fallback_policy="ai",
        )

        self.assertEqual(getattr(router.attribute_target("human_only_attr"), "human_only_attr"), "human")
        self.assertEqual(getattr(router.attribute_target("ai_only_attr"), "ai_only_attr"), "ai")
        self.assertEqual(router.client_for_call(human_call).__class__.__name__, "_FakeHumanClient")
        self.assertEqual(router.client_for_call(ai_call).__class__.__name__, "_FakeAiClient")
        self.assertEqual(getattr(router.seat_type_for_player_id(0), "value", None), "human")
        self.assertIsNone(router.seat_type_for_player_id(99))
        self.assertEqual(human_call.request.fallback_policy, "human_timeout")
        self.assertEqual(ai_call.request.fallback_policy, "ai")

    def test_decision_client_router_can_resolve_seat_types_from_session_seats(self) -> None:
        from apps.server.src.domain.session_models import SeatConfig, SeatType
        from apps.server.src.services.runtime_service import _ServerDecisionClientRouter

        class _FakeHumanClient:
            def __init__(self) -> None:
                self.policy = type("HumanPolicy", (), {})()

            def resolve(self, call):  # noqa: ANN001
                return ("human", call.request.player_id)

        class _FakeAiClient:
            def __init__(self) -> None:
                self.policy = type("AiPolicy", (), {})()

            def resolve(self, call):  # noqa: ANN001
                return ("ai", call.request.player_id)

        router = _ServerDecisionClientRouter(
            session_seats=[
                SeatConfig(seat=1, seat_type=SeatType.HUMAN),
                SeatConfig(seat=2, seat_type=SeatType.AI, ai_profile="balanced"),
            ],
            human_client=_FakeHumanClient(),
            ai_client=_FakeAiClient(),
        )

        human_player = type("Player", (), {"player_id": 0})()
        ai_player = type("Player", (), {"player_id": 1})()
        human_call = build_routed_decision_call(build_decision_invocation("choose_movement", (object(), human_player), {}))
        ai_call = build_routed_decision_call(build_decision_invocation("choose_movement", (object(), ai_player), {}))

        self.assertEqual(getattr(router.seat_type_for_player_id(0), "value", None), "human")
        self.assertEqual(getattr(router.seat_type_for_player_id(1), "value", None), "ai")
        self.assertEqual(router.client_for_call(human_call).resolve(human_call), ("human", 0))
        self.assertEqual(router.client_for_call(ai_call).resolve(ai_call), ("ai", 1))

    def test_client_factory_builds_external_ai_placeholder_per_seat_descriptor(self) -> None:
        from apps.server.src.domain.session_models import ParticipantClientType, SeatConfig, SeatType
        from apps.server.src.services.runtime_service import (
            _ExternalAiDecisionClient,
            _LoopbackExternalAiTransport,
            _ServerDecisionClientFactory,
        )

        gateway = type("Gateway", (), {"_session_id": "sess_loopback"})()
        human_client = object()
        factory = _ServerDecisionClientFactory()
        participants = factory.create_participant_clients(
            session_seats=[
                SeatConfig(
                    seat=1,
                    seat_type=SeatType.AI,
                    ai_profile="balanced",
                    participant_client=ParticipantClientType.EXTERNAL_AI,
                    participant_config={"transport": "loopback", "endpoint": "local://bot-worker-1"},
                ),
                SeatConfig(
                    seat=2,
                    seat_type=SeatType.HUMAN,
                    participant_client=ParticipantClientType.HUMAN_HTTP,
                ),
            ],
            human_client=human_client,
            ai_fallback=object(),
            gateway=gateway,  # type: ignore[arg-type]
        )

        self.assertIs(participants[1], human_client)
        self.assertIsInstance(participants[0], _ExternalAiDecisionClient)
        self.assertIsInstance(participants[0]._transport, _LoopbackExternalAiTransport)
        self.assertEqual(participants[0]._transport._config["endpoint"], "local://bot-worker-1")

    def test_client_factory_builds_http_external_transport_when_requested(self) -> None:
        from apps.server.src.domain.session_models import ParticipantClientType, SeatConfig, SeatType
        from apps.server.src.services.runtime_service import (
            _ExternalAiDecisionClient,
            _HttpExternalAiTransport,
            _ServerDecisionClientFactory,
        )

        gateway = type("Gateway", (), {"_session_id": "sess_http"})()
        human_client = object()
        sender_calls: list[object] = []
        factory = _ServerDecisionClientFactory(external_ai_sender=lambda envelope: sender_calls.append(envelope) or "minus_one")
        participants = factory.create_participant_clients(
            session_seats=[
                SeatConfig(
                    seat=1,
                    seat_type=SeatType.AI,
                    ai_profile="balanced",
                    participant_client=ParticipantClientType.EXTERNAL_AI,
                    participant_config={"transport": "http", "endpoint": "http://bot-worker.local/decide"},
                )
            ],
            human_client=human_client,
            ai_fallback=object(),
            gateway=gateway,  # type: ignore[arg-type]
        )

        self.assertIsInstance(participants[0], _ExternalAiDecisionClient)
        self.assertIsInstance(participants[0]._transport, _HttpExternalAiTransport)
        self.assertEqual(participants[0]._transport._config["transport"], "http")

    def test_external_ai_transport_enriches_public_context_with_participant_metadata(self) -> None:
        from apps.server.src.services.runtime_service import _LoopbackExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return "minus_one"

        gateway = _FakeGateway()
        transport = _LoopbackExternalAiTransport(
            session_id="sess_ext_1",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=3,
            config={"transport": "loopback", "endpoint": "local://bot-worker-3"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 2, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(gateway.calls[0]["public_context"]["participant_client"], "external_ai")
        self.assertEqual(gateway.calls[0]["public_context"]["participant_seat"], 3)
        self.assertEqual(gateway.calls[0]["public_context"]["participant_transport"], "loopback")
        self.assertEqual(gateway.calls[0]["public_context"]["participant_config"]["endpoint"], "local://bot-worker-3")

    def test_build_decision_invocation_captures_method_and_player_identity(self) -> None:
        player = type("Player", (), {"player_id": 2, "cash": 11})()
        state = type("State", (), {"rounds_completed": 1})()

        invocation = build_decision_invocation(
            "choose_purchase_tile",
            (state, player, 9, "T2", 4),
            {"source": "landing"},
        )

        self.assertEqual(invocation.method_name, "choose_purchase_tile")
        self.assertEqual(invocation.player_id, 2)
        self.assertIs(invocation.player, player)
        self.assertEqual(invocation.args[2], 9)
        self.assertEqual(invocation.kwargs["source"], "landing")

    def test_build_canonical_decision_request_aligns_request_metadata(self) -> None:
        player = type("Player", (), {"player_id": 2, "cash": 11, "position": 8, "shards": 3})()
        state = type("State", (), {"rounds_completed": 1, "turn_index": 3})()
        invocation = build_decision_invocation(
            "choose_purchase_tile",
            (state, player, 9, "T2", 4),
            {"source": "landing"},
        )

        request = build_canonical_decision_request(invocation, fallback_policy="ai")

        self.assertEqual(request.decision_name, "choose_purchase_tile")
        self.assertEqual(request.request_type, "purchase_tile")
        self.assertEqual(request.player_id, 2)
        self.assertEqual(request.round_index, 2)
        self.assertEqual(request.turn_index, 4)
        self.assertEqual(request.public_context["tile_index"], 9)
        self.assertEqual(request.public_context["cost"], 4)
        self.assertEqual(request.fallback_policy, "ai")

    def test_routed_decision_call_exposes_legal_choices_for_external_clients(self) -> None:
        state = type("State", (), {"rounds_completed": 1, "turn_index": 3})()
        player = type("Player", (), {"player_id": 2, "cash": 11, "position": 8, "shards": 3})()

        call = build_routed_decision_call(
            build_decision_invocation("choose_purchase_tile", (state, player, 9, "T2", 4), {"source": "landing"}),
            fallback_policy="ai",
        )

        self.assertEqual(call.request.request_type, "purchase_tile")
        self.assertEqual([choice["choice_id"] for choice in call.legal_choices], ["yes", "no"])

    def test_bridge_allows_injected_decision_client_factory(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeClient:
            def __init__(self, label: str) -> None:
                self.label = label
                self.policy = type("Policy", (), {})()
                self.calls: list[str] = []

            def resolve(self, call):  # noqa: ANN001
                self.calls.append(call.request.request_type)
                return self.label

        class _FakeFactory:
            def __init__(self) -> None:
                self.ai_client = _FakeClient("ai-client")
                self.human_client = _FakeClient("human-client")

            def create_ai_client(self, *, ai_fallback, gateway):  # noqa: ANN001
                del ai_fallback, gateway
                return self.ai_client

            def create_human_client(self, *, human_seats, ai_fallback, gateway):  # noqa: ANN001
                del human_seats, ai_fallback, gateway
                return self.human_client

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            factory = _FakeFactory()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_bridge_client_factory",
                human_seats=[],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                client_factory=factory,
            )
            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 5, "position": 2, "shards": 1})()

            result = bridge.choose_pabal_dice_mode(state, player)

            self.assertEqual(result, "ai-client")
            self.assertEqual(factory.ai_client.calls, ["pabal_dice_mode"])
            self.assertEqual(factory.human_client.calls, [])
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_http_external_transport_sends_envelope_and_parses_choice_id(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        sender_calls: list[object] = []
        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_1",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "timeout_ms": 9000,
                "contract_version": "v1",
                "required_capabilities": ["choice_id_response"],
            },
            healthchecker=lambda _config: {"ok": True, "worker_contract_version": "v1", "capabilities": ["choice_id_response"]},
            sender=lambda envelope: sender_calls.append(envelope) or {"choice_id": "yes"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_purchase_tile", (state, player, 9, "T2", 4), {"source": "landing"}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertTrue(result)
        self.assertEqual(sender_calls[0].request_type, "purchase_tile")
        self.assertEqual(sender_calls[0].worker_contract_version, "v1")
        self.assertEqual(sender_calls[0].required_capabilities, ["choice_id_response"])
        self.assertEqual([choice["choice_id"] for choice in sender_calls[0].legal_choices], ["yes", "no"])
        self.assertEqual(gateway.calls[0]["public_context"]["participant_transport"], "http")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_worker")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_attempt_count"], 1)

    def test_http_external_transport_retries_then_falls_back_to_local_ai(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        attempts: list[int] = []

        def _failing_sender(envelope):  # noqa: ANN001
            attempts.append(envelope.seat)
            raise RuntimeError("worker unavailable")

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_2",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=3,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "retry_count": 2,
                "backoff_ms": 0,
                "fallback_mode": "local_ai",
            },
            healthchecker=lambda _config: {"ok": True, "worker_contract_version": "v1", "capabilities": []},
            sender=_failing_sender,
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 2, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_failure_code"], "worker unavailable")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_fallback_mode"], "local_ai")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_attempt_count"], 3)

    def test_http_external_transport_falls_back_when_healthcheck_misses_required_capability(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_health_1",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "required_capabilities": ["choice_payload_echo"],
            },
            healthchecker=lambda _config: (_ for _ in ()).throw(RuntimeError("external_ai_missing_required_capability")),
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(
            gateway.calls[0]["public_context"]["external_ai_failure_code"],
            "external_ai_missing_required_capability",
        )
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_falls_back_when_healthcheck_misses_required_request_type(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_health_2",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "required_request_types": ["pabal_dice_mode"],
            },
            healthchecker=lambda _config: {
                "ok": True,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["movement"],
            },
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(
            gateway.calls[0]["public_context"]["external_ai_failure_code"],
            "external_ai_missing_required_request_type",
        )
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_falls_back_when_worker_is_not_ready(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_health_not_ready",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "require_ready": True,
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": False,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
            },
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_failure_code"], "external_ai_worker_not_ready")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_ready_state"], "not_ready")

    def test_http_external_transport_falls_back_when_decision_response_reports_not_ready(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_response_not_ready",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "require_ready": True,
                "expected_worker_id": "bot-worker-1",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_id": "bot-worker-1",
                "worker_profile": "reference_heuristic",
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
            },
            sender=lambda _envelope: {"choice_id": "plus_one", "ready": False, "worker_id": "bot-worker-1"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_failure_code"], "external_ai_worker_not_ready")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_ready_state"], "not_ready")

    def test_http_external_transport_falls_back_when_worker_lacks_request_type_support(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_request_type_1",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["movement"],
            },
            sender=lambda _envelope: {"choice_id": "yes"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 8, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_purchase_tile", (state, player, 9, "T2", 4), {"source": "landing"}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertFalse(result)
        self.assertEqual(
            gateway.calls[0]["public_context"]["external_ai_failure_code"],
            "external_ai_missing_request_type_support",
        )
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_falls_back_when_worker_lacks_transport_support(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_transport_support",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
                "supported_transports": ["grpc"],
            },
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(
            gateway.calls[0]["public_context"]["external_ai_failure_code"],
            "external_ai_missing_transport_support",
        )
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_surfaces_worker_policy_metadata(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_policy_metadata",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_id": "bot-worker-1",
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
                "supported_transports": ["http"],
                "policy_mode": "heuristic_v3_gpt",
                "worker_adapter": "reference_heuristic_v1",
                "policy_class": "HeuristicPolicy",
                "decision_style": "contract_heuristic",
            },
            sender=lambda _envelope: {
                "choice_id": "plus_one",
                "worker_id": "bot-worker-1",
                "worker_profile": "reference_heuristic",
                "policy_mode": "heuristic_v3_gpt",
                "worker_adapter": "reference_heuristic_v1",
                "policy_class": "HeuristicPolicy",
                "decision_style": "contract_heuristic",
                "supported_transports": ["http"],
            },
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "plus_one")
        public_context = gateway.calls[0]["public_context"]
        self.assertEqual(public_context["external_ai_worker_profile"], "reference_heuristic")
        self.assertEqual(public_context["external_ai_policy_mode"], "heuristic_v3_gpt")
        self.assertEqual(public_context["external_ai_worker_adapter"], "reference_heuristic_v1")
        self.assertEqual(public_context["external_ai_policy_class"], "HeuristicPolicy")
        self.assertEqual(public_context["external_ai_decision_style"], "contract_heuristic")
        self.assertEqual(public_context["external_ai_resolution_status"], "resolved_by_worker")

    def test_http_external_transport_surfaces_priority_adapter_metadata(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_priority_metadata",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "required_worker_adapter": "priority_score_v1",
                "required_policy_class": "PriorityScoredPolicy",
                "required_decision_style": "priority_scored_contract",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_id": "bot-worker-2",
                "worker_profile": "priority_scored",
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response", "priority_scored_choice"],
                "supported_request_types": ["pabal_dice_mode"],
                "supported_transports": ["http"],
                "policy_mode": "heuristic_v3_gpt",
                "worker_adapter": "priority_score_v1",
                "policy_class": "PriorityScoredPolicy",
                "decision_style": "priority_scored_contract",
            },
            sender=lambda _envelope: {
                "choice_id": "plus_one",
                "worker_id": "bot-worker-2",
                "worker_profile": "priority_scored",
                "policy_mode": "heuristic_v3_gpt",
                "worker_adapter": "priority_score_v1",
                "policy_class": "PriorityScoredPolicy",
                "decision_style": "priority_scored_contract",
                "supported_request_types": ["pabal_dice_mode"],
                "supported_transports": ["http"],
            },
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "plus_one")
        public_context = gateway.calls[0]["public_context"]
        self.assertEqual(public_context["external_ai_worker_profile"], "priority_scored")
        self.assertEqual(public_context["external_ai_worker_adapter"], "priority_score_v1")
        self.assertEqual(public_context["external_ai_policy_class"], "PriorityScoredPolicy")
        self.assertEqual(public_context["external_ai_decision_style"], "priority_scored_contract")
        self.assertEqual(public_context["external_ai_resolution_status"], "resolved_by_worker")

    def test_http_external_transport_falls_back_when_worker_policy_metadata_mismatches(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_policy_mismatch",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "required_policy_mode": "heuristic_v3_gpt",
                "required_decision_style": "contract_heuristic",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
                "policy_mode": "heuristic_v3_gpt",
                "decision_style": "freeform",
            },
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_failure_code"], "external_ai_decision_style_mismatch")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_falls_back_when_worker_policy_class_mismatches(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_policy_class_mismatch",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "required_policy_mode": "heuristic_v3_gpt",
                "required_policy_class": "HeuristicPolicy",
                "required_decision_style": "contract_heuristic",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
                "policy_mode": "heuristic_v3_gpt",
                "policy_class": "ExperimentalPolicy",
                "decision_style": "contract_heuristic",
            },
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_failure_code"], "external_ai_policy_class_mismatch")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_falls_back_when_worker_adapter_mismatches(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_adapter_mismatch",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "required_worker_adapter": "reference_heuristic_v1",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "ready": True,
                "worker_contract_version": "v1",
                "capabilities": ["choice_id_response"],
                "supported_request_types": ["pabal_dice_mode"],
                "worker_adapter": "scripted_test_v1",
            },
            sender=lambda _envelope: {"choice_id": "plus_one"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_failure_code"], "external_ai_worker_adapter_mismatch")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_local_fallback")

    def test_http_external_transport_falls_back_when_worker_identity_mismatches(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                return kwargs["resolver"]()

        transport = _HttpExternalAiTransport(
            session_id="sess_http_identity_1",
            ai_fallback=_FakeAiPolicy(),
            gateway=_FakeGateway(),  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "expected_worker_id": "bot-worker-1",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "worker_id": "bot-worker-1",
                "worker_contract_version": "v1",
                "capabilities": [],
            },
            sender=lambda _envelope: {"choice_id": "plus_one", "worker_id": "intruder-worker"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")

    def test_custom_healthchecker_still_validates_worker_identity(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                return kwargs["resolver"]()

        transport = _HttpExternalAiTransport(
            session_id="sess_http_identity_2",
            ai_fallback=_FakeAiPolicy(),
            gateway=_FakeGateway(),  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "expected_worker_id": "bot-worker-1",
            },
            healthchecker=lambda _config: {
                "ok": True,
                "worker_id": "intruder-worker",
                "worker_contract_version": "v1",
                "capabilities": [],
            },
            sender=lambda _envelope: {"choice_id": "plus_one", "worker_id": "bot-worker-1"},
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")

    def test_auth_headers_merge_custom_header_and_scheme(self) -> None:
        from apps.server.src.services.runtime_service import _merge_external_ai_auth_headers

        headers = {"Content-Type": "application/json"}
        _merge_external_ai_auth_headers(
            headers,
            {
                "auth_token": "worker-secret",
                "auth_header_name": "X-Worker-Auth",
                "auth_scheme": "Token",
            },
        )

        self.assertEqual(headers["X-Worker-Auth"], "Token worker-secret")

    def test_default_healthcheck_cache_key_respects_worker_requirements(self) -> None:
        from apps.server.src.services.runtime_service import _EXTERNAL_AI_HEALTH_CACHE, _default_external_ai_healthcheck

        class _FakeResponse:
            def __init__(self, payload: str) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
                return False

        urlopen_calls: list[str] = []

        def _fake_urlopen(request, timeout=0):  # noqa: ANN001
            del timeout
            urlopen_calls.append(request.full_url)
            return _FakeResponse(
                '{"ok": true, "worker_id": "worker-a", "worker_contract_version": "v1", "capabilities": ["choice_id_response", "healthcheck"], "supported_request_types": ["movement", "purchase_tile"]}'
            )

        _EXTERNAL_AI_HEALTH_CACHE.clear()
        with patch("apps.server.src.services.runtime_service.urllib_request.urlopen", side_effect=_fake_urlopen):
            payload_a = _default_external_ai_healthcheck(
                {
                    "endpoint": "http://bot-worker.local/decide",
                    "healthcheck_ttl_ms": 10000,
                    "expected_worker_id": "worker-a",
                    "healthcheck_policy": "auto",
                    "required_capabilities": ["choice_id_response"],
                }
            )
            payload_b = _default_external_ai_healthcheck(
                {
                    "endpoint": "http://bot-worker.local/decide",
                    "healthcheck_ttl_ms": 10000,
                    "expected_worker_id": "worker-a",
                    "healthcheck_policy": "required",
                    "required_capabilities": ["choice_id_response", "healthcheck"],
                    "required_request_types": ["purchase_tile"],
                }
            )

        self.assertEqual(payload_a["worker_id"], "worker-a")
        self.assertEqual(payload_b["worker_id"], "worker-a")
        self.assertEqual(len(urlopen_calls), 2)

    def test_http_external_transport_can_require_default_healthcheck_with_custom_sender(self) -> None:
        from apps.server.src.services.runtime_service import _EXTERNAL_AI_HEALTH_CACHE, _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        class _FakeResponse:
            def __init__(self, payload: str) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
                return False

        _EXTERNAL_AI_HEALTH_CACHE.clear()
        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_required_health",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "fallback_mode": "local_ai",
                "healthcheck_policy": "required",
                "expected_worker_id": "worker-a",
                "required_request_types": ["purchase_tile"],
            },
            sender=lambda _envelope: {
                "choice_id": "yes",
                "worker_id": "worker-a",
                "supported_request_types": ["purchase_tile"],
            },
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 8, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_purchase_tile", (state, player, 9, "T2", 4), {"source": "landing"}),
            fallback_policy="ai",
        )

        with patch(
            "apps.server.src.services.runtime_service.urllib_request.urlopen",
            return_value=_FakeResponse(
                '{"ok": true, "ready": true, "worker_id": "worker-a", "worker_contract_version": "v1", "capabilities": ["choice_id_response"], "supported_request_types": ["purchase_tile"]}'
            ),
        ) as urlopen:
            result = transport.resolve(call)

        self.assertTrue(result)
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_worker_id"], "worker-a")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "resolved_by_worker")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_ready_state"], "ready")
        self.assertEqual(urlopen.call_count, 1)

    def test_http_external_transport_caps_attempts_by_max_attempt_count(self) -> None:
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        sender_attempts: list[int] = []
        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_attempt_cap",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=2,
            config={
                "transport": "http",
                "endpoint": "http://bot-worker.local/decide",
                "retry_count": 5,
                "max_attempt_count": 2,
                "fallback_mode": "local_ai",
            },
            sender=lambda _envelope: sender_attempts.append(len(sender_attempts) + 1) or (_ for _ in ()).throw(RuntimeError("external_ai_http_error")),
        )
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
            fallback_policy="ai",
        )

        result = transport.resolve(call)

        self.assertEqual(result, "minus_one")
        self.assertEqual(sender_attempts, [1, 2])
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_attempt_count"], 2)
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_attempt_limit"], 2)

    def test_external_ai_error_classifier_maps_timeout_and_known_runtime_codes(self) -> None:
        from apps.server.src.services.runtime_service import _classify_external_ai_error

        self.assertEqual(_classify_external_ai_error(TimeoutError()), "external_ai_timeout")
        self.assertEqual(
            _classify_external_ai_error(RuntimeError("external_ai_worker_identity_mismatch")),
            "external_ai_worker_identity_mismatch",
        )
        self.assertEqual(
            _classify_external_ai_error(RuntimeError("external_ai_missing_required_request_type")),
            "external_ai_missing_required_request_type",
        )
        self.assertEqual(
            _classify_external_ai_error(RuntimeError("external_ai_worker_not_ready")),
            "external_ai_worker_not_ready",
        )
        self.assertEqual(
            _classify_external_ai_error(ValueError("external_ai_response_not_object")),
            "external_ai_response_not_object",
        )

    def test_http_external_transport_reaches_real_worker_over_localhost(self) -> None:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="websockets\\.legacy is deprecated.*",
                    category=DeprecationWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message="websockets\\.server\\.WebSocketServerProtocol is deprecated",
                    category=DeprecationWarning,
                )
                import uvicorn
        except ModuleNotFoundError:
            self.skipTest("uvicorn is not installed in this environment")

        from apps.server.src.external_ai_app import create_app
        from apps.server.src.services.external_ai_worker_service import ExternalAiWorkerService
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError:
            sock.close()
            self.skipTest("localhost socket binding is not permitted in this environment")
        host, port = sock.getsockname()
        sock.close()

        worker = ExternalAiWorkerService(worker_id="worker-http-test", policy_mode="heuristic_v3_gpt")
        app = create_app(worker)
        config = uvicorn.Config(app, host=host, port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if getattr(server, "started", False):
                    break
                time.sleep(0.05)
            else:
                self.fail("external_ai_worker_failed_to_start")

            gateway = _FakeGateway()
            transport = _HttpExternalAiTransport(
                session_id="sess_http_real_worker",
                ai_fallback=_FakeAiPolicy(),
                gateway=gateway,  # type: ignore[arg-type]
                seat=2,
                config={
                    "transport": "http",
                    "endpoint": f"http://{host}:{port}/decide",
                    "timeout_ms": 3000,
                    "retry_count": 0,
                    "backoff_ms": 0,
                    "fallback_mode": "local_ai",
                },
            )
            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 8, "position": 9, "shards": 1})()
            call = build_routed_decision_call(
                build_decision_invocation("choose_purchase_tile", (state, player, 9, "T2", 4), {"source": "landing"}),
                fallback_policy="ai",
            )

            result = transport.resolve(call)

            self.assertTrue(result)
            self.assertEqual(gateway.calls[0]["public_context"]["participant_transport"], "http")
            self.assertEqual(gateway.calls[0]["public_context"]["participant_client"], "external_ai")
            self.assertEqual(gateway.calls[0]["public_context"]["external_ai_worker_profile"], "reference_heuristic")
        finally:
            server.should_exit = True
            thread.join(timeout=5.0)

    def test_http_external_transport_reaches_real_priority_worker_over_localhost(self) -> None:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="websockets\\.legacy is deprecated.*",
                    category=DeprecationWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message="websockets\\.server\\.WebSocketServerProtocol is deprecated",
                    category=DeprecationWarning,
                )
                import uvicorn
        except ModuleNotFoundError:
            self.skipTest("uvicorn is not installed in this environment")

        from apps.server.src.external_ai_app import create_app
        from apps.server.src.services.external_ai_worker_service import ExternalAiWorkerService
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                return kwargs["resolver"]()

        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError:
            sock.close()
            self.skipTest("localhost socket binding is not permitted in this environment")
        host, port = sock.getsockname()
        sock.close()

        worker = ExternalAiWorkerService(
            worker_id="worker-http-priority-test",
            policy_mode="heuristic_v3_gpt",
            worker_profile="priority_scored",
            worker_adapter="priority_score_v1",
        )
        app = create_app(worker)
        config = uvicorn.Config(app, host=host, port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if getattr(server, "started", False):
                    break
                time.sleep(0.05)
            else:
                self.fail("external_ai_priority_worker_failed_to_start")

            gateway = _FakeGateway()
            transport = _HttpExternalAiTransport(
                session_id="sess_http_real_priority_worker",
                ai_fallback=_FakeAiPolicy(),
                gateway=gateway,  # type: ignore[arg-type]
                seat=2,
                config={
                    "transport": "http",
                    "endpoint": f"http://{host}:{port}/decide",
                    "timeout_ms": 3000,
                    "retry_count": 0,
                    "backoff_ms": 0,
                    "fallback_mode": "local_ai",
                    "required_worker_adapter": "priority_score_v1",
                    "required_policy_class": "PriorityScoredPolicy",
                    "required_decision_style": "priority_scored_contract",
                },
            )
            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 8, "position": 9, "shards": 1})()
            call = build_routed_decision_call(
                build_decision_invocation("choose_pabal_dice_mode", (state, player), {}),
                fallback_policy="ai",
            )

            result = transport.resolve(call)

            self.assertEqual(result, "plus_one")
            public_context = gateway.calls[0]["public_context"]
            self.assertEqual(public_context["external_ai_worker_profile"], "priority_scored")
            self.assertEqual(public_context["external_ai_worker_adapter"], "priority_score_v1")
            self.assertEqual(public_context["external_ai_policy_class"], "PriorityScoredPolicy")
            self.assertEqual(public_context["external_ai_decision_style"], "priority_scored_contract")
            self.assertEqual(public_context["external_ai_resolution_status"], "resolved_by_worker")
        finally:
            server.should_exit = True
            thread.join(timeout=5.0)

    def test_start_runtime_uses_async_to_thread_bridge(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        calls: list[tuple[str, int, str | None]] = []
        original = self.runtime_service._run_engine_sync

        def _fake_run_engine_sync(loop, session_id: str, seed: int, policy_mode: str | None) -> None:  # noqa: ANN001
            del loop
            calls.append((session_id, seed, policy_mode))

        self.runtime_service._run_engine_sync = _fake_run_engine_sync  # type: ignore[method-assign]
        try:
            async def _exercise() -> dict:
                await self.runtime_service.start_runtime(session.session_id, seed=99, policy_mode="balanced_v2")
                status_local = self.runtime_service.runtime_status(session.session_id)
                self.assertIn(status_local.get("status"), {"running", "finished"})
                for _ in range(30):
                    status_local = self.runtime_service.runtime_status(session.session_id)
                    if status_local.get("status") == "finished":
                        break
                    await asyncio.sleep(0.01)
                return status_local

            status = asyncio.run(_exercise())
            for _ in range(3):
                status = self.runtime_service.runtime_status(session.session_id)
                if status.get("status") == "finished":
                    break
            self.assertEqual(status.get("status"), "finished")
        finally:
            self.runtime_service._run_engine_sync = original  # type: ignore[method-assign]

        self.assertEqual(calls, [(session.session_id, 99, "balanced_v2")])

    def test_runtime_status_marks_recovery_required_for_in_progress_without_task(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        restarted_runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
        )
        status = restarted_runtime.runtime_status(session.session_id)
        self.assertEqual(status.get("status"), "recovery_required")
        self.assertEqual(status.get("reason"), "runtime_task_missing_after_restart")

    def test_run_engine_sync_uses_human_policy_bridge_when_human_seat_exists(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        import engine

        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        captured: dict[str, object] = {}

        class _FakeGameEngine:
            def __init__(self, config, policy, rng, event_stream, decision_port=None):  # noqa: ANN001
                del config, rng, event_stream
                captured["policy"] = policy
                captured["decision_port"] = decision_port

            def run(self) -> None:
                return None

        loop = asyncio.new_event_loop()
        try:
            with patch.object(engine, "GameEngine", _FakeGameEngine):
                self.runtime_service._run_engine_sync(loop, session.session_id, seed=42, policy_mode=None)
        finally:
            loop.close()

        policy_obj = captured.get("policy")
        self.assertIsNotNone(policy_obj)
        self.assertTrue(hasattr(policy_obj, "_inner"))
        self.assertIs(captured.get("decision_port"), policy_obj)

    def test_run_engine_sync_uses_ai_policy_when_all_seats_are_ai(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        import engine

        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        captured: dict[str, object] = {}

        class _FakeGameEngine:
            def __init__(self, config, policy, rng, event_stream, decision_port=None):  # noqa: ANN001
                del config, rng, event_stream
                captured["policy"] = policy
                captured["decision_port"] = decision_port

            def run(self) -> None:
                return None

        loop = asyncio.new_event_loop()
        try:
            with patch.object(engine, "GameEngine", _FakeGameEngine):
                self.runtime_service._run_engine_sync(loop, session.session_id, seed=42, policy_mode=None)
        finally:
            loop.close()

        policy_obj = captured.get("policy")
        self.assertIsNotNone(policy_obj)
        self.assertTrue(hasattr(policy_obj, "_gateway"))
        self.assertIs(captured.get("decision_port"), policy_obj)

    def test_ai_bridge_emits_requested_then_resolved_for_ai_choice(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 12, "position": 5, "shards": 4})()
            result = bridge.choose_purchase_tile(state, player, 6, "T2", 4, source="landing")
            self.assertFalse(result)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "purchase_tile")
            self.assertEqual(resolved.payload.get("choice_id"), "no")
            self.assertEqual(requested.payload.get("public_context", {}).get("round_index"), 1)
            self.assertEqual(requested.payload.get("public_context", {}).get("turn_index"), 1)
            self.assertEqual(resolved.payload.get("public_context", {}).get("round_index"), 1)
            self.assertEqual(resolved.payload.get("public_context", {}).get("turn_index"), 1)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_mark_target_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_mark_target(self, state, player, actor_name):  # noqa: ANN001
                del state, player, actor_name
                return 3

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_mark_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 2})()
            player = type("Player", (), {"player_id": 1, "cash": 9, "position": 12, "shards": 5})()
            result = bridge.choose_mark_target(state, player, "Bandit")
            self.assertEqual(result, 3)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_mark_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "mark_target")
            self.assertEqual(resolved.payload.get("choice_id"), "3")
            self.assertEqual(requested.payload.get("public_context", {}).get("round_index"), 2)
            self.assertEqual(requested.payload.get("public_context", {}).get("turn_index"), 3)
            self.assertEqual(resolved.payload.get("public_context", {}).get("round_index"), 2)
            self.assertEqual(resolved.payload.get("public_context", {}).get("turn_index"), 3)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_active_flip_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_active_flip_card(self, state, player, flippable_cards):  # noqa: ANN001
                del state, player, flippable_cards
                return 7

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_flip_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 2, "turn_index": 0})()
            player = type("Player", (), {"player_id": 0, "cash": 20, "position": 0, "shards": 4})()
            result = bridge.choose_active_flip_card(state, player, [1, 7, 8])
            self.assertEqual(result, 7)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_flip_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 1
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "active_flip")
            self.assertEqual(resolved.payload.get("choice_id"), "7")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_specific_trick_reward_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeReward:
            def __init__(self, deck_index: int, name: str) -> None:
                self.deck_index = deck_index
                self.name = name

        class _FakeAiPolicy:
            def choose_specific_trick_reward(self, state, player, choices):  # noqa: ANN001
                del state, player
                return choices[1]

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_specific_reward_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 2, "turn_index": 1})()
            player = type("Player", (), {"player_id": 2, "cash": 11, "position": 7, "shards": 4})()
            choices = [_FakeReward(101, "Scout Route"), _FakeReward(102, "Lucky Break")]
            result = bridge.choose_specific_trick_reward(state, player, choices)
            self.assertEqual(getattr(result, "deck_index", None), 102)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_specific_reward_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 3
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "specific_trick_reward")
            self.assertEqual(resolved.payload.get("choice_id"), "102")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_doctrine_relief_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeCandidate:
            def __init__(self, player_id: int) -> None:
                self.player_id = player_id

        class _FakeAiPolicy:
            def choose_doctrine_relief_target(self, state, player, candidates):  # noqa: ANN001
                del state, player, candidates
                return 4

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_doctrine_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 3, "turn_index": 1})()
            player = type("Player", (), {"player_id": 1, "cash": 8, "position": 10, "shards": 2})()
            candidates = [_FakeCandidate(2), _FakeCandidate(4)]
            result = bridge.choose_doctrine_relief_target(state, player, candidates)
            self.assertEqual(result, 4)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_doctrine_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "doctrine_relief")
            self.assertEqual(resolved.payload.get("choice_id"), "4")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_burden_exchange_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeCard:
            burden_cost = 4
            name = "Heavy Burden"

        class _FakeAiPolicy:
            def choose_burden_exchange_on_supply(self, state, player, card):  # noqa: ANN001
                del state, player, card
                return True

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_burden_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 4, "turn_index": 0})()
            player = type("Player", (), {"player_id": 2, "cash": 12, "position": 18, "shards": 3})()
            result = bridge.choose_burden_exchange_on_supply(state, player, _FakeCard())
            self.assertTrue(result)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_burden_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 3
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "burden_exchange")
            self.assertEqual(resolved.payload.get("choice_id"), "yes")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_runaway_step_choice_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_runaway_slave_step(self, state, player, one_short_pos, bonus_target_pos, bonus_target_kind):  # noqa: ANN001
                del state, player, one_short_pos, bonus_target_pos, bonus_target_kind
                return True

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_runaway_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 5, "turn_index": 0})()
            player = type("Player", (), {"player_id": 0, "cash": 9, "position": 22, "shards": 5})()
            result = bridge.choose_runaway_slave_step(state, player, 25, 26, "S")
            self.assertTrue(result)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_runaway_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 1
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "runaway_step_choice")
            self.assertEqual(resolved.payload.get("choice_id"), "yes")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_coin_placement_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_coin_placement_tile(self, state, player):  # noqa: ANN001
                del state, player
                return 18

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_coin_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 5, "turn_index": 2})()
            player = type(
                "Player",
                (),
                {
                    "player_id": 1,
                    "cash": 14,
                    "position": 9,
                    "shards": 4,
                    "visited_owned_tile_indices": [6, 18, 27],
                },
            )()
            result = bridge.choose_coin_placement_tile(state, player)
            self.assertEqual(result, 18)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_coin_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "coin_placement")
            self.assertEqual(resolved.payload.get("choice_id"), "18")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_geo_bonus_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_geo_bonus(self, state, player, actor_name):  # noqa: ANN001
                del state, player, actor_name
                return "cash"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_geo_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 6, "turn_index": 3})()
            player = type("Player", (), {"player_id": 3, "cash": 10, "position": 30, "shards": 6})()
            result = bridge.choose_geo_bonus(state, player, "Surveyor")
            self.assertEqual(result, "cash")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_geo_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 4
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "geo_bonus")
            self.assertEqual(resolved.payload.get("choice_id"), "cash")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_pabal_dice_mode_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_pabal_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 2, "turn_index": 5})()
            player = type("Player", (), {"player_id": 0, "cash": 9, "position": 12, "shards": 8})()
            result = bridge.choose_pabal_dice_mode(state, player)
            self.assertEqual(result, "minus_one")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_pabal_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 1
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "pabal_dice_mode")
            self.assertEqual(resolved.payload.get("choice_id"), "minus_one")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_replaces_inner_ask_with_server_prompt_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_req_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_ready = False
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_ready = "bridge_req_1" in self.prompt_service._pending  # type: ignore[attr-defined]
                if pending_ready:
                    break
                time.sleep(0.01)
            self.assertTrue(pending_ready)

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": "bridge_req_1",
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "roll")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_test"),
                loop,
            ).result(timeout=2.0)
            self.assertTrue(any(msg.type == "prompt" and msg.payload.get("request_id") == "bridge_req_1" for msg in published))
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == "bridge_req_1"
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertEqual(len(resolved_all), 1)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(resolved.payload.get("resolution"), "accepted")
            self.assertEqual(resolved.payload.get("choice_id"), "roll")
            self.assertEqual(requested.payload.get("provider"), "human")
            self.assertEqual(resolved.payload.get("provider"), "human")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_can_raise_prompt_required_without_blocking(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_nonblocking_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )

            with self.assertRaises(PromptRequired) as raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_req_nonblocking_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            self.assertEqual(raised.exception.prompt["request_id"], "bridge_req_nonblocking_1")
            self.assertTrue(self.prompt_service.has_pending_for_session("sess_bridge_nonblocking_test"))
            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_nonblocking_test"),
                loop,
            ).result(timeout=2.0)
            self.assertTrue(any(msg.type == "prompt" and msg.payload.get("request_id") == "bridge_req_nonblocking_1" for msg in published))

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": "bridge_req_nonblocking_1",
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")

            replayed = bridge._inner._ask(  # type: ignore[attr-defined]
                {
                    "request_id": "bridge_req_nonblocking_1",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 2000,
                    "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                    "fallback_policy": "timeout_fallback",
                    "public_context": {},
                },
                lambda response: str(response.get("choice_id", "")),
                lambda: "fallback",
            )
            self.assertEqual(replayed, "roll")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_prompt_sequence_can_resume_from_checkpoint_value(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_prompt_seq_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            bridge.set_prompt_sequence(4)

            with self.assertRaises(PromptRequired) as raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {"round_index": 2, "turn_index": 3},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            prompt = raised.exception.prompt
            self.assertEqual(prompt["prompt_instance_id"], 5)
            self.assertEqual(prompt["request_id"], "sess_bridge_prompt_seq_test:r2:t3:p1:movement:5")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_pending_prompt_replay_reuses_stable_request_id_then_advances_sequence(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_stable_replay_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            checkpoint_state = type(
                "CheckpointState",
                (),
                {
                    "prompt_sequence": 2,
                    "pending_prompt_request_id": "sess_bridge_stable_replay_test:r1:t1:p1:trick_to_use:2",
                    "pending_prompt_instance_id": 2,
                },
            )()
            seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)
            self.assertEqual(seed, 1)
            bridge.set_prompt_sequence(seed)

            trick_prompt = {
                "request_type": "trick_to_use",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "none", "label": "Do not use a trick"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            parse_choice = lambda response: str(response.get("choice_id", ""))

            with self.assertRaises(PromptRequired) as raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                )

            request_id = raised.exception.prompt["request_id"]
            self.assertEqual(request_id, "sess_bridge_stable_replay_test:r1:t1:p1:trick_to_use:2")
            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": request_id,
                    "player_id": 1,
                    "choice_id": "none",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")

            bridge.set_prompt_sequence(seed)
            replayed = bridge._inner._ask(  # type: ignore[attr-defined]
                trick_prompt,
                parse_choice,
                lambda: "fallback",
            )
            self.assertEqual(replayed, "none")

            with self.assertRaises(PromptRequired) as movement_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {"round_index": 1, "turn_index": 1},
                    },
                    parse_choice,
                    lambda: "fallback",
                )

            self.assertEqual(
                movement_raised.exception.prompt["request_id"],
                "sess_bridge_stable_replay_test:r1:t1:p1:movement:3",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_prompt_service_supersedes_older_pending_prompt_for_same_player(self) -> None:
        first = self.prompt_service.create_prompt(
            "sess_prompt_supersede",
            {
                "request_id": "sess_prompt_supersede:r1:t1:p1:trick_to_use:1",
                "request_type": "trick_to_use",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "none", "label": "Skip"}],
            },
        )

        second = self.prompt_service.create_prompt(
            "sess_prompt_supersede",
            {
                "request_id": "sess_prompt_supersede:r1:t1:p1:hidden_trick_card:2",
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "42", "label": "무료 증정"}],
            },
        )

        with self.prompt_service._lock:  # type: ignore[attr-defined]
            pending_ids = set(self.prompt_service._pending)  # type: ignore[attr-defined]
            resolved_ids = set(self.prompt_service._resolved)  # type: ignore[attr-defined]
        self.assertNotIn(first.request_id, pending_ids)
        self.assertIn(first.request_id, resolved_ids)
        self.assertIn(second.request_id, pending_ids)

    def test_pending_movement_replay_replays_prior_trick_prompt_before_movement(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_movement_replay_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            checkpoint_state = type(
                "CheckpointState",
                (),
                {
                    "prompt_sequence": 2,
                    "pending_prompt_request_id": "sess_bridge_movement_replay_test:r1:t1:p1:movement:2",
                    "pending_prompt_type": "movement",
                    "pending_prompt_instance_id": 2,
                },
            )()
            seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)
            self.assertEqual(seed, 0)
            trick_prompt = {
                "request_type": "trick_to_use",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "none", "label": "Do not use a trick"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            movement_prompt = {
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            parse_choice = lambda response: str(response.get("choice_id", ""))

            bridge.set_prompt_sequence(seed)
            with self.assertRaises(PromptRequired) as trick_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                trick_raised.exception.prompt["request_id"],
                "sess_bridge_movement_replay_test:r1:t1:p1:trick_to_use:1",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": trick_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "none",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            with self.assertRaises(PromptRequired) as movement_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    movement_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                movement_raised.exception.prompt["request_id"],
                "sess_bridge_movement_replay_test:r1:t1:p1:movement:2",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": movement_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    movement_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "roll",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_turn_start_mark_prompt_replay_seed_matches_character_rule_cases(self) -> None:
        def make_state(character: str, active_by_card: dict[int, str], request_type: str, instance_id: int):
            player = type(
                "Player",
                (),
                {
                    "player_id": 0,
                    "current_character": character,
                    "shards": 3,
                },
            )()
            return type(
                "CheckpointState",
                (),
                {
                    "prompt_sequence": instance_id,
                    "current_round_order": [0],
                    "turn_index": 0,
                    "players": [player],
                    "active_by_card": active_by_card,
                    "pending_prompt_request_id": (
                        f"sess_mark_rule_seed:r1:t1:p1:{request_type}:{instance_id}"
                    ),
                    "pending_prompt_type": request_type,
                    "pending_prompt_instance_id": instance_id,
                },
            )()

        mark_cases = [
            ("자객", {1: "탐관오리", 2: "자객"}),
            ("산적", {1: "탐관오리", 2: "산적"}),
            ("추노꾼", {1: "탐관오리", 3: "추노꾼"}),
            ("박수", {1: "탐관오리", 6: "박수"}),
            ("만신", {1: "탐관오리", 6: "만신"}),
        ]
        for character, active_by_card in mark_cases:
            with self.subTest(character=character):
                self.assertEqual(
                    self.runtime_service._prompt_sequence_seed_for_transition(
                        make_state(character, active_by_card, "trick_to_use", 2)
                    ),
                    0,
                )
                self.assertEqual(
                    self.runtime_service._prompt_sequence_seed_for_transition(
                        make_state(character, active_by_card, "movement", 3)
                    ),
                    0,
                )

        suppressed_by_eosa_cases = [
            ("자객", {1: "어사", 2: "자객"}),
            ("산적", {1: "어사", 2: "산적"}),
        ]
        for character, active_by_card in suppressed_by_eosa_cases:
            with self.subTest(character=character, eosa=True):
                self.assertEqual(
                    self.runtime_service._prompt_sequence_seed_for_transition(
                        make_state(character, active_by_card, "trick_to_use", 2)
                    ),
                    1,
                )
                self.assertEqual(
                    self.runtime_service._prompt_sequence_seed_for_transition(
                        make_state(character, active_by_card, "movement", 3)
                    ),
                    1,
                )

    def test_turn_start_mark_replay_rewinds_before_pending_trick_and_movement_prompts(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_mark_trick_replay_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            player = type(
                "Player",
                (),
                {
                    "player_id": 0,
                    "current_character": "산적",
                    "shards": 3,
                },
            )()
            checkpoint_base = {
                "prompt_sequence": 2,
                "current_round_order": [0],
                "turn_index": 0,
                "players": [player],
                "active_by_card": {1: "탐관오리", 2: "산적"},
            }
            pending_trick_state = type(
                "CheckpointState",
                (),
                {
                    **checkpoint_base,
                    "pending_prompt_request_id": "sess_bridge_mark_trick_replay_test:r1:t1:p1:trick_to_use:2",
                    "pending_prompt_type": "trick_to_use",
                    "pending_prompt_instance_id": 2,
                },
            )()
            pending_movement_state = type(
                "CheckpointState",
                (),
                {
                    **checkpoint_base,
                    "prompt_sequence": 3,
                    "pending_prompt_request_id": "sess_bridge_mark_trick_replay_test:r1:t1:p1:movement:3",
                    "pending_prompt_type": "movement",
                    "pending_prompt_instance_id": 3,
                },
            )()
            seed = self.runtime_service._prompt_sequence_seed_for_transition(pending_trick_state)
            self.assertEqual(seed, 0)
            self.assertEqual(self.runtime_service._prompt_sequence_seed_for_transition(pending_movement_state), 0)

            mark_prompt = {
                "request_type": "mark_target",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "none", "label": "Do not mark"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            trick_prompt = {
                "request_type": "trick_to_use",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "none", "label": "Do not use a trick"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            movement_prompt = {
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            parse_choice = lambda response: str(response.get("choice_id", ""))

            bridge.set_prompt_sequence(seed)
            with self.assertRaises(PromptRequired) as mark_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    mark_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                mark_raised.exception.prompt["request_id"],
                "sess_bridge_mark_trick_replay_test:r1:t1:p1:mark_target:1",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": mark_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "none",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    mark_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            with self.assertRaises(PromptRequired) as trick_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                trick_raised.exception.prompt["request_id"],
                "sess_bridge_mark_trick_replay_test:r1:t1:p1:trick_to_use:2",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": trick_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "none",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    mark_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            with self.assertRaises(PromptRequired) as movement_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    movement_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                movement_raised.exception.prompt["request_id"],
                "sess_bridge_mark_trick_replay_test:r1:t1:p1:movement:3",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": movement_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    mark_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    trick_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "none",
            )
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    movement_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "roll",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_synced_hidden_trick_continuation_replays_same_movement_prompt(self) -> None:
        checkpoint_state = type(
            "CheckpointState",
            (),
            {
                "prompt_sequence": 7,
                "pending_prompt_request_id": "sess_synced_hidden:r1:t2:p2:movement:7",
                "pending_prompt_type": "movement",
                "pending_prompt_instance_id": 7,
                "pending_actions": [
                    {
                        "type": "continue_after_trick_phase",
                        "payload": {"hidden_trick_synced": True},
                    }
                ],
            },
        )()

        seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)

        self.assertEqual(seed, 6)

    def test_round_start_prompt_replay_rewinds_to_draft_start(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_round_start_replay_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            checkpoint_state = type(
                "CheckpointState",
                (),
                {
                    "prompt_sequence": 2,
                    "pending_prompt_request_id": "sess_bridge_round_start_replay_test:r1:t1:p1:final_character:2",
                    "pending_prompt_type": "final_character",
                    "pending_prompt_instance_id": 2,
                    "current_round_order": [],
                },
            )()
            seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)
            self.assertEqual(seed, 0)

            draft_prompt = {
                "request_type": "draft_card",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "7", "label": "견제자"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            final_prompt = {
                "request_type": "final_character",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "7", "label": "견제자"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            parse_choice = lambda response: str(response.get("choice_id", ""))

            bridge.set_prompt_sequence(seed)
            with self.assertRaises(PromptRequired) as draft_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    draft_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                draft_raised.exception.prompt["request_id"],
                "sess_bridge_round_start_replay_test:r1:t1:p1:draft_card:1",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": draft_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "7",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    draft_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "7",
            )
            with self.assertRaises(PromptRequired) as final_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    final_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                final_raised.exception.prompt["request_id"],
                "sess_bridge_round_start_replay_test:r1:t1:p1:final_character:2",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": final_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "7",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    draft_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "7",
            )
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    final_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "7",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_round_start_prompt_replay_rewinds_even_when_previous_order_remains(self) -> None:
        checkpoint_state = type(
            "CheckpointState",
            (),
            {
                "prompt_sequence": 6,
                "pending_prompt_request_id": "sess_round2_replay:r2:t5:p2:final_character:6",
                "pending_prompt_type": "final_character",
                "pending_prompt_instance_id": 6,
                "current_round_order": [2, 0, 1, 3],
            },
        )()

        seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)

        self.assertEqual(seed, 0)

    def test_round_setup_prompt_replay_clears_stale_round_order(self) -> None:
        checkpoint_state = type(
            "CheckpointState",
            (),
            {
                "pending_prompt_request_id": "sess_round_setup_replay:r1:t1:p1:draft_card:1",
                "pending_prompt_type": "draft_card",
                "current_round_order": [0, 1, 2, 3],
            },
        )()

        RuntimeService._prepare_state_for_transition_replay(checkpoint_state)

        self.assertEqual(checkpoint_state.current_round_order, [])

    def test_round_setup_hidden_trick_replay_rewinds_to_setup_start_when_base_exists(self) -> None:
        checkpoint_state = type(
            "CheckpointState",
            (),
            {
                "prompt_sequence": 3,
                "pending_prompt_request_id": "sess_hidden_setup:r1:t1:p1:hidden_trick_card:3",
                "pending_prompt_type": "hidden_trick_card",
                "pending_prompt_instance_id": 3,
                "current_round_order": [0, 1, 2, 3],
                "round_setup_replay_base": {"tiles": [{"tile_id": 0}], "current_round_order": [0, 1, 2, 3]},
            },
        )()

        seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)
        RuntimeService._prepare_state_for_transition_replay(checkpoint_state)

        self.assertEqual(seed, 0)
        self.assertEqual(checkpoint_state.current_round_order, [])

    def test_round_setup_hidden_trick_without_replay_base_keeps_bridge_replay_seed(self) -> None:
        checkpoint_state = type(
            "CheckpointState",
            (),
            {
                "prompt_sequence": 3,
                "pending_prompt_request_id": "sess_hidden_regular:r1:t1:p1:hidden_trick_card:3",
                "pending_prompt_type": "hidden_trick_card",
                "pending_prompt_instance_id": 3,
                "current_round_order": [0, 1, 2, 3],
            },
        )()

        seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)

        self.assertEqual(seed, 2)
        self.assertEqual(checkpoint_state.current_round_order, [0, 1, 2, 3])

    def test_first_human_draft_resume_auto_resolves_forced_draft_before_final_character(self) -> None:
        store = _MutableGameStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            first = runtime._run_engine_transition_once_sync(
                loop,
                session.session_id,
                42,
                None,
                False,
                None,
                None,
            )
            self.assertEqual(first["status"], "waiting_input")
            self.assertEqual(first["request_type"], "draft_card")
            self.assertEqual(first["player_id"], 1)

            with self.prompt_service._lock:  # type: ignore[attr-defined]
                pending_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            self.prompt_service.submit_decision(
                {
                    "request_id": pending_prompt.request_id,
                    "player_id": 1,
                    "choice_id": pending_prompt.payload["legal_choices"][0]["choice_id"],
                }
            )

            second = runtime._run_engine_transition_once_sync(
                loop,
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

            self.assertEqual(second["status"], "waiting_input")
            self.assertEqual(second["request_type"], "final_character")
            self.assertEqual(second["player_id"], 1)
            self.assertEqual(store.current_state.get("pending_prompt_type"), "final_character")
            self.assertEqual(store.current_state.get("pending_prompt_player_id"), 1)
            self.assertEqual(store.current_state.get("current_round_order"), [])
            with self.prompt_service._lock:  # type: ignore[attr-defined]
                final_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            self.assertEqual(len(final_prompt.payload["legal_choices"]), 2)
            events = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot(session.session_id),
                loop,
            ).result(timeout=2.0)
            turn_starts = [
                msg
                for msg in events
                if msg.type == "event" and msg.payload.get("event_type") == "turn_start"
            ]
            self.assertEqual(turn_starts, [])
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_round_setup_prompt_replay_does_not_republish_previous_draft_events(self) -> None:
        store = _MutableGameStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            runtime._run_engine_transition_once_sync(
                loop,
                session.session_id,
                42,
                None,
                False,
                None,
                None,
            )
            with self.prompt_service._lock:  # type: ignore[attr-defined]
                first_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            self.prompt_service.submit_decision(
                {
                    "request_id": first_prompt.request_id,
                    "player_id": 1,
                    "choice_id": first_prompt.payload["legal_choices"][0]["choice_id"],
                }
            )

            runtime._run_engine_transition_once_sync(
                loop,
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

            messages = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot(session.session_id),
                loop,
            ).result(timeout=2.0)
            events = [msg.payload for msg in messages if msg.type == "event"]
            round_starts = [event for event in events if event.get("event_type") == "round_start"]
            weather_reveals = [event for event in events if event.get("event_type") == "weather_reveal"]
            p1_draft_phase_1 = [
                event
                for event in events
                if event.get("event_type") == "draft_pick"
                and event.get("acting_player_id") == 1
                and event.get("draft_phase") == 1
            ]

            self.assertEqual(len(round_starts), 1)
            self.assertEqual(len(weather_reveals), 1)
            self.assertEqual(len(p1_draft_phase_1), 1)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_pending_hidden_trick_replay_resumes_same_hidden_selection(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_hidden_replay_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            checkpoint_state = type(
                "CheckpointState",
                (),
                {
                    "prompt_sequence": 2,
                    "pending_prompt_request_id": "sess_bridge_hidden_replay_test:r1:t1:p1:hidden_trick_card:2",
                    "pending_prompt_type": "hidden_trick_card",
                    "pending_prompt_instance_id": 2,
                },
            )()
            seed = self.runtime_service._prompt_sequence_seed_for_transition(checkpoint_state)
            self.assertEqual(seed, 1)
            hidden_prompt = {
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "timeout_ms": 2000,
                "legal_choices": [{"choice_id": "42", "label": "호객꾼"}],
                "fallback_policy": "timeout_fallback",
                "public_context": {"round_index": 1, "turn_index": 1},
            }
            parse_choice = lambda response: str(response.get("choice_id", ""))

            bridge.set_prompt_sequence(seed)
            with self.assertRaises(PromptRequired) as hidden_raised:
                bridge._inner._ask(  # type: ignore[attr-defined]
                    hidden_prompt,
                    parse_choice,
                    lambda: "fallback",
                )
            self.assertEqual(
                hidden_raised.exception.prompt["request_id"],
                "sess_bridge_hidden_replay_test:r1:t1:p1:hidden_trick_card:2",
            )
            self.prompt_service.submit_decision(
                {
                    "request_id": hidden_raised.exception.prompt["request_id"],
                    "player_id": 1,
                    "choice_id": "42",
                }
            )

            bridge.set_prompt_sequence(seed)
            self.assertEqual(
                bridge._inner._ask(  # type: ignore[attr-defined]
                    hidden_prompt,
                    parse_choice,
                    lambda: "fallback",
                ),
                "42",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_decision_gateway_uses_canonical_prompt_id_when_context_is_sparse(self) -> None:
        from apps.server.src.services.decision_gateway import DecisionGateway, PromptRequired

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            gateway = DecisionGateway(
                session_id="sess_sparse_prompt_id_test",
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )

            with self.assertRaises(PromptRequired) as raised:
                gateway.resolve_human_prompt(
                    {
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            prompt = raised.exception.prompt
            self.assertEqual(prompt["request_id"], "sess_sparse_prompt_id_test:r0:t0:p1:movement:0")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_keeps_pabal_dice_mode_on_prompt_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            class _FakeAiPolicy:
                def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                    del state, player
                    return "plus_one"

            bridge = _ServerHumanPolicyBridge(
                session_id="sess_human_pabal_bridge",
                human_seats=[0],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 4})()
            player = type("Player", (), {"player_id": 0, "cash": 11, "position": 8, "shards": 8})()
            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge.choose_pabal_dice_mode(state, player)

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_prompt = None
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_prompt = next(iter(self.prompt_service._pending.values()), None)  # type: ignore[attr-defined]
                if pending_prompt:
                    break
                time.sleep(0.01)

            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None
            self.assertEqual(pending_prompt.payload["request_type"], "pabal_dice_mode")
            self.assertEqual(pending_prompt.payload["player_id"], 1)

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": pending_prompt.request_id,
                    "player_id": 1,
                    "choice_id": "minus_one",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "minus_one")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_human_pabal_bridge"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event"
                and (
                    msg.payload.get("request_type") == "pabal_dice_mode"
                    or msg.payload.get("request_id") == pending_prompt.request_id
                )
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "human")
            self.assertEqual(resolved.payload.get("provider"), "human")
            self.assertEqual(requested.payload.get("request_type"), "pabal_dice_mode")
            self.assertEqual(resolved.payload.get("choice_id"), "minus_one")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_mixed_bridge_routes_human_seat_choice_through_human_provider(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def __init__(self) -> None:
                self.calls = 0

            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                self.calls += 1
                return "plus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            ai_policy = _FakeAiPolicy()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_mixed_human_provider",
                human_seats=[0],
                ai_fallback=ai_policy,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 0})()
            player = type("Player", (), {"player_id": 0, "cash": 10, "position": 3, "shards": 4})()
            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge.choose_pabal_dice_mode(state, player)

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_prompt = None
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_prompt = next(iter(self.prompt_service._pending.values()), None)  # type: ignore[attr-defined]
                if pending_prompt is not None:
                    break
                time.sleep(0.01)

            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None
            self.prompt_service.submit_decision(
                {
                    "request_id": pending_prompt.request_id,
                    "player_id": 1,
                    "choice_id": "minus_one",
                }
            )

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "minus_one")
            self.assertEqual(ai_policy.calls, 0)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_mixed_bridge_routes_non_human_seat_choice_through_ai_provider(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def __init__(self) -> None:
                self.calls = 0

            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                self.calls += 1
                return "minus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            ai_policy = _FakeAiPolicy()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_mixed_ai_provider",
                human_seats=[0],
                ai_fallback=ai_policy,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 1})()
            ai_player = type("Player", (), {"player_id": 1, "cash": 9, "position": 6, "shards": 5})()
            choice = bridge.choose_pabal_dice_mode(state, ai_player)

            self.assertEqual(choice, "minus_one")
            self.assertEqual(ai_policy.calls, 1)
            with self.prompt_service._lock:  # type: ignore[attr-defined]
                self.assertEqual(len(self.prompt_service._pending), 0)  # type: ignore[attr-defined]
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_bridge_request_routes_engine_style_request_through_ai_provider(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def __init__(self) -> None:
                self.calls = 0

            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                self.calls += 1
                return "minus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            ai_policy = _FakeAiPolicy()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_bridge_request_ai",
                human_seats=[],
                ai_fallback=ai_policy,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )
            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 9, "position": 12, "shards": 8})()
            request = type(
                "DecisionRequest",
                (),
                {
                    "decision_name": "choose_pabal_dice_mode",
                    "args": (state, player),
                    "kwargs": {},
                },
            )()

            result = bridge.request(request)

            self.assertEqual(result, "minus_one")
            self.assertEqual(ai_policy.calls, 1)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_build_decision_invocation_from_engine_request_restores_state_and_player_prefix(self) -> None:
        state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
        player = type("Player", (), {"player_id": 1, "cash": 9, "position": 12, "shards": 8})()
        request = type(
            "DecisionRequest",
            (),
            {
                "decision_name": "choose_draft_card",
                "state": state,
                "player": player,
                "args": ([3, 7],),
                "kwargs": {},
            },
        )()

        invocation = build_decision_invocation_from_request(request)

        self.assertIs(invocation.state, state)
        self.assertIs(invocation.player, player)
        self.assertEqual(invocation.args, (state, player, [3, 7]))

    def test_bridge_request_routes_engine_style_draft_request_through_ai_provider(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def __init__(self) -> None:
                self.calls: list[tuple[object, object, list[int]]] = []

            def choose_draft_card(self, state, player, offered_cards):  # noqa: ANN001
                self.calls.append((state, player, list(offered_cards)))
                return offered_cards[0]

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            ai_policy = _FakeAiPolicy()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_bridge_request_draft_ai",
                human_seats=[],
                ai_fallback=ai_policy,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )
            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 9, "position": 12, "shards": 8})()
            request = type(
                "DecisionRequest",
                (),
                {
                    "decision_name": "choose_draft_card",
                    "state": state,
                    "player": player,
                    "args": ([5, 8],),
                    "kwargs": {},
                    "fallback_policy": "required",
                },
            )()

            result = bridge.request(request)

            self.assertEqual(result, 5)
            self.assertEqual(ai_policy.calls, [(state, player, [5, 8])])
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_timeout_path_emits_resolved_before_timeout_event(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_timeout",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_timeout_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 50,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "fallback_choice_id": "roll",
                        "public_context": {"round_index": 1, "turn_index": 1},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()
            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "fallback")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_timeout"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == "bridge_timeout_1"
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            timeout_event = next(
                (msg for msg in bridge_events if msg.payload.get("event_type") == "decision_timeout_fallback"),
                None,
            )
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertEqual(len(resolved_all), 1)
            self.assertIsNotNone(timeout_event)
            self.assertLess(requested.seq, resolved.seq)
            self.assertLess(resolved.seq, timeout_event.seq)
            self.assertEqual(resolved.payload.get("resolution"), "timeout_fallback")
            self.assertEqual(requested.payload.get("provider"), "human")
            self.assertEqual(resolved.payload.get("provider"), "human")
            self.assertEqual(timeout_event.payload.get("provider"), "human")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_parser_error_emits_single_parser_fallback_resolution(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_parser_fallback",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_parser_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {"round_index": 1, "turn_index": 2},
                    },
                    lambda _response: (_ for _ in ()).throw(ValueError("parser failure")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_ready = False
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_ready = "bridge_parser_1" in self.prompt_service._pending  # type: ignore[attr-defined]
                if pending_ready:
                    break
                time.sleep(0.01)
            self.assertTrue(pending_ready)

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": "bridge_parser_1",
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")
            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "fallback")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_parser_fallback"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == "bridge_parser_1"
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            self.assertIsNotNone(requested)
            self.assertEqual(len(resolved_all), 1)
            self.assertEqual(resolved_all[0].payload.get("resolution"), "parser_error_fallback")
            self.assertEqual(resolved_all[0].payload.get("choice_id"), "roll")
            self.assertLess(requested.seq, resolved_all[0].seq)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()


class _RecoveryGameStateStoreStub:
    def load_checkpoint(self, session_id: str) -> dict:
        return {
            "schema_version": 1,
            "session_id": session_id,
            "latest_seq": 7,
            "turn_index": 2,
        }

    def load_current_state(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "private_hands": {"1": ["hidden-card"]},
            "turn_index": 2,
        }

    def load_projected_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, player_id
        if viewer == "public":
            return {"players": {"items": []}}
        return {}

    def load_view_state(self, session_id: str) -> dict:
        del session_id
        return {"legacy": True}


class _MutableGameStateStoreStub:
    def __init__(self) -> None:
        self.current_state: dict = {}
        self.checkpoint: dict = {}
        self.commits: list[dict] = []

    def load_checkpoint(self, session_id: str) -> dict | None:
        del session_id
        return copy.deepcopy(self.checkpoint) if self.checkpoint else None

    def load_current_state(self, session_id: str) -> dict | None:
        del session_id
        return copy.deepcopy(self.current_state) if self.current_state else None

    def load_projected_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, viewer, player_id
        return {}

    def load_view_state(self, session_id: str) -> dict:
        del session_id
        return {}

    def commit_transition(
        self,
        session_id: str,
        *,
        current_state: dict,
        checkpoint: dict,
        command_consumer_name: str | None = None,
        command_seq: int | None = None,
        runtime_event_payload: dict | None = None,
        runtime_event_server_time_ms: int | None = None,
    ) -> None:
        self.current_state = copy.deepcopy(current_state)
        self.checkpoint = copy.deepcopy(checkpoint)
        self.commits.append(
            {
                "session_id": session_id,
                "current_state": copy.deepcopy(current_state),
                "checkpoint": copy.deepcopy(checkpoint),
                "command_consumer_name": command_consumer_name,
                "command_seq": command_seq,
                "runtime_event_payload": copy.deepcopy(runtime_event_payload or {}),
                "runtime_event_server_time_ms": runtime_event_server_time_ms,
            }
        )


class _RuntimeStateStoreStub:
    def __init__(self) -> None:
        self.statuses: dict[str, dict] = {}

    def save_status(self, session_id: str, payload: dict) -> None:
        self.statuses[session_id] = dict(payload)

    def load_status(self, session_id: str) -> dict | None:
        payload = self.statuses.get(session_id)
        return dict(payload) if payload is not None else None

    def lease_owner(self, session_id: str) -> str | None:
        del session_id
        return None

    def acquire_lease(self, session_id: str, worker_id: str, ttl_ms: int) -> bool:
        del session_id, worker_id, ttl_ms
        return True

    def refresh_lease(self, session_id: str, worker_id: str, ttl_ms: int) -> bool:
        del session_id, worker_id, ttl_ms
        return True

    def release_lease(self, session_id: str, worker_id: str) -> bool:
        del session_id, worker_id
        return True

    def append_fallback(self, session_id: str, record: dict, *, max_items: int = 20) -> None:
        del session_id, record, max_items

    def recent_fallbacks(self, session_id: str, limit: int = 10) -> list[dict]:
        del session_id, limit
        return []

    def delete_session_data(self, session_id: str) -> None:
        self.statuses.pop(session_id, None)


if __name__ == "__main__":
    unittest.main()
