# CLAUDE Visual Game — Engine Substrate Plan
## 버전: 1.1 | 날짜: 2026-03-28 | 상태: [Phase 1 Complete — Phase 2 Ready]

---

## 역할 분담

이 플랜은 **CLAUDE 구현체가 소유하는 하위 계층**만 다룬다.

| 계층 | 소유 | 문서 |
|------|------|------|
| 상위 아키텍처 (Projection, Renderer, Session, Adapter 계층 설계) | GPT | `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md` |
| **하위 substrate (event 공급, board 상태, engine 스냅샷)** | **CLAUDE** | **이 문서** |

```
GPT 계층
  RuntimeSession / PublicGameProjection / Renderer / DecisionAdapter
  ───────────────────── 계약 경계 ─────────────────────
CLAUDE 계층  ← 이 플랜의 범위
  structured event stream  (engine.py → _log())
  BoardPublicState         (board_layout.json + tile_owner + tile_coins)
  PlayerPublicState        (GameState.players → public fields)
  MovementTrace            (path segments, dice values)
  ───────────────────── 진실의 원천 ─────────────────────
  engine.py  (GameState mutation authority)
```

---

## Authoritative Source 정책

| 소스 | 용도 | 우선순위 |
|------|------|----------|
| `engine.py` GameState (live) | Phase 4+ 라이브 플레이 | 1 |
| `engine.py` structured event stream (`enable_logging=True`) | Phase 1–3 리플레이 | 2 |
| `games.jsonl` summary 필드 | 집계 통계 전용 | 3 |
| `/result/*.md` | 사람이 읽는 리뷰 산출물 — **replay와 무관** | — |

> `/result`는 계속 리뷰 산출물 전용이다. replay 재구성의 입력으로 쓰지 않는다.

---

## 현재 Event Stream 상태 진단

`enable_logging=True` 시 기록되는 이벤트 중 **replay/시각화에 충분한 것**:

| 이벤트 | 상태 | 포함 정보 |
|--------|------|-----------|
| `initial_active_faces` | ✅ | 카드별 초기 활성 캐릭터 |
| `initial_public_tricks` | ✅ | 전원 공개 잔꾀 패 |
| `weather_round` | ✅ | 날씨 카드 + 효과 |
| `draft_pick` | ✅ | 플레이어별 드래프트 선택 |
| `final_character_choice` | ✅ | 최종 캐릭터 확정 |
| `turn_start` | ✅ | 플레이어, 캐릭터 |
| `mark_queued` | ✅ | source, target, payload |
| `mark_target_none/missing` | ✅ | 지목 실패 사유 |
| `forced_move` | ✅ | start_pos, end_pos |
| `trick_used` | ✅ | 카드, resolution |
| `baksu_transfer` | ✅ | 짐 이전 상세 |
| `fortune_cleanup_before/after` | ✅ | 정산 운수 |
| `trick_supply` | ✅ | F 임계값, 공급 상세 |

**replay/시각화에 필요하나 현재 누락된 것** (이 플랜의 구현 대상):

| 누락 이벤트 | 관련 시각화 | 심각도 |
|-------------|-------------|--------|
| `dice_roll` | 주사위 결과, 사용 카드 | 🔴 |
| `player_move` (path 포함) | 이동 애니메이션, 경로 | 🔴 |
| `rent_paid` | 렌트 지불 패널 | 🔴 |
| `tile_purchased` | 타일 소유주 변경 | 🔴 |
| `f_value_change` | F 게이지 델타 | 🔴 |
| `lap_reward_chosen` | 랩 보상 선택 결과 | 🟡 |
| `fortune_drawn` | 운수 카드 드로우 | 🟡 |
| `mark_resolved` | 지목 성공/실패 결과 | 🟡 |
| `marker_transferred` | 징표 이동 | 🟡 |
| `turn_end_snapshot` | 턴 종료 시 전체 public 상태 스냅샷 | 🟡 |
| `trick_instant_prompt` | 잔꾀 즉시 사용 창 (Phase 4 전용) | 🟢 |

---

## 공급할 데이터 계약 (CLAUDE → GPT 경계)

GPT 계층이 소비할 수 있도록 CLAUDE가 공급하는 타입들.
타입 정의는 CLAUDE 코드베이스에 위치한다.

### StructuredEvent (공통 래퍼)

```python
# 모든 _log() 행의 공통 필드
{
  "event": str,               # 이벤트 식별자
  "round_index": int,         # 라운드 (1-indexed)
  "turn_index": int,          # 누적 턴 수
  "acting_player": int | None # 1-indexed player id, 없으면 None
}
```

### MovementTrace

```python
{
  "event": "player_move",
  "player": int,              # 1-indexed
  "from_pos": int,            # 출발 타일 index (0-39)
  "to_pos": int,              # 도착 타일 index
  "path": list[int],          # 경유 타일 전체 시퀀스 (from_pos 포함, to_pos 포함)
  "lapped": bool,             # 랩(기점) 통과 여부
  "dice_values": list[int],   # 사용한 주사위 값 목록
  "cards_used": list[int],    # 사용한 카드 값 목록
  "move_cause": str           # "normal" | "trick_boost" | "extra_die"
}
```

### DiceRollEvent

```python
{
  "event": "dice_roll",
  "player": int,
  "dice_values": list[int],   # 이번 굴림 결과
  "total": int,
  "cards_available": list[int],  # 사용 가능했던 카드 값
  "cards_used": list[int],
  "trick_delta": int          # 잔꾀에 의한 가감 (+/-)
}
```

### RentPaidEvent

```python
{
  "event": "rent_paid",
  "payer": int,               # 1-indexed
  "owner": int,               # 1-indexed
  "tile_index": int,
  "base_amount": int,
  "final_amount": int,        # 할인/배율 적용 후
  "modifiers": list[str]      # 예: ["halved_weather", "double_global"]
}
```

### TilePurchasedEvent

```python
{
  "event": "tile_purchased",
  "player": int,
  "tile_index": int,
  "cost": int,
  "kind": str,                # "T2" | "T3" | "MALICIOUS"
  "source": str               # "landing" | "adjacent" | "trick"
}
```

### FValueChangeEvent

```python
{
  "event": "f_value_change",
  "before": float,
  "after": float,
  "delta": float,
  "reason": str,              # "f1_landing" | "f2_landing" | "effect" | ...
  "next_supply_threshold": int
}
```

### LapRewardChosenEvent

```python
{
  "event": "lap_reward_chosen",
  "player": int,
  "choice": str,              # "cash" | "coins" | "shards"
  "amount": int,
  "pool_remaining": dict      # {"cash": n, "coins": n, "shards": n}
}
```

### FortuneDrawnEvent

```python
{
  "event": "fortune_drawn",
  "player": int,
  "card_name": str,
  "card_effect_summary": str  # 공개 표시용 효과 요약
}
```

### MarkResolvedEvent

```python
{
  "event": "mark_resolved",
  "source": int,
  "target": int,
  "success": bool,
  "effect_type": str,         # "bandit_tax" | "hunter_pull" | "baksu_transfer" | ...
  "outcome_summary": str
}
```

### MarkerTransferredEvent

```python
{
  "event": "marker_transferred",
  "from_player": int,
  "to_player": int,
  "reason": str               # "round_end" | "character_effect"
}
```

### TurnEndSnapshotEvent

```python
{
  "event": "turn_end_snapshot",
  "player": int,
  "f_value": float,
  "marker_owner": int,
  # PlayerPublicState 전원
  "players": list[PlayerPublicState],
  # BoardPublicState (40타일 전체)
  "board": BoardPublicState
}
```

### PlayerPublicState (스냅샷 내 사용)

```python
{
  "player_id": int,           # 1-indexed
  "character": str,
  "position": int,            # 0-39
  "cash": int,
  "shards": int,
  "hand_coins": int,
  "score_coins_placed": int,
  "tiles_owned": int,
  "alive": bool,
  "public_tricks": list[str],
  "hidden_trick_count": int,
  "pending_mark": bool,       # 지목 대기 여부
  "is_mark_source": bool      # 지목 실행 여부
}
```

### BoardPublicState (스냅샷 내 사용)

```python
{
  "tiles": list[TilePublicState]  # index 0-39 순서
}

# TilePublicState
{
  "index": int,
  "kind": str,                # "F1" | "F2" | "S" | "T2" | "T3" | "MALICIOUS"
  "block_id": int,
  "zone_color": str | None,
  "purchase_cost": int | None,
  "rent_cost": int | None,
  "owner_id": int | None,     # 1-indexed, None이면 미소유
  "score_coins": int,
  "pawns": list[int]          # 현재 이 타일에 있는 플레이어 id (1-indexed)
}
```

---

## Phase 계획

### Phase 1-S (Substrate): Engine Event Stream 강화 ✅ COMPLETE

**목표**: `enable_logging=True` 실행 시 완전한 replay-grade event stream 생성.

**대상 파일**: `CLAUDE/engine.py`, `CLAUDE/effect_handlers.py`, `CLAUDE/viewer/`
**원칙**: 기존 `_log()` 호출 패턴 유지. 게임 로직 불변. enable_logging guard 준수.

**완료**: 2026-03-28 — PR #14 (CLAUDE-MAIN → main) — 20종 이벤트 구현

#### S-T1. 이동 관련 이벤트 추가
- `dice_roll` — `_resolve_move()` 진입 전 굴림 결과 로깅
- `player_move` — `_resolve_move()` 완료 후 path 포함 로깅
- path 계산: `from_pos`에서 `total` 만큼 전진하는 경유 타일 배열

#### S-T2. 경제 이벤트 추가
- `rent_paid` — `_pay_or_bankrupt()` 렌트 경로에서 로깅
- `tile_purchased` — `handle_unowned_landing` / `_handle_purchase` 완료 후 로깅
- `f_value_change` — F값 변경 직후 로깅 (기존 코드 내 변경 지점 확인 필요)

#### S-T3. 게임 흐름 이벤트 추가
- `lap_reward_chosen` — `handle_lap_reward` 완료 후 로깅
- `fortune_drawn` — 운수 카드 드로우 시 로깅
- `mark_resolved` — `_resolve_pending_marks()` 각 mark 처리 완료 후 로깅
- `marker_transferred` — `_resolve_marker_flip()` 완료 후 로깅

#### S-T4. 스냅샷 이벤트 추가
- `turn_end_snapshot` — `_take_turn()` 완료 직후
- `PlayerPublicState` / `BoardPublicState` 직렬화 헬퍼 메서드 추가

### Phase 1-V (Validation): 샘플 로그 생성 및 검증 ✅ COMPLETE

**목표**: S 태스크 완료 후 full 로그로 1게임을 실행하여 누락 없는지 확인.

```bash
python simulate_with_logs.py --log-level full --games 1 --seed 42
```

검증 기준:
- 모든 플레이어 이동에 `dice_roll` + `player_move` 쌍 존재
- 모든 렌트 지불에 `rent_paid` 존재
- 모든 타일 구매에 `tile_purchased` 존재
- 매 턴 종료 시 `turn_end_snapshot` 존재
- `turn_end_snapshot`의 player 상태가 다음 `turn_start`의 상태와 일치

**완료**: 2026-03-28 — `CLAUDE/validate_vis_stream.py` — seed 42/137/999 전부 통과

### Phase 2 (Replay Viewer)

GPT 계층이 Phase 1-S/V 완료 후 `ReplayProjection`을 구현한다.
CLAUDE 책임: structured event stream을 안정적으로 공급하는 것.

### Phase 3 (Live Spectator)

CLAUDE 엔진은 `enable_logging=True`로 실행되며 실시간 event stream을 파일 또는 queue에 append.
GPT 계층이 해당 stream을 polling 또는 WebSocket으로 소비.

### Phase 4 (Human Play Runtime)

GPT 계층의 `RuntimePrompt`에 대응하는 CLAUDE 엔진 변경:
- `GameEngine`에 `decision_provider: DecisionProvider` 인터페이스 주입
- 기존 `policy.choose_*()` 호출을 `decision_provider.request()` 로 통일
- `AiDecisionProvider` (기존 정책 시스템 래핑)
- `HumanDecisionProvider` (WebSocket/queue 대기)

> **엔진 로직 불변 원칙 유지**: 결정 요청 방식만 추상화, 게임 규칙 코드 미수정.

---

## 파일 구조 (CLAUDE 담당)

```
CLAUDE/
├── engine.py                  ← S-T1~T4 이벤트 추가 (기존 파일 수정)
├── viewer/                    ← NEW: substrate 공급 모듈
│   ├── __init__.py
│   ├── public_state.py        ← PlayerPublicState, BoardPublicState, TilePublicState 타입 정의
│   ├── snapshot_builder.py    ← GameState → TurnEndSnapshotEvent 변환
│   └── event_schema.py        ← 모든 structured event 타입 상수/validator
└── (Phase 4)
    └── decision_provider.py   ← DecisionProvider 인터페이스 + AiDecisionProvider
```

GPT 계층 (`GPT/viewer/` 등)은 위 `viewer/` 모듈의 스키마를 import 또는 JSON spec으로 참조.

---

## 불변 규칙

1. `engine.py` 게임 로직 불변 — `_log()` 호출 추가만 허용
2. `/result/*.md`는 replay 재구성 입력으로 사용 금지
3. `games.jsonl` summary 필드는 집계 통계 전용
4. `BoardPublicState` / `PlayerPublicState`는 공개 정보만 포함 — 히든 잔꾀 내용 등 비공개 정보 제외
5. GPT 계층은 engine 내부 (`GameState`, `PlayerState`)를 직접 import 금지 — substrate 타입(`viewer/`)만 사용
