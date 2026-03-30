# packages/runtime-contracts

Shared runtime schemas and contracts:

- event envelopes
- prompt/decision envelopes
- compatibility alias policy

## WS Contract Freeze (OI7)

WebSocket transport schemas and frozen examples live in:

- `packages/runtime-contracts/ws/schemas`
- `packages/runtime-contracts/ws/examples`

Current frozen scope:

- inbound messages: `event`, `prompt`, `decision_ack`, `error`, `heartbeat`
- outbound messages: `resume`, `decision`

Validation baseline is enforced in:

- `apps/server/tests/test_runtime_contract_examples.py`
