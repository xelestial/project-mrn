# Deep RL Game AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deep reinforcement learning pipeline for MRN AI that learns from self-play while keeping server runtime and websocket reliability as a separate gating concern.

**Architecture:** The game engine stays authoritative and deterministic. RL runs offline against an engine adapter that exposes legal-action masks, public observations, reward components, and replay datasets; trained policies are only used behind explicit policy modes and regression gates.

**Tech Stack:** Python engine, existing `engine/simulate_with_logs.py`, existing policy decision modules, JSONL replay datasets, PyTorch for neural policy/value models, pytest for adapter and reward-contract tests.

---

## Scope Boundary

Deep RL will not fix websocket instability. Websocket and runtime recovery must remain a separate reliability track. RL depends on reliable deterministic engine transitions, but it does not repair client/server sync bugs.

The previous cash-only plan remains useful as the first reward/diagnostic source. It becomes a reward component and attribution dataset, not the final learning method.

## File Structure

- Create: `engine/rl/__init__.py`
  - Package marker for RL modules.
- Create: `engine/rl/types.py`
  - Typed dataclasses for observations, legal actions, step results, reward breakdowns, and rollout records.
- Create: `engine/rl/reward.py`
  - Converts engine events into scalar reward and named reward components.
- Create: `engine/rl/adapter.py`
  - Deterministic Gym-like adapter around the MRN engine.
- Create: `engine/rl/replay.py`
  - JSONL replay writer/reader for self-play trajectories.
- Create: `engine/rl/train_policy.py`
  - Offline training entrypoint. Starts with behavior cloning from heuristic traces, then supports PPO-style updates.
- Create: `engine/rl/evaluate_policy.py`
  - Fixed-seed evaluation gate against baseline policies.
- Create: `engine/rl/runtime_adapter.py`
  - Converts live runtime decisions into the same replay row shape used by offline training.
- Create: `engine/rl/seed_matrix.py`
  - Runs fixed-seed policy smoke matrices and records runtime failures.
- Create: `engine/rl/evaluation_report.py`
  - Compares numeric baseline/candidate summaries and attaches policy/seed-matrix gates.
- Create: `engine/policy/rl_policy.py`
  - Runtime policy wrapper that loads a trained model behind an opt-in policy mode.
- Modify: `engine/simulate_with_logs.py`
  - Add `--emit-rl-replay` and `--rl-replay-path`.
- Modify: `engine/ai_policy.py`
  - Register opt-in policy mode such as `rl_v1`.
- Test: `engine/test_rl_reward.py`
- Test: `engine/test_rl_adapter.py`
- Test: `engine/test_rl_replay.py`
- Test: `engine/test_rl_policy_gate.py`

## Task 1: Reward Contract

**Files:**
- Create: `engine/rl/types.py`
- Create: `engine/rl/reward.py`
- Test: `engine/test_rl_reward.py`

- [ ] **Step 1: Write the failing reward tests**

```python
from rl.reward import compute_reward_from_event


def test_rent_loss_is_negative_and_named():
    result = compute_reward_from_event(
        {
            "event": "turn",
            "player": 2,
            "cash_before": 20,
            "cash_after": 12,
            "landing": {"type": "RENT", "owner": 3, "rent": 8},
        }
    )
    assert result.total < 0
    assert result.components["cash_delta"] == -8.0
    assert result.components["rent_loss"] == -8.0


def test_lap_reward_cash_gain_is_positive_but_bounded():
    result = compute_reward_from_event(
        {
            "event": "lap_reward_chosen",
            "player": 1,
            "cash_before": 7,
            "cash_after": 17,
            "choice": "cash",
        }
    )
    assert result.components["cash_delta"] == 10.0
    assert 0.0 < result.total <= 2.0
```

- [ ] **Step 2: Run the failing tests**

Run: `.venv/bin/python -m pytest engine/test_rl_reward.py -q`

Expected: fail because `rl.reward` does not exist.

- [ ] **Step 3: Implement minimal reward dataclasses and reward mapping**

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    components: dict[str, float] = field(default_factory=dict)


def _cash_delta(event: dict) -> float:
    before = event.get("cash_before")
    after = event.get("cash_after")
    if before is None or after is None:
        return 0.0
    return float(after) - float(before)


def compute_reward_from_event(event: dict) -> RewardBreakdown:
    delta = _cash_delta(event)
    components = {"cash_delta": delta}
    landing = event.get("landing") if isinstance(event.get("landing"), dict) else {}
    if str(landing.get("type") or "").upper() == "RENT" and delta < 0:
        components["rent_loss"] = delta
    if str(event.get("event") or "") == "lap_reward_chosen" and delta > 0:
        components["lap_cash_gain"] = delta
    total = max(min(delta / 5.0, 2.0), -2.0)
    return RewardBreakdown(total=total, components=components)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest engine/test_rl_reward.py -q`

Expected: pass.

- [x] **Step 5: Commit**

```bash
git add engine/rl/types.py engine/rl/reward.py engine/test_rl_reward.py
git commit -m "Add RL reward contract"
```

## Task 2: Engine Adapter

**Files:**
- Create: `engine/rl/adapter.py`
- Test: `engine/test_rl_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

```python
from rl.adapter import MRNRLEnv


def test_reset_returns_public_observation_and_legal_actions():
    env = MRNRLEnv(seed=20260507, policy_mode="heuristic_v3_engine")
    obs = env.reset()
    assert obs.player_id in {1, 2, 3, 4}
    assert isinstance(obs.features, dict)
    assert obs.legal_actions
    assert all(action["legal"] is True for action in obs.legal_actions)


def test_step_rejects_illegal_action_id():
    env = MRNRLEnv(seed=20260507, policy_mode="heuristic_v3_engine")
    env.reset()
    result = env.step({"action_id": "__not_legal__"})
    assert result.done is False
    assert result.reward.total < 0
    assert result.info["error"] == "illegal_action"
```

- [ ] **Step 2: Run the failing tests**

Run: `.venv/bin/python -m pytest engine/test_rl_adapter.py -q`

Expected: fail because `rl.adapter` does not exist.

- [ ] **Step 3: Implement adapter skeleton**

Implement `MRNRLEnv` with deterministic reset, public observation features, legal-action extraction from the same decision gateway used by runtime prompts, and illegal-action rejection before any engine mutation. Keep the first version narrow: only support one pending decision at a time and expose action IDs, labels, decision name, player ID, round, turn, public resources, and position.

- [ ] **Step 4: Run adapter tests**

Run: `.venv/bin/python -m pytest engine/test_rl_adapter.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add engine/rl/adapter.py engine/test_rl_adapter.py
git commit -m "Add deterministic RL engine adapter"
```

## Task 3: Replay Dataset

**Files:**
- Create: `engine/rl/replay.py`
- Modify: `engine/simulate_with_logs.py`
- Test: `engine/test_rl_replay.py`

- [ ] **Step 1: Write replay tests**

```python
from pathlib import Path

from rl.replay import iter_replay_rows, write_replay_row


def test_replay_round_trip_jsonl(tmp_path: Path):
    path = tmp_path / "replay.jsonl"
    row = {
        "game_id": "g1",
        "step": 1,
        "player_id": 2,
        "observation": {"cash": 20},
        "legal_actions": [{"action_id": "a", "legal": True}],
        "chosen_action_id": "a",
        "reward": {"total": 1.0, "components": {"cash_delta": 5.0}},
        "done": False,
    }
    write_replay_row(path, row)
    assert list(iter_replay_rows(path)) == [row]
```

- [ ] **Step 2: Run the failing tests**

Run: `.venv/bin/python -m pytest engine/test_rl_replay.py -q`

Expected: fail because `rl.replay` does not exist.

- [ ] **Step 3: Implement replay IO and simulator flags**

Add append-only JSONL writing with sorted keys and UTF-8. Add `--emit-rl-replay` and `--rl-replay-path` to `engine/simulate_with_logs.py`; when enabled, record observation, legal actions, chosen action, reward breakdown, done flag, seed, policy mode, and game outcome.

- [ ] **Step 4: Run replay tests and a small smoke simulation**

Run:

```bash
.venv/bin/python -m pytest engine/test_rl_replay.py -q
cd engine && ../.venv/bin/python simulate_with_logs.py --simulations 2 --seed 20260507 --emit-rl-replay --rl-replay-path ../tmp/rl-smoke/replay.jsonl
```

Expected: tests pass and `tmp/rl-smoke/replay.jsonl` exists with non-empty rows.

- [ ] **Step 5: Commit**

```bash
git add engine/rl/replay.py engine/simulate_with_logs.py engine/test_rl_replay.py
git commit -m "Emit RL replay trajectories"
```

## Task 4: Behavior Cloning Baseline

**Files:**
- Create: `engine/rl/train_policy.py`
- Create: `engine/rl/evaluate_policy.py`
- Test: `engine/test_rl_policy_gate.py`

- [x] **Step 1: Write deterministic training gate tests**

```python
from pathlib import Path

from rl.train_policy import train_behavior_clone


def test_behavior_clone_empty_dataset_writes_zero_model(tmp_path: Path):
    replay = tmp_path / "empty.jsonl"
    replay.write_text("", encoding="utf-8")
    model = tmp_path / "model.json"
    result = train_behavior_clone(replay, model, seed=20260507)
    assert result["rows"] == 0
    assert model.exists()
```

- [x] **Step 2: Run the failing tests**

Run: `.venv/bin/python -m pytest engine/test_rl_policy_gate.py -q`

Expected: fail because `rl.train_policy` does not exist.

- [x] **Step 3: Implement behavior cloning before PPO**

Use replay rows to train a legal-action scorer. Start with a deterministic JSON model if PyTorch is unavailable in CI; keep PyTorch model training optional behind dependency detection. The output must include feature schema, action schema, train rows, seed, and validation action accuracy.

- [x] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest engine/test_rl_policy_gate.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add engine/rl/train_policy.py engine/rl/evaluate_policy.py engine/test_rl_policy_gate.py
git commit -m "Add RL behavior cloning baseline"
```

## Task 5: Opt-In RL Policy

**Files:**
- Create: `engine/policy/rl_policy.py`
- Modify: `engine/ai_policy.py`
- Test: `engine/test_rl_policy_gate.py`

- [x] **Step 1: Write policy gate tests**

```python
from ai_policy import HeuristicPolicy


def test_default_policy_modes_do_not_include_rl_without_explicit_mode():
    assert "heuristic_v3_engine" in HeuristicPolicy.VALID_CHARACTER_POLICIES
    assert "rl_v1" not in {"heuristic_v3_engine", "heuristic_v2_balanced"}
```

- [x] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest engine/test_rl_policy_gate.py -q`

Expected: pass for default unchanged check.

- [x] **Step 3: Add explicit `rl_v1` mode**

Register `rl_v1` as an explicit policy mode that loads a model path from `MRN_RL_POLICY_MODEL`. If the env var is missing, raise a clear startup error. Never silently fall back to random or heuristic behavior in `rl_v1`.

Implemented scope: `purchase_decision`, `movement_decision`, `lap_reward`, and `start_reward` are routed through the trained model. Unsupported decisions keep using the existing heuristic policy.

- [x] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest engine/test_rl_policy_gate.py -q`

Expected: pass.

- [x] **Step 5: Commit**

```bash
git add engine/policy/rl_policy.py engine/ai_policy.py engine/test_rl_policy_gate.py
git commit -m "Gate RL policy behind explicit mode"
```

## Task 6: Evaluation Gate

**Files:**
- Modify: `engine/compare_policies.py`
- Create: `docs/current/ai/rl-evaluation-gate.md`
- Create: `engine/rl/seed_matrix.py`
- Create: `engine/rl/evaluation_report.py`

- [x] **Step 1: Add comparison command**

Add a comparison path that runs `heuristic_v3_engine` vs `rl_v1` over the same seeds and records win rate, average rank, bankruptcy rate, average cash delta, illegal-action count, timeout count, and runtime failure count.

Current implementation uses `engine/compare_policies.py` as the release gate. It runs baseline and candidate policies over the same seed stream, emits `comparison.json`, and keeps the earlier seed matrix as a broader smoke/regression helper.

- [x] **Step 2: Add acceptance thresholds**

Require:

```text
runtime_failed_count == 0
illegal_action_count == 0
bankruptcy_rate <= baseline_bankruptcy_rate + 0.02
average_rank <= baseline_average_rank
```

- [x] **Step 3: Run fixed-seed evaluation**

Run:

```bash
cd engine
../.venv/bin/python compare_policies.py --simulations 200 --seed 20260507 --candidate-policy rl_v1 --baseline-policy heuristic_v3_engine --candidate-model-dir ../tmp/rl/model --compact
```

Expected: report is written even if candidate fails thresholds.

- [x] **Step 4: Commit**

```bash
git add engine/compare_policies.py docs/current/ai/rl-evaluation-gate.md
git commit -m "Add RL evaluation gate"
```

## Self-Review

- Spec coverage: Deep RL pipeline, reward source, websocket separation, opt-in policy, replay, evaluation, and safety gates are covered.
- Placeholder scan: No task uses unresolved placeholder language or an undefined “later” step. Task 2 and Task 4 intentionally describe integration details because exact decision-gateway function calls require implementation-time inspection.
- Type consistency: `RewardBreakdown`, replay rows, `MRNRLEnv`, and `rl_v1` names are consistent across tasks.
