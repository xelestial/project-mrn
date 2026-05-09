# tools/checks

Check orchestration scripts (lint, unit, integration, e2e wrappers).

Policy guardrails:

- `python tools/encoding_gate.py`
- `python tools/plan_policy_gate.py`
- `.venv/bin/python tools/checks/workflow_gate.py --workflow all`
- `make test-workflow-runtime`
- `make test-workflow-prompt`
- `make test-workflow-protocol`
- `make test-workflow-redis`
- `make test-workflow-rl`
- `make test-workflow-browser`
- `make test-workflow-all`
- `PYTHONPATH=engine .venv/bin/python tools/checks/full_stack_protocol_rl_gate.py --profile smoke --base-url http://127.0.0.1:9091`
- `PYTHONPATH=engine .venv/bin/python tools/checks/full_stack_protocol_rl_gate.py --profile local --base-url http://127.0.0.1:9091`
- `PYTHONPATH=engine .venv/bin/python tools/checks/rl_gate.py --profile smoke`
- `PYTHONPATH=engine .venv/bin/python tools/checks/rl_gate.py --profile local`
- `.venv/bin/python tools/checks/redis_state_inspector.py --session <session_id> --pretty --fail-on critical`

`workflow_gate.py` is the workflow-level test orchestrator. It does not replace focused unit tests; it groups connected checks into named flows so a failure can be read as "runtime transition", "prompt lifecycle", "Redis state", "headless protocol", "RL gate", or "browser gameplay" instead of as an isolated file. It writes a compact `workflow_report.json` and per-stage stdout/stderr logs under `tmp/workflow-gate/` by default.

`make test-workflow-all` intentionally runs the deterministic local workflow set: runtime, prompt, Redis, protocol unit/headless, and engine RL smoke. Browser/live checks need running services, so use `make test-workflow-browser`, `make test-workflow-protocol-live`, or `make test-workflow-all-browser` when the local stack is up.

`full_stack_protocol_rl_gate.py` is the authoritative REST/WebSocket learning gate. It creates real sessions, joins all seats as headless frontend clients, collects compact protocol traces, trains a PyTorch policy, serves it through HTTP, and evaluates the candidate over the same WebSocket decision path. Its smoke profile uses a short official `rules.end` override by default; pass `--config-json` to replace that config. Backend timing logs are required by default, with 5000ms command/transition limits and one Redis/view commit per command boundary.

`rl_gate.py` is engine-only and remains useful for fast policy iteration. It does not validate WebSocket reconnect/resume, frontend selectors, prompt ledgers, or decision acknowledgements.

The smoke profiles are short CI/dev sanity checks. The local profiles run larger quality gates and write artifacts under `tmp/rl/` by default. Local/full profiles exit successfully only when their full acceptance checks pass.
