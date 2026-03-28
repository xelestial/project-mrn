from __future__ import annotations

from typing import Sequence

from config import CellKind
from policy.decision.scored_choice import run_ranked_choice


def choose_coin_placement_tile_id(
    candidates: Sequence[int],
    *,
    tile_coins: Sequence[int],
    board: Sequence[CellKind],
    player_position: int,
    max_coins_per_tile: int,
    token_opt_profile: bool,
) -> int | None:
    if not candidates:
        return None
    if token_opt_profile:
        board_len = len(board)
        return run_ranked_choice(
            candidates,
            ranker=lambda i: (
                tile_coins[i],
                board[i] == CellKind.T3,
                -(((i - player_position) % board_len) or board_len),
                max_coins_per_tile - tile_coins[i],
                -i,
            ),
        ).choice
    return run_ranked_choice(
        candidates,
        ranker=lambda i: (
            max_coins_per_tile - tile_coins[i],
            board[i] == CellKind.T3,
            -i,
        ),
    ).choice
