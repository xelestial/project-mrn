# BASEGAME AI ARCHITECTURE SPECIFICATION
## 공동 아키텍처 명세 (Claude 제안 + GPT 보강안 통합)
### 버전: 0.2 JOINT DRAFT | 날짜: 2026-03-27
### 레이블: [EXP] — Phase 1 착수 기준, Phase 3~4는 추후 확정

---

## 0. 목적

엔진을 수정하지 않고, Claude와 GPT가 각자 JSON/모듈만 교체해서
서로 다른 전략을 독립적으로 실험할 수 있는 구조를 만든다.

핵심 원칙:
> **"설정은 외부화한다. 해석은 코드로 남긴다."**

---

## 1. 외부화할 것 vs 코드로 남길 것

### 1.1 JSON / 설정 파일로 외부화하기 좋은 것

| 대상 | 현재 위치 | 분리 파일 |
|------|-----------|-----------|
| 6축 가중치 (expansion/economy/...) | `PROFILE_WEIGHTS` 딕셔너리 | `profiles/policy_weights_*.json` |
| 16인물 base score | `character_values` 클래스 변수 | `profiles/character_values_*.json` |
| 생존 임계값 상수 | `survival_common.py` 매직넘버 | `profiles/survival_threshold_*.json` |
| 캐릭터 그룹 집합 | `policy_groups.py` 상수 | `profiles/character_groups.json` |
| 지목 리스크 상수 | `MARK_ACTOR_BASE_RISK` | `profiles/mark_risk.json` |
| 지목 추측 파라미터 | `MARK_GUESS_*` 상수들 | `profiles/mark_risk.json` |

### 1.2 코드로 반드시 남겨야 하는 것

다음은 "값"이 아니라 "해석 로직"이므로 JSON 외부화 금지:

- 아전 overlap kill window 판단
- 객주 lap engine window 판단
- 박수/만신 shard checkpoint 전환 로직
- 사기꾼 SWINDLE_FAIL 생존성 게이트
- leader denial snapshot 복합 판단
- overlap / revisit / finisher window 복합 분기
- 탐관오리/어사 양면 카드 관계 처리

**규칙**: JSON에는 `float`, `int`, `str`, `list[str]` 만 넣는다.
함수 호출이나 조건 분기가 필요하면 코드로 남긴다.

---

## 2. 전체 구조 (합의안)

```
policy/
  profile/
    spec.py                  ← PolicyProfileSpec (frozen dataclass)
    registry.py              ← PROFILE_REGISTRY
    presets.py               ← 기본 프리셋 등록
  survival/
    strategy.py              ← SurvivalStrategy 인터페이스
    thresholds.py            ← SurvivalThresholdSpec (frozen dataclass)
    orchestrator.py          ← 기존 survival_common.py 흡수
    guards.py                ← 액션 생존 가드 함수들
  context/
    turn_context.py          ← TurnContext (frozen dataclass)
    builder.py               ← TurnContextBuilder
    economy_features.py      ← 경제 feature 계산
    danger_features.py       ← 위협 feature 계산
    token_features.py        ← 코인/토큰 feature 계산
    race_features.py         ← 레이스 포지션 feature 계산
  character_eval/
    registry.py              ← CHARACTER_EVALUATOR_REGISTRY
    asa_tamgwan.py           ← 어사/탐관오리 페어 평가기
    jagaek_sanjeok.py        ← 자객/산적 페어
    chuno_escape.py          ← 추노꾼/탈출노비 페어
    pabal_ajeon.py           ← 파발꾼/아전 페어
    doctrine_pair.py         ← 교리연구관/감독관 페어
    shaman_pair.py           ← 박수/만신 페어
    geo_pair.py              ← 객주/중매꾼 페어
    builder_swindler.py      ← 건설업자/사기꾼 페어
  decision/
    draft.py                 ← DraftStrategy 인터페이스 + 구현
    movement.py              ← MovementStrategy
    purchase.py              ← PurchaseGateStrategy
    lap_reward.py            ← LapRewardStrategy
    mark_target.py           ← MarkTargetStrategy
    marker_flip.py           ← MarkerFlipStrategy
  asset/
    policy_asset.py          ← PolicyAsset (조합 자산)
    factory.py               ← PolicyAssetFactory
  registry/
    profile_registry.py      ← ProfileRegistry
    strategy_registry.py     ← STRATEGY_REGISTRY (stable key)

profiles/
  policy_weights_control.json
  policy_weights_balanced.json
  policy_weights_v3_gpt.json
  policy_weights_v3_claude.json
  character_values_default.json
  survival_threshold_default.json
  survival_threshold_aggressive.json
  character_groups.json
  mark_risk.json

policy_profiles/
  v3_gpt.json
  v3_claude.json
  control.json
  balanced.json
```

---

## 3. 핵심 인터페이스 설계

### 3.1 PolicyProfileSpec (설정 데이터)

```python
@dataclass(frozen=True, slots=True)
class PolicyProfileSpec:
    """설정값 전용 — 해석 로직 없음"""
    name: str
    weights: PolicyWeightProfile
    character_values: CharacterValueProfile
    character_groups: CharacterGroupProfile
    mark_risk: MarkRiskProfile
    # strategy는 registry key로만 참조
    survival_strategy_key: str = "survival/default_v1"
    lap_reward_strategy_key: str = "lap_reward/base_v1"
    purchase_gate_strategy_key: str = "purchase_gate/base_v1"
    draft_strategy_key: str = "draft/base_v1"
```

### 3.2 STRATEGY_REGISTRY (stable key 방식)

```python
# registry/strategy_registry.py
STRATEGY_REGISTRY: dict[str, type] = {
    # Survival
    "survival/default_v1":        DefaultSurvivalStrategy,
    "survival/v3_gpt_v1":         V3GptSurvivalStrategy,
    "survival/v3_claude_v1":      V3ClaudeSurvivalStrategy,
    # Lap Reward
    "lap_reward/base_v1":         BaseLapRewardStrategy,
    "lap_reward/control_v1":      ControlLapRewardStrategy,
    "lap_reward/token_opt_v1":    TokenOptLapRewardStrategy,
    "lap_reward/v3_gpt_v1":       V3GptLapRewardStrategy,
    # Purchase Gate
    "purchase_gate/base_v1":      BasePurchaseGate,
    "purchase_gate/v3_gpt_v1":    V3GptPurchaseGate,
    # Draft
    "draft/base_v1":              BaseDraftStrategy,
    "draft/v3_gpt_v1":            V3GptDraftStrategy,
    # Character Evaluators
    "char_eval/asa_tamgwan_v1":   AsaTamgwanEvaluator,
    "char_eval/shaman_pair_v1":   ShamanPairEvaluator,
}
```

규칙:
- key 형식: `{domain}/{name}_{version}`
- 버전 번호는 단조 증가
- 삭제 금지, deprecated 처리만 허용

### 3.3 TurnContext (typed context)

```python
@dataclass(frozen=True, slots=True)
class TurnContext:
    """
    한 턴의 공개 정보 스냅샷.
    dict 대신 typed 구조 — key drift / 오타 방지.
    analysis pipeline의 feature와 필드명 공유.
    """
    # 경제
    own_cash: int
    own_tiles: int
    own_shards: int
    own_hand_coins: int
    cash_margin_vs_best: float
    tiles_margin_vs_best: float
    # 위협
    rent_exposure_prob: float
    rent_exposure_peak: float
    two_turn_lethal_prob: float
    burden_cleanup_cost: float
    active_drain_pressure: float
    # 이동/랩
    next_lap_prob_1t: float
    next_lap_prob_2t: float
    land_f_prob: float
    # 코인/토큰
    placeable_own_tiles: int
    token_window_score: float
    # 레이스
    is_leader: bool
    leader_gap: float
    f_remaining: float
    # 지목/마커
    controller_need: float
    money_distress: float
    survival_urgency: float
    # 메타
    round_index: int
    alive_count: int
    notes: tuple[str, ...] = ()
```

### 3.4 SurvivalStrategy (독립 축)

```python
class SurvivalStrategy(ABC):
    """
    PolicyProfile과 독립적으로 교체 가능한 생존 판단 모듈.
    같은 profile + 다른 survival 조합 실험 지원.
    """
    @abstractmethod
    def build_orchestrator(
        self, 
        signals: SurvivalSignals,
        context: TurnContext
    ) -> SurvivalOrchestratorState: ...

    @abstractmethod
    def evaluate_character(
        self,
        character_name: str,
        context: TurnContext,
        orchestrator: SurvivalOrchestratorState
    ) -> CharacterSurvivalAdvice: ...
```

### 3.5 PolicyAsset (조합 자산)

```python
@dataclass(slots=True)
class PolicyAsset:
    """
    ProfileSpec + SurvivalStrategy + DecisionBundle의 조합.
    JSON에서 key로 조립, Factory가 실제 객체 주입.
    """
    spec: PolicyProfileSpec
    survival: SurvivalStrategy
    lap_reward: LapRewardStrategy
    purchase_gate: PurchaseGateStrategy
    draft: DraftStrategy
    character_evaluators: dict[str, CharacterEvaluator]
    context_builder: TurnContextBuilder
```

---

## 4. 단계별 마이그레이션 플랜

### Phase 1 — 값 외부화 (즉시 착수, 엔진 무수정)
```
대상:
  PROFILE_WEIGHTS → profiles/policy_weights_*.json
  character_values → profiles/character_values_*.json
  MARK_ACTOR_BASE_RISK 등 → profiles/mark_risk.json
  SurvivalThreshold 매직넘버 → profiles/survival_threshold_*.json

새 파일:
  policy/profile/spec.py
  policy_profile_creator.py  (board_layout_creator.py 패턴)
  profiles/*.json

하위 호환:
  HeuristicPolicy는 기존처럼 동작
  JSON 로드로만 교체, 로직 변경 없음
```

### Phase 2 — TurnContext + Registry 도입
```
대상:
  context: dict → TurnContext frozen dataclass
  클래스명 문자열 → STRATEGY_REGISTRY key
  생존 임계값 → SurvivalThresholdSpec 주입

새 파일:
  policy/context/turn_context.py
  policy/context/builder.py
  policy/registry/strategy_registry.py
  policy/survival/thresholds.py

하위 호환:
  _generic_survival_context() 반환값을 TurnContext로 병행 허용
  기존 dict 접근은 점진적으로 교체
```

### Phase 3 — Strategy 분리 + CharacterEvaluator
```
대상:
  choose_lap_reward() → LapRewardStrategy.choose()
  choose_purchase_tile() → PurchaseGateStrategy.should_buy()
  _character_score_breakdown_v2() → CharacterEvaluator + DraftStrategy
  character_eval/ 페어별 evaluator 생성

새 파일:
  policy/decision/*.py
  policy/character_eval/*.py
  policy/survival/strategy.py

주의:
  이 단계부터 ai_policy.py 수정 불가피
  Phase 3 착수 전 양측 합의 필요
```

### Phase 4 — PolicyAsset + Factory 완성
```
대상:
  PolicyAsset 조합 구조 완성
  PolicyAssetFactory JSON 로더
  asset hash 로깅 (실험 재현성)

새 파일:
  policy/asset/policy_asset.py
  policy/asset/factory.py

효과:
  JSON 파일만 교체해서 전략 조합 실험
  Claude/GPT 각자 JSON만 수정, ai_policy.py 충돌 없음
```

---

## 5. 프로파일 JSON 예시

### `policy_profiles/v3_gpt.json`

```json
{
  "name": "heuristic_v3_gpt_exp",
  "weights": {
    "expansion": 1.68, "economy": 1.55, "disruption": 1.28,
    "meta": 1.18, "combo": 2.15, "survival": 1.18
  },
  "character_values": {
    "어사": 6.0, "탐관오리": 7.5, "자객": 7.2, "산적": 7.0,
    "추노꾼": 6.8, "탈출 노비": 6.2, "파발꾼": 7.9, "아전": 7.0,
    "교리 연구관": 6.4, "교리 감독관": 6.4,
    "박수": 7.2, "만신": 6.9,
    "객주": 7.6, "중매꾼": 7.4, "건설업자": 7.8, "사기꾼": 7.7
  },
  "survival_strategy_key": "survival/v3_gpt_v1",
  "lap_reward_strategy_key": "lap_reward/v3_gpt_v1",
  "purchase_gate_strategy_key": "purchase_gate/v3_gpt_v1",
  "draft_strategy_key": "draft/v3_gpt_v1"
}
```

---

## 6. 우선순위 및 ROI

| 분리 항목 | 난이도 | 충돌 감소 효과 | 실험 가속 | 우선순위 |
|-----------|--------|---------------|-----------|----------|
| PROFILE_WEIGHTS 외부화 | 낮음 | 높음 | 높음 | **Phase 1** |
| character_values 외부화 | 낮음 | 중간 | 중간 | **Phase 1** |
| survival threshold 외부화 | 낮음 | 높음 | 높음 | **Phase 1** |
| STRATEGY_REGISTRY 도입 | 낮음 | 높음 | 낮음 | **Phase 2** |
| TurnContext dataclass | 중간 | 중간 | 중간 | **Phase 2** |
| SurvivalStrategy 독립 | 중간 | 높음 | 높음 | **Phase 2** |
| LapReward/Purchase 분리 | 중간 | 높음 | 높음 | Phase 3 |
| CharacterEvaluator 분리 | 높음 | 매우 높음 | 매우 높음 | Phase 3 |
| PolicyAsset + Factory | 높음 | 매우 높음 | 매우 높음 | Phase 4 |

---

## 7. 이 설계가 주는 것

1. **충돌 방지**: Claude/GPT 각자 JSON만 수정 → ai_policy.py 충돌 없음
2. **실험 속도**: JSON 파일 교체만으로 새 조합 즉시 실험
3. **추적 가능성**: asset hash 로깅 → 어떤 설정이 어떤 결과인지 추적
4. **테스트 분리**: 각 Strategy/Evaluator를 독립 유닛테스트
5. **롤백 용이**: JSON 버전만 바꾸면 롤백
6. **교차 실험**: v3_gpt 가중치 + v3_claude 생존전략 조합 실험 가능

## 8. 이 설계가 주지 않는 것 (한계)

- 게임 메카닉 이해는 코드에 남음 — JSON으로 완전 대체 불가
- Phase 3 이후는 ai_policy.py 수정 불가피 — 착수 전 양측 합의 필요
- CharacterEvaluator 분리는 현재 3000줄 ai_policy.py의 대수술

