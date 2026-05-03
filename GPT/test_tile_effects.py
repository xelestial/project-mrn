from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from ai_policy import HeuristicPolicy
from config import CellKind, GameConfig
from engine import GameEngine
from runtime_modules.contracts import Modifier
from runtime_modules.modifiers import BUILDER_FREE_PURCHASE_KIND, ModifierRegistry
from state import GameState
from tile_effects import (
    build_purchase_context,
    build_rent_context,
    build_score_token_placement_context,
    consume_rent_one_shots,
)


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


def test_module_purchase_context_uses_builder_modifier_without_character_name() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    state.runtime_runner_kind = "module"
    player = state.players[0]
    player.current_character = "어사"
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    ModifierRegistry(state.runtime_modifier_registry).add(
        Modifier(
            modifier_id="modifier:test:builder:free_purchase",
            source_module_id="CharacterStartModule:test",
            target_module_type="PurchaseDecisionModule",
            scope="turn",
            owner_player_id=player.player_id,
            priority=10,
            payload={"kind": BUILDER_FREE_PURCHASE_KIND},
            propagation=["PurchaseCommitModule", "ArrivalTileModule"],
            expires_on="turn_completed",
        )
    )

    context = build_purchase_context(state, player, tile_index, state.board[tile_index], source="landing_purchase")

    assert context.base_cost > 0
    assert context.final_cost == 0
    assert context.one_shot_consumptions == []
    assert context.cost_breakdown[-1]["modifier"] == "builder_free_purchase"


def test_module_purchase_context_does_not_use_builder_name_without_modifier() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    state.runtime_runner_kind = "module"
    player = state.players[0]
    player.current_character = "건설업자"
    tile_index = state.first_tile_position(kinds=[CellKind.T2])

    context = build_purchase_context(state, player, tile_index, state.board[tile_index], source="landing_purchase")

    assert context.base_cost > 0
    assert context.final_cost == context.base_cost
    assert all(item["modifier"] != "builder_free_purchase" for item in context.cost_breakdown)


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


def test_rent_context_applies_weather_and_waiver_breakdown() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    payer = state.players[0]
    owner = state.players[1]
    tile_index = 1
    state.tile_owner[tile_index] = owner.player_id
    state.current_weather_effects = {"검은 달"}
    payer.rent_waiver_count_this_turn = 1

    context = build_rent_context(state, payer, tile_index, owner.player_id)

    assert context.base_rent > 0
    assert context.final_rent == 0
    assert [item["modifier"] for item in context.rent_breakdown] == [
        "base_rent_cost",
        "color_weather_rent_double",
        "rent_waiver_count_this_turn",
    ]
    assert context.one_shot_consumptions == ["rent_waiver_count_this_turn"]

    consume_rent_one_shots(payer, context.one_shot_consumptions)

    assert payer.rent_waiver_count_this_turn == 0


def test_rent_context_can_exclude_normal_rent_waivers_for_non_rent_costs() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    payer = state.players[0]
    owner = state.players[1]
    tile_index = state.first_tile_position(kinds=[CellKind.T3])
    payer.trick_all_rent_waiver_this_turn = True
    payer.rent_waiver_count_this_turn = 1

    context = build_rent_context(state, payer, tile_index, owner.player_id, include_waivers=False)

    assert context.final_rent == context.base_rent
    assert context.one_shot_consumptions == []


def test_score_token_placement_context_limits_by_hand_room_and_rule_limit() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.hand_coins = 5
    state.tile_coins[tile_index] = 2

    context = build_score_token_placement_context(state, player, tile_index, max_place=3, source="purchase")

    assert context.can_place is True
    assert context.amount == min(5, context.tile_capacity - 2, 3)
    assert context.to_payload()["source"] == "purchase"
    assert context.to_payload()["tile_tokens_before"] == 2


def test_score_token_placement_context_reports_blocked_reason() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.hand_coins = 0

    context = build_score_token_placement_context(state, player, tile_index)

    assert context.can_place is False
    assert context.amount == 0
    assert context.blocked_reason == "no_hand_tokens"
