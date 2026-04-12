# docs/backend

Backend service boundaries, DI notes, selector migration notes, and runtime operation docs.

Read these first:

1. `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
4. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
5. `docs/backend/online-game-interface-spec.md`
6. `docs/backend/turn-structure-and-order-source-map.md`

Canonical backend references:

- `docs/backend/runtime-logging-policy.md`
- `docs/engineering/[PLAN]_BACKEND_SELECTOR_AND_MIDDLEWARE_VIEWMODEL_MIGRATION.md`

Operational defaults:

- backend standard local port: `8000`
- frontend standard local dev port: `4174`
- frontend should only point elsewhere through explicit env injection (`MRN_WEB_API_PORT`, `MRN_WEB_API_HOST`, `MRN_WEB_API_TARGET`)
