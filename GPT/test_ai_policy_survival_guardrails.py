from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from config import GameConfig
from state import GameState, CellKind
from ai_policy import HeuristicPolicy
from fortune_cards import FortuneCard
from trick_cards import TrickCard


def _make_state() -> GameState:
    return GameState.create(GameConfig())


def test_generic_survival_context_exposes_cleanup_downside_fields():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 12
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "가벼운 짐", ""),
    ]
    state.fortune_draw_pile = [
        FortuneCard(1, "산불 발생", ""),
        FortuneCard(2, "화재 발생", ""),
        FortuneCard(3, "길이 열리다", ""),
    ]
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
    ctx = policy._generic_survival_context(state, player, player.current_character)
    assert ctx["own_burdens"] == 2.0
    assert ctx["downside_expected_cleanup_cost"] > 0.0
    assert ctx["worst_cleanup_cost"] >= ctx["downside_expected_cleanup_cost"]


def test_choose_purchase_tile_blocked_by_cleanup_hard_guard():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 14
    player.position = 0
    player.visited_owned_tile_indices = [2, 4]
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
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
    assert policy.choose_purchase_tile(state, player, pos, CellKind.T2, 4, source="landing") is False


class _ForcedScorePolicy(HeuristicPolicy):
    def _is_v2_mode(self):
        return True

    def _character_score_breakdown_v2(self, state, player, active_name):
        base = 5000.0 if active_name in {"중매꾼", "건설업자", "사기꾼"} else 0.0
        return base, [f"forced_base={base:.1f}"]


def _make_growth_block_state() -> GameState:
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 14
    player.position = 0
    player.visited_owned_tile_indices = [2, 4]
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
    state.active_by_card[1] = "중매꾼"
    state.active_by_card[2] = "객주"
    state.active_by_card[3] = "자객"
    return state


def test_choose_final_character_excludes_survival_hard_blocked_growth_when_safe_option_exists():
    state = _make_growth_block_state()
    player = state.players[0]
    policy = _ForcedScorePolicy(character_policy_mode="heuristic_v2_balanced")
    choice = policy.choose_final_character(state, player, [1, 2])
    assert choice == "객주"


def test_choose_draft_card_excludes_survival_hard_blocked_growth_when_safe_option_exists():
    state = _make_growth_block_state()
    player = state.players[0]
    policy = _ForcedScorePolicy(character_policy_mode="heuristic_v2_balanced")
    choice = policy.choose_draft_card(state, player, [1, 2])
    assert choice == 2
