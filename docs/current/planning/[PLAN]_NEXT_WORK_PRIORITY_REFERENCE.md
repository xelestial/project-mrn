# [PLAN] Next Work Priority Reference

Status: ACTIVE  
Updated: 2026-05-08
Owner: Engine runtime

## Purpose

This is the current execution board.

Keep it short. If a detailed plan is needed, create it under the relevant
current docs area and link it here only while it is active.

## P0

P0 means work that blocks truthful gameplay, runtime safety, data durability, or
canonical decision/selector correctness.

## Always-Check Order

1. `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
3. `docs/current/planning/PLAN_STATUS_INDEX.md`
4. `docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`
5. active feature plan or contract for the touched subsystem

## Current Priority Order

### 1. Runtime Contract And Modular Runtime Stabilization

Use:

- `docs/current/planning/[PLAN]_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`
- `docs/current/runtime/end-to-end-contract.md`
- `docs/current/runtime/round-action-control-matrix.md`
- `docs/current/engineering/[PLAN]_FAST_CHECK_GAME_RULE_HARNESS.md`
- `docs/current/engineering/[PLAN]_TILE_TRAIT_ACTION_PIPELINE.md`

Current goal:

- keep `engine/`, `apps/server/`, and `apps/web/` synchronized on prompt,
  action, event, and round semantics
- separate `PlayerId`, `SeatId`, `ViewerId`, `RequestId`, `EventId`, and
  numeric commit/event/stream sequences before adding more protocol behavior
- preserve modular-runtime frame behavior while avoiding stale migration-plan
  assumptions
- add semantic regression tests before changing rule flow, prompt lifecycle, or
  server projection behavior

### 2. Redis-Authoritative State And Visibility Projection

Use:

- `docs/current/planning/[PLAN]_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`
- `docs/current/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md`
- `docs/current/runtime/end-to-end-contract.md`
- `docs/current/backend/runtime-logging-policy.md`

Current goal:

- finish transition-level durability and restart confidence
- keep per-player visibility and public/private event projection correct
- make Redis self-contained enough to inspect prompt lifecycle, viewer outbox,
  source event heads, commit heads, and active runtime frame within the one-hour
  debug retention window
- prefer contract-level checks over ad hoc UI observation
- preserve production-like Redis restart-smoke evidence when backend/runtime
  boundary work changes process roles, recovery, prompt continuation, or stream
  projection

### 3. Frontend Readability Follow-Up

Use:

- `docs/current/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`
- `docs/current/frontend/[AUDIT]_MRN_FRONTEND_GAME_DESIGN_REVIEW_2026-04-30.md`

Current goal:

- continue from the implemented board-first baseline
- make effect cause, prompt cause, and state delta legible during live play
- avoid reopening removed UI/UX plans unless the canonical document explicitly
  reintroduces them as current work
- keep frontend prompt selectors aligned with backend `view_state` and runtime
  module owners before changing component-level display logic

### 4. Real Playtests

Use:

- `docs/current/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md`
- `docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`

Current goal:

- run human + local AI + external AI sessions
- collect concrete evidence instead of reopening broad plans
- verify external worker endpoint capability before session attachment

## Closed Enough

Do not reopen these as broad plan tracks unless new evidence appears:

- architecture migration
- decision-contract unification
- string/resource migration
- parameter-driven decoupling
- superseded frontend priority/proposal/report docs
- implemented modular-runtime migration plans

## Daily Rule

If a task is unclear:

1. check rules
2. check this file and `docs/current/planning/PLAN_STATUS_INDEX.md`
3. check the current contract or canonical frontend/API/backend doc for the
   touched surface
4. prefer the smallest change that improves real playability or runtime safety
