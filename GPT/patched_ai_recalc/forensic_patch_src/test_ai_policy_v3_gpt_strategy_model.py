from ai_policy import HeuristicPolicy
from config import GameConfig
from state import GameState, CellKind
from trick_cards import TrickCard


def _make_state() -> GameState:
    return GameState.create(GameConfig())


def test_v3_gpt_values_baksu_shard_checkpoint_over_generic_cash_role():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 10
    player.shards = 4
    player.trick_hand = [TrickCard(1, "무거운 짐", "")]
    state.active_by_card[1] = "박수"
    state.active_by_card[2] = "객주"
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt")
    choice = policy.choose_final_character(state, player, [1, 2])
    assert choice == "박수"


def test_v3_gpt_prefers_shards_for_baksu_before_five_shards():
    state = _make_state()
    player = state.players[0]
    player.current_character = "박수"
    player.cash = 12
    player.shards = 4
    player.hand_coins = 1
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt", lap_policy_mode="heuristic_v3_gpt")
    decision = policy.choose_lap_reward(state, player)
    assert decision.choice == "shards"


def test_v3_gpt_allows_safe_low_cost_t3_for_online_baksu():
    state = _make_state()
    player = state.players[0]
    player.current_character = "박수"
    player.cash = 12
    player.shards = 5
    player.position = 0
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "가벼운 짐", ""),
    ]
    pos = 6
    state.board[pos] = CellKind.T3
    state.tile_owner[pos] = None
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt")
    assert policy.choose_purchase_tile(state, player, pos, CellKind.T3, 2, source="landing") is True
