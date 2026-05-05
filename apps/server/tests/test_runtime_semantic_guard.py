from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

import apps.server.src.domain.runtime_semantic_guard as runtime_semantic_guard
from apps.server.src.domain.runtime_semantic_guard import (
    ACTION_TYPE_REQUIRED_MODULES,
    MODULE_ALLOWED_FRAMES,
    RuntimeSemanticViolation,
    validate_checkpoint_payload,
    validate_stream_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


def test_rejects_simultaneous_module_prompt_without_batch_id() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="simultaneous prompt missing batch_id"):
        validate_stream_payload(
            history=[],
            msg_type="prompt",
            payload={
                "runner_kind": "module",
                "request_id": "req_resupply_p1",
                "request_type": "burden_exchange",
                "player_id": 1,
                "resume_token": "resume:1",
                "frame_id": "simul:resupply:1:0",
                "module_id": "mod:simul:resupply:1:0:processing",
                "module_type": "ResupplyModule",
                "module_cursor": "await_resupply_batch:1",
                "legal_choices": [{"choice_id": "yes"}],
            },
        )


def test_rejects_simultaneous_module_prompt_without_batch_wire_state() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="simultaneous prompt missing batch state"):
        validate_stream_payload(
            history=[],
            msg_type="prompt",
            payload={
                "runner_kind": "module",
                "request_id": "req_resupply_p1",
                "request_type": "burden_exchange",
                "player_id": 1,
                "resume_token": "resume:1",
                "frame_id": "simul:resupply:1:0",
                "module_id": "mod:simul:resupply:1:0:processing",
                "module_type": "ResupplyModule",
                "module_cursor": "await_resupply_batch:1",
                "batch_id": "batch:simul:resupply:1:0",
                "legal_choices": [{"choice_id": "yes"}],
            },
        )


def test_allows_single_player_prompt_inside_simultaneous_frame_without_batch_state() -> None:
    validate_stream_payload(
        history=[],
        msg_type="prompt",
        payload={
            "runner_kind": "module",
            "request_id": "req_hidden_p1",
            "request_type": "hidden_trick_card",
            "player_id": 1,
            "resume_token": "resume:1",
            "frame_id": "simul:resupply:1:0",
            "module_id": "mod:simul:resupply:1:0:processing",
            "module_type": "ResupplyModule",
            "module_cursor": "hidden_trick_card:await_choice",
            "legal_choices": [{"choice_id": "0"}],
        },
    )


def test_semantic_guard_derives_module_and_action_catalogs_from_engine_runtime_modules() -> None:
    from runtime_modules.catalog import MODULE_RULES
    from runtime_modules.sequence_modules import (
        ACTION_TYPE_TO_MODULE_TYPE,
        FORTUNE_ACTION_TYPE_TO_MODULE_TYPE,
        SIMULTANEOUS_ACTION_TYPE_TO_MODULE_TYPE,
    )

    assert MODULE_ALLOWED_FRAMES == {
        module_type: set(rule.frame_types)
        for module_type, rule in MODULE_RULES.items()
    }
    assert ACTION_TYPE_REQUIRED_MODULES == {
        **ACTION_TYPE_TO_MODULE_TYPE,
        **FORTUNE_ACTION_TYPE_TO_MODULE_TYPE,
        **SIMULTANEOUS_ACTION_TYPE_TO_MODULE_TYPE,
    }
    source = inspect.getsource(runtime_semantic_guard)
    assert "MODULE_ALLOWED_FRAMES: dict" not in source
    assert "ACTION_TYPE_REQUIRED_MODULES: dict" not in source


def test_semantic_guard_imports_engine_catalog_without_external_pythonpath() -> None:
    env = {**os.environ, "PYTHONPATH": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import apps.server.src.domain.runtime_semantic_guard as g; "
                "print(len(g.MODULE_ALLOWED_FRAMES), len(g.ACTION_TYPE_REQUIRED_MODULES))"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip()


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


def test_card_flip_guard_uses_checkpoint_active_module_when_payload_omits_module_id() -> None:
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
                            {"module_id": "mod:p1", "module_type": "PlayerTurnModule", "status": "skipped"},
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


def test_checkpoint_rejects_action_payload_owned_by_wrong_sequence_module() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="resolve_purchase_tile.*PurchaseCommitModule.*MapMoveModule"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:action:1:p0:move",
                        "frame_type": "sequence",
                        "status": "running",
                        "active_module_id": "mod:move",
                        "module_queue": [
                            {
                                "module_id": "mod:move",
                                "module_type": "MapMoveModule",
                                "status": "running",
                                "payload": {
                                    "action": {
                                        "action_id": "act:purchase",
                                        "type": "resolve_purchase_tile",
                                        "actor_player_id": 0,
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        )


def test_checkpoint_allows_matching_native_action_sequence_module() -> None:
    validate_checkpoint_payload(
        {
            "runtime_runner_kind": "module",
            "runtime_frame_stack": [
                {
                    "frame_id": "seq:action:1:p0:move",
                    "frame_type": "sequence",
                    "status": "running",
                    "active_module_id": "mod:move",
                    "module_queue": [
                        {
                            "module_id": "mod:move",
                            "module_type": "MapMoveModule",
                            "status": "running",
                            "payload": {
                                "action": {
                                    "action_id": "act:move",
                                    "type": "apply_move",
                                    "actor_player_id": 0,
                                }
                            },
                        }
                    ],
                }
            ],
        }
    )


def test_checkpoint_allows_matching_simultaneous_resupply_action_module() -> None:
    validate_checkpoint_payload(
        {
            "runtime_runner_kind": "module",
            "runtime_frame_stack": [
                {
                    "frame_id": "simul:resupply:1:3",
                    "frame_type": "simultaneous",
                    "status": "running",
                    "active_module_id": "mod:resupply",
                    "module_queue": [
                        {
                            "module_id": "mod:resupply",
                            "module_type": "ResupplyModule",
                            "status": "running",
                            "payload": {
                                "action": {
                                    "action_id": "act:supply:1:3",
                                    "type": "resolve_supply_threshold",
                                    "actor_player_id": 0,
                                    "source": "supply_threshold",
                                    "payload": {
                                        "threshold": 3,
                                        "participants": [0, 1, 2, 3],
                                    },
                                }
                            },
                        }
                    ],
                }
            ],
        }
    )


def test_checkpoint_rejects_turn_end_snapshot_sequence_adapter() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="TurnEndSnapshotModule is not allowed in sequence frame"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:turn_completion:1:p0:1",
                        "frame_type": "sequence",
                        "status": "running",
                        "active_module_id": "mod:turn-end",
                        "module_queue": [
                            {
                                "module_id": "mod:turn-end",
                                "module_type": "TurnEndSnapshotModule",
                                "status": "running",
                                "payload": {
                                    "pending_turn_completion": {
                                        "player_id": 0,
                                        "finisher_before": 0,
                                        "disruption_before": {},
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        )


def test_checkpoint_rejects_uncatalogued_action_module_owner() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="action type apply_move belongs to MapMoveModule"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:action:1:p0:uncatalogued",
                        "frame_type": "sequence",
                        "status": "running",
                        "active_module_id": "mod:uncatalogued",
                        "module_queue": [
                            {
                                "module_id": "mod:uncatalogued",
                                "module_type": "UncataloguedActionModule",
                                "status": "running",
                                "payload": {
                                    "action": {
                                        "action_id": "act:uncatalogued",
                                        "type": "apply_move",
                                        "actor_player_id": 0,
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        )


def test_checkpoint_rejects_unknown_action_payload_without_native_module_owner() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="unknown action type resolve_unreviewed_legacy_effect"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:action:1:p0:unknown",
                        "frame_type": "sequence",
                        "status": "running",
                        "active_module_id": "mod:unknown",
                        "module_queue": [
                            {
                                "module_id": "mod:unknown",
                                "module_type": "MapMoveModule",
                                "status": "running",
                                "payload": {
                                    "action": {
                                        "action_id": "act:unknown",
                                        "type": "resolve_unreviewed_legacy_effect",
                                        "actor_player_id": 0,
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        )


def test_checkpoint_rejects_unknown_fortune_action_even_inside_fortune_module() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="unknown action type resolve_fortune_unreviewed_effect"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:action:1:p0:fortune",
                        "frame_type": "sequence",
                        "status": "running",
                        "active_module_id": "mod:fortune",
                        "module_queue": [
                            {
                                "module_id": "mod:fortune",
                                "module_type": "FortuneResolveModule",
                                "status": "running",
                                "payload": {
                                    "action": {
                                        "action_id": "act:fortune",
                                        "type": "resolve_fortune_unreviewed_effect",
                                        "actor_player_id": 0,
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        )


def test_checkpoint_rejects_rent_action_outside_rent_payment_module() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="resolve_rent_payment.*RentPaymentModule.*ArrivalTileModule"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:action:1:p0:arrival",
                        "frame_type": "sequence",
                        "status": "running",
                        "active_module_id": "mod:arrival",
                        "module_queue": [
                            {
                                "module_id": "mod:arrival",
                                "module_type": "ArrivalTileModule",
                                "status": "running",
                                "payload": {
                                    "action": {
                                        "action_id": "act:rent",
                                        "type": "resolve_rent_payment",
                                        "actor_player_id": 0,
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        )


def test_checkpoint_allows_matching_rent_payment_sequence_module() -> None:
    validate_checkpoint_payload(
        {
            "runtime_runner_kind": "module",
            "runtime_frame_stack": [
                {
                    "frame_id": "seq:action:1:p0:rent",
                    "frame_type": "sequence",
                    "status": "running",
                    "active_module_id": "mod:rent",
                    "module_queue": [
                        {
                            "module_id": "mod:rent",
                            "module_type": "RentPaymentModule",
                            "status": "running",
                            "payload": {
                                "action": {
                                    "action_id": "act:rent",
                                    "type": "resolve_rent_payment",
                                    "actor_player_id": 0,
                                }
                            },
                        }
                    ],
                }
            ],
        }
    )
