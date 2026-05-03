# tools/scripts

Operational scripts for local runs, export, and migration helpers.

- `redis_restart_smoke.py`: starts the Redis-backed backend worker stack, creates
  a live human+AI session, restarts backend/worker processes, and verifies
  health, worker readiness, runtime status, Redis hash-tag prefix reporting,
  and replay continuity. It defaults to Compose project `project-mrn` because
  the local compose file uses fixed container names. For production-like
  topologies, run with `--skip-up`, `--restart-command`,
  `--worker-health-command`, and `--expected-redis-hash-tag` so the same smoke
  checks exercise the target platform's actual process manager.
