# Human + External AI Playtest Checklist

Status: ACTIVE  
Updated: 2026-04-12

## Goal

Use this checklist when running a real local playtest with:

- human seats
- local AI seats
- external AI seats

The preferred stronger worker path is:

- `worker_profile=priority_scored`

## Local Startup

1. Start the stronger external worker:

```bash
.venv/bin/python tools/run_external_ai_worker.py \
  --host 127.0.0.1 \
  --port 8011 \
  --worker-id local-priority-bot \
  --policy-mode heuristic_v3_gpt \
  --worker-profile priority_scored \
  --worker-adapter priority_score_v1
```

2. Start the server:

```bash
.venv/bin/python -m uvicorn apps.server.src.app:app --host 127.0.0.1 --port 8000
```

3. Smoke-check the worker contract before opening the web app:

```bash
.venv/bin/python tools/check_external_ai_endpoint.py \
  --base-url http://127.0.0.1:8011 \
  --require-ready \
  --require-profile priority_scored \
  --require-adapter priority_score_v1 \
  --require-policy-class PriorityScoredPolicy \
  --require-decision-style priority_scored_contract \
  --require-request-type movement \
  --require-request-type purchase_tile
```

4. Start the web app:

```bash
cd apps/web
npm run dev -- --host 127.0.0.1 --port 4174
```

If backend is not on the standard local port, inject it explicitly:

```bash
cd apps/web
MRN_WEB_API_PORT=8011 npm run dev -- --host 127.0.0.1 --port 4174
```

## Session Config

Base your session payload on:

- `docs/engineering/examples/external_ai_http_session_payload.json`

Recommended stronger-worker settings:

- `worker_profile=priority_scored`
- `fallback_mode=local_ai`
- `healthcheck_policy=required`
- `require_ready=true`

## What To Verify

1. Human prompt flow still opens only for human seats.
2. External AI turns show:
   - worker id
   - adapter
   - policy class
   - decision style
3. Success turns show `resolved_by_worker`.
4. Timeout / not-ready turns show local fallback continuity instead of breaking the scene.
5. Spectator and turn-stage both keep:
   - weather
   - payoff continuity
   - worker provenance
6. Long chains still read naturally after:
   - worker success
   - worker fallback
   - handoff to the next seat

## Evidence To Capture

When a visual drift issue appears, capture:

- session payload
- exact event ordering
- whether the turn was worker-resolved or fallback-resolved
- which panel looked wrong:
  - spectator
  - turn-stage
  - prompt
  - theater

Only reopen visual cleanup from concrete evidence like this.
