# External AI HTTP Contract

This directory freezes the server-to-worker HTTP contract for `external_ai` participants.

## Scope

- `request`: canonical decision request envelope sent from the runtime server to an external AI worker
- `response`: canonical choice response returned by that worker

## Notes

- `legal_choices` is the authoritative choice list.
- The worker should respond with one `choice_id` from that list.
- Runtime timeout / retry / fallback policy remains owned by the server seat descriptor.

## Local Worker

Run the reference worker locally:

```bash
.venv311/bin/python tools/run_external_ai_worker.py --host 127.0.0.1 --port 8011
```

Health check:

```bash
curl http://127.0.0.1:8011/health
```

Decision request:

```bash
curl -X POST http://127.0.0.1:8011/decide \
  -H 'Content-Type: application/json' \
  -d @packages/runtime-contracts/external-ai/examples/request.purchase_tile.json
```

The reference worker is intentionally contract-driven:

- it consumes the frozen HTTP request envelope
- it selects a canonical `choice_id` from `legal_choices`
- it can return the matched `choice_payload` for debugging and inspection
- it exposes `worker_contract_version`, `capabilities`, and `supported_request_types`
- the runtime server remains responsible for timeout / retry / fallback

The request envelope also carries:

- `worker_contract_version`
- `required_capabilities`

The server can preflight worker health and capability compatibility before decision POSTs when seat config enables the default healthcheck path.

Frozen examples now cover:

- `purchase_tile`
- `movement`
- `lap_reward`

See `docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md` for a full local session example.
