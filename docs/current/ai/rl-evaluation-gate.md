# RL Evaluation Gate

Status: ACTIVE

## Purpose

`rl_v1` is an opt-in learned policy. It must pass a fixed-seed comparison gate before anyone treats it as a candidate for broader use.

There are two gates:

- Full-stack protocol gate: authoritative stability gate. It runs the same REST, WebSocket, prompt, decision, ack, and `view_commit` path as a real game.
- Engine-only gate: fast baseline and debugging gate. It compares a baseline policy and a candidate policy over the same deterministic seed stream, then writes `comparison.json`.

Do not treat an engine-only pass as production readiness. It does not exercise WebSocket reconnect/resume, session joins, prompt ledgers, decision acknowledgements, or frontend selector contracts.

## Full-Stack Protocol Gate

The full-stack gate starts a real server stack, creates a session through REST, joins every seat as a headless-human client, starts the game, and drives all player decisions over WebSocket. The frontend side does not render React. It uses the shared stream contract, reducer/selectors, and decision protocol through `HeadlessGameClient`.

Start the live stack:

```bash
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml up -d --build
```

The protocol Redis instance must run with `maxmemory-policy noeviction` and enough memory for a full live game. The default compose value is `2gb`. Evicting keys such as runtime leases, command sequence keys, or current state can make a healthy WebSocket client observe a broken game. `allkeys-lru` is invalid for this gate. Hitting Redis OOM is also invalid; a live run with `total_error_replies > 0` is rejected even when `evicted_keys == 0`.

Check Redis before running:

```bash
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml exec -T redis \
  redis-cli CONFIG GET maxmemory

docker compose -p project-mrn-protocol -f docker-compose.protocol.yml exec -T redis \
  redis-cli CONFIG GET maxmemory-policy

docker compose -p project-mrn-protocol -f docker-compose.protocol.yml exec -T redis \
  redis-cli INFO stats
```

Run one live protocol game:

```bash
cd apps/web
npm run rl:protocol-gate -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --seed 20260525 \
  --timeout-ms 1800000 \
  --idle-timeout-ms 120000 \
  --out /tmp/mrn_protocol_trace_live_20260525.jsonl \
  --replay-out /tmp/mrn_rl_replay_live_20260525.jsonl \
  --progress-interval-ms 30000
```

For short protocol debugging runs, pass official server end-rule config through the session-create payload:

```bash
cd apps/web
npm run rl:protocol-gate -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --seed 20260525 \
  --config-json '{"rules":{"end":{"f_threshold":4,"monopolies_to_trigger_end":1,"tiles_to_trigger_end":4,"alive_players_at_most":1}}}'
```

To evaluate a policy served outside the Node process, use the HTTP policy bridge. The bridge receives only legal choices and compact projected state from that player's WebSocket projection; it does not receive hidden payloads or raw `view_state`.

```bash
cd apps/web
npm run rl:protocol-gate -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --policy http \
  --policy-http-url http://127.0.0.1:7777/decide \
  --policy-http-timeout-ms 2000
```

The command writes a compact protocol trace and an RL replay conversion. It also writes progress snapshots to stderr so long-running games can be inspected without stopping the run.

Run repeated live protocol games through the dedicated runner, not a hand-written shell loop with `tee`:

```bash
cd apps/web
npm run rl:protocol-gate:games -- \
  --games 5 \
  --run-root tmp/rl/full-stack-protocol/backend-timing-gate \
  --seed-base 2026051100 \
  -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --timeout-ms 600000 \
  --idle-timeout-ms 120000 \
  --progress-interval-ms 10000 \
  --raw-prompt-fallback-delay-ms off \
  --require-backend-timing \
  --max-backend-command-ms 4000 \
  --max-backend-transition-ms 4000 \
  --max-backend-redis-commit-count 1 \
  --max-backend-view-commit-count 1 \
  --backend-docker-compose-project project-mrn-protocol \
  --backend-docker-compose-file ../../docker-compose.protocol.yml \
  --backend-docker-compose-service server
```

The runner resolves `--run-root` from the repository root and passes absolute `--out`, `--replay-out`, and `--summary-out` paths to each game. This avoids the known failure mode where `npm --prefix apps/web` changes the npm script cwd while shell `tee` still resolves paths from the outer shell cwd.

Full-stack acceptance requires:

- `runtime_failed == 0`
- `illegal_action == 0`
- `timeout == 0`
- one-game wall-clock duration stays under 10 minutes for the normal no-deliberation click-through path, unless the run intentionally measures slow human deliberation or production-length endurance
- rejected decision acknowledgements `== 0`
- decision fallback count `== 0`
- unrecovered stale decision acknowledgements `== 0`
- unbounded or policy-recomputed retries for the same active prompt `== 0`
- stream/client error count `== 0`
- non-monotonic commit sequence count `== 0`
- semantic runtime position regression count `== 0`
- reconnect/resume repair failures `== 0`
- Redis `evicted_keys == 0`
- Redis `total_error_replies == 0`
- final runtime status reaches `completed`

The gate must fail fast on apparent "waiting" when the active prompt is unchanged and the client has already sent a decision. The only allowed recovery is a bounded resend of the same decision selected for that prompt. The adapter must not invoke the policy again for the same `request_id`, because that hides ACK loss and makes the browser path differ from RL training.

Duration is itself a stability signal. Human games become long because players deliberate to win, not because the protocol needs that time. A single familiar operator clicking through the normal flow without deliberation can complete one game within 10 minutes, so a headless one-game run that exceeds 10 minutes is presumed broken until trace, server, and Redis logs prove the delay was intentional.

After a live run, inspect server logs for runtime or storage guardrail events:

```bash
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml logs \
  server command-wakeup-worker prompt-timeout-worker --since 40m
```

For every live headless RL run, compare the trace, server logs, and Redis command records before accepting the result:

- report wall-clock duration and harness `duration_ms`
- report per-command timing from both the frontend trace (`prompt -> decision -> ack`) and `runtime_command_process_timing`
- compare trace `decision_sent`, server `decision_received`, trace `decision_ack`, and Redis `decision_submitted`
- report `decision_timeout_fallback_seen`, Redis fallback entries, rejected ACKs, stale ACKs, send failures, and client errors
- report per-seat accepted decisions, prompt observations, suppressed duplicates, stale retries, and unacked retries
- investigate any player that appears to build commands alone; do not wait for timeout to explain it away
- if reconnect fires after `decision_sent`, the same active prompt must be resent immediately as a bounded unacked retry; a 5-second retry wait is a protocol defect, not acceptable learning latency
- if server logs show `runtime_wakeup_deferred_command` / `command_processing_already_active`, verify the same command is retried and then appears in `runtime_command_process_timing`; an accepted-but-never-reprocessed command is a game-stopping protocol bug
- run live protocol gates against `http://127.0.0.1:9091` unless the protocol compose port is explicitly overridden
- stop the run immediately on the first protocol suspicion (`decision_timeout_fallback_seen`, rejected ACK, illegal action, stream/client error, private data leak, malformed identity, or Redis/server/trace mismatch); do not continue RL training on suspect data

Passing example evidence shape:

```text
duration: wall_ms and duration_ms recorded
decisions: trace sent == server received == trace ack == Redis submitted
fallbacks: 0
rejected/stale/send_failure/client_error: 0
runtime_status: completed
```

The `contract` profile is for faster protocol regression checks. It is useful in CI, but the live profile is the RL stability gate.

Default comparison:

- Baseline: `heuristic_v3_engine`
- Candidate: `rl_v1`
- LAP policy: `heuristic_v3_engine`

## Command

Run the full-stack learning and live protocol evaluation pipeline:

```bash
PYTHONPATH=engine .venv/bin/python tools/checks/full_stack_protocol_rl_gate.py \
  --profile smoke \
  --base-url http://127.0.0.1:9091
```

The smoke profile runs one baseline live game, converts the protocol trace to replay rows, trains a small PyTorch behavior-clone model, serves it through the HTTP policy bridge, and runs one candidate live game over the same REST/WebSocket/prompt/decision path. By default it uses the short official `rules.end` override shown above so CI/dev runs do not depend on a long production-length game. Pass `--config-json` to replace that default. The larger profiles increase the seed matrix and use normal game configuration unless a config override is supplied:

```bash
PYTHONPATH=engine .venv/bin/python tools/checks/full_stack_protocol_rl_gate.py \
  --profile local \
  --base-url http://127.0.0.1:9091
```

The full-stack pipeline writes:

- `baseline/seed_*/protocol_trace.jsonl`
- `baseline/seed_*/rl_replay.jsonl`
- `train/rl_replay.jsonl`
- `model/policy_model.json`
- `model/policy_model.pt` when PyTorch training has data
- `policy_server/stdout.log`
- `policy_server/stderr.log`
- `candidate/seed_*/protocol_trace.jsonl`
- `candidate/seed_*/rl_replay.jsonl`
- `pipeline_summary.json`

Use `pipeline_summary.json` as the primary report. A smoke run exits successfully only when the baseline and candidate protocol runs are stable and training data was produced. The local/full profiles exit successfully only when the stability and quality checks both pass.

## Engine-Only Command

Run the auxiliary engine-only local gate pipeline:

```bash
PYTHONPATH=engine .venv/bin/python tools/checks/rl_gate.py --profile local
```

The direct module command is equivalent and allows explicit parameter overrides:

```bash
PYTHONPATH=engine .venv/bin/python -m rl.gate_pipeline \
  --output-dir tmp/rl/gate \
  --train-games 200 \
  --eval-games 100 \
  --mixed-seat-games 20 \
  --epochs 8 \
  --hidden-size 64 \
  --seed 20260507
```

The pipeline writes:

- `train_source/rl_replay.jsonl`
- `model/policy_model.json`
- `model/policy_model.pt` when PyTorch training has data
- `compare/comparison.json`
- `learning_diagnostics.json`
- `pipeline_summary.json`

Use this pipeline for fast policy iteration and debugging. It is not a replacement for the full-stack live protocol gate because it does not exercise REST session lifecycle, WebSocket reconnect/resume, frontend selectors, prompt ledgers, or decision acknowledgements.

Use `pipeline_summary.json` as the first engine-only reporting artifact. Use `learning_diagnostics.json` to inspect the highest-weight losing samples, worst action buckets, and failed comparison checks.

For a short sanity check:

```bash
PYTHONPATH=engine .venv/bin/python tools/checks/rl_gate.py --profile smoke
```

The smoke profile fails only on runtime failures, illegal actions, or timeouts. It still reports quality-gate rejection in JSON, but that rejection is not enough to fail the smoke command. The local profile fails unless the full acceptance gate passes.

Manual steps are still available when a run needs to be split apart.

Generate fresh replay rows:

```bash
PYTHONPATH=engine .venv/bin/python engine/simulate_with_logs.py \
  --games 100 \
  --seed 20260507 \
  --output-dir tmp/rl-train-source \
  --policy-mode heuristic_v3_engine \
  --lap-policy-mode heuristic_v3_engine \
  --log-level none \
  --emit-rl-replay \
  --rl-replay-path tmp/rl/replay.jsonl
```

Train a behavior-clone baseline model:

```bash
PYTHONPATH=engine .venv/bin/python -m rl.train_policy \
  tmp/rl/replay.jsonl \
  tmp/rl/model \
  --epochs 4 \
  --hidden-size 64
```

Run the acceptance gate:

```bash
PYTHONPATH=engine .venv/bin/python engine/compare_policies.py \
  --simulations 50 \
  --seed 20260507 \
  --baseline-policy heuristic_v3_engine \
  --candidate-policy rl_v1 \
  --candidate-model-dir tmp/rl/model \
  --policy-eval-replay tmp/rl/replay.jsonl \
  --mixed-seat-simulations 20 \
  --output-dir tmp/rl/compare \
  --compact
```

## Acceptance Checks

The candidate is accepted only when every check passes:

- `runtime_failed_count == 0`
- `illegal_action_count == 0`
- `timeout_count == 0`
- `candidate.bankruptcy_rate <= baseline.bankruptcy_rate + 0.02`
- `candidate.average_rank <= baseline.average_rank`
- If `--mixed-seat-simulations` is set:
  - each seat is evaluated once with only that player using `rl_v1`
  - aggregate mixed-seat bankruptcy rate must not regress beyond `0.02`
  - aggregate mixed-seat average rank must not regress

`comparison.json` is still written when the candidate fails. Failed reports are useful evidence and should not be discarded.

## Mixed-Seat Mode

Self-play average rank is weak when all four players use the same policy, because the population is symmetric. Mixed-seat mode addresses that by rotating `rl_v1` through player seats 1-4 while the other three seats stay on the baseline policy.

The report writes per-seat rotations under `mixed_seat.rotations[]` and an aggregate under `mixed_seat.aggregate`.

## Diagnostics

Build diagnostics from existing artifacts:

```bash
PYTHONPATH=engine .venv/bin/python -m rl.diagnostics \
  --replay tmp/rl/replay.jsonl \
  --comparison tmp/rl/compare/comparison.json \
  --output tmp/rl/learning_diagnostics.json
```

The diagnostics report groups replay rows by decision and action, tracks average reward and sample weight, lists high-weight losses, and copies failed gate checks from the comparison report. This is the starting point for deciding whether the next change belongs in reward shaping, legal-action modeling, or policy architecture.

## Headless Protocol Timing

Headless protocol runs are timing evidence only when the adapter behaves like a fast browser operator. The default adapter must choose bounded legal actions for repeatable optional prompts. In particular, `burden_exchange` defaults to `no`; choosing `yes` repeatedly is a deliberate stress scenario and must be labeled separately before using the run as game-duration evidence.

When a live run is slow, inspect command latency before continuing training:

- prompt-to-decision latency should stay near client-policy latency.
- decision-to-ACK latency identifies backend/runtime/Redis delay.
- repeated optional prompt types, especially `burden_exchange`, must be counted by request type and choice id.
- if the same module frame emits many batches from one turn, stop learning and classify whether the adapter policy or engine rule caused the churn.
- if a decision ACK is accepted but runtime status later becomes `rejected`, stop the run immediately. Compare the command payload, checkpoint `runtime_active_prompt`, and replayed module prompt; a mismatch means the continuation contract broke, not that the learner should keep waiting.
