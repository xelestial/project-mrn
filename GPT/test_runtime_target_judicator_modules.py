from __future__ import annotations

from types import SimpleNamespace

from runtime_modules.contracts import Modifier, ModifierRegistryState
from runtime_modules.handlers.turn import handle_target_judicator
from runtime_modules.modifiers import MUROE_SKILL_SUPPRESSION_KIND, MUROE_SKILL_SUPPRESSION_REASON, ModifierRegistry
from runtime_modules.runner import ModuleRunner
from runtime_modules.turn_modules import build_turn_frame


class _FakeEngine:
    def __init__(self) -> None:
        self.adjudications = 0

    def _adjudicate_character_mark(self, state, player):  # noqa: ANN001
        del state, player
        self.adjudications += 1
        return {
            "mode": "immediate",
            "effect_type": "assassin_reveal",
            "target_character": "산적",
            "target_player_id": 1,
            "decision": {"choice_id": "p2"},
        }


def _turn_context() -> tuple[SimpleNamespace, object, object]:
    state = SimpleNamespace(
        rounds_completed=0,
        players=[
            SimpleNamespace(player_id=0, alive=True, current_character="자객"),
            SimpleNamespace(player_id=1, alive=True, current_character="산적"),
        ],
        runtime_modifier_registry=ModifierRegistryState(),
        runtime_module_journal=[],
    )
    frame = build_turn_frame(1, 0, parent_module_id="round:1:p0")
    module = next(item for item in frame.module_queue if item.module_type == "TargetJudicatorModule")
    return state, frame, module


def test_target_judicator_inserts_immediate_marker_transfer_module() -> None:
    from runtime_modules.handlers.turn import TurnFrameHandlerContext

    state, frame, module = _turn_context()
    engine = _FakeEngine()

    result = handle_target_judicator(
        TurnFrameHandlerContext(
            runner=ModuleRunner(),
            engine=engine,
            state=state,
            frame=frame,
            module=module,
            player_id=0,
            player=state.players[0],
        )
    )

    assert result["module_type"] == "TargetJudicatorModule"
    assert engine.adjudications == 1
    inserted_index = frame.module_queue.index(module) + 1
    inserted = frame.module_queue[inserted_index]
    assert inserted.module_type == "ImmediateMarkerTransferModule"
    assert inserted.payload["effect_type"] == "assassin_reveal"
    assert inserted.payload["target_player_id"] == 1


def test_target_judicator_suppression_modifier_blocks_adjudication() -> None:
    from runtime_modules.handlers.turn import TurnFrameHandlerContext

    state, frame, module = _turn_context()
    registry = ModifierRegistry(state.runtime_modifier_registry)
    registry.add(
        Modifier(
            modifier_id="modifier:test:eosa:suppress:0",
            source_module_id="CharacterModifierSeedModule",
            target_module_type="CharacterStartModule",
            scope="round",
            owner_player_id=0,
            priority=0,
            payload={
                "kind": MUROE_SKILL_SUPPRESSION_KIND,
                "reason": MUROE_SKILL_SUPPRESSION_REASON,
            },
            propagation=["TargetJudicatorModule"],
            expires_on="round_completed",
        )
    )
    engine = _FakeEngine()

    result = handle_target_judicator(
        TurnFrameHandlerContext(
            runner=ModuleRunner(),
            engine=engine,
            state=state,
            frame=frame,
            module=module,
            player_id=0,
            player=state.players[0],
        )
    )

    assert result["suppressed"] is True
    assert engine.adjudications == 0
    assert [item.module_type for item in frame.module_queue].count("ImmediateMarkerTransferModule") == 0
