# Claude Visualization Game Substrate Reference

## Status
- `REFERENCE`
- Source branch: `CLAUDE-MAIN`
- Source file: `PLAN/VISUALIZATION_GAME_PLAN.md`

## Why This File Exists
The current branch does not contain Claude's visualization substrate plan as a local file.

That branch-only document is still important because it defines lower-layer replay/live-play substrate ideas that complement the current GPT-side canonical plan:
- structured event stream enrichment
- authoritative source policy
- board public state
- player public state
- movement trace
- replay-grade event requirements

This reference note exists so the current branch can track that dependency without pretending the full Claude document is locally owned here.

## Recommended Role Split

### GPT-owned upper architecture
- runtime session
- replay/live projection
- renderer
- public-vs-analysis view
- human/AI decision adapter

Canonical local plan:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

### Claude-owned lower substrate reference
- engine event enrichment
- public board snapshot contract
- public player snapshot contract
- movement trace contract
- authoritative replay source policy

External source:
- `CLAUDE-MAIN:PLAN/VISUALIZATION_GAME_PLAN.md`

## Practical Guidance
When implementing visual replay or playable runtime work on this branch:

1. Follow `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md` as the top-level execution plan.
2. Use the Claude branch substrate plan as the lower-layer contract reference.
3. Do not treat `/result/*.md` as replay authority.
4. Prefer:
   - engine state
   - structured event stream
   - deterministic rerun
   as replay/live truth sources.

## Current Decision
Keep this as a short reference note instead of copying the entire Claude branch document into the current branch.

Reason:
- avoids duplicate ownership
- avoids stale divergence
- keeps current-branch planning readable
