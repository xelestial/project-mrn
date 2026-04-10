# Online Game API Spec (REST + WebSocket)

Canonical document path for the current runtime API contract.

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-31`  
Parents:
- `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
- `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`

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
- `recovery_required` (session is `in_progress` but runtime task is missing after restart; requires recovery/abort decision)

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

Additive view-model channel:

- stream/replay payloads may include a renderer-agnostic `payload.view_state` object
- current first migrated slice is `payload.view_state.players`
- current additive slices are:
  - `view_state.players`
  - `view_state.active_slots`
  - `view_state.mark_target`
  - `view_state.reveals`
  - `view_state.board`
  - `view_state.prompt`
  - `view_state.hand_tray`
  - `view_state.turn_stage`
  - `view_state.scene`
- `view_state.players` currently contains:
  - `ordered_player_ids`
  - `marker_owner_player_id`
  - `marker_draft_direction`
- `view_state.players.items` may include canonical player-card fields such as:
  - `current_character_face`
  - `priority_slot`
  - `is_current_actor`
  - `is_marker_owner`
- `view_state.active_slots.items` contains canonical slot projections for the active-character strip
- `view_state.mark_target.candidates` contains canonical mark-target candidates derived from the same slot projection
- `view_state.reveals.items` contains canonical current-turn public reveal items in backend-owned order
  - fields currently include:
    - `seq`
    - `event_code`
    - `event_order`
    - `tone`
    - `focus_tile_index`
    - `is_interrupt`
- `view_state.board.last_move` contains the latest board movement projection:
  - `player_id`
  - `from_tile_index`
  - `to_tile_index`
  - `path_tile_indices`
- `view_state.board.tiles` contains canonical dynamic board-surface projection:
  - `tile_index`
  - `score_coin_count`
  - `owner_player_id`
  - `pawn_player_ids`
- `view_state.prompt.active` contains backend-owned active prompt projection when a live prompt exists
  - fields currently include:
    - `request_id`
    - `request_type`
    - `player_id`
    - `timeout_ms`
    - `choices`
    - `public_context`
    - `behavior`
    - `surface`
  - `behavior` may include:
    - `normalized_request_type`
    - `single_surface`
    - `auto_continue`
    - `chain_key`
    - `chain_item_count`
    - `current_item_deck_index`
  - `surface` contains backend-owned renderer-agnostic prompt-surface projection
    - common fields:
      - `kind`
      - `blocks_public_events`
    - `surface.lap_reward` may include:
      - `budget`
      - `cash_pool`
      - `shards_pool`
      - `coins_pool`
      - `cash_point_cost`
      - `shards_point_cost`
      - `coins_point_cost`
      - `options[]`
        - `choice_id`
        - `cash_units`
        - `shard_units`
        - `coin_units`
        - `spent_points`
    - `surface.burden_exchange_batch` may include:
      - `burden_card_count`
      - `current_f_value`
      - `supply_threshold`
      - `cards[]`
        - `deck_index`
        - `name`
        - `description`
        - `burden_cost`
        - `is_current_target`
    - `surface.mark_target` may include:
      - `actor_name`
      - `target_count`
      - `none_choice_id`
      - `candidates[]`
        - `choice_id`
        - `slot`
        - `player_id`
        - `name`
        - `label`
    - `surface.character_pick` may include:
      - `selection_count`
      - `options[]`
        - `choice_id`
        - `name`
        - `description`
    - `surface.purchase_tile` may include:
      - `tile_index`
      - `tile_label`
      - `tile_color`
      - `cost`
      - `cash_after_purchase`
      - `cash_gap`
      - `options[]`
        - `choice_id`
        - `title`
        - `description`
        - `tile_index`
        - `is_purchase`
    - `surface.trick_tile_target` may include:
      - `effect_name`
      - `tile_count`
      - `options[]`
        - `choice_id`
        - `tile_index`
        - `title`
        - `description`
    - `surface.coin_placement` may include:
      - `owned_tile_count`
      - `options[]`
        - `choice_id`
        - `tile_index`
        - `title`
        - `description`
    - `surface.movement` may include:
      - `roll_choice_id`
      - `card_pool[]`
      - `can_use_two_cards`
      - `card_choices[]`
        - `choice_id`
        - `cards[]`
        - `title`
        - `description`
    - `surface.hand_choice` may include:
      - `mode`
      - `pass_choice_id`
      - `cards[]`
        - `choice_id`
        - `deck_index`
        - `name`
        - `description`
        - `is_hidden`
        - `is_usable`
    - `surface.doctrine_relief` may include:
      - `candidate_count`
      - `options[]`
        - `choice_id`
        - `target_player_id`
        - `burden_count`
        - `title`
        - `description`
    - `surface.geo_bonus` may include:
      - `actor_name`
      - `options[]`
        - `choice_id`
        - `reward_kind`
        - `title`
        - `description`
    - `surface.specific_trick_reward` may include:
      - `reward_count`
      - `options[]`
        - `choice_id`
        - `deck_index`
        - `name`
        - `description`
    - `surface.pabal_dice_mode` may include:
      - `options[]`
        - `choice_id`
        - `dice_mode`
        - `title`
        - `description`
    - `surface.runaway_step` may include:
      - `bonus_choice_id`
      - `stay_choice_id`
      - `one_short_pos`
      - `bonus_target_pos`
      - `bonus_target_kind`
    - `surface.active_flip` may include:
      - `selection_count`
      - `finish_choice_id`
      - `options[]`
        - `choice_id`
        - `name`
        - `description`
- `view_state.prompt.last_feedback` may carry the latest prompt lifecycle result
  - fields currently include:
    - `request_id`
    - `status`
    - `reason`
  - current status values surfaced through the projection are:
    - `accepted`
    - `rejected`
    - `stale`
    - `timeout_fallback` on the raw backend side, though current web fallback helper only consumes `accepted/rejected/stale`
- `view_state.hand_tray.cards` contains the canonical current visible hand/burden tray for the stream consumer
  - fields currently include:
    - `key`
    - `name`
    - `description`
    - `deck_index`
    - `is_hidden`
    - `is_current_target`
- `view_state.turn_stage` contains backend-owned current turn/beat projection
  - fields currently include:
    - `turn_start_seq`
    - `actor_player_id`
    - `round_index`
    - `turn_index`
    - `character`
    - `weather_name`
    - `weather_effect`
    - `current_beat_kind`
    - `current_beat_event_code`
    - `current_beat_request_type`
    - `current_beat_seq`
    - `focus_tile_index`
    - `focus_tile_indices`
    - `prompt_request_type`
    - external-ai status fields mirrored from decision public context
    - actor resource fields mirrored from prompt public context
    - `progress_codes`
- `view_state.scene` contains backend-owned renderer-agnostic scene reduction for summary / theater / core-action surfaces
  - `view_state.scene.situation` currently includes:
    - `actor_player_id`
    - `round_index`
    - `turn_index`
    - `headline_seq`
    - `headline_message_type`
    - `headline_event_code`
    - `weather_name`
    - `weather_effect`
  - `view_state.scene.theater_feed` currently includes:
    - `seq`
    - `message_type`
    - `event_code`
    - `tone`
    - `lane`
    - `actor_player_id`
    - `round_index`
    - `turn_index`
  - `view_state.scene.core_action_feed` currently includes:
    - `seq`
    - `event_code`
    - `actor_player_id`
    - `round_index`
    - `turn_index`
  - `view_state.scene.timeline` currently includes:
    - `seq`
    - `message_type`
    - `event_code`
  - `view_state.scene.critical_alerts` currently includes:
    - `seq`
    - `message_type`
    - `event_code`
    - `severity`
- clients may consume `view_state` when present and fall back to raw event reduction when absent during migration

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
- may also include additive `view_state` data during selector migration

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

Additive migration note:

- prompts may also carry the same additive `view_state` object as stream events

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

- `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`

Verification reference:

- `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`
