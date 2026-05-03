# docs/backend

Backend service boundaries, DI notes, selector migration notes, and runtime operation docs.

Read these first:

1. `docs/current/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/current/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
4. `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
5. `docs/current/backend/online-game-interface-spec.md`
6. `docs/current/backend/turn-structure-and-order-source-map.md`

Canonical backend references:

- `docs/current/backend/runtime-logging-policy.md`
- `docs/current/engineering/[PLAN]_BACKEND_SELECTOR_AND_MIDDLEWARE_VIEWMODEL_MIGRATION.md`
- `docs/current/engineering/[PLAN]_ROOM_SERVER_CLIENT_ELECTRON_ARCHITECTURE.md`

Operational defaults:

- backend standard local port: `9090`
- frontend standard local dev port: `9000`
- frontend should only point elsewhere through explicit env injection (`MRN_WEB_API_PORT`, `MRN_WEB_API_HOST`, `MRN_WEB_API_TARGET`)

Runtime safety rules:

- gameplay rule code should compare canonical ids, not localized Korean names
- the repository policy gate for this is `tools/gameplay_literal_gate.py`
- allowed runtime exceptions are limited to compatibility alias resolution and explicit log-label strings documented in `docs/current/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
- session REST bootstrap should expose both `parameter_manifest` and `initial_active_by_card`
- backend selector changes should be validated alongside:
  - `apps/server/tests/test_sessions_api.py`
  - `apps/server/tests/test_view_state_player_selector.py`
  - `apps/server/tests/test_view_state_scene_selector.py`
  - `apps/server/tests/test_view_state_turn_selector.py`
