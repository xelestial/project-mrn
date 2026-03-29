# [PLAN] Implementation Document Usage Guide

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-29`  
Purpose: prevent document mixing during implementation

## Why This Exists

We now have legacy plans, active execution plans, and reference/proposal documents in parallel.
Without a strict reading order, implementation can drift or mix old assumptions.

This guide defines exactly:

- which document to read first
- which document is authoritative per topic
- which documents are reference-only

## Mandatory Reading Order (Before Coding)

Read in this exact order:

1. `PLAN/PLAN_STATUS_INDEX.md`
2. `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
3. `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
4. `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
5. Task-specific spec:
   - UI/component work: `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
   - DI/interface work: `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
   - transport/API work: `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
   - directory/file placement: `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`

If a task touches multiple areas, read all relevant task-specific specs.

## Authority Matrix

| Concern | Primary Source | Secondary Source |
|---|---|---|
| canonical active plan set | `PLAN/PLAN_STATUS_INDEX.md` | this guide |
| runtime/public event contract | `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` | API/interface specs |
| phase order and milestones | `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md` | detailed execution plan |
| granular implementation backlog | `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md` | plan status index |
| frontend component boundaries | `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md` | React top-level plan |
| backend/frontend DI ports | `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md` | contract doc |
| REST/WS payloads | `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md` | interface spec |
| where code should be placed | `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md` | React top-level plan |

## Conflict Resolution Rule

If documents conflict, resolve in this order:

1. Engine code and runtime truth (`GPT/engine.py`, `GPT/effect_handlers.py`)
2. `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
3. `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md` and `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
4. `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md` and detailed execution/component specs
5. proposal/reference documents

When conflict is found, fix docs in the same PR that implements code changes.

## Do-Not-Drive List (Reference Only)

The following can inform discussion but must not directly drive implementation tasks:

- `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md`
- `PLAN/[PROPOSAL]_VISUALIZATION_RUNTIME_DIRECTION.md`
- `PLAN/VISUALIZATION_GAME_PLAN.md`
- `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- all `[COMPLETE]_*.md`
- `PLAN/[SUPERSEDED]_GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md`

## Implementation Start Checklist

Before starting a coding task:

1. Confirm task scope in `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`.
2. Confirm data/contract fields in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`.
3. Confirm API/interface shape in the relevant `[PLAN]_...SPEC.md`.
4. Confirm target directory in `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`.
5. If any ambiguity remains, update plan docs first, then implement.

## PR Checklist (Documentation Guard)

For each implementation PR:

1. Mention which spec documents were used.
2. Update changed spec files in the same PR.
3. If status changes, update `PLAN/PLAN_STATUS_INDEX.md`.
4. Avoid introducing new behavior based only on proposal/reference docs.
