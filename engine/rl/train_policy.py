from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Iterable

from rl.replay import iter_replay_rows


MODEL_JSON = "policy_model.json"
MODEL_PT = "policy_model.pt"
_MODEL_CACHE: dict[tuple[str, int, int], tuple[Any, dict[str, Any]]] = {}
_MAX_MODEL_CACHE_SIZE = 4


def train_behavior_clone(
    *,
    replay_path: str | Path,
    output_dir: str | Path,
    seed: int = 20260507,
    epochs: int = 8,
    hidden_size: int = 64,
    learning_rate: float = 0.01,
    validation_fraction: float = 0.2,
) -> dict[str, Any]:
    rows = list(iter_replay_rows(replay_path))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not rows:
        result = _empty_model(seed=seed)
        _write_json(out / MODEL_JSON, result)
        return result

    torch = _load_torch()
    random.Random(seed).shuffle(rows)
    feature_schema = {
        "version": 2,
        "numeric_slots": 32,
        "hash_slots": 96,
        "feature_dim": 128,
        "hash_fields": [
            "decision_key",
            "action_id",
            "player_id",
            "character",
            "request_type",
            "module_type",
            "action_label",
        ],
    }
    examples = _build_training_examples(rows, feature_schema)
    if not examples:
        result = _empty_model(seed=seed, rows=len(rows))
        _write_json(out / MODEL_JSON, result)
        return result

    split_index = max(1, int(len(examples) * (1.0 - validation_fraction)))
    if split_index >= len(examples) and len(examples) > 1:
        split_index = len(examples) - 1
    train_examples = examples[:split_index]
    validation_examples = examples[split_index:] or examples[:]

    torch.manual_seed(seed)
    model = _ActionScorer(feature_schema["feature_dim"], hidden_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_fn = torch.nn.BCEWithLogitsLoss(reduction="none")

    x_train = torch.tensor([item[0] for item in train_examples], dtype=torch.float32)
    y_train = torch.tensor([[item[1]] for item in train_examples], dtype=torch.float32)
    w_train = torch.tensor([[item[2]] for item in train_examples], dtype=torch.float32)
    for _ in range(max(1, epochs)):
        optimizer.zero_grad(set_to_none=True)
        logits = model(x_train)
        losses = loss_fn(logits, y_train)
        loss = (losses * w_train).sum() / w_train.sum().clamp_min(1.0)
        loss.backward()
        optimizer.step()

    validation_accuracy = _validation_accuracy(torch, model, validation_examples)
    metadata = {
        "model_type": "torch_behavior_clone",
        "seed": seed,
        "rows": len(rows),
        "train_examples": len(examples),
        "epochs": max(1, epochs),
        "hidden_size": hidden_size,
        "learning_rate": learning_rate,
        "validation_accuracy": validation_accuracy,
        "sample_weight": _sample_weight_summary(examples),
        "feature_schema": feature_schema,
        "action_schema": _action_schema(rows),
    }
    torch.save({"state_dict": model.state_dict(), "metadata": metadata}, out / MODEL_PT)
    _write_json(out / MODEL_JSON, metadata)
    return metadata


def predict_action(*, model_dir: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    out = Path(model_dir)
    metadata_path = out / MODEL_JSON
    if not metadata_path.exists():
        raise FileNotFoundError(f"RL policy metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    legal_actions = [action for action in row.get("legal_actions") or [] if action.get("legal", True)]
    if not legal_actions:
        return {"action_id": "", "scores": []}
    if metadata.get("model_type") == "empty":
        return {"action_id": str(legal_actions[0].get("action_id") or ""), "scores": []}

    torch = _load_torch()
    model, model_metadata = _load_policy_model(out, metadata)
    feature_schema = model_metadata["feature_schema"]

    scored: list[dict[str, Any]] = []
    with torch.no_grad():
        for action in legal_actions:
            action_id = str(action.get("action_id") or "")
            vector = torch.tensor([_vectorize(row, action_id, feature_schema)], dtype=torch.float32)
            score = float(torch.sigmoid(model(vector))[0][0].item())
            scored.append({"action_id": action_id, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"action_id": scored[0]["action_id"], "scores": scored}


class _ActionScorer:
    def __new__(cls, feature_dim: int, hidden_size: int):
        torch = _load_torch()

        class ActionScorer(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.layers = torch.nn.Sequential(
                    torch.nn.Linear(feature_dim, hidden_size),
                    torch.nn.ReLU(),
                    torch.nn.Linear(hidden_size, max(4, hidden_size // 2)),
                    torch.nn.ReLU(),
                    torch.nn.Linear(max(4, hidden_size // 2), 1),
                )

            def forward(self, x):
                return self.layers(x)

        return ActionScorer()


def _build_training_examples(rows: Iterable[dict[str, Any]], feature_schema: dict[str, Any]) -> list[tuple[list[float], float, float]]:
    examples: list[tuple[list[float], float, float]] = []
    for row in rows:
        chosen = str(row.get("chosen_action_id") or "")
        row_weight = _row_sample_weight(row)
        for action in row.get("legal_actions") or []:
            if not action.get("legal", True):
                continue
            action_id = str(action.get("action_id") or "")
            label = 1.0 if action_id == chosen else 0.0
            action_weight = row_weight * _action_sample_weight(row, action)
            weight = action_weight if label else max(0.25, action_weight * 0.45)
            examples.append((_vectorize(row, action_id, feature_schema), label, weight))
    return examples


def _vectorize(row: dict[str, Any], action_id: str, feature_schema: dict[str, Any]) -> list[float]:
    numeric_slots = int(feature_schema["numeric_slots"])
    hash_slots = int(feature_schema["hash_slots"])
    values = _numeric_values(row.get("observation") or {})[:numeric_slots]
    vector = [0.0] * (numeric_slots + hash_slots)
    for index, value in enumerate(values):
        vector[index] = max(-10.0, min(10.0, float(value) / 20.0))
    hash_base = numeric_slots
    for token in _hash_tokens(row, action_id):
        bucket = _stable_hash(token) % hash_slots
        vector[hash_base + bucket] += 1.0
    return vector


def _numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return [1.0 if value else 0.0]
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        result: list[float] = []
        for key in sorted(value.keys()):
            result.extend(_numeric_values(value[key]))
        return result
    if isinstance(value, list):
        result: list[float] = []
        for item in value:
            result.extend(_numeric_values(item))
        return result
    return []


def _hash_tokens(row: dict[str, Any], action_id: str) -> list[str]:
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    prompt = row.get("prompt") if isinstance(row.get("prompt"), dict) else {}
    matching_action = next(
        (
            action
            for action in row.get("legal_actions") or []
            if str(action.get("action_id") or "") == action_id
        ),
        {},
    )
    action_label = ""
    if isinstance(matching_action, dict):
        action_label = str(matching_action.get("label") or matching_action.get("title") or "")
    return [
        f"decision:{row.get('decision_key')}",
        f"action:{action_id}",
        f"decision_action:{row.get('decision_key')}:{action_id}",
        f"player:{row.get('player_id')}",
        f"character:{observation.get('character')}",
        f"request:{prompt.get('request_type') or row.get('request_type') or row.get('decision_key')}",
        f"module:{prompt.get('module_type') or observation.get('module_type')}",
        f"action_label:{action_label}",
        f"legal_count:{len(row.get('legal_actions') or [])}",
    ]


def _stable_hash(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _validation_accuracy(torch: Any, model: Any, validation_examples: list[tuple[list[float], float, float]]) -> float:
    if not validation_examples:
        return 0.0
    x_val = torch.tensor([item[0] for item in validation_examples], dtype=torch.float32)
    y_val = torch.tensor([item[1] for item in validation_examples], dtype=torch.float32)
    with torch.no_grad():
        predicted = (torch.sigmoid(model(x_val)).reshape(-1) >= 0.5).float()
    return float((predicted == y_val).float().mean().item())


def _row_sample_weight(row: dict[str, Any]) -> float:
    raw = row.get("sample_weight")
    if isinstance(raw, (int, float)):
        return max(0.25, min(8.0, float(raw)))
    reward = row.get("reward") if isinstance(row.get("reward"), dict) else {}
    reward_total = float(reward.get("total") or 0.0)
    outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
    weight = 1.0 + min(1.5, abs(reward_total) * 0.5)
    if outcome.get("won"):
        weight += 0.6
    rank = _outcome_rank(outcome)
    if rank == 1:
        weight += 0.6
    elif rank >= 4:
        weight += 0.35
    if outcome.get("bankrupt") or outcome.get("bankruptcy") or outcome.get("alive") is False:
        weight += 0.75
    components = reward.get("components") if isinstance(reward.get("components"), dict) else {}
    for key, value in components.items():
        if not isinstance(value, (int, float)):
            continue
        if any(token in str(key) for token in ("cash", "money", "coin", "shard", "score", "rent", "bankrupt", "end_time", "f_value")):
            weight += min(1.25, abs(float(value)) * 0.35)
    return max(0.25, min(8.0, weight))


def _action_sample_weight(row: dict[str, Any], action: dict[str, Any]) -> float:
    decision_key = str(row.get("decision_key") or "")
    action_id = str(action.get("action_id") or "")
    label = str(action.get("label") or action.get("title") or "")
    text = f"{decision_key} {action_id} {label}".lower()
    multiplier = 1.0
    if any(token in text for token in ("cash", "money", "coin", "buy", "rent", "냥", "돈", "엽전", "구매", "렌트")):
        multiplier += 0.2
    if any(token in text for token in ("shard", "score", "point", "조각", "승점", "점수")):
        multiplier += 0.2
    if any(token in text for token in ("move", "dice", "fortune", "이동", "주사위", "운수")):
        multiplier += 0.15
    return min(1.6, multiplier)


def _outcome_rank(outcome: dict[str, Any]) -> int:
    value = outcome.get("rank", outcome.get("final_rank"))
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _load_policy_model(model_dir: Path, metadata: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    model_path = model_dir / MODEL_PT
    json_path = model_dir / MODEL_JSON
    if not model_path.exists():
        raise FileNotFoundError(f"RL policy weights not found: {model_path}")
    key = (
        str(model_path.resolve()),
        model_path.stat().st_mtime_ns,
        json_path.stat().st_mtime_ns if json_path.exists() else 0,
    )
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    torch = _load_torch()
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model_metadata = checkpoint.get("metadata") or metadata
    feature_schema = model_metadata["feature_schema"]
    model = _ActionScorer(feature_schema["feature_dim"], int(model_metadata["hidden_size"]))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    if len(_MODEL_CACHE) >= _MAX_MODEL_CACHE_SIZE:
        _MODEL_CACHE.clear()
    _MODEL_CACHE[key] = (model, model_metadata)
    return model, model_metadata


def _sample_weight_summary(examples: list[tuple[list[float], float, float]]) -> dict[str, float]:
    weights = [float(item[2]) for item in examples]
    if not weights:
        return {"min": 0.0, "max": 0.0, "avg": 0.0}
    return {
        "min": min(weights),
        "max": max(weights),
        "avg": sum(weights) / len(weights),
    }


def _action_schema(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decision_actions: dict[str, set[str]] = {}
    for row in rows:
        decision_key = str(row.get("decision_key") or "unknown")
        decision_actions.setdefault(decision_key, set())
        for action in row.get("legal_actions") or []:
            decision_actions[decision_key].add(str(action.get("action_id") or ""))
    return {
        "version": 1,
        "decisions": {decision: sorted(actions) for decision, actions in sorted(decision_actions.items())},
    }


def _empty_model(*, seed: int, rows: int = 0) -> dict[str, Any]:
    return {
        "model_type": "empty",
        "seed": seed,
        "rows": rows,
        "train_examples": 0,
        "validation_accuracy": 0.0,
        "feature_schema": {"version": 2, "numeric_slots": 32, "hash_slots": 96, "feature_dim": 128},
        "action_schema": {"version": 1, "decisions": {}},
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_torch():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required for RL policy training. Install it in .venv with: .venv/bin/python -m pip install torch numpy") from exc
    return torch


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a torch behavior-cloning RL policy from MRN replay JSONL.")
    parser.add_argument("replay_path")
    parser.add_argument("output_dir")
    parser.add_argument("--seed", type=int, default=20260507)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--hidden-size", type=int, default=64)
    args = parser.parse_args()
    result = train_behavior_clone(
        replay_path=args.replay_path,
        output_dir=args.output_dir,
        seed=args.seed,
        epochs=args.epochs,
        hidden_size=args.hidden_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
