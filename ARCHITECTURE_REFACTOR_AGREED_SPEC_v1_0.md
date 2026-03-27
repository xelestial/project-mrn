# ARCHITECTURE REFACTOR AGREED SPEC
## Basegame Simulator 공동 아키텍처 리팩토링 최종 합의안
### 버전: 1.0 | 날짜: 2026-03-27

---

## 0. 목적

이 문서는 Basegame Simulator의 정책/생존/분석 구조를
공동 작업(GPT / Claude) 기준으로 재정리한 **최종 합의 아키텍처 명세**다.

목표는 다음과 같다.

1. 메인 엔진 로직 수정 없이 정책 실험 범위를 최대화한다.
2. GPT와 Claude가 같은 코드베이스에서 충돌을 줄이고 병렬 작업할 수 있게 한다.
3. `ai_policy.py`에 과도하게 응집된 책임을 여러 모듈로 분산한다.
4. 프로파일, 생존 전략, 행동 결정기, 캐릭터 평가기, 파생 컨텍스트 계산기를 독립 교체 가능하게 만든다.
5. Python 환경에서 ScriptableObject-like 운영이 가능하도록 Policy Asset + Factory 구조를 도입한다.
6. 로그/분석 체계를 누적 가능한 자산으로 유지한다.

이 문서는 관련 초안과 상호 검토를 거친 뒤 합의된 최종 기준이다.

---

## 1. 최상위 원칙

### 1.1 엔진 안정성 우선
정책 리팩토링의 목표는 엔진을 자주 건드리는 것이 아니라,
정책/분석 레이어를 더 잘 분리하는 것이다.

### 1.2 문서와 코드 동기화
새 구조 도입 시:
- 대응 문서(`*.md`)도 같이 갱신
- CHANGELOG 기록
- doc integrity 유지

### 1.3 설정과 해석 분리
- **설정(setting)**: 외부화 가능
- **해석(interpretation)**: 코드/전략/평가기로 유지

### 1.4 생존은 독립 축
생존은 단순 profile weight가 아니라,
정책 전반을 제어하는 상위 제약이다.
따라서 profile 내부에 묻지 않고 별도 모듈로 둔다.

### 1.5 조립형 정책
정책은 하나의 거대한 클래스가 아니라,
여러 역할 객체를 조합한 결과여야 한다.

---

## 2. 현재 구조에 대한 합의 판단

현재 구조는 이미 다음 기반을 갖고 있다.

- 엔진/룰/정책/분석 레이어가 어느 정도 분리되어 있음
- `ruleset.json`, `board_layout.json`, `rule_scripts.json` 등 외부화 기반 존재
- `simulate_with_logs.py`, `run_chunked_batch.py`, `analyze_strategy_logs.py` 존재
- 문서 무결성 체계 존재

그러나 현재 정책 레이어는 여전히 다음 문제가 있다.

1. `ai_policy.py` 응집도 과다
2. 프로파일 / 생존 / 행동결정 / 캐릭터 해석 / 파생 지표 계산이 한곳에 몰림
3. 공동 작업 시 충돌 위험이 큼
4. 로그/분석과 연결되는 feature 정의가 코드 내부에 흩어질 가능성이 큼

이 문서는 위 문제를 해결하기 위한 합의 구조를 정의한다.

---

## 3. 최종 채택 구조

```text
policy/
  profile/
    spec.py
    registry.py
    presets.py
  survival/
    strategy.py
    thresholds.py
    orchestrator.py
    guards.py
    signals.py
  context/
    turn_context.py
    builder.py
    economy_features.py
    danger_features.py
    token_features.py
    race_features.py
  character_eval/
    registry.py
    base.py
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
    character_select.py
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

analysis/
  log_pipeline.py
  stats_pipeline.py
  annotators/
    danger_window_annotator.py
    overlap_kill_annotator.py
    lap_engine_annotator.py
    pivotal_event_annotator.py
```

---

## 4. 프로파일 구조 합의

## 4.1 ProfileSpec 도입
프로파일은 데이터 객체로 정의한다.

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ProfileSpec:
    canonical_name: str
    aliases: tuple[str, ...]
    weights: dict[str, float]
    tags: frozenset[str]
    options: dict[str, Any]
```

## 4.2 canonical name + alias
- 로그/summary에는 **canonical name**만 기록
- 과거 호환성을 위해 alias는 허용
- alias는 registry에서만 해석

예:
- `heuristic_v3_gpt_exp`
- `heuristic_v3_claude_exp`

호환 alias 예:
- `heuristic_v3_gpt`
- `v3_claude`
- `heuristic_v2_v3_claude`

## 4.3 ProfileRegistry
프로파일 등록/조회는 registry가 담당한다.

```python
class ProfileRegistry:
    def register(self, spec: ProfileSpec) -> None: ...
    def resolve(self, name: str) -> ProfileSpec: ...
```

---

## 5. 생존 전략 구조 합의

## 5.1 독립 모듈화
생존 전략은 프로파일의 하위 옵션이 아니라,
별도 모듈로 둔다.

## 5.2 기본 인터페이스
```python
class SurvivalStrategy:
    def evaluate(self, state, player, ctx) -> "SurvivalAssessment":
        ...
```

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SurvivalAssessment:
    money_distress: float
    reserve_gap: float
    rent_pressure: float
    burden_pressure: float
    two_turn_lethal_prob: float
    controller_need: float
    survivable: bool
    notes: tuple[str, ...] = ()
```

## 5.3 대표 구현 예시
- `ConservativeSurvivalStrategy`
- `BalancedSurvivalStrategy`
- `RiskOnSurvivalStrategy`

## 5.4 합의 원칙
- survival은 독립 축
- profile은 어떤 survival preset을 사용할지 참조/파라미터화 가능
- 같은 profile + 다른 survival 전략 비교가 가능해야 함

---

## 6. TurnContext / Feature 계산 구조 합의

## 6.1 dict 기반 context 지양
`context: dict` 구조는 공동 작업과 장기 진화에 취약하므로,
typed dataclass 기반 context를 쓴다.

## 6.2 TurnContextBuilder 도입
```python
class TurnContextBuilder:
    def build(self, state, player) -> "TurnContext":
        ...
```

예시:
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class TurnContext:
    own_tiles: int
    tiles_margin_vs_best: int
    own_cash: int
    cash_margin_vs_best: int
    own_shards: int
    rent_exposure: float
    burden_cleanup_cost: int
    next_lap_chance_1t: float
    next_lap_chance_2t: float
    overlap_enemy_count: int
    overlap_on_enemy_land: bool
    own_monopoly_count: int
    lap_pool_remaining_score: float
    notes: tuple[str, ...] = ()
```

## 6.3 합의 원칙
- 공용 파생 지표는 context builder가 계산
- decision/evaluator/survival 모두 같은 context를 공유
- 분석 pipeline feature 정의와 의미를 최대한 맞춘다

---

## 7. CharacterEvaluator 구조 합의

## 7.1 필요성
단순 `character_values` 외부화만으로는 충분하지 않다.

다음은 값만으로 표현되지 않는다.
- 아전 overlap kill window
- 객주 lap engine
- 박수/만신 burden 해석
- 탐관오리/어사 양면 카드 관계
- 사기꾼 SWINDLE_FAIL 생존 게이트

## 7.2 pair 단위 분리
양면 카드 구조상, pair 단위 evaluator 분리를 기본으로 한다.

예:
- `asa_tamgwan.py`
- `jagaek_sanjeok.py`
- `chuno_escape.py`
- `pabal_ajeon.py`
- `doctrine_pair.py`
- `shaman_pair.py`
- `geo_pair.py`
- `builder_swindler.py`

## 7.3 인터페이스
```python
class CharacterEvaluator:
    def score(self, state, player, ctx) -> tuple[float, tuple[str, ...]]:
        ...
```

## 7.4 CharacterEvaluatorRegistry
캐릭터/카드쌍 evaluator 등록 및 조회는 registry에서 수행한다.

---

## 8. 행동 결정기(Decision Bundle) 구조 합의

## 8.1 대상
다음 결정 축은 독립 모듈로 분리한다.

- draft
- final character choice
- movement
- purchase
- lap reward
- trick use
- mark target
- marker flip

## 8.2 예시 구조
```text
decision/
  draft.py
  character_select.py
  movement.py
  purchase.py
  lap_reward.py
  trick_use.py
  mark_target.py
  marker_flip.py
```

## 8.3 인터페이스 예시
```python
class PurchaseDecider:
    def choose(self, state, player, ctx, survival) -> bool:
        ...
```

## 8.4 합의 원칙
- 행동별 실험이 가능해야 한다
- GPT/Claude가 서로 다른 결정기만 교체해도 전체 정책이 조립 가능해야 한다

---

## 9. Strategy 식별 규칙 합의

## 9.1 class name 문자열 직접 사용 금지
전략 식별은 클래스명을 직접 JSON에 넣지 않는다.

금지 예:
```json
{
  "lap_reward_strategy": "V3GptLapRewardStrategy"
}
```

## 9.2 stable registry key 사용
예:
```python
STRATEGY_REGISTRY = {
    "lap_reward/v3_gpt_v1": V3GptLapRewardStrategy,
    "purchase_gate/v3_gpt_v1": V3GptPurchaseGate,
    "draft/balanced_v2": BalancedDraftStrategy,
}
```

JSON/YAML/asset에는 stable key를 저장한다.

예:
```json
{
  "lap_reward_strategy": "lap_reward/v3_gpt_v1",
  "purchase_gate_strategy": "purchase_gate/v3_gpt_v1"
}
```

## 9.3 이유
- rename 안전성
- IDE refactor 안전성
- dead reference 감소
- runtime typo 위험 감소

---

## 10. PolicyAsset + Factory 구조 합의

## 10.1 목표
Python에서 ScriptableObject-like 운영을 하기 위해
PolicyAsset + Factory 구조를 채택한다.

## 10.2 PolicyAsset 예시
```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class PolicyAsset:
    profile: str
    survival: str
    context_builder: str
    movement_decider: str
    purchase_decider: str
    lap_reward_decider: str
    mark_decider: str
    marker_flip_decider: str
    character_pack: str
    options: dict[str, Any]
```

## 10.3 Factory
```python
class PolicyFactory:
    def from_asset(self, asset: PolicyAsset):
        ...
```

## 10.4 합의 원칙
- 조합 실험은 asset 단위로 가능해야 한다
- 로그/summary에는 가능하면 asset hash 또는 asset id를 남긴다
- profile / survival / decision / evaluator 조합을 외부 자산으로 관리할 수 있게 한다

---

## 11. 설정과 해석의 구분

## 11.1 외부화 가능한 것
- weights
- base character values
- thresholds
- risk constants
- group membership
- preset references

## 11.2 코드로 유지할 것
- overlap kill 판정
- lap engine 판정
- burden pressure 해석
- takeover survivability gate
- revisit / leader denial 같은 복합 전략 해석
- 다중 feature 조합 분기

## 11.3 합의 원칙
**설정은 외부화, 해석은 코드로 유지**한다.

---

## 12. 엔진 수정 허용 범위

정책 리팩토링 과정에서 엔진 수정은 기본적으로 지양한다.

다만 다음은 허용한다.

1. 버그 수정
2. 룰 정합성 수정
3. 로깅/분석 필드 추가
4. semantic event 추적 보강

허용 시 필수:
- CHANGELOG 기록
- 대응 `.md` 갱신
- 회귀 테스트 수행

---

## 13. 분석 파이프라인 구조 합의

## 13.1 역할 분리
- **log_pipeline**: 원본 로그 → row/feature 변환
- **stats_pipeline**: row/feature → 집계/요약/리포트 생성
- **annotators**: semantic explanation 추가

## 13.2 Annotator 레이어 예시
- `danger_window_annotator.py`
- `overlap_kill_annotator.py`
- `lap_engine_annotator.py`
- `pivotal_event_annotator.py`

## 13.3 합의 원칙
- 엔진을 덜 건드리면서 분석력을 강화
- 도메인 특화 feature를 annotator 계층에서 풍부하게 추가
- GPT/Claude가 분석 feature를 병렬 확장 가능하게 함

---

## 14. Phase별 실제 적용 계획

## Phase 1: 즉시 착수 가능
다음은 바로 분리/도입한다.

### Deliverables
- `profiles/spec.py`
- `profiles/registry.py`
- `profiles/presets.py`
- `registry/strategy_registry.py`
- `profile_weights.json`
- `character_values.json`

### 목표
- weights / base values / thresholds 외부화
- profile alias / canonical name 정리
- strategy stable key 도입

---

## Phase 2: 공동 작업 안정화
### Deliverables
- `survival/strategy.py`
- `survival/orchestrator.py`
- `context/turn_context.py`
- `context/builder.py`

### 목표
- survival 독립 축화
- typed TurnContext 도입
- 공용 feature 계산 분리

---

## Phase 3: 게임 해석 모듈화
### Deliverables
- `character_eval/registry.py`
- pair별 evaluator 파일들
- `decision/` 하위 모듈

### 목표
- 캐릭터 복합 해석 분리
- 행동 결정기 모듈화
- 공동 병렬 작업 충돌 최소화

---

## Phase 4: ScriptableObject-like 운영
### Deliverables
- `asset/policy_asset.py`
- `asset/factory.py`
- asset 기반 실험 조합 파일들

### 목표
- 조합 실험 외부화
- asset hash 기반 재현성 강화
- profile/survival/decision/evaluator 조립형 운영 완성

---

## 15. 공동 작업 관점의 최종 합의

공동 작업의 핵심은 다음과 같다.

1. 엔진은 가능한 안정적으로 유지
2. 정책은 DI 가능한 조립형 구조로 분리
3. profile과 survival은 분리
4. character evaluator는 별도 레이어로 둔다
5. context는 typed builder로 통일
6. strategy 식별은 stable registry key 기반
7. 실험 조합은 PolicyAsset으로 외부화
8. 로그/분석은 공통 스키마로 유지

---

## 16. 최종 결론

본 문서는 다음에 합의한다.

- Claude 제안의 **단계적 리팩토링 플랜은 채택**
- 값 외부화와 전략 인터페이스 분리는 우선 적용
- 다만 최종 구조는 단순 JSON 외부화나 profile container 하나로 끝내지 않는다
- 반드시 다음 축을 포함한다:

```text
ProfileSpec
+ ProfileRegistry
+ SurvivalStrategy
+ TurnContextBuilder
+ CharacterEvaluatorRegistry
+ DecisionBundle
+ PolicyAssetFactory
+ StrategyRegistry
```

즉 최종 합의된 방향은:

**“생존을 프로파일 안에 완전히 흡수하는 것”이 아니라,  
정책을 DI 가능한 조립형 시스템으로 재구성하는 것**이다.

이 구조가 가장 적은 충돌로 가장 높은 재현성과 확장성을 제공한다.
