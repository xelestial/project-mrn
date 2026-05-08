# tools/checks

Check orchestration scripts (lint, unit, integration, e2e wrappers).

Policy guardrails:

- `python tools/encoding_gate.py`
- `python tools/plan_policy_gate.py`
- `PYTHONPATH=engine .venv/bin/python tools/checks/full_stack_protocol_rl_gate.py --profile smoke --base-url http://127.0.0.1:9091`
- `PYTHONPATH=engine .venv/bin/python tools/checks/full_stack_protocol_rl_gate.py --profile local --base-url http://127.0.0.1:9091`
- `PYTHONPATH=engine .venv/bin/python tools/checks/rl_gate.py --profile smoke`
- `PYTHONPATH=engine .venv/bin/python tools/checks/rl_gate.py --profile local`

`full_stack_protocol_rl_gate.py` is the authoritative REST/WebSocket learning gate. It creates real sessions, joins all seats as headless frontend clients, collects compact protocol traces, trains a PyTorch policy, serves it through HTTP, and evaluates the candidate over the same WebSocket decision path. Its smoke profile uses a short `runtime.max_turns` override by default; pass `--config-json` to replace that config.

`rl_gate.py` is engine-only and remains useful for fast policy iteration. It does not validate WebSocket reconnect/resume, frontend selectors, prompt ledgers, or decision acknowledgements.

The smoke profiles are short CI/dev sanity checks. The local profiles run larger quality gates and write artifacts under `tmp/rl/` by default. Local/full profiles exit successfully only when their full acceptance checks pass.
