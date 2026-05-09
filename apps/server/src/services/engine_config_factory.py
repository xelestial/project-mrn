from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


class EngineConfigFactory:
    """Build runtime GameConfig from resolved session parameters."""

    def create(self, resolved_parameters: dict[str, Any]):
        cfg = self._load_default_config()
        runtime = dict(resolved_parameters.get("runtime", {}))
        seats = dict(resolved_parameters.get("seats", {}))
        dice = dict(resolved_parameters.get("dice", {}))
        economy = dict(resolved_parameters.get("economy", {}))
        resources = dict(resolved_parameters.get("resources", {}))
        rules = dict(resolved_parameters.get("rules", {}))

        player_count = int(runtime.get("player_count", seats.get("max", cfg.player_count)))
        cfg.player_count = player_count

        dice_values = dice.get("values")
        if isinstance(dice_values, list) and dice_values:
            cfg.dice_cards.values = tuple(int(v) for v in dice_values)
        dice_max = dice.get("max_cards_per_turn")
        if isinstance(dice_max, int):
            cfg.dice_cards.max_cards_per_turn = int(dice_max)

        start_cash = economy.get("starting_cash")
        if isinstance(start_cash, int):
            cfg.economy.starting_cash = int(start_cash)
        start_shards = resources.get("starting_shards")
        if isinstance(start_shards, int):
            cfg.shards.starting_shards = int(start_shards)

        end = rules.get("end")
        if isinstance(end, dict) and cfg.rules is not None:
            cfg.rules.end.f_threshold = end.get("f_threshold")
            cfg.rules.end.monopolies_to_trigger_end = int(
                end.get("monopolies_to_trigger_end", cfg.rules.end.monopolies_to_trigger_end)
            )
            cfg.rules.end.tiles_to_trigger_end = end.get("tiles_to_trigger_end")
            cfg.rules.end.alive_players_at_most = int(
                end.get("alive_players_at_most", cfg.rules.end.alive_players_at_most)
            )
            max_rounds = end.get("max_rounds", runtime.get("max_rounds", cfg.rules.end.max_rounds))
            cfg.rules.end.max_rounds = None if max_rounds is None else int(max_rounds)
            max_turns = end.get("max_turns", runtime.get("max_turns", cfg.rules.end.max_turns))
            cfg.rules.end.max_turns = None if max_turns is None else int(max_turns)
            cfg.rules.sync_to_config_mirrors(cfg)
        elif cfg.rules is not None and (
            runtime.get("max_rounds") is not None or runtime.get("max_turns") is not None
        ):
            if runtime.get("max_rounds") is not None:
                cfg.rules.end.max_rounds = int(runtime["max_rounds"])
            if runtime.get("max_turns") is not None:
                cfg.rules.end.max_turns = int(runtime["max_turns"])
            cfg.rules.sync_to_config_mirrors(cfg)

        return cfg

    @staticmethod
    def _load_default_config():
        root = Path(__file__).resolve().parents[4]
        engine_dir = root / "engine"
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        from config import DEFAULT_CONFIG

        return copy.deepcopy(DEFAULT_CONFIG)
