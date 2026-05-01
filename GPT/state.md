# state.py

게임 상태 및 플레이어 상태 정의 문서.

## 2026-04-29 Redis checkpoint note
- `GameState.to_checkpoint_payload()` exports the canonical deterministic engine state for Redis storage.
- `GameState.from_checkpoint_payload(config, payload)` rebuilds board, player, deck, discard, weather, active-card, round, and turn fields from that payload.
- Board runtime state is part of the checkpoint, not a projection cache: each `TileState` serializes kind, block/zone metadata, purchase/rent values, owner, and score coins.
- Card runtime state is part of the checkpoint: fortune, trick, and weather draw piles preserve order; discard piles preserve graveyard order; player trick hands preserve card identity and hidden-card identity.
- Redis recovery uses this payload as the authoritative state shape; frontend view state remains a projection, not the source of truth.
- Prompt continuation metadata is part of the canonical checkpoint: `prompt_sequence`, `pending_prompt_request_id`, `pending_prompt_type`, `pending_prompt_player_id`, and `pending_prompt_instance_id`.
- Action continuation metadata is also checkpointed through `pending_actions`. Each entry is a serializable `ActionEnvelope`, not a Python callable, so later Redis recovery can resume queued movement/arrival steps without depending on process memory.
- Scheduled continuation metadata is checkpointed through `scheduled_actions`. These are also `ActionEnvelope` records, but they include a target player and phase such as `turn_start`; the engine materializes matching scheduled actions into `pending_actions` when that player/phase becomes current.
- `pending_action_log` carries the in-progress turn-log aggregate while movement and arrival are split across multiple queued actions.
- `pending_turn_completion` carries the small deferred turn-finalization envelope while normal turn movement is split into queued `apply_move -> resolve_arrival` transitions. Redis recovery uses it to emit the turn-end snapshot and advance the turn cursor only after queued movement work is finished.
- `pending_actions` may also carry phase-continuation envelopes such as `continue_after_trick_phase`. These are queued after trick-generated movement or landing actions so the same turn resumes at the correct phase instead of falling back to turn-start/trick selection after the action queue drains.

## 현재 구조
- `GameState.create()`는 `BoardConfig.build_tile_metadata()` 결과를 바탕으로 `TileState` 목록을 만든다.
- `TileState`는 정적 메타데이터와 런타임 갱신값을 함께 가진다.

## TileState 주요 필드
- `index`
- `kind`
- `block_id`
- `zone_color`
- `purchase_cost`
- `rent_cost`
- `owner_id`
- `score_coins`

## 호환성
- 기존 엔진/AI가 쓰던 `state.board[pos]`, `state.tile_owner[pos]`, `state.tile_coins[pos]` 접근은 view 객체로 유지한다.
- 따라서 내부 단일 진실원은 `state.tiles`지만, 기존 코드와의 호환도 보장한다.

## 메타데이터 기반 질의
- `tile_at(index)`
- `tile_positions(...)`
- `first_tile_position(...)`
- `block_tile_positions(block_id, land_only=...)`
- `adjacent_land_positions(pos)`

이 helpers를 써서 테스트/로직이 절대 좌표에 덜 의존하도록 한다.


## Rule injection interaction
`GameState.create()` still builds runtime state from `GameConfig`, but starting hand coins now come from `config.rules.token.starting_hand_coins`.


## 0.7.60 note
Initial player cash and shards are now sourced from `config.rules.economy` and `config.rules.resources` before legacy mirrors are populated.


### 0.7.61 tile runtime metadata
`TileState` now carries `economy_profile` in addition to resolved purchase/rent values so runtime logic can preserve structural board metadata and still read injected rules.

- `PlayerState.team_id`: 팀전 모드 확장을 위한 선택 필드. 기본 자유대전에서는 `None`이며, 교리 연구관/감독관의 짐 제거 대상 범위를 결정할 때만 사용된다.

- `PlayerState.team_id`: 팀전 확장을 위한 선택 필드. `None`이면 기본 자유대전으로 간주한다.
