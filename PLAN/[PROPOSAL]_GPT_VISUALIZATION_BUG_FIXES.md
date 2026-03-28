# [PROPOSAL] GPT Visualization Bug Fixes

Status: `PROPOSAL`
Owner: `GPT`
Last reviewed on: `2026-03-29`

## Purpose
This document is now a narrow GPT-side bug memo.

It no longer represents the full active corrective backlog.
The primary corrective split is:
- `PLAN/[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`

Use this file only for:
- renderer-local GPT issues
- replay/view compatibility cleanup notes
- lower-priority viewer polish gaps

## Status Summary

### Already fixed on `main`
These were previously tracked here and are no longer active blockers:
- human-play `HUMAN_SEAT` indexing mismatch
- human-play player color indexing mismatch
- `submit_response()` race window
- prompt `player_id` 0-based display mismatch
- human-play final-character crash path
- human-play stale public-state field usage
- Phase 4 false-positive test path

These should now be treated as closed regression items, not open work.

## Remaining GPT-side Proposal Items

### M-1. Prompt envelope normalization
Priority: `P1`
Status: `OPEN`

Current issue:
- `human_policy.py` still emits prompt-family dicts in an ad-hoc shape

Target:
- one stable GPT-side adapter aligned with the shared contract

Why this matters:
- the current baseline works
- but expansion to more prompt families will be fragile unless the envelope is normalized now

### M-2. Replay renderer / projection compatibility cleanup
Priority: `P1`
Status: `OPEN`

Current issue:
- replay projection and replay renderers still show small contract drift and compatibility inconsistencies

Target areas:
- `GPT/viewer/replay.py`
- `GPT/viewer/renderers/markdown_renderer.py`
- `GPT/viewer/renderers/html_renderer.py`
- replay-side tests

Goal:
- replay path should be internally consistent with current `main`
- replay tests should reflect actual current projection shape

### M-3. Plan/status document alignment
Priority: `P1`
Status: `OPEN`

Current issue:
- documentation still does not cleanly separate:
  - completed baseline viewer/runtime work
  - remaining contract cleanup
  - remaining Phase 5 UI work

Target files:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/PLAN_STATUS_INDEX.md`

### M-4. Optional HTML renderer hardening
Priority: `P2`
Status: `OPTIONAL`

Examples:
- template substitution hardening
- replay HTML resilience against future freer-form string payloads

Note:
- this is not a current blocker
- only do this after prompt normalization and replay cleanup

## What This Proposal Should No Longer Drive
Do not use this file as the source of truth for:
- CLAUDE substrate work
- shared contract naming
- top-level visualization roadmap

Those belong to:
- `PLAN/[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
