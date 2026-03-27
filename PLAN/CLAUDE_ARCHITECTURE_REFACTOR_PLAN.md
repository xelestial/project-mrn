# CLAUDE 아키텍처 리팩토링 플랜
## Claude 구현체 전용 실행 계획
### 버전: 1.1 | 날짜: 2026-03-27 | 상태: [EXP]

---

## 0. 이 문서의 목적

`ARCHITECTURE_REFACTOR_AGREED_SPEC_v1_0.md`에 합의된 공동 구조를
**CLAUDE/ 구현체 기준으로 구체화**한 실행 계획이다.

- 현재 CLAUDE/ 상태 진단
- 합의 구조까지의 갭 분석
- Phase별 실행 태스크 목록
- Claude 전용 설계 결정 사항

이 문서는 GPT/ 또는 GEMINI/의 작업 범위와 겹치지 않는다.
공동 계약 변경이 필요하면 `COLLAB_SPEC`과 `ARCHITECTURE_REFACTOR_AGREED_SPEC`을 먼저 갱신한다.

### v1.1 변경 내역 (GPT 플랜 검토 후 반영)

`GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md` 검토 결과 두 가지를 반영:

1. **Decision 추출 순서 정렬** (Phase 3): GPT가 커플링 리스크 기준으로 제안한 순서와 일치시킴
   - `lap_reward → purchase → draft/character → mark → movement → trick → marker_flip`
2. **PolicyAsset 조기 스캐폴드** (Phase 2에 추가): 조합 루트를 빈 브리지로 먼저 생성해두는 방식 반영
   - Phase 4에서 완성하되, Phase 2에서 passthrough 뼈대를 먼저 잡음

나머지 구조(Phase 순서, 타깃 디렉토리, 설계 결정)는 유지.

---

## 1. 현재 CLAUDE/ 구현 상태 진단

### 1.1 이미 분리된 것 (선행 작업 완료)

| 모듈 | 역할 | 상태 |
|------|------|------|
| `survival_common.py` | SurvivalSignals, ActionGuardContext, SwindleGuardDecision, is_action_survivable | ✅ 분리됨 |
| `policy_groups.py` | 캐릭터 그룹 집합 상수 | ✅ 분리됨 |
| `policy_mark_utils.py` | 지목 추측 파라미터, 공개 후보 필터 | ✅ 분리됨 |
| `policy_hooks.py` | before/after 훅 등록 체계 | ✅ 분리됨 |
| `game_rules.py` + `ruleset.json` | 규칙 외부화 | ✅ 완료 |
| `board_layout.json` | 보드 외부화 | ✅ 완료 |

### 1.2 합의 구조 대비 미완성 항목

| 합의 목표 | 현재 상태 | 갭 |
|-----------|-----------|-----|
| `policy/profile/spec.py` — ProfileSpec frozen dataclass | 없음. weights가 `ai_policy.py` 내 딕셔너리로 하드코딩 | **Phase 1** |
| `profiles/policy_weights_*.json` — 가중치 외부화 | `PROFILE_WEIGHTS` 딕셔너리가 코드 내부에 있음 | **Phase 1** |
| `profiles/character_values_*.json` — 인물 점수 외부화 | `character_values` 클래스 변수 내부 | **Phase 1** |
| `profiles/survival_threshold_*.json` — 생존 임계값 외부화 | `survival_common.py` 내 매직넘버 | **Phase 1** |
| `policy/context/turn_context.py` — typed TurnContext | `context: dict` 기반 | **Phase 2** |
| `policy/context/builder.py` — TurnContextBuilder | `_generic_survival_context()` 내부 함수로 존재 | **Phase 2** |
| `policy/registry/strategy_registry.py` — stable key | 없음. 클래스 직접 참조 | **Phase 2** |
| `policy/survival/strategy.py` — SurvivalStrategy ABC | `SurvivalOrchestratorState`가 survival_common 내 함수로 존재 | **Phase 2** |
| `policy/character_eval/*.py` — pair 단위 evaluator | `_character_score_breakdown_v2()`가 ai_policy.py 내 단일 3000줄 함수 | **Phase 3** |
| `policy/decision/*.py` — 행동별 독립 모듈 | ai_policy.py 내 choose_*() 메서드로 혼재 | **Phase 3** |
| `policy/asset/policy_asset.py` — PolicyAsset 조합 자산 | 없음 | **Phase 4** |
| `policy/asset/factory.py` — PolicyAssetFactory | 없음 | **Phase 4** |

### 1.3 현재 ai_policy.py 의존 관계 (문제 지점)

```
ai_policy.py
  ├── 직접 포함: PROFILE_WEIGHTS, character_values, 매직넘버 임계값
  ├── choose_character() → _character_score_breakdown_v2() [8 페어 × 복합 조건]
  ├── choose_movement()  → _race_position_context(), _f_progress_context()
  ├── choose_purchase()  → survival_common.is_action_survivable()
  ├── choose_lap_reward() → 내부 로직 (v3_claude 전용 분기 포함)
  ├── choose_trick_use() → 내부 로직
  ├── choose_mark_target() → policy_mark_utils 위임 (부분 분리됨)
  └── survival_common.py  ← 이미 분리 (good)
```

핵심 문제: `_character_score_breakdown_v2()`가 8개 페어 로직을
하나의 함수 안에 전부 포함하고 있어, 인물 평가 단위 테스트와
Claude/GPT 병렬 실험이 모두 어렵다.

---

## 2. 갭 분석 요약

### 2.1 가장 긴급한 갭 (충돌 위험)

1. **PROFILE_WEIGHTS 코드 내부화** — Claude/GPT가 같은 딕셔너리를 수정하면 충돌
2. **_character_score_breakdown_v2() 모놀리스** — 3 AI가 같은 함수를 동시에 수정 불가능
3. **context: dict** — 필드명 오타/드리프트가 런타임까지 발견 안 됨

### 2.2 실험 속도에 직결되는 갭

1. **character_values 외부화 미완** — 인물 가중치 실험 시 매번 코드 수정 필요
2. **survival threshold 매직넘버** — 생존 민감도 실험 시 코드 직접 수정 필요
3. **ProfileSpec 없음** — 동일 코드에서 여러 프로파일 조합 비교 불가

---

## 3. Phase별 실행 계획

### Phase 1 — 값 외부화 (엔진 무수정, 행동 변경 없음)

**목표**: 가중치/임계값을 JSON으로 빼내고, 코드는 이를 로딩하도록 변경.
행동이 바뀌어서는 안 된다. 기존 테스트가 그대로 통과해야 한다.

#### 태스크 목록

**T1-1: `profiles/` 디렉토리 생성 및 JSON 파일 작성**

```
CLAUDE/profiles/
  policy_weights_v3_claude.json     ← PROFILE_WEIGHTS["v3_claude"] 추출
  policy_weights_balanced.json      ← PROFILE_WEIGHTS["heuristic_v2_balanced"] 추출
  policy_weights_control.json       ← PROFILE_WEIGHTS["heuristic_v2_control"] 추출
  policy_weights_token_opt.json     ← PROFILE_WEIGHTS["heuristic_v2_token_opt"] 추출
  character_values_v3_claude.json   ← character_values 추출
  character_values_default.json     ← 기본값 (v2 계열 공통)
  survival_threshold_default.json   ← survival_common.py 매직넘버 추출
  mark_risk_default.json            ← MARK_ACTOR_BASE_RISK, MARK_GUESS_* 추출
  character_groups.json             ← policy_groups.py 그룹 집합 추출
```

**T1-2: `policy/profile/spec.py` 작성**

```python
@dataclass(frozen=True, slots=True)
class PolicyProfileSpec:
    name: str
    weights: dict[str, float]
    character_values: dict[str, float]
    survival_strategy_key: str = "survival/default_v1"
    lap_reward_strategy_key: str = "lap_reward/base_v1"
    purchase_gate_strategy_key: str = "purchase_gate/base_v1"
    draft_strategy_key: str = "draft/base_v1"
```

**T1-3: `policy/profile/registry.py` 작성**

- `ProfileRegistry.register(spec)` / `ProfileRegistry.resolve(name)` 구현
- alias 지원: `v3_claude`, `heuristic_v2_v3_claude` → canonical `heuristic_v3_claude_exp`

**T1-4: `policy/profile/presets.py` 작성**

- JSON 로딩 후 `ProfileRegistry`에 등록하는 초기화 함수

**T1-5: `ai_policy.py` 수정 — JSON 로드로 교체**

- `PROFILE_WEIGHTS` 딕셔너리 → `ProfileRegistry.resolve(name).weights` 로 교체
- `character_values` → `ProfileRegistry.resolve(name).character_values` 로 교체
- 행동 변경 없음

**T1-6: `survival_common.py` 수정 — threshold JSON 로드**

- 매직넘버 상수 → `SurvivalThresholdSpec` dataclass + `profiles/survival_threshold_*.json` 로드

**완료 기준**:
- `pytest -q` 전체 통과
- 100판 기준 승률 변화 ±1%p 이내 (동일 seed)

---

### Phase 2 — TurnContext + SurvivalStrategy 분리

**목표**: dict 기반 context를 typed dataclass로 교체.
survival을 독립 인터페이스로 분리.

#### 태스크 목록

**T2-1: `policy/context/turn_context.py` 작성**

합의 스펙의 `TurnContext` frozen dataclass 그대로 구현.
기존 `_generic_survival_context()` 반환 필드를 기준으로 필드 목록 확정.

**T2-2: `policy/context/builder.py` 작성**

- `TurnContextBuilder.build(state, player) -> TurnContext` 구현
- 기존 `_generic_survival_context()`, `_race_position_context()`, `_f_progress_context()` 로직 흡수

**T2-3: `policy/context/` feature 분리 파일들**

```
economy_features.py   ← own_cash, tiles_margin, rent_exposure 계산
danger_features.py    ← two_turn_lethal_prob, burden_cleanup_cost 계산
token_features.py     ← placeable_own_tiles, token_window_score 계산
race_features.py      ← is_leader, leader_gap, f_remaining 계산
```

각 파일은 `state, player` 를 받아 해당 feature 그룹을 반환하는 순수 함수 모음.

**T2-4: `policy/registry/strategy_registry.py` 작성**

```python
STRATEGY_REGISTRY: dict[str, type] = {
    "survival/default_v1": DefaultSurvivalStrategy,
    "survival/v3_claude_v1": V3ClaudeSurvivalStrategy,
    "lap_reward/base_v1": BaseLapRewardStrategy,
    ...
}
```

**T2-5: `policy/survival/strategy.py` 작성**

- `SurvivalStrategy` ABC 정의
- `SurvivalAssessment` frozen dataclass 정의
- `DefaultSurvivalStrategy` — 기존 survival_common 로직 흡수
- `V3ClaudeSurvivalStrategy` — v3_claude 전용 임계값 적용

**T2-6: `ai_policy.py` 수정 — TurnContext 병행 사용**

- `_generic_survival_context()` → `TurnContextBuilder.build()` 로 점진 교체
- dict 접근 → `ctx.field_name` 으로 점진 교체 (타입 에러 즉시 감지)

**T2-7: `policy/asset/policy_asset.py` 조기 스캐폴드 (브리지)**

GPT 플랜 Phase C 반영: PolicyAsset/Factory를 Phase 4에서 완성하기 전에
빈 passthrough 뼈대로 먼저 생성해 조합 경계를 확립한다.

```python
# policy/asset/policy_asset.py — Phase 2 브리지 (내부는 기존 로직 위임)
@dataclass(slots=True)
class PolicyAsset:
    spec: PolicyProfileSpec
    survival: Any   # Phase 3에서 SurvivalStrategy로 교체
    # 나머지 필드는 Phase 3~4에서 추가
```

- `PolicyFactory.from_name(name)` → 기존 `HeuristicPolicy(name)` 위임
- 엔진 계약(`choose_*` 인터페이스) 변경 없음

**완료 기준**:
- `pytest -q` 전체 통과
- `context: dict` 접근 코드가 `ai_policy.py` 내에 남아 있어도 허용 (점진 교체)
- `SurvivalStrategy.evaluate()` 를 통한 100판 승률 ±1%p 이내 유지

---

### Phase 3 — CharacterEvaluator + Decision 모듈화

**목표**: `_character_score_breakdown_v2()` 를 8개 pair evaluator로 분해.
`choose_*()` 메서드를 독립 decision 모듈로 분리.

> **주의**: Phase 3부터 `ai_policy.py` 구조가 실질적으로 바뀐다.
> 착수 전 GPT/GEMINI와 작업 범위 조율 필요 (PLAN/ 공유).

#### 태스크 목록

**T3-1: `policy/character_eval/base.py` 작성**

```python
class CharacterEvaluator(ABC):
    @abstractmethod
    def score(
        self, state, player, ctx: TurnContext, survival: SurvivalAssessment
    ) -> tuple[float, tuple[str, ...]]:
        ...
```

**T3-2: pair별 evaluator 파일 작성 (8개)**

| 파일 | 대상 페어 | 핵심 로직 |
|------|-----------|-----------|
| `asa_tamgwan.py` | 어사 / 탐관오리 | 우선권 1 가치, 세금 수입, 봉쇄 상황 |
| `jagaek_sanjeok.py` | 자객 / 산적 | 지목 kill window, overlap 판단 |
| `chuno_escape.py` | 추노꾼 / 탈출 노비 | 강제이동 위협, 탈출 동선 |
| `pabal_ajeon.py` | 파발꾼 / 아전 | 이동 버프, overlap kill window |
| `doctrine_pair.py` | 교리 연구관 / 감독관 | 턴 시작 짐 제거, 징표 이동 |
| `shaman_pair.py` | 박수 / 만신 | shard checkpoint, burden fallback 엔진 |
| `geo_pair.py` | 객주 / 중매꾼 | lap engine, 이동 최적화 |
| `builder_swindler.py` | 건설업자 / 사기꾼 | 무료 건설, SWINDLE_FAIL 생존 게이트 |

각 파일에는 두 캐릭터의 `CharacterEvaluator` 구현 포함.

**T3-3: `policy/character_eval/registry.py` 작성**

```python
CHARACTER_EVALUATOR_REGISTRY: dict[str, CharacterEvaluator] = {
    "char_eval/asa_tamgwan_v1": AsaTamgwanEvaluator(),
    "char_eval/shaman_pair_v1": ShamanPairEvaluator(),
    ...
}
```

**T3-4: `policy/decision/` 파일들 작성 (커플링 리스크 기준 순서)**

GPT 플랜과 정렬된 추출 순서 — 리스크 낮은 것부터:

```
lap_reward.py     ← 1순위: 독립적, 엔진 상태 변경 없음
purchase.py       ← 2순위: survival gate와 명확한 경계
draft.py          ← 3순위: character_eval 결과 소비자
mark_target.py    ← 4순위: policy_mark_utils 이미 분리됨
movement.py       ← 5순위: race context 의존, 중간 복잡도
trick_use.py      ← 6순위: 멀티 카드 상태 의존
marker_flip.py    ← 7순위: 가장 드문 결정, 마지막
```

각 파일은 단일 책임: 해당 결정 축의 로직만 포함.
`ai_policy.py`의 `choose_*()` 메서드는 해당 decision 모듈로 위임.

**T3-5: `ai_policy.py` 구조 변경**

```python
class HeuristicPolicy(BasePolicy):
    def __init__(self, asset: PolicyAsset):  # Phase 4에서 완성
        self.evaluators = asset.character_evaluators
        self.purchase_gate = asset.purchase_gate
        ...

    def choose_character(self, state, player, candidates):
        ctx = self.context_builder.build(state, player)
        survival = self.survival.evaluate(state, player, ctx)
        return self.draft.choose(state, player, ctx, survival, self.evaluators)
```

**완료 기준**:
- `_character_score_breakdown_v2()` 가 `ai_policy.py`에서 제거됨
- 각 evaluator 단위 테스트 작성 및 통과
- 100판 승률 ±2%p 이내 유지 (리팩토링이므로 행동 보존 목표)

---

### Phase 4 — PolicyAsset + Factory 완성

**목표**: ProfileSpec + SurvivalStrategy + DecisionBundle을 JSON으로 조립 가능하게.
실험 재현성 확보.

#### 태스크 목록

**T4-1: `policy/asset/policy_asset.py` 작성**

```python
@dataclass(slots=True)
class PolicyAsset:
    spec: PolicyProfileSpec
    survival: SurvivalStrategy
    lap_reward: LapRewardStrategy
    purchase_gate: PurchaseGateStrategy
    draft: DraftStrategy
    character_evaluators: dict[str, CharacterEvaluator]
    context_builder: TurnContextBuilder
```

**T4-2: `policy/asset/factory.py` 작성**

```python
class PolicyAssetFactory:
    def from_json(self, path: str) -> PolicyAsset: ...
    def from_spec(self, spec_dict: dict) -> PolicyAsset: ...
```

**T4-3: `policy_profiles/` 디렉토리 생성**

```
CLAUDE/policy_profiles/
  v3_claude.json    ← 현재 heuristic_v2_v3_claude 설정 전체
  control.json
  balanced.json
  token_opt.json
```

예시 (`v3_claude.json`):
```json
{
  "name": "heuristic_v3_claude_exp",
  "profile_key": "weights/v3_claude",
  "survival_strategy_key": "survival/v3_claude_v1",
  "lap_reward_strategy_key": "lap_reward/v3_claude_v1",
  "purchase_gate_strategy_key": "purchase_gate/v3_claude_v1",
  "draft_strategy_key": "draft/v3_claude_v1",
  "character_evaluator_keys": [
    "char_eval/asa_tamgwan_v1",
    "char_eval/shaman_pair_v1",
    "char_eval/jagaek_sanjeok_v1",
    "char_eval/chuno_escape_v1",
    "char_eval/pabal_ajeon_v1",
    "char_eval/doctrine_pair_v1",
    "char_eval/geo_pair_v1",
    "char_eval/builder_swindler_v1"
  ]
}
```

**T4-4: asset hash 로깅 추가**

- `simulate_with_logs.py` 의 게임 결과에 `"policy_asset_hash": str` 필드 추가
- asset hash = `sha256(json.dumps(asset_dict, sort_keys=True))[:8]`

**완료 기준**:
- JSON 파일만 교체해서 전략 조합 실험 가능
- `pytest -q` 전체 통과
- summary.json에 `policy_asset_hash` 필드 포함

---

## 4. 최종 목표 디렉토리 구조

```
CLAUDE/
  policy/
    profile/
      spec.py
      registry.py
      presets.py
    survival/
      strategy.py         ← SurvivalStrategy ABC + 구현체들
      thresholds.py       ← SurvivalThresholdSpec
      orchestrator.py     ← 기존 survival_common.py 흡수
      guards.py           ← is_action_survivable, swindle_guard
      signals.py          ← SurvivalSignals dataclass
    context/
      turn_context.py
      builder.py
      economy_features.py
      danger_features.py
      token_features.py
      race_features.py
    character_eval/
      base.py
      registry.py
      asa_tamgwan.py
      jagaek_sanjeok.py
      chuno_escape.py
      pabal_ajeon.py
      doctrine_pair.py
      shaman_pair.py
      geo_pair.py
      builder_swindler.py
    decision/
      draft.py
      movement.py
      purchase.py
      lap_reward.py
      trick_use.py
      mark_target.py
      marker_flip.py
    asset/
      policy_asset.py
      factory.py
    registry/
      strategy_registry.py
      profile_registry.py
  profiles/
    policy_weights_v3_claude.json
    policy_weights_balanced.json
    policy_weights_control.json
    policy_weights_token_opt.json
    character_values_v3_claude.json
    character_values_default.json
    survival_threshold_default.json
    survival_threshold_v3_claude.json
    mark_risk_default.json
    character_groups.json
  policy_profiles/
    v3_claude.json
    balanced.json
    control.json
    token_opt.json
  ai_policy.py             ← 각 모듈 위임자 역할로 축소
  survival_common.py       ← policy/survival/ 으로 점진 이전
  policy_groups.py         ← profiles/character_groups.json 으로 이전
  policy_mark_utils.py     ← 유지 (policy/decision/mark_target.py 로 이전 예정)
  policy_hooks.py          ← 유지
```

---

## 5. 설계 결정 사항 (Claude 전용)

### 5.1 v3_claude 생존 전략

`V3ClaudeSurvivalStrategy` 는 기존 v3_claude 설계 철학을 반영:
- **박수 폴백 엔진 우선**: shard ≥ 5 + burden 있으면 cleanup_lock 해제
- **어사/탐관오리 우선권 1**: buy_value > 0 조건에서 expansion bonus 적극 부여
- **과도한 보수성 방지**: survival weight를 1.2로 제한 (control의 1.6 대비)

### 5.2 점진 마이그레이션 원칙

- Phase 1~2는 **행동 보존 리팩토링** — 승률이 변하면 안 됨
- Phase 3부터 **전략 실험 가능** — 승률 변화 허용, 단 롤백 기준 준수
- 각 Phase 완료마다 `pytest -q` + 100판 시뮬레이션 검증

### 5.3 ai_policy.py 최종 역할

Phase 4 완료 후 `ai_policy.py`는:
- `PolicyAssetFactory`로 asset 조립
- `HeuristicPolicy` 의 thin wrapper 역할
- 레거시 `ArenaPolicy` 인터페이스 유지 (엔진 호환)

함수 길이 200줄 초과 금지 (COLLAB_SPEC 5.3) — 현재 상태에서 가장 먼저 해소해야 할 항목.

### 5.4 character_eval 페어 분리 순서

리팩토링 위험도 기준 순서:
1. `shaman_pair.py` — 가장 독립적, shard checkpoint 로직 명확
2. `geo_pair.py` — lap engine, 행동 영향이 큼, 검증 우선
3. `asa_tamgwan.py` — 우선권 로직 단순, 테스트 작성 쉬움
4. `builder_swindler.py` — SWINDLE_FAIL 게이트 복잡, 마지막

---

## 6. 리스크 및 완화 방안

| 리스크 | 확률 | 완화 방안 |
|--------|------|-----------|
| JSON 로드 실패로 기존 프로파일 동작 불가 | 중간 | Phase 1에서 fallback: JSON 없으면 코드 내 상수 사용 |
| TurnContext 필드 불일치로 기존 분석 파이프라인 깨짐 | 중간 | Phase 2에서 dict → TurnContext 병행 기간 유지 |
| char_eval 분리 후 v3_claude 승률 하락 | 높음 | Phase 3 착수 전 100판 기준선 고정, 분리 후 즉시 비교 |
| ai_policy.py 수정 중 GPT/GEMINI 와 충돌 | 중간 | PLAN/ 에 착수 전 공지, Phase 3 이전 양측 타임라인 공유 |

---

## 7. 진행 상황 추적

| Phase | 상태 | 완료 기준 충족 여부 |
|-------|------|---------------------|
| Phase 1: 값 외부화 | 🔲 미착수 | - |
| Phase 2: TurnContext + SurvivalStrategy | 🔲 미착수 | - |
| Phase 3: CharacterEvaluator + Decision | 🔲 미착수 | - |
| Phase 4: PolicyAsset + Factory | 🔲 미착수 | - |

---

*이 문서는 Claude 작업 진행에 따라 갱신된다.*
*공동 계약(COLLAB_SPEC, ARCHITECTURE_REFACTOR_AGREED_SPEC)과 충돌하면 공동 계약이 우선한다.*
