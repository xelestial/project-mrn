from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from config import GameConfig
    from state import GameState, PlayerState


@dataclass(slots=True)
class TokenRules:
    starting_hand_coins: int = 0
    lap_reward_coins: int = 3
    max_coins_per_tile: int = 3
    max_place_per_visit: int = 3
    can_place_on_first_purchase: bool = True
    max_place_on_purchase: int = 1
    transfer_coins_on_takeover: bool = True
    coins_from_visiting_own_tile: int = 1

    def can_place_on_purchase(self, state: 'GameState', player: 'PlayerState', pos: int) -> bool:
        return self.can_place_on_first_purchase and player.hand_coins > 0 and state.tile_owner[pos] == player.player_id

    def place_limit_on_purchase(self, state: 'GameState', player: 'PlayerState', pos: int) -> int:
        return self.max_place_on_purchase

    def tile_capacity(self, state: 'GameState', pos: int) -> int:
        return self.max_coins_per_tile


@dataclass(slots=True)
class LapRewardRules:
    cash: int = 5
    coins: int = 3
    shards: int = 3
    points_budget: int = 10
    cash_point_cost: int = 2
    shards_point_cost: int = 3
    coins_point_cost: int = 3
    cash_pool: int = 30
    shards_pool: int = 18
    coins_pool: int = 18


@dataclass(slots=True)
class StartRewardRules:
    points_budget: int = 20
    cash_point_cost: int = 2
    shards_point_cost: int = 3
    coins_point_cost: int = 3
    cash_pool: int = 30
    shards_pool: int = 18
    coins_pool: int = 18


@dataclass(slots=True)
class TakeoverRules:
    blocked_by_monopoly: bool = True
    transfer_tile_coins: bool = True

    def is_takeover_blocked(self, engine, state: 'GameState', pos: int, new_owner: Optional[int]) -> bool:
        prev_owner = state.tile_owner[pos]
        if prev_owner is None or new_owner is None or prev_owner == new_owner:
            return False
        if self.blocked_by_monopoly:
            return engine._is_monopoly_tile(state, pos)
        return False


@dataclass(slots=True)
class ForceSaleRules:
    refund_purchase_cost: bool = True
    return_tile_coins_to_original_owner: bool = True
    block_repurchase_until_next_turn: bool = True


@dataclass(slots=True)
class EndConditionRules:
    f_threshold: Optional[float] = 15.0
    monopolies_to_trigger_end: int = 3
    tiles_to_trigger_end: Optional[int] = 9
    alive_players_at_most: int = 2
    max_rounds: Optional[int] = None
    max_turns: Optional[int] = None

    def evaluate_end_reason(self, engine, state: 'GameState') -> str | None:
        if self.f_threshold is not None and state.f_value >= self.f_threshold:
            return 'F_THRESHOLD'
        if self.monopolies_to_trigger_end and any(
            p.alive and engine._count_monopolies_owned(state, p.player_id) >= self.monopolies_to_trigger_end
            for p in state.players
        ):
            return 'THREE_MONOPOLIES'
        if self.tiles_to_trigger_end is not None and any(
            p.alive and p.tiles_owned >= self.tiles_to_trigger_end for p in state.players
        ):
            return 'NINE_TILES'
        effective_alive_threshold = min(
            int(self.alive_players_at_most),
            max(1, int(getattr(state.config, "player_count", len(state.players))) - 1),
        )
        if state.alive_count() <= effective_alive_threshold:
            return 'ALIVE_THRESHOLD'
        if self.max_rounds is not None and state.rounds_completed >= self.max_rounds:
            return 'MAX_ROUNDS'
        if self.max_turns is not None and state.turn_index >= self.max_turns:
            return 'MAX_TURNS'
        return None


@dataclass(slots=True)
class EconomyRules:
    starting_cash: int = 20
    land_profiles: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        'HIGH': (5, 5),
        'MID': (4, 4),
        'LOW': (3, 3),
    })

    def _cost_pair_for(self, state: 'GameState', pos: int) -> Tuple[int, int]:
        tile = state.tile_at(pos)
        if tile.purchase_cost is not None and tile.rent_cost is not None:
            return tile.purchase_cost, tile.rent_cost
        if tile.economy_profile:
            try:
                return self.land_profiles[tile.economy_profile]
            except KeyError as exc:
                raise KeyError(f"Unknown economy profile {tile.economy_profile!r} for tile {pos}") from exc
        raise ValueError(f'tile {pos} has no purchase/rent cost metadata or economy profile')

    def purchase_cost_for(self, state: 'GameState', pos: int) -> int:
        return self._cost_pair_for(state, pos)[0]

    def rent_cost_for(self, state: 'GameState', pos: int) -> int:
        return self._cost_pair_for(state, pos)[1]


@dataclass(slots=True)
class ResourceRules:
    starting_shards: int = 2


@dataclass(slots=True)
class DiceRules:
    enabled: bool = True
    values: Tuple[int, ...] = (1, 2, 3, 4, 5, 6)
    one_shot: bool = True
    max_cards_per_turn: int = 2
    use_one_card_plus_one_die: bool = True


@dataclass(slots=True)
class SpecialTileRules:
    s_display_name: str = '운수'
    f1_increment: float = 1.0
    f2_increment: float = 2.0
    f1_shards: int = 1
    f2_shards: int = 2
    malicious_land_multiplier: int = 3
    s_cash_plus1_probability: float = 0.50
    s_cash_plus2_probability: float = 0.25
    s_cash_minus1_probability: float = 0.25

    def malicious_cost_for(self, state: 'GameState', pos: int) -> int:
        return state.config.rules.economy.purchase_cost_for(state, pos) * self.malicious_land_multiplier


@dataclass(slots=True)
class GameRules:
    token: TokenRules = field(default_factory=TokenRules)
    lap_reward: LapRewardRules = field(default_factory=LapRewardRules)
    start_reward: StartRewardRules = field(default_factory=StartRewardRules)
    takeover: TakeoverRules = field(default_factory=TakeoverRules)
    force_sale: ForceSaleRules = field(default_factory=ForceSaleRules)
    end: EndConditionRules = field(default_factory=EndConditionRules)
    economy: EconomyRules = field(default_factory=EconomyRules)
    resources: ResourceRules = field(default_factory=ResourceRules)
    dice: DiceRules = field(default_factory=DiceRules)
    special_tiles: SpecialTileRules = field(default_factory=SpecialTileRules)

    def sync_from_config_mirrors(self, config: 'GameConfig') -> None:
        self.token.starting_hand_coins = config.coins.starting_hand_coins
        self.token.lap_reward_coins = config.coins.lap_reward_coins
        self.token.coins_from_visiting_own_tile = config.coins.coins_from_visiting_own_tile
        self.lap_reward.coins = config.coins.lap_reward_coins
        self.token.max_coins_per_tile = config.coins.max_coins_per_tile
        self.token.max_place_per_visit = config.coins.max_place_per_visit
        self.token.can_place_on_first_purchase = config.coins.can_place_on_first_purchase
        self.lap_reward.cash = config.coins.lap_reward_cash
        self.lap_reward.coins = config.coins.lap_reward_coins
        self.lap_reward.shards = config.shards.lap_reward_shards
        self.economy.starting_cash = config.economy.starting_cash
        self.economy.land_profiles = {name: (rule.purchase_cost, rule.rent_cost) for name, rule in config.economy.tile_profile_costs.items()}
        self.resources.starting_shards = config.shards.starting_shards
        self.dice.enabled = config.dice_cards.enabled
        self.dice.values = tuple(config.dice_cards.values)
        self.dice.one_shot = config.dice_cards.one_shot
        self.dice.max_cards_per_turn = config.dice_cards.max_cards_per_turn
        self.dice.use_one_card_plus_one_die = config.dice_cards.use_one_card_plus_one_die
        self.special_tiles.s_display_name = config.board.special_tile_s_display_name
        self.special_tiles.f1_increment = config.board.f1_increment
        self.special_tiles.f2_increment = config.board.f2_increment
        self.special_tiles.f1_shards = config.board.f1_shards
        self.special_tiles.f2_shards = config.board.f2_shards
        self.special_tiles.malicious_land_multiplier = config.board.malicious_land_multiplier
        self.special_tiles.s_cash_plus1_probability = config.board.s_cash_plus1_probability
        self.special_tiles.s_cash_plus2_probability = config.board.s_cash_plus2_probability
        self.special_tiles.s_cash_minus1_probability = config.board.s_cash_minus1_probability
        self.end.f_threshold = config.board.f_end_value
        self.end.monopolies_to_trigger_end = config.end.monopolies_to_trigger_end
        self.end.tiles_to_trigger_end = config.end.higher_tiles_to_trigger_end
        self.end.alive_players_at_most = config.end.end_when_alive_players_at_most
        self.end.max_rounds = config.end.max_rounds
        self.end.max_turns = config.end.max_turns

    def sync_to_config_mirrors(self, config: 'GameConfig') -> None:
        config.coins.starting_hand_coins = self.token.starting_hand_coins
        config.coins.lap_reward_coins = self.lap_reward.coins
        config.coins.coins_from_visiting_own_tile = self.token.coins_from_visiting_own_tile
        self.token.lap_reward_coins = self.lap_reward.coins
        config.coins.max_coins_per_tile = self.token.max_coins_per_tile
        config.coins.max_place_per_visit = self.token.max_place_per_visit
        config.coins.can_place_on_first_purchase = self.token.can_place_on_first_purchase
        config.coins.lap_reward_cash = self.lap_reward.cash
        config.shards.lap_reward_shards = self.lap_reward.shards
        config.economy.starting_cash = self.economy.starting_cash
        from config import TileRule
        config.economy.tile_profile_costs = {name: TileRule(purchase_cost=pair[0], rent_cost=pair[1]) for name, pair in self.economy.land_profiles.items()}
        config.shards.starting_shards = self.resources.starting_shards
        config.dice_cards.enabled = self.dice.enabled
        config.dice_cards.values = tuple(self.dice.values)
        config.dice_cards.one_shot = self.dice.one_shot
        config.dice_cards.max_cards_per_turn = self.dice.max_cards_per_turn
        config.dice_cards.use_one_card_plus_one_die = self.dice.use_one_card_plus_one_die
        config.board.special_tile_s_display_name = self.special_tiles.s_display_name
        config.board.f1_increment = self.special_tiles.f1_increment
        config.board.f2_increment = self.special_tiles.f2_increment
        config.board.f1_shards = self.special_tiles.f1_shards
        config.board.f2_shards = self.special_tiles.f2_shards
        config.board.malicious_land_multiplier = self.special_tiles.malicious_land_multiplier
        config.board.s_cash_plus1_probability = self.special_tiles.s_cash_plus1_probability
        config.board.s_cash_plus2_probability = self.special_tiles.s_cash_plus2_probability
        config.board.s_cash_minus1_probability = self.special_tiles.s_cash_minus1_probability
        if self.end.f_threshold is not None:
            config.board.f_end_value = self.end.f_threshold
        config.end.monopolies_to_trigger_end = self.end.monopolies_to_trigger_end
        config.end.higher_tiles_to_trigger_end = self.end.tiles_to_trigger_end
        config.end.end_when_alive_players_at_most = self.end.alive_players_at_most
        config.end.max_rounds = self.end.max_rounds
        config.end.max_turns = self.end.max_turns
