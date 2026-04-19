# board_layout_creator.py

Loads external board layouts into `BoardConfig`.

Supported sources:
- Full JSON layout spec with `layout_metadata` + `tiles`
- CSV tile spec with optional sidecar metadata JSON (`*_meta.json`)
- CSV tile spec with explicit metadata path via CLI (`--board-layout-meta`)

Externalized board-level metadata includes:
- S tile display name and outcome probabilities
- F1/F2 F deltas and shard rewards
- malicious land multiplier
- zone color sequence


### 0.7.61 structure-only board layout
Board layout JSON/CSV may now omit `purchase_cost` and `rent_cost` and provide `economy_profile` instead. This keeps board layout structural while ruleset JSON remains numeric.

### 0.7.62 path resolution
Relative layout paths now fall back to the module directory so tests and tooling work even when the current working directory is the repository root.
