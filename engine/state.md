# state.py

`GameState` and `PlayerState` define the canonical engine checkpoint.

## Checkpoint Content

`GameState.to_checkpoint_payload()` exports deterministic runtime state for Redis storage. `GameState.from_checkpoint_payload(config, payload)` rebuilds the same canonical state.

The checkpoint includes:

- players, board, tile ownership, score coins, decks, discard piles, weather, round, and turn fields
- prompt continuation metadata
- queued `ActionEnvelope` records
- scheduled phase actions
- in-progress turn-log aggregation
- runtime bridge fields needed by active module frames

Frontend view state is a projection. Redis recovery resumes from `GameState`, frame stack, and module cursor.

## Tile Runtime State

`TileState` is the single runtime owner for tile metadata and mutable tile values:

- `index`
- `kind`
- `block_id`
- `zone_color`
- `purchase_cost`
- `rent_cost`
- `owner_id`
- `score_coins`
- `economy_profile`

Use helpers such as `tile_at`, `tile_positions`, `first_tile_position`, `block_tile_positions`, and `adjacent_land_positions` instead of hardcoded board coordinates.

## Rule Data

Initial resources and economy values come from `config.rules`. Config mirror fields are synchronized from the same rule object so modules read a consistent value set.
