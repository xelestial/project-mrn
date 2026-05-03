# [READY] CLAUDE Phase 1 Visualization Substrate — Complete

**날짜**: 2026-03-28
**작성**: CLAUDE
**대상**: GPT
**상태**: Phase 1-S + Phase 1-V 완료 — Phase 2 구현 가능

---

## 요약

CLAUDE 측 Phase 1 (Substrate + Validation)이 완료되었다.
GPT는 이제 `SHARED_VISUAL_RUNTIME_CONTRACT.md`에 정의된 이벤트 스트림을 소비하는
상위 계층 (`ReplayProjection`, `RuntimeSession`, `Renderer` 등)을 구현할 수 있다.

---

## 구현된 내용

### 신규 패키지: `CLAUDE/viewer/`

| 파일 | 내용 |
|------|------|
| `viewer/__init__.py` | 패키지 루트 |
| `viewer/events.py` | `VisEvent` dataclass, `Phase` 상수 |
| `viewer/stream.py` | `VisEventStream` — append-only, `to_jsonl()`, `summary()` |
| `viewer/public_state.py` | `PlayerPublicState`, `TilePublicState`, `BoardPublicState` + build_ 함수 |

### Engine 변경 (하위 호환)

```python
# 기존 사용법 — 변화 없음
engine = GameEngine(config, policy)

# 시각화 활성화
from viewer.stream import VisEventStream
stream = VisEventStream()
engine = GameEngine(config, policy, event_stream=stream)
engine.run()
stream.to_jsonl("replay.jsonl")  # 저장
events = stream.to_list()        # dict 목록
```

### 구현된 이벤트 (20종)

| event_type | public_phase | 발생 조건 |
|---|---|---|
| `session_start` | `session_start` | 게임 시작 1회 |
| `round_start` | `weather` | 라운드 시작마다 |
| `weather_reveal` | `weather` | 날씨 카드 공개 후 |
| `draft_pick` | `draft` | 각 드래프트 픽마다 |
| `final_character_choice` | `character_select` | 최종 캐릭터 확정마다 |
| `turn_start` | `turn_start` | 각 턴 시작 (skipped 포함) |
| `trick_window_open` | `trick_window` | 잔꾀 단계 시작 |
| `trick_window_closed` | `trick_window` | 잔꾀 단계 종료 |
| `dice_roll` | `movement` | 이동 결정 직후 |
| `player_move` | `movement` | 이동 완료 후 |
| `landing_resolved` | `landing` | 착지 처리 완료 후 |
| `rent_paid` | `landing` | 렌트 지불 시 |
| `tile_purchased` | `landing` | 타일 구매 시 |
| `fortune_drawn` | `fortune` | 운수 카드 드로우 시 |
| `fortune_resolved` | `fortune` | 운수 카드 효과 적용 후 |
| `mark_resolved` | `mark` | 지목 효과 처리 완료 후 |
| `marker_transferred` | `economy` | 징표 소유자 변경 시 |
| `lap_reward_chosen` | `lap_reward` | 랩 보상 선택 후 |
| `f_value_change` | `economy` | F값 변경마다 |
| `bankruptcy` | `economy` | 파산 처리 직전 |
| `turn_end_snapshot` | `turn_end` | 각 턴 종료 후 |
| `game_end` | `game_end` | 게임 종료 1회 |

---

## 공통 Envelope 필드 (모든 이벤트)

```python
{
  "event_type": str,          # snake_case
  "session_id": str,          # UUID4 — 게임당 1개
  "round_index": int,         # 1-indexed
  "turn_index": int,          # 1-indexed, 누적
  "step_index": int,          # 단조증가, deterministic sequence id
  "acting_player_id": int | None,  # 1-indexed, 세션/라운드 이벤트는 None
  "public_phase": str,        # Phase 상수
  # + 이벤트별 payload 필드 (flat merge)
}
```

---

## Public State 타입

`turn_end_snapshot` 및 `bankruptcy` payload에 포함되는 스냅샷 타입:

- `PlayerPublicState` — player_id, seat, display_name, alive, character, position, cash, shards, hand_score_coins, placed_score_coins, owned_tile_count, owned_tile_indices, public_tricks, hidden_trick_count, mark_status, pending_mark_source, public_effects, burden_summary
- `TilePublicState` — tile_index, tile_kind, block_id, zone_color, purchase_cost, rent_cost, owner_player_id, score_coin_count, pawn_player_ids
- `BoardPublicState` — tiles, f_value, marker_owner_player_id, round_index, turn_index

---

## 검증 결과

`CLAUDE/validate_vis_stream.py` — seed 42, 137, 999 전부 통과

- 모든 필수 envelope 필드 존재
- step_index 단조 증가
- session_id 일관성
- dice_roll ↔ player_move 쌍 일치
- turn_start ↔ turn_end_snapshot 쌍 일치
- session_start 첫 번째, game_end 마지막

---

## Phase 2 시작을 위한 GPT 측 준비사항

1. `VisEventStream.to_list()` 또는 `.to_jsonl()` 출력을 소비하는 `ReplayProjection` 구현
2. `PlayerPublicState` / `BoardPublicState` dict를 렌더링 상태로 변환하는 어댑터
3. `turn_end_snapshot` 이벤트를 기준점으로 상태 재구성
4. `session_id` + `step_index`를 replay 탐색 키로 활용

---

## 참고

- 계약 명세: `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- CLAUDE substrate 계획: `PLAN/VISUALIZATION_GAME_PLAN.md`
- 구현 PR: xelestial/project-mrn#14 (CLAUDE-MAIN → main)
