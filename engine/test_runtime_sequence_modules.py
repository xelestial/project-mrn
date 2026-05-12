from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from state import ActionEnvelope
from config import GameConfig
from state import GameState
from runtime_modules.contracts import Modifier, ModifierRegistryState, ModuleJournalEntry, ModuleRef
from runtime_modules.modifiers import MUROE_SKILL_SUPPRESSION_KIND, MUROE_SKILL_SUPPRESSION_REASON
from runtime_modules.round_modules import build_round_frame
from runtime_modules.runner import ModuleRunner, ModuleRunnerError
from runtime_modules.sequence_modules import (
    ACTION_TYPE_TO_MODULE_TYPE,
    FORTUNE_ACTION_TYPE_TO_MODULE_TYPE,
    TRICK_SEQUENCE_MODULE_TYPES,
    UnknownActionTypeError,
    build_action_sequence_frame,
    build_roll_and_arrive_sequence_frame,
    build_trick_sequence_frame,
    module_type_for_action,
)
from runtime_modules.simultaneous import build_resupply_frame
from runtime_modules.turn_modules import build_turn_frame


def test_trick_sequence_frame_contains_trick_boundary_modules() -> None:
    frame = build_trick_sequence_frame(
        1,
        0,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trickwindow",
    )

    assert frame.frame_type == "sequence"
    assert [module.module_type for module in frame.module_queue] == list(TRICK_SEQUENCE_MODULE_TYPES)
    assert frame.parent_frame_id == "turn:1:p0"


def test_fortune_extra_roll_is_sequence_not_new_turn() -> None:
    frame = build_roll_and_arrive_sequence_frame(
        3,
        1,
        2,
        parent_frame_id="turn:3:p1",
        parent_module_id="mod:turn:3:p1:fortune",
    )

    assert frame.frame_type == "sequence"
    assert frame.owner_player_id == 1
    assert frame.frame_id.startswith("seq:roll_and_arrive")
    assert [module.module_type for module in frame.module_queue] == [
        "FortuneResolveModule",
        "MapMoveModule",
        "ArrivalTileModule",
    ]


def test_action_sequence_frame_maps_pending_actions_to_typed_modules() -> None:
    frame = build_action_sequence_frame(
        2,
        0,
        4,
        [
            {
                "action_id": "a1",
                "type": "request_purchase_tile",
                "actor_player_id": 0,
                "source": "landing",
                "payload": {"tile_index": 5},
            },
            {
                "action_id": "a2",
                "type": "resolve_rent_payment",
                "actor_player_id": 0,
                "source": "rent",
                "payload": {"tile_index": 8, "owner": 1},
            },
            {
                "action_id": "a3",
                "type": "resolve_fortune_land_thief",
                "actor_player_id": 0,
                "source": "fortune",
                "payload": {},
            },
        ],
        parent_frame_id="round:2",
        parent_module_id="mod:turn:2:p0:0:playerturn",
    )

    assert frame.frame_type == "sequence"
    assert [module.module_type for module in frame.module_queue] == [
        ACTION_TYPE_TO_MODULE_TYPE["request_purchase_tile"],
        ACTION_TYPE_TO_MODULE_TYPE["resolve_rent_payment"],
        "FortuneResolveModule",
    ]
    assert frame.module_queue[0].payload["action"]["action_id"] == "a1"


def test_fortune_resolve_has_explicit_sequence_handler_not_payload_fallback() -> None:
    from runtime_modules.handlers.sequence import SEQUENCE_FRAME_HANDLERS

    assert "FortuneResolveModule" in SEQUENCE_FRAME_HANDLERS


def test_fortune_action_types_are_never_legacy_or_turn_modules() -> None:
    assert set(FORTUNE_ACTION_TYPE_TO_MODULE_TYPE.values()) == {"FortuneResolveModule"}
    assert {
        module_type_for_action(action_type)
        for action_type in FORTUNE_ACTION_TYPE_TO_MODULE_TYPE
    } == {"FortuneResolveModule"}


def test_lap_reward_action_is_owned_by_native_lap_reward_module() -> None:
    assert module_type_for_action("resolve_lap_reward") == "LapRewardModule"


def test_prompt_resuming_actions_are_owned_by_native_sequence_modules() -> None:
    prompt_action_boundaries = {
        "resolve_mark": "PendingMarkResolutionModule",
        "resolve_lap_reward": "LapRewardModule",
        "request_purchase_tile": "PurchaseDecisionModule",
        "resolve_purchase_tile": "PurchaseCommitModule",
        "request_score_token_placement": "ScoreTokenPlacementPromptModule",
        "resolve_score_token_placement": "ScoreTokenPlacementCommitModule",
        "resolve_trick_tile_rent_modifier": "TrickTileRentModifierModule",
    }

    for action_type, module_type in prompt_action_boundaries.items():
        assert module_type_for_action(action_type) == module_type
        assert module_type.endswith("Module")


def test_unknown_fortune_action_type_must_be_catalogued_before_sequence_build() -> None:
    with pytest.raises(UnknownActionTypeError, match="resolve_fortune_unreviewed_effect"):
        module_type_for_action("resolve_fortune_unreviewed_effect")


def test_unknown_action_type_cannot_be_wrapped_in_legacy_action_sequence() -> None:
    with pytest.raises(UnknownActionTypeError, match="resolve_unreviewed_legacy_effect"):
        build_action_sequence_frame(
            1,
            0,
            0,
            [{"type": "resolve_unreviewed_legacy_effect", "actor_player_id": 0}],
            parent_frame_id="turn:1:p0",
            parent_module_id="mod:turn:1:p0:arrival",
            session_id="s1",
        )


def test_fortune_followup_is_parented_under_current_sequence_module() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _execute_action(self, state, action, *, queue_followups: bool):
            assert action.type == "resolve_fortune_land_thief"
            assert queue_followups is True
            state.pending_actions.append(
                ActionEnvelope(
                    action_id="fortune-followup-move",
                    type="apply_move",
                    actor_player_id=0,
                    source="fortune",
                    payload={"move_value": 2},
                )
            )
            return {"type": "QUEUED_MOVE"}

        def _log(self, _event):
            return None

    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [
            {
                "action_id": "fortune-1",
                "type": "resolve_fortune_land_thief",
                "actor_player_id": 0,
                "source": "fortune",
                "payload": {},
            },
            {
                "action_id": "purchase-after-fortune",
                "type": "request_purchase_tile",
                "actor_player_id": 0,
                "source": "arrival",
                "payload": {"tile_index": 4},
            },
        ],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:dice",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "FortuneResolveModule"
    followup_frame = state.runtime_frame_stack[-1]
    assert followup_frame is not frame
    assert followup_frame.frame_type == "sequence"
    assert followup_frame.parent_frame_id == frame.frame_id
    assert followup_frame.created_by_module_id == frame.module_queue[0].module_id
    assert followup_frame.module_queue[0].module_type == "MapMoveModule"
    assert all(active.frame_type != "turn" for active in state.runtime_frame_stack)


def test_fortune_followup_actions_stay_in_sequence_module_chain() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.executed: list[str] = []
            self.logs: list[dict] = []

        def _execute_action(self, state, action, *, queue_followups: bool):
            self.executed.append(action.type)
            assert queue_followups is True
            if action.type == "resolve_fortune_land_thief":
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id="move-from-fortune",
                        type="apply_move",
                        actor_player_id=0,
                        source="fortune",
                        payload={"move_value": 3, "schedule_arrival": True},
                    )
                )
                return {"type": "QUEUED_FORTUNE_MOVE"}
            if action.type == "apply_move":
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id="arrival-from-fortune",
                        type="resolve_arrival",
                        actor_player_id=0,
                        source="fortune",
                        payload={"tile_index": 3},
                    )
                )
                return {"type": "MOVE_APPLIED"}
            if action.type == "resolve_arrival":
                return {"type": "ARRIVAL_RESOLVED"}
            raise AssertionError(f"unexpected action {action.type}")

        def _log(self, event):
            self.logs.append(dict(event))

    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [
            {
                "action_id": "fortune-1",
                "type": "resolve_fortune_land_thief",
                "actor_player_id": 0,
                "source": "fortune",
                "payload": {},
            }
        ],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    fortune = runner.advance_engine(engine, state)
    move = runner.advance_engine(engine, state)
    arrival = runner.advance_engine(engine, state)

    assert [fortune["module_type"], move["module_type"], arrival["module_type"]] == [
        "FortuneResolveModule",
        "MapMoveModule",
        "ArrivalTileModule",
    ]
    assert [fortune["module_boundary"], move["module_boundary"], arrival["module_boundary"]] == ["native", "native", "native"]
    assert engine.executed == ["resolve_fortune_land_thief", "apply_move", "resolve_arrival"]
    assert all(frame.frame_type == "sequence" for frame in state.runtime_frame_stack)


def test_all_fortune_decision_actions_can_chain_move_and_arrival_without_legacy_turn_restart() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.executed: list[str] = []

        def _execute_action(self, state, action, *, queue_followups: bool):
            self.executed.append(action.type)
            assert queue_followups is True
            if action.type.startswith("resolve_fortune_"):
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id=f"move-after-{action.type}",
                        type="apply_move",
                        actor_player_id=0,
                        source="fortune",
                        payload={"move_value": 2},
                    )
                )
                return {"type": "QUEUED_FORTUNE_MOVE"}
            if action.type == "apply_move":
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id="arrival-after-fortune",
                        type="resolve_arrival",
                        actor_player_id=0,
                        source="fortune",
                        payload={"tile_index": 2},
                    )
                )
                return {"type": "MOVE_APPLIED"}
            if action.type == "resolve_arrival":
                return {"type": "ARRIVAL_RESOLVED"}
            raise AssertionError(f"unexpected action {action.type}")

        def _log(self, _event):
            return None

    for fortune_action_type in FORTUNE_ACTION_TYPE_TO_MODULE_TYPE:
        frame = build_action_sequence_frame(
            1,
            0,
            0,
            [
                {
                    "action_id": fortune_action_type,
                    "type": fortune_action_type,
                    "actor_player_id": 0,
                    "source": "fortune",
                    "payload": {},
                }
            ],
            parent_frame_id="turn:1:p0",
            parent_module_id="mod:turn:1:p0:fortune",
            session_id="test-session",
        )
        state = SimpleNamespace(
            pending_actions=[],
            pending_turn_completion={},
            players=[SimpleNamespace(player_id=0, alive=True)],
            runtime_frame_stack=[frame],
            runtime_module_journal=[],
            rounds_completed=0,
            current_round_order=[0],
            turn_index=0,
        )
        engine = FakeEngine()
        runner = ModuleRunner()

        fortune = runner.advance_engine(engine, state)
        move = runner.advance_engine(engine, state)
        arrival = runner.advance_engine(engine, state)

        assert [fortune["module_type"], move["module_type"], arrival["module_type"]] == [
            "FortuneResolveModule",
            "MapMoveModule",
            "ArrivalTileModule",
        ]
        assert [fortune["module_boundary"], move["module_boundary"], arrival["module_boundary"]] == [
            "native",
            "native",
            "native",
        ]
        assert engine.executed == [fortune_action_type, "apply_move", "resolve_arrival"]
        assert all(active.frame_type == "sequence" for active in state.runtime_frame_stack)


def test_purchase_decision_and_commit_stay_in_native_purchase_modules() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.executed: list[str] = []

        def _execute_action(self, state, action, *, queue_followups: bool):
            self.executed.append(action.type)
            assert queue_followups is True
            if action.type == "request_purchase_tile":
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id="purchase-commit",
                        type="resolve_purchase_tile",
                        actor_player_id=0,
                        source="purchase_prompt",
                        payload={"tile_index": 7, "decision": "buy"},
                    )
                )
                return {"type": "PURCHASE_PROMPTED"}
            if action.type == "resolve_purchase_tile":
                return {"type": "PURCHASE_COMMITTED"}
            raise AssertionError(f"unexpected action {action.type}")

        def _log(self, _event):
            return None

    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [
            {
                "action_id": "purchase-decision",
                "type": "request_purchase_tile",
                "actor_player_id": 0,
                "source": "arrival",
                "payload": {"tile_index": 7},
            }
        ],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    decision = runner.advance_engine(engine, state)
    commit = runner.advance_engine(engine, state)

    assert [decision["module_type"], commit["module_type"]] == ["PurchaseDecisionModule", "PurchaseCommitModule"]
    assert [decision["module_boundary"], commit["module_boundary"]] == ["native", "native"]
    assert engine.executed == ["request_purchase_tile", "resolve_purchase_tile"]


def test_rent_payment_stays_in_native_rent_module_before_post_effects() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.executed: list[str] = []

        def _execute_action(self, state, action, *, queue_followups: bool):
            self.executed.append(action.type)
            assert queue_followups is True
            if action.type == "resolve_rent_payment":
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id="rent-post-effects",
                        type="resolve_landing_post_effects",
                        actor_player_id=0,
                        source="rent_post_landing",
                        payload={"tile_index": 7, "base_event": {"type": "RENT"}},
                    )
                )
                return {"type": "RENT"}
            if action.type == "resolve_landing_post_effects":
                return {"type": "RENT", "trick_same_tile_cash_gain": 2}
            raise AssertionError(f"unexpected action {action.type}")

        def _log(self, _event):
            return None

    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [
            {
                "action_id": "rent-payment",
                "type": "resolve_rent_payment",
                "actor_player_id": 0,
                "source": "landing_rent",
                "payload": {"tile_index": 7, "owner": 1},
            }
        ],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    rent = runner.advance_engine(engine, state)
    post_effects = runner.advance_engine(engine, state)

    assert [rent["module_type"], post_effects["module_type"]] == ["RentPaymentModule", "LandingPostEffectsModule"]
    assert [rent["module_boundary"], post_effects["module_boundary"]] == ["native", "native"]
    assert engine.executed == ["resolve_rent_payment", "resolve_landing_post_effects"]


def test_supply_threshold_action_cannot_be_wrapped_in_legacy_action_sequence() -> None:
    with pytest.raises(ValueError, match="resolve_supply_threshold.*SimultaneousResolutionFrame"):
        build_action_sequence_frame(
            1,
            0,
            0,
            [{"type": "resolve_supply_threshold", "actor_player_id": 0}],
            parent_frame_id="turn:1:p0",
            parent_module_id="mod:turn:1:p0:arrival",
            session_id="s1",
        )


def test_uncatalogued_action_module_checkpoint_cannot_be_resumed_silently() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

    frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trick",
        session_id="test-session",
    )
    frame.frame_id = "seq:action:1:p0:uncatalogued"
    frame.module_queue = [
        ModuleRef(
            module_id="mod:seq:action:1:p0:uncatalogued",
            module_type="UncataloguedActionModule",
            phase="sequence",
            owner_player_id=0,
            payload={"action": {"action_id": "uncatalogued", "type": "apply_move", "actor_player_id": 0}},
        )
    ]
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    with pytest.raises(ModuleRunnerError, match="action type apply_move belongs to MapMoveModule"):
        ModuleRunner().advance_engine(FakeEngine(), state)


def test_module_runner_rejects_action_payload_module_mismatch_before_execution() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _execute_action(self, *_args, **_kwargs):
            raise AssertionError("mismatched action payload must not reach engine action execution")

    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [{"action_id": "move-1", "type": "apply_move", "actor_player_id": 0, "source": "test"}],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:dice",
        session_id="test-session",
    )
    frame.module_queue[0].module_type = "ArrivalTileModule"
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    with pytest.raises(ModuleRunnerError, match="apply_move.*MapMoveModule.*ArrivalTileModule"):
        ModuleRunner().advance_engine(FakeEngine(), state)


def test_trick_choice_module_cannot_own_native_action_payload() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _use_trick_phase(self, *_args, **_kwargs):
            raise AssertionError("trick prompt must not open when module owns a native action payload")

        def _execute_action(self, *_args, **_kwargs):
            raise AssertionError("native action must not execute from a trick choice module")

    frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trick",
        session_id="test-session",
    )
    frame.module_queue[0].payload["action"] = {
        "action_id": "move-from-trick-choice",
        "type": "apply_move",
        "actor_player_id": 0,
        "source": "test",
    }
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True, trick_hand=[])],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    with pytest.raises(ModuleRunnerError, match="sequence module ownership.*apply_move.*MapMoveModule.*TrickChoiceModule"):
        ModuleRunner().advance_engine(FakeEngine(), state)


def test_continue_after_trick_phase_action_executes_and_attaches_turn_completion() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.executed: list[str] = []
            self.logs: list[dict] = []

        def _execute_action(self, state, action, *, queue_followups: bool):
            self.executed.append(action.type)
            assert queue_followups is True
            if action.type == "continue_after_trick_phase":
                state.pending_turn_completion = {
                    "player_id": 0,
                    "finisher_before": 2,
                    "disruption_before": {"leader_id": 1},
                }
                state.pending_actions.append(
                    ActionEnvelope(
                        action_id="move-after-trick",
                        type="apply_move",
                        actor_player_id=0,
                        source="continue_after_trick_phase",
                        payload={"move_value": 4},
                    )
                )
                return {"type": "CONTINUE_AFTER_TRICK_PHASE"}
            raise AssertionError(f"unexpected action {action.type}")

        def _log(self, event):
            self.logs.append(dict(event))

    turn_frame = build_turn_frame(1, 0, parent_module_id="mod:round:1:p0", session_id="test-session")
    turn_frame.status = "suspended"
    sequence_frame = build_action_sequence_frame(
        1,
        0,
        0,
        [
            {
                "action_id": "continue-after-trick",
                "type": "continue_after_trick_phase",
                "actor_player_id": 0,
                "source": "trick",
                "payload": {"hidden_trick_synced": True},
            }
        ],
        parent_frame_id=turn_frame.frame_id,
        parent_module_id="mod:turn:1:p0:trickwindow",
        session_id="test-session",
    )
    assert sequence_frame.module_queue[0].module_type == "TrickDeferredFollowupsModule"
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[turn_frame, sequence_frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "TrickDeferredFollowupsModule"
    assert result["action_type"] == "continue_after_trick_phase"
    assert result["module_boundary"] == "native"
    assert state.pending_turn_completion == {}
    turn_end_module = next(module for module in turn_frame.module_queue if module.module_type == "TurnEndSnapshotModule")
    assert turn_end_module.payload["turn_completion"] == {
        "player_id": 0,
        "finisher_before": 2,
        "disruption_before": {"leader_id": 1},
    }
    followup_sequence = state.runtime_frame_stack[-1]
    assert followup_sequence is not sequence_frame
    assert followup_sequence.module_queue[0].module_type == "MapMoveModule"


def test_pending_supply_threshold_action_is_promoted_to_resupply_frame_before_sequence_actions() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

    turn_frame = build_turn_frame(1, 0, parent_module_id="mod:round:1:playerturn", session_id="test-session")
    state = SimpleNamespace(
        pending_actions=[
            ActionEnvelope(
                action_id="supply-1",
                type="resolve_supply_threshold",
                actor_player_id=0,
                source="supply_threshold",
                payload={"threshold": 3, "participants": [0, 1]},
            ),
            ActionEnvelope(
                action_id="move-after-supply",
                type="apply_move",
                actor_player_id=0,
                source="fortune",
                payload={"move_value": 2},
            ),
        ],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True), SimpleNamespace(player_id=1, alive=True)],
        runtime_frame_stack=[turn_frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0, 1],
        turn_index=0,
    )

    ModuleRunner()._promote_pending_work_to_sequence_frames(FakeEngine(), state)

    assert state.pending_actions == []
    assert [frame.frame_type for frame in state.runtime_frame_stack] == ["turn", "simultaneous", "sequence"]
    resupply_module = next(
        module for module in state.runtime_frame_stack[1].module_queue if module.module_type == "ResupplyModule"
    )
    assert resupply_module.payload["action"]["action_id"] == "supply-1"
    assert state.runtime_frame_stack[2].module_queue[0].module_type == "MapMoveModule"


def test_pending_actions_already_owned_by_runtime_frames_are_not_promoted_again() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

    turn_frame = build_turn_frame(2, 0, parent_module_id="mod:round:2:playerturn", session_id="test-session")
    resupply_frame = build_resupply_frame(
        2,
        83,
        parent_frame_id=turn_frame.frame_id,
        parent_module_id="mod:turn:2:p0:trickwindow",
        session_id="test-session",
        participants=[0, 1],
    )
    resupply_module = next(module for module in resupply_frame.module_queue if module.module_type == "ResupplyModule")
    resupply_module.payload["action"] = {
        "action_id": "supply-1",
        "type": "resolve_supply_threshold",
        "actor_player_id": 0,
        "source": "trick_supply_threshold",
        "payload": {"threshold": 6},
    }
    sequence_frame = build_action_sequence_frame(
        2,
        0,
        84,
        [
            {
                "action_id": "continue-1",
                "type": "continue_after_trick_phase",
                "actor_player_id": 0,
                "source": "trick_supply_threshold",
                "payload": {},
            }
        ],
        parent_frame_id=turn_frame.frame_id,
        parent_module_id="mod:turn:2:p0:trickwindow",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[
            ActionEnvelope(
                action_id="supply-1",
                type="resolve_supply_threshold",
                actor_player_id=0,
                source="trick_supply_threshold",
                payload={"threshold": 6},
            ),
            ActionEnvelope(
                action_id="continue-1",
                type="continue_after_trick_phase",
                actor_player_id=0,
                source="trick_supply_threshold",
                payload={},
            ),
        ],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True), SimpleNamespace(player_id=1, alive=True)],
        runtime_frame_stack=[turn_frame, resupply_frame, sequence_frame],
        runtime_module_journal=[],
        rounds_completed=1,
        current_round_order=[0, 1],
        turn_index=0,
    )

    ModuleRunner()._promote_pending_work_to_sequence_frames(FakeEngine(), state)

    assert state.pending_actions == []
    assert [frame.frame_id for frame in state.runtime_frame_stack] == [
        turn_frame.frame_id,
        resupply_frame.frame_id,
        sequence_frame.frame_id,
    ]


def test_module_runner_promotes_pending_actions_before_execution() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.executed: list[str] = []
            self.logs: list[dict] = []

        def _run_next_action_transition(self, state):
            raise AssertionError("module runner must not consume pending_actions as the next-work owner")

        def _execute_action(self, state, action, *, queue_followups: bool):
            self.executed.append(action.action_id)
            assert queue_followups is True
            return {"type": "NOOP"}

        def _log(self, event):
            self.logs.append(dict(event))

    round_frame = build_round_frame(1, player_order=[0], completed_setup=True)
    player_module = next(module for module in round_frame.module_queue if module.module_type == "PlayerTurnModule")
    player_module.status = "suspended"
    state = SimpleNamespace(
        pending_actions=[
            ActionEnvelope(
                action_id="act-1",
                type="apply_move",
                actor_player_id=0,
                source="test",
                payload={"move_value": 1},
            )
        ],
        pending_turn_completion={},
        runtime_frame_stack=[round_frame],
        runtime_module_journal=[
            ModuleJournalEntry(
                module_id=module_id,
                frame_id=round_frame.frame_id,
                status="completed",
                idempotency_key=module_id,
            )
            for module_id in round_frame.completed_module_ids
        ],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    engine = FakeEngine()
    result = ModuleRunner().advance_engine(engine, state)

    assert result["module_type"] == "MapMoveModule"
    assert engine.executed == ["act-1"]
    assert result["pending_actions"] == 0
    assert state.pending_actions == []
    sequence_frames = [frame for frame in state.runtime_frame_stack if frame.frame_type == "sequence"]
    assert [frame.status for frame in sequence_frames] == ["completed"]
    assert sequence_frames[0].module_queue[0].module_type == "MapMoveModule"


def test_turn_completion_is_owned_by_turn_end_snapshot_module_not_sequence_adapter() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _finish_turn_after_trick_phase(self, state, player, *, finisher_before: int, disruption_before: dict):
            state.pending_actions.append(
                ActionEnvelope(
                    action_id="move-after-dice",
                    type="apply_move",
                    actor_player_id=0,
                    source="dice",
                    payload={"move_value": 1},
                )
            )
            state.pending_turn_completion = {
                "player_id": player.player_id,
                "finisher_before": finisher_before,
                "disruption_before": dict(disruption_before),
            }

    player = SimpleNamespace(
        player_id=0,
        alive=True,
        extra_dice_count_this_turn=0,
        trick_dice_delta_this_turn=0,
    )
    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    dice_module = next(module for module in turn_frame.module_queue if module.module_type == "DiceRollModule")
    for module in turn_frame.module_queue:
        if module.module_id == dice_module.module_id:
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    state = SimpleNamespace(
        current_weather_effects=[],
        pending_actions=[],
        pending_turn_completion={},
        players=[player],
        runtime_frame_stack=[turn_frame],
        runtime_module_journal=[],
        runtime_modifier_registry=ModifierRegistryState(),
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "DiceRollModule"
    assert state.pending_turn_completion == {}
    turn_end_module = next(module for module in turn_frame.module_queue if module.module_type == "TurnEndSnapshotModule")
    assert turn_end_module.payload["turn_completion"] == {
        "player_id": 0,
        "finisher_before": 0,
        "disruption_before": {},
    }
    sequence_frames = [frame for frame in state.runtime_frame_stack if frame.frame_type == "sequence"]
    assert [frame.module_queue[0].module_type for frame in sequence_frames] == ["MapMoveModule"]
    assert all(
        module.module_type != "TurnEndSnapshotModule"
        for frame in sequence_frames
        for module in frame.module_queue
    )


def test_module_runner_rejects_orphan_pending_turn_completion_checkpoint() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _leader_disruption_snapshot(self, *_args, **_kwargs):
            return {}

        def _maybe_award_control_finisher_window(self, *_args, **_kwargs):
            return False

        def _emit_vis(self, *_args, **_kwargs):
            return None

        def _check_end(self, *_args, **_kwargs):
            return False

    round_frame = build_round_frame(1, player_order=[0], completed_setup=True)
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={"player_id": 0, "disruption_before": {}, "finisher_before": 0},
        runtime_frame_stack=[round_frame],
        runtime_module_journal=[],
        players=[SimpleNamespace(player_id=0, alive=True, control_finisher_turns=0, control_finisher_reason="")],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    with pytest.raises(ModuleRunnerError, match="pending_turn_completion.*TurnEndSnapshotModule"):
        ModuleRunner().advance_engine(FakeEngine(), state)


def test_turn_end_snapshot_counts_completed_turn_before_end_rule() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _leader_disruption_snapshot(self, *_args, **_kwargs):
            return {}

        def _maybe_award_control_finisher_window(self, *_args, **_kwargs):
            return False

        def _emit_vis(self, *_args, **_kwargs):
            return None

        def _check_end(self, state):
            return state.turn_index >= 1

    state = GameState.create(GameConfig(player_count=1))
    state.current_round_order = [0]
    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    for module in turn_frame.module_queue:
        if module.module_type == "TurnEndSnapshotModule":
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    state.runtime_frame_stack = [turn_frame]

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["status"] == "completed"
    assert result["reason"] == "end_rule"
    assert state.turn_index == 1
    assert turn_frame.status == "completed"


def test_module_runner_has_no_direct_turn_body_boundary_after_cutover() -> None:
    source = Path("engine/runtime_modules/runner.py").read_text(encoding="utf-8")
    start = source.index("def _advance_player_turn_module")
    end = source.index("def _advance_turn_frame", start)
    player_turn_section = source[start:end]

    assert "engine._take_turn" not in player_turn_section
    assert "build_turn_completion_sequence_frame" not in player_turn_section
    assert "pending_turn_completion" not in player_turn_section


def test_trick_window_spawns_child_sequence_instead_of_replaying_turn_modules() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.vis_events: list[str] = []

        def _emit_vis(self, event_type, *_args, **_kwargs):
            self.vis_events.append(str(event_type))

        def _use_trick_phase(self, *_args, **_kwargs):
            raise AssertionError("TrickWindowModule must delegate to a TrickSequenceFrame")

    player = SimpleNamespace(
        alive=True,
        player_id=0,
        current_character="산적",
        position=0,
        trick_hand=[SimpleNamespace(name="잔꾀", deck_index=101)],
        public_trick_names=lambda: ["잔꾀"],
        hidden_trick_count=lambda: 0,
    )
    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    for module in turn_frame.module_queue:
        if module.module_type == "TrickWindowModule":
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    state = SimpleNamespace(
        current_weather_effects=[],
        pending_actions=[],
        pending_turn_completion={},
        players=[player],
        runtime_frame_stack=[turn_frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "TrickWindowModule"
    assert result["pending_modules"] == len(TRICK_SEQUENCE_MODULE_TYPES)
    trick_module = next(module for module in turn_frame.module_queue if module.module_type == "TrickWindowModule")
    assert trick_module.status == "suspended"
    assert trick_module.cursor == "child_trick_sequence"
    sequence_frame = state.runtime_frame_stack[-1]
    assert sequence_frame.frame_type == "sequence"
    assert sequence_frame.created_by_module_id == trick_module.module_id
    assert [module.module_type for module in sequence_frame.module_queue] == list(TRICK_SEQUENCE_MODULE_TYPES)


def test_completed_trick_sequence_resumes_turn_without_reopening_trick_window() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.vis_events: list[str] = []
            self.finish_calls = 0

        def _emit_vis(self, event_type, *_args, **_kwargs):
            self.vis_events.append(str(event_type))

        def _resolve_pending_marks(self, *_args, **_kwargs):
            raise AssertionError("completed pre-trick modules must not replay after trick sequence completion")

        def _apply_character_start(self, *_args, **_kwargs):
            raise AssertionError("character start must not replay after trick sequence completion")

        def _use_trick_phase(self, *_args, **_kwargs):
            raise AssertionError("trick choice must stay inside the completed TrickSequenceFrame")

        def _finish_turn_after_trick_phase(self, *_args, **_kwargs):
            self.finish_calls += 1

    player = SimpleNamespace(
        alive=True,
        player_id=0,
        current_character="산적",
        position=0,
        trick_hand=[SimpleNamespace(name="잔꾀", deck_index=101)],
        public_trick_names=lambda: ["잔꾀"],
        hidden_trick_count=lambda: 0,
    )
    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    trick_module = next(module for module in turn_frame.module_queue if module.module_type == "TrickWindowModule")
    for module in turn_frame.module_queue:
        if module.module_id == trick_module.module_id:
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    trick_module.status = "suspended"
    trick_module.cursor = "child_trick_sequence"
    trick_module.payload["window_opened"] = True
    turn_frame.status = "suspended"

    sequence_frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id=turn_frame.frame_id,
        parent_module_id=trick_module.module_id,
        session_id="test-session",
    )
    for module in sequence_frame.module_queue:
        module.status = "completed"
        sequence_frame.completed_module_ids.append(module.module_id)
    sequence_frame.status = "completed"
    trick_module.suspension_id = sequence_frame.frame_id

    state = SimpleNamespace(
        current_weather_effects=[],
        pending_actions=[],
        pending_turn_completion={},
        players=[player],
        runtime_frame_stack=[turn_frame, sequence_frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    resumed = runner.advance_engine(engine, state)
    rolled = runner.advance_engine(engine, state)

    assert resumed["module_type"] == "TrickWindowModule"
    assert trick_module.status == "completed"
    assert engine.vis_events == []
    assert rolled["module_type"] == "DiceRollModule"
    assert engine.finish_calls == 1


def test_character_start_suppression_consumes_modifier_without_legacy_character_start() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.logs: list[dict] = []
            self.vis_events: list[str] = []

        def _log(self, event):
            self.logs.append(dict(event))

        def _emit_vis(self, event_type, *_args, **_kwargs):
            self.vis_events.append(str(event_type))

        def _apply_character_start(self, *_args, **_kwargs):
            raise AssertionError("CharacterStartModule must consume suppress modifiers before ability flow")

    player = SimpleNamespace(
        alive=True,
        player_id=0,
        current_character="산적",
        attribute="무뢰",
        extra_dice_count_this_turn=0,
    )
    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    character_module = next(module for module in turn_frame.module_queue if module.module_type == "CharacterStartModule")
    for module in turn_frame.module_queue:
        if module.module_id == character_module.module_id:
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    modifier = Modifier(
        modifier_id="modifier:test:eosa:suppress:p0",
        source_module_id="mod:round:1:eosa",
        target_module_type="CharacterStartModule",
        scope="single_use",
        owner_player_id=0,
        priority=0,
        payload={"kind": MUROE_SKILL_SUPPRESSION_KIND, "reason": MUROE_SKILL_SUPPRESSION_REASON},
        propagation=["TargetJudicatorModule"],
        expires_on="turn_completed",
    )
    state = SimpleNamespace(
        current_weather_effects=[],
        pending_actions=[],
        pending_turn_completion={},
        players=[player],
        runtime_frame_stack=[turn_frame],
        runtime_module_journal=[],
        runtime_modifier_registry=ModifierRegistryState(modifiers=[modifier]),
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "CharacterStartModule"
    assert result["suppressed"] is True
    assert character_module.status == "completed"
    assert modifier.consumed is True


def test_trick_choice_continues_to_resolve_module_inside_same_sequence() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _use_trick_phase(self, *_args, **_kwargs):
            return False

    player = SimpleNamespace(player_id=0, alive=True, trick_hand=[], current_character="산적")
    frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trickwindow",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[player],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "TrickChoiceModule"
    assert frame.status == "running"
    assert frame.module_queue[0].status == "completed"
    assert frame.module_queue[2].module_type == "TrickResolveModule"
    assert frame.module_queue[2].status == "queued"


def test_trick_visibility_prompt_suspends_visibility_module_without_replaying_choice() -> None:
    class HiddenPromptRaised(RuntimeError):
        pass

    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self._suppress_hidden_trick_selection = False
            self.trick_choice_calls = 0
            self.suppressed_visibility_calls = 0
            self.unsuppressed_visibility_calls = 0

        def _use_trick_phase(self, state, player, **_kwargs):
            self.trick_choice_calls += 1
            state.runtime_last_trick_sequence_result = {
                "phase": "regular",
                "selected_trick": "test trick",
                "resolution": {"type": "NOOP"},
                "deferred_followups": False,
            }
            self._sync_trick_visibility(state, player)
            return False

        def _sync_trick_visibility(self, _state, player):
            if self._suppress_hidden_trick_selection:
                self.suppressed_visibility_calls += 1
                return
            self.unsuppressed_visibility_calls += 1
            if self.unsuppressed_visibility_calls == 1:
                raise HiddenPromptRaised("hidden trick selection prompt")
            player.hidden_trick_deck_index = player.trick_hand[0].deck_index

    player = SimpleNamespace(
        player_id=0,
        alive=True,
        trick_hand=[SimpleNamespace(deck_index=11, name="test trick")],
        hidden_trick_deck_index=None,
        current_character="산적",
    )
    frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trickwindow",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[player],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    choice = runner.advance_engine(engine, state)

    assert choice["module_type"] == "TrickChoiceModule"
    assert engine.trick_choice_calls == 1
    assert engine.suppressed_visibility_calls == 1

    with pytest.raises(HiddenPromptRaised):
        for _ in range(8):
            runner.advance_engine(engine, state)

    visibility_module = next(module for module in frame.module_queue if module.module_type == "TrickVisibilitySyncModule")
    assert frame.active_module_id == visibility_module.module_id
    assert visibility_module.status == "suspended"
    assert engine.trick_choice_calls == 1

    resumed = runner.advance_engine(engine, state)

    assert resumed["module_type"] == "TrickVisibilitySyncModule"
    assert player.hidden_trick_deck_index == 11
    assert engine.trick_choice_calls == 1


def test_trick_resolve_followup_schedules_next_choice_in_same_sequence() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

    frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trickwindow",
        session_id="test-session",
    )
    for module in frame.module_queue[:2]:
        module.status = "completed"
        frame.completed_module_ids.append(module.module_id)
    resolve_module = frame.module_queue[2]
    resolve_module.payload["followup_trick_prompt"] = True
    resolve_module.payload["turn_context"] = {"origin": "trick"}
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "TrickResolveModule"
    followup = frame.module_queue[3]
    assert followup.module_type == "TrickChoiceModule"
    assert followup.status == "queued"
    assert followup.payload["turn_context"] == {"origin": "trick"}
    assert {
        "CharacterStartModule",
        "PendingMarkResolutionModule",
        "TargetJudicatorModule",
        "TrickWindowModule",
    }.isdisjoint({module.module_type for module in frame.module_queue})


def test_trick_resolve_followup_insertion_is_idempotent_on_module_retry() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

    frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:trickwindow",
        session_id="test-session",
    )
    for module in frame.module_queue[:2]:
        module.status = "completed"
        frame.completed_module_ids.append(module.module_id)
    resolve_module = frame.module_queue[2]
    resolve_module.status = "running"
    resolve_module.payload["followup_trick_prompt"] = True
    resolve_module.payload["turn_context"] = {"origin": "retry_after_insert"}
    already_inserted = ModuleRef(
        module_id=f"{resolve_module.module_id}:followup_choice:1",
        module_type="TrickChoiceModule",
        phase="trickchoice",
        owner_player_id=0,
        payload={"turn_context": {"origin": "retry_after_insert"}},
        idempotency_key=f"{resolve_module.idempotency_key}:followup_choice:1",
    )
    resolve_index = frame.module_queue.index(resolve_module)
    frame.module_queue.insert(resolve_index + 1, already_inserted)
    resolve_module.payload["followup_choice_module_id"] = already_inserted.module_id
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True)],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "TrickResolveModule"
    followups = [
        module
        for module in frame.module_queue
        if module.module_type == "TrickChoiceModule" and module.module_id.startswith(f"{resolve_module.module_id}:followup_choice")
    ]
    assert [module.module_id for module in followups] == [already_inserted.module_id]


def test_trick_followup_runs_inside_child_sequence_before_turn_dice() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.trick_choice_calls = 0

        def _use_trick_phase(self, *_args, **_kwargs):
            self.trick_choice_calls += 1
            return False

        def _finish_turn_after_trick_phase(self, *_args, **_kwargs):
            raise AssertionError("turn dice must wait until the trick sequence frame is drained")

    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    trick_module = next(module for module in turn_frame.module_queue if module.module_type == "TrickWindowModule")
    dice_module = next(module for module in turn_frame.module_queue if module.module_type == "DiceRollModule")
    for module in turn_frame.module_queue:
        if module.module_id == trick_module.module_id:
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    trick_module.status = "suspended"
    trick_module.cursor = "child_trick_sequence"
    turn_frame.status = "suspended"

    sequence_frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id=turn_frame.frame_id,
        parent_module_id=trick_module.module_id,
        session_id="test-session",
    )
    for module in sequence_frame.module_queue[:2]:
        module.status = "completed"
        sequence_frame.completed_module_ids.append(module.module_id)
    resolve_module = sequence_frame.module_queue[2]
    resolve_module.payload["followup_trick_prompt"] = True
    resolve_module.payload["turn_context"] = {"origin": "first_trick"}
    trick_module.suspension_id = sequence_frame.frame_id

    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True, trick_hand=[], current_character="산적")],
        runtime_frame_stack=[turn_frame, sequence_frame],
        runtime_module_journal=[],
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    resolved = runner.advance_engine(engine, state)
    followup = runner.advance_engine(engine, state)

    assert resolved["module_type"] == "TrickResolveModule"
    assert followup["module_type"] == "TrickChoiceModule"
    assert engine.trick_choice_calls == 1
    assert trick_module.status == "suspended"
    assert dice_module.status == "queued"
    assert sequence_frame.status == "running"


def test_bandit_mark_then_trick_followup_never_replays_target_or_trick_window() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def __init__(self) -> None:
            self.trick_choice_calls = 0
            self.finish_calls = 0

        def _emit_vis(self, *_args, **_kwargs):
            raise AssertionError("completed TrickWindowModule must not reopen visual prompt")

        def _resolve_pending_marks(self, *_args, **_kwargs):
            raise AssertionError("pending mark resolution must not replay after trick followup")

        def _apply_character_start(self, *_args, **_kwargs):
            raise AssertionError("character start must not replay after trick followup")

        def _adjudicate_character_mark(self, *_args, **_kwargs):
            raise AssertionError("target adjudicator must not replay after trick followup")

        def _use_trick_phase(self, *_args, **_kwargs):
            self.trick_choice_calls += 1
            return False

        def _finish_turn_after_trick_phase(self, *_args, **_kwargs):
            self.finish_calls += 1

    turn_frame = build_turn_frame(
        1,
        0,
        parent_module_id="mod:round:1:playerturn:p0",
        session_id="test-session",
    )
    trick_module = next(module for module in turn_frame.module_queue if module.module_type == "TrickWindowModule")
    for module in turn_frame.module_queue:
        if module.module_id == trick_module.module_id:
            break
        module.status = "completed"
        turn_frame.completed_module_ids.append(module.module_id)
    trick_module.status = "suspended"
    trick_module.cursor = "child_trick_sequence"
    trick_module.payload["window_opened"] = True
    turn_frame.status = "suspended"

    sequence_frame = build_trick_sequence_frame(
        1,
        0,
        0,
        parent_frame_id=turn_frame.frame_id,
        parent_module_id=trick_module.module_id,
        session_id="test-session",
    )
    for module in sequence_frame.module_queue[:2]:
        module.status = "completed"
        sequence_frame.completed_module_ids.append(module.module_id)
    resolve_module = sequence_frame.module_queue[2]
    resolve_module.payload["followup_trick_prompt"] = True
    resolve_module.payload["turn_context"] = {"after": "bandit_mark"}
    trick_module.suspension_id = sequence_frame.frame_id

    state = SimpleNamespace(
        current_weather_effects=[],
        pending_actions=[],
        pending_turn_completion={},
        players=[SimpleNamespace(player_id=0, alive=True, trick_hand=[], current_character="산적")],
        runtime_frame_stack=[turn_frame, sequence_frame],
        runtime_module_journal=[],
        runtime_modifier_registry=ModifierRegistryState(),
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )
    engine = FakeEngine()
    runner = ModuleRunner()

    module_types = [runner.advance_engine(engine, state)["module_type"] for _ in range(7)]

    assert module_types == [
        "TrickResolveModule",
        "TrickChoiceModule",
        "TrickDiscardModule",
        "TrickDeferredFollowupsModule",
        "TrickVisibilitySyncModule",
        "DiceRollModule",
        "MovementResolveModule",
    ]
    assert engine.trick_choice_calls == 1
    assert engine.finish_calls == 1
    assert len([frame for frame in state.runtime_frame_stack if frame.frame_type == "sequence"]) == 1


def test_sequence_module_receives_applicable_modifiers_before_execution() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _execute_action(self, _state, action, *, queue_followups: bool):
            assert action.action_id == "move-1"
            assert queue_followups is True
            return {"type": "NOOP"}

        def _log(self, _event):
            return None

    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [
            {
                "action_id": "move-1",
                "type": "apply_move",
                "actor_player_id": 0,
                "source": "test",
                "payload": {"move_value": 2},
            }
        ],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:fortune",
        session_id="test-session",
    )
    state = SimpleNamespace(
        pending_actions=[],
        pending_turn_completion={},
        players=[],
        runtime_frame_stack=[frame],
        runtime_module_journal=[],
        runtime_modifier_registry=ModifierRegistryState(
            modifiers=[
                Modifier(
                    modifier_id="modifier:test:map",
                    source_module_id="mod:source",
                    target_module_type="MapMoveModule",
                    scope="turn",
                    owner_player_id=0,
                    priority=10,
                    payload={"kind": "test_move_modifier"},
                )
            ]
        ),
        rounds_completed=0,
        current_round_order=[0],
        turn_index=0,
    )

    result = ModuleRunner().advance_engine(FakeEngine(), state)

    assert result["module_type"] == "MapMoveModule"
    assert frame.module_queue[0].modifiers == ["modifier:test:map"]
