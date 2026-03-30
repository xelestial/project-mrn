# Online Game API Spec (REST + WebSocket)

Canonical document path. Mirror in `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md` is kept only for legacy links.

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-31`  
Parents:
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`

## Purpose

Define the concrete API contract for online session lifecycle, live stream, prompt delivery, and decision submission.

## API Versioning

- Base path: `/api/v1`
- WebSocket path: `/api/v1/sessions/{session_id}/stream`
- Breaking changes require `/api/v2`

## REST API

All REST responses use envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Error envelope:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "INVALID_STATE_TRANSITION",
    "category": "state",
    "message": "Session cannot be started from current state.",
    "retryable": false
  }
}
```

## 1) Create Session

`POST /api/v1/sessions`

Request:

```json
{
  "seats": [
    { "seat": 1, "seat_type": "human" },
    { "seat": 2, "seat_type": "ai", "ai_profile": "balanced" },
    { "seat": 3, "seat_type": "ai", "ai_profile": "aggressive" },
    { "seat": 4, "seat_type": "human" }
  ],
  "config": {
    "seed": 42,
    "seat_limits": { "min": 1, "max": 4, "allowed": [1, 2, 3, 4] },
    "board_topology": "ring"
  }
}
```

Current v1 supported session `config` keys (baseline):

- `seed`
- `seat_limits` (`min`, `max`, `allowed`)
- `board_topology` (`ring` | `line`)
- `starting_cash`
- `starting_shards`
- `dice_values`
- `dice_max_cards_per_turn`
- `labels`

Response `data`:

```json
{
  "session_id": "sess_abc123",
  "status": "waiting",
  "host_token": "host_tok_x",
  "join_tokens": {
    "1": "seat1_tok_x",
    "4": "seat4_tok_x"
  },
  "created_at": "2026-03-29T13:00:00Z"
}
```

## 2) List Sessions

`GET /api/v1/sessions`

Response `data`:

```json
{
  "sessions": [
    {
      "session_id": "sess_abc123",
      "status": "waiting",
      "round_index": 0,
      "turn_index": 0,
      "created_at": "2026-03-29T13:00:00Z"
    }
  ]
}
```

## 3) Get Session

`GET /api/v1/sessions/{session_id}`

Response `data`:

```json
{
  "session_id": "sess_abc123",
  "status": "in_progress",
  "round_index": 2,
  "turn_index": 7,
  "seats": [
    { "seat": 1, "seat_type": "human", "connected": true, "player_id": 1 },
    { "seat": 2, "seat_type": "ai", "connected": true, "player_id": 2 },
    { "seat": 3, "seat_type": "ai", "connected": true, "player_id": 3 },
    { "seat": 4, "seat_type": "human", "connected": false, "player_id": 4 }
  ]
}
```

## 4) Join Session

`POST /api/v1/sessions/{session_id}/join`

Request:

```json
{
  "seat": 1,
  "join_token": "seat1_tok_x",
  "display_name": "Player 1"
}
```

Response `data`:

```json
{
  "session_id": "sess_abc123",
  "seat": 1,
  "player_id": 1,
  "session_token": "sess_tok_player1",
  "role": "seat"
}
```

## 5) Start Session

`POST /api/v1/sessions/{session_id}/start`

Request:

```json
{
  "host_token": "host_tok_x"
}
```

Response `data`:

```json
{
  "session_id": "sess_abc123",
  "status": "in_progress",
  "started_at": "2026-03-29T13:05:00Z"
}
```

## 6) Replay Export

`GET /api/v1/sessions/{session_id}/replay`

Response `data`:

```json
{
  "session_id": "sess_abc123",
  "event_count": 742,
  "events": []
}
```

## 7) Runtime Status

`GET /api/v1/sessions/{session_id}/runtime-status`

Response `data`:

```json
{
  "session_id": "sess_abc123",
  "runtime": {
    "status": "running"
  }
}
```

Possible runtime status:

- `idle`
- `running`
- `finished`
- `failed`
- `stop_requested`

## 8) Debug Prompt Injection (Dev Only)

`POST /api/v1/sessions/{session_id}/prompts/debug`

Purpose:

- inject a prompt envelope for transport/prompt-flow smoke testing
- not intended as production gameplay endpoint

Request:

```json
{
  "request_id": "req_debug_move_1",
  "request_type": "movement",
  "player_id": 1,
  "timeout_ms": 30000,
  "choices": [
    { "choice_id": "roll", "title": "Roll dice", "description": "Normal move." }
  ],
  "public_context": {
    "round_index": 1,
    "turn_index": 1
  }
}
```

## WebSocket API

Endpoint:

`WS /api/v1/sessions/{session_id}/stream?token={session_token}`

Spectator mode:

- token omitted
- receives events only
- no prompts

Seat mode:

- `token` query param required (`session_token` from join API)
- only seat-authenticated sockets can submit `decision`

## Server to Client Messages

Common envelope:

```json
{
  "type": "event",
  "seq": 1042,
  "session_id": "sess_abc123",
  "server_time_ms": 1743210000123,
  "payload": {}
}
```

`type` values:

- `event`
- `prompt`
- `decision_ack`
- `error`
- `heartbeat`

## WS Contract Freeze Artifacts (`v1`)

Canonical frozen schemas:

- `packages/runtime-contracts/ws/schemas/inbound.event.schema.json`
- `packages/runtime-contracts/ws/schemas/inbound.prompt.schema.json`
- `packages/runtime-contracts/ws/schemas/inbound.decision_ack.schema.json`
- `packages/runtime-contracts/ws/schemas/inbound.error.schema.json`
- `packages/runtime-contracts/ws/schemas/inbound.heartbeat.schema.json`
- `packages/runtime-contracts/ws/schemas/outbound.resume.schema.json`
- `packages/runtime-contracts/ws/schemas/outbound.decision.schema.json`

Canonical examples:

- `packages/runtime-contracts/ws/examples/inbound.event.parameter_manifest.json`
- `packages/runtime-contracts/ws/examples/inbound.prompt.movement.json`
- `packages/runtime-contracts/ws/examples/inbound.decision_ack.accepted.json`
- `packages/runtime-contracts/ws/examples/inbound.error.resume_gap_too_old.json`
- `packages/runtime-contracts/ws/examples/inbound.heartbeat.backpressure.json`
- `packages/runtime-contracts/ws/examples/outbound.resume.json`
- `packages/runtime-contracts/ws/examples/outbound.decision.movement_roll.json`

Validation baseline:

- `apps/server/tests/test_runtime_contract_examples.py`

## `event`

Payload:

- `VisEventEnvelope` from shared runtime contract.

## `prompt`

Payload:

```json
{
  "request_id": "req_turn7_move",
  "request_type": "movement",
  "player_id": 1,
  "timeout_ms": 30000,
  "fallback_policy": "auto_roll_dice",
  "choices": [
    { "choice_id": "roll", "title": "Roll dice", "description": "Normal move." },
    { "choice_id": "dice_1_4", "title": "Use dice cards 1,4", "description": "Fixed move 5." }
  ],
  "public_context": {
    "round_index": 2,
    "turn_index": 7,
    "weather_name": "Emergency Shelter"
  }
}
```

Canonical `request_type` set (v1 human policy):

- `movement`
- `runaway_step_choice`
- `lap_reward`
- `draft_card`
- `final_character` (compat alias accepted in UI: `final_character_choice`)
- `trick_to_use`
- `purchase_tile`
- `hidden_trick_card`
- `mark_target`
- `coin_placement`
- `geo_bonus`
- `doctrine_relief`
- `active_flip`
- `specific_trick_reward`
- `burden_exchange`

## `decision_ack`

Payload:

```json
{
  "request_id": "req_turn7_move",
  "status": "accepted",
  "player_id": 1
}
```

`status` values:

- `accepted`
- `rejected`
- `stale`

## `error`

Payload:

```json
{
  "code": "STALE_REQUEST_ID",
  "category": "prompt",
  "message": "Decision request is stale.",
  "retryable": false,
  "request_id": "req_turn7_move"
}
```

## `heartbeat`

Payload:

```json
{
  "interval_ms": 5000,
  "backpressure": {
    "subscriber_count": 2,
    "drop_count": 4,
    "queue_size": 256
  }
}
```

Notes:
- `backpressure.drop_count` is cumulative per session since process start.
- Clients may surface this as transport health telemetry.

## Client to Server Messages

## `resume`

```json
{
  "type": "resume",
  "last_seq": 1041
}
```

## `decision`

```json
{
  "type": "decision",
  "request_id": "req_turn7_move",
  "player_id": 1,
  "choice_id": "roll",
  "choice_payload": {},
  "client_seq": 1045
}
```

Server-side validation:

- spectator decision submission => `UNAUTHORIZED_SEAT`
- seat decision with mismatched `player_id` => `PLAYER_MISMATCH`
- stale/missing prompt request => `decision_ack.status=stale`

## Timeout and Idempotency Rules

- `request_id` is unique per prompt.
- First valid decision wins.
- Duplicate decisions for accepted request return `decision_ack.status=stale`.
- Timeout triggers server fallback once.
- Fallback result is emitted as public events.
- Recommended fallback trace event payload:
  - `event_type=decision_timeout_fallback`
  - `request_id`, `player_id`, `fallback_policy`, `round_index`, `turn_index`
  - `fallback_execution` (`executed`)
  - `fallback_choice_id`

## Resume Rules

- Client must send `resume` after reconnect.
- If `last_seq` is within server buffer, replay starts at `last_seq + 1`.
- If too old, server returns error code `RESUME_GAP_TOO_OLD` and sends latest snapshot + current stream.

## Security Rules (v1)

- Host actions require `host_token`.
- Seat decision actions require seat `session_token`.
- Spectator token has read-only permissions.
- Token scope: single session.

## Error Code Catalog

| Code | HTTP/WS Context | Meaning | Retry |
|---|---|---|---|
| `SESSION_NOT_FOUND` | REST/WS | Invalid session id | no |
| `UNAUTHORIZED_SEAT` | REST/WS | Token does not match seat/session | no |
| `INVALID_STATE_TRANSITION` | REST | Illegal session lifecycle change | no |
| `PROMPT_TIMEOUT` | WS | Prompt expired before decision | no |
| `STALE_REQUEST_ID` | WS | Decision for outdated prompt | no |
| `PLAYER_MISMATCH` | WS | Decision player_id does not match authenticated seat | no |
| `DECISION_REJECTED` | WS | Invalid choice payload or seat mismatch | depends |
| `RUNTIME_EXECUTION_FAILED` | WS | Background engine execution failed | no |
| `RUNTIME_STALLED_WARN` | WS | Runtime inactivity watchdog warning | yes |
| `RESUME_GAP_TOO_OLD` | WS | Replay buffer cannot satisfy last_seq | yes |
| `INTERNAL_SERVER_ERROR` | REST/WS | Unexpected server fault | yes |

## API Change Management

For every API change:

1. Update this API spec.
2. Update interface spec.
3. Update shared runtime contract if event/prompt payload changed.
4. Add parser/integration tests for new fields.
5. Add migration note when changing existing field names.

## Parameter Manifest Extension (`Baseline Implemented`)

To reduce hardcoded frontend/backend coupling for game-rule changes, v1 now includes a baseline session-scoped parameter manifest.

Implemented baseline fields:

- `parameter_manifest.manifest_version`
- `parameter_manifest.manifest_hash`
- `parameter_manifest.source_fingerprints`
- `parameter_manifest.version`
- `parameter_manifest.board` (tile topology + tile metadata)
- `parameter_manifest.seats` (seat limits/model)
- `parameter_manifest.dice` (values, per-turn limits)
- `parameter_manifest.labels` (event/tile/prompt display labels)

Implemented delivery points:

- `POST /sessions` response (`data.parameter_manifest`)
- `GET /sessions/{id}` response (`data.parameter_manifest`)
- `POST /sessions/{id}/start` response (`data.parameter_manifest`)
- stream event `event_type=parameter_manifest` emitted on session start

Remaining hardening:

- broaden manifest contract coverage beyond current reconnect + baseline Playwright E2E fixtures
- expand manifest variation matrix (seat/topology/economy/dice) in browser E2E

Client runtime rule:

- if server emits a different `manifest_hash` than currently hydrated client state,
  client must discard topology/label projection caches and rehydrate from the new manifest.

Reference plan:

- `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`

Verification reference:

- `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`
