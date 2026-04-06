# External AI Worker Runbook

Status: ACTIVE  
Updated: 2026-04-07

## Purpose

This runbook explains how to run the reference external AI worker locally and attach it to a session as a real HTTP participant.

## Start the Worker

```bash
.venv311/bin/python tools/run_external_ai_worker.py --host 127.0.0.1 --port 8011
```

Optional flags:

- `--worker-id local-bot-1`
- `--policy-mode heuristic_v3_gpt`
- `--log-level debug`
- `--reload`

## Verify Health

```bash
curl http://127.0.0.1:8011/health
```

If worker auth is enabled:

```bash
MRN_EXTERNAL_AI_AUTH_HEADER_NAME=X-Worker-Auth \
MRN_EXTERNAL_AI_AUTH_SCHEME=Token \
MRN_EXTERNAL_AI_AUTH_TOKEN=worker-secret \
.venv311/bin/python tools/run_external_ai_worker.py --host 127.0.0.1 --port 8011
```

Then verify health with:

```bash
curl -H 'X-Worker-Auth: Token worker-secret' http://127.0.0.1:8011/health
```

Expected shape:

```json
{
  "ok": true,
  "worker_id": "external-ai-worker",
  "policy_mode": "heuristic_v3_gpt",
  "policy_class": "HeuristicPolicy",
  "decision_style": "contract_heuristic",
  "supported_transports": ["http"]
}
```

## Attach a Seat to the Worker

Use `participant_client: "external_ai"` on an AI seat and provide an HTTP endpoint.

```json
{
  "seats": [
    {
      "seat": 1,
      "seat_type": "ai",
      "ai_profile": "balanced",
      "participant_client": "external_ai",
      "participant_config": {
        "transport": "http",
        "endpoint": "http://127.0.0.1:8011/decide"
      }
    },
    {
      "seat": 2,
      "seat_type": "human"
    }
  ],
  "config": {
    "seed": 42,
    "seat_limits": { "min": 1, "max": 2, "allowed": [1, 2] },
    "participants": {
      "external_ai": {
        "transport": "http",
        "contract_version": "v1",
        "expected_worker_id": "local-bot-1",
        "auth_token": "worker-secret",
        "auth_header_name": "X-Worker-Auth",
        "auth_scheme": "Token",
        "timeout_ms": 15000,
        "retry_count": 1,
        "backoff_ms": 250,
        "fallback_mode": "local_ai",
        "healthcheck_path": "/health",
        "healthcheck_ttl_ms": 10000,
        "required_capabilities": ["choice_id_response", "healthcheck"],
        "headers": {}
      }
    }
  }
}
```

## Worker Contract

The server sends the frozen request envelope from:

- `packages/runtime-contracts/external-ai/schemas/request.schema.json`

The worker returns the frozen response shape from:

- `packages/runtime-contracts/external-ai/schemas/response.schema.json`

Important rules:

- `legal_choices` is authoritative
- the worker should respond with one canonical `choice_id`
- the worker should expose a matching `worker_contract_version`
- the worker should advertise the capabilities required by the seat config
- when configured, worker auth and `expected_worker_id` must match on both `/health` and `/decide`
- the server owns timeout, retry, and fallback behavior
- the server converts `choice_id` back into engine-native values through method-specific parsers

## Failure Behavior

When `participant_config.fallback_mode` is `local_ai`:

- HTTP failures or timeouts retry according to `retry_count` and `backoff_ms`
- after retries are exhausted, the seat falls back to the in-process AI policy
- the decision still resolves on the canonical runtime event stream

When `fallback_mode` is `error`:

- the transport raises after retry exhaustion
- runtime error handling remains server-owned
