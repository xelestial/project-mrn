from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Iterable, List, Optional, Tuple

from characters import STARTING_ACTIVE_BY_CARD
from weather_cards import WEATHER_ZONE_COLORS
from game_rules import GameRules
from game_rules_loader import load_ruleset


class CellKind(IntEnum):
    F1 = 1
    F2 = 2
    S = 3
    T2 = 4
    T3 = 5
    MALICIOUS = 6


@dataclass(slots=True, frozen=True)
class TileRule:
    purchase_cost: int
    rent_cost: int


@dataclass(slots=True, frozen=True)
class TileMetadata:
    index: int
    kind: CellKind
    block_id: int
    zone_color: Optional[str]
    purchase_cost: Optional[int]
    rent_cost: Optional[int]
    economy_profile: Optional[str] = None

    @property
    def is_land(self) -> bool:
        return self.kind in (CellKind.T2, CellKind.T3)


@dataclass(slots=True, frozen=True)
class BoardLayoutMetadata:
    special_tile_s_display_name: str = "운수"
    f_end_value: float = 15.0
    f1_increment: float = 1.0
    f2_increment: float = 2.0
    f1_shards: int = 1
    f2_shards: int = 2
    malicious_land_multiplier: int = 3
    s_cash_plus1_probability: float = 0.50
    s_cash_plus2_probability: float = 0.25
    s_cash_minus1_probability: float = 0.25
    zone_colors: Tuple[str, ...] = WEATHER_ZONE_COLORS

    @classmethod
    def from_external_dict(cls, raw: dict | None) -> "BoardLayoutMetadata":
        raw = dict(raw or {})
        special_tiles = dict(raw.get("special_tiles") or {})
        f1 = dict(special_tiles.get("F1") or {})
        f2 = dict(special_tiles.get("F2") or {})
        s = dict(special_tiles.get("S") or {})
        malicious = dict(special_tiles.get("MALICIOUS") or {})
        zone_colors = tuple(raw.get("zone_colors", cls().zone_colors))
        return cls(
            special_tile_s_display_name=raw.get("special_tile_s_display_name", s.get("display_name", "운수")),
            f_end_value=float(raw.get("f_end_value", 15.0)),
            f1_increment=float(raw.get("f1_increment", f1.get("f_delta", 1.0))),
            f2_increment=float(raw.get("f2_increment", f2.get("f_delta", 2.0))),
            f1_shards=int(raw.get("f1_shards", f1.get("shards", 1))),
            f2_shards=int(raw.get("f2_shards", f2.get("shards", 2))),
            malicious_land_multiplier=int(raw.get("malicious_land_multiplier", malicious.get("multiplier", 3))),
            s_cash_plus1_probability=float(raw.get("s_cash_plus1_probability", s.get("cash_plus1_probability", 0.50))),
            s_cash_plus2_probability=float(raw.get("s_cash_plus2_probability", s.get("cash_plus2_probability", 0.25))),
            s_cash_minus1_probability=float(raw.get("s_cash_minus1_probability", s.get("cash_minus1_probability", 0.25))),
            zone_colors=zone_colors,
        )


@dataclass(slots=True)
class BoardConfig:
    loop_pattern: Optional[Tuple[CellKind, ...]] = None
    special_tile_s_display_name: str = "운수"
    side_pattern: Optional[Tuple[CellKind, ...]] = field(
        default_factory=lambda: (
            CellKind.F1,
            CellKind.T2, CellKind.T2,
            CellKind.S,
            CellKind.T2, CellKind.T3, CellKind.T2,
            CellKind.S,
            CellKind.T2, CellKind.T2,
            CellKind.F2,
        )
    )
    f_end_value: float = 15.0
    f1_increment: float = 1.0
    f2_increment: float = 2.0
    f1_shards: int = 1
    f2_shards: int = 2
    malicious_land_multiplier: int = 3
    s_cash_plus1_probability: float = 0.50
    s_cash_plus2_probability: float = 0.25
    s_cash_minus1_probability: float = 0.25
    zone_colors: Tuple[str, ...] = WEATHER_ZONE_COLORS
    side_land_profile_keys: Optional[Tuple[str, ...]] = field(
        default_factory=lambda: (
            'HIGH', 'HIGH', 'LOW', 'MID', 'LOW', 'HIGH', 'HIGH',
        )
    )
    side_land_tile_rules: Optional[Tuple[TileRule, ...]] = None
    tile_metadata_layout: Optional[Tuple[TileMetadata, ...]] = None
    _loop_cache: Tuple[CellKind, ...] = field(init=False, repr=False)
    _block_ids_cache: Tuple[int, ...] = field(init=False, repr=False)
    _block_color_map_cache: Dict[int, str] = field(init=False, repr=False)
    _land_tile_rule_overrides_cache: Dict[int, TileRule] = field(init=False, repr=False)
    _land_tile_profile_overrides_cache: Dict[int, str] = field(init=False, repr=False)
    _tile_metadata_cache: Tuple[TileMetadata, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.tile_metadata_layout is not None:
            self._tile_metadata_cache = self._normalize_tile_metadata_layout(self.tile_metadata_layout)
            self._loop_cache = tuple(tile.kind for tile in self._tile_metadata_cache)
            self._block_ids_cache = tuple(tile.block_id for tile in self._tile_metadata_cache)
            self._block_color_map_cache = self._compute_block_color_map_from_metadata(self._tile_metadata_cache)
            self._land_tile_rule_overrides_cache, self._land_tile_profile_overrides_cache = self._compute_land_tile_overrides_from_metadata(self._tile_metadata_cache)
            return
        self._loop_cache = self._compute_loop_cache()
        self._block_ids_cache = self._compute_block_ids_cache(self._loop_cache)
        self._block_color_map_cache = self._compute_block_color_map_cache(self._block_ids_cache)
        self._land_tile_rule_overrides_cache, self._land_tile_profile_overrides_cache = self._compute_land_tile_overrides_cache(self._loop_cache)
        self._tile_metadata_cache = self._compute_tile_metadata_cache(self._loop_cache)

    @staticmethod
    def _normalize_tile_metadata_layout(layout: Iterable[TileMetadata]) -> Tuple[TileMetadata, ...]:
        tiles = tuple(sorted(layout, key=lambda tile: tile.index))
        if not tiles:
            raise ValueError("tile_metadata_layout must not be empty")
        expected = list(range(len(tiles)))
        actual = [tile.index for tile in tiles]
        if actual != expected:
            raise ValueError("tile_metadata_layout indices must be contiguous and start at 0")
        return tiles

    def _compute_loop_cache(self) -> Tuple[CellKind, ...]:
        if self.loop_pattern is not None:
            return tuple(self.loop_pattern)
        if self.side_pattern is None:
            raise ValueError("Either loop_pattern, side_pattern, or tile_metadata_layout must be provided")
        side = list(self.side_pattern)
        board: List[CellKind] = []
        board += side
        board += side[1:-1]
        board += side
        board += side[1:-1]
        return tuple(board)

    @staticmethod
    def _compute_block_ids_cache(board: Tuple[CellKind, ...]) -> Tuple[int, ...]:
        block_ids: List[int] = [-1] * len(board)
        current = 0
        in_run = False
        for i, cell in enumerate(board):
            if cell in (CellKind.T2, CellKind.T3):
                if not in_run:
                    in_run = True
                    current += 1
                block_ids[i] = current
            else:
                in_run = False
        return tuple(block_ids)

    @staticmethod
    def _compute_block_color_map_from_metadata(metadata: Tuple[TileMetadata, ...]) -> Dict[int, str]:
        mapping: Dict[int, str] = {}
        for tile in metadata:
            if tile.block_id <= 0 or tile.zone_color is None:
                continue
            mapping.setdefault(tile.block_id, tile.zone_color)
        return mapping

    def _compute_block_color_map_cache(self, block_ids: Tuple[int, ...]) -> Dict[int, str]:
        colors = tuple(self.zone_colors)
        if not colors:
            raise ValueError("zone_colors must not be empty")
        mapping: Dict[int, str] = {}
        for bid in sorted({b for b in block_ids if b > 0}):
            mapping[bid] = colors[(bid - 1) % len(colors)]
        return mapping

    def _compute_land_tile_overrides_cache(self, board: Tuple[CellKind, ...]) -> tuple[Dict[int, TileRule], Dict[int, str]]:
        rule_overrides: Dict[int, TileRule] = {}
        profile_overrides: Dict[int, str] = {}
        side_land_index = 0
        for i, cell in enumerate(board):
            if cell in (CellKind.F1, CellKind.F2):
                side_land_index = 0
                continue
            if cell not in (CellKind.T2, CellKind.T3):
                continue
            if self.side_land_profile_keys is not None:
                if side_land_index >= len(self.side_land_profile_keys):
                    raise ValueError('side_land_profile_keys is shorter than the number of land tiles on a side')
                profile_overrides[i] = self.side_land_profile_keys[side_land_index]
            elif self.side_land_tile_rules is not None:
                if side_land_index >= len(self.side_land_tile_rules):
                    raise ValueError('side_land_tile_rules is shorter than the number of land tiles on a side')
                rule_overrides[i] = self.side_land_tile_rules[side_land_index]
            side_land_index += 1
        return rule_overrides, profile_overrides

    @staticmethod
    def _compute_land_tile_overrides_from_metadata(metadata: Tuple[TileMetadata, ...]) -> tuple[Dict[int, TileRule], Dict[int, str]]:
        rule_overrides: Dict[int, TileRule] = {}
        profile_overrides: Dict[int, str] = {}
        for tile in metadata:
            if not tile.is_land:
                continue
            if tile.purchase_cost is not None and tile.rent_cost is not None:
                rule_overrides[tile.index] = TileRule(purchase_cost=tile.purchase_cost, rent_cost=tile.rent_cost)
            if tile.economy_profile:
                profile_overrides[tile.index] = tile.economy_profile
        return rule_overrides, profile_overrides

    def _compute_tile_metadata_cache(self, board: Tuple[CellKind, ...]) -> Tuple[TileMetadata, ...]:
        metadata: List[TileMetadata] = []
        for idx, kind in enumerate(board):
            block_id = self._block_ids_cache[idx]
            rule = self._land_tile_rule_overrides_cache.get(idx)
            metadata.append(
                TileMetadata(
                    index=idx,
                    kind=kind,
                    block_id=block_id,
                    zone_color=self._block_color_map_cache.get(block_id),
                    purchase_cost=None if rule is None else rule.purchase_cost,
                    rent_cost=None if rule is None else rule.rent_cost,
                    economy_profile=self._land_tile_profile_overrides_cache.get(idx),
                )
            )
        return tuple(metadata)

    def build_loop(self) -> List[CellKind]:
        return [tile.kind for tile in self._tile_metadata_cache]

    def block_ids(self) -> List[int]:
        return [tile.block_id for tile in self._tile_metadata_cache]

    def build_block_color_map(self) -> Dict[int, str]:
        return dict(self._block_color_map_cache)

    def build_land_tile_rule_overrides(self, profile_costs: Optional[Dict[str, Tuple[int, int]]] = None) -> Dict[int, TileRule]:
        overrides = dict(self._land_tile_rule_overrides_cache)
        if profile_costs:
            for idx, profile in self._land_tile_profile_overrides_cache.items():
                if idx in overrides:
                    continue
                if profile not in profile_costs:
                    raise KeyError(f'Unknown economy profile: {profile}')
                purchase_cost, rent_cost = profile_costs[profile]
                overrides[idx] = TileRule(purchase_cost=purchase_cost, rent_cost=rent_cost)
        return overrides

    def build_tile_metadata(self) -> List[TileMetadata]:
        return list(self._tile_metadata_cache)

    def block_tile_indices(self, block_id: int, *, land_only: bool = False) -> List[int]:
        return [
            tile.index for tile in self._tile_metadata_cache
            if tile.block_id == block_id and (not land_only or tile.is_land)
        ]

    def tile_indices_by_kind(self, *kinds: CellKind) -> List[int]:
        wanted = set(kinds)
        return [tile.index for tile in self._tile_metadata_cache if tile.kind in wanted]

    @classmethod
    def from_tile_metadata(
        cls,
        tile_metadata: Iterable[TileMetadata],
        *,
        layout_metadata: BoardLayoutMetadata | None = None,
    ) -> "BoardConfig":
        meta = layout_metadata or BoardLayoutMetadata()
        return cls(
            special_tile_s_display_name=meta.special_tile_s_display_name,
            f_end_value=meta.f_end_value,
            f1_increment=meta.f1_increment,
            f2_increment=meta.f2_increment,
            f1_shards=meta.f1_shards,
            f2_shards=meta.f2_shards,
            malicious_land_multiplier=meta.malicious_land_multiplier,
            s_cash_plus1_probability=meta.s_cash_plus1_probability,
            s_cash_plus2_probability=meta.s_cash_plus2_probability,
            s_cash_minus1_probability=meta.s_cash_minus1_probability,
            zone_colors=tuple(meta.zone_colors),
            tile_metadata_layout=tuple(tile_metadata),
            loop_pattern=None,
            side_pattern=None,
            side_land_profile_keys=None,
            side_land_tile_rules=None,
        )


@dataclass(slots=True)
class CoinRule:
    starting_hand_coins: int = 0
    lap_reward_cash: int = 5
    lap_reward_coins: int = 3
    coins_from_visiting_own_tile: int = 1
    max_coins_per_tile: int = 3
    max_place_per_visit: int = 3
    can_place_on_first_purchase: bool = True


@dataclass(slots=True)
class ShardRule:
    starting_shards: int = 2
    lap_reward_shards: int = 3


@dataclass(slots=True)
class EconomyRule:
    starting_cash: int = 20
    tile_profile_costs: Dict[str, TileRule] = field(default_factory=lambda: {
        'HIGH': TileRule(purchase_cost=5, rent_cost=5),
        'MID': TileRule(purchase_cost=4, rent_cost=4),
        'LOW': TileRule(purchase_cost=3, rent_cost=3),
    })
    tile_rules: Dict[CellKind, TileRule] = field(
        default_factory=lambda: {
            CellKind.T2: TileRule(purchase_cost=3, rent_cost=3),
            CellKind.T3: TileRule(purchase_cost=4, rent_cost=4),
        }
    )
    tile_rule_overrides: Dict[int, TileRule] = field(default_factory=dict)

    def tile_rule_for(self, board: List[CellKind], pos: int) -> TileRule:
        if pos in self.tile_rule_overrides:
            return self.tile_rule_overrides[pos]
        return self.tile_rules[board[pos]]

    def purchase_cost_for(self, board: List[CellKind], pos: int) -> int:
        return self.tile_rule_for(board, pos).purchase_cost

    def rent_cost_for(self, board: List[CellKind], pos: int) -> int:
        return self.tile_rule_for(board, pos).rent_cost

    def malicious_cost_for(self, board: List[CellKind], pos: int, multiplier: int = 3) -> int:
        return self.purchase_cost_for(board, pos) * multiplier


@dataclass(slots=True)
class EndRule:
    tiles_to_trigger_end: int | None = None
    monopolies_to_trigger_end: int = 3
    higher_tiles_to_trigger_end: int | None = 9
    end_when_alive_players_at_most: int = 2
    max_rounds: int | None = None
    max_turns: int | None = None


@dataclass(slots=True)
class DiceCardRule:
    enabled: bool = True
    values: Tuple[int, ...] = (1, 2, 3, 4, 5, 6)
    one_shot: bool = True
    max_cards_per_turn: int = 2
    use_one_card_plus_one_die: bool = True


@dataclass(slots=True)
class CharacterRule:
    starting_active_by_card: Dict[int, str] = field(default_factory=lambda: dict(STARTING_ACTIVE_BY_CARD))
    randomize_starting_active_by_card: bool = True
    hidden_selection: bool = True


@dataclass(slots=True)
class GameConfig:
    player_count: int = 4
    fortune_csv_path: str = "fortune.csv"
    trick_csv_path: str = "trick.csv"
    weather_csv_path: str = "weather.csv"
    rule_scripts_path: str = "rule_scripts.json"
    ruleset_path: str | None = "ruleset.json"
    board: BoardConfig = field(default_factory=BoardConfig)
    economy: EconomyRule = field(default_factory=EconomyRule)
    coins: CoinRule = field(default_factory=CoinRule)
    shards: ShardRule = field(default_factory=ShardRule)
    end: EndRule = field(default_factory=EndRule)
    dice_cards: DiceCardRule = field(default_factory=DiceCardRule)
    characters: CharacterRule = field(default_factory=CharacterRule)
    initial_position_index: int = 0
    rules: GameRules | None = None

    def __post_init__(self) -> None:
        if not self.economy.tile_rule_overrides:
            profile_costs = {name: (rule.purchase_cost, rule.rent_cost) for name, rule in self.economy.tile_profile_costs.items()}
            self.economy.tile_rule_overrides = self.board.build_land_tile_rule_overrides(profile_costs)
        if self.rules is None and self.ruleset_path:
            loaded_rules = load_ruleset(self.ruleset_path)
            if loaded_rules is not None:
                self.rules = loaded_rules
        if self.rules is None:
            self.rules = GameRules()
            self.rules.sync_from_config_mirrors(self)
        else:
            self.rules.sync_to_config_mirrors(self)
        profile_costs = {name: (rule.purchase_cost, rule.rent_cost) for name, rule in self.economy.tile_profile_costs.items()}
        self.economy.tile_rule_overrides = self.board.build_land_tile_rule_overrides(profile_costs)


DEFAULT_CONFIG = GameConfig()
