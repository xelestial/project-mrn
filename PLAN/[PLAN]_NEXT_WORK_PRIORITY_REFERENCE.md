# [PLAN] Next Work Priority Reference

Status: ACTIVE  
Updated: 2026-04-04  
Owner: GPT

## Purpose

이 문서는 "다음 작업을 무엇부터 해야 하는지"를 빠르게 결정하기 위한 단일 참조 문서다.  
구현 시작 전, 이 문서를 먼저 확인한다.

## Priority Buckets

## P0 (Immediate / Blocker)

1. Unified Decision API 계약 고정 + 서버 게이트웨이 도입
- Source plans:
  - `PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md`
  - `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
- Why now:
  - AI/인간 처리 경계 통일이 없으면 룰/UI/로그 회귀가 반복됨
- Exit:
  - `DecisionRequest -> DecisionResponse` 계약 고정
  - `decision_requested/resolved/timeout_fallback` 이벤트 순서 고정

2. Human Play 룰/로그 체감 순서 정렬
- Source plan:
  - `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
- Why now:
  - 사용자 체감 흐름이 엔진 순서와 다르면 플레이 불가능 상태가 지속됨
- Exit:
  - core lane / prompt lane / system lane 분리
  - weather/fortune/mark 표시가 룰 순서와 일치

3. 룰 문서 정합성 감사 + 회귀 방지
- Source plan:
  - `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
- Why now:
  - 룰 문서 업데이트 후 엔진/런타임/UI 불일치 위험 큼
- Exit:
  - 룰 문서와 동작 차이 목록 0건 또는 의도된 예외 문서화

## P1 (Stabilization)

1. Decision API 경로 E2E 자동화
- server/web/engine 혼합 테스트로 1 human + 3 AI 시나리오 고정

2. Prompt UX 간결화/불변성
- actionable prompt만 blocking
- non-actionable은 observer 카드

3. 로그/리플레이 가독성 정규화
- 내부 코드명이 아닌 플레이어 친화 문구 우선

## P2 (Maintainability / DI Expansion)

1. mark/fortune/weather behavior DI 확장
- provider 또는 registry로 동작 분리

2. selector 하드코딩 축소
- canonical payload 우선 렌더링

3. 계약 예제/스키마 자동 검증 강화
- schema fixture + parser/property tests

## P3 (Polish / Performance)

1. 시각 연출 개선(애니메이션/이벤트 카드/턴 극장)
2. 대규모 세션/재연결 성능 튜닝
3. 운영 가이드/인수인계 문서 고도화

## Always-Check Order (When starting work)

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
3. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
4. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
5. `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`

## Conflict Resolution Rule

문서 간 충돌 시 적용 우선순위:
1. `docs/Game-Rules.md`
2. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
3. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
4. `PLAN/PLAN_STATUS_INDEX.md`

