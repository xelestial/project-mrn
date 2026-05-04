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
- `redis_platform_smoke_from_manifest.py`: validates a platform-managed Redis
  runtime manifest, builds the matching `redis_restart_smoke.py` command, and
  can run the manifest's preflight plus restart/decision smoke. Use
  `--validate-only` before rollout, `--print-command` for deployment logs, and
  `--run --preflight` for the repository-local executable profile. Add
  `--evidence-output <path>` to store the manifest summary, generated command,
  and final smoke JSON as a rollout artifact. Use
  `--require-external-topology` for real staging/production evidence; it rejects
  local smoke profiles and requires a filled external platform manifest.
