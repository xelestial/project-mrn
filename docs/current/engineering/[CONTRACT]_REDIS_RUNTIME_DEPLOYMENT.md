# Redis Runtime Deployment Contract

## 1. Purpose

Redis-backed live gameplay requires the backend, workers, and Redis to behave
as one runtime system. This contract turns that requirement into process roles,
readiness checks, rollout invariants, and smoke-test evidence.

The machine-readable process contract lives at
`deploy/redis-runtime/process-contract.json`.
The platform-managed mapping template lives at
`deploy/redis-runtime/platform-managed.manifest.template.json`; copy it into the
target deployment system and replace the placeholder restart/exec commands with
that platform's native commands before rollout smoke.

## 2. Required Roles

| Role | Owner | Readiness | Restart policy |
| --- | --- | --- | --- |
| `server` | REST, WebSocket, projection, session recovery trigger | `GET /health` | always restart; use `MRN_RESTART_RECOVERY_POLICY=keep` only after the target topology passes restart smoke |
| `prompt-timeout-worker` | expired prompt fallback commands | `python -m apps.server.src.workers.prompt_timeout_worker_app --health` | always restart with `MRN_RESTART_RECOVERY_POLICY=keep` |
| `command-wakeup-worker` | accepted command stream wakeups | `python -m apps.server.src.workers.command_wakeup_worker_app --health` | always restart with `MRN_RESTART_RECOVERY_POLICY=keep` |

All roles must share the same `MRN_REDIS_URL`, `MRN_REDIS_KEY_PREFIX`, and
archive destination policy. For Redis Cluster, the prefix must include one
stable hash tag, such as `mrn:{project-mrn-prod}`, and every role must report
that same tag in `/health` or worker `--health`.

## 3. Rollout Smoke

The local production-like manifest is
`deploy/redis-runtime/docker-compose.runtime.yml`; copy
`deploy/redis-runtime/.env.example` to an environment-specific file and set a
shared Redis hash-tagged prefix before starting it. This manifest intentionally
uses the same required roles as `process-contract.json`: `server`,
`prompt-timeout-worker`, and `command-wakeup-worker`, plus Redis with append-only
persistence.

For local production-like verification, run:

```bash
MRN_REDIS_KEY_PREFIX='mrn:{runtime-compose-smoke}' \
python3 tools/scripts/redis_restart_smoke.py \
  --compose-project project-mrn-runtime-smoke \
  --compose-file deploy/redis-runtime/docker-compose.runtime.yml \
  --topology-name local-runtime-compose \
  --expected-redis-hash-tag runtime-compose-smoke \
  --decision-smoke
```

For a platform-managed environment, run:

```bash
MRN_REDIS_KEY_PREFIX='mrn:{project-mrn-prod}' \
python3 tools/scripts/redis_restart_smoke.py \
  --skip-up \
  --topology-name <deployment-name> \
  --expected-redis-hash-tag project-mrn-prod \
  --restart-command '<platform restart command for server and both workers>' \
  --worker-health-command '<platform exec prompt-timeout-worker -- python -m apps.server.src.workers.prompt_timeout_worker_app --health>' \
  --worker-health-command '<platform exec command-wakeup-worker -- python -m apps.server.src.workers.command_wakeup_worker_app --health>' \
  --decision-smoke
```

The placeholder values in `platform-managed.manifest.template.json` map the same
contract to platform roles:

- `server`: web process, `/health` readiness, restart command placeholder
- `prompt-timeout-worker`: worker process, `--health` readiness command, worker
  smoke health command placeholder
- `command-wakeup-worker`: worker process, `--health` readiness command, worker
  smoke health command placeholder

Passing evidence must include:

- `before_status=waiting_input`
- `after_status=waiting_input`
- replay event count after restart is greater than or equal to the count before restart
- `worker_health_checks` is at least two
- `/health.redis.cluster_hash_tag` equals the expected hash tag
- `decision_smoke.accepted_status=accepted`
- duplicate submission for the same `request_id` returns `stale` or `rejected`
- the runtime advances from the submitted request id to the next waiting input,
  `finished`, `unavailable`, or `aborted`
- replay event count after decision smoke is greater than the restart replay count

Latest checked local production-like evidence:

- checked `2026-05-04`
- topology `local-runtime-compose`
- prefix `mrn:{runtime-compose-smoke}`
- session `sess_Lg6Pa5oX8kLUxx_ZFsfXxArD`
- status `waiting_input -> waiting_input`
- replay events `11 -> 12`
- worker health checks `4`

Latest checked local restart+decision evidence:

- checked `2026-05-04`
- topology `local-runtime-compose-decision`
- prefix `mrn:{runtime-decision-smoke}`
- session `sess_Y8h_pqW5y78vTjqlDjHjF8Ge`
- restart status `waiting_input -> waiting_input`
- restart replay events `11 -> 12`
- worker health checks `4`
- decision request `sess_Y8h_pqW5y78vTjqlDjHjF8Ge:r1:t1:p1:draft_card:1`
- accepted decision status `accepted`
- duplicate decision status `stale`, reason `already_resolved`
- decision advanced to
  `sess_Y8h_pqW5y78vTjqlDjHjF8Ge:r1:t1:p1:final_character:1`
- post-decision replay events `26`

Latest checked platform-managed input-path evidence:

- checked `2026-05-04`
- topology `local-runtime-platform-managed`
- restart mode `custom-command`
- prefix `mrn:{runtime-platform-smoke}`
- session `sess_puHzrvjLOoEdawsov5ef0m-K`
- status `waiting_input -> waiting_input`
- replay events `11 -> 12`
- worker health checks `4`

This proves the repository's `--skip-up`/custom-command smoke contract and
manifest mapping shape. A real external deployment still must replace the
placeholder restart and worker exec commands in
`platform-managed.manifest.template.json` with the target platform's native
commands and capture fresh passing smoke evidence before live routing.

## 4. Failure Rules

- If `/health` reports no Redis or an invalid hash tag, do not route live
  sessions to the deployment.
- If either worker health command fails, the deployment is not ready even when
  the server health endpoint is healthy.
- If restart smoke reports `recovery_required`, `unavailable`, or replay shrink,
  keep `server` on `MRN_RESTART_RECOVERY_POLICY=abort_in_progress` for that
  topology and investigate Redis/runtime recovery before rollout.
- If accepted decisions do not advance after restart, treat
  `command-wakeup-worker` as down or offset-stale until proven otherwise.
- If duplicate decision smoke accepts the second submission, stop rollout and
  investigate Redis prompt/command dedupe before testing frontend behavior.
