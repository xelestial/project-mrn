# Human + External AI Playtest Checklist

Status: ACTIVE  
Updated: 2026-05-01

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
.venv/bin/python -m uvicorn apps.server.src.app:app --host 127.0.0.1 --port 9090
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
npm run dev -- --host 127.0.0.1 --port 9000
```

If backend is not on the standard local port, inject it explicitly:

```bash
cd apps/web
MRN_WEB_API_PORT=8011 npm run dev -- --host 127.0.0.1 --port 9000
```

## Session Config

Base your session payload on:

- `docs/current/engineering/examples/external_ai_http_session_payload.json`

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
7. The current UI exposes stable selectors or equivalent DOM evidence for every effect surface:
   - current weather
   - spectator/stage turn context
   - worker provenance
   - event/reveal feed items
   - rent, fortune, trick, and passive bonus effects
8. Treat these as mandatory watch targets in every browser playtest:
   - character draft and final-character prompt: choices, selected character, ability text, ordering, and viewport fit
   - mark-target prompt: legal candidates, explicit no-target choice, active slot or character identity, and submit result
   - mark-effect resolution: `mark_resolved` overlay/feed/stage text plus any cash, shard, burden, trick, or movement delta
   - off-turn actions: AI, external-worker, passive, fortune, weather, and follow-up effects remain visible while the local player waits
   - dice roll and movement: dice source, rolled value or card mode, path/movement event, landing, and resource delta are causally readable
9. Character and other blocking prompts fit in the target desktop viewport without document-level overflow.

## Effect-Display Release Gate

Before closing a Redis/browser effect-display regression, run:

```bash
cd apps/web
npm run e2e:human-runtime
```

The work is not closed while the suite still lacks stable DOM evidence for spectator/stage context, weather, worker provenance, or reveal/feed items. Future closure evidence must explicitly account for the mandatory watch targets: character draft, mark-target prompt, mark-effect resolution, off-turn actions, and dice roll/movement. If a live run does not naturally reach one, record it as not reached and cover it with targeted e2e or regression evidence before claiming the area is verified. If the UI intentionally replaced older selectors such as `spectator-turn-panel` or `board-event-reveal-*`, migrate the test contract to the new stable selectors in the same change.

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

## Cleanup Requirement

After every browser playtest:

1. Close all browser contexts/pages opened for the test.
2. Stop the local runtime if it was started only for the test:

```bash
./run-docker.sh down
```

3. Confirm no project containers remain:

```bash
docker compose -p project-mrn -f docker-compose.yml ps
```

Memory pressure from accumulated browser tabs can look like a frozen game screen, so cleanup is part of the test result.

Only reopen visual cleanup from concrete evidence like this.
