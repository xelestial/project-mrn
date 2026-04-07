# PLAN Status Index

Status: ACTIVE  
Updated: 2026-04-07  
Owner: GPT

## Purpose

This file answers one question only:

What documents still matter right now?

## Current Repo State

The broad migration / architecture phase is closed enough.

Current repo-side work is narrower:

1. UI/UX readability and playability recovery
2. real playtest-driven stabilization
3. stronger external AI worker operational hookup

## Canonical Current Documents

Read and maintain these:

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/Game-Rules.md`
3. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
5. `docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md`

## Closed Enough

These are not active implementation tracks anymore:

- broad architecture migration
- decision-contract unification as a repo-wide plan theme
- string/resource migration as a standalone track
- parameter-decoupling as a standalone track

Those themes should reopen only if a concrete regression or rollout need appears.

## Remaining Open Work

Open work is operational, not architectural:

1. attach a real stronger external worker/service endpoint
2. run human + local AI + external AI playtests
3. fix only the concrete UI/UX gaps found in those playtests

## Rule For New Work

Do not reopen old architecture or migration documents by default.

If a new task appears:

1. start from current rules
2. start from the one-page UI/UX priority doc
3. start from playtest evidence
4. record new decisions in the worklog instead of reviving old umbrella plans
