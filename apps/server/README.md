# apps/server

FastAPI-based online game backend runtime.

Initial scope:

- session lifecycle REST endpoints
- WebSocket stream placeholder
- prompt routing and runtime services (next phases)

Run locally without Docker:

`uvicorn apps.server.src.app:app --reload --port 9090`

Run the Redis-backed stack with Docker Compose from the repository root:

```bash
docker compose up --build redis server prompt-timeout-worker command-wakeup-worker
```

Services:

- `redis`: Redis 7 with AOF enabled, exposed on `127.0.0.1:6379`, container name `project-mrn`.
- `server`: FastAPI backend on `127.0.0.1:9090`; Compose waits for Redis and marks the service healthy through `/health`.
- `prompt-timeout-worker`: standalone timeout worker using `apps.server.src.workers.prompt_timeout_worker_app`; must run whenever Redis-backed human prompts are enabled.
- `command-wakeup-worker`: standalone command stream worker using `apps.server.src.workers.command_wakeup_worker_app`; must run whenever Redis-backed human decisions can resume a waiting runtime.

Production process contract:

- Run exactly these long-lived process roles against the same `MRN_REDIS_URL` and `MRN_REDIS_KEY_PREFIX`: `server`, `prompt-timeout-worker`, and `command-wakeup-worker`.
- Start workers only after `/health` is healthy, and configure process-manager restarts for all three roles.
- Configure the `server` restart recovery policy for the deployment's session ownership model. `MRN_RESTART_RECOVERY_POLICY=abort_in_progress` is still the conservative server default until restart recovery is smoke-tested in the target environment.
- Run standalone workers with `MRN_RESTART_RECOVERY_POLICY=keep` because they are not session owners and must not abort in-progress sessions during startup.
- Treat accepted decision commands as wakeup edges. The command wakeup worker records each command offset once, then the runtime must drain deterministic queued actions until `waiting_input`, `finished`, or `unavailable`; `dice_roll` followed by `idle` with `pending_actions > 0` means the command transition loop is broken or the worker is stale.
- Use one shared durable volume or object-store export path for `MRN_GAME_LOG_ARCHIVE_PATH` if archived game logs must survive container replacement.

If a manually started Redis container named `project-mrn` is already running, stop it before using Compose:

```bash
docker stop project-mrn
```
