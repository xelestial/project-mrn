from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from config import GameConfig
from state import GameState


def test_runtime_player_spawn_matches_injected_ruleset_defaults():
    cfg = GameConfig()
    state = GameState.create(cfg)
    assert cfg.economy.starting_cash == cfg.rules.economy.starting_cash
    assert cfg.coins.starting_hand_coins == cfg.rules.token.starting_hand_coins
    assert cfg.shards.starting_shards == cfg.rules.resources.starting_shards
    assert cfg.coins.lap_reward_cash == cfg.rules.lap_reward.cash
    assert cfg.coins.lap_reward_coins == cfg.rules.lap_reward.coins
    assert cfg.shards.lap_reward_shards == cfg.rules.lap_reward.shards
    assert cfg.board.f_end_value == cfg.rules.end.f_threshold
    assert cfg.end.monopolies_to_trigger_end == cfg.rules.end.monopolies_to_trigger_end
    assert cfg.end.higher_tiles_to_trigger_end == cfg.rules.end.tiles_to_trigger_end
    assert cfg.end.end_when_alive_players_at_most == cfg.rules.end.alive_players_at_most
    assert cfg.end.max_rounds == cfg.rules.end.max_rounds
    assert cfg.end.max_turns == cfg.rules.end.max_turns
    for player in state.players:
        assert player.cash == cfg.rules.economy.starting_cash
        assert player.hand_coins == cfg.rules.token.starting_hand_coins
        assert player.shards == cfg.rules.resources.starting_shards
