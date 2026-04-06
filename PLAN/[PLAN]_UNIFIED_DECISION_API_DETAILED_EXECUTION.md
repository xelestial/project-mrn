# [PLAN] Unified Decision API 상세 실행계획

Status: ACTIVE  
Updated: 2026-04-04  
Owner: GPT  
Depends On: [PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md)

## 1) 목표

AI와 인간 플레이어의 결정을 모두 동일한 API 형식으로 처리한다.
- 단일 계약: `DecisionRequest -> DecisionResponse`
- 단일 진입점: `DecisionGateway`
- 단일 감사 로그: `decision_requested / decision_resolved / decision_timeout_fallback`

## 2) 범위

포함:
- 서버 런타임 결정 라우팅 구조 개편
- 엔진 의사결정 호출 경계 추상화
- 프론트 프롬프트 소비 구조 정렬
- 테스트/회귀/관측 체계

제외:
- Unity 클라이언트 구현
- 계정/인증 확장
- 인프라 배포 자동화

## 3) 실행 원칙

- 엔진은 resolver(human/ai)를 직접 분기하지 않는다.
- 모든 request는 `request_id` 기준 멱등 처리한다.
- 결정 이벤트는 도메인 이벤트보다 먼저 기록한다.
- 기존 경로는 `decision_api_mode=legacy|unified` 플래그로 병행 운영한다.

## 4) 현재 요청 타입 전수 목록 (이행 대상)

현재 `GPT/viewer/human_policy.py` 기준:
- `movement`
- `runaway_step_choice`
- `lap_reward`
- `draft_card`
- `final_character`
- `trick_to_use`
- `purchase_tile`
- `hidden_trick_card`
- `mark_target`
- `coin_placement`
- `geo_bonus`
- `doctrine_relief`
- `active_flip`
- `specific_trick_reward`
- `burden_exchange`

## 5) 워크스트림

## WS-A 계약/스키마 고정

목표:
- request/response envelope를 고정하고 파서 호환 윈도우를 명확히 한다.

작업:
- `packages/runtime-contracts/ws/schemas`에 `decision_request_v1`, `decision_response_v1` 추가
- `request_type` enum 소스 고정
- 서버/프론트 fixture 동기화
- 예제 payload를 `packages/runtime-contracts/ws/examples`에 추가

완료조건:
- schema validation 통과
- 예제 fixture 기반 파서 테스트 통과

## WS-B 서버 게이트웨이 도입

목표:
- RuntimeService가 직접 human bridge를 호출하지 않고 gateway를 통해 처리한다.

작업:
- 신규 파일 추가:
  - `apps/server/src/services/decision_gateway.py`
  - `apps/server/src/services/decision_router.py`
  - `apps/server/src/services/decision_providers/human_provider.py`
  - `apps/server/src/services/decision_providers/ai_provider.py`
  - `apps/server/src/services/decision_providers/fallback_provider.py`
- `runtime_service.py`에서 `_ServerHumanPolicyBridge` 의존 축소
- `prompt_service.py`는 human provider 하위 lifecycle 서비스로 역할 축소
- `stream.py` decision 수신 경로를 gateway 상태와 일치시키도록 보강

완료조건:
- human/ai/fallback 모두 gateway 경유
- `decision_requested -> decision_resolved` 이벤트 발행 확인

## WS-C 엔진 포트 마이그레이션

목표:
- `choose_*` 직접 접근을 `DecisionPort` 추상화로 대체한다.

작업:
- `GPT/engine.py`에 `DecisionPort` 주입점 추가
- 우선순위 순차 전환:
  - 1차: `draft_card`, `final_character`, `movement`, `trick_to_use`, `purchase_tile`
  - 2차: `mark_target`, `lap_reward`, `active_flip`, `runaway_step_choice`
  - 3차: `coin_placement`, `geo_bonus`, `doctrine_relief`, `specific_trick_reward`, `burden_exchange`
- 기존 policy fallback은 adapter로 유지

완료조건:
- 엔진 경로에서 resolver 타입 분기 제거
- request/response만 소비하도록 정리

## WS-D 프론트 처리 정렬

목표:
- prompt UI가 gateway의 canonical request만 소비하도록 맞춘다.

작업:
- `apps/web/src/domain/selectors/promptSelectors.ts`를 canonical 필드 우선으로 단순화
- `PromptOverlay.tsx`에서 request_type별 렌더만 담당하고 fallback 로직 제거
- `App.tsx`에서 actionable prompt / passive observer 분리를 gateway ack 기준으로 통일
- lane 분리 유지:
  - core event lane
  - prompt/decision lane
  - system lane

완료조건:
- 인간 좌석 prompt 처리와 관전자 표시가 충돌하지 않음
- watchdog/error가 core 진행 카드를 덮지 않음

## WS-E 테스트/회귀/관측

목표:
- 전환 중 회귀를 막고 원인 추적 가능성을 높인다.

작업:
- 서버 테스트:
  - `apps/server/tests/test_decision_gateway.py`
  - `apps/server/tests/test_runtime_service.py` 확장
  - 타임아웃/중복 응답/오래된 request 처리 테스트
- 엔진 테스트:
  - `GPT/test_prompt_contract.py` 확장
  - 요청 타입별 round-trip 테스트
- 프론트 테스트:
  - `apps/web/src/domain/selectors/*.spec.ts`
  - `PromptOverlay` request_type 커버리지
- E2E:
  - 1 human + 3 AI 시나리오
  - 최소 1회씩 모든 request_type 발생하도록 fixture 실행

완료조건:
- 필수 테스트 전부 green
- 회귀 체크리스트 전부 pass

## 6) PR 단위 실행 순서

PR-01:
- WS-A 스키마/예제/타입 추가
- legacy 파서 호환 유지

PR-02:
- WS-B `DecisionGateway` 골격 + router + provider 인터페이스
- runtime_service 연결 최소 경로

PR-03:
- WS-B human provider 연결
- prompt_service 연동 및 timeout/fallback 경로 이관

PR-04:
- WS-B ai provider 연결
- ai도 request/response 경유하도록 통일

PR-05:
- WS-C 1차 엔진 전환 (draft/final/movement/trick/purchase)

PR-06:
- WS-C 2차 엔진 전환 (mark/lap/active_flip/runaway)

PR-07:
- WS-C 3차 엔진 전환 (coin/geo/doctrine/specific/burden)

PR-08:
- WS-D 프론트 prompt selector/overlay 정렬

PR-09:
- WS-D lane 고정 + 상태 표시 정리

PR-10:
- WS-E 서버/엔진/프론트 테스트 확장

PR-11:
- WS-E E2E 혼합 좌석 시나리오 + 회귀 문서 업데이트

PR-12:
- `decision_api_mode=unified` 기본값 전환
- `legacy` 경로는 deprecation 상태로 유지

## 7) 단계별 게이트 (진입/종료 조건)

P0 진입 조건:
- 기존 빌드/테스트 기준선 확보

P0 종료 조건:
- 계약 스키마 freeze + 호환 파서 통과

P1 종료 조건:
- 서버 runtime에서 human/ai/fallback 공통 gateway 경로 확인

P2 종료 조건:
- 엔진 결정 호출 100%가 DecisionPort 경유

P3 종료 조건:
- 1 human + 3 AI 혼합 플레이에서 request 처리 멈춤/순서 역전/중복 처리 없음

## 8) 리스크와 롤백

리스크:
- 대규모 경계 변경으로 진행 중 prompt 동작 회귀
- 이벤트 순서 체감 악화

대응:
- feature flag 운영:
  - `decision_api_mode=legacy` 즉시 롤백 가능
- request_id 멱등 강제
- PR별 smoke 기준 미달 시 병합 금지

## 9) 산출물

필수 산출물:
- 계약 문서/스키마/예제
- 서버 gateway/provider 코드
- 엔진 DecisionPort 적용
- 프론트 prompt 소비 정렬
- 테스트 리포트

문서 업데이트 대상:
- [PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md)
- [PLAN/PLAN_STATUS_INDEX.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/PLAN/PLAN_STATUS_INDEX.md)
- [docs/backend/log-engine-generation-audit.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/docs/backend/log-engine-generation-audit.md)

## 10) 즉시 시작 작업 (다음 실행 묶음)

1. PR-01 착수:
- runtime-contract schema/fixtures 추가
- 서버/프론트 타입 동기화

2. PR-02 착수:
- `DecisionGateway`와 provider 인터페이스 생성
- runtime_service 연결 포인트 추가

3. PR-03 착수:
- human provider + prompt lifecycle 이관
- timeout/fallback 이벤트 순서 고정 테스트 추가
## 2026-04-04 Progress Update (P0-1)

- Implemented in server runtime bridge:
  - emit `decision_requested` when prompt is registered.
  - emit `decision_resolved` on:
    - accepted decision
    - timeout fallback
    - parser-error fallback.
- Implemented in stream timeout lane:
  - enforce `decision_resolved` before `decision_timeout_fallback`.
- Added/updated tests:
  - `apps/server/tests/test_runtime_service.py`
    - request/resolve ordering assertion for accepted path.
    - timeout ordering assertion (`requested < resolved < timeout_fallback`).
    - parser-error fallback assertion (single resolved emission).
  - `apps/server/tests/test_stream_api.py`
    - timeout lane ordering assertion (`resolved` < `timeout_fallback` seq).
  - web selector/label tests updated for decision events visibility.
  - `apps/server/tests/test_runtime_contract_examples.py`
    - added ordered sequence fixture validation:
      - `decision_requested -> decision_resolved -> player_move`
      - `decision_requested -> decision_resolved -> decision_timeout_fallback -> turn_end_snapshot`
  - `apps/web/src/domain/selectors/streamSelectors.spec.ts`
    - added mixed human-play regression case:
      - decision flow stays visible in theater (`prompt` lane)
      - core turn progression (`dice_roll`, `player_move`, `landing_resolved`) remains visible

## Remaining P0-1 Actions

1. Verify CI execution result for `backend-decision-contract-tests` workflow after push.
2. Continue P0-2 lane UX refinement in live human-play screen integration.
3. Keep React prompt lifecycle aligned with canonical decision events so resolved non-local prompts cannot remain open from `prompt`-only state.

## Local Validation Note

- In the current local environment, FastAPI-gated stream API tests are partially skipped.
- Runtime bridge/unit coverage is active and passing.
- Non-timeout stream branch validation will be finalized via:
  - CI run with FastAPI-enabled test matrix, and
  - follow-up local verification when full backend test dependencies are available.

## 2026-04-05 Progress Update (P0-1 -> P0-2 bridge)

- React selector layer now consumes canonical decision-close signals in addition to `decision_ack`.
  - `selectActivePrompt(...)` closes prompt state when later messages include:
    - `decision_resolved`
    - `decision_timeout_fallback`
- Situation summary no longer treats prompt/system chatter as the main narrative event.
  - filtered from headline selection:
    - `prompt`
    - `decision_ack`
    - prompt-lane decision events
    - `parameter_manifest`
    - runtime `error` messages
- Added regression coverage in:
  - `apps/web/src/domain/selectors/promptSelectors.spec.ts`
  - `apps/web/src/domain/selectors/streamSelectors.spec.ts`
- Local validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts`
  - passed (`18 passed`)

## 2026-04-05 UI Follow-through Note

- P0-2 follow-through started in the React screen:
  - a dedicated `CoreActionPanel` is now mounted under the stage panel
  - latest public/non-local turn action is surfaced as a hero card
  - recent public actions are surfaced as a compact feed
- Legacy duplicated action strip/banner UI is hidden so the runtime contract now maps to a single visible public-action lane.
- Local validation:
  - `npm run build`
  - passed (`apps/web`)

## 2026-04-06 Progress Update (runtime wrapper unification)

- Added `apps/server/src/services/decision_gateway.py` as the canonical runtime decision publisher.
- Server runtime no longer keeps AI seats fully outside the decision contract.
  - `RuntimeService` now mounts `_ServerDecisionPolicyBridge` instead of a human-only bridge.
  - Human seats still use prompt/request-response flow.
  - AI seats now also emit:
    - `decision_requested`
    - `decision_resolved`
    through the same server-side gateway boundary.
- Added provider tagging:
  - `provider="human"`
  - `provider="ai"`
- This closes the previous "AI direct-call bypass" gap at the runtime boundary.
- Remaining P0-1 work is now narrower:
  1. move more request-type serialization/context logic out of the bridge and into typed provider classes
  2. migrate engine-side `choose_*` callsites toward a real `DecisionPort`
  3. expand backend tests beyond the current runtime-wrapper slice

## 2026-04-06 Progress Update (canonical payload builders)

- `DecisionGateway` now also owns shared payload builders for:
  - `decision_ack`
  - `decision_requested`
  - `decision_resolved`
  - `decision_timeout_fallback`
- The websocket route timeout/ack path now uses those builders too.
- Result:
  - human timeout fallback emission no longer drifts away from the runtime gateway shape
  - human websocket `decision_ack` now also carries `provider="human"` consistently
- Updated coverage:
  - `apps/server/tests/test_runtime_service.py`
  - `apps/server/tests/test_stream_api.py`
- Remaining P0-1 work is now:
  1. typed provider cleanup so bridge mapping logic is less string-heavy
  2. engine-side `DecisionPort` migration
  3. broader stream API coverage in environments with full FastAPI test support

## 2026-04-06 Progress Update (canonical request-type resolver)

- The runtime bridge no longer owns its own request-type mapping table.
- `apps/server/src/services/decision_gateway.py` now owns:
  - `METHOD_REQUEST_TYPE_MAP`
  - `decision_request_type_for_method(...)`
- `apps/server/src/services/runtime_service.py` now uses that shared resolver when AI-seat choices are normalized into decision lifecycle events.
- Result:
  - one fewer bridge-local string table
  - lower drift risk between AI-seat request publication and the canonical gateway contract
- Updated coverage:
  - `apps/server/tests/test_runtime_service.py`
- Remaining P0-1 work is now:
  1. typed provider classes so human / AI dispatch logic is less concentrated in `_ServerDecisionPolicyBridge`
  2. engine-side `DecisionPort` migration
  3. broader stream API coverage in environments with full FastAPI test support

## 2026-04-06 Progress Update (gateway lifecycle helper convergence)

- `DecisionGateway` now also centralizes the repeated publish steps for:
  - `decision_requested`
  - `decision_resolved`
  - `decision_timeout_fallback`
- This means human and AI flows now share:
  - canonical payload builders
  - canonical request-type mapping
  - canonical lifecycle publish helpers
- Result:
  - one fewer source of branch-local lifecycle drift inside the gateway itself
  - narrower remaining work before a future typed `DecisionPort` migration
- Remaining P0-1 work is now:
  1. typed provider classes so human / AI dispatch logic is less concentrated in `_ServerDecisionPolicyBridge`
  2. engine-side `DecisionPort` migration
  3. broader stream API coverage in environments with full FastAPI test support

## 2026-04-06 Progress Update (specialty method drift guard)

- Added explicit runtime coverage for AI `choose_mark_target`.
- This now guards another specialty decision seam so AI-side canonical publication is verified for:
  - request type: `mark_target`
  - lifecycle:
    - `decision_requested`
    - `decision_resolved`
- Result:
  - branch-local drift risk is lower for non-movement, non-purchase decisions too
- Remaining P0-1 work is now:
  1. typed provider classes so human / AI dispatch logic is less concentrated in `_ServerDecisionPolicyBridge`
  2. engine-side `DecisionPort` migration
  3. continue extending specialty-method decision coverage
