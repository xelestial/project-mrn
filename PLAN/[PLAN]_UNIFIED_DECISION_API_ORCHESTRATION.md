# [PLAN] Unified Decision API Orchestration (AI + Human)

Status: ACTIVE  
Updated: 2026-04-04  
Owner: GPT

Detailed execution: [PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md)

## 1) Goal

엔진이 AI/인간을 구분해서 직접 호출하지 않고, **동일한 요청-처리 API 계약**으로만 의사결정을 수행하도록 전환한다.

핵심 원칙:
- 모든 결정은 `DecisionRequest -> DecisionResponse`로 처리
- 인간/AI는 라우팅만 다르고 계약은 동일
- 엔진은 “누가 결정했는지”를 모르고 결과만 소비

---

## 2) Why This Is Needed

현재는 다음 문제가 혼재:
- 엔진 내부 `choose_*` 호출 + human bridge 우회 로직 혼합
- 프롬프트/결정/이벤트가 섞여 사용자 체감 순서가 흔들림
- 룰 변경 시 엔진/서버/UI 동시 수정이 빈번

이 계획은 이를 **단일 결정 파이프라인**으로 통일해 결합도를 낮춘다.

---

## 3) Target Architecture

## 3.1 Core Components

1. `DecisionGateway` (new, server)
- 엔진에서 발생한 의사결정 요청을 수신
- 요청 저장, 라우팅, 타임아웃, fallback, 결과 검증 담당

2. `DecisionRouter` (new, server)
- seat 타입 기준 라우팅
  - human seat -> WS prompt channel
  - ai seat -> AI decision worker

3. `DecisionProvider` interface (new)
- `request_decision(request) -> response`
- 구현체:
  - `HumanDecisionProvider`
  - `AiDecisionProvider`
  - `FallbackDecisionProvider`

4. `DecisionLedger` (new)
- `decision_requested`, `decision_resolved`, `decision_timeout_fallback`를 순서 보존으로 기록
- 로그/리플레이/감사 공통 소스

## 3.2 Engine Boundary

엔진은 아래 포트만 사용:
- `DecisionPort.request(request: DecisionRequest) -> DecisionResponse`

즉, `policy.choose_*` 직접 접근을 점진 제거하고 `DecisionPort`를 통한 호출로 치환한다.

---

## 4) Unified Contract (v1)

## 4.1 DecisionRequest
- `request_id`
- `request_type`
- `session_id`
- `player_id`
- `round_index`
- `turn_index`
- `step_index`
- `legal_choices[]` (`choice_id`, `label`, `value`)
- `public_context`
- `timeout_ms`
- `fallback_policy`

## 4.2 DecisionResponse
- `request_id`
- `choice_id`
- `resolver` (`human` | `ai` | `fallback`)
- `latency_ms`
- `resolved_at_ms`
- `validation` (`accepted` | `rejected`)
- `reason` (optional)

## 4.3 Event Ordering Rule

결정 관련 고정 순서:
1. `decision_requested`
2. (`prompt` and/or `ai_decision_started`)
3. `decision_resolved` or `decision_timeout_fallback`
4. 그 다음 엔진 도메인 이벤트 진행 (`dice_roll`, `player_move`, ...)

---

## 5) Scope Of Change

## 5.1 Backend (required)
- `apps/server/src/services/runtime_service.py`
  - 현재 `_ServerHumanPolicyBridge` 중심 경로를 `DecisionGateway` 중심으로 전환
- `apps/server/src/services/prompt_service.py`
  - human provider 하위 서비스로 역할 축소
- `apps/server/src/routes/stream.py`
  - prompt/decision 수신은 유지하되 gateway 상태와 동기화
- 신규 파일:
  - `apps/server/src/services/decision_gateway.py`
  - `apps/server/src/services/decision_router.py`
  - `apps/server/src/services/decision_providers/*.py`

## 5.2 Engine/GPT (required)
- `GPT/engine.py`
  - 의사결정 호출부를 `DecisionPort`로 추상화
- `GPT/viewer/human_policy.py`
  - 점진 축소: UI 전용 prompt 생성 유틸 또는 provider 어댑터로 이동
- `GPT/policy/*`
  - AI 의사결정을 provider로 감싸 동일 응답 포맷 반환

## 5.3 Frontend (required)
- `apps/web/src/App.tsx`, `PromptOverlay.tsx`, selector들
  - prompt를 “human provider가 받은 DecisionRequest”로 표현
  - ack/error와 core-event lane 분리 유지

## 5.4 Contracts (required)
- `packages/runtime-contracts/ws/schemas/*`
- 요청/응답 예제 fixture + 역직렬화 테스트 추가

---

## 6) DI Principle For Mark/Fortune/Weather

본 계획에서 DI는 2단계로 분리:

1. **Decision DI (이번 계획의 필수)**
- 누가 결정을 내리는지(인간/AI/fallback) 완전 주입형

2. **Rule Behavior DI (병행/후속)**
- mark/fortune/weather 자체 효과를 provider/script registry로 전환
- 이 문서는 우선 Decision DI를 완성하고, Rule DI는 별도 트랙으로 연결

---

## 7) Delivery Phases

## P0 - Contract Freeze + Compatibility Layer
- DecisionRequest/Response 스키마 확정
- 기존 human policy path를 compatibility adapter로 유지
- 기존 프론트가 깨지지 않도록 alias window 유지

## P1 - Gateway First Runtime
- RuntimeService에서 DecisionGateway 도입
- human/ai/fallback 모두 gateway를 통해 처리
- `decision_requested/resolved` 이벤트 발행

## P2 - Engine Port Migration
- 엔진 주요 의사결정 포인트를 DecisionPort 호출로 치환
- `choose_*` 직접 호출 제거(우선순위 높은 플로우부터)

## P3 - Hardening
- 순서 불변 테스트
- 타임아웃/fallback 회귀 테스트
- 1 human + 3 AI 장기 플레이 테스트

---

## 8) Test Plan

필수 테스트:
- 단일 요청 lifecycle:
  - requested -> resolved
  - requested -> timeout_fallback
- 라우팅:
  - 같은 request_type이 human/ai 모두 동일 schema로 처리
- 순서:
  - 결정 이벤트가 도메인 이벤트 앞에 고정 배치
- 회귀:
  - 기존 prompt request_type 전체 커버리지 유지

파일 후보:
- `apps/server/tests/test_decision_gateway.py`
- `apps/server/tests/test_runtime_service.py`
- `apps/web/src/domain/selectors/*.spec.ts`
- `GPT/test_prompt_contract.py` (확장)

---

## 9) Risks And Guardrails

리스크:
- 대규모 변경으로 진행 중 UX 회귀 가능

가드레일:
- compatibility adapter 기간 유지
- feature flag:
  - `decision_api_mode = legacy | unified`
- 단계별 머지(계약 -> 서버 -> 엔진 -> 프론트)

---

## 10) Definition Of Done

- AI/인간 모두 동일 DecisionRequest/Response 계약으로 처리
- 엔진이 resolver 타입(human/ai)을 직접 분기하지 않음
- 결정 관련 로그가 순서적으로 재현 가능
- 기존 룰 플로우(드래프트/지목/운세/날씨/이동/구매/턴 종료)가 unified path에서 동일 동작
