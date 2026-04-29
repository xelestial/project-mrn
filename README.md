# project-mrn

Current status: playable web/runtime project under UI/UX stabilization.

## Read First

- [Game rules](/Users/sil/Workspace/project-mrn/docs/Game-Rules.md)
- [Mandatory engineering rules](/Users/sil/Workspace/project-mrn/docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md)
- [Current plan status](/Users/sil/Workspace/project-mrn/PLAN/PLAN_STATUS_INDEX.md)
- [Current next-work board](/Users/sil/Workspace/project-mrn/PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md)
- [UI/UX one-page priority](/Users/sil/Workspace/project-mrn/docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md)

## Active Areas

- Engine core: `GPT/`
- Server/runtime: `apps/server/`
- Web client: `apps/web/`

## Redis Local Stack

The backend Redis stack can be started with Docker Compose:

```bash
docker compose up --build redis server prompt-timeout-worker
```

This starts Redis (`project-mrn`), the FastAPI server, and the standalone prompt timeout worker.

## Current Focus

1. UI/UX readability and playability recovery
2. human + AI playtest stabilization
3. stronger external AI worker operational hookup

## Current Supporting Docs

- [docs/api/README.md](/Users/sil/Workspace/project-mrn/docs/api/README.md)
- [docs/backend/README.md](/Users/sil/Workspace/project-mrn/docs/backend/README.md)
- [docs/frontend/README.md](/Users/sil/Workspace/project-mrn/docs/frontend/README.md)
- [docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md](/Users/sil/Workspace/project-mrn/docs/engineering/[WORKLOG]_IMPLEMENTATION_JOURNAL.md)
- [docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md](/Users/sil/Workspace/project-mrn/docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md)
- [docs/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md](/Users/sil/Workspace/project-mrn/docs/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md)
