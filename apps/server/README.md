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
- `server`: FastAPI backend on `127.0.0.1:9090`.
- `prompt-timeout-worker`: standalone timeout worker using `apps.server.src.workers.prompt_timeout_worker_app`.
- `command-wakeup-worker`: standalone command stream worker using `apps.server.src.workers.command_wakeup_worker_app`.

If a manually started Redis container named `project-mrn` is already running, stop it before using Compose:

```bash
docker stop project-mrn
```
