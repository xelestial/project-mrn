# Legacy vs React Parity Checklist

Canonical document path. Mirror in `PLAN/[CHECKLIST]_LEGACY_VS_REACT_PARITY.md` is kept only for legacy links.

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-31`

Purpose:
- track cutover readiness from legacy viewer/runtime paths to React/FastAPI runtime
- prevent hidden regressions during migration

## Scope

Comparison targets:

- Legacy path: `GPT/viewer/*`, `run_human_play.py`, legacy replay HTML
- React path: `apps/web/*`, `apps/server/*`, WS runtime + REST session lifecycle

## A. Session and Transport

- [x] create/list/get/join/start session lifecycle works
- [x] seat-token join and host-token start validation works
- [x] WS connect + resume flow works
- [x] reconnect with `last_seq` replay works
- [x] gap-too-old handling (`RESUME_GAP_TOO_OLD`) works
- [x] heartbeat/backpressure payload is visible in client

## B. Prompt and Decision Flow

- [x] prompt envelope required fields are present
- [x] decision ack (`accepted/rejected/stale`) handled in UI
- [x] timeout fallback trace event emitted
- [x] prompt helper text covers full human-policy request matrix
- [x] stale/rejected UX feedback appears in overlay

## C. Board and Projection

- [x] board renders from snapshot when available
- [x] board bootstraps from manifest when snapshot is absent
- [x] topology-aware projection baseline exists (`ring`/`line`)
- [x] tile labels can be overridden from manifest labels
- [x] API/WS integration fixture covers non-default seat/topology manifest (`3-seat + line`)
- [x] backend transport E2E fixture covers non-default seat/topology manifest replay
- [x] browser non-default topology E2E fixture (`apps/web/e2e/fixtures/non_default_topology_line_3seat.json` + fixture integrity spec)

## D. Parameter Decoupling

- [x] session API includes `parameter_manifest`
- [x] stream includes `parameter_manifest` event
- [x] frontend rehydrates on manifest hash changes (baseline)
- [x] stream-manifest rehydrate updates topology/labels in session state
- [x] API-level reconnect fixture replays latest manifest variant payload
- [x] web reconnect-flow fixture validates reducer+selector+rehydrate chain (`manifestReconnectFlow.spec.ts`)
- [x] backend transport E2E fixture validates reconnect replay after manifest-hash change
- [x] stale artifact gate is active in CI
- [x] browser manifest-hash reconnect E2E fixture (`apps/web/e2e/fixtures/manifest_hash_reconnect.json` + fixture integrity spec)
- [x] broader parameter matrix E2E fixture (`2-seat + economy/dice overrides`) is covered in parity spec

## E. UX Parity

- [x] timeline + situation + board + player panels baseline
- [x] non-human incident card stack baseline
- [x] collapsible prompt overlay baseline
- [x] bankruptcy/endgame alert parity polish (`selectCriticalAlerts` now includes bankruptcy/game_end/runtime criticals)
- [x] full theater continuity parity against legacy (theater feed now includes event + prompt + decision_ack continuity lane)

## F. Release Gates

- [x] web unit tests green
- [x] server unit/integration tests green
- [x] browser E2E parity baseline green (`apps/web/e2e/parity.spec.ts`)
- [x] replay parity acceptance pass (`python GPT/test_replay_viewer.py`)
- [x] live human-play acceptance pass (`python GPT/test_human_play.py`)

## Notes

- This checklist is a release artifact and must be updated in any PR that changes runtime contract, prompt UX, or board projection behavior.
- Acceptance evidence (`2026-03-31`):
  - `result/acceptance/2026-03-31_replay_parity.log`
  - `result/acceptance/2026-03-31_live_human_play.log`
