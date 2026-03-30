# Claude Substrate Maintenance Loop

Status: `ACTIVE`  
Updated: `2026-03-31`  
Scope: contract fidelity, validator health, lower-layer payload completeness

## Purpose

Operationalize substrate maintenance as a lightweight recurring loop:

- no viewer/runtime ownership drift
- no broad alias re-expansion
- contract/payload validator maintenance only

This is the canonical substrate-loop execution guide while ownership is unified under GPT.

## In-Scope Tasks

1. Event/state contract verification against shared runtime contract.
2. Validator refresh when canonical fields evolve.
3. Public payload completeness checks for replay/live consumers.
4. Lower-layer substrate bug fixes discovered by checks above.

## Out-of-Scope Tasks

1. Viewer wording/layout/UX redesign.
2. Session/runtime architecture redesign.
3. Transport fields that bypass shared contract boundaries.

## Loop Cadence

Run this loop:

- at least once per contract-impacting PR (`C1`)
- or once per release candidate cycle

## Loop Steps

1. Confirm shared contract baseline:
   - `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
2. Run substrate validator and replay checks:
   - `python -m pytest GPT/test_visual_runtime_substrate.py`
   - `python GPT/test_replay_viewer.py`
3. If contract fields changed, update strict payload requirements in:
   - `GPT/validate_vis_stream.py`
4. Re-run tests.
5. Update status docs:
   - `PLAN/PLAN_STATUS_INDEX.md`
   - `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

## Quality Bar

Changes are acceptable only if:

1. validator tightening does not introduce false positives for optional events
2. payload requirements match emitted canonical fields
3. replay checks pass across deterministic seeds

## Latest Loop Result (`2026-03-31`)

- Contract/validator sync check:
  - `round_start` strict fields aligned (`initial`, `alive_player_ids`, `marker_owner_player_id`)
  - `trick_used` strict fields aligned (`phase`, `card_name`, `card_description`, `resolution`)
- Verification:
  - `python -m pytest GPT/test_visual_runtime_substrate.py` -> `2 passed`
  - `python GPT/test_replay_viewer.py` -> `Phase 2: ALL TESTS PASSED`
- Drift verdict:
  - no canonical contract drift detected in this loop pass

## Escalation Rule

If a contract drift is found that affects frontend/API behavior:

1. classify as `C1 Contract` in PR description
2. update relevant API/interface docs in same PR
3. include compatibility note when aliases are touched
