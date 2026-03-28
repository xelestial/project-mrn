"""viewer/public_state.py — public state dataclasses (SHARED_CONTRACT Layer 2).

These dataclasses define the public snapshot types:
  PlayerPublicState  — per-player public information
  TilePublicState    — per-tile public information
  BoardPublicState   — board-level public snapshot

Builder functions extract public state from engine internals without leaking
hidden information (hidden trick cards, private mark details, etc.).

Field names follow SHARED_VISUAL_RUNTIME_CONTRACT.md §Public State Schemas.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Public state dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PlayerPublicState:
    """Public player state visible to all players (SHARED_CONTRACT §PlayerPublicState)."""
    player_id: int                  # 1-indexed
    seat: int                       # 1-indexed seat number
    display_name: str
    alive: bool
    character: str
    position: int                   # 0-indexed tile index
    cash: int
    shards: int
    hand_score_coins: int           # score coins held in hand
    placed_score_coins: int         # score coins placed on owned tiles
    owned_tile_count: int
    owned_tile_indices: list[int]   # 0-indexed tile indices
    public_tricks: list[str]        # names of visible trick cards
    hidden_trick_count: int         # count only, not contents
    mark_status: str                # "clear" | "marked" | "immune"
    pending_mark_source: int | None # 1-indexed source player_id, or None
    public_effects: list[str]       # publicly visible active effects
    burden_summary: list[str]       # names of burden cards in hand

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # GPT viewer compatibility aliases
        d["tiles_owned"] = d["owned_tile_count"]
        d["score_coins_placed"] = d["placed_score_coins"]
        d["trick_cards_visible"] = d["public_tricks"]
        d["is_marked"] = d["mark_status"] == "marked"
        d["immune_to_marks"] = d["mark_status"] == "immune"
        return d


@dataclass
class TilePublicState:
    """Public tile state (SHARED_CONTRACT §TilePublicState)."""
    tile_index: int                 # 0-indexed
    tile_kind: str                  # CellKind name: T2, T3, F1, F2, S, START, etc.
    block_id: int                   # color-group block id
    zone_color: str                 # color string or ""
    purchase_cost: int | None
    rent_cost: int | None
    owner_player_id: int | None     # 1-indexed, or None if unowned
    score_coin_count: int           # placed score coins on tile
    pawn_player_ids: list[int]      # 1-indexed players currently on this tile

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class BoardPublicState:
    """Board-level public snapshot (SHARED_CONTRACT §BoardPublicState)."""
    tiles: list[TilePublicState]
    f_value: float
    marker_owner_player_id: int     # 1-indexed
    round_index: int
    turn_index: int

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # GPT viewer compatibility alias
        d["marker_owner_id"] = d["marker_owner_player_id"]
        return d


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

def build_player_public_state(player: Any, state: Any) -> PlayerPublicState:
    """Build PlayerPublicState from engine PlayerState + GameState.

    Hidden information never included:
    - hidden trick card name/content (only count)
    - internal mark details beyond source player_id
    """
    owned_indices = [t.index for t in state.tiles if t.owner_id == player.player_id]

    burden_cards = [c.name for c in player.trick_hand if getattr(c, "is_burden", False)]

    if getattr(player, "immune_to_marks_this_round", False):
        mark_status = "immune"
    elif player.pending_marks:
        mark_status = "marked"
    else:
        mark_status = "clear"

    pending_source: int | None = None
    if player.pending_marks:
        raw = player.pending_marks[0].get("source_player_id")
        if raw is not None:
            pending_source = raw + 1  # Convert 0-indexed → 1-indexed

    public_effects: list[str] = []
    for attr, label in [
        ("trick_zone_chain_this_turn", "zone_chain"),
        ("trick_encounter_boost_this_turn", "encounter_boost"),
        ("trick_force_sale_landing_this_turn", "force_sale"),
        ("trick_one_extra_adjacent_buy_this_turn", "extra_adjacent_buy"),
        ("trick_same_tile_cash2_this_turn", "same_tile_cash2"),
        ("trick_same_tile_shard_rake_this_turn", "same_tile_shard_rake"),
        ("trick_personal_rent_half_this_turn", "personal_rent_half"),
        ("trick_free_purchase_this_turn", "free_purchase"),
    ]:
        if getattr(player, attr, False):
            public_effects.append(label)

    return PlayerPublicState(
        player_id=player.player_id + 1,
        seat=player.player_id + 1,
        display_name=f"Player {player.player_id + 1}",
        alive=player.alive,
        character=player.current_character,
        position=player.position,
        cash=player.cash,
        shards=player.shards,
        hand_score_coins=player.hand_coins,
        placed_score_coins=player.score_coins_placed,
        owned_tile_count=player.tiles_owned,
        owned_tile_indices=owned_indices,
        public_tricks=player.public_trick_names(),
        hidden_trick_count=player.hidden_trick_count(),
        mark_status=mark_status,
        pending_mark_source=pending_source,
        public_effects=public_effects,
        burden_summary=burden_cards,
    )


def build_tile_public_state(tile: Any, state: Any) -> TilePublicState:
    """Build TilePublicState from engine TileState + GameState."""
    pawn_ids = [
        p.player_id + 1
        for p in state.players
        if p.alive and p.position == tile.index
    ]
    return TilePublicState(
        tile_index=tile.index,
        tile_kind=tile.kind.name,
        block_id=tile.block_id,
        zone_color=tile.zone_color or "",
        purchase_cost=tile.purchase_cost,
        rent_cost=tile.rent_cost,
        owner_player_id=(tile.owner_id + 1) if tile.owner_id is not None else None,
        score_coin_count=tile.score_coins,
        pawn_player_ids=pawn_ids,
    )


def build_board_public_state(state: Any) -> BoardPublicState:
    """Build BoardPublicState from engine GameState."""
    tiles = [build_tile_public_state(t, state) for t in state.tiles]
    return BoardPublicState(
        tiles=tiles,
        f_value=state.f_value,
        marker_owner_player_id=state.marker_owner_id + 1,
        round_index=state.rounds_completed + 1,
        turn_index=state.turn_index + 1,
    )


def build_turn_end_snapshot(state: Any) -> dict:
    """Build a full turn-end snapshot dict (used in turn_end_snapshot event payload)."""
    return {
        "players": [build_player_public_state(p, state).to_dict() for p in state.players],
        "board": build_board_public_state(state).to_dict(),
    }
