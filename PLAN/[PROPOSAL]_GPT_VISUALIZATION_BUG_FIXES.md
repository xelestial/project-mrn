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
- plan/status document alignment drift

These should now be treated as closed regression items, not open work.

## Remaining GPT-side Proposal Items

### M-1. Prompt envelope strict cleanup
Priority: `P1`
Status: `PARTIAL`

Current state:
- `prompt_contract.py` already exists
- `human_policy.py` already emits canonical prompt keys

Remaining issue:
- legacy mirrors and top-level context flattening still exist for compatibility

Opinion:
- this is now a cleanup item, not an enablement item

### M-2. Replay renderer / projection compatibility cleanup
Priority: `P1`
Status: `PARTIAL`

Current state:
- replay projection and replay renderers are already baseline-functional
- replay HTML has been materially improved for human-readable viewing

Remaining issue:
- smaller compatibility gaps and fallback-path cleanup still remain
- replay polish still needs periodic alignment with current event wording and ordering

Target areas:
- `GPT/viewer/replay.py`
- `GPT/viewer/renderers/markdown_renderer.py`
- `GPT/viewer/renderers/html_renderer.py`
- replay-side tests

### M-3. Plan/status document alignment
Priority: `P1`
Status: `DONE`

Closed by:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/PLAN_STATUS_INDEX.md`
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

Opinion:
- this was a real problem
- it is no longer a current GPT-side backlog item

### M-4. Optional HTML renderer hardening
Priority: `P2`
Status: `OPTIONAL`

Examples:
- template substitution hardening
- replay HTML resilience against future freer-form string payloads

Note:
- this is not a current blocker
- only do this after prompt-envelope strict cleanup and replay cleanup

## What This Proposal Should No Longer Drive
Do not use this file as the source of truth for:
- CLAUDE substrate work
- shared contract naming
- top-level visualization roadmap

Those belong to:
- `PLAN/[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
