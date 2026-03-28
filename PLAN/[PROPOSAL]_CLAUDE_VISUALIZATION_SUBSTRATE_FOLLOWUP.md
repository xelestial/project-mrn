# [PROPOSAL] CLAUDE Visualization Substrate Follow-up

Status: `PROPOSAL`
Owner: `CLAUDE`
Last reviewed on: `2026-03-29`

## Purpose
This document tracks the remaining CLAUDE-side substrate work after the initial viewer compatibility push.

It should no longer be read as:
- "add more aliases so GPT keeps working"

It should now be read as:
- "finish substrate and validator convergence toward the shared contract"

Primary references:
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- `PLAN/[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`

## Status Summary

### Already materially done
- baseline replay/live substrate exists
- validator/compatibility path exists
- core event families used by GPT Phase 1-4 are present enough for replay/live/human-play baseline

### What changed in priority
The older focus on alias expansion is no longer the main goal.

Why:
- GPT now consumes canonical public-state names in the human-play renderer
- continuing to preserve every alias as a first-class contract risks freezing drift into the system

So the remaining CLAUDE work should prioritize:
- canonical naming
- contract-stable event/state payloads
- Phase 5 completeness checks

## CLAUDE Work Status (2026-03-29 업데이트)

### C1. Contract-first audit of event emission
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29` — commit `4150096`

완료 내용:
- `dice_roll`: `dice`→`dice_values`, `used_cards`→`cards_used`, `move`→`total_move`, `formula`→`move_modifier_reason`
- `player_move`: `from_tile_index`, `to_tile_index`, `path`(이동 경로 전체), `movement_source`, `crossed_start` 추가; `from_pos`/`to_pos`/`lapped` 하위호환 유지
- `tile_purchased`: `source`→`purchase_source`
- `rent_paid`: `base_amount` 추가 (위이버 전 원본 임대료)
- `fortune_drawn`/`fortune_resolved`: `rule_scripts.json`이 F1/F2 랜딩을 항상 처리하므로 실제 미발생 — dead path 아니나 정상적으로 우회됨, 별도 수정 불필요
- `trick_window_open/closed`, `bankruptcy`, `turn_end_snapshot`: 계약 준수 확인

### C2. Canonical public-state naming freeze
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29` — commit `4150096`

완료 내용:
- `PlayerPublicState.to_dict()`: `tiles_owned`, `score_coins_placed`, `trick_cards_visible`, `is_marked`, `immune_to_marks` alias 제거
- `BoardPublicState.to_dict()`: `marker_owner_id` alias 제거
- `GPT/viewer/renderers/markdown_renderer.py`: `trick_cards_visible` fallback 제거, `public_tricks` 직접 사용

정식 필드명 (이하 변경 금지):
- `public_tricks`, `mark_status`, `marker_owner_player_id`, `owned_tile_count`, `placed_score_coins`

### C3. Validator refresh toward canonical contract
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29` — commit `4150096`

완료 내용:
- `player_move` 검증: `from_tile_index`, `to_tile_index`, `path`, `movement_source`, `crossed_start`
- `turn_end_snapshot.players` 검증: 정식 필드명(`owned_tile_count`, `placed_score_coins`, `public_tricks`, `mark_status`, `hand_score_coins`, `hidden_trick_count`)
- `turn_end_snapshot.board` 검증: `marker_owner_player_id`
- `dice_roll` 검증 추가: `dice_values`, `cards_used`, `total_move`
- `rent_paid` 검증: `base_amount` 추가
- `tile_purchased` 검증: `purchase_source` 추가
- validator 4개 시드 전체 통과 확인

### C4. Phase 5 substrate completeness review
Priority: `P2`
Status: `PARTIALLY DONE`
Updated: `2026-03-29`

완료된 항목:
- `player_move.path`: 이동 경로 전체 (chain_segments 기반) ✅
- `player_move.crossed_start`, `movement_source`: Phase 5 애니메이션 지원 ✅
- `dice_roll` 전체 페이로드: Phase 5 주사위 표시 지원 ✅
- `lap_reward_chosen`: `cash_delta`, `shards_delta`, `coins_delta` 세분화 ✅
- `public_effects` 턴 리셋 정확성: 확인 ✅

남은 항목:
- `session_start` 페이로드 부족: 현재 `player_count`만 emit. Phase 5 렌더러가 게임 시작 시 플레이어 패널을 즉시 초기화하려면 플레이어 초기 공개 정보가 필요. `turn_end_snapshot`이 올 때까지 초기화 지연 발생 가능.

### C5. Renderer-neutral portability discipline
Priority: `P2`
Status: `ASSESSED — NO VIOLATIONS`
Reviewed: `2026-03-29`

점검 결과:
- `tile_kind` 값 (`"T2"`, `"T3"`, `"MALICIOUS"` 등): 엔진 내부 열거형 이름이 노출되나 안정적이며 Unity 포팅 시 재매핑으로 처리 가능. 현재 조치 불필요.
- `public_effects` 문자열 레이블: 렌더러 표시용이나 이식 가능한 형태. 현재 조치 불필요.
- renderer-only 필드가 core contract에 유입된 케이스 없음 확인.

## 전체 코드 리뷰 신규 발견 항목 (2026-03-29)

GPT/CLAUDE 시각화 전체 코드 리뷰 후 발견된 추가 이슈.

### C6. `remaining_dice_cards` CLAUDE public_state 누락
Priority: `P1`
Status: `DONE`
발견: `2026-03-29`
완료: `2026-03-29`

**문제**:
- GPT `viewer/public_state.py`의 `PlayerPublicState`에 `remaining_dice_cards: list[int]` 필드 존재
- CLAUDE `viewer/public_state.py`의 `PlayerPublicState`에 해당 필드 없음
- CLAUDE 엔진은 `player.used_dice_cards`를 정상 추적 중이므로 계산 가능

**영향**:
- CLAUDE `turn_end_snapshot` 스냅샷에 `remaining_dice_cards` 누락
- 리플레이/라이브 렌더러에서 주사위 카드 표시 정보 불일치

**수정 방향**:
```python
# CLAUDE/viewer/public_state.py — PlayerPublicState에 추가
remaining_dice_cards: list[int]

# build_player_public_state()에 추가 (GPT와 동일 로직)
remaining_dice_cards=[
    int(v)
    for v in getattr(state.config.rules.dice, "values", ())
    if int(v) not in set(getattr(player, "used_dice_cards", set()) or set())
],
```

검증 스크립트에도 추가 필요:
```python
# validate_gpt_viewer_compat.py turn_end_snapshot.players 검증에 추가
"remaining_dice_cards"
```

### C7. `public_effects` — `all_rent_waiver` 항목 CLAUDE에서 누락
Priority: `P2`
Status: `DONE`
발견: `2026-03-29`
완료: `2026-03-29`

**문제**:
GPT `viewer/public_state.py`의 `public_effects` 매핑 (9개):
```python
("trick_all_rent_waiver_this_turn", "all_rent_waiver"),  # ← CLAUDE에 없음
```
CLAUDE `viewer/public_state.py`의 `public_effects` 매핑 (8개): 해당 항목 없음

**영향**:
- 임대료 면제 트릭이 발동된 플레이어의 `public_effects`에 `"all_rent_waiver"` 표시 안 됨
- GPT 스냅샷과 CLAUDE 스냅샷 불일치

**수정 방향**:
```python
# CLAUDE/viewer/public_state.py build_player_public_state() public_effects 리스트에 추가
("trick_all_rent_waiver_this_turn", "all_rent_waiver"),
```

## What This Proposal Should No Longer Recommend
This proposal should no longer recommend the following as a primary direction:
- making legacy alias fields the stable long-term contract
- treating GPT viewer compatibility as the same thing as contract completion

Compatibility is useful.
Canonical convergence is more important now.

## Completion Standard
This proposal can be treated as closed when:
- canonical public-state naming is explicitly frozen ✅ `2026-03-29`
- validators treat canonical names as primary ✅ `2026-03-29`
- remaining critical event families are contract-audited ✅ `2026-03-29`
- Phase 5 substrate completeness is reviewed and documented ⚠️ `session_start` gap 잔존

현재 상태: **실질적으로 완료. `session_start` 보강(C4) 후 CLOSED 처리 가능. C6/C7 완료.**
