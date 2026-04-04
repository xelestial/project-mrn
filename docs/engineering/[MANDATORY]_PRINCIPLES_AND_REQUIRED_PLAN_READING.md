# [MANDATORY] Principles And Required Plan Reading

Status: ACTIVE  
Updated: 2026-04-04  
Scope: engine / server / web / contracts

## CI Guardrail (Fixed)

These mandatory rules are enforced by:

- `.github/workflows/plan-policy-gate.yml`
- `tools/encoding_gate.py`
- `tools/plan_policy_gate.py`

Local checks:

- `python tools/encoding_gate.py`
- `python tools/plan_policy_gate.py`

## 1) Mandatory Reading Before Any Implementation

Read in this order before starting implementation:

1. `docs/Game-Rules.md`
2. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
3. `PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md`
4. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
5. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
6. `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
7. `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
8. `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
9. `PLAN/PLAN_STATUS_INDEX.md`

## 2) Mandatory Engineering Principles

## P-01 Encoding

- CP-949 사용 금지.
- UTF-8(가능하면 UTF-8 with LF) 사용.
- 문서/코드/CSV/로그 샘플 모두 동일 인코딩 유지.

## P-02 DI and Boundary

- AI/인간 처리 분기는 엔진 내부 분기 금지, API/Provider 경계에서 처리.
- `DecisionRequest -> DecisionResponse` 계약을 단일 진입점으로 유지.
- mark/fortune/weather 규칙은 엔진 직접 분기 대신 provider/registry 주입 구조로 유지.

## P-03 Low Coupling / High Maintainability

- 엔진/서버/프론트 직접 참조를 줄이고 계약 객체 전달로 연결.
- 하드코딩 문자열(이벤트명/라벨/룰 상수) 분산 금지.
- canonical payload를 1차 소스로 사용하고 selector 후처리는 최소화.

## P-04 Ordering and Determinism

- 결정 이벤트 순서 고정:
  - `decision_requested -> decision_resolved(or timeout_fallback) -> domain events`
- `seq` 단조 증가 보장.
- 재연 가능성을 위해 append-only 로그 원칙 유지.

## P-05 Testing Discipline

- 계약 변경 시 schema fixture + parser test + e2e 최소 1개 필수.
- 1 human + 3 AI 혼합 시나리오 통합 테스트 필수.
- 룰 문서 변경 시 엔진/서버/UI 정합성 문서 업데이트 필수.

## P-06 UX Safety Rules

- actionable prompt만 blocking.
- non-actionable prompt는 observer 카드로 표시.
- system error/warning은 core gameplay narrative를 덮지 않음.

## P-07 Documentation Policy

- 계획/정책/아키텍처 문서는 `main` 기준으로 유지.
- 구현 변경 시 다음 문서를 함께 갱신:
  - 해당 PLAN 문서
  - `PLAN/PLAN_STATUS_INDEX.md`
  - 관련 `docs/*` 사양 문서

## P-08 Work Execution Rules (Added)

- 작업 원칙 - 소규모/대규모 작업에 관계 없이 어떤 일을 했는지 요약하여 작업 일지 문서에 남긴다.
- 작업 원칙 - 로직 등 복잡한 변경은 계획 문서를 먼저 작성한다.
- 작업 일지 문서: `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`

## 3) Working Checklist (Must pass before merge)

- [ ] 필독 순서 문서 확인
- [ ] Game-Rules와 구현 동작 차이 확인 및 기록
- [ ] Decision API 계약 위반 없음
- [ ] CP-949 검출 없음
- [ ] 테스트 통과
- [ ] 변경 문서 동시 업데이트 완료

## P-09 UI String Ownership (Added)

- New user-facing UI strings should be defined in shared resource/catalog modules first.
- Avoid embedding large visible phrases directly inside React runtime components when the text is likely to be reused or revised.
- If wording changes affect theater/stage/prompt/lobby UX, update both:
  - `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
  - `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`
