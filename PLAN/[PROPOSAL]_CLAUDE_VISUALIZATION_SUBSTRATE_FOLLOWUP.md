# [PROPOSAL] CLAUDE Visualization Substrate Follow-up

**작성일**: 2026-03-29
**상태**: PROPOSAL
**대상 코드베이스**: CLAUDE
**출처**: GPT 시각화 코드 리뷰 (Phase 2–4) 및 CLAUDE Phase 2-S 완료 후

---

## 배경

CLAUDE Phase 2-S에서 GPT 뷰어 호환성 alias 필드를 추가 완료하였다.
이 문서는 리뷰 과정에서 발견된 CLAUDE substrate 측의 잔여 확인 항목 및 개선 사항을 기록한다.

---

## PR25 재점검 및 최종 의견

`origin/main`의 PR #25 반영 후 다시 점검했다.
아래 두 가지를 기준으로 현재 상태를 확인했다.

- `python CLAUDE\\validate_gpt_viewer_compat.py` → 통과
- `python GPT\\test_human_play.py` → 여전히 `[human-game] ERROR: 8` / `KeyError: 8` 발생, 그러나 테스트는 `ALL TESTS PASSED`로 끝남

최종 의견:

- `C-3`는 사실상 완료되었다.
  - `validate_gpt_viewer_compat.py`는 현재 `main`에서 확장된 커버리지를 포함하고, 검증도 통과한다.
- `C-1`은 더 이상 현재 우선순위의 활성 blocker로 보지 않는다.
  - 현재 구현에서는 `fortune_drawn` / `fortune_resolved` 경로가 rule-script 경로에 의해 사실상 우회된다는 점이 검증 스크립트에 명시되었다.
  - 규칙 구조가 바뀌지 않는 한, 지금 시점의 주된 문제는 아니다.
- `C-2`는 방향을 바꿔야 한다.
  - PR #25는 GPT viewer 호환을 위해 alias 중심 검증을 강화했지만,
    앞으로의 기준은 shared contract의 canonical 이름이어야 한다.
  - 즉 `marker_owner_id`, `tiles_owned`, `trick_cards_visible`, `is_marked`, `immune_to_marks`
    같은 viewer 호환 alias를 더 늘리는 것이 아니라,
    `marker_owner_player_id`, `owned_tile_count`, `public_tricks`, `mark_status`
    같은 canonical 이름으로 수렴해야 한다.

정리하면:

- 이 문서는 **Phase 2-S 호환성 follow-up 기록**으로는 유효하다.
- 그러나 이후 구현을 이 문서가 직접 끌고 가면 안 된다.
- 앞으로의 CLAUDE 측 남은 일은
  - alias 확장
  - viewer 맞춤 보정

  이 아니라,

  - shared contract canonical naming 수렴
  - substrate/event schema의 renderer-neutral 정리

  여야 한다.

---

## 확인 필요 항목

### C-1: fortune_drawn 이벤트 — 실제 발생 여부 미확인

**파일**: `CLAUDE/engine.py:1624`
**현황**:
```python
self._emit_vis("fortune_drawn", Phase.FORTUNE, player.player_id + 1, state,
               card_name=card.name, card_effect=card.effect)
```

테스트한 모든 시드(42, 137, 999, 7, 13)에서 `fortune_drawn` 이벤트가 관측되지 않았다.
`fortune_drawn`이 emit되는 경로(`_resolve_fortune_on_f_landing`)가 게임 진행 중 실제로
호출되는지 확인이 필요하다.

**확인 방법**:
```python
# 더 많은 시드에서 fortune_drawn 발생 여부 점검
seeds_to_try = range(1, 200)
for s in seeds_to_try:
    stream = run_seed(s)
    if any(e.event_type == "fortune_drawn" for e in stream.events):
        print(f"fortune_drawn found: seed={s}")
        break
```

**결과에 따른 조치**:
- 발생하는 시드가 있으면 → `validate_gpt_viewer_compat.py`에 검증 추가
- 전혀 발생하지 않으면 → 이벤트 경로가 dead code인지 엔진 점검

---

### C-2: marker_transferred — 조건부 emit 범위 검토

**파일**: `CLAUDE/effect_handlers.py:265`
**현황**:
```python
if previous_owner != state.marker_owner_id:
    engine._emit_vis("marker_transferred", ...)
```

징표(marker)가 이동하지 않은 경우(소유자 변경 없음) emit하지 않는 것은 정상이다.
그러나 GPT 뷰어는 `marker_transferred` 이벤트 없이도 `turn_end_snapshot.board.marker_owner_id`
필드로 현재 소유자를 파악한다.

**확인 항목**:
- `turn_end_snapshot.board.marker_owner_id` 값이 항상 최신 상태인지 확인
- 특히 게임 최초 턴 (초기 소유자 P1, 징표 이동 없음) 상태가 올바르게 표시되는지 확인

---

### C-3: validate_gpt_viewer_compat.py — 검증 커버리지 확장

**파일**: `CLAUDE/validate_gpt_viewer_compat.py`

현재 검증에서 아래 이벤트는 미확인:
- `fortune_drawn` (C-1 확인 후 추가)
- `fortune_resolved`
- `bankruptcy`
- `trick_window_open` / `trick_window_closed`

**수정 방향**:
```python
# 검증 항목 추가
if t == "fortune_drawn" and "fortune_drawn" not in found:
    found["fortune_drawn"] = True
    check_field(errors, t, ev, "card_name")

if t == "bankruptcy" and "bankruptcy" not in found:
    found["bankruptcy"] = True
    check_field(errors, t, ev, "player_id")
```

---

## 완료된 항목 (Phase 2-S)

아래 항목은 Phase 2-S에서 이미 수정 완료하였다. 참조용으로 기록한다.

주의:
- 아래 이름 중 일부는 `shared contract` 기준 canonical 이름이 아니라
  `GPT viewer` 호환을 위한 legacy alias이다.
- 이후 새 작업의 기준 이름은 `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`를 따른다.

| 항목 | 파일 | 수정 내용 |
|------|------|---------|
| player_move | engine.py | `+from_pos`, `+to_pos`, `+lapped` |
| rent_paid | effect_handlers.py | `+payer_player_id`, `+final_amount` |
| lap_reward_chosen | effect_handlers.py | `+amount` |
| weather_reveal | engine.py | `+weather_name` |
| game_end | engine.py | `+winner_player_id`, `+reason` |
| mark_resolved | engine.py | `+success`, `+target_player_id` |
| PlayerPublicState | viewer/public_state.py | `+tiles_owned`, `+trick_cards_visible`, `+is_marked`, `+immune_to_marks` |
| BoardPublicState | viewer/public_state.py | `+marker_owner_id` |

---

## 수정 우선 순위

| 순위 | ID | 난이도 | 영향 |
|------|-----|--------|------|
| 1 | canonical convergence | 중간 | shared contract와 viewer alias를 분리하고 canonical 이름으로 수렴 |
| 2 | C-2 재정의 | 낮음 | marker 관련 이름/의미를 contract 기준으로 정리 |
| 3 | C-1 보관 | 낮음 | fortune 경로는 현재 blocker가 아니라 기록성 확인 항목 |

---

## 관련 문서

- `PLAN/VISUALIZATION_GAME_PLAN.md` — CLAUDE substrate 원본 플랜
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` — 공유 계약
- `PLAN/[PROPOSAL]_GPT_VISUALIZATION_BUG_FIXES.md` — GPT 측 버그 수정 항목
- `CLAUDE/validate_gpt_viewer_compat.py` — GPT 뷰어 호환성 검증 스크립트
