# RL Evaluation Gate

Status: ACTIVE

## Purpose

`rl_v1` is an opt-in learned policy. It must pass a fixed-seed comparison gate before anyone treats it as a candidate for broader use.

The gate compares a baseline policy and a candidate policy over the same deterministic seed stream, then writes `comparison.json`.

Default comparison:

- Baseline: `heuristic_v3_engine`
- Candidate: `rl_v1`
- LAP policy: `heuristic_v3_engine`

## Command

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

`comparison.json` is still written when the candidate fails. Failed reports are useful evidence and should not be discarded.

## Current Limitation

Average rank is weak when all four players use the same policy, because the population is symmetric. It is still useful as a safety regression check, but a stronger mixed-seat evaluation should be added before a learned policy becomes a default policy.
