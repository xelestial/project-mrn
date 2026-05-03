# PLAN Status Index

Status: ACTIVE  
Updated: 2026-05-03  
Owner: GPT

## Purpose

This file answers one question only:

What documents still matter right now?

## Current Repo State

The broad architecture migration era is closed enough. Current work should start
from the runtime contracts, current gameplay rules, and the short priority board
instead of reopening old umbrella plans.

Current repo-side work has four active tracks:

1. Runtime contract and modular-runtime stabilization
2. Redis-authoritative game state and visibility projection hardening
3. UI/UX readability follow-up from the current canonical frontend baseline
4. Real human/local-AI/external-AI playtest stabilization

The 2026-05-02 modular runtime migration plans are implemented and archived.
The current source of truth for that surface is now:

- `docs/current/runtime/end-to-end-contract.md`
- `docs/current/runtime/round-action-control-matrix.md`
- `GPT/runtime_modules/`
- `apps/server/src/services/runtime_service.py`

## Canonical Current Documents

Read and maintain these:

1. `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/current/Game-Rules.md`
3. `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `docs/current/runtime/end-to-end-contract.md`
5. `docs/current/runtime/round-action-control-matrix.md`
6. `docs/current/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`
7. `docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`
8. `docs/current/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md`
9. `docs/current/engineering/[PLAN]_VISIBILITY_PROJECTION_REDIS.md`
10. `docs/current/engineering/[PLAN]_TILE_TRAIT_ACTION_PIPELINE.md`

## Current Reference Sets

- API and server contracts: `docs/current/api/`, `docs/current/backend/`
- Frontend baseline and audit: `docs/current/frontend/`
- Runtime contracts: `docs/current/runtime/`
- Rule/balance/reference material: `docs/current/rules/`
- External AI operation: `docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`
- Human/external AI playtest checklist: `docs/current/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md`

## Archived Documents

Docs under `docs/archive/` are historical. They can explain why the current
shape exists, but they are not execution sources unless a current document
explicitly says to consult them.

Archived categories:

- superseded frontend plans, proposals, and reports
- implemented modular-runtime migration plans
- older sync/patch handoff notes
- duplicate backend-selector plan copy
- invalid trick-card source snapshot
- Redis UI playtest findings superseded by the lessons document

## Closed Enough

These are not active broad implementation tracks anymore:

- broad architecture migration
- decision-contract unification as a repo-wide plan theme
- string/resource migration as a standalone track
- parameter-decoupling as a standalone track
- quarter-view board/event presentation as a standalone frontend rebuild plan
- desktop turn overlay / board readability as a standalone plan

Those themes should reopen only if a concrete regression or rollout need appears.

## Remaining Open Work

1. Redis-authoritative game state migration. Redis-backed rooms, sessions,
   streams, prompts, runtime metadata, command streams, prompt timeout worker
   service/entrypoint, command wakeup worker service/entrypoint, Docker Compose
   local worker wiring, local JSON archive export, live checkpoint/view-state
   storage, canonical GameState checkpoint serialization/hydration, recovery
   checkpoint fixture, restart integration coverage, Redis-persisted command
   worker offsets, Lua-backed command/lease primitives, command-triggered
   transition commit metadata, Redis hash-tag health reporting, local backend
   restart smoke, authenticated REST restart recovery, and worker readiness
   commands are implemented. Remaining work is running restart smoke against
   the target production topology, adding platform-specific worker deployment
   manifests, and continuing the larger engine-native module migration beyond
   the guarded prompt continuation boundaries. See `docs/current/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md`.
2. Runtime contract stabilization. Keep end-to-end payload shape, round/action
   control, prompt lifecycle, and modular-runtime frame semantics synchronized
   between `GPT/`, `apps/server/`, and `apps/web/`.
3. UI/UX follow-up. Use only
   `docs/current/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md` and
   `docs/current/frontend/[AUDIT]_MRN_FRONTEND_GAME_DESIGN_REVIEW_2026-04-30.md`
   as current frontend planning inputs.

## Rule For New Work

Do not reopen old architecture or migration documents by default.

If a new task appears:

1. start from current rules
2. start from this index and the next-work board
3. start from the runtime/frontend/API contracts for the touched surface
4. start from playtest evidence when behavior is uncertain
5. record new decisions in the worklog instead of reviving old umbrella plans
