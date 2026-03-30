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

        return cfg

    @staticmethod
    def _load_default_config():
        root = Path(__file__).resolve().parents[4]
        gpt_dir = root / "GPT"
        if str(gpt_dir) not in sys.path:
            sys.path.insert(0, str(gpt_dir))
        from config import DEFAULT_CONFIG

        return copy.deepcopy(DEFAULT_CONFIG)
