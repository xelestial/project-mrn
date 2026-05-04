from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from config import DEFAULT_CONFIG
from simulate_with_logs import run as simulate_run
from text_encoding import configure_utf8_io

FEATURE_NAMES = [
    "turn_progress",
    "reverse_turn_index",
    "alive_players",
    "f_value",
    "own_cash",
    "own_tiles",
    "own_hand_coins",
    "own_shards",
    "own_laps_completed",
    "cash_margin_vs_best",
    "tiles_margin_vs_best",
    "hand_margin_vs_best",
    "shards_margin_vs_best",
    "laps_margin_vs_best",
    "laps_gained",
    "lap_reward_count",
    "used_trick",
    "used_pair_move",
    "landing_purchase",
    "landing_takeover",
    "landing_rent",
    "landing_special",
    "landing_bankrupt",
]


def load_games_jsonl(path: str | Path) -> list[dict]:
    games = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                games.append(json.loads(line))
    return games


def _starting_player_state() -> dict:
    return {
        "cash": DEFAULT_CONFIG.economy.starting_cash,
        "tiles": 0,
        "hand_coins": DEFAULT_CONFIG.coins.starting_hand_coins,
        "shards": DEFAULT_CONFIG.shards.starting_shards,
        "laps_completed": 0,
        "position": DEFAULT_CONFIG.initial_position_index,
        "alive": True,
        "character": None,
    }


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def _landing_flags(turn_row: dict) -> dict[str, int]:
    landing = turn_row.get("landing") or {}
    ltype = landing.get("type", "")
    cell = turn_row.get("cell", "")
    return {
        "landing_purchase": int("PURCHASE" in ltype),
        "landing_takeover": int("TAKEOVER" in ltype),
        "landing_rent": int(ltype == "RENT" or "RENT" in ltype),
        "landing_special": int(cell in {"F1", "F2", "S"}),
        "landing_bankrupt": int(bool(landing.get("bankrupt"))),
    }


def _best_opponent_value(states: dict[int, dict], pid: int, key: str) -> float:
    others = [s.get(key, 0) for opid, s in states.items() if opid != pid and s.get("alive", True)]
    return max(others) if others else 0.0


def extract_turn_feature_rows(games: Iterable[dict]) -> list[dict]:
    rows: list[dict] = []
    for game in games:
        total_turns = int(game.get("total_turns", 0))
        winner_ids = set(int(w) for w in game.get("winner_ids", []))
        player_states = {pid: _starting_player_state() for pid in range(1, 5)}
        events_in_turn: list[dict] = []
        action_log = list(game.get("action_log") or [])
        for event in action_log:
            if event.get("event") != "turn":
                events_in_turn.append(event)
                continue
            pid = int(event["player"])
            state = player_states[pid]
            laps_gained = int(event.get("laps_gained", 0) or 0)
            lap_events = list(event.get("lap_events") or [])
            used_trick = int(any(e.get("event") == "trick_used" and int(e.get("player", -1)) == pid for e in events_in_turn))
            movement = event.get("movement") or {}
            used_pair_move = int(movement.get("mode") in {"card_pair_fixed", "card_pair", "card_pair_plus_die"} or len(movement.get("used_cards") or []) >= 2)

            state.update(
                {
                    "cash": float(event.get("cash_after", state["cash"])),
                    "tiles": float(event.get("tiles_after", state["tiles"])),
                    "hand_coins": float(event.get("hand_coins_after", state["hand_coins"])),
                    "shards": float(event.get("shards_after", state["shards"])),
                    "position": int(event.get("end_pos", state["position"])),
                    "alive": bool(event.get("alive_after", state["alive"])),
                    "character": event.get("character") or state.get("character"),
                    "laps_completed": float(state.get("laps_completed", 0) + laps_gained),
                }
            )
            alive_players = sum(1 for s in player_states.values() if s.get("alive", True))
            reverse_turn_index = max(total_turns - int(event.get("turn_index_global", 0)), 0)
            turn_progress = _safe_div(float(event.get("turn_index_global", 0)), float(total_turns))
            flags = _landing_flags(event)
            row = {
                "game_id": game.get("global_game_index", game.get("game_id", 0)),
                "chunk_game_id": game.get("game_id", 0),
                "turn_index_global": int(event.get("turn_index_global", 0)),
                "round_index": int(event.get("round_index", 0)),
                "player_id": pid,
                "character": state.get("character") or "",
                "won": int(pid in winner_ids),
                "turns_to_end": reverse_turn_index,
                "end_reason": game.get("end_reason", ""),
                "turn_progress": turn_progress,
                "reverse_turn_index": float(reverse_turn_index),
                "alive_players": float(alive_players),
                "f_value": float(event.get("f_after", event.get("f_before", 0.0)) or 0.0),
                "own_cash": float(state["cash"]),
                "own_tiles": float(state["tiles"]),
                "own_hand_coins": float(state["hand_coins"]),
                "own_shards": float(state["shards"]),
                "own_laps_completed": float(state["laps_completed"]),
                "cash_margin_vs_best": float(state["cash"] - _best_opponent_value(player_states, pid, "cash")),
                "tiles_margin_vs_best": float(state["tiles"] - _best_opponent_value(player_states, pid, "tiles")),
                "hand_margin_vs_best": float(state["hand_coins"] - _best_opponent_value(player_states, pid, "hand_coins")),
                "shards_margin_vs_best": float(state["shards"] - _best_opponent_value(player_states, pid, "shards")),
                "laps_margin_vs_best": float(state["laps_completed"] - _best_opponent_value(player_states, pid, "laps_completed")),
                "laps_gained": float(laps_gained),
                "lap_reward_count": float(len(lap_events)),
                "used_trick": float(used_trick),
                "used_pair_move": float(used_pair_move),
                **{k: float(v) for k, v in flags.items()},
            }
            rows.append(row)
            events_in_turn = []
    return rows


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def build_summary(games: list[dict], turn_rows: list[dict]) -> dict:
    by_bucket: dict[str, list[int]] = defaultdict(list)
    for row in turn_rows:
        t = int(row["turns_to_end"])
        if t <= 4:
            bucket = "late_0_4"
        elif t <= 9:
            bucket = "late_5_9"
        elif t <= 19:
            bucket = "mid_10_19"
        else:
            bucket = "early_20_plus"
        by_bucket[bucket].append(row["won"])

    event_counter = Counter()
    for row in turn_rows:
        for key in ("landing_purchase", "landing_takeover", "landing_rent", "landing_special", "used_trick", "used_pair_move"):
            if row.get(key):
                event_counter[key] += 1

    return {
        "games": len(games),
        "turn_rows": len(turn_rows),
        "avg_turns_per_game": _mean(g.get("total_turns", 0) for g in games),
        "win_rate_by_stage": {k: _mean(v) for k, v in by_bucket.items()},
        "event_counts": dict(event_counter),
    }


def train_logistic_model(turn_rows: list[dict], *, epochs: int = 250, lr: float = 0.05, l2: float = 1e-4) -> dict:
    if not turn_rows:
        return {
            "feature_names": FEATURE_NAMES,
            "means": {name: 0.0 for name in FEATURE_NAMES},
            "scales": {name: 1.0 for name in FEATURE_NAMES},
            "weights": {name: 0.0 for name in FEATURE_NAMES},
            "bias": 0.0,
            "train_rows": 0,
        }
    means = {name: _mean(row[name] for row in turn_rows) for name in FEATURE_NAMES}
    scales = {}
    for name in FEATURE_NAMES:
        variance = _mean((row[name] - means[name]) ** 2 for row in turn_rows)
        scales[name] = math.sqrt(variance) if variance > 1e-12 else 1.0
    weights = {name: 0.0 for name in FEATURE_NAMES}
    bias = 0.0
    for _ in range(epochs):
        grad_w = {name: 0.0 for name in FEATURE_NAMES}
        grad_b = 0.0
        for row in turn_rows:
            z = bias
            for name in FEATURE_NAMES:
                z += weights[name] * ((row[name] - means[name]) / scales[name])
            p = 1.0 / (1.0 + math.exp(-max(min(z, 30.0), -30.0)))
            err = p - float(row["won"])
            grad_b += err
            for name in FEATURE_NAMES:
                grad_w[name] += err * ((row[name] - means[name]) / scales[name])
        n = float(len(turn_rows))
        bias -= lr * (grad_b / n)
        for name in FEATURE_NAMES:
            weights[name] -= lr * ((grad_w[name] / n) + l2 * weights[name])
    return {
        "feature_names": FEATURE_NAMES,
        "means": means,
        "scales": scales,
        "weights": weights,
        "bias": bias,
        "train_rows": len(turn_rows),
    }


def predict_win_probability(row: dict, model: dict) -> float:
    z = float(model.get("bias", 0.0))
    means = model.get("means", {})
    scales = model.get("scales", {})
    weights = model.get("weights", {})
    for name in model.get("feature_names", FEATURE_NAMES):
        scale = float(scales.get(name, 1.0) or 1.0)
        z += float(weights.get(name, 0.0)) * ((float(row.get(name, 0.0)) - float(means.get(name, 0.0))) / scale)
    return 1.0 / (1.0 + math.exp(-max(min(z, 30.0), -30.0)))


def annotate_rows_with_probability(turn_rows: list[dict], model: dict) -> list[dict]:
    annotated = []
    for row in turn_rows:
        enriched = dict(row)
        enriched["predicted_win_prob"] = predict_win_probability(row, model)
        annotated.append(enriched)
    return annotated


def compute_pivotal_turns(turn_rows: list[dict]) -> list[dict]:
    by_game_player: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in turn_rows:
        by_game_player[(int(row["game_id"]), int(row["player_id"]))].append(row)
    pivotal: list[dict] = []
    for (game_id, player_id), rows in by_game_player.items():
        rows = sorted(rows, key=lambda r: r["turn_index_global"])
        previous = None
        best = None
        for row in rows:
            current = float(row.get("predicted_win_prob", 0.0))
            delta = current - (previous if previous is not None else 0.0)
            if best is None or delta > best["prob_delta"]:
                best = {
                    "game_id": game_id,
                    "player_id": player_id,
                    "character": row.get("character", ""),
                    "won": int(row.get("won", 0)),
                    "turn_index_global": int(row["turn_index_global"]),
                    "turns_to_end": int(row["turns_to_end"]),
                    "predicted_win_prob": current,
                    "prob_delta": delta,
                    "landing_purchase": int(row.get("landing_purchase", 0)),
                    "landing_takeover": int(row.get("landing_takeover", 0)),
                    "landing_rent": int(row.get("landing_rent", 0)),
                    "used_trick": int(row.get("used_trick", 0)),
                    "lap_reward_count": int(row.get("lap_reward_count", 0)),
                }
            previous = current
        if best is not None:
            pivotal.append(best)
    pivotal.sort(key=lambda r: (r["won"], r["prob_delta"]), reverse=True)
    return pivotal


def write_json(path: str | Path, payload: dict | list) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: str | Path, rows: list[dict]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def analyze_games_jsonl(games_jsonl: str | Path, output_dir: str | Path) -> dict:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    games = load_games_jsonl(games_jsonl)
    turn_rows = extract_turn_feature_rows(games)
    model = train_logistic_model(turn_rows)
    annotated_rows = annotate_rows_with_probability(turn_rows, model)
    pivotal = compute_pivotal_turns(annotated_rows)
    summary = build_summary(games, annotated_rows)
    importance = sorted(
        ({"feature": name, "abs_weight": abs(float(model["weights"][name])), "weight": float(model["weights"][name])} for name in FEATURE_NAMES),
        key=lambda x: x["abs_weight"],
        reverse=True,
    )
    write_json(out_dir / "summary.json", summary)
    write_json(out_dir / "win_model.json", model)
    write_json(out_dir / "feature_importance.json", importance)
    write_json(out_dir / "pivotal_turns.json", pivotal[:200])
    write_jsonl(out_dir / "turn_features.jsonl", annotated_rows)
    write_csv(out_dir / "turn_features.csv", annotated_rows)
    return {
        "summary": summary,
        "win_model": model,
        "feature_importance": importance[:20],
        "pivotal_turns": pivotal[:20],
    }


def run_pipeline(simulations: int, seed: int, output_dir: str | Path, policy_mode: str = "arena") -> dict:
    out_dir = Path(output_dir)
    sim_dir = out_dir / "simulation"
    analysis_dir = out_dir / "analysis"
    simulate_run(
        simulations=simulations,
        seed=seed,
        output_dir=str(sim_dir),
        log_level="full",
        policy_mode=policy_mode,
        emit_summary=False,
    )
    return analyze_games_jsonl(sim_dir / "games.jsonl", analysis_dir)


def main() -> None:
    configure_utf8_io()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_analyze = sub.add_parser("analyze")
    ap_analyze.add_argument("--games-jsonl", required=True)
    ap_analyze.add_argument("--output-dir", required=True)

    ap_pipeline = sub.add_parser("pipeline")
    ap_pipeline.add_argument("--simulations", type=int, required=True)
    ap_pipeline.add_argument("--seed", type=int, default=42)
    ap_pipeline.add_argument("--output-dir", required=True)
    ap_pipeline.add_argument("--policy-mode", type=str, default="arena")

    args = ap.parse_args()
    if args.cmd == "analyze":
        payload = analyze_games_jsonl(args.games_jsonl, args.output_dir)
    else:
        payload = run_pipeline(args.simulations, args.seed, args.output_dir, policy_mode=args.policy_mode)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
