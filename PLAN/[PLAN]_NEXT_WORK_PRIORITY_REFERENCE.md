# [PLAN] Next Work Priority Reference

Status: ACTIVE  
Updated: 2026-04-04  
Owner: GPT

## Purpose

이 문서는 다음 작업의 우선순위를 고정하고, 시작 전에 반드시 확인해야 할 기준을 제공합니다.

## Current Execution Status

- `P0-1` 진행 중 (started: 2026-04-04)
  - 범위: Unified Decision API 계약 정합성 점검 및 이벤트 순서 고정
  - 현재 착수:
    - `decision_requested` / `decision_resolved` 서버 이벤트 발행 추가
    - 관련 단위 테스트 보강
    - timeout fallback lane에서도 `decision_resolved -> decision_timeout_fallback` 순서 고정
    - web selector/label 경로에 decision 이벤트 가시성 반영
    - retry/reconnect ordering fixture 추가
    - backend decision contract CI workflow 추가

- `P0-2` 진행 중
  - 범위: Human Play 룰/로그 체감 순서 정렬
  - 진행:
    - turn theater lane 분리(`core/prompt/system`) 구현
    - selector + UI 표기 + 회귀 테스트 반영
    - lane 그룹 렌더링(핵심 진행/선택응답/시스템) 반영
    - prompt 폭주 시에도 core가 유지되도록 lane quota 정책 반영
    - actor-focus 우선순위 반영(타 플레이어 core 행동 가시성 강화)
    - prompt lane 내부 우선순위 반영(결과/타임아웃/응답/요청 순)
    - lane별 접기/펼치기 제어 추가(운영자 가시성 제어)

## Priority Buckets

## P0 (Immediate / Blocker)

1. Unified Decision API 계약 고정 + 서버 게임런타임 주입
- Source plans:
  - `PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md`
  - `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
- Exit:
  - `DecisionRequest -> DecisionResponse` 계약 고정
  - `decision_requested/resolved/timeout_fallback` 이벤트 순서 고정

2. Human Play 룰/로그 체감 순서 정렬
- Source plan:
  - `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
- Exit:
  - core lane / prompt lane / system lane 분리
  - weather/fortune/mark 표시 순서 룰 일치

3. 룰 문서 정합성 감사 + 재발 방지
- Source plan:
  - `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
- Exit:
  - 룰 문서와 구현 차이 목록 0건, 또는 예외 문서화

## P1 (Stabilization)

1. Decision API 경로 E2E 자동화
- server/web/engine 통합 테스트로 1 human + 3 AI 시나리오 고정

2. Prompt UX 간결화 분류
- actionable prompt만 blocking
- non-actionable은 observer 카드

3. 로그/리플레이 가독성 정리
- 이벤트 코드명이 아닌 플레이어 친화 문구 우선

## P2 (Maintainability / DI Expansion)

1. mark/fortune/weather behavior DI 확장
- provider 또는 registry로 동작 분리

2. selector 하드코딩 축소
- canonical payload 우선, 후처리 최소화

3. 계약 역직렬화/스키마 자동 검증 강화
- schema fixture + parser/property tests

## P3 (Polish / Performance)

1. 시각 연출 개선(애니메이션/이벤트 카드/턴 극장)
2. 대규모 세션/재연결 성능 최적화
3. 운영 가이드/인수인계 문서 고도화

## Always-Check Order (When starting work)

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
3. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
4. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
5. `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`

## Conflict Resolution Rule

문서가 충돌하면 아래 순서로 적용:

1. `docs/Game-Rules.md`
2. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
3. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
4. `PLAN/PLAN_STATUS_INDEX.md`

## 2026-04-04 Progress Snapshot (Latest)

- P0-1 (Unified Decision API ordering/contracts):
  - Runtime bridge ordering and timeout ordering are fixed.
  - Retry/reconnect ordering fixtures are in place.
  - Contract-level ordered sequence fixtures are added.
  - Human-play selector regression fixture verifies decision/core lane coexistence.
  - Status: locally complete; waiting for CI confirmation on fastapi-enabled matrix.
- P0-2 (Human-play log experience):
  - Lane grouping/priority/toggle controls are implemented.
  - Actor visibility baseline improved (turn-stage panel + board pawn visibility).
  - Prompt payload/render parity hardened:
    - draft/final character ability text is now carried in decision payload.
    - hidden-trick prompt now carries full-hand context for single unified card-grid rendering.
    - mark-target prompt shows explicit character/player target summary.
    - prompt overlay copy and interaction flow were normalized for human play:
      - movement split to roll/card mode with compact card chips.
      - trick/hidden-trick unified hand display with hidden/usability states.
      - prompt label/helper catalogs rewritten with clean UTF-8 Korean wording.
  - Newly reinforced:
    - match screen now shows a `core action strip` (latest core events) for non-local turn visibility.
    - weather effect fallback text is persisted even when reveal payload omits explicit effect detail.
    - prompt submit reliability now guards against lost sends:
      - decision send path returns explicit success/failure.
      - `처리 중` 상태는 실제 전송 성공 이후에만 진입.
      - 연결 불안정/단절 시 busy 상태를 자동 해제하고 재시도 메시지를 노출.
    - generic prompt cards now render human wording by request type:
      - lap reward / purchase / active flip / burden exchange 선택지가 기계식 id 대신 플레이어 문구로 표시.
  - Next: continue live-screen UX parity fixes (prompt placement, text normalization, and action narration polish).

## 2026-04-05 Priority Update

- New active plan added:
  - `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
- Reason:
  - repeated mojibake/string-regression risk remains high when user-facing copy lives inside React components
  - this is now a direct blocker for stable human-play UX recovery

Updated short-term priority order:

1. `P0-2` keep live human-play UI flow recovery moving
2. `P0-string` externalize user-facing strings from critical React match surfaces
3. `P0-1` keep Unified Decision API contract/order stable while UI refactors continue

Immediate execution note:

- Any change touching these files should prefer resource extraction over new inline copy:
  - `apps/web/src/App.tsx`
  - `apps/web/src/features/theater/*`
  - `apps/web/src/features/stage/*`
  - `apps/web/src/features/prompt/*`
  - `apps/web/src/features/lobby/*`
