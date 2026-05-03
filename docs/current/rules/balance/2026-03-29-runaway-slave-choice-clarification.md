# 2026-03-29 Runaway Slave Choice Clarification

This note records a clarified interpretation for `탈출 노비`.

## Clarified Rule

When `탈출 노비` is exactly one step short of a valid:

- `시작` tile
- `종료` tile
- `운수` tile

the player may move into that tile.

Important:

- this is an optional choice
- it is not a forced automatic correction

## Gameplay Meaning

The ability should be understood as:

- `할 수 있다`
- not `반드시 그렇게 이동한다`

So if both the normal landing tile and the special one-short destination matter,
the acting player should be able to choose.

## Implementation Direction

- engine/runtime behavior should not silently force `+1` movement in every qualifying case
- human-facing movement prompts should surface the branch explicitly when the rule is relevant
- AI movement logic may choose the branch, but the branch should remain conceptually optional

## Why This Matters

This affects:

- tactical escape
- safe `운수` routing
- exact `종료` timing
- replay/live viewer correctness when explaining why a pawn arrived on a special tile
