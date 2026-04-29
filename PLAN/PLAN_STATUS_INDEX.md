# PLAN Status Index

Status: ACTIVE  
Updated: 2026-04-29  
Owner: GPT

## Purpose

This file answers one question only:

What documents still matter right now?

## Current Repo State

The broad migration / architecture phase is closed enough.

Current repo-side work has one newly reopened architecture track:

1. Redis-authoritative game state migration
2. UI/UX readability and playability recovery
3. real playtest-driven stabilization
4. stronger external AI worker operational hookup

## Canonical Current Documents

Read and maintain these:

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/Game-Rules.md`
3. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
5. `docs/frontend/[PLAN]_LIVE_PLAY_STATE_AND_DECISION_RECOVERY.md`
6. `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`
7. `docs/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md`

## Closed Enough

These are not active implementation tracks anymore:

- broad architecture migration
- decision-contract unification as a repo-wide plan theme
- string/resource migration as a standalone track
- parameter-decoupling as a standalone track

Those themes should reopen only if a concrete regression or rollout need appears.

## Remaining Open Work

Open work is operational, not architectural. The previously listed items were closed on 2026-04-25:

1. external worker/service endpoint smoke: closed with `priority_score_v1` worker health + `/decide` check.
2. human + local AI + external AI playtest startup: closed with `sess_a0e25380c58f`.
3. concrete UI/UX gaps from that pass: closed for the `No mark` contract mismatch and mark success reveal stack.
4. quick-start / prompt payload / parity E2E drift: closed by restoring the quick-start lobby action, accepting legacy `choices` prompt payloads, and updating parity checks to the current quarter-view UI.

Current open work:

1. Redis-authoritative game state migration. Redis-backed rooms, sessions, streams, prompts, runtime metadata, command streams, prompt timeout worker service/entrypoint, command wakeup worker service/entrypoint, Docker Compose local worker wiring, local JSON archive export, live checkpoint/view-state storage, recovery checkpoint fixture, restart integration coverage, and Lua-backed command/lease primitives are now implemented as the first migration batch. Remaining work is resumable engine transition refactoring, full transition-level Lua/transaction commits, Redis-persisted worker offsets, and production-specific worker deployment settings. See `docs/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md`.

## Rule For New Work

Do not reopen old architecture or migration documents by default.

If a new task appears:

1. start from current rules
2. start from the one-page UI/UX priority doc
3. start from playtest evidence
4. record new decisions in the worklog instead of reviving old umbrella plans
