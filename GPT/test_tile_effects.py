from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from ai_policy import HeuristicPolicy
from config import CellKind, GameConfig
from engine import GameEngine
from state import GameState
from tile_effects import build_purchase_context


def test_purchase_context_applies_trick_free_purchase_modifier() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.trick_free_purchase_this_turn = True

    context = build_purchase_context(state, player, tile_index, state.board[tile_index], source="landing_purchase")

    assert context.base_cost > 0
    assert context.final_cost == 0
    assert context.one_shot_consumptions == ["trick_free_purchase_this_turn"]
    assert context.cost_breakdown[-1]["modifier"] == "free_purchase_once"


def test_purchase_context_builder_free_purchase_does_not_consume_one_shot_flag() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.current_character = "건설업자"
    player.trick_free_purchase_this_turn = True

    context = build_purchase_context(state, player, tile_index, state.board[tile_index], source="landing_purchase")

    assert context.final_cost == 0
    assert context.one_shot_consumptions == []
    assert context.cost_breakdown[-1]["modifier"] == "builder_free_purchase"


def test_successful_trick_free_purchase_consumes_flag_once() -> None:
    class YesDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_purchase_tile":
                return True
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=YesDecisionPort())
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.trick_free_purchase_this_turn = True
    cash_before = player.cash

    result = engine._resolve_purchase_tile_decision(state, player, tile_index, state.board[tile_index], source="landing_purchase")

    assert result["type"] == "PURCHASE"
    assert result["cost"] == 0
    assert result["base_cost"] > 0
    assert result["purchase_context"]["one_shot_consumptions"] == ["trick_free_purchase_this_turn"]
    assert player.cash == cash_before
    assert player.trick_free_purchase_this_turn is False


def test_skipped_trick_free_purchase_preserves_flag() -> None:
    class NoDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_purchase_tile":
                return False
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=NoDecisionPort())
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.trick_free_purchase_this_turn = True

    result = engine._resolve_purchase_tile_decision(state, player, tile_index, state.board[tile_index], source="landing_purchase")

    assert result["type"] == "PURCHASE_SKIP_POLICY"
    assert result["cost"] == 0
    assert player.trick_free_purchase_this_turn is True
    assert state.tile_owner[tile_index] is None
