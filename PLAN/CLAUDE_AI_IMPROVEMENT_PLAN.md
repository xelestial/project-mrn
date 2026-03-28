# CLAUDE AI Improvement Plan

Status: `ACTIVE`
Owner: `CLAUDE`
작성일: `2026-03-29`

## Goal

CLAUDE의 `HeuristicPolicy`를 독자적으로 개선한다.

GPT의 Decision Pipeline 구조와 무관하게, CLAUDE는 자체 엔진·배틀 인프라·평가 도구를 이용해
전략 품질을 점진적으로 높인다.

---

## 현재 상태 진단

### 강점

| 영역 | 수준 | 근거 |
|------|------|------|
| 구매 결정 | High | 생존 가드·독점 가중치·청소 비용 통합 |
| 캐릭터 선택/드래프트 | Medium-High | 다차원 평가자, 프로파일별 가중치 |
| 랩 보상 | Medium-High | 완전 탐색, 캐릭터 보너스 통합 |
| 생존 모델링 | High | v3_claude 짐 카드 패널티, 예비금 플로어 정교화 |

### 약점 (개선 우선 대상)

| 영역 | 수준 | 문제 |
|------|------|------|
| 트릭 카드 사용 | Low | 정적 조회 테이블, 핸드 조합 분석 없음 |
| 이동 결정 | Medium | 착지 점수만 평가 — 다음 턴 리스크 미반영 |
| 코인 배치 | Low | 단순 그리디, 상대 경로 분석 없음 |
| 마크 타깃 | Medium | 현재 위협 점수만 사용, 포워드 모델링 없음 |
| 적응적 프로파일링 | 없음 | 게임 상황과 무관하게 고정 프로파일 사용 |

---

## 설계 원칙

1. **독립 개선**: GPT 파이프라인 구조 의존 금지. CLAUDE 엔진·`ai_policy.py`·`CLAUDE/policy/decision/` 내에서 자족적으로 완결.
2. **측정 우선**: 개선 전에 기준선 수립, 개선 후 수치 검증.
3. **프로파일 보존**: 기존 7개 프로파일 호환성 유지. 신규 프로파일은 추가 방식.
4. **점진적 통합**: 각 Phase를 독립 배틀 실험으로 검증 후 병합.
5. **순수 함수 지향**: 새 결정 로직은 `state`·`player` 인자만 받는 순수 함수로 작성 — 단위 테스트 가능.

---

## Phase 계획

---

## Phase 1. 평가 기반 수립

**목표**: 현재 AI 품질을 수치로 측정할 수 있는 기반 마련.

**이유**: 개선 여부를 수치 없이 판단하면 회귀 탐지가 불가능하다.

### 1-A. 결정별 품질 로깅

각 주요 결정에 `debug` 정보를 출력하는 패시브 계측기 추가.

```python
# 예시: movement 결정 시 상위 3개 후보 및 점수 기록
{
  "decision": "movement",
  "player": 2,
  "turn": 14,
  "top3": [
    {"move": 6, "land": 22, "score": 3.2, "reason": "T3_own_revisit+coin"},
    {"move": 5, "land": 21, "score": 2.1, "reason": "T2_purchase"},
    {"move": 4, "land": 20, "score": 1.8, "reason": "F2_shard"}
  ],
  "chosen": {"move": 6, "land": 22}
}
```

대상 결정: movement, purchase, trick_to_use, mark_target, coin_placement

### 1-B. 배틀 평가 스크립트

`CLAUDE/eval_ai_quality.py` 작성.

- 100시드 × 4인 배틀 실행
- 측정 지표:
  - 승률 (vs. v1, v2_balanced, v3_claude 자전전)
  - 생존 턴 수 평균
  - 파산 빈도
  - 결정 유형별 평균 점수

### 1-C. 기준선 수립

현재 프로파일별 100시드 배틀 결과를 `CLAUDE/eval_baselines/` 에 저장.
이후 Phase 결과와 비교.

**완료 기준**:
- `eval_ai_quality.py` 실행 시 지표 출력
- 기준선 데이터 파일 존재
- 주요 결정 debug 로그 확인 가능

---

## Phase 2. 트릭 카드 시스템 개선

**목표**: 정적 조회 테이블을 핸드·게임 상황 인식 평가로 교체.

**현재 문제**:
```python
# 현재: 카드 이름 → 고정 점수
TRICK_VALUES = {"성물 수집가": 1.8, "무료 증정": 1.6, ...}
```
- 핸드 구성 분석 없음 (짐 카드 2개 들고 공격 카드 쓰는 경우 발생)
- 게임 단계 미반영 (후반 독점 국면에서 초반 카드 가중치 그대로 사용)
- 시너지 하드코딩 (무료증정+중매꾼만 인식)

### 2-A. 핸드 위험도 계산

```python
def hand_burden_pressure(player) -> float:
    """현재 핸드의 짐 카드 비율 → 트릭 사용 억제 신호."""
    burdens = sum(1 for c in player.trick_hand if c.is_burden)
    total = len(player.trick_hand)
    return burdens / max(total, 1)
```

짐 카드 비율이 높을수록 공격 트릭 사용 억제 → 청소 우선.

### 2-B. 게임 단계 가중치

```python
def game_phase(state) -> str:
    """early / mid / late 구분."""
    turns = state.turn_index
    if turns < 12: return "early"
    if turns < 30: return "mid"
    return "late"
```

- early: 핸드 확장 카드 선호
- mid: 공격·시너지 카드 선호
- late: 즉시 점수 카드 선호, 짐 청소 최우선

### 2-C. 동적 시너지 탐지

캐릭터-카드 시너지를 hardcode 대신 테이블로 관리:

```python
CHAR_TRICK_SYNERGY = {
    "중매꾼": {"무료 증정": +2.0, "공매도": +1.5},
    "건설업자": {"무료 증정": +1.8, "구역 연쇄": +2.2},
    "객주": {"같은 칸 코인": +2.4},
    "탐관오리": {"인신매매": +1.6, "추방": +1.4},
}
```

### 2-D. 타이밍 가드

- 랩 직전 (3칸 이내): 비용 소모 트릭 사용 억제
- 마크 위험 상태: 방어 트릭 우선
- 파산 위협: 트릭 사용 전면 억제

**완료 기준**:
- 100시드 배틀에서 트릭 사용률 +15% 이상 향상
- 짐 카드 보유 중 공격 트릭 잘못 사용 빈도 -50%
- Phase 1 기준선 대비 승률 동등 이상

---

## Phase 3. 이동 결정 단기 예측 개선

**목표**: 착지 점수에 "다음 1턴 기대값" 추가.

**현재 문제**:
```python
score = _landing_score(pos) + _move_bonus(pos) + _survival_adjustment()
# 착지 직후 상황만 평가 — 다음 턴 리스크 미반영
```

### 3-A. 랜딩 후 기대 임대료 위험 계산

착지 후 상대가 내 위치에 돌아올 확률 추정:

```python
def post_landing_rent_risk(state, player, land_pos) -> float:
    """land_pos 소유 타일이 없거나 타인 소유일 때
    다음 1-2턴 내 내 위치에 상대 착지 가능성 × 예상 임대료."""
    risk = 0.0
    for opp in state.players:
        if not opp.alive or opp.player_id == player.player_id:
            continue
        dist = (land_pos - opp.position) % len(state.board)
        if 1 <= dist <= 8:  # 주사위 범위 내
            owner = state.tile_owner[land_pos]
            if owner is not None and owner != player.player_id:
                rent = engine._effective_rent(state, land_pos, player, owner)
                proximity_weight = 1.0 - (dist - 1) / 8
                risk += rent * proximity_weight
    return risk
```

착지 점수에서 차감.

### 3-B. 카드 소모 비용 모델링

주사위 카드 1장 소모 = "미래 이동 옵션 감소". 카드 사용 시 기회비용 패널티 추가:

```python
def card_opportunity_cost(player, cards_used: int) -> float:
    remaining = len([v for v in config.dice.values
                     if v not in player.used_dice_cards])
    if remaining <= 1:
        return 1.5 * cards_used  # 마지막 카드 — 높은 비용
    return 0.3 * cards_used
```

### 3-C. 독점 완성 기회 점수

1칸 차이로 독점 가능한 타일에 착지하는 경우 +보너스:

```python
def monopoly_near_completion_bonus(state, player, land_pos) -> float:
    block = state.block_ids[land_pos]
    owned = sum(1 for t in state.tiles
                if state.block_ids[t.index] == block
                and t.owner_id == player.player_id)
    total = sum(1 for t in state.tiles if state.block_ids[t.index] == block)
    if total - owned == 1:  # 독점 1칸 남음
        return 3.5
    return 0.0
```

**완료 기준**:
- 이동 결정 debug에서 risk/cost 항목 확인 가능
- 100시드 기준 파산 빈도 -10% 이상
- 승률 Phase 1 기준선 대비 동등 이상

---

## Phase 4. 코인 배치 개선

**목표**: 상대 경로 분석 기반 최적 배치.

**현재 문제**: 단순 그리디 — 빈 슬롯 많은 타일 우선.

### 4-A. 상대 방문 빈도 추정

```python
def expected_opponent_visits(state, player, tile_idx, horizon=5) -> float:
    """향후 horizon턴 내 타일에 상대 착지 기대 횟수."""
    count = 0.0
    board_len = len(state.board)
    for opp in state.players:
        if not opp.alive or opp.player_id == player.player_id:
            continue
        dist = (tile_idx - opp.position) % board_len
        if dist == 0:
            continue
        # 기본 이동 범위 [2, 12] 균등 분포 가정
        for roll in range(2, 13):
            if roll == dist % board_len:
                count += 1 / 11
    return count * horizon
```

상대 방문 기대 횟수 높은 타일에 코인 배치 우선.

### 4-B. 임대료 효율 가중치

```python
coin_value = tile.rent_cost * expected_visits - tile_tax_risk
```

단순 빈 슬롯 우선 → 임대료 × 방문 기대값 우선으로 교체.

**완료 기준**:
- 100시드 코인 수익률 +20% 이상
- 코인 배치 debug에 기대 방문 횟수 노출

---

## Phase 5. 적응형 프로파일 전환

**목표**: 게임 상황에 따라 런타임에 프로파일 전환.

**현재 문제**: 게임 시작 시 고정된 프로파일 사용 — 리딩 중 공격, 뒤처질 때 수비 불가.

### 5-A. 상황 분류기

```python
def game_situation(state, player) -> str:
    """현재 플레이어의 게임 상황 분류."""
    my_rank = sorted_rank(state, player)
    win_prob = estimate_win_probability(state, player)  # 간단한 휴리스틱

    if win_prob > 0.6:
        return "leading"        # 수성 → control 프로파일
    elif win_prob < 0.25:
        return "trailing"       # 추격 → aggressive 프로파일
    elif has_heavy_burden(player):
        return "survival"       # 생존 위기 → avoid_control
    else:
        return "balanced"       # 기본 → balanced
```

### 5-B. 상황별 프로파일 매핑

```python
SITUATION_PROFILE = {
    "leading": "heuristic_v2_control",
    "trailing": "heuristic_v2_aggressive",
    "survival": "heuristic_v2_avoid_control",
    "balanced": "heuristic_v2_balanced",
}
```

턴 시작마다 재평가 — 상황 변화 시 자동 전환.

### 5-C. 전환 이력 로깅

```python
{
  "event": "profile_switch",
  "turn": 18,
  "player": 3,
  "from": "balanced",
  "to": "aggressive",
  "reason": "trailing (win_prob=0.18)"
}
```

**완료 기준**:
- 100시드에서 프로파일 전환 이벤트 발생 확인
- 고정 프로파일 대비 trailing 상황 회복률 +10% 이상

---

## Phase 6. 마크 타깃 전략 개선

**목표**: 현재 위협 점수 → 포워드 리스크 모델링.

**현재 문제**: 현재 cash/shards 점수 + 캐릭터별 고정 프로파일만 사용.

### 6-A. 랩 임박 위협

```python
def lap_threat_bonus(state, target) -> float:
    """타깃이 n턴 내 랩 완주 가능성 × 기대 보상."""
    tiles_to_go = (len(state.board) - target.position) % len(state.board)
    if tiles_to_go <= 8:
        lap_reward_est = estimate_lap_reward(state, target)
        return lap_reward_est * (1.0 - tiles_to_go / 8)
    return 0.0
```

### 6-B. 독점 완성 차단

```python
def monopoly_block_value(state, target) -> float:
    """타깃이 독점 완성 1개 이내인 블록 수 × 블록 가치."""
    value = 0.0
    for block_id in unique_blocks(state):
        target_owned = count_owned_in_block(state, target, block_id)
        total = count_total_in_block(state, block_id)
        if total - target_owned == 1:
            value += estimate_block_rent_value(state, block_id)
    return value
```

### 6-C. 파산 강제 효율

마크 효과가 파산을 유발할 수 있는 타깃에 추가 보너스:

```python
def bankruptcy_induction_bonus(state, player, target) -> float:
    """마크 → 임대료 강제 → 파산 가능성."""
    if is_추노꾼(player):
        # 추노꾼: 타깃을 고임대료 타일로 강제 이동
        forced_rent = max_rent_in_path(state, target)
        if target.cash < forced_rent * 1.2:
            return 2.5
    return 0.0
```

**완료 기준**:
- 100시드 마크 효과 실현율 +15%
- 마크 타깃 debug에 lap_threat, monopoly_block, bankruptcy 항목 노출

---

## 수행 순서 및 의존성

```
Phase 1 (평가 기반)
    └── Phase 2 (트릭 개선)     ← 약점 최우선
    └── Phase 3 (이동 개선)     ← Phase 1 이후 병렬 가능
    └── Phase 4 (코인 개선)     ← Phase 1 이후 병렬 가능
Phase 2, 3, 4 완료
    └── Phase 5 (적응 프로파일) ← Phase 2-4 안정화 후
Phase 5 완료
    └── Phase 6 (마크 개선)     ← Phase 5 기반 위에서 완성도 높이기
```

---

## 파일 구조 계획

```
CLAUDE/
├── ai_policy.py                    # 기존 (수정)
├── eval_ai_quality.py              # Phase 1-A 신규
├── eval_baselines/                 # Phase 1-C 신규
│   ├── v1_baseline.json
│   └── v3_claude_baseline.json
├── policy/
│   └── decision/
│       ├── movement.py             # Phase 3 수정
│       ├── trick_usage.py          # Phase 2 수정 (신규 파일 가능)
│       ├── coin_placement.py       # Phase 4 수정
│       ├── mark_target.py          # Phase 6 수정
│       └── adaptive_profile.py    # Phase 5 신규
```

---

## 성공 기준 (전체)

| 지표 | 목표 |
|------|------|
| v3_claude vs. v1 승률 | +10%p 이상 향상 |
| 파산 빈도 | -15% 이상 감소 |
| 트릭 카드 효율 | 잘못된 사용 -50% |
| 적응 프로파일 전환 | trailing → 회복률 +10%p |
| 코인 수익률 | +20% 이상 향상 |

---

## 관련 문서

- `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md` — 아키텍처 참조
- `PLAN/[COMPLETE]_CLAUDE_MULTI_AGENT_BATTLE_PLAN.md` — 배틀 평가 인프라 참조
- `CLAUDE/ai_policy.py` — 현재 구현
- `CLAUDE/policy/decision/` — 결정 모듈
