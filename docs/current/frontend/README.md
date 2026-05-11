# docs/frontend

Current frontend reference set.

Read in this order:

1. `docs/current/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/current/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/current/engineering/[PLAN]_ROOM_SERVER_CLIENT_ELECTRON_ARCHITECTURE.md`
4. `docs/current/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`

For 3D board work, read after the canonical UI/UX document:

5. `docs/current/frontend/[PLAN]_3D_BOARD_RENDERING_CONTRACT.md`
6. `docs/current/frontend/[PLAN]_3D_INTERACTION_AND_PROMPT_MAPPING.md`
7. `docs/current/frontend/[PLAN]_3D_VISIBILITY_AND_ANIMATION_RULES.md`

Notes:

- frontend rendering should increasingly depend on backend selector output
- frontend UI/UX plan, proposal, and report docs are closed or reference-only unless the canonical document explicitly points back to them
- session bootstrap should prefer session payload + selector metadata over localized text inference
- browser runtime regressions are checked by the GitHub Actions workflow `frontend-browser-runtime-tests`
- 3D board work must preserve backend-authoritative gameplay state and treat animation as cosmetic only
- 3D board work must keep existing 2D HUD/prompt/event surfaces usable until 3D runtime checks pass

## Frontend Runtime Contracts

Canonical runtime bootstrap inputs:

1. session REST payload
   - `parameter_manifest`
   - `initial_active_by_card`
2. replay / websocket event stream
   - `session_start`
   - `parameter_manifest`
   - `view_state.active_slots`
3. frontend manifest rehydration
   - `apps/web/src/domain/manifest/manifestRehydrate.ts`
   - must preserve board, seats, dice, economy, and resources from the latest known manifest

Frontend selectors should render:

- active strip from `view_state.active_slots`, with session `initial_active_by_card` as the pre-stream fallback
- weather headline/detail from structured fields, not from concatenated display strings
- prompt choice rows from `data-*` / selector metadata, not from broad text blocks

## 3D Board Frontend Contracts

3D board work is allowed only as a presentation/input layer over backend-owned `ViewCommit.view_state`.

Canonical 3D planning docs:

1. `docs/current/frontend/[PLAN]_3D_BOARD_RENDERING_CONTRACT.md`
   - 3D coordinate system
   - tile-to-world projection
   - pawn/coin/ownership marker defaults
   - orthographic camera defaults
   - rendering tests
2. `docs/current/frontend/[PLAN]_3D_INTERACTION_AND_PROMPT_MAPPING.md`
   - prompt choice to 3D target mapping
   - tile click behavior
   - local stale-submission guards
   - 2D fallback requirements
3. `docs/current/frontend/[PLAN]_3D_VISIBILITY_AND_ANIMATION_RULES.md`
   - viewer-specific visibility rules
   - private information protection
   - cosmetic animation authority rules
   - reconnect/static recovery defaults

Initial 3D MVP defaults:

- feature flag: `MRN_ENABLE_3D_BOARD=true`
- board topology: 40-tile square ring
- tile indices: `0`, `10`, `20`, `30` are corners
- coordinate system: X/Z board plane, Y up
- camera: orthographic, default position `[7.5, 9.0, 7.5]`
- interaction: focus-then-confirm, not single-click submit
- assets: primitive meshes first, no GLB dependency in MVP
- animation: cosmetic only; latest `ViewCommit` always wins
- 2D HUD/prompt/event feed remain active and authoritative for explanations

## Dev Server And Backend Port Injection

Frontend dev defaults to backend `127.0.0.1:9090`.

Use one of these patterns when a different backend is running:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
MRN_WEB_API_PORT=8011 npm run dev -- --host 127.0.0.1 --port 9000
```

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
MRN_WEB_API_TARGET=http://127.0.0.1:18001 npm run dev -- --host 127.0.0.1 --port 9000
```

Priority order:

1. `MRN_WEB_API_TARGET`
2. `MRN_WEB_API_HOST` + `MRN_WEB_API_PORT`
3. default `http://127.0.0.1:9090`

## Browser Runtime CI

Primary frontend browser checks:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run e2e:parity -- --list
npm run e2e:human-runtime -- --list
```

Canonical workflow:

- `.github/workflows/frontend-browser-runtime-tests.yml`

The workflow is expected to cover:

- initial active-face hydration
- draft / mark / purchase prompt layout
- weather headline/detail rendering
- runtime theater/spectator structure

## Live Full-Game Screen Check

The live browser full-game check has no total game-duration failure limit. Game duration is a rule outcome, not a browser-test criterion.

The failure criterion is screen progress:

- every decision/prompt remains governed by the server prompt timeout, currently 30 seconds by default.
- while the automated browser check is running, the visible screen signature must change within 60 seconds.
- the latest authoritative `ViewCommit.commit_seq` is sampled for diagnostics only and does not reset the visible-screen stall timer.
- if the visible signature does not change for 60 seconds, treat it as `screen_update_stalled`.
- time spent inspecting code or not running the browser-check process is not counted.

Run:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run e2e:live-full-game
```

Optional smoke mode can shorten rule completion without changing the screen-progress criterion:

```bash
MRN_FULL_GAME_BOUNDED=1 npm run e2e:live-full-game
```

## Human Runtime E2E Gate

`REDIS-UI-10` is resolved as of 2026-05-01. `npm --prefix apps/web run e2e:human-runtime` passed 18 of 18 checks after restoring spectator/core-action/reveal selectors, fixing desktop prompt overflow, and preserving effect-causality ordering.

For future effect-display regressions, the frontend must prove one of these before marking work complete:

- the existing `spectator-turn-panel`, `spectator-turn-weather`, `spectator-turn-worker`, and `board-event-reveal-*` selectors are present when the corresponding UI is visible
- or the suite has been intentionally migrated to new stable selectors with equivalent coverage

Coverage must include weather context, worker success/fallback provenance, rent/payoff reveals, fortune reveals, trick effects, passive bonuses, and desktop overflow checks for blocking prompts.
