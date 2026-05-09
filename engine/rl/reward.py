from __future__ import annotations

from rl.types import RewardBreakdown


def _numeric_delta(event: dict, before_key: str, after_key: str) -> float:
    before = event.get(before_key)
    after = event.get(after_key)
    if before is None or after is None:
        return 0.0
    return float(after) - float(before)


def compute_reward_from_event(event: dict | None) -> RewardBreakdown:
    if not isinstance(event, dict):
        return RewardBreakdown(total=0.0, components={"cash_delta": 0.0})

    cash_delta = _numeric_delta(event, "cash_before", "cash_after")
    shard_delta = _numeric_delta(event, "shards_before", "shards_after")
    score_delta = _numeric_delta(event, "score_before", "score_after")
    end_time_delta = _numeric_delta(event, "f_value_before", "f_value_after")
    placed_delta = _numeric_delta(event, "placed_score_coins_before", "placed_score_coins_after")
    tile_delta = _numeric_delta(event, "tiles_owned_before", "tiles_owned_after")
    cash_after = event.get("cash_after")
    components = {
        "cash_delta": cash_delta,
        "shard_delta": shard_delta,
        "score_delta": score_delta,
        "end_time_delta": end_time_delta,
        "placed_score_delta": placed_delta,
        "tile_delta": tile_delta,
    }
    landing = event.get("landing") if isinstance(event.get("landing"), dict) else {}
    landing_type = str(landing.get("type") or "").upper()
    event_name = str(event.get("event") or "")

    if "RENT" in landing_type and cash_delta < 0:
        components["rent_loss"] = cash_delta
    if event_name == "lap_reward_chosen" and cash_delta > 0:
        components["lap_cash_gain"] = cash_delta
    if "PURCHASE" in landing_type and cash_delta < 0:
        components["purchase_spend"] = cash_delta
    if cash_after is not None:
        cash_after_float = float(cash_after)
        if cash_after_float <= 0:
            components["cash_death_risk"] = -2.0
        elif cash_after_float < 5:
            components["low_cash_risk"] = -(5.0 - cash_after_float) / 5.0
    if event.get("bankrupt") or event.get("bankruptcy_info") or event_name == "bankruptcy":
        components["bankruptcy"] = -4.0

    total_raw = (
        (cash_delta / 5.0)
        + (shard_delta * 0.4)
        + (score_delta * 0.6)
        + (placed_delta * 0.8)
        + (tile_delta * 0.25)
        - (end_time_delta * 0.2)
        + sum(float(components.get(key, 0.0) or 0.0) for key in ("low_cash_risk", "cash_death_risk", "bankruptcy"))
    )
    total = max(min(total_raw, 3.0), -4.0)
    return RewardBreakdown(total=total, components=components)
