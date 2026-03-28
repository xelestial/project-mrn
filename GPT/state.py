from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set

from characters import CHARACTERS
from config import CellKind, GameConfig, TileMetadata
from fortune_cards import FortuneCard, build_fortune_deck
from trick_cards import TrickCard, build_trick_deck
from weather_cards import WeatherCard, build_weather_deck


@dataclass(slots=True)
class TileState:
    index: int
    kind: CellKind
    block_id: int
    zone_color: Optional[str]
    purchase_cost: Optional[int]
    rent_cost: Optional[int]
    economy_profile: Optional[str] = None
    owner_id: Optional[int] = None
    score_coins: int = 0

    @property
    def is_land(self) -> bool:
        return self.kind in (CellKind.T2, CellKind.T3)

    @property
    def cumulative_score(self) -> int:
        return self.score_coins

    @classmethod
    def from_metadata(cls, metadata: TileMetadata, config: GameConfig | None = None) -> "TileState":
        purchase_cost = metadata.purchase_cost
        rent_cost = metadata.rent_cost
        if config is not None and metadata.is_land and metadata.economy_profile and (purchase_cost is None or rent_cost is None):
            pair = config.rules.economy.land_profiles[metadata.economy_profile]
            purchase_cost = pair[0]
            rent_cost = pair[1]
        return cls(
            index=metadata.index,
            kind=metadata.kind,
            block_id=metadata.block_id,
            zone_color=metadata.zone_color,
            purchase_cost=purchase_cost,
            rent_cost=rent_cost,
            economy_profile=metadata.economy_profile,
        )


class TileAttrView(Sequence):
    __slots__ = ("_tiles", "_getter", "_setter")

    def __init__(self, tiles: List[TileState], getter: Callable[[TileState], object], setter: Callable[[TileState, object], None] | None = None):
        self._tiles = tiles
        self._getter = getter
        self._setter = setter

    def __getitem__(self, key):
        if isinstance(key, slice):
            return [self._getter(tile) for tile in self._tiles[key]]
        return self._getter(self._tiles[key])

    def __setitem__(self, key, value) -> None:
        if self._setter is None:
            raise TypeError("This tile view is read-only")
        if isinstance(key, slice):
            indices = range(*key.indices(len(self._tiles)))
            values = list(value)
            if len(values) != len(list(indices)):
                raise ValueError("Slice assignment size mismatch")
            for idx, item in zip(indices, values):
                self._setter(self._tiles[idx], item)
            return
        self._setter(self._tiles[key], value)

    def __len__(self) -> int:
        return len(self._tiles)

    def __iter__(self) -> Iterator[object]:
        for tile in self._tiles:
            yield self._getter(tile)

    def __repr__(self) -> str:
        return repr(list(self))


@dataclass(slots=True)
class PlayerState:
    player_id: int
    position: int
    cash: int
    team_id: Optional[int] = None
    alive: bool = True
    hand_coins: int = 0
    shards: int = 0
    tiles_owned: int = 0
    score_coins_placed: int = 0
    total_steps: int = 0
    turns_taken: int = 0
    first_purchase_turn_by_tile: dict[int, int] = field(default_factory=dict)
    visited_owned_tile_indices: Set[int] = field(default_factory=set)
    used_dice_cards: Set[int] = field(default_factory=set)
    current_character: str = ""
    skipped_turn: bool = False
    immune_to_marks_this_round: bool = False
    free_purchase_this_turn: bool = False
    extra_dice_count_this_turn: int = 0
    block_start_reward_this_turn: bool = False
    pending_marks: List[dict] = field(default_factory=list)
    drafted_cards: List[int] = field(default_factory=list)
    revealed_this_round: bool = False
    trick_hand: List[TrickCard] = field(default_factory=list)
    hidden_trick_deck_index: Optional[int] = None
    extra_shard_gain_this_turn: int = 0
    rent_waiver_count_this_turn: int = 0
    trick_all_rent_waiver_this_turn: bool = False
    trick_free_purchase_this_turn: bool = False
    trick_dice_delta_this_turn: int = 0
    rolled_dice_count_this_turn: int = 0
    trick_personal_rent_half_this_turn: bool = False
    trick_same_tile_cash2_this_turn: bool = False
    trick_same_tile_shard_rake_this_turn: bool = False
    trick_one_extra_adjacent_buy_this_turn: bool = False
    trick_encounter_boost_this_turn: bool = False
    trick_force_sale_landing_this_turn: bool = False
    trick_zone_chain_this_turn: bool = False
    control_finisher_turns: int = 0
    control_finisher_reason: str = ""

    @property
    def attribute(self) -> str:
        return CHARACTERS[self.current_character].attribute if self.current_character else ""

    def public_trick_cards(self) -> List[TrickCard]:
        if not self.trick_hand:
            return []
        return [c for c in self.trick_hand if c.deck_index != self.hidden_trick_deck_index]

    def public_trick_names(self) -> List[str]:
        return [c.name for c in self.public_trick_cards()]

    def hidden_trick_count(self) -> int:
        return 1 if self.trick_hand else 0


@dataclass(slots=True)
class GameState:
    config: GameConfig
    tiles: List[TileState]
    board: TileAttrView
    block_ids: TileAttrView
    tile_owner: TileAttrView
    tile_coins: TileAttrView
    block_color_map: Dict[int, str]
    f_value: float = 0.0
    turn_index: int = 0
    rounds_completed: int = 0
    current_round_order: List[int] = field(default_factory=list)
    bankrupt_players: int = 0
    malicious_tiles: int = 0
    winner_ids: List[int] = field(default_factory=list)
    end_reason: str = ""
    players: List[PlayerState] = field(default_factory=list)
    marker_owner_id: int = 0
    active_by_card: Dict[int, str] = field(default_factory=dict)
    pending_marker_flip_owner_id: Optional[int] = None
    fortune_draw_pile: List[FortuneCard] = field(default_factory=list)
    fortune_discard_pile: List[FortuneCard] = field(default_factory=list)
    trick_draw_pile: List[TrickCard] = field(default_factory=list)
    trick_discard_pile: List[TrickCard] = field(default_factory=list)
    weather_draw_pile: List[WeatherCard] = field(default_factory=list)
    weather_discard_pile: List[WeatherCard] = field(default_factory=list)
    current_weather: WeatherCard | None = None
    current_weather_effects: Set[str] = field(default_factory=set)
    next_supply_f_threshold: int = 3
    global_rent_half_this_turn: bool = False
    global_rent_double_this_turn: bool = False
    global_rent_double_permanent: bool = False
    tile_rent_modifiers_this_turn: Dict[int, int] = field(default_factory=dict)
    tile_purchase_blocked_turn_index: Dict[int, int] = field(default_factory=dict)
    lap_reward_cash_pool_remaining: int = 60
    lap_reward_shards_pool_remaining: int = 40
    lap_reward_coins_pool_remaining: int = 18

    @classmethod
    def create(cls, config: GameConfig) -> "GameState":
        tiles = [TileState.from_metadata(metadata, config) for metadata in config.board.build_tile_metadata()]
        players = [
            PlayerState(
                player_id=i,
                position=config.initial_position_index,
                cash=config.rules.economy.starting_cash,
                hand_coins=config.rules.token.starting_hand_coins,
                shards=config.rules.resources.starting_shards,
            )
            for i in range(config.player_count)
        ]
        return cls(
            config=config,
            tiles=tiles,
            board=TileAttrView(tiles, lambda tile: tile.kind, lambda tile, value: setattr(tile, "kind", value)),
            block_ids=TileAttrView(tiles, lambda tile: tile.block_id),
            tile_owner=TileAttrView(tiles, lambda tile: tile.owner_id, lambda tile, value: setattr(tile, "owner_id", value)),
            tile_coins=TileAttrView(tiles, lambda tile: tile.score_coins, lambda tile, value: setattr(tile, "score_coins", value)),
            block_color_map=config.board.build_block_color_map(),
            current_round_order=list(range(config.player_count)),
            players=players,
            marker_owner_id=0,
            active_by_card=dict(config.characters.starting_active_by_card),
            fortune_draw_pile=build_fortune_deck(config.fortune_csv_path),
            trick_draw_pile=build_trick_deck(config.trick_csv_path),
            weather_draw_pile=build_weather_deck(config.weather_csv_path),
            lap_reward_cash_pool_remaining=config.rules.lap_reward.cash_pool,
            lap_reward_shards_pool_remaining=config.rules.lap_reward.shards_pool,
            lap_reward_coins_pool_remaining=config.rules.lap_reward.coins_pool,
        )

    def alive_player_ids(self) -> List[int]:
        return [p.player_id for p in self.players if p.alive]

    def alive_count(self) -> int:
        return sum(1 for p in self.players if p.alive)

    def total_score(self, player_id: int) -> int:
        p = self.players[player_id]
        return p.tiles_owned + p.score_coins_placed

    def tile_at(self, index: int) -> TileState:
        return self.tiles[index]

    def tile_positions(self, *, kinds: Iterable[CellKind] | None = None, land_only: bool = False, block_id: int | None = None, owner_id: int | None | object = ... , zone_color: str | None = None) -> List[int]:
        kind_set = set(kinds) if kinds is not None else None
        positions: List[int] = []
        for tile in self.tiles:
            if land_only and not tile.is_land:
                continue
            if kind_set is not None and tile.kind not in kind_set:
                continue
            if block_id is not None and tile.block_id != block_id:
                continue
            if owner_id is not ... and tile.owner_id != owner_id:
                continue
            if zone_color is not None and tile.zone_color != zone_color:
                continue
            positions.append(tile.index)
        return positions

    def first_tile_position(self, *, kinds: Iterable[CellKind] | None = None, land_only: bool = False, block_id: int | None = None, owner_id: int | None | object = ... , zone_color: str | None = None) -> int:
        positions = self.tile_positions(kinds=kinds, land_only=land_only, block_id=block_id, owner_id=owner_id, zone_color=zone_color)
        if not positions:
            raise LookupError("No tile matched the requested metadata filters")
        return positions[0]

    def block_tile_positions(self, block_id: int, *, land_only: bool = False) -> List[int]:
        return self.tile_positions(land_only=land_only, block_id=block_id)

    def adjacent_land_positions(self, pos: int) -> List[int]:
        block_id = self.tiles[pos].block_id
        if block_id < 0:
            return []
        return [idx for idx in self.block_tile_positions(block_id, land_only=True) if idx != pos]
