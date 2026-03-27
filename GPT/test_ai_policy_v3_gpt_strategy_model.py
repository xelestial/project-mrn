from ai_policy import HeuristicPolicy
from config import GameConfig
from state import GameState, CellKind
from fortune_cards import FortuneCard
from trick_cards import TrickCard


def _make_state() -> GameState:
    return GameState.create(GameConfig())


def test_v3_gpt_no_longer_forces_baksu_before_five_shards_without_window():
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
    assert choice == "객주"


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


def test_v3_gpt_prefers_coins_after_generic_shard_threshold():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 14
    player.shards = 6
    player.hand_coins = 0
    player.visited_owned_tile_indices = [6]
    state.tile_owner[6] = player.player_id
    state.board[6] = CellKind.T3
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt", lap_policy_mode="heuristic_v3_gpt")
    decision = policy.choose_lap_reward(state, player)
    assert decision.choice == "coins"


def test_v3_gpt_allows_safe_growth_t2_buy_when_not_under_pressure():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 15
    player.shards = 5
    player.position = 0
    pos = 4
    state.board[pos] = CellKind.T2
    state.tile_owner[pos] = None
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt")
    assert policy.choose_purchase_tile(state, player, pos, CellKind.T2, 2, source="landing") is True


def test_v3_gpt_prefers_controller_over_precheckpoint_baksu_when_cash_starved():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 5
    player.shards = 3
    player.trick_hand = [TrickCard(1, "무거운 짐", "")]
    state.active_by_card[5] = "교리 연구관"
    state.active_by_card[6] = "박수"
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt")
    choice = policy.choose_final_character(state, player, [5, 6])
    assert choice == "교리 연구관"


def test_v3_gpt_prefers_shards_over_coins_when_cleanup_is_building():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 10
    player.shards = 4
    player.hand_coins = 0
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "가벼운 짐", ""),
    ]
    player.visited_owned_tile_indices = [6]
    state.board[6] = CellKind.T3
    state.tile_owner[6] = player.player_id
    state.fortune_draw_pile = [
        FortuneCard(1, "산불 발생", ""),
        FortuneCard(2, "화재 발생", ""),
        FortuneCard(3, "길이 열리다", ""),
    ]
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt", lap_policy_mode="heuristic_v3_gpt")
    decision = policy.choose_lap_reward(state, player)
    assert decision.choice in {"cash", "shards"}


def test_v3_gpt_prefers_cash_over_coins_when_cleanup_and_cash_are_critical():
    state = _make_state()
    player = state.players[0]
    player.current_character = "객주"
    player.cash = 4
    player.shards = 6
    player.hand_coins = 0
    player.trick_hand = [
        TrickCard(1, "무거운 짐", ""),
        TrickCard(2, "가벼운 짐", ""),
    ]
    player.visited_owned_tile_indices = [6]
    state.board[6] = CellKind.T3
    state.tile_owner[6] = player.player_id
    state.fortune_draw_pile = [
        FortuneCard(1, "산불 발생", ""),
        FortuneCard(2, "화재 발생", ""),
        FortuneCard(3, "길이 열리다", ""),
    ]
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt", lap_policy_mode="heuristic_v3_gpt")
    decision = policy.choose_lap_reward(state, player)
    assert decision.choice == "cash"


def test_v3_gpt_flips_leader_gakju_when_public_lap_engine_is_live():
    state = _make_state()
    player = state.players[0]
    player.current_character = "교리 감독관"
    leader = state.players[1]
    leader.current_character = "객주"
    leader.tiles_owned = 7
    leader.cash = 18
    leader.position = 0
    leader.trick_hand = [
        TrickCard(1, "과속", ""),
        TrickCard(2, "도움 닫기", ""),
        TrickCard(3, "이럇!", ""),
    ]
    state.active_by_card[7] = "객주"
    state.active_by_card[1] = "어사"
    policy = HeuristicPolicy(character_policy_mode="heuristic_v3_gpt")
    choice = policy.choose_active_flip_card(state, player, [1, 7])
    assert choice == 7
