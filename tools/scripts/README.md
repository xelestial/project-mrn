# tools/scripts

Operational scripts for local runs, export, and migration helpers.

- `redis_restart_smoke.py`: starts the Redis-backed backend worker stack, creates
  a live human+AI session, restarts backend/worker processes, and verifies
  health, runtime status, Redis hash-tag prefix reporting, and replay
  continuity. It defaults to Compose project `project-mrn` because the local
  compose file uses fixed container names.
