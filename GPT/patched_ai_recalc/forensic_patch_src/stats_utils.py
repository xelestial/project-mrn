from __future__ import annotations

from collections import Counter

PLAYER_KEYS = ["score", "tiles", "placed", "hand", "cash", "shards", "laps_completed", "lap_rewards_received"]
STRATEGY_KEYS = [
    "purchases","purchase_t2","purchase_t3","rent_paid","own_tile_visits","f1_visits","f2_visits","s_visits","s_triggers","malicious_visits","cards_used","card_turns","single_card_turns","pair_card_turns","tricks_used","anytime_tricks_used","regular_tricks_used","lap_cash_choices","lap_coin_choices","coins_gained_own_tile","coins_placed","lap_shard_choices","shards_gained_f","shards_gained_lap","shard_income_cash","mark_attempts","mark_successes","mark_fail_no_target","mark_fail_missing","mark_fail_blocked","mark_success_rate"
]


def _safe_number(value):
    return value if isinstance(value, (int, float)) and value is not None else 0


def _avg(rows, key):
    return sum(_safe_number(r.get(key, 0)) for r in rows) / len(rows) if rows else 0.0


def _first_nonempty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def compute_basic_stats_from_games(games):
    winner_rows = []
    non_rows = []
    winner_strategy = []
    non_strategy = []
    games_count = 0
    character_counts = Counter()
    final_character_counts = Counter()
    winner_character_counts = Counter()
    missing_character_summary_rows = 0
    missing_strategy_character_rows = 0
    null_numeric_fields = Counter()
    first_scores = []
    second_scores = []
    first_place_laps_completed = []
    second_place_laps_completed = []
    first_place_lap_rewards = []
    second_place_lap_rewards = []
    total_mark_attempts = 0
    total_mark_successes = 0

    for g in games:
        games_count += 1
        winners = set(g.get("winner_ids", []))
        player_summary = list(g.get("player_summary", []))
        if player_summary:
            ordered = sorted(player_summary, key=lambda p: (_safe_number(p.get("score", 0)), _safe_number(p.get("cash", 0)), _safe_number(p.get("tiles_owned", 0))), reverse=True)
            first_scores.append(_safe_number(ordered[0].get("score", 0)))
            first_place_laps_completed.append(_safe_number(ordered[0].get("laps_completed", 0)))
            first_place_lap_rewards.append(_safe_number(ordered[0].get("lap_rewards_received", 0)))
            if len(ordered) > 1:
                second_scores.append(_safe_number(ordered[1].get("score", 0)))
                second_place_laps_completed.append(_safe_number(ordered[1].get("laps_completed", 0)))
                second_place_lap_rewards.append(_safe_number(ordered[1].get("lap_rewards_received", 0)))
        strategy_by_pid = {s["player_id"]: s for s in g.get("strategy_summary", [])}
        for strat in g.get("strategy_summary", []):
            counts = strat.get("character_choice_counts") or {}
            if counts:
                character_counts.update(counts)
            else:
                strategy_character = _first_nonempty(strat.get("last_selected_character"), strat.get("character"))
                if strategy_character:
                    character_counts[strategy_character] += 1
                else:
                    missing_strategy_character_rows += 1
        for p in player_summary:
            s = strategy_by_pid.get(p["player_id"])
            player_character = _first_nonempty(
                p.get("character", ""),
                (s or {}).get("last_selected_character", "") if s is not None else "",
                (s or {}).get("character", "") if s is not None else "",
            )
            if player_character:
                final_character_counts[player_character] += 1
                if (p["player_id"] + 1) in winners:
                    winner_character_counts[player_character] += 1
            else:
                missing_character_summary_rows += 1
            row = {
                "score": _safe_number(p.get("score", 0)),
                "tiles": _safe_number(p.get("tiles_owned", 0)),
                "placed": _safe_number(p.get("placed_score_coins", 0)),
                "hand": _safe_number(p.get("hand_coins", 0)),
                "cash": _safe_number(p.get("cash", 0)),
                "shards": _safe_number(p.get("shards", 0)),
                "laps_completed": _safe_number(p.get("laps_completed", 0)),
                "lap_rewards_received": _safe_number(p.get("lap_rewards_received", 0)),
                "character": player_character,
            }
            field_map = {
                "score": "score",
                "tiles": "tiles_owned",
                "placed": "placed_score_coins",
                "hand": "hand_coins",
                "cash": "cash",
                "shards": "shards",
                "laps_completed": "laps_completed",
                "lap_rewards_received": "lap_rewards_received",
            }
            for key, source_key in field_map.items():
                if p.get(source_key, 0) is None:
                    null_numeric_fields[key] += 1
            target = winner_rows if (p["player_id"] + 1) in winners else non_rows
            target.append(row)
            if s is not None:
                total_mark_attempts += _safe_number(s.get("mark_attempts", 0))
                total_mark_successes += _safe_number(s.get("mark_successes", 0))
                normalized_strategy = {}
                for k in STRATEGY_KEYS:
                    normalized_strategy[k] = _safe_number(s.get(k, 0))
                normalized_strategy["character"] = _first_nonempty(s.get("character", ""), s.get("last_selected_character", ""))
                starget = winner_strategy if (p["player_id"] + 1) in winners else non_strategy
                starget.append(normalized_strategy)
    return {
        "games": games_count,
        "player_samples": games_count * 4,
        "winner_avg": {k: _avg(winner_rows, k) for k in PLAYER_KEYS},
        "non_winner_avg": {k: _avg(non_rows, k) for k in PLAYER_KEYS},
        "winner_strategy_avg": {k: _avg(winner_strategy, k) for k in STRATEGY_KEYS},
        "non_winner_strategy_avg": {k: _avg(non_strategy, k) for k in STRATEGY_KEYS},
        "character_pick_counts": dict(character_counts),
        "final_character_counts": dict(final_character_counts),
        "winner_character_counts": dict(winner_character_counts),
        "reliability": {
            "missing_character_summary_rows": missing_character_summary_rows,
            "missing_strategy_character_rows": missing_strategy_character_rows,
            "null_numeric_fields": dict(null_numeric_fields),
        },
        "first_place_score_avg": sum(first_scores) / len(first_scores) if first_scores else 0.0,
        "second_place_score_avg": sum(second_scores) / len(second_scores) if second_scores else 0.0,
        "first_place_laps_completed_avg": sum(first_place_laps_completed) / len(first_place_laps_completed) if first_place_laps_completed else 0.0,
        "second_place_laps_completed_avg": sum(second_place_laps_completed) / len(second_place_laps_completed) if second_place_laps_completed else 0.0,
        "first_place_lap_reward_avg": sum(first_place_lap_rewards) / len(first_place_lap_rewards) if first_place_lap_rewards else 0.0,
        "second_place_lap_reward_avg": sum(second_place_lap_rewards) / len(second_place_lap_rewards) if second_place_lap_rewards else 0.0,
        "total_mark_attempts": total_mark_attempts,
        "total_mark_successes": total_mark_successes,
        "mark_success_rate": (total_mark_successes / total_mark_attempts) if total_mark_attempts else 0.0,
    }
