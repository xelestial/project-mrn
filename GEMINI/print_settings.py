from __future__ import annotations

from config import DEFAULT_CONFIG
from doc_integrity import summarize_integrity

def main() -> None:
    cfg = DEFAULT_CONFIG
    print("=== Current Simulator Settings ===")
    print(f"version={__import__("metadata").GAME_VERSION}")
    print(f"players={cfg.player_count}")
    print(f"starting_cash={cfg.economy.starting_cash}")
    print(f"starting_hand_coins={cfg.coins.starting_hand_coins}")
    print(f"starting_shards={cfg.shards.starting_shards}")
    print(f"lap_reward_cash={cfg.coins.lap_reward_cash}")
    print(f"lap_reward_coins={cfg.coins.lap_reward_coins}")
    print(f"lap_reward_shards={cfg.shards.lap_reward_shards}")
    print(f"f_end_value={cfg.board.f_end_value}")
    print(f"randomize_starting_active_by_card={cfg.characters.randomize_starting_active_by_card}")
    print(f"side_land_purchase_costs={[rule.purchase_cost for rule in cfg.board.side_land_tile_rules or ()]}")
    print(f"side_land_rent_costs={[rule.rent_cost for rule in cfg.board.side_land_tile_rules or ()]}")
    print(f"malicious_land_multiplier={cfg.board.malicious_land_multiplier}")
    if cfg.board.side_land_tile_rules:
        print(f"side_land_malicious_costs={[rule.purchase_cost * cfg.board.malicious_land_multiplier for rule in cfg.board.side_land_tile_rules]}")
    print(f"tiles_to_trigger_end={cfg.end.tiles_to_trigger_end}")
    print(f"monopolies_to_trigger_end={cfg.end.monopolies_to_trigger_end}")
    print(f"higher_tiles_to_trigger_end={cfg.end.higher_tiles_to_trigger_end}")
    print(f"alive_players_end_threshold={cfg.end.end_when_alive_players_at_most}")
    integrity = summarize_integrity()
    print(f"doc_integrity_ok={integrity['ok']}")
    print(f"checked_pairs={integrity['checked_pairs']}")

if __name__ == "__main__":
    main()
