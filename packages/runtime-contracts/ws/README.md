# WS Runtime Contract

This directory freezes v1 transport contracts for the online runtime.

## Layout

- `schemas/`: JSON Schema files by message type.
- `examples/`: canonical payload examples used for docs and tests.
  - Includes per-message fixtures and ordered sequence fixtures for decision lanes.

## Scope

Inbound (`server -> client`):

- `event`
- `prompt`
- `decision_ack`
- `error`
- `heartbeat`

Prompt payloads use canonical `legal_choices` as the primary choice list. A legacy `choices` field may still appear temporarily for compatibility, but frozen examples and new surfaces should prefer `legal_choices`.

Outbound (`client -> server`):

- `resume`
- `decision`

## Change Rules

1. Additive changes only by default.
2. Breaking changes require:
   - schema update
   - example update
   - API/interface spec update
   - compatibility note in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Ordered Sequence Fixtures

- `sequence.decision.accepted_then_domain.json`
  - `decision_requested -> decision_resolved -> player_move`
- `sequence.decision.timeout_then_domain.json`
  - `decision_requested -> decision_resolved -> decision_timeout_fallback -> turn_end_snapshot`
