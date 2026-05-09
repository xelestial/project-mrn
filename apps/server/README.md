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
- For Redis Cluster or any Redis environment that enforces key slots, set one stable hash tag in the prefix for every role, for example `MRN_REDIS_KEY_PREFIX=mrn:{project-mrn-prod}`. The runtime Lua/transaction envelope can touch session state, command offsets, prompt records, stream indexes, and view projections together, so those keys must stay in the same Redis hash slot.
- Start workers only after `/health` is healthy, and configure process-manager restarts for all three roles.
- Configure the `server` restart recovery policy for the deployment's session ownership model. `MRN_RESTART_RECOVERY_POLICY=abort_in_progress` is still the conservative server default until restart recovery is smoke-tested in the target environment.
- Run standalone workers with `MRN_RESTART_RECOVERY_POLICY=keep` because they are not session owners and must not abort in-progress sessions during startup.
- Worker readiness commands are process-local and must succeed before routing live sessions to the deployment:
  `python -m apps.server.src.workers.prompt_timeout_worker_app --health` and
  `python -m apps.server.src.workers.command_wakeup_worker_app --health`.
- Treat accepted decision commands as wakeup edges. The command wakeup worker records each command offset once, then the runtime must drain deterministic queued actions until `waiting_input`, `completed`, or `unavailable`; `dice_roll` followed by `idle` with `pending_actions > 0` means the command transition loop is broken or the worker is stale.
- Use one shared durable volume or object-store export path for `MRN_GAME_LOG_ARCHIVE_PATH` if archived game logs must survive container replacement.

Restart smoke:

```bash
python3 tools/scripts/redis_restart_smoke.py
```

The smoke starts the Redis-backed backend roles with a hash-tagged key prefix,
creates a live human+AI session, restarts `server`, `prompt-timeout-worker`, and
`command-wakeup-worker`, runs worker `--health` readiness checks, then verifies
health, runtime status, and replay continuity. It runs the server with
`MRN_RESTART_RECOVERY_POLICY=keep` because the purpose is to prove live session
survival. Run it with the target deployment's `MRN_REDIS_KEY_PREFIX` before
enabling Redis Cluster or multi-process runtime rollout. Because
`docker-compose.yml` intentionally uses fixed container names for local tooling,
the smoke defaults to the `project-mrn` Compose project and reuses stopped
containers from that project. If matching containers are already running, the
script stops before touching them unless you use `--skip-up` or set
`MRN_SMOKE_REPLACE_EXISTING=1`.
If the fixed-name containers belong to another Compose project, rerun with the
matching `--compose-project` value or clear that stack first.

Production-like topology smoke:

```bash
MRN_REDIS_KEY_PREFIX='mrn:{project-mrn-prod}' \
python3 tools/scripts/redis_restart_smoke.py \
  --skip-up \
  --topology-name staging-blue \
  --expected-redis-hash-tag project-mrn-prod \
  --restart-command 'your-platform restart server prompt-timeout-worker command-wakeup-worker' \
  --worker-health-command 'your-platform exec prompt-timeout-worker -- python -m apps.server.src.workers.prompt_timeout_worker_app --health' \
  --worker-health-command 'your-platform exec command-wakeup-worker -- python -m apps.server.src.workers.command_wakeup_worker_app --health'
```

The production-like mode keeps the same engine/backend/Redis/WebSocket
continuity assertions, but delegates process restart and worker readiness to the
operator's platform commands.

If a manually started Redis container named `project-mrn` is already running, stop it before using Compose:

```bash
docker stop project-mrn
```
