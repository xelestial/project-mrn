from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set

from characters import CHARACTERS
from config import CellKind, GameConfig, TileMetadata
from fortune_cards import FortuneCard, build_fortune_deck
from runtime_modules.contracts import (
    FrameState,
    ModifierRegistryState,
    ModuleJournalEntry,
    PromptContinuation,
    SimultaneousPromptBatchContinuation,
)
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
    trick_obstacle_this_round: bool = False
    trick_zone_chain_this_turn: bool = False
    trick_reroll_budget_this_turn: int = 0
    trick_reroll_label_this_turn: str = ""
    control_finisher_turns: int = 0
    control_finisher_reason: str = ""

    @property
    def attribute(self) -> str:
        if not self.current_character:
            return ""
        char_def = CHARACTERS[self.current_character]
        return char_def.attribute

    def public_trick_cards(self) -> List[TrickCard]:
        if not self.trick_hand:
            return []
        return [c for c in self.trick_hand if c.deck_index != self.hidden_trick_deck_index]

    def public_trick_names(self) -> List[str]:
        return [c.name for c in self.public_trick_cards()]

    def hidden_trick_count(self) -> int:
        if self.hidden_trick_deck_index is None:
            return 0
        return 1 if any(c.deck_index == self.hidden_trick_deck_index for c in self.trick_hand) else 0


@dataclass(slots=True)
class ActionEnvelope:
    action_id: str
    type: str
    actor_player_id: int
    source: str = ""
    target_player_id: int | None = None
    phase: str = ""
    priority: int = 100
    parent_action_id: str = ""
    idempotency_key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict:
        payload = {
            "action_id": self.action_id,
            "type": self.type,
            "actor_player_id": self.actor_player_id,
            "source": self.source,
            "payload": dict(self.payload),
        }
        if self.target_player_id is not None:
            payload["target_player_id"] = self.target_player_id
        if self.phase:
            payload["phase"] = self.phase
        if self.priority != 100:
            payload["priority"] = self.priority
        if self.parent_action_id:
            payload["parent_action_id"] = self.parent_action_id
        if self.idempotency_key:
            payload["idempotency_key"] = self.idempotency_key
        return payload

    @classmethod
    def from_payload(cls, payload: dict) -> "ActionEnvelope":
        raw_target = payload.get("target_player_id")
        return cls(
            action_id=str(payload.get("action_id", "")),
            type=str(payload.get("type", "")),
            actor_player_id=int(payload.get("actor_player_id", 0)),
            source=str(payload.get("source", "")),
            target_player_id=None if raw_target is None else int(raw_target),
            phase=str(payload.get("phase", "")),
            priority=int(payload.get("priority", 100)),
            parent_action_id=str(payload.get("parent_action_id", "")),
            idempotency_key=str(payload.get("idempotency_key", "")),
            payload=dict(payload.get("payload") or {}),
        )


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
    marker_draft_clockwise: bool = True
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
    lap_reward_cash_pool_remaining: int = 30
    lap_reward_shards_pool_remaining: int = 18
    lap_reward_coins_pool_remaining: int = 18
    prompt_sequence: int = 0
    pending_prompt_request_id: str = ""
    pending_prompt_type: str = ""
    pending_prompt_player_id: int = 0
    pending_prompt_instance_id: int = 0
    pending_actions: List[ActionEnvelope] = field(default_factory=list)
    scheduled_actions: List[ActionEnvelope] = field(default_factory=list)
    pending_action_log: dict[str, Any] = field(default_factory=dict)
    pending_turn_completion: dict[str, Any] = field(default_factory=dict)
    round_setup_replay_base: dict[str, Any] = field(default_factory=dict)
    runtime_runner_kind: str = "legacy"
    runtime_checkpoint_schema_version: int = 1
    runtime_frame_stack: List[FrameState] = field(default_factory=list)
    runtime_module_journal: List[ModuleJournalEntry] = field(default_factory=list)
    runtime_active_prompt: PromptContinuation | None = None
    runtime_active_prompt_batch: SimultaneousPromptBatchContinuation | None = None
    runtime_scheduled_turn_injections: Dict[str, List[dict[str, Any]]] = field(default_factory=dict)
    runtime_modifier_registry: ModifierRegistryState = field(default_factory=ModifierRegistryState)

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
            marker_draft_clockwise=True,
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

    def to_checkpoint_payload(self) -> dict:
        return {
            "schema_version": 1,
            "turn_index": self.turn_index,
            "rounds_completed": self.rounds_completed,
            "current_round_order": list(self.current_round_order),
            "f_value": self.f_value,
            "bankrupt_players": self.bankrupt_players,
            "malicious_tiles": self.malicious_tiles,
            "winner_ids": list(self.winner_ids),
            "end_reason": self.end_reason,
            "marker_owner_id": self.marker_owner_id,
            "marker_draft_clockwise": self.marker_draft_clockwise,
            "active_by_card": dict(self.active_by_card),
            "pending_marker_flip_owner_id": self.pending_marker_flip_owner_id,
            "current_weather_effects": sorted(self.current_weather_effects),
            "next_supply_f_threshold": self.next_supply_f_threshold,
            "global_rent_half_this_turn": self.global_rent_half_this_turn,
            "global_rent_double_this_turn": self.global_rent_double_this_turn,
            "global_rent_double_permanent": self.global_rent_double_permanent,
            "tile_rent_modifiers_this_turn": dict(self.tile_rent_modifiers_this_turn),
            "tile_purchase_blocked_turn_index": dict(self.tile_purchase_blocked_turn_index),
            "lap_reward_cash_pool_remaining": self.lap_reward_cash_pool_remaining,
            "lap_reward_shards_pool_remaining": self.lap_reward_shards_pool_remaining,
            "lap_reward_coins_pool_remaining": self.lap_reward_coins_pool_remaining,
            "prompt_sequence": self.prompt_sequence,
            "pending_prompt_request_id": self.pending_prompt_request_id,
            "pending_prompt_type": self.pending_prompt_type,
            "pending_prompt_player_id": self.pending_prompt_player_id,
            "pending_prompt_instance_id": self.pending_prompt_instance_id,
            "pending_actions": [action.to_payload() for action in self.pending_actions],
            "scheduled_actions": [action.to_payload() for action in self.scheduled_actions],
            "pending_action_log": dict(self.pending_action_log),
            "pending_turn_completion": dict(self.pending_turn_completion),
            "round_setup_replay_base": dict(self.round_setup_replay_base),
            "runtime_runner_kind": self.runtime_runner_kind,
            "runtime_checkpoint_schema_version": self.runtime_checkpoint_schema_version,
            "runtime_frame_stack": [frame.to_payload() for frame in self.runtime_frame_stack],
            "runtime_module_journal": [entry.to_payload() for entry in self.runtime_module_journal],
            "runtime_active_prompt": None if self.runtime_active_prompt is None else self.runtime_active_prompt.to_payload(),
            "runtime_active_prompt_batch": None
            if self.runtime_active_prompt_batch is None
            else self.runtime_active_prompt_batch.to_payload(),
            "runtime_scheduled_turn_injections": dict(self.runtime_scheduled_turn_injections),
            "runtime_modifier_registry": self.runtime_modifier_registry.to_payload(),
            "tiles": [_tile_to_payload(tile) for tile in self.tiles],
            "players": [_player_to_payload(player) for player in self.players],
            "fortune_draw_pile": [_card_key(card) for card in self.fortune_draw_pile],
            "fortune_discard_pile": [_card_key(card) for card in self.fortune_discard_pile],
            "trick_draw_pile": [_card_key(card) for card in self.trick_draw_pile],
            "trick_discard_pile": [_card_key(card) for card in self.trick_discard_pile],
            "weather_draw_pile": [_card_key(card) for card in self.weather_draw_pile],
            "weather_discard_pile": [_card_key(card) for card in self.weather_discard_pile],
            "current_weather": None if self.current_weather is None else _card_key(self.current_weather),
        }

    @classmethod
    def from_checkpoint_payload(cls, config: GameConfig, payload: dict) -> "GameState":
        state = cls.create(config)
        fortune_by_id = _cards_by_deck_index(build_fortune_deck(config.fortune_csv_path))
        trick_by_id = _cards_by_deck_index(build_trick_deck(config.trick_csv_path))
        weather_by_id = _cards_by_deck_index(build_weather_deck(config.weather_csv_path))

        state.turn_index = int(payload.get("turn_index", state.turn_index))
        state.rounds_completed = int(payload.get("rounds_completed", state.rounds_completed))
        state.current_round_order = [int(item) for item in payload.get("current_round_order", state.current_round_order)]
        state.f_value = float(payload.get("f_value", state.f_value))
        state.bankrupt_players = int(payload.get("bankrupt_players", state.bankrupt_players))
        state.malicious_tiles = int(payload.get("malicious_tiles", state.malicious_tiles))
        state.winner_ids = [int(item) for item in payload.get("winner_ids", state.winner_ids)]
        state.end_reason = str(payload.get("end_reason", state.end_reason))
        state.marker_owner_id = int(payload.get("marker_owner_id", state.marker_owner_id))
        state.marker_draft_clockwise = bool(payload.get("marker_draft_clockwise", state.marker_draft_clockwise))
        state.active_by_card = {int(key): str(value) for key, value in dict(payload.get("active_by_card", state.active_by_card)).items()}
        raw_pending_owner = payload.get("pending_marker_flip_owner_id", state.pending_marker_flip_owner_id)
        state.pending_marker_flip_owner_id = None if raw_pending_owner is None else int(raw_pending_owner)
        state.current_weather_effects = {str(item) for item in payload.get("current_weather_effects", [])}
        state.next_supply_f_threshold = int(payload.get("next_supply_f_threshold", state.next_supply_f_threshold))
        state.global_rent_half_this_turn = bool(payload.get("global_rent_half_this_turn", state.global_rent_half_this_turn))
        state.global_rent_double_this_turn = bool(payload.get("global_rent_double_this_turn", state.global_rent_double_this_turn))
        state.global_rent_double_permanent = bool(payload.get("global_rent_double_permanent", state.global_rent_double_permanent))
        state.tile_rent_modifiers_this_turn = {int(key): int(value) for key, value in dict(payload.get("tile_rent_modifiers_this_turn", {})).items()}
        state.tile_purchase_blocked_turn_index = {int(key): int(value) for key, value in dict(payload.get("tile_purchase_blocked_turn_index", {})).items()}
        state.lap_reward_cash_pool_remaining = int(payload.get("lap_reward_cash_pool_remaining", state.lap_reward_cash_pool_remaining))
        state.lap_reward_shards_pool_remaining = int(payload.get("lap_reward_shards_pool_remaining", state.lap_reward_shards_pool_remaining))
        state.lap_reward_coins_pool_remaining = int(payload.get("lap_reward_coins_pool_remaining", state.lap_reward_coins_pool_remaining))
        state.prompt_sequence = int(payload.get("prompt_sequence", state.prompt_sequence))
        state.pending_prompt_request_id = str(payload.get("pending_prompt_request_id", state.pending_prompt_request_id))
        state.pending_prompt_type = str(payload.get("pending_prompt_type", state.pending_prompt_type))
        state.pending_prompt_player_id = int(payload.get("pending_prompt_player_id", state.pending_prompt_player_id))
        state.pending_prompt_instance_id = int(payload.get("pending_prompt_instance_id", state.pending_prompt_instance_id))
        state.pending_actions = [
            ActionEnvelope.from_payload(raw_action)
            for raw_action in payload.get("pending_actions", [])
            if isinstance(raw_action, dict)
        ]
        state.scheduled_actions = [
            ActionEnvelope.from_payload(raw_action)
            for raw_action in payload.get("scheduled_actions", [])
            if isinstance(raw_action, dict)
        ]
        state.pending_action_log = dict(payload.get("pending_action_log") or {})
        state.pending_turn_completion = dict(payload.get("pending_turn_completion") or {})
        state.round_setup_replay_base = dict(payload.get("round_setup_replay_base") or {})
        state.runtime_runner_kind = str(payload.get("runtime_runner_kind", state.runtime_runner_kind) or "legacy")
        state.runtime_checkpoint_schema_version = int(
            payload.get("runtime_checkpoint_schema_version", state.runtime_checkpoint_schema_version) or 1
        )
        state.runtime_frame_stack = [
            FrameState.from_payload(raw_frame)
            for raw_frame in payload.get("runtime_frame_stack", [])
            if isinstance(raw_frame, dict)
        ]
        state.runtime_module_journal = [
            ModuleJournalEntry.from_payload(raw_entry)
            for raw_entry in payload.get("runtime_module_journal", [])
            if isinstance(raw_entry, dict)
        ]
        raw_runtime_prompt = payload.get("runtime_active_prompt")
        state.runtime_active_prompt = (
            PromptContinuation.from_payload(raw_runtime_prompt)
            if isinstance(raw_runtime_prompt, dict)
            else None
        )
        raw_runtime_prompt_batch = payload.get("runtime_active_prompt_batch")
        state.runtime_active_prompt_batch = (
            SimultaneousPromptBatchContinuation.from_payload(raw_runtime_prompt_batch)
            if isinstance(raw_runtime_prompt_batch, dict)
            else None
        )
        state.runtime_scheduled_turn_injections = dict(payload.get("runtime_scheduled_turn_injections") or {})
        raw_modifier_registry = payload.get("runtime_modifier_registry")
        state.runtime_modifier_registry = (
            ModifierRegistryState.from_payload(raw_modifier_registry)
            if isinstance(raw_modifier_registry, dict)
            else ModifierRegistryState()
        )

        for raw_tile in payload.get("tiles", []):
            if not isinstance(raw_tile, dict):
                continue
            index = int(raw_tile.get("index", -1))
            if 0 <= index < len(state.tiles):
                _apply_tile_payload(state.tiles[index], raw_tile)
        for raw_player in payload.get("players", []):
            if not isinstance(raw_player, dict):
                continue
            player_id = int(raw_player.get("player_id", -1))
            if 0 <= player_id < len(state.players):
                _apply_player_payload(state.players[player_id], raw_player, trick_by_id)

        state.fortune_draw_pile = _cards_from_keys(payload.get("fortune_draw_pile", []), fortune_by_id)
        state.fortune_discard_pile = _cards_from_keys(payload.get("fortune_discard_pile", []), fortune_by_id)
        state.trick_draw_pile = _cards_from_keys(payload.get("trick_draw_pile", []), trick_by_id)
        state.trick_discard_pile = _cards_from_keys(payload.get("trick_discard_pile", []), trick_by_id)
        state.weather_draw_pile = _cards_from_keys(payload.get("weather_draw_pile", []), weather_by_id)
        state.weather_discard_pile = _cards_from_keys(payload.get("weather_discard_pile", []), weather_by_id)
        state.current_weather = _card_from_key(payload.get("current_weather"), weather_by_id)
        return state


def _tile_to_payload(tile: TileState) -> dict:
    return {
        "index": tile.index,
        "kind": tile.kind.name,
        "block_id": tile.block_id,
        "zone_color": tile.zone_color,
        "purchase_cost": tile.purchase_cost,
        "rent_cost": tile.rent_cost,
        "economy_profile": tile.economy_profile,
        "owner_id": tile.owner_id,
        "score_coins": tile.score_coins,
    }


def _apply_tile_payload(tile: TileState, payload: dict) -> None:
    tile.kind = CellKind[str(payload.get("kind", tile.kind.name))]
    tile.block_id = int(payload.get("block_id", tile.block_id))
    tile.zone_color = payload.get("zone_color", tile.zone_color)
    tile.purchase_cost = _optional_int(payload.get("purchase_cost", tile.purchase_cost))
    tile.rent_cost = _optional_int(payload.get("rent_cost", tile.rent_cost))
    tile.economy_profile = payload.get("economy_profile", tile.economy_profile)
    tile.owner_id = _optional_int(payload.get("owner_id", tile.owner_id))
    tile.score_coins = int(payload.get("score_coins", tile.score_coins))


def _player_to_payload(player: PlayerState) -> dict:
    payload = {}
    for item in fields(PlayerState):
        value = getattr(player, item.name)
        if item.name == "trick_hand":
            payload[item.name] = [_card_key(card) for card in value]
        elif isinstance(value, set):
            payload[item.name] = sorted(value)
        else:
            payload[item.name] = value
    return payload


def _apply_player_payload(player: PlayerState, payload: dict, trick_by_id: dict[int, TrickCard]) -> None:
    for item in fields(PlayerState):
        if item.name not in payload:
            continue
        value = payload[item.name]
        if item.name == "trick_hand":
            setattr(player, item.name, _cards_from_keys(value, trick_by_id))
        elif item.name in {"visited_owned_tile_indices", "used_dice_cards"}:
            setattr(player, item.name, {int(entry) for entry in value or []})
        else:
            setattr(player, item.name, value)


def _card_key(card) -> int:
    return int(card.deck_index)


def _cards_by_deck_index(cards: list) -> dict[int, object]:
    return {int(card.deck_index): card for card in cards}


def _card_from_key(raw_key, cards_by_id: dict[int, object]):
    if raw_key is None:
        return None
    return cards_by_id[int(raw_key)]


def _cards_from_keys(raw_keys, cards_by_id: dict[int, object]) -> list:
    return [_card_from_key(raw_key, cards_by_id) for raw_key in raw_keys or [] if raw_key is not None]


def _optional_int(value) -> int | None:
    return None if value is None else int(value)
