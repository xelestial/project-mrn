# docs/frontend

Current frontend reference set.

Read in this order:

1. `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
4. `docs/frontend/[PLAN]_BOARD_COORDINATE_SYSTEM_AND_HUD_LAYOUT_STABILIZATION.md`
5. `docs/frontend/[PLAN]_LIVE_PLAY_STATE_AND_DECISION_RECOVERY.md`

Notes:

- frontend rendering should increasingly depend on backend selector output
- the proposal docs remain as rationale and design direction

## Dev Server And Backend Port Injection

Frontend dev defaults to backend `127.0.0.1:8000`.

Use one of these patterns when a different backend is running:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
MRN_WEB_API_PORT=8011 npm run dev -- --host 127.0.0.1 --port 4174
```

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
MRN_WEB_API_TARGET=http://127.0.0.1:18001 npm run dev -- --host 127.0.0.1 --port 4174
```

Priority order:

1. `MRN_WEB_API_TARGET`
2. `MRN_WEB_API_HOST` + `MRN_WEB_API_PORT`
3. default `http://127.0.0.1:8000`
