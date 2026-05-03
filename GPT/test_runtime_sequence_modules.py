from __future__ import annotations

from types import SimpleNamespace

from state import ActionEnvelope
from runtime_modules.contracts import Modifier, ModifierRegistryState, ModuleJournalEntry
from runtime_modules.round_modules import build_round_frame
from runtime_modules.runner import ModuleRunner
from runtime_modules.sequence_modules import (
    ACTION_TYPE_TO_MODULE_TYPE,
    TRICK_SEQUENCE_MODULE_TYPES,
    build_action_sequence_frame,
    build_roll_and_arrive_sequence_frame,
    build_trick_sequence_frame,
    module_type_for_action,
)
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
                "type": "resolve_fortune_bonus_roll",
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
        "FortuneResolveModule",
    ]
    assert frame.module_queue[0].payload["action"]["action_id"] == "a1"


def test_fortune_resolve_has_explicit_sequence_handler_not_payload_fallback() -> None:
    from runtime_modules.handlers.sequence import SEQUENCE_FRAME_HANDLERS

    assert "FortuneResolveModule" in SEQUENCE_FRAME_HANDLERS


def test_fortune_action_types_are_never_legacy_or_turn_modules() -> None:
    fortune_action_types = [
        "resolve_fortune_bonus_roll",
        "resolve_fortune_land_thief",
        "resolve_fortune_purchase_discount",
        "resolve_fortune_move_to_marker",
    ]

    assert {module_type_for_action(action_type) for action_type in fortune_action_types} == {"FortuneResolveModule"}


def test_fortune_followup_is_parented_under_current_sequence_module() -> None:
    class FakeEngine:
        _vis_session_id = "test-session"

        def _execute_action(self, state, action, *, queue_followups: bool):
            assert action.type == "resolve_fortune_bonus_roll"
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
                "type": "resolve_fortune_bonus_roll",
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
            if action.type == "resolve_fortune_bonus_roll":
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
                "type": "resolve_fortune_bonus_roll",
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
    assert engine.executed == ["resolve_fortune_bonus_roll", "apply_move", "resolve_arrival"]
    assert all(frame.frame_type == "sequence" for frame in state.runtime_frame_stack)


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


def test_supply_threshold_action_is_not_built_as_action_sequence_module() -> None:
    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [{"type": "resolve_supply_threshold", "actor_player_id": 0}],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="s1",
    )

    assert all(module.module_type != "ResupplyModule" for module in frame.module_queue)
    assert frame.module_queue[0].module_type == "LegacyActionAdapterModule"


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
        pending_turn_completion={"player_id": 0, "disruption_before": {}, "finisher_before": 0},
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
    assert [frame.status for frame in sequence_frames] == ["running", "completed"]
    assert sequence_frames[0].module_queue[0].module_type == "TurnEndSnapshotModule"


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
