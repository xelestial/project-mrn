from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from ai_policy import HeuristicPolicy
from config import GameConfig
from fortune_cards import FortuneCard
from state import CellKind, GameState
from trick_cards import TrickCard


def _make_state() -> GameState:
    return GameState.create(GameConfig())


def test_v3_gpt_prefers_cash_lap_reward_under_cleanup_pressure():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 7
    player.shards = 4
    player.hand_coins = 2
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "무거운 짐", ""),
    ]
    state.fortune_draw_pile = [
        FortuneCard(1, "산불 발생", ""),
        FortuneCard(2, "화재 발생", ""),
        FortuneCard(3, "길이 열리다", ""),
    ]
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt", lap_policy_mode="heuristic_v3_gpt")
    decision = policy.choose_lap_reward(state, player)
    assert decision.choice == "cash"


def test_v3_gpt_blocks_noncritical_buy_earlier_when_cleanup_risk_is_live():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 13
    player.position = 0
    player.hand_coins = 2
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "무거운 짐", ""),
        TrickCard(3, "가벼운 짐", ""),
    ]
    state.fortune_draw_pile = [
        FortuneCard(1, "산불 발생", ""),
        FortuneCard(2, "화재 발생", ""),
        FortuneCard(3, "길이 열리다", ""),
    ]
    pos = 6
    state.board[pos] = CellKind.T2
    state.tile_owner[pos] = None
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt")
    assert policy.choose_purchase_tile(state, player, pos, CellKind.T2, 4, source="landing") is False
