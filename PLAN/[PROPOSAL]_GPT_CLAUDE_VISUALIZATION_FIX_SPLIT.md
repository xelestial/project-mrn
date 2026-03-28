# [PROPOSAL] GPT / CLAUDE Visualization Fix Split After PR22

Status: `PROPOSAL`
Reviewed against: `main`
Last reviewed on: `2026-03-29`

## Purpose
This document tracks the corrective visualization work that still matters on `main`.

It is not the top-level product plan.
It is the current split of:
- what GPT has already corrected
- what GPT still owns
- what CLAUDE still owns

Canonical references:
- product/runtime plan: `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- shared contract baseline: `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Current Main-Branch Read

### Confirmed complete enough
- Phase 1 visual substrate exists
- Phase 2 replay viewer exists
- Phase 3 live spectator exists
- Phase 4 baseline human-play loop exists

### Confirmed recently corrected by GPT
- human-play final-character crash
- Phase 4 false-positive test path
- `play_html.py` stale public-state field usage

### Confirmed still open
- prompt envelope still drifts from the shared contract
- plan/status documents still overstate or under-specify current `main`
- replay/renderer compatibility still has small contract alignment gaps

### Confirmed recently closed (CLAUDE)
- CLAUDE substrate legacy alias expansion: closed `2026-03-29`
- CLAUDE event payload canonical field names: closed `2026-03-29`
- CLAUDE public-state alias cleanup: closed `2026-03-29`
- CLAUDE validator canonical refresh: closed `2026-03-29`

## Ownership Rule

- GPT owns upper runtime correction:
  - prompt adapter
  - human-play flow
  - renderer behavior
  - application tests
  - plan/status document correction
- CLAUDE owns lower substrate correction:
  - event/schema stability
  - authoritative public-state naming
  - replay/live event completeness
  - renderer-neutral contract fidelity

Shared rule:
- no one should silently rename contract fields in implementation only
- contract changes must be reflected in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## GPT Status

### GPT work already closed

#### G1. Human-play final-character crash
Status: `DONE`

Closed by:
- `GPT/viewer/human_policy.py`
- `GPT/test_human_play.py`

Result:
- final-character choice now resolves to the engine-valid character identifier family
- Phase 4 no longer crashes from legal final-character input

#### G2. Renderer/public-state field drift in human play
Status: `DONE`

Closed by:
- `GPT/viewer/renderers/play_html.py`

Result:
- human-play renderer now consumes canonical public-state names
- stale fields such as `marker_owner_id`, `trick_cards_visible`, `tiles_owned`, `score_coins_placed` are no longer the active human-play dependency

#### G3. Phase 4 test trustworthiness
Status: `DONE`

Closed by:
- `GPT/viewer/live_server.py`
- `GPT/viewer/prompt_server.py`
- `GPT/test_human_play.py`

Result:
- background game-thread errors are surfaced through status
- Phase 4 regression path now fails when the runtime dies internally

### GPT work still open

#### G4. Normalize the prompt envelope at the GPT boundary
Priority: `P1`
Status: `OPEN`

What remains:
- stop growing ad-hoc prompt dicts in `GPT/viewer/human_policy.py`
- introduce one stable prompt adapter/envelope aligned to the shared contract

Minimum target:
- `request_type`
- `player_id`
- `legal_choices`
- `can_pass`
- `public_context`
- response values distinct from display labels

Why it still matters:
- current human-play works, but it is not yet contract-clean
- future prompt types will become brittle if this is not normalized now

#### G5. Correct plan/status documents to match `main`
Priority: `P1`
Status: `OPEN`

At minimum:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/PLAN_STATUS_INDEX.md`

What remains:
- Phase 4 status should reflect current baseline-stable state, not ambiguous completion claims
- plan docs should clearly separate:
  - completed substrate/replay/live/human-play baseline
  - remaining Phase 5 UI work
  - remaining contract-cleanup work

#### G6. Replay-side compatibility cleanup
Priority: `P2`
Status: `OPEN`

What remains:
- align replay projection / markdown/html renderers with current `main` contracts
- remove remaining small mismatches that are not Phase 4 blockers but still muddy the viewer stack

Primary area:
- replay renderer / projection compatibility, not human-play runtime

## CLAUDE Status

### CLAUDE work closed

#### C-legacy-alias-expansion
Status: `CLOSED`
Closed: `2026-03-29`

#### C1. Close substrate drift against the shared contract
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29` — commit `4150096`

Closed by:
- `CLAUDE/engine.py`: `dice_roll` / `player_move` / `tile_purchased` 필드명 정규화
- `CLAUDE/effect_handlers.py`: `rent_paid.base_amount`, `tile_purchased.purchase_source` 추가
- `player_move.path` (이동 경로 전체) 추가

#### C2. Freeze authoritative public-state naming
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29` — commit `4150096`

Closed by:
- `CLAUDE/viewer/public_state.py`: `PlayerPublicState.to_dict()` / `BoardPublicState.to_dict()` 에서 모든 legacy alias 제거
- `GPT/viewer/renderers/markdown_renderer.py`: `trick_cards_visible` fallback 제거

Frozen canonical names:
- `public_tricks`, `mark_status`, `marker_owner_player_id`, `owned_tile_count`, `placed_score_coins`

### CLAUDE work still open

#### C3. Verify Phase 5 substrate completeness
Priority: `P2`
Status: `PARTIALLY DONE`
Updated: `2026-03-29`

완료:
- `player_move.path`, `from_tile_index`, `to_tile_index`, `movement_source`, `crossed_start` ✅
- `dice_roll` 전체 페이로드 정규화 ✅
- `public_effects` 턴 리셋 정확성 확인 ✅

잔존:
- `session_start` 페이로드에 플레이어 초기 공개 정보 없음 — Phase 5 렌더러 즉시 초기화 불가

#### C4. Keep renderer-neutral transport discipline
Priority: `P2`
Status: `ASSESSED — NO VIOLATIONS`
Reviewed: `2026-03-29`

- `tile_kind` / `public_effects` 문자열: 이식 가능 형태 확인
- renderer-only 필드가 core contract에 유입된 케이스 없음

## Shared Coordination Items

### S1. Freeze prompt value semantics
Still required.

Need agreement on:
- what label the user sees
- what value the engine receives
- which identifier family is authoritative for characters, tiles, tricks, and players

### S2. Freeze seat / player-id semantics
Still required.

Need agreement on:
- 0-based internal seat vs 1-based public `player_id`
- whether `seat`, `player_id`, and rendered order are distinct concepts

### S3. Keep renderer out of rule reconstruction
Still required.

Renderer may format and visualize.
It should not invent missing rule meaning because substrate data is incomplete.

## Recommended Execution Order Now
1. GPT closes `G4` — prompt envelope normalization
2. GPT closes `G5` — plan/status docs ⚠️ (일부 완료, 세부 정렬 잔존)
3. ~~CLAUDE closes `C1` and `C2`~~ ✅ `2026-03-29` DONE
4. GPT closes `G6` — replay-side compatibility cleanup
5. CLAUDE closes `C3` — `session_start` payload 보강 (Phase 5 착수 전)
6. GPT and CLAUDE begin Phase 5 UI expansion on top of the cleaned contract

## Completion Standard
This proposal can be treated as closed when all of the following are true:
- human-play crash regression stays closed ✅
- Phase 4 tests remain trustworthy ✅
- prompt envelope is contract-normalized (GPT: G4 open)
- plan/status docs reflect actual `main` (GPT: G5 partially done)
- CLAUDE substrate follow-up uses canonical public-state names ✅ `2026-03-29`
- replay/live renderer stack no longer depends on contract drift (GPT: G6 open)
- Phase 5 substrate completeness confirmed (CLAUDE: C3 partially done)
