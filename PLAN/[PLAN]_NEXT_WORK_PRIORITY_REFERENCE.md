# [PLAN] Next Work Priority Reference

Status: ACTIVE  
Updated: 2026-04-07  
Owner: GPT

## Purpose

This is the current execution board.

Keep it short.

## Current Priority Order

### 1. Human-play UI/UX recovery

Use:

- `docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
- `docs/frontend/[PROPOSAL]_UI_UX_ISSUE_FIX_PLAN.md`
- `docs/frontend/[PROPOSAL]_UI_UX_DETAILED_SPEC.md`

Current goal:

- make the game readable
- make current turn / remote turn / prompt cause obvious
- keep the board as the primary surface
- keep multi-target prompts visible on the board instead of collapsing them to one tile

### 2. Real playtests

Use:

- `docs/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md`

Current goal:

- run human + local AI + external AI sessions
- collect concrete evidence instead of reopening broad old plans
- use the checklist and smoke-check the stronger worker before browser playtests

### 3. Stronger external worker rollout support

Use:

- `docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`

Current goal:

- attach a real stronger worker endpoint to the already-stabilized seam
- keep repo edits limited to rollout support and concrete regressions
- verify endpoint compatibility with `tools/check_external_ai_endpoint.py` before session attachment

## Closed Enough

Do not reopen these as broad plan tracks unless new evidence appears:

- architecture migration
- decision-contract unification
- string/resource migration
- parameter-driven decoupling

## Daily Rule

If a task is unclear:

1. check rules
2. check this file
3. check the one-page UI/UX priority doc
4. prefer the smallest change that improves real playability
