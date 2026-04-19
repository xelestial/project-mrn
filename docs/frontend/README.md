# docs/frontend

Current frontend reference set.

Read in this order:

1. `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/engineering/[PLAN]_ROOM_SERVER_CLIENT_ELECTRON_ARCHITECTURE.md`
4. `docs/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`

Notes:

- frontend rendering should increasingly depend on backend selector output
- old frontend UI/UX plan, proposal, and report docs are closed or reference-only unless the canonical document explicitly points back to them
- session bootstrap should prefer session payload + selector metadata over localized text inference
- browser runtime regressions are checked by the GitHub Actions workflow `frontend-browser-runtime-tests`

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
