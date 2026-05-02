from __future__ import annotations

from types import SimpleNamespace

from state import ActionEnvelope
from runtime_modules.contracts import ModuleJournalEntry
from runtime_modules.round_modules import build_round_frame
from runtime_modules.runner import ModuleRunner
from runtime_modules.sequence_modules import (
    ACTION_TYPE_TO_MODULE_TYPE,
    TRICK_SEQUENCE_MODULE_TYPES,
    build_action_sequence_frame,
    build_roll_and_arrive_sequence_frame,
    build_trick_sequence_frame,
)


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
