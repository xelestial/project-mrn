# project-mrn

Current status: playable web/runtime project under UI/UX stabilization.

## Read First

- [Game rules](/Users/sil/Workspace/project-mrn/docs/current/Game-Rules.md)
- [Mandatory engineering rules](/Users/sil/Workspace/project-mrn/docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md)
- [Current plan status](/Users/sil/Workspace/project-mrn/docs/current/planning/PLAN_STATUS_INDEX.md)
- [Current next-work board](/Users/sil/Workspace/project-mrn/docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md)
- [Documentation index](/Users/sil/Workspace/project-mrn/docs/README.md)
- [UI/UX canonical future work](/Users/sil/Workspace/project-mrn/docs/current/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md)

## Active Areas

- Game engine and deterministic rules: `engine/`
- Backend API, Redis state, workers, and realtime streams: `apps/server/`
- Web client and browser E2E fixtures: `apps/web/`
- Shared runtime contracts: `packages/runtime-contracts/`
- Engine policy package metadata: `packages/policy-engine/`
- Current documentation: `docs/current/`
- Maintenance and smoke-test tooling: `tools/`

## Redis Local Stack

The backend Redis stack can be started with Docker Compose:

```bash
docker compose up --build redis server prompt-timeout-worker
```

This starts Redis (`project-mrn`), the FastAPI server, the standalone prompt timeout worker, and the command wakeup worker.

## Current Focus

1. runtime contract and modular-runtime stabilization
2. Redis-authoritative state / visibility projection hardening
3. UI/UX readability follow-up from the canonical frontend baseline
4. human + AI playtest stabilization

## Current Supporting Docs

- [docs/current/api/README.md](/Users/sil/Workspace/project-mrn/docs/current/api/README.md)
- [docs/current/backend/README.md](/Users/sil/Workspace/project-mrn/docs/current/backend/README.md)
- [docs/current/frontend/README.md](/Users/sil/Workspace/project-mrn/docs/current/frontend/README.md)
- [docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md](/Users/sil/Workspace/project-mrn/docs/current/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md)
- [docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md](/Users/sil/Workspace/project-mrn/docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md)
- [docs/current/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md](/Users/sil/Workspace/project-mrn/docs/current/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md)
