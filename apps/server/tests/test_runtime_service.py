from __future__ import annotations

import asyncio
import socket
import threading
import time
import unittest
from unittest.mock import patch

from apps.server.src.services.decision_gateway import (
    build_decision_invocation,
    build_canonical_decision_request,
    build_routed_decision_call,
    build_public_context,
    decision_request_type_for_method,
    serialize_ai_choice_id,
)
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.prompt_service import PromptService


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
                "tile_index": 9,
                "cost": 4,
                "source": "landing",
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
                "one_short_pos": 25,
                "bonus_target_pos": 26,
                "bonus_target_kind": "S",
            },
        )

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
        finally:
            server.should_exit = True
            thread.join(timeout=5.0)

    def test_http_external_transport_reaches_real_priority_worker_over_localhost(self) -> None:
        try:
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


if __name__ == "__main__":
    unittest.main()
