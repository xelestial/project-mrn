# BASEGAME COLLABORATION SPECIFICATION
## Claude / GPT 공동 개발 원칙 명세
### 버전: 0.3 | 날짜: 2026-03-27

---

## 0. 이 문서의 목적

Claude와 GPT가 같은 시뮬레이터 코드베이스(`Basegame v0.7.61+`)를 독립적으로 패치하면서도
- 서로의 변경이 충돌하지 않고
- 실험 중인 기능과 안정화된 기능이 명확히 구분되며
- 로그/분석 결과가 동일 포맷으로 비교 가능하고
- 버그 원인을 빠르게 추적할 수 있도록

**공통 계약**을 정의한다.

이 문서는 코드보다 우선한다. 코드가 이 문서와 충돌하면 코드를 고친다.

관련 문서:
- `ARCHITECTURE_REFACTOR_AGREED_SPEC_v1_0.md` — 최종 합의된 아키텍처 기준
- `ARCHITECTURE_IMPL_GUIDE.md` — 구현 예시 및 단계별 적용 가이드

---

## 1. 브랜치/버전 네이밍 규칙

### 1.1 정책(Policy) 식별자
```
heuristic_v3_{owner}_{stage}
```
- `owner`: `claude` 또는 `gpt`
- `stage`: `exp` (실험) | `stab` (안정화 진행중) | `rel` (릴리스)

예시:
- `heuristic_v3_claude_exp` — Claude 실험 중
- `heuristic_v3_gpt_stab`   — GPT 안정화 중
- `heuristic_v3_rel`        — 양측 합의된 릴리스 (owner 없음)

### 1.2 실험 디렉토리
```
exp_v3c_v{N}/    → Claude 실험 결과
exp_v3g_v{N}/    → GPT 실험 결과
exp_joint_v{N}/  → 공동 비교 실험 결과
```

### 1.3 패치 버전
- 단일 오너 패치: `v{N}_{owner}` (예: `v8_claude`, `v8_gpt`)
- 공동 머지: `v{N}_joint`
- 롤백: `v{N}_{owner}_rollback`

---

## 2. 공통 아키텍처 원칙

### 2.1 계층 분리 (변경 금지 경계)

```
[엔진 레이어]      engine.py, effect_handlers.py, event_system.py
      ↑ 원칙적으로 직접 수정하지 않음 (버그 수정 / 룰 정합성 수정 / 로깅·분석 필드 추가만 예외)
[규칙 레이어]      game_rules.py, ruleset.json, rule_scripts.json
      ↑ 룰 변경은 반드시 ruleset.json 또는 rule_scripts.json으로만
[정책 레이어]      ai_policy.py, survival_common.py, policy_*.py
      ← AI 패치의 주 작업 영역
[분석 레이어]      simulate_with_logs.py, stats_utils.py, log_pipeline.py
      ← 출력 포맷은 공통 스펙을 따라야 함
```

**원칙:**
- AI 정책 패치는 `ai_policy.py`, `survival_common.py`, `policy_groups.py`, `policy_mark_utils.py`만 수정한다.
- `engine.py` 수정은 버그 수정, 룰 정합성 수정, 로깅/분석 필드 추가에 한해 허용한다.
- 그 외 정책 실험 목적의 엔진 수정은 금지하며, 우선 `rule_scripts.json` 또는 `effect_handlers.py` 경로를 검토한다.
- `config.py`의 기본값 변경은 `ruleset.json`으로만.

### 2.2 공통 진입점 (실험 실행 표준)

모든 실험은 아래 커맨드 형식을 따른다:

```bash
python run_chunked_batch.py \
  --simulations 100 \
  --chunk-size 10 \
  --seed {SEED} \
  --output-dir {exp_dir} \
  --policy-mode arena \
  --player-character-policies \
    heuristic_v3_{owner},heuristic_v2_token_opt,heuristic_v2_control,heuristic_v2_balanced \
  --log-level summary
```

**아레나 슬롯 고정:**
```
플레이어 1: 테스트 대상 (v3_claude 또는 v3_gpt)
플레이어 2: heuristic_v2_token_opt   (대조군 고정)
플레이어 3: heuristic_v2_control     (대조군 고정)
플레이어 4: heuristic_v2_balanced    (대조군 고정)
```

이 슬롯 배정이 바뀌면 과거 실험과 승률 비교가 불가능해진다.

---

## 3. 공통 로그 스펙

### 3.1 게임 단위 필수 필드

모든 게임 결과에 다음 필드가 반드시 있어야 한다:

```python
{
  "version": str,          # 엔진 버전 (예: "0.7.61")
  "run_id": str,           # 실험 식별자
  "owner": str,            # "claude" | "gpt" | "joint"
  "patch_version": str,    # 예: "v8_claude"
  "game_seed": int,
  "chunk_id": int,
  "global_game_index": int,
  "winner_ids": list[int],
  "end_reason": str,
  "total_turns": int,
  "final_f_value": float,
  "bankrupt_players": int,
  "player_summary": [...],
  "strategy_summary": [...],
  "bankruptcy_events": [...],
  "weather_history": [...]
}
```

### 3.2 summary.json 필수 필드

비교 가능성을 위해 summary.json에 반드시 포함:

```python
{
  "version": str,
  "owner": str,
  "patch_version": str,
  "games": int,
  "end_reasons": dict,
  "bankrupt_any_rate": float,
  "avg_total_turns": float,
  "avg_final_f_value": float,
  "character_policy_stats": {
    "heuristic_v3_{owner}": {
      "appearances": int,
      "win_share_rate": float,
      "outright_win_rate": float
    }
  },
  "first_place_score_avg": float,
  "mark_success_rate": float,
  "lap_choice_rates": {"cash": float, "shards": float, "coins": float}
}
```

### 3.3 로그 이벤트 네이밍

새 이벤트를 추가할 때:
- `semantic_event`: `{domain}.{action}.{phase}` 형식 (예: `baksu.fallback.activate`)
- `runtime_event`: snake_case (예: `cleanup_lock_released`)
- 기존 이벤트 이름 변경 금지 (파서 하위 호환 파괴)

---

## 4. 공통 분석 파이프라인

### 4.1 표준 집계 지표

실험 비교 시 반드시 아래 6개 지표를 함께 보고한다:

| 지표 | 설명 | 목표 방향 |
|------|------|----------|
| `win_rate` | 테스트 정책의 outright 승률 | ↑ |
| `bankrupt_any_rate` | 파산 발생 게임 비율 | ↓ |
| `avg_total_turns` | 평균 게임 길이 | 안정적 유지 |
| `alive_threshold_rate` | ALIVE_THRESHOLD 종료 비율 | ↓ |
| `first_death_turn_avg` | 첫 사망 평균 턴 | ↑ |
| `own_policy_f1_visits_avg` | 테스트 정책 F1 방문 횟수 | 참고용 |

### 4.2 통계적 유의성 기준

- 100게임 미만: 방향성 참고만 (실제 결론 금지)
- 100게임: 기본 비교 가능 (±5%p 오차 허용)
- 300게임 이상: 결론 내릴 수 있는 최소 기준
- 유의미한 변화 기준: **±3%p 이상 승률 차이 + 파산율 악화 없음**

### 4.3 회귀 판단 기준

다음 중 하나라도 발생하면 **즉시 롤백**:
- 승률이 이전 버전 대비 **-5%p 이상** 하락
- 파산율이 **+10%p 이상** 상승
- 평균 게임 길이가 **±8턴 이상** 급변
- `pytest -q` 실패

---

## 5. 코딩 원칙

### 5.1 MUST (반드시)

```
MUST: 모든 패치는 CHANGELOG.md에 기록한다.
MUST: 수정한 .py 파일에 대응하는 .md 파일도 갱신한다.
MUST: 새 상수/임계값은 반드시 named constant로 명명한다 (매직넘버 금지).
MUST: 공통 생존 신호는 survival_common.py를 통해서만 읽는다.
MUST: 모든 실험 결과는 owner 필드를 포함한다.
MUST: 실험 전 pytest -q 통과 확인.
```

### 5.2 MUST NOT (절대 금지)

```
MUST NOT: engine.py를 AI 정책 패치에서 직접 수정.
MUST NOT: 기존 이벤트 이름/로그 필드 이름 변경.
MUST NOT: 공통 대조군 슬롯(플레이어2,3,4) 정책 변경.
MUST NOT: 롤백 기준 충족 시 패치 유지.
MUST NOT: 실험 중 기능을 안정화 기능처럼 문서화.
MUST NOT: 상대 오너의 패치 버전을 직접 수정 (PR/리뷰 없이).
```

### 5.3 린트 기준

```
- 함수 길이: 100줄 이하 권장, 200줄 초과 금지
- 중첩 깊이: 4단계 이하
- 타입 힌트: 공개 함수 서명에 반드시
- 변수명: snake_case, 약어 사용 시 주석 필수
- 임포트: 순환 임포트 금지 (특히 engine ↔ ai_policy)
```

---

## 6. Try-Catch 원칙

### 6.1 엔진 레이어 (engine.py, effect_handlers.py)

```python
# ✅ 허용: 개별 게임 실패를 청크 배치에서 격리
try:
    result = engine.run()
except Exception as e:
    ef.write(json.dumps({"error": repr(e), "traceback": ...}))
    raise  # 반드시 재발생 (조용한 무시 금지)

# ❌ 금지: 게임 내부 로직을 try-catch로 묵살
try:
    landing_result = self._resolve_landing(state, player)
except:  # bare except 절대 금지
    landing_result = {}  # 이런 패턴 금지
```

### 6.2 정책 레이어 (ai_policy.py)

```python
# ✅ 허용: 점수 계산 실패 시 기본값 반환 (게임 진행 보호)
try:
    score = self._character_score_breakdown_v2(state, player, name)
except Exception:
    score = (0.0, ["fallback_score"])  # 로그 없이 조용히 처리 가능

# ❌ 금지: 상태 변경이 포함된 로직을 try-catch로 보호
try:
    player.cash -= cost  # 상태 변경은 try-catch 금지
    state.tile_owner[pos] = player.player_id
except:
    pass
```

### 6.3 분석/배치 레이어

```python
# ✅ 허용: JSON 파싱 실패 허용
try:
    row = json.loads(line)
except json.JSONDecodeError:
    continue  # 손상된 로그 행 스킵

# ✅ 허용: 누락 필드 기본값 처리
value = row.get("win_rate", 0.0)  # try-catch보다 .get() 우선
```

### 6.4 공통 원칙
- `bare except:` 절대 금지 → 반드시 `except Exception:` 또는 구체적 예외
- 조용한 무시(silent swallow) 금지 → 최소 로그 남기거나 재발생
- 상태 변경 코드는 try-catch 감싸지 않기
- 외부 I/O(파일, JSON)에만 try-catch 적극 사용

---

## 7. 기능 상태 레이블

모든 기능/패치는 다음 레이블 중 하나를 CHANGELOG에 명시:

| 레이블 | 의미 | 조건 |
|--------|------|------|
| `[EXP]` | 실험 중 | 100게임 미만 또는 회귀 미확인 |
| `[STAB]` | 안정화 중 | 100게임 이상, 회귀 없음 확인 |
| `[REL]` | 릴리스 | 300게임+, 양측 합의, pytest 통과 |
| `[ROLLBACK]` | 롤백됨 | 회귀 기준 충족으로 폐기 |
| `[DEPRECATED]` | 지원 종료 예정 | 다음 버전에서 제거 예정 |

---

## 8. 메카닉 이해 원칙 (핵심)

> **코드보다 메카닉 이해가 먼저다.**

AI가 새 로직을 구현하기 전에 반드시 확인해야 하는 것:

1. **자원 흐름의 방향** — 돈/조각이 누구에게서 누구에게로 가는가
2. **인과 관계** — A가 B를 야기하는가, B가 A를 야기하는가
3. **타이밍** — 이 효과는 언제 발생하는가 (자기 턴 / 오프턴 / 라운드 시작)
4. **예외 조건** — 어사, 독점 보호, 마크 차단 등이 이 로직에 영향을 주는가

**방향성 오류(directional error)는 가장 위험한 버그다.**
잘못된 방향으로 구현된 패치는 승률을 올리는 게 아니라 내린다.
확신이 없으면 구현하지 않는다.

---

## 9. 충돌 해결 프로토콜

Claude와 GPT의 패치가 같은 코드를 수정했을 때:

1. **기능 충돌** (같은 함수를 다른 방식으로 수정): 최신 실험 결과로 결정
2. **개념 충돌** (메카닉 해석이 다를 때): 원칙 문서/룰 텍스트 기준으로 결정, 의심 시 시뮬레이션
3. **성능 충돌** (A는 올리고 B는 내릴 때): 양측 합의 전까지 두 버전 별도 실험
4. **해결 불가**: joint 실험으로 데이터 기반 결정, 데이터도 불명확하면 conservative 선택

---

## 10. 이 문서의 갱신 규칙

- 양측 합의 없이 단독 수정 금지
- 합의된 수정은 `COLLAB_SPEC_DRAFT.md` → `COLLAB_SPEC_v{N}.md`로 버전업
- 실험 기반으로 원칙이 틀렸음이 증명되면 즉시 개정
- 이 문서 자체도 [EXP] 레이블 — 첫 공동 실험 후 개정 예정

