# survival_common.py

공용 생존 규칙 모듈이다. AI 정책 내부에 흩어져 있던 생존 판단 임계값과 공통 가드를 이 파일에 모아 관리한다.

## 목적
- 공통 생존 신호(`reserve`, `money_distress`, `two_turn_lethal_prob`, cleanup 비용)를 한 곳에서 다룬다.
- 개별 액션(구매, 이동, 잔꾀, 사기꾼 인수)이 같은 생존 기준을 공유하게 한다.
- 향후 임계값 조정 시 `ai_policy.py` 곳곳을 동시에 고칠 필요를 줄인다.

## 주요 구성
- `SurvivalSignals`: AI가 계산한 생존 신호의 표준 구조체
- `ActionGuardContext`: 공통 액션 생존 가드 입력 구조체
- `SwindleGuardDecision`: 사기꾼 인수 판단 결과 구조체
- `build_action_guard_context(...)`: 일반 액션용 reserve floor 계산
- `is_action_survivable(...)`: 비용 지불 후 생존 가능 여부 판정
- `swindle_operating_reserve(...)`: 사기꾼 전용 운영 reserve 계산
- `evaluate_swindle_guard(...)`: 사기꾼 인수 허용/차단 및 이유 판정

## 설계 원칙
- 행동 기대값보다 생존을 우선한다.
- profile별 취향보다 공통 생존 가드가 먼저 적용된다.
- cleanup/2턴 lethal/public cleanup 같은 공용 위협은 공통 모듈에서 계산 규칙을 유지한다.


## SurvivalOrchestratorState
- `build_survival_orchestrator(signals)` builds a survival-first orchestration state from common signals.
- `evaluate_character_survival_priority(...)` applies heavy survival-first bonuses/penalties before profile-specific character scoring.
- Intent: survival is treated as a first-pass veto/weighting layer, not a late additive tweak.


## Update note
- survival_common now provides character survival advice (severity, bias, hard-block hint).
- ai_policy consumes this advice as a first-stage input; only true-suicide cases receive a hard-block hint, while final selection remains policy-owned.
