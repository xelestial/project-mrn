from config import GameConfig
from state import GameState
from ai_policy import HeuristicPolicy
from fortune_cards import FortuneCard
from trick_cards import TrickCard


def _make_state() -> GameState:
    return GameState.create(GameConfig())


def test_cleanup_deck_profile_includes_positive_cleanup_cards_in_net_expectation():
    state = _make_state()
    state.fortune_draw_pile = [
        FortuneCard(1, "자원 재활용", ""),
        FortuneCard(2, "모두의 재활용", ""),
        FortuneCard(3, "화재 발생", ""),
        FortuneCard(4, "산불 발생", ""),
    ]
    state.fortune_discard_pile = []
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
    profile = policy._fortune_cleanup_deck_profile(state)
    assert profile["remaining_positive_cleanup_cards"] == 2.0
    assert profile["remaining_negative_cleanup_cards"] == 2.0
    assert profile["expected_cleanup_multiplier"] == 0.25
    assert profile["expected_negative_cleanup_multiplier"] == 0.75


def test_choose_burden_exchange_on_supply_respects_cleanup_reserve_floor():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 10
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "가벼운 짐", ""),
    ]
    state.fortune_draw_pile = [
        FortuneCard(1, "산불 발생", ""),
        FortuneCard(2, "화재 발생", ""),
        FortuneCard(3, "길이 열리다", ""),
    ]
    card = TrickCard(99, "교환 테스트", "")
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
    assert policy.choose_burden_exchange_on_supply(state, player, card) is False


def test_common_token_place_bonus_applies_outside_token_opt_profile():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.hand_coins = 2
    player.position = 0
    # make tile 2 owned by player and placeable
    state.tile_owner[2] = player.player_id
    state.tile_coins[2] = 0
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
    bonus = policy._common_token_place_bonus(state, player, 2, revisit_gap=3)
    assert bonus > 0.0
