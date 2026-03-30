# WS Runtime Contract

This directory freezes v1 transport contracts for the online runtime.

## Layout

- `schemas/`: JSON Schema files by message type.
- `examples/`: canonical payload examples used for docs and tests.

## Scope

Inbound (`server -> client`):

- `event`
- `prompt`
- `decision_ack`
- `error`
- `heartbeat`

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
