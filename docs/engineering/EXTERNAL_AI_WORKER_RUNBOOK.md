# External AI Worker Runbook

Status: ACTIVE  
Updated: 2026-04-07

## Purpose

This runbook explains how to run the reference external AI worker locally and attach it to a session as a real HTTP participant.

For a production-shaped session payload example, see:

- `docs/engineering/examples/external_ai_http_session_payload.json`

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
  "ready": true,
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
        "healthcheck_policy": "required",
        "require_ready": true,
        "max_attempt_count": 3,
        "required_capabilities": ["choice_id_response", "healthcheck"],
        "required_request_types": ["movement", "purchase_tile"],
        "required_policy_mode": "heuristic_v3_gpt",
        "required_decision_style": "contract_heuristic",
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
- when provided, `supported_request_types` should accurately describe which canonical request types the worker can actually resolve
- when configured, `required_request_types` must be a subset of the worker's advertised `supported_request_types`
- when configured, `required_policy_mode` must match the worker's advertised `policy_mode`
- when configured, `required_decision_style` must match the worker's advertised `decision_style`
- when configured, worker auth and `expected_worker_id` must match on both `/health` and `/decide`
- `healthcheck_policy=required` keeps health preflight active even when the runtime uses an injected custom sender seam
- `healthcheck_policy=disabled` skips health preflight intentionally and should only be used for tightly controlled local/testing setups
- `require_ready=true` also requires `/health` to advertise `ready: true`
- `max_attempt_count` caps total worker call attempts even if `retry_count` is set higher
- the server owns timeout, retry, and fallback behavior
- the server converts `choice_id` back into engine-native values through method-specific parsers

## Deployment Checklist

- assign a stable `worker_id` and mirror it in `expected_worker_id`
- require a non-empty auth token on both `/health` and `/decide`
- expose the health endpoint on the same worker deployment as `/decide`
- advertise required capabilities before attaching the seat in production
- advertise every request type listed in `required_request_types` before attaching the seat in production
- keep `fallback_mode=local_ai` for the first production rollout unless explicit hard-fail behavior is desired

## Failure Behavior

When `participant_config.fallback_mode` is `local_ai`:

- HTTP failures or timeouts retry according to `retry_count` and `backoff_ms`
- after retries are exhausted, the seat falls back to the in-process AI policy
- the decision still resolves on the canonical runtime event stream

When `fallback_mode` is `error`:

- the transport raises after retry exhaustion
- runtime error handling remains server-owned

Useful failure codes seen from the runtime seam:

- `external_ai_http_error`
- `external_ai_timeout`
- `external_ai_healthcheck_failed`
- `external_ai_worker_identity_mismatch`
- `external_ai_contract_version_mismatch`
- `external_ai_missing_required_capability`
- `external_ai_missing_required_request_type`
- `external_ai_policy_mode_mismatch`
- `external_ai_decision_style_mismatch`
- `external_ai_worker_not_ready`
- `external_ai_missing_choice_id`

Useful runtime status values surfaced into prompt/event `public_context`:

- `external_ai_resolution_status=resolved_by_worker`
- `external_ai_resolution_status=worker_failed`
- `external_ai_resolution_status=resolved_by_local_fallback`
- `external_ai_attempt_count=<n>`
- `external_ai_attempt_limit=<n>`
