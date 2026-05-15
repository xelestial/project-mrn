from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import warnings
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.server.src.domain.protocol_identity import assert_no_public_identity_numeric_leaks
from apps.server.src.services.decision_gateway import (
    build_decision_invocation,
    build_decision_invocation_from_request,
    build_canonical_decision_request,
    build_routed_decision_call,
    build_public_context,
    decision_request_type_for_method,
    serialize_ai_choice_id,
)
from apps.server.src.services.prompt_boundary_builder import PromptBoundaryBuilder
from apps.server.src.services.prompt_fingerprint import ensure_prompt_fingerprint, prompt_fingerprint_mismatch
from apps.server.src.services.runtime_service import RuntimeDecisionResume, RuntimeService
from apps.server.src.services.runtime_service import _LocalHumanDecisionClient
from apps.server.src.services.command_boundary_store import CommandBoundaryGameStateStore
from apps.server.src.services.runtime_service import (
    _FanoutVisEventStream,
    _runtime_frame_type_from_frame_id,
    _run_runtime_stream_task_sync,
    _schedule_runtime_stream_task,
    _runtime_failure_diagnostics,
    _runtime_continuation_debug_fields,
    _runtime_module_debug_fields,
    _sync_state_prompt_request_id,
    _snapshot_pulse_specs_from_source_messages,
    resolve_runtime_runner_kind,
    runtime_checkpoint_schema_version_for_runner,
)
from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.infra.game_debug_log import debug_game_log_run_dir
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.realtime_persistence import ViewCommitSequenceConflict
from apps.server.src.services.session_loop import SessionCommandExecutor
from runtime_modules.contracts import FrameState, ModuleRef
from runtime_modules.prompts import PromptApi
from runtime_modules.simultaneous import build_resupply_frame


WEBSOCKETS_DEPRECATION_MESSAGE = "websockets\\." + "leg" + "acy is deprecated.*"


pytestmark = [
    pytest.mark.filterwarnings(f"ignore:{WEBSOCKETS_DEPRECATION_MESSAGE}:DeprecationWarning"),
    pytest.mark.filterwarnings(
        "ignore:websockets\\.server\\.WebSocketServerProtocol is deprecated:DeprecationWarning"
    ),
]

warnings.filterwarnings(
    "ignore",
    message=WEBSOCKETS_DEPRECATION_MESSAGE,
    category=DeprecationWarning,
)


class SnapshotPulseSpecTests(unittest.TestCase):
    def test_round_and_turn_start_events_create_guardrail_pulses(self) -> None:
        specs = _snapshot_pulse_specs_from_source_messages(
            [
                {
                    "type": "event",
                    "seq": 1,
                    "payload": {"event_type": "round_start", "round_index": 2},
                },
                {
                    "type": "event",
                    "seq": 2,
                    "payload": {"event_type": "turn_start", "acting_player_id": 3},
                },
            ],
            after_seq=0,
        )

        self.assertEqual(
            specs,
            [
                {"reason": "round_start_guardrail", "target_player_id": None},
                {"reason": "turn_start_guardrail", "target_player_id": 3},
            ],
        )

    def test_snapshot_pulse_specs_ignore_old_source_events_and_non_events(self) -> None:
        specs = _snapshot_pulse_specs_from_source_messages(
            [
                {
                    "type": "event",
                    "seq": 3,
                    "payload": {"event_type": "round_start", "round_index": 2},
                },
                {
                    "type": "snapshot_pulse",
                    "seq": 4,
                    "payload": {"reason": "round_start_guardrail"},
                },
                {
                    "type": "event",
                    "seq": 5,
                    "payload": {"event_type": "turn_start", "player_id": 2},
                },
            ],
            after_seq=3,
        )

        self.assertEqual(specs, [{"reason": "turn_start_guardrail", "target_player_id": 2}])
warnings.filterwarnings(
    "ignore",
    message="websockets\\.server\\.WebSocketServerProtocol is deprecated",
    category=DeprecationWarning,
)


class RuntimeEngineExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_executor_limits_concurrent_engine_work(self) -> None:
        runtime = RuntimeService(
            session_service=SessionService(),
            stream_service=StreamService(),
            prompt_service=PromptService(),
            runtime_engine_workers=1,
        )
        started: list[str] = []
        first_entered = threading.Event()
        release_first = threading.Event()

        def blocking_transition(label: str) -> str:
            started.append(label)
            if label == "first":
                first_entered.set()
                release_first.wait(timeout=2.0)
            return label

        try:
            first = asyncio.create_task(runtime._run_in_runtime_executor(blocking_transition, "first"))
            deadline = time.monotonic() + 2.0
            while not first_entered.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            self.assertTrue(first_entered.is_set())

            second = asyncio.create_task(runtime._run_in_runtime_executor(blocking_transition, "second"))
            await asyncio.sleep(0.05)
            self.assertEqual(started, ["first"])

            release_first.set()
            self.assertEqual(await first, "first")
            self.assertEqual(await second, "second")
            self.assertEqual(started, ["first", "second"])
        finally:
            release_first.set()
            runtime._runtime_executor.shutdown(wait=True, cancel_futures=True)


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

    def _create_started_two_player_session(self):
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        return self.session_service.start_session(session.session_id, session.host_token)

    def test_builds_recoverable_batch_prompt_view_state_from_checkpoint(self) -> None:
        checkpoint_payload = {
            "players": [{"player_id": 1}, {"player_id": 2}],
            "runtime_active_prompt_batch": {
                "batch_id": "batch:simul:resupply:1:13:mod:resupply:1",
                "request_type": "burden_exchange",
                "missing_player_ids": [0, 1],
                "resume_tokens_by_player_id": {"0": "resume_p1", "1": "resume_p2"},
                "prompts_by_player_id": {
                    "0": {
                        "request_id": "batch:simul:resupply:1:13:mod:resupply:1:p0",
                        "request_type": "burden_exchange",
                        "prompt_instance_id": 31,
                        "resume_token": "resume_p1",
                        "frame_id": "simul:resupply:1:13",
                        "module_id": "mod:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                        "legal_choices": [{"choice_id": "no", "title": "교환 안 함"}],
                        "public_context": {"card_name": "무거운 짐"},
                    }
                },
            },
        }
        active_module = {
            "runner_kind": "module",
            "frame_id": "simul:resupply:1:13",
            "frame_type": "simultaneous",
            "module_id": "mod:resupply",
            "module_type": "ResupplyModule",
            "module_cursor": "await_resupply_batch:1",
        }

        prompt_view = self.runtime_service._build_prompt_view_state_for_viewer(
            checkpoint_payload=checkpoint_payload,
            viewer={"role": "seat", "player_id": 1},
            active_module=active_module,
            commit_seq=77,
        )

        active = prompt_view["active"]
        self.assertEqual(active["player_id"], 1)
        self.assertEqual(active["commit_seq"], 77)
        self.assertEqual(active["runner_kind"], "module")
        self.assertEqual(active["prompt_instance_id"], 31)
        self.assertEqual(active["batch_id"], "batch:simul:resupply:1:13:mod:resupply:1")
        self.assertEqual(active["missing_player_ids"], [1, 2])
        self.assertEqual(active["resume_tokens_by_player_id"], {"1": "resume_p1", "2": "resume_p2"})

    def test_single_prompt_view_prefers_canonical_pending_request_id(self) -> None:
        legacy_request_id = "sess_test:prompt:frame:round%3A1:module:mod%3Around%3A1:cursor:draft%3Apick%3A1:p1:draft_card:2"
        public_request_id = "req_public_prompt_2"
        checkpoint_payload = {
            "players": [{"player_id": 1}, {"player_id": 2}],
            "pending_prompt_request_id": public_request_id,
            "pending_prompt_type": "draft_card",
            "pending_prompt_player_id": 2,
            "pending_prompt_instance_id": 2,
            "runtime_active_prompt": {
                "request_id": legacy_request_id,
                "request_type": "draft_card",
                "player_id": 1,
                "prompt_instance_id": 2,
                "resume_token": "resume_p2",
                "frame_id": "round:1",
                "module_id": "mod:round:1:draft",
                "module_type": "DraftModule",
                "module_cursor": "draft:pick:1:p1",
                "legal_choices": [{"choice_id": "card:2", "title": "Card 2"}],
            },
        }
        active_module = {
            "runner_kind": "module",
            "frame_id": "round:1",
            "frame_type": "round",
            "module_id": "mod:round:1:draft",
            "module_type": "DraftModule",
            "module_cursor": "draft:pick:1:p1",
        }

        prompt_view = self.runtime_service._build_prompt_view_state_for_viewer(
            checkpoint_payload=checkpoint_payload,
            viewer={"role": "seat", "player_id": 2},
            active_module=active_module,
            commit_seq=88,
        )

        active = prompt_view["active"]
        self.assertEqual(active["request_id"], public_request_id)
        self.assertEqual(active["legacy_request_id"], legacy_request_id)

    def test_sync_state_prompt_request_id_updates_matching_active_prompt(self) -> None:
        state = SimpleNamespace(
            pending_prompt_request_id="legacy_request",
            runtime_active_prompt=SimpleNamespace(request_id="legacy_request", prompt_instance_id=7),
            runtime_active_prompt_batch=None,
        )

        _sync_state_prompt_request_id(
            state,
            {"request_id": "req_public_7", "prompt_instance_id": 7},
        )

        self.assertEqual(state.pending_prompt_request_id, "req_public_7")
        self.assertEqual(state.runtime_active_prompt.request_id, "req_public_7")

    @staticmethod
    def _module_prompt(
        payload: dict,
        *,
        frame_id: str = "turn:1:p0",
        module_id: str = "mod:turn:1:p0:test_prompt",
        module_type: str = "DiceRollModule",
        module_cursor: str = "test:await_choice",
        resume_token: str = "resume_test_prompt",
    ) -> dict:
        prompt = dict(payload)
        prompt.update(
            {
                "runner_kind": "module",
                "resume_token": resume_token,
                "frame_id": frame_id,
                "module_id": module_id,
                "module_type": module_type,
                "module_cursor": module_cursor,
                "runtime_module": {
                    "runner_kind": "module",
                    "frame_type": _runtime_frame_type_from_frame_id(frame_id),
                    "frame_id": frame_id,
                    "module_id": module_id,
                    "module_type": module_type,
                    "module_cursor": module_cursor,
                },
            }
        )
        return prompt

    @staticmethod
    def _module_decision(prompt: dict, choice_id: str, *, player_id: int | None = None) -> dict:
        decision = {
            "request_id": prompt["request_id"],
            "player_id": int(player_id if player_id is not None else prompt.get("player_id", 0)),
            "choice_id": str(choice_id),
            "resume_token": prompt["resume_token"],
            "frame_id": prompt["frame_id"],
            "module_id": prompt["module_id"],
            "module_type": prompt["module_type"],
            "module_cursor": prompt["module_cursor"],
        }
        return decision

    def _assert_public_prompt_request_id(self, prompt: dict, legacy_request_id: str) -> str:
        public_request_id = str(prompt.get("request_id") or "")
        self.assertTrue(public_request_id.startswith("req_"))
        self.assertEqual(prompt.get("public_request_id"), public_request_id)
        self.assertEqual(prompt.get("legacy_request_id"), legacy_request_id)
        self.assertNotEqual(public_request_id, legacy_request_id)
        return public_request_id

    def test_checkpoint_prompt_boundary_normalizes_sequence_frame_type(self) -> None:
        payload = RuntimeService._prompt_boundary_payload_from_continuation(
            {
                "request_id": "req_seq_prompt",
                "request_type": "trick_to_use",
                "player_id": 0,
                "prompt_instance_id": 11,
                "resume_token": "resume_seq_prompt",
                "frame_id": "seq:trick:1:p0:15",
                "module_id": "mod:seq:trick:1:p0:15:choice",
                "module_type": "TrickChoiceModule",
                "module_cursor": "trick_choice:await_choice",
                "legal_choices": [{"choice_id": "skip"}],
            },
            player_id=1,
            batch_payload=None,
        )

        self.assertEqual(payload["runtime_module"]["frame_type"], "sequence")

    @staticmethod
    def _module_state(
        *,
        rounds_completed: int = 0,
        turn_index: int = 0,
        frame_id: str = "turn:1:p0",
        module_id: str = "mod:turn:1:p0:test_prompt",
        module_type: str = "DiceRollModule",
        module_cursor: str = "test:await_choice",
        **attrs,
    ):
        state = type("State", (), {"rounds_completed": rounds_completed, "turn_index": turn_index, **attrs})()
        frame_type = _runtime_frame_type_from_frame_id(frame_id)
        owner_player_id = None if frame_type in {"round", "simultaneous"} else 0
        module = ModuleRef(
            module_id=module_id,
            module_type=module_type,
            phase="test_prompt",
            owner_player_id=owner_player_id,
            status="suspended",
            cursor=module_cursor,
            suspension_id=f"suspend:{module_id}",
        )
        state.runtime_runner_kind = "module"
        state.runtime_frame_stack = [
            FrameState(
                frame_id=frame_id,
                frame_type=frame_type,
                owner_player_id=owner_player_id,
                parent_frame_id=None,
                status="suspended",
                active_module_id=module_id,
                module_queue=[module],
            )
        ]
        state.runtime_active_prompt = None
        state.runtime_active_prompt_batch = None
        return state

    def test_runtime_runner_defaults_to_module_for_live_sessions(self) -> None:
        self.assertEqual(resolve_runtime_runner_kind({}, RuntimeSettings()), "module")
        self.assertEqual(
            resolve_runtime_runner_kind(
                {"flags": {"module_metadata_v1": True}},
                RuntimeSettings(),
            ),
            "module",
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

    def test_has_unprocessed_runtime_commands_checks_consumer_offset(self) -> None:
        command_store = _CommandStoreStub(
            offset=1,
            commands=[
                {"seq": 1, "type": "decision_submitted"},
                {"seq": 2, "type": "decision_resolved"},
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )

        self.assertTrue(runtime.has_unprocessed_runtime_commands("sess_pending"))

        command_store.offset = 2

        self.assertFalse(runtime.has_unprocessed_runtime_commands("sess_pending"))

    def test_pending_resume_command_ignores_consumed_offset_command(self) -> None:
        command_store = _CommandStoreStub(
            offset=7,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": "sess_1:r1:t1:p1:final_character:1",
                        "choice_id": "mansin",
                        "frame_id": "turn:1:p0",
                        "module_id": "mod:turn:1:p0:draft",
                        "module_type": "DraftModule",
                        "module_cursor": "final_character:1",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": "sess_1:r1:t1:p1:final_character:1",
                "active_frame_id": "turn:1:p0",
                "active_module_id": "mod:turn:1:p0:draft",
                "active_module_type": "DraftModule",
                "active_module_cursor": "final_character:1",
            },
            "current_state": {},
        }

        command = runtime.pending_resume_command("sess_1")

        self.assertIsNone(command)

    def test_pending_resume_command_returns_unconsumed_matching_command(self) -> None:
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": "sess_1:r1:t1:p1:final_character:1",
                        "choice_id": "mansin",
                        "frame_id": "turn:1:p0",
                        "module_id": "mod:turn:1:p0:draft",
                        "module_type": "DraftModule",
                        "module_cursor": "final_character:1",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": "sess_1:r1:t1:p1:final_character:1",
                "active_frame_id": "turn:1:p0",
                "active_module_id": "mod:turn:1:p0:draft",
                "active_module_type": "DraftModule",
                "active_module_cursor": "final_character:1",
            },
            "current_state": {},
        }

        command = runtime.pending_resume_command("sess_1")

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command["seq"], 7)

    def test_pending_resume_command_returns_unconsumed_matching_batch_command(self) -> None:
        request_id = "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p0"
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "player_id": 1,
                        "choice_id": "yes",
                        "frame_id": "simul:resupply:1:95",
                        "module_id": "mod:simul:resupply:1:95:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": "",
                "active_frame_id": "simul:resupply:1:95",
                "active_module_id": "mod:simul:resupply:1:95:resupply",
                "active_module_type": "ResupplyModule",
                "active_module_cursor": "await_resupply_batch:1",
                "runtime_active_prompt_batch": {
                    "batch_id": "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
                    "missing_player_ids": [0, 1],
                    "prompts_by_player_id": {
                        "0": {
                            "request_id": request_id,
                            "frame_id": "simul:resupply:1:95",
                            "module_id": "mod:simul:resupply:1:95:resupply",
                            "module_type": "ResupplyModule",
                            "module_cursor": "await_resupply_batch:1",
                        },
                        "1": {
                            "request_id": (
                                "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p1"
                            ),
                            "frame_id": "simul:resupply:1:95",
                            "module_id": "mod:simul:resupply:1:95:resupply",
                            "module_type": "ResupplyModule",
                            "module_cursor": "await_resupply_batch:1",
                        },
                    },
                },
            },
            "current_state": {},
        }

        command = runtime.pending_resume_command("sess_1")

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command["seq"], 7)

    def test_pending_resume_command_ignores_resolved_batch_request(self) -> None:
        request_id = "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p0"
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "player_id": 1,
                        "choice_id": "yes",
                        "frame_id": "simul:resupply:1:95",
                        "module_id": "mod:simul:resupply:1:95:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                    },
                },
                {
                    "seq": 8,
                    "type": "decision_resolved",
                    "payload": {"request_id": request_id},
                },
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "runtime_active_prompt_batch": {
                    "missing_player_ids": [0],
                    "prompts_by_player_id": {
                        "0": {
                            "request_id": request_id,
                            "frame_id": "simul:resupply:1:95",
                            "module_id": "mod:simul:resupply:1:95:resupply",
                            "module_type": "ResupplyModule",
                            "module_cursor": "await_resupply_batch:1",
                        }
                    },
                },
                "active_frame_id": "simul:resupply:1:95",
                "active_module_id": "mod:simul:resupply:1:95:resupply",
                "active_module_type": "ResupplyModule",
                "active_module_cursor": "await_resupply_batch:1",
            },
            "current_state": {},
        }

        command = runtime.pending_resume_command("sess_1")

        self.assertIsNone(command)

    def test_pending_resume_command_uses_runtime_active_prompt_request_id(self) -> None:
        request_id = "sess_1:r2:t9:p4:active_flip:120"
        command_store = _CommandStoreStub(
            offset=61,
            commands=[
                {
                    "seq": 62,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "player_id": 3,
                        "choice_id": "none",
                        "frame_id": "round:2",
                        "module_id": "mod:round:2:roundendcardflip",
                        "module_type": "RoundEndCardFlipModule",
                        "module_cursor": "start",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": "",
                "runtime_active_prompt": {
                    "request_id": request_id,
                    "player_id": 3,
                    "frame_id": "round:2",
                    "module_id": "mod:round:2:roundendcardflip",
                    "module_type": "RoundEndCardFlipModule",
                    "module_cursor": "start",
                },
                "active_frame_id": "round:2",
                "active_module_id": "mod:round:2:roundendcardflip",
                "active_module_type": "RoundEndCardFlipModule",
                "active_module_cursor": "start",
            },
            "current_state": {},
        }

        command = runtime.pending_resume_command("sess_1")

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command["seq"], 62)

    def test_resolved_timeout_fallback_command_can_resume_waiting_checkpoint(self) -> None:
        request_id = "sess_1:r2:t9:p4:active_flip:120"
        command_store = _CommandStoreStub(
            offset=61,
            commands=[
                {
                    "seq": 62,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "player_id": 3,
                        "choice_id": "none",
                        "source": "timeout_fallback",
                        "decision": {
                            "request_id": request_id,
                            "choice_id": "none",
                            "provider": "timeout_fallback",
                            "frame_id": "round:2",
                            "module_id": "mod:round:2:roundendcardflip",
                            "module_type": "RoundEndCardFlipModule",
                            "module_cursor": "start",
                        },
                    },
                },
                {
                    "seq": 63,
                    "type": "decision_resolved",
                    "payload": {"request_id": request_id},
                },
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "runtime_active_prompt": {
                    "request_id": request_id,
                    "player_id": 3,
                    "frame_id": "round:2",
                    "module_id": "mod:round:2:roundendcardflip",
                    "module_type": "RoundEndCardFlipModule",
                    "module_cursor": "start",
                },
                "active_frame_id": "round:2",
                "active_module_id": "mod:round:2:roundendcardflip",
                "active_module_type": "RoundEndCardFlipModule",
                "active_module_cursor": "start",
            },
            "current_state": {},
        }

        pending = runtime.pending_resume_command("sess_1")
        matching = runtime._matching_resume_command_for_seq("sess_1", 62)

        self.assertIsNotNone(pending)
        self.assertIsNotNone(matching)
        assert pending is not None
        assert matching is not None
        self.assertEqual(pending["seq"], 62)
        self.assertEqual(matching["seq"], 62)

    def test_runtime_runner_ignores_classic_override_after_cutover(self) -> None:
        self.assertEqual(resolve_runtime_runner_kind({"runner_kind": "module"}, RuntimeSettings()), "module")
        self.assertEqual(resolve_runtime_runner_kind({"runner_kind": "classic"}, RuntimeSettings()), "module")
        self.assertEqual(resolve_runtime_runner_kind({"runtime_runner_kind": "classic"}, RuntimeSettings()), "module")
        self.assertEqual(runtime_checkpoint_schema_version_for_runner("classic"), 3)

    def test_runtime_service_has_no_engine_replay_hooks(self) -> None:
        source = Path("apps/server/src/services/runtime_service.py").read_text(encoding="utf-8")

        self.assertNotIn("_run_" + "leg" + "acy_engine_sync", source)
        self.assertNotIn("_prompt_sequence_seed_for_transition", source)
        self.assertNotIn("_prepare_state_for_transition_replay", source)
        self.assertNotIn("_checkpoint_payload_for_transition_replay", source)

    def test_runtime_module_debug_fields_flatten_step_and_payload_metadata(self) -> None:
        fields = _runtime_module_debug_fields(
            {
                "runner_kind": "module",
                "module_type": "MapMoveModule",
                "frame_id": "seq:roll_and_arrive:1:p0:1",
                "runtime_module": {
                    "runner_kind": "module",
                    "module_id": "mod:seq:roll_and_arrive:1:p0:1:mapmove",
                    "module_type": "MapMoveModule",
                    "idempotency_key": "idem:move",
                },
            }
        )

        self.assertEqual(
            fields,
            {
                "runner_kind": "module",
                "module_type": "MapMoveModule",
                "module_id": "mod:seq:roll_and_arrive:1:p0:1:mapmove",
                "frame_id": "seq:roll_and_arrive:1:p0:1",
                "idempotency_key": "idem:move",
            },
        )

    def test_runtime_module_debug_fields_fills_active_module_from_state(self) -> None:
        active_module = type(
            "Module",
            (),
            {
                "module_id": "mod:turn:1:p0:movement",
                "module_type": "MapMoveModule",
                "idempotency_key": "idem:movement",
            },
        )()
        inactive_module = type(
            "Module",
            (),
            {
                "module_id": "mod:turn:1:p0:dice",
                "module_type": "DiceRollModule",
                "idempotency_key": "idem:dice",
            },
        )()
        active_frame = type(
            "Frame",
            (),
            {
                "frame_id": "turn:1:p0",
                "active_module_id": "mod:turn:1:p0:movement",
                "module_queue": [inactive_module, active_module],
            },
        )()
        state = type(
            "State",
            (),
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [active_frame],
            },
        )()

        fields = _runtime_module_debug_fields({"status": "committed"}, state)

        self.assertEqual(
            fields,
            {
                "runner_kind": "module",
                "module_type": "MapMoveModule",
                "module_id": "mod:turn:1:p0:movement",
                "frame_id": "turn:1:p0",
                "idempotency_key": "idem:movement",
            },
        )

    def test_active_module_from_checkpoint_does_not_promote_queued_module(self) -> None:
        checkpoint = {
            "runtime_runner_kind": "module",
            "runtime_frame_stack": [
                {
                    "frame_id": "round:4",
                    "frame_type": "round",
                    "status": "suspended",
                    "active_module_id": "mod:round:4:p3",
                    "module_queue": [
                        {
                            "module_id": "mod:round:4:p3",
                            "module_type": "PlayerTurnModule",
                            "status": "suspended",
                            "cursor": "child_turn_running",
                        }
                    ],
                },
                {
                    "frame_id": "turn:4:p3",
                    "frame_type": "turn",
                    "status": "running",
                    "active_module_id": "",
                    "module_queue": [
                        {
                            "module_id": "mod:turn:4:p3:targetjudicator",
                            "module_type": "TargetJudicatorModule",
                            "status": "completed",
                        },
                        {
                            "module_id": "mod:turn:4:p3:trickwindow",
                            "module_type": "TrickWindowModule",
                            "status": "queued",
                        },
                    ],
                },
            ],
        }

        active = self.runtime_service._active_runtime_module_from_checkpoint(checkpoint, {})

        self.assertEqual(active["frame_id"], "round:4")
        self.assertEqual(active["module_type"], "PlayerTurnModule")
        self.assertEqual(active["module_status"], "suspended")
        self.assertNotEqual(active["module_type"], "TrickWindowModule")

    def test_runtime_failure_diagnostics_fill_empty_exception_message(self) -> None:
        try:
            raise RuntimeError()
        except RuntimeError as exc:
            diagnostics = _runtime_failure_diagnostics("sess_empty_error", exc)

        self.assertEqual(diagnostics["session_id"], "sess_empty_error")
        self.assertEqual(diagnostics["error"], "Runtime execution failed")
        self.assertEqual(diagnostics["exception_type"], "RuntimeError")
        self.assertEqual(diagnostics["exception_repr"], "RuntimeError()")
        self.assertIn("RuntimeError", diagnostics["traceback"])

    def test_runtime_stream_side_effect_scheduler_does_not_block_on_future_result(self) -> None:
        callbacks = []

        class FutureStub:
            def add_done_callback(self, callback) -> None:
                callbacks.append(callback)

            def result(self, timeout=None):  # pragma: no cover - called only if the scheduler regresses.
                raise AssertionError("stream side-effect scheduler must not block on result")

        async def publish_later():
            return None

        def fake_run_coroutine_threadsafe(coro, loop):
            coro.close()
            return FutureStub()

        with patch(
            "apps.server.src.services.runtime_service.asyncio.run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ):
            _schedule_runtime_stream_task(
                object(),
                "sess_side_effect",
                "runtime_view_commit_emit_failed",
                publish_later,
            )

        self.assertEqual(len(callbacks), 1)

    def test_runtime_stream_sync_task_cancels_on_timeout(self) -> None:
        cancelled = False

        class FutureStub:
            def result(self, timeout=None):
                raise TimeoutError()

            def cancel(self) -> None:
                nonlocal cancelled
                cancelled = True

        async def publish_later():
            return None

        def fake_run_coroutine_threadsafe(coro, loop):
            coro.close()
            return FutureStub()

        with patch(
            "apps.server.src.services.runtime_service.asyncio.run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ):
            ok = _run_runtime_stream_task_sync(
                object(),
                "sess_timeout",
                "runtime_view_commit_emit_failed",
                publish_later,
                timeout=0.1,
            )

        self.assertFalse(ok)
        self.assertTrue(cancelled)

    def test_runtime_stream_sync_task_retries_transient_timeout(self) -> None:
        attempts = 0
        cancelled = 0

        class FutureStub:
            def __init__(self, attempt: int) -> None:
                self._attempt = attempt

            def result(self, timeout=None):
                if self._attempt == 1:
                    raise TimeoutError()
                return None

            def cancel(self) -> None:
                nonlocal cancelled
                cancelled += 1

        async def publish_later():
            return None

        def fake_run_coroutine_threadsafe(coro, loop):
            nonlocal attempts
            attempts += 1
            coro.close()
            return FutureStub(attempts)

        with patch(
            "apps.server.src.services.runtime_service.asyncio.run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ), patch("apps.server.src.services.runtime_service.log_event") as log_event:
            ok = _run_runtime_stream_task_sync(
                object(),
                "sess_retry_timeout",
                "runtime_prompt_publish_failed",
                publish_later,
                timeout=0.1,
                attempts=2,
            )

        self.assertTrue(ok)
        self.assertEqual(attempts, 2)
        self.assertEqual(cancelled, 1)
        log_event.assert_not_called()

    def test_redis_backed_view_commit_emit_is_scheduled_without_blocking_runtime(self) -> None:
        callbacks = []

        class BackendStub:
            pass

        class StreamStub:
            _stream_backend = BackendStub()

            async def emit_latest_view_commit(self, session_id: str):
                return None

        class FutureStub:
            def add_done_callback(self, callback) -> None:
                callbacks.append(callback)

            def result(self, timeout=None):  # pragma: no cover - called only if scheduling regresses.
                raise AssertionError("redis-backed view_commit emit must not block runtime progress")

        def fake_run_coroutine_threadsafe(coro, loop):
            coro.close()
            return FutureStub()

        self.runtime_service._stream_service = StreamStub()
        with patch(
            "apps.server.src.services.runtime_service.asyncio.run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ):
            self.runtime_service._emit_latest_view_commit_sync(object(), "sess_stream_backend")

        self.assertEqual(len(callbacks), 1)

    def test_round_and_turn_snapshot_guardrails_emit_after_latest_view_commit(self) -> None:
        calls: list[tuple[str, str | None, int | None]] = []

        class StreamStub:
            async def emit_latest_view_commit(self, session_id: str):
                calls.append(("view_commit", session_id, None))
                return None

            async def emit_snapshot_pulse(
                self,
                session_id: str,
                *,
                reason: str,
                target_player_id: int | None = None,
            ):
                calls.append((reason, session_id, target_player_id))
                return None

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            self.runtime_service._stream_service = StreamStub()
            self.runtime_service._emit_latest_view_commit_sync(loop, "sess_guardrail_order")
            self.runtime_service._emit_snapshot_pulses_sync(
                loop,
                "sess_guardrail_order",
                [
                    {"reason": "round_start_guardrail", "target_player_id": None},
                    {"reason": "turn_start_guardrail", "target_player_id": 2},
                ],
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

        self.assertEqual(
            calls,
            [
                ("view_commit", "sess_guardrail_order", None),
                ("round_start_guardrail", "sess_guardrail_order", None),
                ("turn_start_guardrail", "sess_guardrail_order", 2),
            ],
        )

    def test_redis_backed_prompt_boundary_publish_is_scheduled_without_blocking_runtime(self) -> None:
        callbacks = []

        class BackendStub:
            pass

        class StreamStub:
            _stream_backend = BackendStub()

            async def publish(self, session_id: str, message_type: str, payload: dict):
                return {"seq": 1, "type": message_type, "payload": payload}

        class FutureStub:
            def add_done_callback(self, callback) -> None:
                callbacks.append(callback)

            def result(self, timeout=None):  # pragma: no cover - called only if scheduling regresses.
                raise AssertionError("redis-backed prompt publish must not block runtime progress")

        def fake_run_coroutine_threadsafe(coro, loop):
            coro.close()
            return FutureStub()

        self.runtime_service._stream_service = StreamStub()
        with patch(
            "apps.server.src.services.runtime_service.asyncio.run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ):
            self.runtime_service._materialize_prompt_boundary_sync(
                object(),
                "sess_prompt_backend",
                {
                    "request_id": "req_prompt_backend",
                    "request_type": "roll",
                    "player_id": 1,
                    "timeout_ms": 30000,
                    "legal_choices": [{"choice_id": "roll"}],
                },
            )

        self.assertEqual(len(callbacks), 2)

    def test_redis_backed_stream_history_reads_do_not_require_event_loop(self) -> None:
        class BackendStub:
            def latest_seq(self, session_id: str) -> int:
                self.latest_session_id = session_id
                return 42

            def source_snapshot(self, session_id: str, through_seq: int | None = None) -> list[dict]:
                self.source_args = (session_id, through_seq)
                return [{"seq": 41, "type": "event", "payload": {"event_type": "turn_start"}}]

        class StreamStub:
            def __init__(self) -> None:
                self._stream_backend = BackendStub()

        service = RuntimeService(
            session_service=self.session_service,
            stream_service=StreamStub(),
            prompt_service=self.prompt_service,
        )

        self.assertEqual(service._latest_stream_seq_sync(None, "sess_backend"), 42)  # type: ignore[attr-defined]
        self.assertEqual(
            service._source_history_sync(None, "sess_backend", 42),  # type: ignore[attr-defined]
            [{"seq": 41, "type": "event", "payload": {"event_type": "turn_start"}}],
        )

    def test_current_actor_prefers_active_turn_frame_owner(self) -> None:
        checkpoint = {
            "turn_index": 14,
            "current_round_order": [1, 2, 3, 0],
            "runtime_frame_stack": [
                {
                    "frame_id": "round:4",
                    "frame_type": "round",
                    "status": "suspended",
                    "active_module_id": "mod:round:4:p3",
                    "module_queue": [],
                },
                {
                    "frame_id": "turn:4:p3",
                    "frame_type": "turn",
                    "owner_player_id": 3,
                    "status": "running",
                    "active_module_id": "",
                    "module_queue": [],
                },
            ],
        }

        self.assertEqual(self.runtime_service._current_actor_player_id(checkpoint), 4)

    def test_runtime_continuation_debug_fields_trace_ids_without_resume_token(self) -> None:
        resume = type(
            "Resume",
            (),
            {
                "request_id": "req:trick:7",
                "request_type": "trick_to_use",
                "player_id": 2,
                "choice_id": "card:11",
                "resume_token": "secret-resume-token",
                "frame_id": "seq:trick:7:p2",
                "module_id": "mod:seq:trick:7:p2:choice",
                "module_type": "TrickChoiceModule",
                "module_cursor": "await_choice",
                "batch_id": "",
            },
        )()
        payload = {
            "pending_prompt_request_id": "req:trick:7",
            "pending_prompt_type": "trick_to_use",
            "pending_prompt_player_id": 2,
            "pending_prompt_instance_id": 7,
            "runtime_active_prompt": {
                "request_id": "req:trick:7",
                "request_type": "trick_to_use",
                "player_id": 2,
                "frame_id": "seq:trick:7:p2",
                "module_id": "mod:seq:trick:7:p2:choice",
                "module_type": "TrickChoiceModule",
                "module_cursor": "await_choice",
                "resume_token": "secret-resume-token",
            },
        }

        fields = _runtime_continuation_debug_fields(payload, resume)

        self.assertEqual(fields["runtime_active_prompt_request_id"], "req:trick:7")
        self.assertEqual(fields["runtime_active_prompt_module_id"], "mod:seq:trick:7:p2:choice")
        self.assertEqual(fields["decision_resume_choice_id"], "card:11")
        self.assertTrue(fields["runtime_active_prompt_resume_token_present"])
        self.assertTrue(fields["decision_resume_token_present"])
        self.assertNotIn("secret-resume-token", json.dumps(fields, ensure_ascii=False))

    def test_runtime_continuation_debug_fields_separates_internal_and_external_player_ids(self) -> None:
        payload = {
            "pending_prompt_request_id": "req:hidden:1",
            "pending_prompt_type": "hidden_trick_card",
            "pending_prompt_player_id": 1,
            "pending_prompt_instance_id": 1,
            "players": [{"player_id": 0}, {"player_id": 1}, {"player_id": 2}, {"player_id": 3}],
            "runtime_active_prompt": {
                "request_id": "req:hidden:1",
                "request_type": "hidden_trick_card",
                "player_id": 0,
                "frame_id": "turn:1:p0",
                "module_id": "mod:hidden:p0",
            },
        }

        fields = _runtime_continuation_debug_fields(payload)

        self.assertEqual(fields["waiting_prompt_player_id"], 1)
        self.assertEqual(fields["runtime_active_prompt_player_id"], 1)
        self.assertEqual(fields["runtime_active_prompt_internal_player_id"], 0)

    def test_fanout_debug_log_writes_only_committed_events_with_module_fields(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir, _temporary_debug_env(enabled="1", log_dir=temp_dir, run_id="fanout-run"):
                stream = _IdempotentStreamServiceStub()
                fanout = _FanoutVisEventStream(
                    loop,
                    stream,
                    "sess_debug_fanout",
                    lambda _session_id: None,
                )
                event = _DebugEventStub(
                    {
                        "event_type": "dice_roll",
                        "runtime_module": {
                            "runner_kind": "module",
                            "frame_id": "seq:roll_and_arrive:1:p0:1",
                            "module_id": "mod:seq:roll_and_arrive:1:p0:1:diceroll",
                            "module_type": "DiceRollModule",
                            "idempotency_key": "idem:dice",
                        },
                    }
                )

                fanout.append(event)
                stream.deduplicate_next_publish = True
                fanout.append(event)

                rows = (debug_game_log_run_dir() / "engine.jsonl").read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(rows), 1)
                parsed = json.loads(rows[0])
                self.assertEqual(parsed["event"], "dice_roll")
                self.assertEqual(parsed["runner_kind"], "module")
                self.assertEqual(parsed["frame_id"], "seq:roll_and_arrive:1:p0:1")
                self.assertEqual(parsed["module_id"], "mod:seq:roll_and_arrive:1:p0:1:diceroll")
                self.assertEqual(parsed["module_type"], "DiceRollModule")
                self.assertEqual(parsed["idempotency_key"], "idem:dice")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_fanout_event_payload_adds_public_identity_for_direct_player(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            stream = _IdempotentStreamServiceStub()
            fanout = _FanoutVisEventStream(
                loop,
                stream,
                "sess_identity_fanout",
                lambda _session_id: None,
                identity_fields_for_player=lambda player_id: {
                    "legacy_player_id": player_id,
                    "seat_index": player_id,
                    "turn_order_index": player_id - 1,
                    "player_label": f"P{player_id}",
                    "public_player_id": f"player_{player_id}",
                    "seat_id": f"seat_{player_id}",
                    "viewer_id": f"viewer_{player_id}",
                },
            )

            fanout.append(_DebugEventStub({"event_type": "dice_roll", "player_id": 2}))

            self.assertEqual(stream.published_payloads[0]["player_id"], 2)
            self.assertEqual(stream.published_payloads[0]["public_player_id"], "player_2")
            self.assertEqual(stream.published_payloads[0]["seat_id"], "seat_2")
            self.assertEqual(stream.published_payloads[0]["viewer_id"], "viewer_2")
            assert_no_public_identity_numeric_leaks(
                stream.published_payloads[0],
                boundary="fanout_direct_player_event",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_fanout_event_payload_adds_actor_public_identity_for_acting_player(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            stream = _IdempotentStreamServiceStub()
            fanout = _FanoutVisEventStream(
                loop,
                stream,
                "sess_identity_fanout",
                lambda _session_id: None,
                identity_fields_for_player=lambda player_id: {
                    "legacy_player_id": player_id,
                    "seat_index": player_id,
                    "turn_order_index": player_id - 1,
                    "player_label": f"P{player_id}",
                    "public_player_id": f"player_{player_id}",
                    "seat_id": f"seat_{player_id}",
                    "viewer_id": f"viewer_{player_id}",
                },
            )

            fanout.append(_DebugEventStub({"event_type": "turn_start", "acting_player_id": 3}))

            self.assertEqual(stream.published_payloads[0]["acting_player_id"], 3)
            self.assertEqual(stream.published_payloads[0]["acting_legacy_player_id"], 3)
            self.assertEqual(stream.published_payloads[0]["acting_public_player_id"], "player_3")
            self.assertEqual(stream.published_payloads[0]["acting_seat_id"], "seat_3")
            self.assertEqual(stream.published_payloads[0]["acting_viewer_id"], "viewer_3")
            assert_no_public_identity_numeric_leaks(
                stream.published_payloads[0],
                boundary="fanout_acting_player_event",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_fanout_event_payload_adds_prefixed_identity_for_related_players(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            stream = _IdempotentStreamServiceStub()
            fanout = _FanoutVisEventStream(
                loop,
                stream,
                "sess_related_identity_fanout",
                lambda _session_id: None,
                identity_fields_for_player=lambda player_id: {
                    "legacy_player_id": player_id,
                    "seat_index": player_id,
                    "turn_order_index": player_id - 1,
                    "player_label": f"P{player_id}",
                    "public_player_id": f"player_{player_id}",
                    "seat_id": f"seat_{player_id}",
                    "viewer_id": f"viewer_{player_id}",
                },
            )

            fanout.append(
                _DebugEventStub(
                    {
                        "event_type": "rent_paid",
                        "payer_player_id": 2,
                        "owner_player_id": 4,
                    }
                )
            )

            payload = stream.published_payloads[0]
            self.assertEqual(payload["payer_player_id"], 2)
            self.assertEqual(payload["payer_legacy_player_id"], 2)
            self.assertEqual(payload["payer_public_player_id"], "player_2")
            self.assertEqual(payload["payer_seat_id"], "seat_2")
            self.assertEqual(payload["payer_viewer_id"], "viewer_2")
            self.assertEqual(payload["owner_player_id"], 4)
            self.assertEqual(payload["owner_legacy_player_id"], 4)
            self.assertEqual(payload["owner_public_player_id"], "player_4")
            self.assertEqual(payload["owner_seat_id"], "seat_4")
            self.assertEqual(payload["owner_viewer_id"], "viewer_4")
            assert_no_public_identity_numeric_leaks(payload, boundary="fanout_related_player_event")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_fanout_event_payload_adds_public_identity_lists_for_player_id_lists(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            stream = _IdempotentStreamServiceStub()
            fanout = _FanoutVisEventStream(
                loop,
                stream,
                "sess_list_identity_fanout",
                lambda _session_id: None,
                identity_fields_for_player=lambda player_id: {
                    "legacy_player_id": player_id,
                    "seat_index": player_id,
                    "turn_order_index": player_id - 1,
                    "player_label": f"P{player_id}",
                    "public_player_id": f"player_{player_id}",
                    "seat_id": f"seat_{player_id}",
                    "viewer_id": f"viewer_{player_id}",
                },
            )

            fanout.append(
                _DebugEventStub(
                    {
                        "event_type": "round_start",
                        "alive_player_ids": [1, 3],
                        "winner_ids": [2, 4],
                    }
                )
            )

            payload = stream.published_payloads[0]
            self.assertEqual(payload["alive_player_ids"], [1, 3])
            self.assertEqual(payload["alive_legacy_player_ids"], [1, 3])
            self.assertEqual(payload["alive_public_player_ids"], ["player_1", "player_3"])
            self.assertEqual(payload["alive_seat_ids"], ["seat_1", "seat_3"])
            self.assertEqual(payload["alive_viewer_ids"], ["viewer_1", "viewer_3"])
            self.assertEqual(payload["winner_ids"], [2, 4])
            self.assertEqual(payload["winner_legacy_player_ids"], [2, 4])
            self.assertEqual(payload["winner_public_player_ids"], ["player_2", "player_4"])
            self.assertEqual(payload["winner_seat_ids"], ["seat_2", "seat_4"])
            self.assertEqual(payload["winner_viewer_ids"], ["viewer_2", "viewer_4"])
            assert_no_public_identity_numeric_leaks(payload, boundary="fanout_player_list_event")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_fanout_snapshot_payload_adds_public_identity_companions(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            stream = _IdempotentStreamServiceStub()
            fanout = _FanoutVisEventStream(
                loop,
                stream,
                "sess_snapshot_identity_fanout",
                lambda _session_id: None,
                identity_fields_for_player=lambda player_id: {
                    "legacy_player_id": player_id,
                    "seat_index": player_id,
                    "turn_order_index": player_id - 1,
                    "player_label": f"P{player_id}",
                    "public_player_id": f"player_{player_id}",
                    "seat_id": f"seat_{player_id}",
                    "viewer_id": f"viewer_{player_id}",
                },
            )

            fanout.append(
                _DebugEventStub(
                    {
                        "event_type": "turn_end_snapshot",
                        "snapshot": {
                            "players": [
                                {"player_id": 1, "cash": 100},
                                {"player_id": 2, "cash": 90},
                            ],
                            "board": {
                                "marker_owner_player_id": 2,
                                "tiles": [
                                    {
                                        "tile_index": 0,
                                        "owner_player_id": 1,
                                        "pawn_player_ids": [1, 2],
                                    }
                                ],
                            },
                            "active_by_card": {"1": "Architect"},
                        },
                    }
                )
            )

            snapshot = stream.published_payloads[0]["snapshot"]
            self.assertEqual(snapshot["players"][0]["player_id"], 1)
            self.assertEqual(snapshot["players"][0]["public_player_id"], "player_1")
            self.assertEqual(snapshot["players"][0]["seat_id"], "seat_1")
            self.assertEqual(snapshot["players"][0]["viewer_id"], "viewer_1")
            self.assertNotIn("legacy_player_id", snapshot["players"][0])

            board = snapshot["board"]
            self.assertEqual(board["marker_owner_player_id"], 2)
            self.assertEqual(board["marker_owner_legacy_player_id"], 2)
            self.assertEqual(board["marker_owner_public_player_id"], "player_2")
            self.assertEqual(board["marker_owner_seat_id"], "seat_2")
            self.assertEqual(board["marker_owner_viewer_id"], "viewer_2")

            tile = board["tiles"][0]
            self.assertEqual(tile["owner_player_id"], 1)
            self.assertEqual(tile["owner_legacy_player_id"], 1)
            self.assertEqual(tile["owner_public_player_id"], "player_1")
            self.assertEqual(tile["owner_seat_id"], "seat_1")
            self.assertEqual(tile["owner_viewer_id"], "viewer_1")
            self.assertEqual(tile["pawn_player_ids"], [1, 2])
            self.assertEqual(tile["pawn_legacy_player_ids"], [1, 2])
            self.assertEqual(tile["pawn_public_player_ids"], ["player_1", "player_2"])
            self.assertEqual(tile["pawn_seat_ids"], ["seat_1", "seat_2"])
            self.assertEqual(tile["pawn_viewer_ids"], ["viewer_1", "viewer_2"])
            self.assertEqual(snapshot["active_by_card"], {"1": "Architect"})
            assert_no_public_identity_numeric_leaks(snapshot, boundary="fanout_snapshot_payload")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_fanout_event_stream_drops_publish_timeout_without_blocking_runtime(self) -> None:
        class StreamStub:
            async def latest_seq(self, session_id: str) -> int:
                del session_id
                return 0

            async def publish(self, session_id: str, event_type: str, payload: dict) -> _PublishedEventStub:
                del session_id, event_type, payload
                return _PublishedEventStub(1)

        cancelled = False

        class FutureStub:
            def __init__(self, value=None, *, timeout: bool = False) -> None:
                self._value = value
                self._timeout = timeout

            def result(self, timeout=None):
                self.timeout_arg = timeout
                if timeout is None:
                    raise AssertionError("fanout stream wait must use a timeout")
                if self._timeout:
                    raise concurrent.futures.TimeoutError()
                return self._value

            def cancel(self) -> None:
                nonlocal cancelled
                cancelled = True

        calls = 0

        def fake_run_coroutine_threadsafe(coro, loop):
            nonlocal calls
            del loop
            calls += 1
            coro.close()
            if calls == 1:
                return FutureStub(0)
            return FutureStub(timeout=True)

        fanout = _FanoutVisEventStream(
            object(),
            StreamStub(),
            "sess_fanout_timeout",
            lambda _session_id: None,
        )

        with patch(
            "apps.server.src.services.runtime_service.asyncio.run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ), patch("apps.server.src.services.runtime_service.log_event") as log_event:
            fanout.append(_DebugEventStub({"event_type": "dice_roll"}))

        self.assertTrue(cancelled)
        log_event.assert_called_once()
        self.assertEqual(log_event.call_args.args[0], "runtime_event_stream_publish_failed")

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
        self.assertNotIn("view_state", internal)
        self.assertTrue(public["recovery_checkpoint"]["available"])
        self.assertNotIn("current_state", public["recovery_checkpoint"])
        self.assertNotIn("view_state", public["recovery_checkpoint"])
        self.assertTrue(public["recovery_checkpoint"]["current_state_available"])

    def test_active_simultaneous_batch_publishes_module_prompts_for_missing_players(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            frame = build_resupply_frame(
                1,
                3,
                parent_frame_id="turn:1:p0",
                parent_module_id="mod:turn:1:p0:arrival",
                participants=[0, 1],
            )
            module = next(module for module in frame.module_queue if module.module_type == "ResupplyModule")
            module.cursor = "await_resupply_batch:1"
            batch = PromptApi().create_batch(
                batch_id="batch:simul:resupply:1",
                frame=frame,
                module=module,
                participant_player_ids=[0, 1],
                request_type="burden_exchange",
                legal_choices_by_player_id={
                    0: [{"choice_id": "yes"}, {"choice_id": "no"}],
                    1: [{"choice_id": "yes"}, {"choice_id": "no"}],
                },
                public_context_by_player_id={
                    0: {"round_index": 1, "turn_index": 3, "card_name": "무거운 짐"},
                    1: {"round_index": 1, "turn_index": 3, "card_name": "가벼운 짐"},
                },
            )
            state = type("State", (), {"runtime_active_prompt_batch": batch})()

            self.runtime_service._publish_active_module_prompt_batch_sync(loop, "sess_batch_prompt", state)

            first_pending = self.prompt_service.get_pending_prompt(
                batch.prompts_by_player_id[0].request_id,
                session_id="sess_batch_prompt",
            )
            second_pending = self.prompt_service.get_pending_prompt(
                batch.prompts_by_player_id[1].request_id,
                session_id="sess_batch_prompt",
            )
            self.assertIsNotNone(first_pending)
            self.assertIsNotNone(second_pending)
            assert first_pending is not None
            self.assertEqual(first_pending.payload["batch_id"], "batch:simul:resupply:1")
            self.assertEqual(first_pending.payload["module_type"], "ResupplyModule")
            self.assertEqual(first_pending.payload["module_cursor"], "await_resupply_batch:1")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_batch_prompt"),
                loop,
            ).result(timeout=2.0)
            prompt_messages = [msg for msg in published if msg.type == "prompt"]
            decision_requested = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("event_type") == "decision_requested"
            ]
            self.assertEqual(len(prompt_messages), 2)
            self.assertEqual(len(decision_requested), 2)
            self.assertEqual(prompt_messages[0].payload["runtime_module"]["frame_type"], "simultaneous")
            self.assertEqual(prompt_messages[0].payload["batch_id"], "batch:simul:resupply:1")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_runtime_prompt_boundary_enriches_active_simultaneous_batch_contract(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            session = self._create_started_two_player_session()
            seat_1, seat_2 = session.seats[0], session.seats[1]
            frame = build_resupply_frame(
                1,
                4,
                parent_frame_id="turn:1:p0",
                parent_module_id="mod:turn:1:p0:arrival",
                participants=[0, 1],
            )
            module = next(module for module in frame.module_queue if module.module_type == "ResupplyModule")
            module.cursor = "await_resupply_batch:1"
            batch = PromptApi().create_batch(
                batch_id="batch:simul:resupply:1:4:mod:simul:resupply:1:4:resupply:1",
                frame=frame,
                module=module,
                participant_player_ids=[0, 1],
                request_type="burden_exchange",
                legal_choices_by_player_id={
                    0: [{"choice_id": "yes"}, {"choice_id": "no"}],
                    1: [{"choice_id": "yes"}, {"choice_id": "no"}],
                },
                public_context_by_player_id={
                    0: {"round_index": 1, "turn_index": 4, "card_name": "무거운 짐"},
                    1: {"round_index": 1, "turn_index": 4, "card_name": "가벼운 짐"},
                },
            )
            state = type("State", (), {"runtime_active_prompt_batch": batch})()
            continuation = batch.prompts_by_player_id[1]
            prompt_payload = {
                "request_id": continuation.request_id,
                "request_type": continuation.request_type,
                "player_id": 2,
                "prompt_instance_id": 12,
                "legal_choices": list(continuation.legal_choices),
                "public_context": dict(continuation.public_context),
                "timeout_ms": 30000,
                "fallback_policy": "required",
                "runner_kind": "module",
                "resume_token": continuation.resume_token,
                "frame_id": continuation.frame_id,
                "module_id": continuation.module_id,
                "module_type": continuation.module_type,
                "module_cursor": continuation.module_cursor,
            }

            self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                session.session_id,
                prompt_payload,
                state=state,
            )

            pending = self.prompt_service.get_pending_prompt(
                continuation.request_id,
                session_id=session.session_id,
            )
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.payload["batch_id"], batch.batch_id)
            self.assertEqual(pending.payload["missing_player_ids"], [1, 2])
            self.assertEqual(
                pending.payload["missing_public_player_ids"],
                [seat_1.public_player_id, seat_2.public_player_id],
            )
            self.assertEqual(pending.payload["missing_seat_ids"], [seat_1.seat_id, seat_2.seat_id])
            self.assertEqual(pending.payload["missing_viewer_ids"], [seat_1.viewer_id, seat_2.viewer_id])
            self.assertEqual(
                pending.payload["resume_tokens_by_player_id"],
                {
                    "1": batch.prompts_by_player_id[0].resume_token,
                    "2": batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(
                pending.payload["resume_tokens_by_public_player_id"],
                {
                    seat_1.public_player_id: batch.prompts_by_player_id[0].resume_token,
                    seat_2.public_player_id: batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(
                pending.payload["resume_tokens_by_seat_id"],
                {
                    seat_1.seat_id: batch.prompts_by_player_id[0].resume_token,
                    seat_2.seat_id: batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(
                pending.payload["resume_tokens_by_viewer_id"],
                {
                    seat_1.viewer_id: batch.prompts_by_player_id[0].resume_token,
                    seat_2.viewer_id: batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(pending.payload["runtime_module"]["frame_type"], "simultaneous")
            assert_no_public_identity_numeric_leaks(
                pending.payload,
                boundary="active_batch_prompt_payload",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_runtime_prompt_boundary_enriches_checkpoint_payload_batch_contract(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            session = self._create_started_two_player_session()
            seat_1, seat_2 = session.seats[0], session.seats[1]
            frame = build_resupply_frame(
                1,
                4,
                parent_frame_id="turn:1:p0",
                parent_module_id="mod:turn:1:p0:arrival",
                participants=[0, 1],
            )
            module = next(module for module in frame.module_queue if module.module_type == "ResupplyModule")
            module.cursor = "await_resupply_batch:1"
            batch = PromptApi().create_batch(
                batch_id="batch:simul:resupply:1:4:mod:simul:resupply:1:4:resupply:1",
                frame=frame,
                module=module,
                participant_player_ids=[0, 1],
                request_type="burden_exchange",
                legal_choices_by_player_id={
                    0: [{"choice_id": "yes"}, {"choice_id": "no"}],
                    1: [{"choice_id": "yes"}, {"choice_id": "no"}],
                },
                public_context_by_player_id={
                    0: {"round_index": 1, "turn_index": 4, "card_name": "무거운 짐"},
                    1: {"round_index": 1, "turn_index": 4, "card_name": "가벼운 짐"},
                },
            )
            batch.missing_player_ids = [0, 1]
            state = type("State", (), {"runtime_active_prompt_batch": batch.to_payload()})()
            continuation = batch.prompts_by_player_id[0]
            prompt_payload = {
                "request_id": continuation.request_id,
                "request_type": continuation.request_type,
                "player_id": 1,
                "prompt_instance_id": 12,
                "legal_choices": list(continuation.legal_choices),
                "public_context": dict(continuation.public_context),
                "timeout_ms": 30000,
                "fallback_policy": "required",
                "runner_kind": "module",
                "resume_token": continuation.resume_token,
                "frame_id": continuation.frame_id,
                "module_id": continuation.module_id,
                "module_type": continuation.module_type,
                "module_cursor": continuation.module_cursor,
            }

            self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                session.session_id,
                prompt_payload,
                state=state,
            )

            pending = self.prompt_service.get_pending_prompt(
                continuation.request_id,
                session_id=session.session_id,
            )
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.payload["batch_id"], batch.batch_id)
            self.assertEqual(pending.payload["missing_player_ids"], [1, 2])
            self.assertEqual(
                pending.payload["missing_public_player_ids"],
                [seat_1.public_player_id, seat_2.public_player_id],
            )
            self.assertEqual(pending.payload["missing_seat_ids"], [seat_1.seat_id, seat_2.seat_id])
            self.assertEqual(pending.payload["missing_viewer_ids"], [seat_1.viewer_id, seat_2.viewer_id])
            self.assertEqual(
                pending.payload["resume_tokens_by_player_id"],
                {
                    "1": batch.prompts_by_player_id[0].resume_token,
                    "2": batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(
                pending.payload["resume_tokens_by_public_player_id"],
                {
                    seat_1.public_player_id: batch.prompts_by_player_id[0].resume_token,
                    seat_2.public_player_id: batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(
                pending.payload["resume_tokens_by_seat_id"],
                {
                    seat_1.seat_id: batch.prompts_by_player_id[0].resume_token,
                    seat_2.seat_id: batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(
                pending.payload["resume_tokens_by_viewer_id"],
                {
                    seat_1.viewer_id: batch.prompts_by_player_id[0].resume_token,
                    seat_2.viewer_id: batch.prompts_by_player_id[1].resume_token,
                },
            )
            self.assertEqual(pending.payload["runtime_module"]["frame_type"], "simultaneous")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

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

    def test_checkpointed_runtime_status_does_not_complete_from_stale_done_task(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        game_state_store = _MutableGameStateStoreStub()
        game_state_store.checkpoint = {
            "session_id": session.session_id,
            "latest_seq": 43,
            "waiting_prompt_request_id": "req_waiting_movement",
        }
        game_state_store.current_state = {
            "session_id": session.session_id,
            "tiles": [],
            "players": [],
        }
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )
        runtime._status[session.session_id] = {"status": "running", "watchdog_state": "ok"}  # type: ignore[attr-defined]
        runtime._last_activity_ms[session.session_id] = runtime._now_ms()  # type: ignore[attr-defined]
        runtime._runtime_tasks[session.session_id] = _DoneRuntimeTaskStub()  # type: ignore[attr-defined]
        runtime._persist_runtime_state(session.session_id)  # type: ignore[attr-defined]

        status = runtime.runtime_status(session.session_id)

        self.assertEqual(status.get("status"), "waiting_input")
        self.assertNotEqual(runtime_state_store.statuses[session.session_id].get("status"), "completed")

    def test_runtime_status_normalizes_waiting_checkpoint_after_restart(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        runtime_state_store.statuses[session.session_id] = {
            "status": "running",
            "watchdog_state": "ok",
            "lease_expires_at_ms": 1,
        }
        game_state_store = _MutableGameStateStoreStub()
        game_state_store.checkpoint = {
            "session_id": session.session_id,
            "latest_seq": 85,
            "waiting_prompt_request_id": "req_hidden_trick",
            "waiting_prompt_player_id": 1,
            "runtime_active_prompt": {
                "request_id": "req_hidden_trick",
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "legal_choices": [{"choice_id": "skip"}],
            },
        }
        game_state_store.current_state = {
            "session_id": session.session_id,
            "tiles": [],
            "players": [],
        }
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )

        status = runtime.runtime_status(session.session_id)

        self.assertEqual(status.get("status"), "waiting_input")
        self.assertEqual(status.get("watchdog_state"), "waiting_input")
        self.assertEqual(runtime_state_store.statuses[session.session_id].get("status"), "waiting_input")
        self.assertIn("recovery_checkpoint", status)

    def test_runtime_status_preserves_rejected_command_over_waiting_checkpoint(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        runtime_state_store.statuses[session.session_id] = {
            "status": "rejected",
            "watchdog_state": "rejected",
            "reason": "decision resume parse failed",
            "processed_command_seq": 79,
        }
        game_state_store = _MutableGameStateStoreStub()
        game_state_store.checkpoint = {
            "session_id": session.session_id,
            "latest_seq": 283,
            "waiting_prompt_request_id": "req_hidden_trick",
            "waiting_prompt_player_id": 1,
            "runtime_active_prompt": {
                "request_id": "req_hidden_trick",
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "legal_choices": [{"choice_id": "14"}],
            },
        }
        game_state_store.current_state = {
            "session_id": session.session_id,
            "tiles": [],
            "players": [],
        }
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )

        status = runtime.runtime_status(session.session_id)

        self.assertEqual(status.get("status"), "rejected")
        self.assertEqual(status.get("watchdog_state"), "rejected")
        self.assertEqual(status.get("reason"), "decision resume parse failed")
        self.assertEqual(status.get("processed_command_seq"), 79)
        self.assertEqual(runtime_state_store.statuses[session.session_id].get("status"), "rejected")
        self.assertIn("recovery_checkpoint", status)

    def test_runtime_status_clears_stale_waiting_input_when_checkpoint_has_no_prompt(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        game_state_store = _MutableGameStateStoreStub()
        game_state_store.checkpoint = {
            "session_id": session.session_id,
            "latest_seq": 86,
            "latest_commit_seq": 212,
            "waiting_prompt_request_id": "",
            "runtime_active_prompt_request_id": "",
        }
        game_state_store.current_state = {
            "session_id": session.session_id,
            "tiles": [],
            "players": [],
            "runtime_active_prompt": {},
        }
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )
        runtime_state_store.statuses[session.session_id] = {
            "status": "waiting_input",
            "watchdog_state": "waiting_input",
            "reason": "checkpoint_waiting_input",
            "lease_expires_at_ms": 1,
        }

        status = runtime.runtime_status(session.session_id)

        self.assertEqual(status.get("status"), "recovery_required")
        self.assertEqual(status.get("watchdog_state"), "recovery_required")
        self.assertEqual(status.get("reason"), "stale_waiting_input_checkpoint")
        self.assertEqual(runtime_state_store.statuses[session.session_id].get("status"), "recovery_required")
        self.assertIn("recovery_checkpoint", status)

    def test_runtime_status_reports_command_processing_active_without_stale_recovery(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        game_state_store = _MutableGameStateStoreStub()
        game_state_store.checkpoint = {
            "session_id": session.session_id,
            "latest_seq": 86,
            "latest_commit_seq": 212,
            "waiting_prompt_request_id": "",
            "runtime_active_prompt_request_id": "",
        }
        game_state_store.current_state = {
            "session_id": session.session_id,
            "tiles": [],
            "players": [],
            "runtime_active_prompt": {},
        }
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )
        runtime_state_store.statuses[session.session_id] = {
            "status": "waiting_input",
            "watchdog_state": "waiting_input",
            "reason": "checkpoint_waiting_input",
            "lease_expires_at_ms": 1,
        }
        self.assertTrue(runtime._begin_command_processing(session.session_id))  # type: ignore[attr-defined]
        try:
            status = runtime.runtime_status(session.session_id)
        finally:
            runtime._end_command_processing(session.session_id)  # type: ignore[attr-defined]

        self.assertEqual(status.get("status"), "running_elsewhere")
        self.assertEqual(status.get("watchdog_state"), "running")
        self.assertEqual(status.get("reason"), "command_processing_active")
        self.assertEqual(runtime_state_store.statuses[session.session_id].get("status"), "waiting_input")

    def test_start_runtime_defers_waiting_checkpoint_without_engine_task(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        game_state_store = _MutableGameStateStoreStub()
        game_state_store.checkpoint = {
            "session_id": session.session_id,
            "latest_seq": 85,
            "waiting_prompt_request_id": "req_hidden_trick",
        }
        game_state_store.current_state = {
            "session_id": session.session_id,
            "tiles": [],
            "players": [],
        }
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )

        asyncio.run(runtime.start_runtime(session.session_id, seed=42, policy_mode=None))

        self.assertNotIn(session.session_id, runtime._runtime_tasks)  # type: ignore[attr-defined]
        self.assertEqual(runtime.runtime_status(session.session_id).get("status"), "waiting_input")

    def test_start_runtime_defers_while_command_processing_is_active(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
        )
        self.assertTrue(runtime._begin_command_processing(session.session_id))  # type: ignore[attr-defined]
        try:
            asyncio.run(runtime.start_runtime(session.session_id, seed=42, policy_mode=None))
        finally:
            runtime._end_command_processing(session.session_id)  # type: ignore[attr-defined]

        self.assertNotIn(session.session_id, runtime._runtime_tasks)  # type: ignore[attr-defined]
        status = runtime_state_store.statuses[session.session_id]
        self.assertEqual(status.get("status"), "running_elsewhere")
        self.assertEqual(status.get("reason"), "command_processing_already_active")
        self.assertIsNone(runtime_state_store.lease_owner(session.session_id))

    def test_runtime_lease_is_not_reentrant_in_same_process(self) -> None:
        runtime_state_store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
        )
        session_id = "sess_reentrant"

        self.assertTrue(runtime._acquire_runtime_lease(session_id))  # type: ignore[attr-defined]
        try:
            self.assertFalse(runtime._acquire_runtime_lease(session_id))  # type: ignore[attr-defined]
            self.assertEqual(runtime_state_store.lease_owner(session_id), runtime._worker_id)  # type: ignore[attr-defined]
        finally:
            runtime._release_runtime_lease(session_id)  # type: ignore[attr-defined]

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
                prompt_payload={
                    "fallback_choice_id": "choice_default",
                    "legal_choices": [{"choice_id": "choice_default", "title": "Default"}],
                },
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

    def test_execute_prompt_fallback_ignores_illegal_explicit_default(self) -> None:
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
                request_id="req_timeout_illegal_default",
                player_id=2,
                fallback_policy="timeout_fallback",
                prompt_payload={
                    "request_type": "movement",
                    "fallback_choice_id": "timeout_fallback",
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

    def test_execute_prompt_fallback_rejects_prompt_without_legal_choices(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        with self.assertRaises(ValueError):
            asyncio.run(
                self.runtime_service.execute_prompt_fallback(
                    session_id=session.session_id,
                    request_id="req_timeout_empty_legal_choices",
                    player_id=2,
                    fallback_policy="timeout_fallback",
                    prompt_payload={
                        "request_type": "movement",
                        "fallback_choice_id": "timeout_fallback",
                        "legal_choices": [],
                    },
                )
            )

        recent = self.runtime_service.runtime_status(session.session_id).get("recent_fallbacks", [])
        self.assertEqual(recent, [])

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
            **_kwargs,
        ) -> dict:
            calls.append((command_consumer_name, command_seq))
            if len(calls) == 1:
                return {"status": "committed", "pending_actions": 1}
            return {"status": "waiting_input", "request_type": "purchase_tile", "player_id": 1}

        with patch.object(self.runtime_service, "_run_engine_transition_once_sync", side_effect=_transition_once):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=self.runtime_service).process_command_once(
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

    def test_command_scope_loop_defers_internal_transition_commits(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        store = _MutableGameStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
        )
        calls: list[tuple[str | None, int | None]] = []

        def _transition_once(
            _loop,
            _session_id: str,
            _seed: int,
            _policy_mode: str | None,
            _require_checkpoint: bool,
            command_consumer_name: str | None,
            command_seq: int | None,
            **kwargs,
        ) -> dict:
            calls.append((command_consumer_name, command_seq))
            processed_consumer = command_consumer_name or kwargs.get("checkpoint_command_consumer_name")
            processed_seq = command_seq if command_seq is not None else kwargs.get("checkpoint_command_seq")
            commit_seq = len(calls)
            boundary_store = kwargs["game_state_store_override"]
            if len(calls) < 3:
                boundary_store.stage_internal_transition(
                    _session_id,
                    current_state={"tiles": [], "transition_index": commit_seq},
                )
                return {"status": "committed", "module_type": f"Module{commit_seq}"}
            boundary_store.commit_transition(
                _session_id,
                current_state={"tiles": [], "transition_index": commit_seq},
                checkpoint={
                    "schema_version": 3,
                    "session_id": _session_id,
                    "runner_kind": "module",
                    "latest_commit_seq": commit_seq,
                },
                view_state={"transition_index": commit_seq},
                view_commits={"spectator": {"commit_seq": commit_seq}},
                command_consumer_name=processed_consumer,
                command_seq=processed_seq,
                expected_previous_commit_seq=commit_seq - 1,
            )
            return {
                "status": "waiting_input",
                "reason": "prompt_required",
                "request_type": "purchase_tile",
                "player_id": 1,
                "module_type": "PromptModule",
            }

        with patch.object(runtime, "_run_engine_transition_once_sync", side_effect=_transition_once):
            result = runtime._run_engine_transition_loop_sync(
                None,  # type: ignore[arg-type]
                session.session_id,
                73,
                None,
                first_command_consumer_name="runtime_wakeup",
                first_command_seq=7,
            )

        self.assertEqual(result["status"], "waiting_input")
        self.assertEqual(result["transitions"], 3)
        self.assertEqual(result["module_transition_count"], 3)
        self.assertEqual(result["redis_commit_count"], 1)
        self.assertEqual(result["view_commit_count"], 1)
        self.assertGreaterEqual(result["engine_loop_total_ms"], result["command_boundary_finalization_ms"])
        self.assertGreaterEqual(result["engine_prepare_ms"], 0)
        self.assertGreaterEqual(result["engine_transition_loop_ms"], 0)
        self.assertEqual(calls, [("runtime_wakeup", 7), (None, None), (None, None)])
        self.assertEqual(len(store.commits), 1)
        self.assertEqual(store.commits[0]["current_state"]["transition_index"], 3)
        self.assertEqual(store.commits[0]["command_seq"], 7)

    def test_process_command_once_logs_processing_timing(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        events: list[tuple[str, dict]] = []

        def _transition_loop(*_args, **_kwargs) -> dict:
            time.sleep(0.002)
            return {"status": "waiting_input", "request_type": "purchase_tile", "player_id": 1}

        def _capture_event(event: str, **fields) -> None:
            events.append((event, fields))

        with (
            patch.object(self.runtime_service, "_run_engine_transition_loop_sync", side_effect=_transition_loop),
            patch("apps.server.src.services.runtime_service.log_event", side_effect=_capture_event),
        ):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=self.runtime_service).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "waiting_input")
        timing_events = [fields for event, fields in events if event == "runtime_command_process_timing"]
        self.assertEqual(len(timing_events), 1)
        timing = timing_events[0]
        self.assertEqual(timing["session_id"], session.session_id)
        self.assertEqual(timing["command_seq"], 7)
        self.assertEqual(timing["consumer_name"], "runtime_wakeup")
        self.assertEqual(timing["result_status"], "waiting_input")
        self.assertGreaterEqual(timing["total_ms"], 1)
        self.assertGreaterEqual(timing["pre_executor_ms"], 0)
        self.assertGreaterEqual(timing["executor_wall_ms"], 1)
        self.assertIn("engine_loop_total_ms", timing)
        self.assertIn("executor_overhead_ms", timing)

    def test_process_command_once_refreshes_runtime_lease_while_transition_runs(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        runtime_state_store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
        )

        def _transition_loop(*_args, **_kwargs) -> dict:
            deadline = time.monotonic() + 0.3
            while len(runtime_state_store.refresh_calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            return {"status": "waiting_input", "request_type": "purchase_tile", "player_id": 1}

        with (
            patch.object(runtime, "_runtime_lease_refresh_interval_seconds", return_value=0.01),
            patch.object(runtime, "_run_engine_transition_loop_sync", side_effect=_transition_loop),
        ):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "waiting_input")
        self.assertGreaterEqual(len(runtime_state_store.refresh_calls), 2)
        self.assertIsNone(runtime_state_store.lease_owner(session.session_id))

    def test_process_command_once_defers_when_runtime_task_is_active(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        self.runtime_service._runtime_tasks[session.session_id] = _PendingRuntimeTaskStub()

        with patch.object(self.runtime_service, "_run_engine_transition_loop_sync", side_effect=AssertionError("must not run")):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=self.runtime_service).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "running_elsewhere")
        self.assertEqual(result["reason"], "runtime_task_already_active")
        self.assertEqual(result["processed_command_seq"], 7)

    def test_process_command_once_skips_already_consumed_command(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        command_store = _CommandStoreStub(offset=7, commands=[{"seq": 7, "type": "decision_submitted"}])
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )

        with patch.object(runtime, "_run_engine_transition_loop_sync", side_effect=AssertionError("must not run")):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "already_processed")
        self.assertEqual(result["processed_command_seq"], 7)

    def test_process_command_once_reprocesses_offset_conflict_when_checkpoint_still_waits_for_command(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        command_store = _CommandStoreStub(
            offset=7,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": "sess_1:r1:t1:p1:final_character:1",
                        "choice_id": "mansin",
                        "frame_id": "turn:1:p0",
                        "module_id": "mod:turn:1:p0:draft",
                        "module_type": "DraftModule",
                        "module_cursor": "final_character:1",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": "sess_1:r1:t1:p1:final_character:1",
                "active_frame_id": "turn:1:p0",
                "active_module_id": "mod:turn:1:p0:draft",
                "active_module_type": "DraftModule",
                "active_module_cursor": "final_character:1",
            },
            "current_state": {},
        }

        with patch.object(runtime, "_run_engine_transition_loop_sync", return_value={"status": "waiting_input"}) as run_loop:
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "waiting_input")
        run_loop.assert_called_once()

    def test_process_command_once_reprocesses_offset_conflict_for_batch_prompt(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        request_id = "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p0"
        command_store = _CommandStoreStub(
            offset=7,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "player_id": 1,
                        "choice_id": "yes",
                        "frame_id": "simul:resupply:1:95",
                        "module_id": "mod:simul:resupply:1:95:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "runtime_active_prompt_batch": {
                    "missing_player_ids": [0],
                    "prompts_by_player_id": {
                        "0": {
                            "request_id": request_id,
                            "frame_id": "simul:resupply:1:95",
                            "module_id": "mod:simul:resupply:1:95:resupply",
                            "module_type": "ResupplyModule",
                            "module_cursor": "await_resupply_batch:1",
                        }
                    },
                },
                "active_frame_id": "simul:resupply:1:95",
                "active_module_id": "mod:simul:resupply:1:95:resupply",
                "active_module_type": "ResupplyModule",
                "active_module_cursor": "await_resupply_batch:1",
            },
            "current_state": {},
        }

        with patch.object(runtime, "_run_engine_transition_loop_sync", return_value={"status": "waiting_input"}) as run_loop:
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "waiting_input")
        run_loop.assert_called_once()

    def test_process_command_once_reprocesses_checkpoint_match_when_pending_lookup_races(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        request_id = "sess_1:r2:t9:p4:active_flip:120"
        command_store = _CommandStoreStub(
            offset=61,
            commands=[
                {
                    "seq": 62,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "player_id": 4,
                        "request_type": "active_flip",
                        "choice_id": "none",
                        "frame_id": "round:2",
                        "module_id": "mod:round:2:roundendcardflip",
                        "module_type": "RoundEndCardFlipModule",
                        "module_cursor": "start",
                    },
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": request_id,
                "active_frame_id": "round:2",
                "active_module_id": "mod:round:2:roundendcardflip",
                "active_module_type": "RoundEndCardFlipModule",
                "active_module_cursor": "start",
            },
            "current_state": {},
        }
        runtime.pending_resume_command = lambda _session_id, consumer_name="runtime_wakeup": None  # type: ignore[method-assign]

        with patch.object(runtime, "_run_engine_transition_loop_sync", return_value={"status": "waiting_input"}) as run_loop:
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=62,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "waiting_input")
        run_loop.assert_called_once()

    def test_command_offset_commit_deferred_when_resume_still_waits_on_same_prompt(self) -> None:
        resume = RuntimeDecisionResume(
            request_id="req_active_flip_120",
            player_id=4,
            request_type="active_flip",
            choice_id="none",
            choice_payload={},
            resume_token="resume_active_flip_120",
            frame_id="round:2",
            module_id="mod:round:2:roundendcardflip",
            module_type="RoundEndCardFlipModule",
            module_cursor="start",
        )
        checkpoint = {
            "waiting_prompt_request_id": "req_active_flip_120",
            "active_frame_id": "round:2",
            "active_module_id": "mod:round:2:roundendcardflip",
            "active_module_type": "RoundEndCardFlipModule",
            "active_module_cursor": "start",
        }

        consumer_name, command_seq = self.runtime_service._command_offset_args_for_commit(
            session_id="sess_1",
            checkpoint=checkpoint,
            command_consumer_name="runtime_wakeup",
            command_seq=62,
            decision_resume=resume,
        )

        self.assertIsNone(consumer_name)
        self.assertIsNone(command_seq)

    def test_command_offset_commit_advances_when_resume_changes_waiting_prompt(self) -> None:
        resume = RuntimeDecisionResume(
            request_id="req_active_flip_120",
            player_id=4,
            request_type="active_flip",
            choice_id="none",
            choice_payload={},
            resume_token="resume_active_flip_120",
            frame_id="round:2",
            module_id="mod:round:2:roundendcardflip",
            module_type="RoundEndCardFlipModule",
            module_cursor="start",
        )
        checkpoint = {
            "waiting_prompt_request_id": "req_purchase_121",
            "active_frame_id": "turn:2:p0",
            "active_module_id": "mod:turn:2:p0:purchase",
            "active_module_type": "PurchaseModule",
            "active_module_cursor": "await_purchase",
        }

        consumer_name, command_seq = self.runtime_service._command_offset_args_for_commit(
            session_id="sess_1",
            checkpoint=checkpoint,
            command_consumer_name="runtime_wakeup",
            command_seq=62,
            decision_resume=resume,
        )

        self.assertEqual(consumer_name, "runtime_wakeup")
        self.assertEqual(command_seq, 62)

    def test_process_command_once_skips_command_that_no_longer_matches_waiting_prompt(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {"request_id": "old_request"},
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {"waiting_prompt_request_id": "new_request"},
            "current_state": {},
        }

        with patch.object(runtime, "_run_engine_transition_loop_sync", side_effect=AssertionError("must not run")):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "command_no_longer_matches_waiting_prompt")
        self.assertEqual(result["consumer_offset"], 7)
        self.assertEqual(command_store.offset, 7)

    def test_process_command_once_advances_offset_when_older_command_precedes_active_prompt(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {"request_id": "old_request"},
                },
                {
                    "seq": 8,
                    "type": "decision_submitted",
                    "payload": {"request_id": "active_request"},
                },
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {"waiting_prompt_request_id": "active_request"},
            "current_state": {},
        }

        with patch.object(runtime, "_run_engine_transition_loop_sync", side_effect=AssertionError("must not run")):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "pending_command_seq_changed")
        self.assertEqual(result["consumer_offset"], 7)
        self.assertEqual(command_store.offset, 7)

    def test_process_command_once_defers_newer_command_until_earlier_pending_is_consumed(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {"request_id": "current_request"},
                },
                {
                    "seq": 8,
                    "type": "decision_submitted",
                    "payload": {"request_id": "next_request"},
                },
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {"waiting_prompt_request_id": "current_request"},
            "current_state": {},
        }

        with patch.object(runtime, "_run_engine_transition_loop_sync", side_effect=AssertionError("must not run")):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=8,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "running_elsewhere")
        self.assertEqual(result["reason"], "pending_command_seq_precedes_target")
        self.assertEqual(result["pending_command_seq"], 7)
        self.assertEqual(command_store.offset, 6)

    def test_process_command_once_checks_active_command_before_stale_guard(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {"request_id": "next_request"},
                }
            ],
        )
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=command_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {"waiting_prompt_request_id": "current_request"},
            "current_state": {},
        }
        self.assertTrue(runtime._begin_command_processing(session.session_id))

        try:
            with patch.object(runtime, "_run_engine_transition_loop_sync", side_effect=AssertionError("must not run")):
                result = asyncio.run(
                    SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                        session_id=session.session_id,
                        command_seq=7,
                        consumer_name="runtime_wakeup",
                        seed=73,
                    )
                )
        finally:
            runtime._end_command_processing(session.session_id)

        self.assertEqual(result["status"], "running_elsewhere")
        self.assertEqual(result["reason"], "command_processing_already_active")
        self.assertEqual(command_store.offset, 6)

    def test_process_command_once_treats_view_commit_conflict_as_recoverable_duplicate(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 73},
        )
        runtime_state_store = _RuntimeStateStoreStub()
        game_state_store = _MutableGameStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state_store,
        )
        runtime.recovery_checkpoint = lambda _session_id: {  # type: ignore[method-assign]
            "available": True,
            "checkpoint": {
                "waiting_prompt_request_id": "req_after_duplicate_commit",
                "runtime_active_prompt": {
                    "request_id": "req_after_duplicate_commit",
                    "legal_choices": [{"choice_id": "yes"}],
                },
            },
            "current_state": {},
        }

        with patch.object(
            runtime,
            "_run_engine_transition_loop_sync",
            side_effect=ViewCommitSequenceConflict("view_commit_seq_conflict"),
        ):
            result = asyncio.run(
                SessionCommandExecutor(runtime_boundary=runtime).process_command_once(
                    session_id=session.session_id,
                    command_seq=7,
                    consumer_name="runtime_wakeup",
                    seed=73,
                )
            )

        self.assertEqual(result["status"], "commit_conflict")
        self.assertEqual(result["reason"], "view_commit_seq_conflict")
        self.assertEqual(result["processed_command_seq"], 7)
        self.assertEqual(runtime.runtime_status(session.session_id)["status"], "waiting_input")
        self.assertNotEqual(runtime_state_store.statuses[session.session_id].get("status"), "failed")

    def test_decision_request_type_for_method_uses_canonical_mapping(self) -> None:
        self.assertEqual(decision_request_type_for_method("choose_purchase_tile"), "purchase_tile")
        self.assertEqual(decision_request_type_for_method("choose_mark_target"), "mark_target")
        self.assertEqual(decision_request_type_for_method("choose_start_reward"), "start_reward")
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
                "effect_context": {
                    "label": "Tile purchase",
                    "detail": "The player reached a purchasable tile and must choose whether to buy it.",
                    "attribution": "Movement result",
                    "tone": "economy",
                    "source": "move",
                    "intent": "buy",
                    "enhanced": True,
                    "source_family": "movement",
                    "source_name": "arrival_purchase",
                },
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
                "effect_context": {
                    "label": "탈출 노비",
                    "detail": "탈출 노비 효과로 추가 이동 여부를 결정합니다.",
                    "attribution": "Character effect",
                    "tone": "move",
                    "source": "character",
                    "intent": "move",
                    "enhanced": True,
                    "source_family": "character",
                    "source_name": "탈출 노비",
                },
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
                "effect_context": {
                    "label": "무거운 짐",
                    "detail": "Supply threshold reached; choose the burden card to resolve.",
                    "attribution": "Supply threshold",
                    "tone": "economy",
                    "source": "trick",
                    "intent": "cost",
                    "enhanced": True,
                    "source_family": "trick",
                    "source_name": "무거운 짐",
                },
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

    def test_specific_trick_reward_requires_non_empty_legal_choices(self) -> None:
        state = type("State", (), {"rounds_completed": 5, "turn_index": 0})()
        player = type("Player", (), {"cash": 9, "position": 22, "shards": 5})()
        invocation = build_decision_invocation("choose_specific_trick_reward", (state, player, []), {})

        with pytest.raises(ValueError, match="specific_trick_reward_requires_legal_choices"):
            build_routed_decision_call(invocation, fallback_policy="required")

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
        self.assertEqual(
            context["offered_faces"],
            [
                {"card_index": 1, "active_character_name": "산적", "inactive_character_name": "어사"},
                {"card_index": 2, "active_character_name": "건설업자", "inactive_character_name": "자객"},
            ],
        )
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
        self.assertEqual(
            context["choice_faces"],
            [
                {"card_index": 7, "active_character_name": "중매꾼", "inactive_character_name": "객주"},
                {"card_index": 8, "active_character_name": "사기꾼", "inactive_character_name": "건설업자"},
            ],
        )
        self.assertEqual([choice["title"] for choice in routed.legal_choices], ["중매꾼", "사기꾼"])
        self.assertEqual(routed.legal_choices[0]["value"]["inactive_character_name"], "객주")
        self.assertEqual(routed.choice_parser("7", invocation.args, invocation.kwargs, invocation.state, invocation.player), "중매꾼")

    def test_public_context_includes_weather_fields_when_state_has_current_weather(self) -> None:
        weather = type("Weather", (), {"name": "긴급 피난", "effect": "모든 짐 제거 비용이 2배가 됩니다."})()
        state = type("State", (), {"rounds_completed": 1, "turn_index": 2, "current_weather": weather})()
        player = type("Player", (), {"cash": 9, "position": 4, "shards": 1})()

        context = build_public_context("choose_purchase_tile", (state, player, 9, "T2", 4), {})

        self.assertEqual(context["weather_name"], "긴급 피난")
        self.assertEqual(context["weather_effect"], "모든 짐 제거 비용이 2배가 됩니다.")

    def test_authoritative_view_commit_projects_current_weather(self) -> None:
        weather = type("Weather", (), {"name": "외세의 침략", "effect": "모든 참가자는 2냥을 은행에 지불하세요"})()
        state = type("State", (), {"current_weather": weather})()

        view_state = self.runtime_service._build_authoritative_view_state(
            session_id="sess_weather_view",
            state=state,
            checkpoint_payload={
                "players": [],
                "rounds_completed": 2,
                "turn_index": 11,
                "marker_owner_id": 0,
                "current_round_order": [],
            },
            runtime_checkpoint={
                "round_index": 3,
                "turn_index": 11,
            },
            public_snapshot={
                "board": {},
                "players": [],
            },
            parameter_manifest={},
            active_module={},
            step={"status": "waiting_input"},
            commit_seq=42,
            viewer={"role": "seat", "player_id": 1},
        )

        self.assertEqual(view_state["turn_stage"]["weather_name"], "외세의 침략")
        self.assertEqual(view_state["turn_stage"]["weather_effect"], "모든 참가자는 2냥을 은행에 지불하세요")
        self.assertEqual(view_state["scene"]["situation"]["weather_name"], "외세의 침략")
        self.assertEqual(view_state["scene"]["situation"]["weather_effect"], "모든 참가자는 2냥을 은행에 지불하세요")

    def test_authoritative_view_commit_includes_turn_label_and_viewer_display_identity(self) -> None:
        commits = self.runtime_service._build_authoritative_view_commits(
            session_id="sess_commit_identity",
            state=type("State", (), {})(),
            checkpoint_payload={
                "players": [{"player_id": 0}],
                "rounds_completed": 1,
                "turn_index": 5,
                "marker_owner_id": 0,
                "current_round_order": [0],
            },
            runtime_checkpoint={
                "round_index": 2,
                "turn_index": 5,
            },
            module_debug_fields={},
            step={"status": "running"},
            commit_seq=9,
            source_event_seq=42,
            source_messages=[],
            server_time_ms=123456,
        )

        spectator = commits["spectator"]
        player = commits["player:1"]

        self.assertEqual(spectator["round_index"], 2)
        self.assertEqual(spectator["turn_index"], 5)
        self.assertEqual(spectator["turn_label"], "R2-T5")
        self.assertEqual(spectator["runtime"]["turn_label"], "R2-T5")
        self.assertEqual(player["viewer"]["player_id"], 1)
        self.assertEqual(player["viewer"]["legacy_player_id"], 1)
        self.assertEqual(player["viewer"]["seat_index"], 1)
        self.assertEqual(player["viewer"]["turn_order_index"], 1)
        self.assertEqual(player["viewer"]["player_label"], "P1")

    def test_authoritative_view_commit_enriches_viewer_with_session_protocol_identity(self) -> None:
        session = self.session_service.create_session(
            [
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"max_players": 2},
        )
        seat = session.seats[0]

        commits = self.runtime_service._build_authoritative_view_commits(
            session_id=session.session_id,
            state=type("State", (), {})(),
            checkpoint_payload={
                "players": [{"player_id": 0}],
                "rounds_completed": 1,
                "turn_index": 5,
                "marker_owner_id": 0,
                "current_round_order": [0],
            },
            runtime_checkpoint={
                "round_index": 2,
                "turn_index": 5,
            },
            module_debug_fields={},
            step={"status": "running"},
            commit_seq=9,
            source_event_seq=42,
            source_messages=[],
            server_time_ms=123456,
        )

        viewer = commits["player:1"]["viewer"]
        self.assertEqual(viewer["player_id"], 1)
        self.assertEqual(viewer["legacy_player_id"], 1)
        self.assertEqual(viewer["seat_index"], 1)
        self.assertEqual(viewer["turn_order_index"], 1)
        self.assertEqual(viewer["player_label"], "P1")
        self.assertEqual(viewer["public_player_id"], seat.public_player_id)
        self.assertEqual(viewer["seat_id"], seat.seat_id)
        self.assertEqual(viewer["viewer_id"], seat.viewer_id)
        self.assertIsInstance(viewer["public_player_id"], str)
        self.assertNotEqual(viewer["public_player_id"], str(viewer["player_id"]))

    def test_authoritative_view_commit_projects_game_end_beat(self) -> None:
        state = type("State", (), {})()

        view_state = self.runtime_service._build_authoritative_view_state(
            session_id="sess_game_end_view",
            state=state,
            checkpoint_payload={
                "players": [],
                "rounds_completed": 4,
                "turn_index": 18,
                "marker_owner_id": 0,
                "current_round_order": [0, 1, 2, 3],
                "winner_ids": [0],
                "end_reason": "ALIVE_THRESHOLD",
            },
            runtime_checkpoint={
                "round_index": 5,
                "turn_index": 18,
            },
            public_snapshot={
                "board": {},
                "players": [],
            },
            parameter_manifest={},
            active_module={},
            step={"status": "completed"},
            commit_seq=43,
            viewer={"role": "spectator"},
        )

        self.assertEqual(view_state["turn_stage"]["current_actor_player_id"], None)
        self.assertEqual(view_state["turn_stage"]["current_beat_event_code"], "game_end")
        self.assertEqual(view_state["turn_stage"]["prompt_request_type"], "-")
        self.assertEqual(view_state["turn_stage"]["current_beat_detail"], "Winner P1 / ALIVE_THRESHOLD")
        self.assertEqual(view_state["scene"]["situation"]["headline_event_code"], "game_end")
        self.assertEqual(view_state["board"]["winner_ids"], [1])
        self.assertEqual(view_state["board"]["end_reason"], "ALIVE_THRESHOLD")

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
        self.assertEqual(
            context["effect_context"],
            {
                "label": "LAP reward",
                "detail": "The player crossed the start tile and must choose the lap reward allocation.",
                "attribution": "Movement result",
                "tone": "economy",
                "source": "move",
                "intent": "gain",
                "enhanced": True,
                "source_family": "movement",
                "source_name": "lap_reward",
            },
        )

    def test_start_reward_context_reuses_reward_allocation_contract(self) -> None:
        rules = type(
            "StartRules",
            (),
            {
                "points_budget": 20,
                "cash_pool": 30,
                "shards_pool": 18,
                "coins_pool": 18,
                "cash_point_cost": 2,
                "shards_point_cost": 3,
                "coins_point_cost": 3,
            },
        )()
        state = type(
            "State",
            (),
            {
                "rounds_completed": 0,
                "turn_index": 0,
                "start_reward_cash_pool_remaining": 27,
                "start_reward_shards_pool_remaining": 16,
                "start_reward_coins_pool_remaining": 15,
                "config": type("Config", (), {"rules": type("Rules", (), {"start_reward": rules})()})(),
            },
        )()
        player = type(
            "Player",
            (),
            {"cash": 20, "position": 0, "shards": 2, "hand_coins": 0, "score_coins_placed": 0, "tiles_owned": 0},
        )()

        context = build_public_context("choose_start_reward", (state, player), {})

        self.assertEqual(context["description"], "게임 시작 초기 세팅 재화를 선택합니다.")
        self.assertEqual(context["budget"], 20)
        self.assertEqual(context["pools"], {"cash": 27, "shards": 16, "coins": 15})
        self.assertEqual(context["unit_costs"], {"cash": 2, "shards": 3, "coins": 3})
        self.assertEqual(context["effect_context"]["label"], "초기 보상")
        self.assertEqual(context["effect_context"]["source_name"], "start_reward")

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
        self.assertEqual(
            context["effect_context"],
            {
                "label": "재뿌리기",
                "detail": "재뿌리기 효과로 대상 타일을 고릅니다.",
                "attribution": "Trick effect",
                "tone": "effect",
                "source": "trick",
                "intent": "target",
                "enhanced": True,
                "source_family": "trick",
                "source_name": "재뿌리기",
            },
        )

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
        self.assertEqual(
            context["effect_context"],
            {
                "label": "중매꾼",
                "detail": "중매꾼 효과로 인접 타일 구매 여부를 결정합니다.",
                "attribution": "Character effect",
                "tone": "economy",
                "source": "character",
                "intent": "buy",
                "enhanced": True,
                "source_family": "character",
                "source_name": "중매꾼",
            },
        )

    def test_effect_context_covers_remaining_effect_prompt_boundaries(self) -> None:
        state = type("State", (), {"rounds_completed": 2, "turn_index": 1})()
        player = type("Player", (), {"player_id": 1, "cash": 8, "position": 4, "shards": 2})()
        reward_card = type("Card", (), {"deck_index": 17, "name": "월리권", "description": "잔꾀 보상"})()
        relief_target = type("Target", (), {"player_id": 2})()

        cases = [
            (
                "choose_pabal_dice_mode",
                (state, player),
                {},
                {"label": "파발꾼", "source": "character", "intent": "dice", "source_name": "파발꾼"},
            ),
            (
                "choose_runaway_slave_step",
                (state, player, 17, 18, "운수"),
                {},
                {"label": "탈출 노비", "source": "character", "intent": "move", "source_name": "탈출 노비"},
            ),
            (
                "choose_doctrine_relief_target",
                (state, player, [relief_target]),
                {},
                {"label": "교리 감독관", "source": "character", "intent": "relief", "source_name": "교리 감독관"},
            ),
            (
                "choose_specific_trick_reward",
                (state, player, [reward_card]),
                {},
                {"label": "잔꾀 보상", "source": "trick", "intent": "gain", "source_name": "specific_trick_reward"},
            ),
            (
                "choose_active_flip_card",
                (state, player, [5, 7]),
                {},
                {"label": "카드 뒤집기", "source": "round_end", "intent": "flip", "source_name": "round_end_card_flip"},
            ),
        ]

        for method_name, args, kwargs, expected in cases:
            with self.subTest(method_name=method_name):
                context = build_public_context(method_name, args, kwargs)
                effect_context = context["effect_context"]
                for key, value in expected.items():
                    self.assertEqual(effect_context[key], value)
                self.assertTrue(effect_context["enhanced"])

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

    def test_decision_resume_preserves_provider_from_command(self) -> None:
        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:  # noqa: ARG002
                return [
                    {
                        "seq": 7,
                        "type": "decision_submitted",
                        "payload": {
                            "request_id": "r_ai",
                            "player_id": 2,
                            "request_type": "movement",
                            "choice_id": "roll",
                            "provider": "ai",
                            "decision": {"request_id": "r_ai", "choice_id": "roll", "provider": "ai"},
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=SessionService(),
            stream_service=StreamService(),
            prompt_service=PromptService(),
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command("s1", 7)

        self.assertIsNotNone(resume)
        assert resume is not None
        self.assertEqual(resume.provider, "ai")

    def test_http_external_transport_sends_envelope_and_parses_choice_id(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def resolve_ai_decision(self, **kwargs):  # noqa: ANN003
                raise AssertionError("HTTP external AI must not resolve through the in-loop sync AI path")

            def resolve_external_ai_prompt(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                raise PromptRequired(
                    {
                        "request_id": "ai_req_1",
                        "request_type": kwargs["request_type"],
                        "player_id": kwargs["player_id"],
                        "public_context": kwargs["public_context"],
                        "legal_choices": kwargs["legal_choices"],
                        "provider": "ai",
                    }
                )

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

        with self.assertRaises(PromptRequired) as raised:
            transport.resolve(call)

        self.assertEqual(sender_calls, [])
        self.assertEqual(raised.exception.prompt["provider"], "ai")
        self.assertEqual(gateway.calls[0]["public_context"]["participant_transport"], "http")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_resolution_status"], "pending")
        self.assertEqual(gateway.calls[0]["public_context"]["external_ai_attempt_count"], 0)
        self.assertEqual([choice["choice_id"] for choice in gateway.calls[0]["legal_choices"]], ["yes", "no"])

    def test_http_external_transport_attaches_module_continuation_metadata(self) -> None:
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import _HttpExternalAiTransport

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        class _FakeGateway:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def _stable_ai_request_id(self, **kwargs):  # noqa: ANN003
                self.calls.append({"stable_ai_request_id": kwargs})
                return "sess_http_module:ai_purchase_tile:p1"

            def resolve_external_ai_prompt(self, **kwargs):  # noqa: ANN003
                self.calls.append(kwargs)
                prompt = {
                    "request_id": kwargs["request_id"],
                    "request_type": kwargs["request_type"],
                    "player_id": kwargs["player_id"],
                    "public_context": kwargs["public_context"],
                    "legal_choices": kwargs["legal_choices"],
                    "provider": "ai",
                }
                prompt.update(kwargs["prompt_metadata"])
                raise PromptRequired(prompt)

        gateway = _FakeGateway()
        transport = _HttpExternalAiTransport(
            session_id="sess_http_module",
            ai_fallback=_FakeAiPolicy(),
            gateway=gateway,  # type: ignore[arg-type]
            seat=1,
            config={"transport": "http", "endpoint": "http://bot-worker.local/decide"},
            sender=lambda _envelope: {"choice_id": "yes"},
        )
        state = self._module_state(
            frame_id="turn:2:p0",
            module_id="mod:turn:2:p0:purchase",
            module_type="PurchaseDecisionModule",
            module_cursor="purchase:await_choice",
        )
        player = type("Player", (), {"player_id": 0, "cash": 5, "position": 9, "shards": 1})()
        call = build_routed_decision_call(
            build_decision_invocation("choose_purchase_tile", (state, player, 9, "T2", 4), {"source": "landing"}),
            fallback_policy="ai",
        )

        with self.assertRaises(PromptRequired) as raised:
            transport.resolve(call)

        prompt = raised.exception.prompt
        self.assertEqual(prompt["request_id"], "sess_http_module:ai_purchase_tile:p1")
        self.assertEqual(prompt["runner_kind"], "module")
        self.assertEqual(prompt["resume_token"], state.runtime_active_prompt.resume_token)
        self.assertEqual(prompt["frame_id"], "turn:2:p0")
        self.assertEqual(prompt["module_id"], "mod:turn:2:p0:purchase")
        self.assertEqual(prompt["module_type"], "PurchaseDecisionModule")
        self.assertEqual(prompt["module_cursor"], "purchase:await_choice")
        self.assertEqual(prompt["runtime_module"]["module_type"], "PurchaseDecisionModule")
        self.assertEqual(gateway.calls[-1]["prompt_metadata"]["resume_token"], state.runtime_active_prompt.resume_token)

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
                self.assertIn(status_local.get("status"), {"running", "completed"})
                for _ in range(30):
                    status_local = self.runtime_service.runtime_status(session.session_id)
                    if status_local.get("status") == "completed":
                        break
                    await asyncio.sleep(0.01)
                return status_local

            status = asyncio.run(_exercise())
            for _ in range(3):
                status = self.runtime_service.runtime_status(session.session_id)
                if status.get("status") == "completed":
                    break
            self.assertEqual(status.get("status"), "completed")
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

    def test_run_engine_sync_requires_game_state_store_after_cutover(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        loop = asyncio.new_event_loop()
        try:
            with self.assertRaisesRegex(RuntimeError, "module_runtime_requires_game_state_store"):
                self.runtime_service._run_engine_sync(loop, session.session_id, seed=42, policy_mode=None)
        finally:
            loop.close()

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
                    self._module_prompt(
                        {
                        "request_id": "bridge_req_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                        }
                    ),
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_prompt = None
            for _ in range(100):
                pending_prompt = self.prompt_service.get_pending_prompt(
                    "bridge_req_1",
                    session_id="sess_bridge_test",
                )
                if pending_prompt is not None:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None

            decision_state = self.prompt_service.submit_decision(
                self._module_decision(pending_prompt.payload, "roll", player_id=1)
            )
            self.assertEqual(decision_state["status"], "accepted")

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "roll")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_test"),
                loop,
            ).result(timeout=2.0)
            public_request_id = pending_prompt.request_id
            self.assertTrue(
                any(
                    msg.type == "prompt"
                    and msg.payload.get("request_id") == public_request_id
                    and msg.payload.get("legacy_request_id") == "bridge_req_1"
                    for msg in published
                )
            )
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == public_request_id
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertEqual(len(resolved_all), 1)
            self.assertEqual(requested.payload.get("legacy_request_id"), "bridge_req_1")
            self.assertEqual(resolved.payload.get("legacy_request_id"), "bridge_req_1")
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
                    self._module_prompt(
                        {
                        "request_id": "bridge_req_nonblocking_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                        }
                    ),
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            public_request_id = self._assert_public_prompt_request_id(
                raised.exception.prompt,
                "bridge_req_nonblocking_1",
            )
            self.assertTrue(self.prompt_service.has_pending_for_session("sess_bridge_nonblocking_test"))
            lifecycle = self.prompt_service.get_prompt_lifecycle(
                "bridge_req_nonblocking_1",
                session_id="sess_bridge_nonblocking_test",
            )
            self.assertIsNotNone(lifecycle)
            assert lifecycle is not None
            self.assertEqual(lifecycle["state"], "created")
            self.assertEqual(lifecycle["request_id"], public_request_id)
            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_nonblocking_test"),
                loop,
            ).result(timeout=2.0)
            self.assertEqual(published, [])

            decision_state = self.prompt_service.submit_decision(
                self._module_decision(raised.exception.prompt, "roll", player_id=1)
            )
            self.assertEqual(decision_state["status"], "accepted")

            replayed = bridge._inner._ask(  # type: ignore[attr-defined]
                self._module_prompt(
                    {
                    "request_id": "bridge_req_nonblocking_1",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 2000,
                    "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                    "fallback_policy": "timeout_fallback",
                    "public_context": {},
                    }
                ),
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
                    self._module_prompt(
                        {
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {"round_index": 2, "turn_index": 3},
                        }
                    ),
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            prompt = raised.exception.prompt
            self.assertEqual(prompt["prompt_instance_id"], 5)
            self._assert_public_prompt_request_id(
                prompt,
                (
                    "sess_bridge_prompt_seq_test:prompt:frame:turn%3A1%3Ap0:"
                    "module:mod%3Aturn%3A1%3Ap0%3Atest_prompt:cursor:test%3Aawait_choice:"
                    "p1:movement:5"
                ),
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

        self.assertIsNone(
            self.prompt_service.get_pending_prompt(
                first.request_id,
                session_id="sess_prompt_supersede",
            )
        )
        self.assertIsNotNone(
            self.prompt_service.get_pending_prompt(
                second.request_id,
                session_id="sess_prompt_supersede",
            )
        )
        stale_result = self.prompt_service.submit_decision(
            {
                "session_id": "sess_prompt_supersede",
                "request_id": first.request_id,
                "player_id": 1,
                "choice_id": "none",
            }
        )
        self.assertEqual(stale_result, {"status": "stale", "reason": "already_resolved"})

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
            config={"seed": 314305415, "runtime": {"ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            first = runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                314305415,
                None,
            )
            self.assertEqual(first["status"], "waiting_input")
            self.assertEqual(first["request_type"], "draft_card")
            self.assertEqual(first["player_id"], 1)

            with self.prompt_service._lock:  # type: ignore[attr-defined]
                pending_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            legal_choices = list(pending_prompt.payload["legal_choices"])
            legal_choice_ids = [str(choice["choice_id"]) for choice in legal_choices]
            self.assertIn("6", legal_choice_ids)
            applause_choice = next(
                (
                    choice
                    for choice in legal_choices
                    if str(choice["choice_id"]) == "6"
                    and str(choice.get("title") or choice.get("label")) == "박수"
                ),
                None,
            )
            self.assertIsNotNone(applause_choice)
            selected_choice_id = str(applause_choice["choice_id"])
            selected_choice_title = str(applause_choice.get("title") or applause_choice.get("label"))
            self.prompt_service.submit_decision(
                {
                    "request_id": pending_prompt.request_id,
                    "player_id": 1,
                    "choice_id": selected_choice_id,
                    "resume_token": pending_prompt.payload["resume_token"],
                    "frame_id": pending_prompt.payload["frame_id"],
                    "module_id": pending_prompt.payload["module_id"],
                    "module_type": pending_prompt.payload["module_type"],
                    "module_cursor": pending_prompt.payload["module_cursor"],
                }
            )

            second = runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                314305415,
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
            final_choice_ids = {str(choice["choice_id"]) for choice in final_prompt.payload["legal_choices"]}
            final_choice_titles = {
                str(choice.get("title") or choice.get("label"))
                for choice in final_prompt.payload["legal_choices"]
            }
            self.assertIn(selected_choice_id, final_choice_ids)
            self.assertIn(selected_choice_title, final_choice_titles)
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

    def test_command_scope_loop_commits_only_terminal_boundary(self) -> None:
        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 314305415, "runtime": {"ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            first = runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                314305415,
                None,
            )
            self.assertEqual(first["status"], "waiting_input")
            self.assertEqual(first["request_type"], "draft_card")

            with self.prompt_service._lock:  # type: ignore[attr-defined]
                pending_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            selected_choice_id = str(pending_prompt.payload["legal_choices"][0]["choice_id"])
            decision_payload = {
                "request_id": pending_prompt.request_id,
                "player_id": 1,
                "choice_id": selected_choice_id,
                "resume_token": pending_prompt.payload["resume_token"],
                "frame_id": pending_prompt.payload["frame_id"],
                "module_id": pending_prompt.payload["module_id"],
                "module_type": pending_prompt.payload["module_type"],
                "module_cursor": pending_prompt.payload["module_cursor"],
            }
            accepted = self.prompt_service.submit_decision(decision_payload)
            self.assertEqual(accepted["status"], "accepted")
            command_store.commands.append(
                {
                    "seq": 1,
                    "type": "decision_submitted",
                    "session_id": session.session_id,
                    "payload": {
                        **decision_payload,
                        "request_type": pending_prompt.payload["request_type"],
                        "decision": dict(decision_payload),
                    },
                }
            )

            store.commits.clear()
            second = runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                314305415,
                None,
                first_command_consumer_name="runtime-worker",
                first_command_seq=1,
            )

            self.assertEqual(second["status"], "waiting_input")
            self.assertEqual(second["request_type"], "final_character")
            self.assertGreaterEqual(second["module_transition_count"], 1)
            self.assertEqual(second["redis_commit_count"], 1)
            self.assertEqual(second["view_commit_count"], 1)
            self.assertEqual(len(store.commits), 1)
            self.assertEqual(store.commits[0]["command_seq"], 1)
            self.assertEqual(store.commits[0]["command_consumer_name"], "runtime-worker")
            commit_envelope = store.commits[0]["checkpoint"]["command_commit_envelope"]
            self.assertTrue(commit_envelope["consumer_offset"])
            self.assertEqual(commit_envelope["offset_consumer"], "runtime-worker")
            self.assertEqual(commit_envelope["offset_seq"], 1)
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
            runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                42,
                None,
            )
            with self.prompt_service._lock:  # type: ignore[attr-defined]
                first_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            self.prompt_service.submit_decision(
                {
                    "request_id": first_prompt.request_id,
                    "player_id": 1,
                    "choice_id": first_prompt.payload["legal_choices"][0]["choice_id"],
                    "resume_token": first_prompt.payload["resume_token"],
                    "frame_id": first_prompt.payload["frame_id"],
                    "module_id": first_prompt.payload["module_id"],
                    "module_type": first_prompt.payload["module_type"],
                    "module_cursor": first_prompt.payload["module_cursor"],
                }
            )

            second = runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                42,
                None,
            )
            self.assertEqual(second["status"], "waiting_input")
            self.assertEqual(second["request_type"], "draft_card")
            with self.prompt_service._lock:  # type: ignore[attr-defined]
                draft_prompt = next(iter(self.prompt_service._pending.values()))  # type: ignore[attr-defined]
            self.prompt_service.submit_decision(
                {
                    "request_id": draft_prompt.request_id,
                    "player_id": 1,
                    "choice_id": draft_prompt.payload["legal_choices"][0]["choice_id"],
                    "resume_token": draft_prompt.payload["resume_token"],
                    "frame_id": draft_prompt.payload["frame_id"],
                    "module_id": draft_prompt.payload["module_id"],
                    "module_type": draft_prompt.payload["module_type"],
                    "module_cursor": draft_prompt.payload["module_cursor"],
                }
            )

            runtime._run_engine_transition_loop_sync(
                loop,
                session.session_id,
                42,
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

    def test_runtime_service_module_transition_does_not_embed_card_rule_suppression(self) -> None:
        source = Path("apps/server/src/services/runtime_service.py").read_text(encoding="utf-8")
        transition_start = source.index("    def _run_engine_transition_once_sync")
        transition_end = source.index("    def _latest_stream_seq_sync", transition_start)
        transition_source = source[transition_start:transition_end]

        self.assertNotIn("_has_live_eosa_player", transition_source)
        self.assertNotIn("_TURN_START_MARK_CHARACTERS", transition_source)
        self.assertNotIn("_MUROE_MARK_CHARACTERS", transition_source)

    def test_stale_module_continuation_rejected_without_engine_advance(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_1",
            prompt_instance_id=1,
            resume_token="token_1",
            frame_id="turn:1:p0",
            module_id="mod:turn:1:p0:movement",
            module_type="MapMoveModule",
            module_cursor="move:await_choice",
            player_id=0,
            request_type="movement",
            legal_choices=[{"choice_id": "roll"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_1",
                    "player_id": 1,
                    "request_type": "movement",
                    "choice_id": "roll",
                    "resume_token": "token_1",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:old",
                    "decision": {},
                },
            }
        )

        with patch.object(
            engine.GameEngine,
            "run_next_transition",
            side_effect=AssertionError("stale module command must not advance engine"),
        ):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "module cursor mismatch")
        self.assertEqual(command_store.offsets, [("runtime-worker", session.session_id, 1)])
        self.assertEqual(store.commits, [])

    def test_module_resume_rejects_module_type_mismatch_without_engine_advance(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_1",
            prompt_instance_id=1,
            resume_token="token_1",
            frame_id="turn:1:p0",
            module_id="mod:turn:1:p0:target_judicator",
            module_type="TargetJudicatorModule",
            module_cursor="await_mark_target",
            player_id=0,
            request_type="choose_mark_target",
            legal_choices=[{"choice_id": "p1"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_1",
                    "player_id": 1,
                    "request_type": "choose_mark_target",
                    "choice_id": "p1",
                    "resume_token": "token_1",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:target_judicator",
                    "module_type": "CharacterStartModule",
                    "module_cursor": "await_mark_target",
                    "decision": {},
                },
            }
        )

        with patch.object(
            engine.GameEngine,
            "run_next_transition",
            side_effect=AssertionError("mismatched module type must not advance engine"),
        ):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "module type mismatch")
        self.assertEqual(command_store.offsets, [("runtime-worker", session.session_id, 1)])
        self.assertEqual(store.commits, [])

    def test_valid_module_continuation_passed_to_engine_transition(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_1",
            prompt_instance_id=1,
            resume_token="token_1",
            frame_id="turn:1:p0",
            module_id="mod:turn:1:p0:movement",
            module_type="MapMoveModule",
            module_cursor="move:await_choice",
            player_id=0,
            request_type="movement",
            legal_choices=[{"choice_id": "roll"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_1",
                    "player_id": 1,
                    "request_type": "movement",
                    "choice_id": "roll",
                    "resume_token": "token_1",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:await_choice",
                    "decision": {},
                },
            }
        )
        seen: list[object] = []

        def _fake_run_next_transition(self, state, decision_resume=None):  # noqa: ANN001
            del self, state
            seen.append(decision_resume)
            return {"status": "committed", "runner_kind": "module", "module_type": "MapMoveModule"}

        with patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "committed")
        self.assertEqual(command_store.offsets, [])
        self.assertEqual(len(seen), 1)
        self.assertIsNotNone(seen[0])
        self.assertEqual(getattr(seen[0], "request_id"), "req_1")
        self.assertEqual(getattr(seen[0], "request_type"), "movement")
        self.assertEqual(getattr(seen[0], "module_cursor"), "move:await_choice")
        self.assertIsNone(store.current_state.get("runtime_active_prompt"))
        self.assertIsNone(store.current_state.get("runtime_active_prompt_batch"))
        self.assertEqual(store.commits[0]["expected_previous_commit_seq"], 4)
        self.assertEqual(store.commits[0]["checkpoint"]["base_commit_seq"], 4)
        self.assertEqual(store.commits[0]["checkpoint"]["latest_commit_seq"], 5)
        self.assertEqual(store.commits[0]["runtime_event_payload"]["base_commit_seq"], 4)
        self.assertNotIn("runtime_active_prompt_request_id", store.commits[0]["runtime_event_payload"])

    def test_command_boundary_internal_transition_stages_state_without_view_commit_build(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime_state_store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
            runtime_state_store=runtime_state_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_1",
            prompt_instance_id=1,
            resume_token="token_1",
            frame_id="turn:1:p0",
            module_id="mod:turn:1:p0:movement",
            module_type="MapMoveModule",
            module_cursor="move:await_choice",
            player_id=0,
            request_type="movement",
            legal_choices=[{"choice_id": "roll"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_1",
                    "player_id": 1,
                    "request_type": "movement",
                    "choice_id": "roll",
                    "resume_token": "token_1",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:await_choice",
                    "decision": {},
                },
            }
        )
        boundary_store = CommandBoundaryGameStateStore(store, session_id=session.session_id, base_commit_seq=4)
        runtime._game_state_store = boundary_store

        def _fake_run_next_transition(self, state, decision_resume=None):  # noqa: ANN001
            del self, decision_resume
            state.runtime_active_prompt = None
            state.turn_index = int(getattr(state, "turn_index", 0) or 0) + 1
            return {"status": "committed", "runner_kind": "module", "module_type": "MapMoveModule"}

        with (
            patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition),
            patch.object(
                runtime,
                "_source_history_sync",
                side_effect=AssertionError("internal command transition must not read source history"),
            ),
            patch.object(
                runtime,
                "_build_authoritative_view_commits",
                side_effect=AssertionError("internal command transition must not build view commits"),
            ),
        ):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
                publish_external_side_effects=False,
            )

        self.assertEqual(result["status"], "committed")
        self.assertEqual(store.commits, [])
        self.assertIsNone(boundary_store.deferred_commit())
        self.assertEqual(boundary_store.redis_commit_count, 0)
        self.assertEqual(boundary_store.view_commit_count, 0)
        self.assertEqual(boundary_store.internal_state_stage_count, 1)
        self.assertNotIn(session.session_id, runtime_state_store.statuses)
        staged_state = boundary_store.load_current_state(session.session_id)
        self.assertIsInstance(staged_state, dict)
        self.assertIsNone(staged_state.get("runtime_active_prompt"))
        self.assertEqual(staged_state.get("turn_index"), 1)

    def test_command_boundary_loop_uses_per_call_store_without_swapping_shared_store(self) -> None:
        store = _MutableGameStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            runtime_state_store=_RuntimeStateStoreStub(),
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        captured_boundary_stores: list[object] = []

        def _fake_prepare(*args, **kwargs):  # noqa: ANN002, ANN003
            del args
            self.assertIs(runtime._game_state_store, store)
            boundary_store = kwargs.get("game_state_store_override")
            self.assertIsNotNone(boundary_store)
            self.assertIsNot(boundary_store, store)
            captured_boundary_stores.append(boundary_store)
            return object()

        def _fake_transition(*args, **kwargs):  # noqa: ANN002, ANN003
            del args
            self.assertIs(runtime._game_state_store, store)
            boundary_store = kwargs.get("game_state_store_override")
            self.assertIs(boundary_store, captured_boundary_stores[0])
            boundary_store.commit_transition(
                session.session_id,
                current_state={"session_id": session.session_id, "tiles": []},
                checkpoint={
                    "schema_version": 3,
                    "session_id": session.session_id,
                    "runner_kind": "module",
                    "has_snapshot": True,
                    "base_commit_seq": 4,
                    "latest_commit_seq": 5,
                },
                view_state={},
                view_commits={"spectator": {"commit_seq": 5, "view_state": {"ok": True}}},
                expected_previous_commit_seq=4,
            )
            return {
                "status": "waiting_input",
                "reason": "prompt_required",
                "runner_kind": "module",
                "module_type": "DraftModule",
                "request_id": "req_next",
                "request_type": "draft_card",
                "player_id": 2,
            }

        with (
            patch.object(runtime, "_prepare_runtime_transition_context_sync", side_effect=_fake_prepare),
            patch.object(runtime, "_run_engine_transition_once_sync", side_effect=_fake_transition),
            patch.object(runtime, "_emit_latest_view_commit_sync", return_value=None),
            patch.object(runtime, "_materialize_prompt_boundaries_from_checkpoint_sync", return_value=None),
        ):
            result = runtime._run_engine_command_boundary_loop_sync(
                None,
                session.session_id,
                42,
                None,
                max_transitions=1,
                first_command_consumer_name="runtime-worker",
                first_command_seq=1,
            )

        self.assertEqual(result["status"], "waiting_input")
        self.assertEqual(result["redis_commit_count"], 1)
        self.assertEqual(result["view_commit_count"], 1)
        self.assertEqual(result["internal_redis_commit_attempt_count"], 1)
        self.assertEqual(len(store.commits), 1)
        self.assertIs(runtime._game_state_store, store)

    def test_command_boundary_loop_blocks_final_commit_when_runtime_lease_is_lost(self) -> None:
        store = _MutableGameStateStoreStub()
        runtime_state_store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            runtime_state_store=runtime_state_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        runtime_state_store.leases[session.session_id] = "other-runtime-worker"
        captured_boundary_stores: list[object] = []

        def _fake_prepare(*args, **kwargs):  # noqa: ANN002, ANN003
            del args
            boundary_store = kwargs.get("game_state_store_override")
            self.assertIsNotNone(boundary_store)
            captured_boundary_stores.append(boundary_store)
            return object()

        def _fake_transition(*args, **kwargs):  # noqa: ANN002, ANN003
            del args
            boundary_store = kwargs.get("game_state_store_override")
            self.assertIs(boundary_store, captured_boundary_stores[0])
            boundary_store.commit_transition(
                session.session_id,
                current_state={"session_id": session.session_id, "tiles": []},
                checkpoint={
                    "schema_version": 3,
                    "session_id": session.session_id,
                    "runner_kind": "module",
                    "has_snapshot": True,
                    "base_commit_seq": 4,
                    "latest_commit_seq": 5,
                },
                view_state={},
                view_commits={"spectator": {"commit_seq": 5, "view_state": {"ok": True}}},
                expected_previous_commit_seq=4,
            )
            return {
                "status": "waiting_input",
                "reason": "prompt_required",
                "runner_kind": "module",
                "module_type": "DraftModule",
                "request_id": "req_next",
                "request_type": "draft_card",
                "player_id": 2,
            }

        with (
            patch.object(runtime, "_prepare_runtime_transition_context_sync", side_effect=_fake_prepare),
            patch.object(runtime, "_run_engine_transition_once_sync", side_effect=_fake_transition),
            patch.object(runtime, "_emit_latest_view_commit_sync", return_value=None),
            patch.object(runtime, "_materialize_prompt_boundaries_from_checkpoint_sync", return_value=None),
        ):
            result = runtime._run_engine_command_boundary_loop_sync(
                None,
                session.session_id,
                42,
                None,
                max_transitions=1,
                first_command_consumer_name="runtime-worker",
                first_command_seq=1,
            )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "runtime_lease_lost_before_commit")
        self.assertEqual(result["lease_owner"], "other-runtime-worker")
        self.assertEqual(result["redis_commit_count"], 0)
        self.assertEqual(result["view_commit_count"], 0)
        self.assertEqual(result["internal_redis_commit_attempt_count"], 1)
        self.assertEqual(store.commits, [])

    def test_command_boundary_loop_hydrates_and_prepares_engine_once(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
            runtime_state_store=_RuntimeStateStoreStub(),
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_1",
            prompt_instance_id=1,
            resume_token="token_1",
            frame_id="turn:1:p0",
            module_id="mod:turn:1:p0:movement",
            module_type="MapMoveModule",
            module_cursor="move:await_choice",
            player_id=0,
            request_type="movement",
            legal_choices=[{"choice_id": "roll"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_1",
                    "player_id": 1,
                    "request_type": "movement",
                    "choice_id": "roll",
                    "resume_token": "token_1",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:await_choice",
                    "decision": {},
                },
            }
        )

        state_ids: list[int] = []
        prepare_calls = 0
        original_prepare_run = engine.GameEngine.prepare_run
        original_hydrate = runtime._hydrate_engine_state  # type: ignore[attr-defined]

        def _fake_prepare_run(self, initial_state=None):  # noqa: ANN001
            nonlocal prepare_calls
            prepare_calls += 1
            return original_prepare_run(self, initial_state=initial_state)

        def _fake_run_next_transition(self, state, decision_resume=None):  # noqa: ANN001
            del self, decision_resume
            state_ids.append(id(state))
            state.runtime_active_prompt = None
            state.turn_index = int(getattr(state, "turn_index", 0) or 0) + 1
            if len(state_ids) < 3:
                return {
                    "status": "committed",
                    "runner_kind": "module",
                    "module_type": "MapMoveModule",
                    "module_cursor": f"internal:{len(state_ids)}",
                }
            return {
                "status": "waiting_input",
                "reason": "prompt_required",
                "runner_kind": "module",
                "module_type": "MapMoveModule",
                "module_cursor": "await_next",
                "request_id": "req_next",
                "request_type": "movement",
                "player_id": 1,
            }

        with (
            patch.object(runtime, "_hydrate_engine_state", wraps=original_hydrate) as hydrate_spy,
            patch.object(engine.GameEngine, "prepare_run", _fake_prepare_run),
            patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition),
            patch.object(runtime, "_source_history_sync", return_value=[]),
            patch.object(
                runtime,
                "_build_authoritative_view_commits",
                return_value={"spectator": {"view_state": {"ok": True}}},
            ),
            patch.object(runtime, "_latest_stream_seq_sync", return_value=0),
            patch.object(runtime, "_emit_latest_view_commit_sync", return_value=None),
            patch.object(runtime, "_materialize_prompt_boundaries_from_checkpoint_sync", return_value=None),
        ):
            result = runtime._run_engine_command_boundary_loop_sync(
                None,
                session.session_id,
                42,
                None,
                max_transitions=5,
                first_command_consumer_name="runtime-worker",
                first_command_seq=1,
            )

        self.assertEqual(result["status"], "waiting_input")
        self.assertEqual(result["transitions"], 3)
        self.assertEqual(hydrate_spy.call_count, 1)
        self.assertEqual(prepare_calls, 1)
        self.assertEqual(len(set(state_ids)), 1)
        self.assertEqual(len(store.commits), 1)
        self.assertEqual(store.commits[0]["checkpoint"]["latest_commit_seq"], 5)

    def test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.prompt_sequence = 60
        state.pending_prompt_request_id = f"{session.session_id}:r1:t3:p1:trick_tile_target:60"
        state.pending_prompt_type = "trick_tile_target"
        state.pending_prompt_player_id = 1
        state.pending_prompt_instance_id = 60
        state.runtime_active_prompt = PromptContinuation(
            request_id=state.pending_prompt_request_id,
            prompt_instance_id=60,
            resume_token="resume_current",
            frame_id="seq:action:1:p0:89",
            module_id="mod:seq:action:1:p0:89:fortuneresolve",
            module_type="FortuneResolveModule",
            module_cursor="await_action_prompt",
            player_id=0,
            request_type="trick_tile_target",
            legal_choices=[{"choice_id": "8"}, {"choice_id": "12"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 104,
            "decision_resume_request_id": f"{session.session_id}:r1:t3:p1:trick_tile_target:58",
            "decision_resume_request_type": "trick_tile_target",
            "decision_resume_player_id": 1,
            "decision_resume_choice_id": "6",
            "decision_resume_prompt_instance_id": 58,
            "decision_resume_frame_id": "seq:action:1:p0:89",
            "decision_resume_module_id": "mod:seq:action:1:p0:89:fortuneresolve",
            "decision_resume_module_type": "FortuneResolveModule",
            "decision_resume_module_cursor": "await_action_prompt",
        }
        command_store.commands.append(
            {
                "seq": 32,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": state.pending_prompt_request_id,
                    "player_id": 1,
                    "request_type": "trick_tile_target",
                    "choice_id": "8",
                    "choice_payload": {"tile_index": 8},
                    "resume_token": "resume_current",
                    "prompt_instance_id": 60,
                    "frame_id": "seq:action:1:p0:89",
                    "module_id": "mod:seq:action:1:p0:89:fortuneresolve",
                    "module_type": "FortuneResolveModule",
                    "module_cursor": "await_action_prompt",
                    "decision": {},
                },
            }
        )
        seen_prompt_sequences: list[int] = []
        original_set_prompt_sequence = _ServerDecisionPolicyBridge.set_prompt_sequence

        def _capture_prompt_sequence(self, value: int) -> None:  # noqa: ANN001
            seen_prompt_sequences.append(int(value))
            original_set_prompt_sequence(self, value)

        def _fake_run_next_transition(self, state, decision_resume=None):  # noqa: ANN001
            del self, state, decision_resume
            return {"status": "committed", "runner_kind": "module", "module_type": "FortuneResolveModule"}

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            with (
                patch.object(_ServerDecisionPolicyBridge, "set_prompt_sequence", _capture_prompt_sequence),
                patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition),
            ):
                result = runtime._run_engine_transition_once_sync(
                    loop,
                    session.session_id,
                    42,
                    None,
                    True,
                    "runtime-worker",
                    32,
                )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

        self.assertEqual(result["status"], "committed")
        self.assertEqual(seen_prompt_sequences[:1], [57])

    def test_module_transition_discards_when_commit_seq_changes_before_write(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_1",
            prompt_instance_id=1,
            resume_token="token_1",
            frame_id="turn:1:p0",
            module_id="mod:turn:1:p0:movement",
            module_type="MapMoveModule",
            module_cursor="move:await_choice",
            player_id=0,
            request_type="movement",
            legal_choices=[{"choice_id": "roll"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_1",
                    "player_id": 1,
                    "request_type": "movement",
                    "choice_id": "roll",
                    "resume_token": "token_1",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:await_choice",
                    "decision": {},
                },
            }
        )
        seen: list[object] = []

        def _fake_run_next_transition(self, state, decision_resume=None):  # noqa: ANN001
            del self, state
            seen.append(decision_resume)
            return {"status": "committed", "runner_kind": "module", "module_type": "MapMoveModule"}

        with (
            patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition),
            patch.object(runtime, "_latest_view_commit_seq", side_effect=[4, 5]),
        ):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "view_commit_seq_changed_before_commit")
        self.assertEqual(result["base_commit_seq"], 4)
        self.assertEqual(result["latest_commit_seq"], 5)
        self.assertEqual(result["attempted_commit_seq"], 5)
        self.assertEqual(len(seen), 1)
        self.assertEqual(command_store.offsets, [])
        self.assertEqual(store.commits, [])

    def test_module_transition_discards_when_runtime_lease_is_lost_before_write(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from state import GameState

        store = _MutableGameStateStoreStub()
        runtime_state_store = _RuntimeStateStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            runtime_state_store=runtime_state_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "latest_commit_seq": 4,
        }
        runtime_state_store.leases[session.session_id] = "other-runtime-worker"

        def _fake_run_next_transition(self, state, decision_resume=None):  # noqa: ANN001
            del self, state, decision_resume
            return {"status": "committed", "runner_kind": "module", "module_type": "MapMoveModule"}

        with (
            patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition),
            patch.object(runtime, "_latest_view_commit_seq", return_value=4),
        ):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "runtime_lease_lost_before_commit")
        self.assertEqual(result["lease_owner"], "other-runtime-worker")
        self.assertEqual(result["base_commit_seq"], 4)
        self.assertEqual(result["attempted_commit_seq"], 5)
        self.assertEqual(store.commits, [])

    def test_simultaneous_batch_continuation_survives_service_reconstruction(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        first_runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        self.session_service.start_session(session.session_id, session.host_token)
        config = first_runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        frame = build_resupply_frame(
            2,
            5,
            parent_frame_id="round:2",
            parent_module_id="mod:round:2:resupply_scheduler",
            participants=[0, 1],
        )
        frame.status = "suspended"
        module = next(module for module in frame.module_queue if module.module_type == "ResupplyModule")
        frame.active_module_id = module.module_id
        module.status = "suspended"
        module.cursor = "await_resupply_batch:5"
        state.runtime_frame_stack = [frame]
        batch = PromptApi().create_batch(
            batch_id="batch:simul:resupply:2:5",
            frame=frame,
            module=module,
            participant_player_ids=[0, 1],
            request_type="burden_exchange",
            legal_choices_by_player_id={
                0: [{"choice_id": "yes"}, {"choice_id": "no"}],
                1: [{"choice_id": "yes"}, {"choice_id": "no"}],
            },
            public_context_by_player_id={
                0: {"round_index": 2, "turn_index": 5, "card_name": "무거운 짐"},
                1: {"round_index": 2, "turn_index": 5, "card_name": "박수"},
            },
            eligibility_snapshot={
                "threshold": 3,
                "targets_by_player": {"0": 101, "1": 102},
                "eligible_burden_deck_indices_by_player": {"0": [101], "1": [102]},
                "processed_burden_deck_indices_by_player": {"0": [100]},
            },
        )
        batch.responses_by_player_id[0] = {"choice_id": "yes"}
        batch.missing_player_ids = [1]
        state.runtime_active_prompt_batch = batch
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
            "runtime_active_prompt_batch": batch.to_payload(),
        }
        prompt = batch.prompts_by_player_id[1]
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": prompt.request_id,
                    "player_id": 2,
                    "request_type": "burden_exchange",
                    "choice_id": "no",
                    "resume_token": prompt.resume_token,
                    "frame_id": prompt.frame_id,
                    "module_id": prompt.module_id,
                    "module_type": prompt.module_type,
                    "module_cursor": prompt.module_cursor,
                    "batch_id": batch.batch_id,
                    "decision": {},
                },
            }
        )

        restarted_runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=PromptService(),
            game_state_store=store,
            command_store=command_store,
        )
        seen: list[dict] = []

        def _fake_run_next_transition(self, resumed_state, decision_resume=None):  # noqa: ANN001
            del self
            active_batch = resumed_state.runtime_active_prompt_batch
            seen.append(
                {
                    "batch_id": active_batch.batch_id,
                    "missing_player_ids": list(active_batch.missing_player_ids),
                    "responses_by_player_id": dict(active_batch.responses_by_player_id),
                    "eligibility_snapshot": dict(active_batch.eligibility_snapshot),
                    "frame_type": resumed_state.runtime_frame_stack[0].frame_type,
                    "module_cursor": next(
                        module
                        for module in resumed_state.runtime_frame_stack[0].module_queue
                        if module.module_type == "ResupplyModule"
                    ).cursor,
                    "resume_batch_id": decision_resume.batch_id,
                    "resume_request_id": decision_resume.request_id,
                    "resume_player_id": decision_resume.player_id,
                    "resume_choice_id": decision_resume.choice_id,
                }
            )
            return {
                "status": "waiting_input",
                "reason": "simultaneous_batch_waiting",
                "runner_kind": "module",
                "frame_id": frame.frame_id,
                "module_id": module.module_id,
                "module_type": "ResupplyModule",
                "module_cursor": "await_resupply_batch:5",
            }

        with patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition):
            result = restarted_runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "waiting_input")
        self.assertEqual(command_store.offsets, [])
        self.assertEqual(
            seen,
            [
                {
                    "batch_id": "batch:simul:resupply:2:5",
                    "missing_player_ids": [1],
                    "responses_by_player_id": {0: {"choice_id": "yes"}},
                    "eligibility_snapshot": {
                        "threshold": 3,
                        "targets_by_player": {"0": 101, "1": 102},
                        "eligible_burden_deck_indices_by_player": {"0": [101], "1": [102]},
                        "processed_burden_deck_indices_by_player": {"0": [100]},
                    },
                    "frame_type": "simultaneous",
                    "module_cursor": "await_resupply_batch:5",
                    "resume_batch_id": "batch:simul:resupply:2:5",
                    "resume_request_id": prompt.request_id,
                    "resume_player_id": 2,
                    "resume_choice_id": "no",
                }
            ],
        )
        self.assertEqual(
            store.commits[0]["checkpoint"]["runtime_active_prompt_batch"]["batch_id"],
            "batch:simul:resupply:2:5",
        )
        self.assertEqual(
            store.commits[0]["checkpoint"]["runtime_active_prompt_batch"]["eligibility_snapshot"],
            {
                "threshold": 3,
                "targets_by_player": {"0": 101, "1": 102},
                "eligible_burden_deck_indices_by_player": {"0": [101], "1": [102]},
                "processed_burden_deck_indices_by_player": {"0": [100]},
            },
        )
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_type"], "ResupplyModule")

    def test_decision_resume_does_not_derive_batch_id_from_batch_request_id(self) -> None:
        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "decision_submitted",
                        "session_id": session_id,
                        "payload": {
                            "request_id": (
                                "batch:simul:resupply:2:107:"
                                "mod:simul:resupply:2:107:resupply:1:p1"
                            ),
                            "player_id": 2,
                            "request_type": "burden_exchange",
                            "choice_id": "yes",
                            "resume_token": "resume_p1",
                            "frame_id": "simul:resupply:2:107",
                            "module_id": "mod:simul:resupply:2:107:resupply",
                            "module_type": "ResupplyModule",
                            "module_cursor": "await_resupply_batch:1",
                            "decision": {},
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command("sess_batch", 7)

        self.assertIsNotNone(resume)
        self.assertEqual(resume.batch_id, "")

    def test_decision_resume_uses_explicit_prompt_instance_id_with_opaque_request_id(self) -> None:
        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "decision_submitted",
                        "session_id": session_id,
                        "payload": {
                            "request_id": "req_opaque_prompt",
                            "prompt_instance_id": 60,
                            "player_id": 1,
                            "request_type": "trick_tile_target",
                            "choice_id": "8",
                            "resume_token": "resume_current",
                            "frame_id": "seq:action:1:p0:89",
                            "module_id": "mod:seq:action:1:p0:89:fortuneresolve",
                            "module_type": "FortuneResolveModule",
                            "module_cursor": "await_action_prompt",
                            "decision": {},
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command("sess_opaque_prompt", 7)

        self.assertIsNotNone(resume)
        assert resume is not None
        self.assertEqual(resume.request_id, "req_opaque_prompt")
        self.assertEqual(resume.prompt_instance_id, 60)
        from apps.server.src.domain.prompt_sequence import prompt_instance_id_from_resume

        self.assertEqual(prompt_instance_id_from_resume(resume), 60)

    def test_prompt_instance_from_resume_does_not_parse_legacy_request_id(self) -> None:
        from apps.server.src.domain.prompt_sequence import prompt_instance_id_from_resume

        resume = RuntimeDecisionResume(
            request_id="sess_1:r3:t9:p1:trick_tile_target:60",
            player_id=1,
            request_type="trick_tile_target",
            choice_id="8",
            choice_payload={},
            resume_token="resume_current",
            frame_id="seq:action:1:p0:89",
            module_id="mod:seq:action:1:p0:89:fortuneresolve",
            module_type="FortuneResolveModule",
            module_cursor="await_action_prompt",
        )

        self.assertEqual(prompt_instance_id_from_resume(resume), 0)

    def test_continuation_debug_fields_include_explicit_decision_resume_prompt_instance_id(self) -> None:
        from apps.server.src.services.runtime_service import _runtime_continuation_debug_fields

        resume = RuntimeDecisionResume(
            request_id="req_opaque_prompt",
            player_id=1,
            request_type="trick_tile_target",
            choice_id="8",
            choice_payload={},
            resume_token="resume_current",
            frame_id="seq:action:1:p0:89",
            module_id="mod:seq:action:1:p0:89:fortuneresolve",
            module_type="FortuneResolveModule",
            module_cursor="await_action_prompt",
            prompt_instance_id=60,
        )

        fields = _runtime_continuation_debug_fields({}, resume)

        self.assertEqual(fields["decision_resume_prompt_instance_id"], 60)

    def test_prompt_boundary_enrichment_uses_explicit_batch_and_player_for_opaque_request_id(self) -> None:
        RuntimeService._ensure_engine_import_path()
        from runtime_modules.prompts import PromptApi

        frame = FrameState(
            frame_id="frame:resupply",
            frame_type="simultaneous",
            owner_player_id=None,
            parent_frame_id=None,
        )
        module = ModuleRef(
            module_id="module:resupply",
            module_type="ResupplyModule",
            phase="round",
            owner_player_id=None,
            cursor="await_resupply_batch:1",
        )
        batch = PromptApi().create_batch(
            batch_id="batch:simul:opaque",
            frame=frame,
            module=module,
            participant_player_ids=[0, 1],
            request_type="burden_exchange",
            legal_choices_by_player_id={0: [{"choice_id": "yes"}], 1: [{"choice_id": "no"}]},
        )
        state = type("State", (), {"runtime_active_prompt_batch": batch})()
        payload = {
            "request_id": "req_opaque_batch_prompt",
            "batch_id": "batch:simul:opaque",
            "player_id": 2,
            "request_type": "burden_exchange",
        }

        RuntimeService._enrich_prompt_boundary_from_active_batch(payload, state)

        expected = batch.prompts_by_player_id[1]
        self.assertEqual(payload["resume_token"], expected.resume_token)
        self.assertEqual(payload["frame_id"], expected.frame_id)
        self.assertEqual(payload["module_id"], expected.module_id)
        self.assertEqual(payload["module_type"], expected.module_type)
        self.assertEqual(payload["module_cursor"], expected.module_cursor)

    def test_decision_resume_from_batch_complete_command_uses_collected_response(self) -> None:
        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "batch_complete",
                        "session_id": session_id,
                        "payload": {
                            "request_id": "batch_complete:batch:simul:resupply:1",
                            "batch_id": "batch:simul:resupply:1",
                            "expected_player_ids": [1, 2],
                            "responses_by_player_id": {
                                "1": {
                                    "request_id": "batch:simul:resupply:1:p0",
                                    "player_id": 1,
                                    "public_player_id": "ply_1",
                                    "request_type": "burden_exchange",
                                    "choice_id": "yes",
                                    "decision": {"choice_payload": {"accepted": True}},
                                    "resume_token": "resume_p0",
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                    "batch_id": "batch:simul:resupply:1",
                                },
                                "2": {
                                    "request_id": "batch:simul:resupply:1:p1",
                                    "player_id": 2,
                                    "public_player_id": "ply_2",
                                    "request_type": "burden_exchange",
                                    "choice_id": "no",
                                    "provider": "ai",
                                    "choice_payload": {"accepted": False},
                                    "resume_token": "resume_p1",
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                    "batch_id": "batch:simul:resupply:1",
                                },
                            },
                            "responses_by_public_player_id": {
                                "ply_1": {"choice_id": "yes", "public_player_id": "ply_1"},
                                "ply_2": {"choice_id": "no", "public_player_id": "ply_2"},
                            },
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command("sess_batch_complete", 7)

        self.assertIsNotNone(resume)
        assert resume is not None
        self.assertEqual(resume.request_id, "batch:simul:resupply:1:p1")
        self.assertEqual(resume.player_id, 2)
        self.assertEqual(resume.choice_id, "no")
        self.assertEqual(resume.choice_payload, {"accepted": False})
        self.assertEqual(resume.batch_id, "batch:simul:resupply:1")
        self.assertEqual(resume.provider, "ai")
        self.assertEqual(sorted(resume.batch_responses_by_player_id), [1, 2])
        self.assertEqual(sorted(resume.batch_responses_by_public_player_id), ["ply_1", "ply_2"])
        self.assertEqual(resume.batch_responses_by_public_player_id["ply_2"]["choice_id"], "no")

    def test_decision_resume_from_batch_complete_command_accepts_public_response_map(self) -> None:
        session = self._create_started_two_player_session()
        seat_1 = session.seats[0]
        seat_2 = session.seats[1]

        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "batch_complete",
                        "session_id": session_id,
                        "payload": {
                            "request_id": "batch_complete:batch:simul:resupply:public",
                            "batch_id": "batch:simul:resupply:public",
                            "expected_public_player_ids": [
                                seat_1.public_player_id,
                                seat_2.public_player_id,
                            ],
                            "responses_by_public_player_id": {
                                seat_1.public_player_id: {
                                    "public_player_id": seat_1.public_player_id,
                                    "request_id": "req_public_batch_p1",
                                    "request_type": "burden_exchange",
                                    "choice_id": "yes",
                                    "choice_payload": {"accepted": True},
                                    "resume_token": "resume_p1",
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                },
                                seat_2.public_player_id: {
                                    "public_player_id": seat_2.public_player_id,
                                    "request_id": "req_public_batch_p2",
                                    "request_type": "burden_exchange",
                                    "choice_id": "no",
                                    "provider": "ai",
                                    "choice_payload": {"accepted": False},
                                    "resume_token": "resume_p2",
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                },
                            },
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command(session.session_id, 7)

        self.assertIsNotNone(resume)
        assert resume is not None
        self.assertEqual(resume.request_id, "req_public_batch_p2")
        self.assertEqual(resume.player_id, 2)
        self.assertEqual(resume.choice_id, "no")
        self.assertEqual(resume.choice_payload, {"accepted": False})
        self.assertEqual(resume.batch_id, "batch:simul:resupply:public")
        self.assertEqual(resume.provider, "ai")
        self.assertEqual(sorted(resume.batch_responses_by_player_id), [1, 2])
        self.assertEqual(resume.batch_responses_by_player_id[1]["public_player_id"], seat_1.public_player_id)
        self.assertEqual(resume.batch_responses_by_player_id[2]["public_player_id"], seat_2.public_player_id)
        self.assertEqual(
            sorted(resume.batch_responses_by_public_player_id),
            sorted([seat_1.public_player_id, seat_2.public_player_id]),
        )

    def test_public_batch_complete_resume_applies_to_internal_engine_batch(self) -> None:
        session = self._create_started_two_player_session()
        seat_1 = session.seats[0]
        seat_2 = session.seats[1]
        frame = FrameState(
            frame_id="frame:resupply",
            frame_type="simultaneous",
            owner_player_id=None,
            parent_frame_id=None,
        )
        module = ModuleRef(
            module_id="module:resupply",
            module_type="ResupplyModule",
            phase="round",
            owner_player_id=None,
            cursor="await_resupply_batch:1",
        )
        batch = PromptApi().create_batch(
            batch_id="batch:simul:resupply:public",
            frame=frame,
            module=module,
            participant_player_ids=[0, 1],
            request_type="burden_exchange",
            legal_choices_by_player_id={0: [{"choice_id": "yes"}], 1: [{"choice_id": "no"}]},
        )
        state = type("State", (), {"runtime_active_prompt_batch": batch})()

        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "batch_complete",
                        "session_id": session_id,
                        "payload": {
                            "request_id": "batch_complete:batch:simul:resupply:public",
                            "batch_id": "batch:simul:resupply:public",
                            "expected_public_player_ids": [
                                seat_1.public_player_id,
                                seat_2.public_player_id,
                            ],
                            "responses_by_public_player_id": {
                                seat_1.public_player_id: {
                                    "public_player_id": seat_1.public_player_id,
                                    "request_id": batch.prompts_by_player_id[0].request_id,
                                    "request_type": "burden_exchange",
                                    "choice_id": "yes",
                                    "choice_payload": {"accepted": True},
                                    "resume_token": batch.prompts_by_player_id[0].resume_token,
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                },
                                seat_2.public_player_id: {
                                    "public_player_id": seat_2.public_player_id,
                                    "request_id": batch.prompts_by_player_id[1].request_id,
                                    "request_type": "burden_exchange",
                                    "choice_id": "no",
                                    "choice_payload": {"accepted": False},
                                    "resume_token": batch.prompts_by_player_id[1].resume_token,
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                },
                            },
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command(session.session_id, 7)

        self.assertIsNotNone(resume)
        assert resume is not None
        runtime._apply_collected_batch_responses_to_state(state, resume)
        self.assertEqual(batch.responses_by_player_id[0]["choice_id"], "yes")
        self.assertEqual(batch.responses_by_player_id[0]["choice_payload"], {"accepted": True})
        self.assertEqual(batch.missing_player_ids, [1])

    def test_public_batch_complete_resume_prefers_legacy_engine_request_id(self) -> None:
        session = self._create_started_two_player_session()
        seat_1 = session.seats[0]
        seat_2 = session.seats[1]
        frame = FrameState(
            frame_id="frame:resupply",
            frame_type="simultaneous",
            owner_player_id=None,
            parent_frame_id=None,
        )
        module = ModuleRef(
            module_id="module:resupply",
            module_type="ResupplyModule",
            phase="round",
            owner_player_id=None,
            cursor="await_resupply_batch:1",
        )
        batch = PromptApi().create_batch(
            batch_id="batch:simul:resupply:public",
            frame=frame,
            module=module,
            participant_player_ids=[0, 1],
            request_type="burden_exchange",
            legal_choices_by_player_id={0: [{"choice_id": "yes"}], 1: [{"choice_id": "no"}]},
        )
        state = type("State", (), {"runtime_active_prompt_batch": batch})()

        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "batch_complete",
                        "session_id": session_id,
                        "payload": {
                            "request_id": "batch_complete:batch:simul:resupply:public",
                            "batch_id": "batch:simul:resupply:public",
                            "expected_public_player_ids": [
                                seat_1.public_player_id,
                                seat_2.public_player_id,
                            ],
                            "responses_by_public_player_id": {
                                seat_1.public_player_id: {
                                    "public_player_id": seat_1.public_player_id,
                                    "request_id": "req_public_batch_p1",
                                    "legacy_request_id": batch.prompts_by_player_id[0].request_id,
                                    "request_type": "burden_exchange",
                                    "choice_id": "yes",
                                    "choice_payload": {"accepted": True},
                                    "resume_token": batch.prompts_by_player_id[0].resume_token,
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                },
                                seat_2.public_player_id: {
                                    "public_player_id": seat_2.public_player_id,
                                    "request_id": "req_public_batch_p2",
                                    "legacy_request_id": batch.prompts_by_player_id[1].request_id,
                                    "request_type": "burden_exchange",
                                    "choice_id": "no",
                                    "choice_payload": {"accepted": False},
                                    "resume_token": batch.prompts_by_player_id[1].resume_token,
                                    "frame_id": "frame:resupply",
                                    "module_id": "module:resupply",
                                    "module_type": "ResupplyModule",
                                    "module_cursor": "await_resupply_batch:1",
                                },
                            },
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command(session.session_id, 7)

        self.assertIsNotNone(resume)
        assert resume is not None
        self.assertEqual(resume.request_id, batch.prompts_by_player_id[1].request_id)
        runtime._validate_decision_resume_against_checkpoint(state, resume)
        runtime._apply_collected_batch_responses_to_state(state, resume)
        self.assertEqual(batch.responses_by_player_id[0]["choice_payload"], {"accepted": True})
        self.assertEqual(batch.missing_player_ids, [1])

    def test_collected_batch_responses_are_applied_before_primary_resume(self) -> None:
        frame = FrameState(
            frame_id="frame:resupply",
            frame_type="simultaneous",
            owner_player_id=None,
            parent_frame_id=None,
        )
        module = ModuleRef(
            module_id="module:resupply",
            module_type="ResupplyModule",
            phase="round",
            owner_player_id=None,
            cursor="await_resupply_batch:1",
        )
        batch = PromptApi().create_batch(
            batch_id="batch:simul:resupply:1",
            frame=frame,
            module=module,
            participant_player_ids=[0, 1],
            request_type="burden_exchange",
            legal_choices_by_player_id={0: [{"choice_id": "yes"}], 1: [{"choice_id": "no"}]},
        )
        state = type("State", (), {"runtime_active_prompt_batch": batch})()
        resume = RuntimeDecisionResume(
            request_id=batch.prompts_by_player_id[1].request_id,
            player_id=2,
            request_type="burden_exchange",
            choice_id="no",
            choice_payload={"accepted": False},
            resume_token=batch.prompts_by_player_id[1].resume_token,
            frame_id="frame:resupply",
            module_id="module:resupply",
            module_type="ResupplyModule",
            module_cursor="await_resupply_batch:1",
            batch_id="batch:simul:resupply:1",
            batch_responses_by_player_id={
                1: {
                    "request_id": batch.prompts_by_player_id[0].request_id,
                    "player_id": 1,
                    "choice_id": "yes",
                    "resume_token": batch.prompts_by_player_id[0].resume_token,
                    "decision": {"choice_payload": {"accepted": True}},
                },
                2: {
                    "request_id": batch.prompts_by_player_id[1].request_id,
                    "player_id": 2,
                    "choice_id": "no",
                    "resume_token": batch.prompts_by_player_id[1].resume_token,
                    "choice_payload": {"accepted": False},
                },
            },
        )

        self.runtime_service._apply_collected_batch_responses_to_state(state, resume)

        self.assertEqual(batch.responses_by_player_id[0]["choice_id"], "yes")
        self.assertEqual(batch.responses_by_player_id[0]["choice_payload"], {"accepted": True})
        self.assertEqual(batch.missing_player_ids, [1])

    def test_decision_resume_ignores_scalar_choice_payload(self) -> None:
        class _CommandStoreStub:
            def list_commands(self, session_id: str) -> list[dict]:
                return [
                    {
                        "seq": 7,
                        "type": "decision_submitted",
                        "session_id": session_id,
                        "payload": {
                            "request_id": "sess:r1:t1:p1:purchase_tile:19",
                            "player_id": 1,
                            "request_type": "purchase_tile",
                            "choice_id": "yes",
                            "choice_payload": True,
                            "resume_token": "resume_purchase",
                            "frame_id": "seq:action:1:p0:22",
                            "module_id": "mod:seq:action:1:p0:22:purchasedecision",
                            "module_type": "PurchaseDecisionModule",
                            "module_cursor": "await_action_prompt",
                            "decision": {},
                        },
                    }
                ]

        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            command_store=_CommandStoreStub(),
        )

        resume = runtime._decision_resume_from_command("sess_scalar", 7)

        self.assertIsNotNone(resume)
        self.assertEqual(resume.choice_id, "yes")
        self.assertEqual(resume.choice_payload, {})

    def test_module_resume_preserves_checkpoint_frame_stack_without_replay(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import FrameState, ModuleRef, PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_frame_stack = [
            FrameState(
                frame_id="turn:1:p0",
                frame_type="turn",
                owner_player_id=0,
                parent_frame_id=None,
                status="suspended",
                active_module_id="mod:turn:1:p0:trick_window",
                completed_module_ids=[
                    "mod:turn:1:p0:character_start",
                    "mod:turn:1:p0:target_judicator",
                ],
                module_queue=[
                    ModuleRef(
                        module_id="mod:turn:1:p0:character_start",
                        module_type="CharacterStartModule",
                        phase="character",
                        owner_player_id=0,
                        status="completed",
                        cursor="done",
                    ),
                    ModuleRef(
                        module_id="mod:turn:1:p0:target_judicator",
                        module_type="TargetJudicatorModule",
                        phase="target",
                        owner_player_id=0,
                        status="completed",
                        cursor="done",
                    ),
                    ModuleRef(
                        module_id="mod:turn:1:p0:trick_window",
                        module_type="TrickWindowModule",
                        phase="trick",
                        owner_player_id=0,
                        status="suspended",
                        cursor="child_sequence:seq:trick:1:p0",
                    ),
                ],
            ),
            FrameState(
                frame_id="seq:trick:1:p0",
                frame_type="sequence",
                owner_player_id=0,
                parent_frame_id="turn:1:p0",
                status="suspended",
                active_module_id="mod:trick_sequence:1:p0:choice",
                created_by_module_id="mod:turn:1:p0:trick_window",
                module_queue=[
                    ModuleRef(
                        module_id="mod:trick_sequence:1:p0:resolve",
                        module_type="TrickResolveModule",
                        phase="trick",
                        owner_player_id=0,
                        status="completed",
                        cursor="done",
                    ),
                    ModuleRef(
                        module_id="mod:trick_sequence:1:p0:choice",
                        module_type="TrickChoiceModule",
                        phase="trick",
                        owner_player_id=0,
                        status="suspended",
                        cursor="await_trick_prompt",
                        suspension_id="suspend:trick_choice:1",
                    ),
                ],
                completed_module_ids=["mod:trick_sequence:1:p0:resolve"],
            ),
        ]
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_trick_1",
            prompt_instance_id=7,
            resume_token="resume_trick_1",
            frame_id="seq:trick:1:p0",
            module_id="mod:trick_sequence:1:p0:choice",
            module_type="TrickChoiceModule",
            module_cursor="await_trick_prompt",
            player_id=0,
            request_type="trick_to_use",
            legal_choices=[{"choice_id": "defer"}, {"choice_id": "use_trick"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_trick_1",
                    "player_id": 1,
                    "request_type": "trick_to_use",
                    "choice_id": "use_trick",
                    "resume_token": "resume_trick_1",
                    "frame_id": "seq:trick:1:p0",
                    "module_id": "mod:trick_sequence:1:p0:choice",
                    "module_type": "TrickChoiceModule",
                    "module_cursor": "await_trick_prompt",
                    "decision": {"card_id": "quick_wit"},
                },
            }
        )
        seen: list[dict] = []

        def _fake_run_next_transition(self, resumed_state, decision_resume=None):  # noqa: ANN001
            del self
            frames = resumed_state.runtime_frame_stack
            seen.append(
                {
                    "decision_resume": decision_resume,
                    "frame_ids": [frame.frame_id for frame in frames],
                    "frame_statuses": [frame.status for frame in frames],
                    "active_modules": [frame.active_module_id for frame in frames],
                    "turn_window_cursor": frames[0].module_queue[2].cursor,
                    "choice_cursor": frames[1].module_queue[1].cursor,
                    "completed_turn_modules": list(frames[0].completed_module_ids),
                    "active_prompt_token": resumed_state.runtime_active_prompt.resume_token,
                }
            )
            return {"status": "committed", "runner_kind": "module", "module_type": "TrickChoiceModule"}

        with patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "committed")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["frame_ids"], ["turn:1:p0", "seq:trick:1:p0"])
        self.assertEqual(seen[0]["frame_statuses"], ["suspended", "suspended"])
        self.assertEqual(
            seen[0]["active_modules"],
            ["mod:turn:1:p0:trick_window", "mod:trick_sequence:1:p0:choice"],
        )
        self.assertEqual(seen[0]["turn_window_cursor"], "child_sequence:seq:trick:1:p0")
        self.assertEqual(seen[0]["choice_cursor"], "await_trick_prompt")
        self.assertEqual(
            seen[0]["completed_turn_modules"],
            ["mod:turn:1:p0:character_start", "mod:turn:1:p0:target_judicator"],
        )
        self.assertEqual(seen[0]["active_prompt_token"], "resume_trick_1")
        self.assertEqual(getattr(seen[0]["decision_resume"], "choice_id"), "use_trick")
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_type"], "TrickChoiceModule")
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_cursor"], "await_trick_prompt")

    def test_module_resume_preserves_purchase_sequence_checkpoint_without_replay(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import FrameState, ModuleRef, PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_frame_stack = [
            FrameState(
                frame_id="turn:2:p0",
                frame_type="turn",
                owner_player_id=0,
                parent_frame_id=None,
                status="suspended",
                active_module_id="mod:turn:2:p0:arrival",
                completed_module_ids=[
                    "mod:turn:2:p0:character_start",
                    "mod:turn:2:p0:dice",
                    "mod:turn:2:p0:move",
                ],
                module_queue=[
                    ModuleRef(
                        module_id="mod:turn:2:p0:character_start",
                        module_type="CharacterStartModule",
                        phase="character",
                        owner_player_id=0,
                        status="completed",
                        cursor="done",
                    ),
                    ModuleRef(
                        module_id="mod:turn:2:p0:dice",
                        module_type="DiceRollModule",
                        phase="dice",
                        owner_player_id=0,
                        status="completed",
                        cursor="done",
                    ),
                    ModuleRef(
                        module_id="mod:turn:2:p0:move",
                        module_type="MapMoveModule",
                        phase="movement",
                        owner_player_id=0,
                        status="completed",
                        cursor="done",
                    ),
                    ModuleRef(
                        module_id="mod:turn:2:p0:arrival",
                        module_type="ArrivalTileModule",
                        phase="arrival",
                        owner_player_id=0,
                        status="suspended",
                        cursor="child_sequence:seq:purchase:2:p0",
                    ),
                ],
            ),
            FrameState(
                frame_id="seq:purchase:2:p0",
                frame_type="sequence",
                owner_player_id=0,
                parent_frame_id="turn:2:p0",
                status="suspended",
                active_module_id="mod:purchase:2:p0:decision",
                created_by_module_id="mod:turn:2:p0:arrival",
                module_queue=[
                    ModuleRef(
                        module_id="mod:purchase:2:p0:decision",
                        module_type="PurchaseDecisionModule",
                        phase="purchase",
                        owner_player_id=0,
                        status="suspended",
                        cursor="purchase:await_choice",
                        suspension_id="suspend:purchase:1",
                    ),
                    ModuleRef(
                        module_id="mod:purchase:2:p0:commit",
                        module_type="PurchaseCommitModule",
                        phase="purchase",
                        owner_player_id=0,
                        status="queued",
                        cursor="start",
                    ),
                ],
                completed_module_ids=[],
            ),
        ]
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_purchase_1",
            prompt_instance_id=9,
            resume_token="resume_purchase_1",
            frame_id="seq:purchase:2:p0",
            module_id="mod:purchase:2:p0:decision",
            module_type="PurchaseDecisionModule",
            module_cursor="purchase:await_choice",
            player_id=0,
            request_type="purchase_tile",
            legal_choices=[{"choice_id": "yes"}, {"choice_id": "no"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_purchase_1",
                    "player_id": 1,
                    "request_type": "purchase_tile",
                    "choice_id": "yes",
                    "resume_token": "resume_purchase_1",
                    "frame_id": "seq:purchase:2:p0",
                    "module_id": "mod:purchase:2:p0:decision",
                    "module_type": "PurchaseDecisionModule",
                    "module_cursor": "purchase:await_choice",
                    "decision": {},
                },
            }
        )
        seen: list[dict] = []

        def _fake_run_next_transition(self, resumed_state, decision_resume=None):  # noqa: ANN001
            del self
            frames = resumed_state.runtime_frame_stack
            seen.append(
                {
                    "decision_resume": decision_resume,
                    "frame_ids": [frame.frame_id for frame in frames],
                    "active_modules": [frame.active_module_id for frame in frames],
                    "arrival_cursor": frames[0].module_queue[3].cursor,
                    "decision_cursor": frames[1].module_queue[0].cursor,
                    "commit_status": frames[1].module_queue[1].status,
                    "active_prompt_token": resumed_state.runtime_active_prompt.resume_token,
                }
            )
            return {"status": "committed", "runner_kind": "module", "module_type": "PurchaseDecisionModule"}

        with patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "committed")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["frame_ids"], ["turn:2:p0", "seq:purchase:2:p0"])
        self.assertEqual(
            seen[0]["active_modules"],
            ["mod:turn:2:p0:arrival", "mod:purchase:2:p0:decision"],
        )
        self.assertEqual(seen[0]["arrival_cursor"], "child_sequence:seq:purchase:2:p0")
        self.assertEqual(seen[0]["decision_cursor"], "purchase:await_choice")
        self.assertEqual(seen[0]["commit_status"], "queued")
        self.assertEqual(seen[0]["active_prompt_token"], "resume_purchase_1")
        self.assertEqual(getattr(seen[0]["decision_resume"], "module_type"), "PurchaseDecisionModule")
        self.assertEqual(getattr(seen[0]["decision_resume"], "choice_id"), "yes")
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_type"], "PurchaseDecisionModule")
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_cursor"], "purchase:await_choice")

    def test_module_resume_preserves_lap_reward_sequence_checkpoint_without_replay(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import FrameState, ModuleRef, PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        store = _MutableGameStateStoreStub()
        command_store = _CommandStoreStub()
        runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
            game_state_store=store,
            command_store=command_store,
        )
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)
        config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
        state = GameState.create(config)
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = 3
        state.runtime_frame_stack = [
            FrameState(
                frame_id="turn:3:p0",
                frame_type="turn",
                owner_player_id=0,
                parent_frame_id=None,
                status="suspended",
                active_module_id="mod:turn:3:p0:move",
                module_queue=[
                    ModuleRef(
                        module_id="mod:turn:3:p0:move",
                        module_type="MapMoveModule",
                        phase="movement",
                        owner_player_id=0,
                        status="suspended",
                        cursor="child_sequence:seq:lap:3:p0",
                    ),
                ],
            ),
            FrameState(
                frame_id="seq:lap:3:p0",
                frame_type="sequence",
                owner_player_id=0,
                parent_frame_id="turn:3:p0",
                status="suspended",
                active_module_id="mod:lap:3:p0:reward",
                created_by_module_id="mod:turn:3:p0:move",
                module_queue=[
                    ModuleRef(
                        module_id="mod:lap:3:p0:reward",
                        module_type="LapRewardModule",
                        phase="lapreward",
                        owner_player_id=0,
                        status="suspended",
                        cursor="lap_reward:await_choice",
                        suspension_id="suspend:lap_reward:1",
                    ),
                    ModuleRef(
                        module_id="mod:lap:3:p0:arrival",
                        module_type="ArrivalTileModule",
                        phase="arrival",
                        owner_player_id=0,
                        status="queued",
                        cursor="start",
                    ),
                ],
            ),
        ]
        state.runtime_active_prompt = PromptContinuation(
            request_id="req_lap_1",
            prompt_instance_id=11,
            resume_token="resume_lap_1",
            frame_id="seq:lap:3:p0",
            module_id="mod:lap:3:p0:reward",
            module_type="LapRewardModule",
            module_cursor="lap_reward:await_choice",
            player_id=0,
            request_type="lap_reward",
            legal_choices=[{"choice_id": "cash-5_shards-0_coins-0"}],
        )
        store.current_state = state.to_checkpoint_payload()
        store.checkpoint = {
            "schema_version": 3,
            "session_id": session.session_id,
            "runner_kind": "module",
            "has_snapshot": True,
        }
        command_store.commands.append(
            {
                "seq": 1,
                "type": "decision_submitted",
                "session_id": session.session_id,
                "payload": {
                    "request_id": "req_lap_1",
                    "player_id": 1,
                    "request_type": "lap_reward",
                    "choice_id": "cash-5_shards-0_coins-0",
                    "resume_token": "resume_lap_1",
                    "frame_id": "seq:lap:3:p0",
                    "module_id": "mod:lap:3:p0:reward",
                    "module_type": "LapRewardModule",
                    "module_cursor": "lap_reward:await_choice",
                    "decision": {},
                },
            }
        )
        seen: list[dict] = []

        def _fake_run_next_transition(self, resumed_state, decision_resume=None):  # noqa: ANN001
            del self
            frames = resumed_state.runtime_frame_stack
            seen.append(
                {
                    "frame_ids": [frame.frame_id for frame in frames],
                    "active_modules": [frame.active_module_id for frame in frames],
                    "lap_cursor": frames[1].module_queue[0].cursor,
                    "arrival_status": frames[1].module_queue[1].status,
                    "active_prompt_token": resumed_state.runtime_active_prompt.resume_token,
                    "resume_module_type": decision_resume.module_type,
                    "resume_choice_id": decision_resume.choice_id,
                }
            )
            return {"status": "committed", "runner_kind": "module", "module_type": "LapRewardModule"}

        with patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition):
            result = runtime._run_engine_transition_once_sync(
                None,
                session.session_id,
                42,
                None,
                True,
                "runtime-worker",
                1,
            )

        self.assertEqual(result["status"], "committed")
        self.assertEqual(
            seen,
            [
                {
                    "frame_ids": ["turn:3:p0", "seq:lap:3:p0"],
                    "active_modules": ["mod:turn:3:p0:move", "mod:lap:3:p0:reward"],
                    "lap_cursor": "lap_reward:await_choice",
                    "arrival_status": "queued",
                    "active_prompt_token": "resume_lap_1",
                    "resume_module_type": "LapRewardModule",
                    "resume_choice_id": "cash-5_shards-0_coins-0",
                }
            ],
        )
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_type"], "LapRewardModule")
        self.assertEqual(store.commits[0]["checkpoint"]["active_module_cursor"], "lap_reward:await_choice")

    def test_module_resume_prompt_boundary_matrix_preserves_checkpoint_without_replay(self) -> None:
        RuntimeService._ensure_engine_import_path()
        import engine
        from runtime_modules.contracts import FrameState, ModuleRef, PromptContinuation
        from state import GameState

        class _CommandStoreStub:
            def __init__(self) -> None:
                self.commands: list[dict] = []
                self.offsets: list[tuple[str, str, int]] = []

            def list_commands(self, session_id: str) -> list[dict]:
                return [copy.deepcopy(command) for command in self.commands if command["session_id"] == session_id]

            def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
                self.offsets.append((consumer_name, session_id, int(seq)))

        cases = [
            {
                "name": "target_judicator",
                "frame_type": "turn",
                "module_type": "TargetJudicatorModule",
                "request_type": "mark_target",
                "cursor": "target:await_choice",
                "choice_id": "p2",
            },
            {
                "name": "fortune_target",
                "frame_type": "sequence",
                "module_type": "FortuneResolveModule",
                "request_type": "fortune_target",
                "cursor": "fortune:await_choice",
                "choice_id": "p2",
            },
            {
                "name": "rent_payment",
                "frame_type": "sequence",
                "module_type": "RentPaymentModule",
                "request_type": "rent_payment",
                "cursor": "rent:await_choice",
                "choice_id": "pay",
            },
            {
                "name": "score_token",
                "frame_type": "sequence",
                "module_type": "ScoreTokenPlacementPromptModule",
                "request_type": "coin_placement",
                "cursor": "score_token:await_choice",
                "choice_id": "tile-7",
            },
            {
                "name": "character_start_doctrine",
                "frame_type": "turn",
                "module_type": "CharacterStartModule",
                "request_type": "doctrine_relief",
                "cursor": "character_start:await_doctrine_relief",
                "choice_id": "p2",
            },
            {
                "name": "character_start_pabal",
                "frame_type": "turn",
                "module_type": "CharacterStartModule",
                "request_type": "pabal_dice_mode",
                "cursor": "character_start:await_pabal_dice_mode",
                "choice_id": "plus_one",
            },
            {
                "name": "movement_choice",
                "frame_type": "turn",
                "module_type": "DiceRollModule",
                "request_type": "movement",
                "cursor": "dice:await_movement_choice",
                "choice_id": "roll",
            },
            {
                "name": "specific_trick_reward",
                "frame_type": "sequence",
                "module_type": "TrickResolveModule",
                "request_type": "specific_trick_reward",
                "cursor": "trick_resolve:await_specific_reward",
                "choice_id": "102",
            },
            {
                "name": "round_active_flip",
                "frame_type": "round",
                "module_type": "RoundEndCardFlipModule",
                "request_type": "active_flip",
                "cursor": "round_end_card_flip:await_choice",
                "choice_id": "7",
            },
        ]

        for index, case in enumerate(cases, start=1):
            with self.subTest(case=case["name"]):
                store = _MutableGameStateStoreStub()
                command_store = _CommandStoreStub()
                runtime = RuntimeService(
                    session_service=self.session_service,
                    stream_service=self.stream_service,
                    prompt_service=self.prompt_service,
                    game_state_store=store,
                    command_store=command_store,
                )
                session = self.session_service.create_session(
                    seats=[
                        {"seat": 1, "seat_type": "human"},
                        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                        {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
                    ],
                    config={"seed": 42 + index, "runtime": {"runner_kind": "module", "ai_decision_delay_ms": 0}},
                )
                self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
                self.session_service.start_session(session.session_id, session.host_token)
                config = runtime._config_factory.create(session.resolved_parameters)  # type: ignore[attr-defined]
                state = GameState.create(config)
                state.runtime_runner_kind = "module"
                state.runtime_checkpoint_schema_version = 3
                frame_id = f"turn:{index}:p0"
                module_id = f"mod:{case['name']}:{index}:p0"
                if case["frame_type"] == "turn":
                    state.runtime_frame_stack = [
                        FrameState(
                            frame_id=frame_id,
                            frame_type="turn",
                            owner_player_id=0,
                            parent_frame_id=None,
                            status="suspended",
                            active_module_id=module_id,
                            completed_module_ids=["mod:turn:start"],
                            module_queue=[
                                ModuleRef(
                                    module_id="mod:turn:start",
                                    module_type="TurnStartModule",
                                    phase="turn_start",
                                    owner_player_id=0,
                                    status="completed",
                                    cursor="done",
                                ),
                                ModuleRef(
                                    module_id=module_id,
                                    module_type=str(case["module_type"]),
                                    phase=str(case["name"]),
                                    owner_player_id=0,
                                    status="suspended",
                                    cursor=str(case["cursor"]),
                                    suspension_id=f"suspend:{case['name']}:1",
                                ),
                            ],
                        )
                    ]
                    prompt_frame_id = frame_id
                elif case["frame_type"] == "round":
                    round_frame_id = f"round:{index}"
                    state.runtime_frame_stack = [
                        FrameState(
                            frame_id=round_frame_id,
                            frame_type="round",
                            owner_player_id=None,
                            parent_frame_id=None,
                            status="suspended",
                            active_module_id=module_id,
                            module_queue=[
                                ModuleRef(
                                    module_id=module_id,
                                    module_type=str(case["module_type"]),
                                    phase=str(case["name"]),
                                    owner_player_id=0,
                                    status="suspended",
                                    cursor=str(case["cursor"]),
                                    suspension_id=f"suspend:{case['name']}:1",
                                ),
                                ModuleRef(
                                    module_id=f"mod:{case['name']}:{index}:after",
                                    module_type="RoundCleanupAndNextRoundModule",
                                    phase="round_cleanup",
                                    owner_player_id=None,
                                    status="queued",
                                    cursor="start",
                                ),
                            ],
                        )
                    ]
                    prompt_frame_id = round_frame_id
                else:
                    sequence_frame_id = f"seq:{case['name']}:{index}:p0"
                    state.runtime_frame_stack = [
                        FrameState(
                            frame_id=frame_id,
                            frame_type="turn",
                            owner_player_id=0,
                            parent_frame_id=None,
                            status="suspended",
                            active_module_id=f"mod:turn:{index}:p0:arrival",
                            module_queue=[
                                ModuleRef(
                                    module_id=f"mod:turn:{index}:p0:arrival",
                                    module_type="ArrivalTileModule",
                                    phase="arrival",
                                    owner_player_id=0,
                                    status="suspended",
                                    cursor=f"child_sequence:{sequence_frame_id}",
                                ),
                            ],
                        ),
                        FrameState(
                            frame_id=sequence_frame_id,
                            frame_type="sequence",
                            owner_player_id=0,
                            parent_frame_id=frame_id,
                            status="suspended",
                            active_module_id=module_id,
                            created_by_module_id=f"mod:turn:{index}:p0:arrival",
                            module_queue=[
                                ModuleRef(
                                    module_id=module_id,
                                    module_type=str(case["module_type"]),
                                    phase=str(case["name"]),
                                    owner_player_id=0,
                                    status="suspended",
                                    cursor=str(case["cursor"]),
                                    suspension_id=f"suspend:{case['name']}:1",
                                ),
                                ModuleRef(
                                    module_id=f"mod:{case['name']}:{index}:p0:after",
                                    module_type="LandingPostEffectsModule",
                                    phase="post_effects",
                                    owner_player_id=0,
                                    status="queued",
                                    cursor="start",
                                ),
                            ],
                        ),
                    ]
                    prompt_frame_id = sequence_frame_id
                state.runtime_active_prompt = PromptContinuation(
                    request_id=f"req_{case['name']}",
                    prompt_instance_id=100 + index,
                    resume_token=f"resume_{case['name']}",
                    frame_id=prompt_frame_id,
                    module_id=module_id,
                    module_type=str(case["module_type"]),
                    module_cursor=str(case["cursor"]),
                    player_id=0,
                    request_type=str(case["request_type"]),
                    legal_choices=[{"choice_id": str(case["choice_id"])}],
                )
                store.current_state = state.to_checkpoint_payload()
                store.checkpoint = {
                    "schema_version": 3,
                    "session_id": session.session_id,
                    "runner_kind": "module",
                    "has_snapshot": True,
                }
                command_store.commands.append(
                    {
                        "seq": 1,
                        "type": "decision_submitted",
                        "session_id": session.session_id,
                        "payload": {
                            "request_id": f"req_{case['name']}",
                            "player_id": 1,
                            "request_type": str(case["request_type"]),
                            "choice_id": str(case["choice_id"]),
                            "resume_token": f"resume_{case['name']}",
                            "frame_id": prompt_frame_id,
                            "module_id": module_id,
                            "module_type": str(case["module_type"]),
                            "module_cursor": str(case["cursor"]),
                            "decision": {},
                        },
                    }
                )
                seen: list[dict] = []

                def _fake_run_next_transition(self, resumed_state, decision_resume=None):  # noqa: ANN001
                    del self
                    frames = resumed_state.runtime_frame_stack
                    active_frame = frames[-1]
                    active_module_index = 1 if active_frame.frame_type == "turn" else 0
                    seen.append(
                        {
                            "frame_ids": [frame.frame_id for frame in frames],
                            "active_module_id": active_frame.active_module_id,
                            "active_module_cursor": active_frame.module_queue[active_module_index].cursor,
                            "active_prompt_token": resumed_state.runtime_active_prompt.resume_token,
                            "resume_module_type": decision_resume.module_type,
                            "resume_choice_id": decision_resume.choice_id,
                        }
                    )
                    return {"status": "committed", "runner_kind": "module", "module_type": case["module_type"]}

                with patch.object(engine.GameEngine, "run_next_transition", _fake_run_next_transition):
                    result = runtime._run_engine_transition_once_sync(
                        None,
                        session.session_id,
                        42,
                        None,
                        True,
                        "runtime-worker",
                        1,
                    )

                self.assertEqual(result["status"], "committed")
                self.assertEqual(len(seen), 1)
                self.assertEqual(seen[0]["active_module_id"], module_id)
                self.assertEqual(seen[0]["active_module_cursor"], case["cursor"])
                self.assertEqual(seen[0]["active_prompt_token"], f"resume_{case['name']}")
                self.assertEqual(seen[0]["resume_module_type"], case["module_type"])
                self.assertEqual(seen[0]["resume_choice_id"], case["choice_id"])
                self.assertEqual(store.commits[0]["checkpoint"]["active_module_type"], case["module_type"])
                self.assertEqual(store.commits[0]["checkpoint"]["active_module_cursor"], case["cursor"])

    def test_bridge_consumes_valid_decision_resume_without_creating_prompt(self) -> None:
        RuntimeService._ensure_engine_import_path()
        from engine import DecisionRequest
        from apps.server.src.services.runtime_service import RuntimeDecisionResume, _ServerDecisionPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_resume_bridge_test",
                session_seats=[],
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            bridge.set_decision_resume(
                RuntimeDecisionResume(
                    request_id="req_purchase_1",
                    player_id=1,
                    request_type="purchase_tile",
                    choice_id="yes",
                    choice_payload={},
                    resume_token="token_1",
                    frame_id="turn:1:p0",
                    module_id="mod:turn:1:p0:purchase",
                    module_type="PurchaseTileModule",
                    module_cursor="purchase:await_choice",
                )
            )
            state = type(
                "State",
                (),
                {"rounds_completed": 0, "turn_index": 0, "block_ids": [0, 0], "board": [], "tile_owner": []},
            )()
            player = type("Player", (), {"player_id": 0, "cash": 10, "position": 0, "shards": 0})()
            request = DecisionRequest(
                decision_name="choose_purchase_tile",
                request_type="purchase_tile",
                state=state,
                player=player,
                player_id=0,
                round_index=1,
                turn_index=1,
                args=(9, "T2", 4),
                kwargs={},
                fallback_policy="required",
            )

            with patch.object(
                bridge._gateway,
                "resolve_human_prompt",
                side_effect=AssertionError("verified module continuation must not create a new prompt"),
            ):
                result = bridge.request(request)

            self.assertIs(result, True)
            self.assertIsNone(bridge._decision_resume)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_bridge_consumes_direct_choose_resume_without_creating_prompt(self) -> None:
        from apps.server.src.services.runtime_service import RuntimeDecisionResume, _ServerDecisionPolicyBridge

        class _DummyAi:
            def choose_hidden_trick_card(self, state, player, hand):
                del state, player
                return hand[0]

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_direct_resume_bridge_test",
                session_seats=[],
                human_seats=[0],
                ai_fallback=_DummyAi(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            card_a = type("Card", (), {"deck_index": 37, "name": "저속", "description": "desc-a"})()
            card_b = type("Card", (), {"deck_index": 21, "name": "도움 닫기", "description": "desc-b"})()
            player = type(
                "Player",
                (),
                {
                    "player_id": 0,
                    "cash": 10,
                    "position": 0,
                    "shards": 0,
                    "hidden_trick_deck_index": None,
                    "trick_hand": [card_a, card_b],
                },
            )()
            state = type(
                "State",
                (),
                {
                    "rounds_completed": 0,
                    "turn_index": 0,
                    "active_by_card": {},
                    "runtime_runner_kind": "module",
                },
            )()
            bridge.set_decision_resume(
                RuntimeDecisionResume(
                    request_id="sess_direct_resume_bridge_test:r1:t0:p1:hidden_trick_card:3",
                    player_id=1,
                    request_type="hidden_trick_card",
                    choice_id="37",
                    choice_payload={},
                    resume_token="resume_hidden_37",
                    frame_id="round:1",
                    module_id="mod:round:1:draft",
                    module_type="DraftModule",
                    module_cursor="draft:final:3",
                )
            )

            with patch.object(
                bridge._gateway,
                "resolve_human_prompt",
                side_effect=AssertionError("direct choose resume must not create a new prompt"),
            ):
                result = bridge.choose_hidden_trick_card(state, player, [card_a, card_b])

            self.assertIs(result, card_a)
            self.assertIsNone(bridge._decision_resume)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_bridge_uses_checkpoint_validated_resume_when_replayed_legal_choices_drift(self) -> None:
        from apps.server.src.services.decision_gateway import build_routed_decision_call as original_build_call
        from apps.server.src.services.runtime_service import RuntimeDecisionResume, _ServerDecisionPolicyBridge

        class _DummyAi:
            def choose_hidden_trick_card(self, state, player, hand):
                del state, player
                return hand[0]

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_replayed_legal_drift_test",
                session_seats=[],
                human_seats=[0],
                ai_fallback=_DummyAi(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            card_a = type("Card", (), {"deck_index": 14, "name": "숨김", "description": "desc-a"})()
            card_b = type("Card", (), {"deck_index": 17, "name": "후보", "description": "desc-b"})()
            player = type(
                "Player",
                (),
                {
                    "player_id": 0,
                    "cash": 10,
                    "position": 0,
                    "shards": 0,
                    "hidden_trick_deck_index": None,
                    "trick_hand": [card_a, card_b],
                },
            )()
            state = type(
                "State",
                (),
                {
                    "rounds_completed": 1,
                    "turn_index": 6,
                    "active_by_card": {},
                    "runtime_runner_kind": "module",
                },
            )()
            bridge.set_decision_resume(
                RuntimeDecisionResume(
                    request_id="sess_replayed_legal_drift_test:r2:t7:p1:hidden_trick_card:65",
                    player_id=1,
                    request_type="hidden_trick_card",
                    choice_id="14",
                    choice_payload={"deck_index": 14},
                    resume_token="resume_hidden_14",
                    frame_id="seq:action:2:p0:216",
                    module_id="mod:seq:action:2:p0:216:pendingmarkresolution",
                    module_type="PendingMarkResolutionModule",
                    module_cursor="await_action_prompt",
                )
            )

            def drifted_build_call(invocation, *, fallback_policy="ai"):
                call = original_build_call(invocation, fallback_policy=fallback_policy)
                return replace(call, legal_choices=[{"choice_id": "17"}])

            with patch(
                "apps.server.src.services.runtime_service.build_routed_decision_call",
                side_effect=drifted_build_call,
            ), patch.object(
                bridge._gateway,
                "resolve_human_prompt",
                side_effect=AssertionError("checkpoint-validated resume must not create a new prompt"),
            ):
                result = bridge.choose_hidden_trick_card(state, player, [card_b])

            self.assertEqual(getattr(result, "deck_index", None), 14)
            self.assertIsNone(bridge._decision_resume)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_bridge_consumes_active_flip_batch_resume_payload(self) -> None:
        from apps.server.src.services.runtime_service import RuntimeDecisionResume, _ServerDecisionPolicyBridge

        class _DummyAi:
            def choose_active_flip_card(self, state, player, flippable_cards):
                del state, player, flippable_cards
                return None

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_active_flip_batch_resume_test",
                session_seats=[],
                human_seats=[0],
                ai_fallback=_DummyAi(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            state = type(
                "State",
                (),
                {
                    "rounds_completed": 0,
                    "turn_index": 0,
                    "active_by_card": {
                        1: "박수",
                        7: "아전",
                        8: "교리 연구관",
                    },
                },
            )()
            player = type("Player", (), {"player_id": 0, "cash": 10, "position": 0, "shards": 0})()
            bridge.set_decision_resume(
                RuntimeDecisionResume(
                    request_id="sess_active_flip_batch_resume_test:r1:t0:p1:active_flip:5",
                    player_id=1,
                    request_type="active_flip",
                    choice_id="none",
                    choice_payload={
                        "selected_choice_ids": ["1", "7", "none"],
                        "finish_after_selection": True,
                    },
                    resume_token="resume_active_flip",
                    frame_id="turn:1:p0",
                    module_id="mod:turn:1:p0:active_flip",
                    module_type="RoundEndCardFlipModule",
                    module_cursor="active_flip:await_choice",
                )
            )

            with patch.object(
                bridge._gateway,
                "resolve_human_prompt",
                side_effect=AssertionError("active flip resume must not create a new prompt"),
            ):
                result = bridge.choose_active_flip_card(state, player, [1, 7, 8])

            self.assertEqual(result, [1, 7])
            self.assertIsNone(bridge._decision_resume)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_bridge_defers_decision_resume_until_matching_replayed_prompt(self) -> None:
        RuntimeService._ensure_engine_import_path()
        from engine import DecisionRequest
        from apps.server.src.services.decision_gateway import PromptRequired
        from apps.server.src.services.runtime_service import RuntimeDecisionResume, _ServerDecisionPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            session_id = "sess_resume_bridge_replay_test"
            bridge = _ServerDecisionPolicyBridge(
                session_id=session_id,
                session_seats=[],
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            state = self._module_state(
                frame_id="round:1",
                module_id="mod:round:1:draft",
                module_type="DraftModule",
                module_cursor="draft:await_choice",
                rounds_completed=0,
                turn_index=0,
                block_ids=[0, 0],
                board=[],
                tile_owner=[],
                active_by_card={5: "교리 연구관", 7: "중매꾼"},
            )
            player = type(
                "Player",
                (),
                {
                    "player_id": 0,
                    "cash": 10,
                    "position": 0,
                    "shards": 0,
                    "drafted_cards": [],
                    "hidden_trick_deck_index": None,
                    "trick_hand": [],
                },
            )()
            draft_request = DecisionRequest(
                decision_name="choose_draft_card",
                request_type="draft_card",
                state=state,
                player=player,
                player_id=0,
                round_index=1,
                turn_index=0,
                args=([5, 7],),
                kwargs={},
                fallback_policy="required",
            )
            final_request = DecisionRequest(
                decision_name="choose_final_character",
                request_type="final_character",
                state=state,
                player=player,
                player_id=0,
                round_index=1,
                turn_index=0,
                args=([5, 7],),
                kwargs={},
                fallback_policy="required",
            )

            bridge.set_prompt_sequence(0)
            with self.assertRaises(PromptRequired) as raised:
                bridge.request(draft_request)
            draft_prompt = raised.exception.prompt
            self.assertEqual(draft_prompt["request_type"], "draft_card")
            accepted = self.prompt_service.submit_decision(
                {
                    **self._module_decision(draft_prompt, "5", player_id=1),
                    "type": "decision",
                    "choice_payload": {},
                    "provider": "human",
                }
            )
            self.assertEqual(accepted["status"], "accepted")

            bridge.set_decision_resume(
                RuntimeDecisionResume(
                    request_id=f"{session_id}:r1:t0:p1:final_character:2",
                    player_id=1,
                    request_type="final_character",
                    choice_id="5",
                    choice_payload={},
                    resume_token="token_final",
                    frame_id="round:1",
                    module_id="mod:round:1:draft",
                    module_type="DraftModule",
                    module_cursor="draft:await_choice",
                )
            )

            bridge.set_prompt_sequence(0)
            self.assertEqual(bridge.request(draft_request), 5)
            self.assertIsNotNone(bridge._decision_resume)
            self.assertEqual(bridge.request(final_request), "교리 연구관")
            self.assertIsNone(bridge._decision_resume)
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
                    self._module_prompt(
                        {
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                        }
                    ),
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            prompt = raised.exception.prompt
            self._assert_public_prompt_request_id(
                prompt,
                (
                    "sess_sparse_prompt_id_test:prompt:frame:turn%3A1%3Ap0:"
                    "module:mod%3Aturn%3A1%3Ap0%3Atest_prompt:cursor:test%3Aawait_choice:"
                    "p1:movement:0"
                ),
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_decision_gateway_leaves_pending_prompt_publish_to_runtime_boundary(self) -> None:
        from apps.server.src.services.decision_gateway import DecisionGateway, PromptRequired

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            gateway = DecisionGateway(
                session_id="sess_pending_prompt_repair",
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            prompt = self._module_prompt(
                {
                    "request_id": "repair_req_1",
                    "request_type": "final_character",
                    "player_id": 1,
                    "timeout_ms": 2000,
                    "legal_choices": [
                        {"choice_id": "character:6", "label": "박수"},
                        {"choice_id": "character:8", "label": "건설업자"},
                    ],
                    "fallback_policy": "timeout_fallback",
                    "public_context": {"round_index": 1, "turn_index": 1},
                },
                frame_id="round:1:draft:p1",
                module_type="DraftModule",
                module_cursor="final_character",
            )
            self.prompt_service.create_prompt("sess_pending_prompt_repair", prompt)

            with self.assertRaises(PromptRequired) as raised:
                gateway.resolve_human_prompt(
                    prompt,
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            messages = asyncio.run(self.stream_service.snapshot("sess_pending_prompt_repair"))
            prompt_messages = [msg for msg in messages if msg.type == "prompt"]
            requested_events = [
                msg
                for msg in messages
                if msg.type == "event" and msg.payload.get("event_type") == "decision_requested"
            ]

            public_request_id = self._assert_public_prompt_request_id(raised.exception.prompt, "repair_req_1")
            lifecycle = self.prompt_service.get_prompt_lifecycle(
                "repair_req_1",
                session_id="sess_pending_prompt_repair",
            )
            self.assertIsNotNone(lifecycle)
            assert lifecycle is not None
            self.assertEqual(lifecycle["state"], "created")
            self.assertEqual(lifecycle["request_id"], public_request_id)
            self.assertEqual(messages, [])

            self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                "sess_pending_prompt_repair",
                raised.exception.prompt,
            )
            messages = asyncio.run(self.stream_service.snapshot("sess_pending_prompt_repair"))
            prompt_messages = [msg for msg in messages if msg.type == "prompt"]
            requested_events = [
                msg
                for msg in messages
                if msg.type == "event" and msg.payload.get("event_type") == "decision_requested"
            ]
            self.assertEqual(len(prompt_messages), 1)
            self.assertEqual(prompt_messages[0].payload["request_id"], public_request_id)
            self.assertEqual(prompt_messages[0].payload["legacy_request_id"], "repair_req_1")
            self.assertEqual(prompt_messages[0].payload["legal_choices"][0]["label"], "박수")
            self.assertEqual(len(requested_events), 1)
            self.assertEqual(requested_events[0].payload["request_id"], public_request_id)
            self.assertEqual(requested_events[0].payload["legacy_request_id"], "repair_req_1")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_decision_gateway_checks_replay_without_waiting_for_new_prompt(self) -> None:
        from apps.server.src.services.decision_gateway import DecisionGateway, PromptRequired

        session_id = "sess_nonblocking_replay_probe"
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        original_wait = self.prompt_service.wait_for_decision
        observed_timeouts: list[int] = []
        try:
            def _record_wait(request_id: str, timeout_ms: int, session_id: str | None = None) -> dict | None:
                observed_timeouts.append(timeout_ms)
                return original_wait(request_id, timeout_ms=timeout_ms, session_id=session_id)

            self.prompt_service.wait_for_decision = _record_wait  # type: ignore[method-assign]
            gateway = DecisionGateway(
                session_id=session_id,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )

            with self.assertRaises(PromptRequired):
                gateway.resolve_human_prompt(
                    self._module_prompt(
                        {
                            "request_id": "nonblocking_probe_req_1",
                            "request_type": "movement",
                            "player_id": 1,
                            "timeout_ms": 2000,
                            "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                            "fallback_policy": "timeout_fallback",
                            "public_context": {"round_index": 1, "turn_index": 0},
                        }
                    ),
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            self.assertEqual(observed_timeouts, [0])
        finally:
            self.prompt_service.wait_for_decision = original_wait  # type: ignore[method-assign]
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_decision_gateway_reuses_pending_prompt_id_when_blocking(self) -> None:
        from apps.server.src.services.decision_gateway import DecisionGateway

        session_id = "sess_blocking_pending_reuse"
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        wait_thread: threading.Thread | None = None
        try:
            gateway = DecisionGateway(
                session_id=session_id,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=True,
            )
            prompt = self._module_prompt(
                {
                    "request_id": "blocking_reuse_req_1",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 500,
                    "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                    "fallback_policy": "timeout_fallback",
                    "public_context": {"round_index": 1, "turn_index": 0},
                }
            )
            self.prompt_service.create_prompt(session_id, prompt)

            result: dict[str, str] = {}
            errors: list[BaseException] = []

            def _wait_for_prompt() -> None:
                try:
                    result["choice"] = gateway.resolve_human_prompt(
                        prompt,
                        lambda response: str(response.get("choice_id", "")),
                        lambda: "fallback",
                    )
                except BaseException as exc:  # pragma: no cover - surfaced by assertion below
                    errors.append(exc)

            wait_thread = threading.Thread(target=_wait_for_prompt, daemon=True)
            wait_thread.start()

            observed_prompt: dict | None = None
            deadline = time.time() + 2.0
            while time.time() < deadline and observed_prompt is None:
                messages = asyncio.run_coroutine_threadsafe(
                    self.stream_service.snapshot(session_id),
                    loop,
                ).result(timeout=2.0)
                prompt_messages = [msg for msg in messages if msg.type == "prompt"]
                if prompt_messages:
                    observed_prompt = dict(prompt_messages[-1].payload)
                    break
                time.sleep(0.01)

            self.assertIsNotNone(observed_prompt)
            assert observed_prompt is not None
            accepted = self.prompt_service.submit_decision(
                self._module_decision(observed_prompt, "roll", player_id=1)
            )
            self.assertEqual(accepted["status"], "accepted")
            wait_thread.join(timeout=2.0)

            self.assertFalse(wait_thread.is_alive())
            self.assertEqual(errors, [])
            self._assert_public_prompt_request_id(observed_prompt, "blocking_reuse_req_1")
            self.assertEqual(result.get("choice"), "roll")

            messages = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot(session_id),
                loop,
            ).result(timeout=2.0)
            published_request_ids = [
                str(msg.payload.get("request_id"))
                for msg in messages
                if msg.type in {"prompt", "event"} and msg.payload.get("request_id")
            ]
            self.assertNotIn(f"{session_id}_req_", " ".join(published_request_ids))
        finally:
            if wait_thread is not None:
                wait_thread.join(timeout=1.0)
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_decision_gateway_has_no_process_local_request_seq_fallback(self) -> None:
        source = Path("apps/server/src/services/decision_gateway.py").read_text(encoding="utf-8")

        self.assertNotIn("_request_seq", source)
        self.assertNotIn("next_request_id", source)
        self.assertNotIn("uuid.uuid4", source)

    def test_runtime_prompt_boundary_materializes_missing_stream_prompt(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            prompt = self._module_prompt(
                {
                    "request_id": "runtime_boundary_req_1",
                    "request_type": "final_character",
                    "player_id": 1,
                    "timeout_ms": 30000,
                    "legal_choices": [
                        {"choice_id": "character:6", "label": "박수"},
                        {"choice_id": "character:8", "label": "건설업자"},
                    ],
                    "fallback_policy": "required",
                    "public_context": {"round_index": 1, "turn_index": 0},
                },
                frame_id="round:1:draft:p1",
                module_type="DraftModule",
                module_cursor="final_character",
            )
            self.prompt_service.create_prompt("sess_runtime_boundary_prompt", prompt)

            self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                "sess_runtime_boundary_prompt",
                prompt,
            )
            self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                "sess_runtime_boundary_prompt",
                prompt,
            )

            messages = asyncio.run(self.stream_service.snapshot("sess_runtime_boundary_prompt"))
            prompt_messages = [msg for msg in messages if msg.type == "prompt"]
            requested_events = [
                msg
                for msg in messages
                if msg.type == "event" and msg.payload.get("event_type") == "decision_requested"
            ]

            self.assertEqual(len(prompt_messages), 1)
            public_request_id = self._assert_public_prompt_request_id(
                prompt_messages[0].payload,
                "runtime_boundary_req_1",
            )
            self.assertEqual(
                [choice["label"] for choice in prompt_messages[0].payload["legal_choices"]],
                ["박수", "건설업자"],
            )
            self.assertEqual(len(requested_events), 1)
            self.assertEqual(requested_events[0].payload["request_id"], public_request_id)
            self.assertEqual(requested_events[0].payload["legacy_request_id"], "runtime_boundary_req_1")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_runtime_prompt_boundary_can_publish_after_view_commit_guardrail(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            session = self.session_service.create_session(
                [
                    {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                    {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                ],
                config={"max_players": 2},
            )
            seat = session.seats[1]
            prompt = self._module_prompt(
                {
                    "request_id": "runtime_boundary_delayed_req_1",
                    "request_type": "dice_roll",
                    "player_id": 2,
                    "prompt_instance_id": 12,
                    "timeout_ms": 30000,
                    "legal_choices": [{"choice_id": "roll"}],
                    "fallback_policy": "required",
                    "public_context": {"round_index": 1, "turn_index": 4},
                },
                frame_id="turn:1:p1",
                module_type="DiceRollModule",
                module_cursor="await_roll",
            )

            payload = self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                session.session_id,
                prompt,
                publish=False,
            )

            self.assertIsNotNone(payload)
            pending_prompt = self.prompt_service.get_pending_prompt("runtime_boundary_delayed_req_1")
            self.assertIsNotNone(pending_prompt)
            self.assertEqual(pending_prompt.payload["player_id"], 2)
            public_request_id = self._assert_public_prompt_request_id(
                payload,
                "runtime_boundary_delayed_req_1",
            )
            messages_before_publish = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot(session.session_id),
                loop,
            ).result(timeout=2.0)
            self.assertEqual(messages_before_publish, [])

            self.runtime_service._publish_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                session.session_id,
                payload,
            )
            messages_after_publish = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot(session.session_id),
                loop,
            ).result(timeout=2.0)

            self.assertEqual([msg.type for msg in messages_after_publish], ["prompt", "event"])
            self.assertEqual(messages_after_publish[0].payload["request_id"], public_request_id)
            self.assertEqual(
                messages_after_publish[0].payload["legacy_request_id"],
                "runtime_boundary_delayed_req_1",
            )
            self.assertNotIn("player_id", messages_after_publish[0].payload)
            self.assertEqual(messages_after_publish[0].payload["legacy_player_id"], 2)
            self.assertNotIn("player_id_alias_role", messages_after_publish[0].payload)
            self.assertEqual(messages_after_publish[0].payload["primary_player_id"], seat.public_player_id)
            self.assertEqual(messages_after_publish[0].payload["primary_player_id_source"], "public")
            self.assertEqual(messages_after_publish[0].payload["public_player_id"], seat.public_player_id)
            self.assertEqual(messages_after_publish[0].payload["seat_id"], seat.seat_id)
            self.assertEqual(messages_after_publish[0].payload["viewer_id"], seat.viewer_id)
            self.assertEqual(messages_after_publish[1].payload["event_type"], "decision_requested")
            self.assertEqual(messages_after_publish[1].payload["request_id"], public_request_id)
            self.assertEqual(
                messages_after_publish[1].payload["legacy_request_id"],
                "runtime_boundary_delayed_req_1",
            )
            self.assertNotIn("player_id", messages_after_publish[1].payload)
            self.assertEqual(messages_after_publish[1].payload["legacy_player_id"], 2)
            self.assertNotIn("player_id_alias_role", messages_after_publish[1].payload)
            self.assertEqual(messages_after_publish[1].payload["primary_player_id"], seat.public_player_id)
            self.assertEqual(messages_after_publish[1].payload["primary_player_id_source"], "public")
            self.assertEqual(messages_after_publish[1].payload["public_player_id"], seat.public_player_id)
            self.assertEqual(messages_after_publish[1].payload["seat_id"], seat.seat_id)
            self.assertEqual(messages_after_publish[1].payload["viewer_id"], seat.viewer_id)
            assert_no_public_identity_numeric_leaks(
                messages_after_publish[0].payload,
                boundary="runtime_prompt_message",
            )
            assert_no_public_identity_numeric_leaks(
                messages_after_publish[1].payload,
                boundary="runtime_decision_requested_event",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_runtime_prompt_boundary_enriches_target_choice_identity_companions(self) -> None:
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            session = self._create_started_two_player_session()
            target_seat = session.seats[1]
            prompt = self._module_prompt(
                {
                    "request_id": "runtime_boundary_target_req_1",
                    "request_type": "doctrine_relief",
                    "player_id": 1,
                    "prompt_instance_id": 13,
                    "timeout_ms": 30000,
                    "legal_choices": [
                        {
                            "choice_id": "1",
                            "label": "P2",
                            "value": {"target_player_id": 2, "burden_count": 1},
                        }
                    ],
                    "fallback_policy": "required",
                    "public_context": {"round_index": 1, "turn_index": 4},
                },
                frame_id="turn:1:p0",
                module_type="DoctrineReliefModule",
                module_cursor="await_doctrine_relief",
            )

            payload = self.runtime_service._materialize_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                session.session_id,
                prompt,
                publish=False,
            )

            self.assertIsNotNone(payload)
            pending_prompt = self.prompt_service.get_pending_prompt(
                "runtime_boundary_target_req_1",
                session_id=session.session_id,
            )
            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None
            pending_value = pending_prompt.payload["legal_choices"][0]["value"]
            self.assertEqual(pending_value["target_player_id"], 2)
            self.assertEqual(pending_value["target_legacy_player_id"], 2)
            self.assertEqual(pending_value["target_public_player_id"], target_seat.public_player_id)
            self.assertEqual(pending_value["target_seat_id"], target_seat.seat_id)
            self.assertEqual(pending_value["target_viewer_id"], target_seat.viewer_id)

            self.runtime_service._publish_prompt_boundary_sync(  # type: ignore[attr-defined]
                loop,
                session.session_id,
                payload,
            )
            messages = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot(session.session_id),
                loop,
            ).result(timeout=2.0)
            prompt_messages = [msg for msg in messages if msg.type == "prompt"]
            self.assertEqual(len(prompt_messages), 1)
            published_value = prompt_messages[0].payload["legal_choices"][0]["value"]
            self.assertEqual(published_value["target_player_id"], 2)
            self.assertEqual(published_value["target_legacy_player_id"], 2)
            self.assertEqual(published_value["target_public_player_id"], target_seat.public_player_id)
            self.assertEqual(published_value["target_seat_id"], target_seat.seat_id)
            self.assertEqual(published_value["target_viewer_id"], target_seat.viewer_id)
            assert_no_public_identity_numeric_leaks(
                prompt_messages[0].payload,
                boundary="runtime_target_choice_prompt_message",
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_decision_gateway_rejects_replayed_decision_when_prompt_shape_changes(self) -> None:
        from apps.server.src.services.decision_gateway import (
            DecisionGateway,
            PromptFingerprintMismatch,
            PromptRequired,
        )

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            gateway = DecisionGateway(
                session_id="sess_prompt_fingerprint_test",
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
                blocking_human_prompts=False,
            )
            original_prompt = self._module_prompt(
                {
                    "request_id": "shape_req_1",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 2000,
                    "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                    "fallback_policy": "timeout_fallback",
                    "public_context": {"round_index": 1, "turn_index": 0},
                }
            )

            with self.assertRaises(PromptRequired):
                gateway.resolve_human_prompt(
                    original_prompt,
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )
            accepted = self.prompt_service.submit_decision(
                self._module_decision(original_prompt, "roll", player_id=1)
            )
            self.assertEqual(accepted["status"], "accepted")

            changed_prompt = {
                **original_prompt,
                "legal_choices": [{"choice_id": "card_1", "label": "Use card"}],
            }
            with self.assertRaises(PromptFingerprintMismatch):
                gateway.resolve_human_prompt(
                    changed_prompt,
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_prompt_boundary_replay_uses_existing_continuation_contract(self) -> None:
        frame_id = "seq:action:1:p3:130"
        module_id = "mod:seq:action:1:p3:130:arrivaltile"
        module_type = "ArrivalTileModule"
        module_cursor = "await_action_prompt"
        request_id = "req_replay_contract"
        original_context = {
            "round_index": 1,
            "turn_index": 3,
            "player_cash": 28,
            "current_f_value": 9,
        }
        original_choices = [
            {"choice_id": "yes", "label": "Pay 2", "value": {"burden_cost": 2}},
            {"choice_id": "no", "label": "Keep burden", "value": {"burden_cost": 2}},
        ]
        continuation = SimpleNamespace(
            request_id=request_id,
            request_type="burden_exchange",
            player_id=0,
            prompt_instance_id=32,
            legal_choices=original_choices,
            public_context=original_context,
            resume_token="resume_existing_prompt",
            frame_id=frame_id,
            module_id=module_id,
            module_type=module_type,
            module_cursor=module_cursor,
        )
        state = self._module_state(
            rounds_completed=1,
            turn_index=3,
            frame_id=frame_id,
            module_id=module_id,
            module_type=module_type,
            module_cursor=module_cursor,
        )
        state.runtime_active_prompt = continuation
        active_call = SimpleNamespace(
            invocation=SimpleNamespace(state=state),
            request=SimpleNamespace(
                request_type="burden_exchange",
                player_id=0,
                fallback_policy="required",
                public_context={
                    "round_index": 1,
                    "turn_index": 3,
                    "player_cash": 999,
                    "current_f_value": 10,
                },
            ),
            legal_choices=[
                {"choice_id": "yes", "label": "Pay 9", "value": {"burden_cost": 9}},
                {"choice_id": "no", "label": "Keep burden", "value": {"burden_cost": 9}},
            ],
        )
        pending_payload = ensure_prompt_fingerprint(
            {
                "request_id": request_id,
                "request_type": "burden_exchange",
                "player_id": 1,
                "prompt_instance_id": 32,
                "legal_choices": original_choices,
                "public_context": original_context,
                "timeout_ms": 30000,
                "fallback_policy": "required",
                "runner_kind": "module",
                "resume_token": "resume_existing_prompt",
                "frame_id": frame_id,
                "module_id": module_id,
                "module_type": module_type,
                "module_cursor": module_cursor,
            }
        )

        envelope = PromptBoundaryBuilder(current_prompt_sequence=32).prepare(
            {"request_type": "burden_exchange", "fallback_policy": "required"},
            active_call=active_call,
        )
        replay_payload = ensure_prompt_fingerprint({**envelope, "timeout_ms": 30000})

        self.assertEqual(envelope["request_id"], request_id)
        self.assertEqual(envelope["prompt_instance_id"], 32)
        self.assertEqual(envelope["legal_choices"], original_choices)
        self.assertEqual(envelope["public_context"], original_context)
        self.assertFalse(prompt_fingerprint_mismatch(pending_payload, replay_payload))

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

            state = self._module_state(rounds_completed=1, turn_index=4)
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
                self._module_decision(pending_prompt.payload, "minus_one", player_id=1)
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

            state = self._module_state(rounds_completed=1, turn_index=0)
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
                self._module_decision(pending_prompt.payload, "minus_one", player_id=1)
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
                    self._module_prompt(
                        {
                        "request_id": "bridge_timeout_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 50,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "fallback_choice_id": "roll",
                        "public_context": {"round_index": 1, "turn_index": 1},
                        }
                    ),
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
            prompt_message = next((msg for msg in published if msg.type == "prompt"), None)
            self.assertIsNotNone(prompt_message)
            assert prompt_message is not None
            public_request_id = self._assert_public_prompt_request_id(
                prompt_message.payload,
                "bridge_timeout_1",
            )
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == public_request_id
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
            self.assertEqual(requested.payload.get("legacy_request_id"), "bridge_timeout_1")
            self.assertEqual(resolved.payload.get("legacy_request_id"), "bridge_timeout_1")
            self.assertEqual(timeout_event.payload.get("legacy_request_id"), "bridge_timeout_1")
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
                    self._module_prompt(
                        {
                        "request_id": "bridge_parser_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {"round_index": 1, "turn_index": 2},
                        }
                    ),
                    lambda _response: (_ for _ in ()).throw(ValueError("parser failure")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_prompt = None
            for _ in range(100):
                pending_prompt = self.prompt_service.get_pending_prompt(
                    "bridge_parser_1",
                    session_id="sess_bridge_parser_fallback",
                )
                if pending_prompt is not None:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None

            decision_state = self.prompt_service.submit_decision(
                self._module_decision(pending_prompt.payload, "roll", player_id=1)
            )
            self.assertEqual(decision_state["status"], "accepted")
            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "fallback")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_parser_fallback"),
                loop,
            ).result(timeout=2.0)
            public_request_id = pending_prompt.request_id
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == public_request_id
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            self.assertIsNotNone(requested)
            self.assertEqual(len(resolved_all), 1)
            self.assertEqual(requested.payload.get("legacy_request_id"), "bridge_parser_1")
            self.assertEqual(resolved_all[0].payload.get("legacy_request_id"), "bridge_parser_1")
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

    def load_cached_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, player_id
        if viewer == "public":
            return {"players": {"items": []}}
        return {}

    def load_view_state(self, session_id: str) -> dict:
        del session_id
        return {"view_state_alias": True}


class _MutableGameStateStoreStub:
    def __init__(self) -> None:
        self.current_state: dict = {}
        self.checkpoint: dict = {}
        self.view_state: dict = {}
        self.view_commits: dict[str, dict] = {}
        self.commits: list[dict] = []

    def load_checkpoint(self, session_id: str) -> dict | None:
        del session_id
        return copy.deepcopy(self.checkpoint) if self.checkpoint else None

    def load_current_state(self, session_id: str) -> dict | None:
        del session_id
        return copy.deepcopy(self.current_state) if self.current_state else None

    def load_cached_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, viewer, player_id
        return {}

    def load_view_state(self, session_id: str) -> dict:
        del session_id
        return copy.deepcopy(self.view_state)

    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        del session_id
        label = f"player:{int(player_id)}" if viewer == "player" and player_id is not None else str(viewer)
        payload = self.view_commits.get(label)
        return copy.deepcopy(payload) if payload is not None else None

    def commit_transition(
        self,
        session_id: str,
        *,
        current_state: dict,
        checkpoint: dict,
        view_state: dict | None = None,
        view_commits: dict[str, dict] | None = None,
        command_consumer_name: str | None = None,
        command_seq: int | None = None,
        runtime_event_payload: dict | None = None,
        runtime_event_server_time_ms: int | None = None,
        expected_previous_commit_seq: int | None = None,
    ) -> None:
        self.current_state = copy.deepcopy(current_state)
        self.checkpoint = copy.deepcopy(checkpoint)
        self.view_state = copy.deepcopy(view_state or {})
        self.view_commits = copy.deepcopy(view_commits or {})
        self.commits.append(
            {
                "session_id": session_id,
                "current_state": copy.deepcopy(current_state),
                "checkpoint": copy.deepcopy(checkpoint),
                "view_state": copy.deepcopy(view_state or {}),
                "view_commits": copy.deepcopy(view_commits or {}),
                "command_consumer_name": command_consumer_name,
                "command_seq": command_seq,
                "runtime_event_payload": copy.deepcopy(runtime_event_payload or {}),
                "runtime_event_server_time_ms": runtime_event_server_time_ms,
                "expected_previous_commit_seq": expected_previous_commit_seq,
            }
        )


class _RuntimeStateStoreStub:
    def __init__(self) -> None:
        self.statuses: dict[str, dict] = {}
        self.leases: dict[str, str] = {}
        self.refresh_calls: list[tuple[str, str, int]] = []

    def save_status(self, session_id: str, payload: dict) -> None:
        self.statuses[session_id] = dict(payload)

    def load_status(self, session_id: str) -> dict | None:
        payload = self.statuses.get(session_id)
        return dict(payload) if payload is not None else None

    def lease_owner(self, session_id: str) -> str | None:
        return self.leases.get(session_id)

    def acquire_lease(self, session_id: str, worker_id: str, ttl_ms: int) -> bool:
        del ttl_ms
        owner = self.leases.get(session_id)
        if owner is not None and owner != worker_id:
            return False
        self.leases[session_id] = worker_id
        return True

    def refresh_lease(self, session_id: str, worker_id: str, ttl_ms: int) -> bool:
        self.refresh_calls.append((session_id, worker_id, int(ttl_ms)))
        if self.leases.get(session_id) != worker_id:
            return False
        self.leases[session_id] = worker_id
        return True

    def release_lease(self, session_id: str, worker_id: str) -> bool:
        if self.leases.get(session_id) != worker_id:
            return False
        self.leases.pop(session_id, None)
        return True

    def append_fallback(self, session_id: str, record: dict, *, max_items: int = 20) -> None:
        del session_id, record, max_items

    def recent_fallbacks(self, session_id: str, limit: int = 10) -> list[dict]:
        del session_id, limit
        return []

    def delete_session_data(self, session_id: str) -> None:
        self.statuses.pop(session_id, None)


class _DoneRuntimeTaskStub:
    def done(self) -> bool:
        return True


class _PendingRuntimeTaskStub:
    def done(self) -> bool:
        return False


class _CommandStoreStub:
    def __init__(self, *, offset: int = 0, commands: list[dict] | None = None) -> None:
        self.offset = int(offset)
        self.commands = list(commands or [])

    def load_consumer_offset(self, consumer_name: str, session_id: str) -> int:
        del consumer_name, session_id
        return self.offset

    def list_commands(self, session_id: str) -> list[dict]:
        del session_id
        return list(self.commands)

    def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
        del consumer_name, session_id
        self.offset = max(self.offset, int(seq))


class _DebugEventStub:
    def __init__(self, payload: dict) -> None:
        self._payload = copy.deepcopy(payload)

    def to_dict(self) -> dict:
        return copy.deepcopy(self._payload)


class _PublishedEventStub:
    def __init__(self, seq: int) -> None:
        self.seq = seq


class _IdempotentStreamServiceStub:
    def __init__(self) -> None:
        self.seq = 0
        self.deduplicate_next_publish = False
        self.published_payloads: list[dict] = []

    async def latest_seq(self, session_id: str) -> int:
        del session_id
        return self.seq

    async def publish(self, session_id: str, event_type: str, payload: dict) -> _PublishedEventStub:
        del session_id, event_type
        self.published_payloads.append(copy.deepcopy(payload))
        if self.deduplicate_next_publish:
            self.deduplicate_next_publish = False
            return _PublishedEventStub(self.seq)
        self.seq += 1
        return _PublishedEventStub(self.seq)


class _temporary_debug_env:
    def __init__(self, *, enabled: str, log_dir: str, run_id: str | None = None) -> None:
        self._enabled = enabled
        self._log_dir = log_dir
        self._run_id = run_id
        self._before_enabled: str | None = None
        self._before_dir: str | None = None
        self._before_run_id: str | None = None

    def __enter__(self) -> None:
        self._before_enabled = os.environ.get("MRN_DEBUG_GAME_LOGS")
        self._before_dir = os.environ.get("MRN_DEBUG_GAME_LOG_DIR")
        self._before_run_id = os.environ.get("MRN_DEBUG_GAME_LOG_RUN_ID")
        os.environ["MRN_DEBUG_GAME_LOGS"] = self._enabled
        os.environ["MRN_DEBUG_GAME_LOG_DIR"] = self._log_dir
        if self._run_id is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_RUN_ID", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_RUN_ID"] = self._run_id

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._before_enabled is None:
            os.environ.pop("MRN_DEBUG_GAME_LOGS", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOGS"] = self._before_enabled
        if self._before_dir is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_DIR", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_DIR"] = self._before_dir
        if self._before_run_id is None:
            os.environ.pop("MRN_DEBUG_GAME_LOG_RUN_ID", None)
        else:
            os.environ["MRN_DEBUG_GAME_LOG_RUN_ID"] = self._before_run_id


if __name__ == "__main__":
    unittest.main()
