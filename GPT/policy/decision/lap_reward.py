from __future__ import annotations

from dataclasses import dataclass

from policy.context.turn_plan import TurnPlanContext


def apply_turn_plan_lap_bias(
    cash_score: float,
    shard_score: float,
    coin_score: float,
    *,
    plan_ctx: TurnPlanContext,
    cross_start: float,
    is_lap_engine_character: bool,
) -> tuple[float, float, float, str | None]:
    preferred_override: str | None = None
    if plan_ctx.resource_intent == "shard_checkpoint":
        shard_score += 1.15
        coin_score -= 0.35
        if plan_ctx.shards < 5:
            preferred_override = "shards"
    elif plan_ctx.resource_intent == "cash_first":
        cash_score += 0.55
        if plan_ctx.cleanup_stage in {"critical", "meltdown"}:
            preferred_override = "cash"
    elif plan_ctx.resource_intent == "card_preserve" and plan_ctx.plan_key == "lap_engine" and is_lap_engine_character:
        coin_score += 0.35 + 0.25 * cross_start

    if plan_ctx.plan_key == "survival_recovery" and plan_ctx.cleanup_stage in {"critical", "meltdown"}:
        cash_score += 0.35
        preferred_override = preferred_override or "cash"
    elif plan_ctx.plan_key == "controller_disrupt" and plan_ctx.cleanup_stage in {"stable", "strained"}:
        shard_score += 0.20

    return cash_score, shard_score, coin_score, preferred_override


def resolve_lap_reward_bundle(
    *,
    cash_pool: int,
    shards_pool: int,
    coins_pool: int,
    points_budget: int,
    cash_point_cost: int,
    shards_point_cost: int,
    coins_point_cost: int,
    cash_unit_score: float,
    shard_unit_score: float,
    coin_unit_score: float,
    preferred: str | None = None,
) -> tuple[str, int, int, int]:
    best: tuple[float, int, int, int, str] | None = None
    preferred_bonus = {preferred: 0.08} if preferred else {}
    for cash_units in range(0, min(cash_pool, points_budget // max(1, cash_point_cost)) + 1):
        cash_points = cash_units * cash_point_cost
        if cash_points > points_budget:
            break
        shard_cap = min(shards_pool, (points_budget - cash_points) // max(1, shards_point_cost))
        for shard_units in range(0, shard_cap + 1):
            spent = cash_points + shard_units * shards_point_cost
            coin_cap = min(coins_pool, (points_budget - spent) // max(1, coins_point_cost))
            for coin_units in range(0, coin_cap + 1):
                total_spent = spent + coin_units * coins_point_cost
                if total_spent <= 0 or total_spent > points_budget:
                    continue
                utility = (
                    cash_units * cash_unit_score
                    + shard_units * shard_unit_score
                    + coin_units * coin_unit_score
                    + 0.02 * total_spent
                )
                if preferred:
                    dominant = max(
                        ((cash_units, "cash"), (shard_units, "shards"), (coin_units, "coins")),
                        key=lambda item: (item[0], preferred_bonus.get(item[1], 0.0)),
                    )[1]
                    utility += preferred_bonus.get(dominant, 0.0)
                candidate = (utility, cash_units, shard_units, coin_units, preferred or "mixed")
                if best is None or candidate > best:
                    best = candidate

    if best is None:
        return ("blocked", 0, 0, 0)

    _, cash_units, shard_units, coin_units, _ = best
    components = [(cash_units, "cash"), (shard_units, "shards"), (coin_units, "coins")]
    choice = max(components, key=lambda item: item[0])[1] if sum(v for v, _ in components) > 0 else "blocked"
    if preferred == "cash" and cash_units > 0:
        choice = "cash"
    elif preferred == "shards" and shard_units > 0:
        choice = "shards"
    elif preferred == "coins" and coin_units > 0:
        choice = "coins"
    return (choice, cash_units, shard_units, coin_units)


@dataclass(frozen=True, slots=True)
class V3LapRewardInputs:
    current_character: str | None
    cash: int
    shards: int
    hand_coins: int
    placeable: bool
    buy_value: float
    cross_start: float
    land_f: float
    land_f_value: float
    own_land: float
    token_window_score: float
    token_window_nearest_distance: float
    token_window_revisit_prob: float
    cleanup_pressure: float
    next_negative_cleanup_prob: float
    two_negative_cleanup_prob: float
    expected_cleanup_cost: float
    survival_cash_pressure: bool
    burden_count: float
    lap_cash_preference: float
    lap_shard_preference: float
    cleanup_growth_locked: bool
    cleanup_stage: str
    cleanup_stage_score: float
    is_leader: bool
    rich_pool: float
    is_baksu: bool
    is_mansin: bool
    is_shard_hunter: bool
    is_controller: bool
    is_gakju: bool


@dataclass(frozen=True, slots=True)
class BasicLapRewardInputs:
    current_character: str | None
    cash: int
    shards: int
    placeable: bool
    survival_cash_pressure: bool
    is_shard_hunter: bool


@dataclass(frozen=True, slots=True)
class V2ProfileLapRewardInputs:
    profile: str
    cash: int
    shards: int
    hand_coins: int
    placeable: bool
    buy_value: float
    land_f: float
    land_f_value: float
    own_land: float
    token_combo: float
    token_window_score: float
    token_window_placeable_count: float
    token_window_nearest_distance: float
    token_window_revisit_prob: float
    emergency: float = 0.0
    finisher_window: float = 0.0
    low_cash: float = 0.0
    cash_after_reserve: float = 0.0
    rent_pressure: float = 0.0
    burden_count: float = 0.0
    cleanup_pressure: float = 0.0
    solo_leader: bool = False
    near_end: bool = False
    is_controller_role: bool = False


def apply_v2_profile_lap_reward_bias(
    cash_score: float,
    shard_score: float,
    coin_score: float,
    *,
    inputs: V2ProfileLapRewardInputs,
) -> tuple[float, float, float, str | None]:
    preferred_override: str | None = None
    if inputs.profile == "control":
        shard_score += 1.1 + 0.55 * inputs.emergency
        cash_score += 0.1
        if inputs.solo_leader:
            shard_score += 0.45
        if inputs.near_end:
            shard_score += 0.55
        if inputs.is_controller_role:
            shard_score += 0.4
        if inputs.placeable:
            coin_score += 0.45
        if inputs.finisher_window > 0.0 and inputs.placeable and inputs.cash_after_reserve >= 0.5:
            coin_score += 1.85 + 0.55 * inputs.finisher_window
            cash_score += 0.25 * inputs.finisher_window
            preferred_override = "coins"
        if inputs.finisher_window > 0.0 and inputs.buy_value > 0.0 and inputs.cash_after_reserve >= 0.0:
            cash_score += 0.35 + 0.15 * inputs.finisher_window
        if inputs.low_cash > 0.0:
            cash_score += 0.55 * inputs.low_cash
        if inputs.cash_after_reserve <= 0.0:
            cash_score += 0.9 + 0.2 * max(0.0, -inputs.cash_after_reserve)
        if inputs.rent_pressure >= 1.7:
            cash_score += 0.45 + 0.18 * inputs.rent_pressure
        if inputs.burden_count >= 1.0 and inputs.cleanup_pressure >= 2.2:
            cash_score += 0.5 + 0.18 * inputs.burden_count + 0.08 * max(0.0, inputs.cleanup_pressure - 2.2)
        if inputs.cash <= 3:
            cash_score += 2.0
        elif inputs.cash <= 5 and inputs.cash_after_reserve <= -0.5 and inputs.emergency < 3.0:
            cash_score += 1.5
        elif inputs.cash <= 6 and inputs.rent_pressure >= 2.0 and inputs.emergency < 2.6:
            cash_score += 1.25
    elif inputs.profile == "growth":
        shard_score += 0.4
        coin_score += 0.8
    elif inputs.profile == "avoid_control":
        cash_score += 0.8
    elif inputs.profile == "aggressive":
        coin_score += 1.8
        cash_score -= 0.2
    elif inputs.profile == "token_opt":
        coin_score += 1.8 + 2.1 * inputs.own_land + 0.9 * inputs.token_combo + 0.75 * inputs.token_window_score
        if inputs.token_window_placeable_count <= 0.0:
            coin_score -= 2.1
            cash_score += 0.55
        if inputs.token_window_nearest_distance <= 4.0:
            coin_score += 0.9
        if inputs.token_window_revisit_prob >= 0.28:
            coin_score += 0.8
        if inputs.hand_coins >= 3 and inputs.token_window_revisit_prob < 0.12:
            cash_score += 0.9
        shard_score += max(0.0, 0.20 * inputs.land_f * inputs.land_f_value)
        cash_score -= 0.2
    return cash_score, shard_score, coin_score, preferred_override


def evaluate_basic_lap_reward(
    inputs: BasicLapRewardInputs,
    *,
    balanced: bool,
) -> tuple[float, float, float, str]:
    if inputs.survival_cash_pressure:
        return (1.0, 0.2, 0.1, "cash")
    if balanced:
        if inputs.placeable:
            return (0.2, 0.1, 1.0, "coins")
        if inputs.cash < 8:
            return (1.0, 0.2, 0.1, "cash")
        if inputs.is_shard_hunter or inputs.shards < 4:
            return (0.2, 1.0, 0.1, "shards")
        return (1.0, 0.2, 0.1, "cash")

    if inputs.cash < 8:
        return (1.0, 0.2, 0.1, "cash")
    if inputs.is_shard_hunter:
        return (0.2, 1.0, 0.1, "shards")
    if inputs.placeable:
        return (0.2, 0.1, 1.0, "coins")
    return (1.0, 0.2, 0.1, "cash")


def evaluate_v3_lap_reward(
    inputs: V3LapRewardInputs,
    *,
    plan_ctx: TurnPlanContext | None = None,
) -> tuple[float, float, float, str]:
    current_char = inputs.current_character
    negative_risk = max(inputs.next_negative_cleanup_prob, inputs.two_negative_cleanup_prob)
    shard_checkpoint_need = min(max(0, 5 - inputs.shards), 2) + 0.8 * min(max(0, 7 - inputs.shards), 2)
    distress_level = (
        max(0.0, 10.0 - inputs.cash) / 4.0
        + 0.75 * max(0.0, inputs.cleanup_pressure - 1.5)
        + 1.20 * max(0.0, negative_risk - 0.15)
    )

    cash_score = 1.2 + 0.4 * max(0, 10 - inputs.cash)
    cash_score += 0.52 * max(0.0, 12.0 - inputs.cash) + 0.28 * inputs.expected_cleanup_cost + 0.16 * distress_level

    shard_score = 0.8 + 0.68 + 0.38 * shard_checkpoint_need + max(0.0, 0.16 * inputs.land_f * inputs.land_f_value)
    if not (inputs.is_baksu or inputs.is_mansin or inputs.is_shard_hunter) and inputs.shards >= 5:
        shard_score -= 0.65 + 0.12 * max(0, inputs.shards - 5)

    coin_score = 1.55 + 1.55 * inputs.own_land + 0.95 * inputs.token_window_score
    if inputs.token_window_nearest_distance <= 4.0:
        coin_score += 0.62
    if inputs.token_window_revisit_prob >= 0.25:
        coin_score += 0.78
    if inputs.placeable:
        coin_score += 0.55

    cash_score += inputs.lap_cash_preference
    shard_score += inputs.lap_shard_preference
    if inputs.cleanup_growth_locked:
        coin_score -= 0.55 + 0.22 * inputs.cleanup_stage_score
    if inputs.burden_count >= 1.0 and inputs.shards < 7:
        shard_score += 0.30 + 0.18 * inputs.burden_count

    preferred_override: str | None = None

    if inputs.cleanup_pressure >= 1.8 or negative_risk >= 0.18 or inputs.survival_cash_pressure:
        cash_score += 0.92 + 0.24 * inputs.cleanup_pressure + 0.30 * max(0.0, negative_risk - 0.18)
        shard_score += 0.28 * shard_checkpoint_need
        coin_score -= 0.45 + 0.10 * inputs.cleanup_pressure
    elif inputs.placeable or inputs.own_land >= 0.12 or inputs.token_window_score >= 0.80:
        cash_score -= 0.40
        coin_score += 2.75 + 0.82 * inputs.token_window_score + 0.62 * inputs.own_land
        if (
            not inputs.cleanup_growth_locked
            and (
                not (inputs.is_baksu or inputs.is_mansin)
                or (inputs.is_baksu and inputs.shards >= 5)
                or (inputs.is_mansin and inputs.shards >= 7)
            )
        ):
            preferred_override = "coins"

    if (
        inputs.cleanup_pressure < 1.20
        and negative_risk < 0.12
        and inputs.cash >= 7
    ):
        cash_score -= 0.55
        if inputs.placeable:
            coin_score += 1.55 + 0.30 * inputs.token_window_score
            if not inputs.cleanup_growth_locked:
                preferred_override = preferred_override or "coins"
        elif inputs.buy_value >= 1.0:
            coin_score += 0.70

    if inputs.is_baksu:
        if inputs.shards < 5:
            shard_score += 3.10 + 0.35 * max(0, 5 - inputs.shards)
            preferred_override = "shards"
        elif inputs.shards < 7:
            shard_score += 1.35 + 0.18 * max(0, 7 - inputs.shards)
            coin_score += 0.22
        else:
            cash_score += 0.20
            coin_score += 0.46
    elif inputs.is_mansin:
        if inputs.shards < 7:
            shard_score += 1.35 + 0.15 * max(0, 7 - inputs.shards)
        else:
            cash_score += 0.18
            coin_score += 0.28

    if inputs.is_controller and inputs.cleanup_stage_score >= 1.0:
        cash_score += 0.22 * inputs.cleanup_stage_score
        if inputs.shards < 7:
            shard_score += 0.18 * inputs.cleanup_stage_score

    if (
        inputs.shards >= 7
        and inputs.token_window_score >= 1.10
        and inputs.hand_coins > 0
        and not inputs.survival_cash_pressure
        and negative_risk < 0.22
    ):
        coin_score += 0.85

    if inputs.shards >= 10 and inputs.cleanup_stage in {"stable", "strained"}:
        cash_score -= 0.20
        shard_score -= 0.55
        coin_score += 0.72

    if inputs.is_gakju and inputs.cross_start > 0.25:
        cash_score += 0.35
        coin_score += 0.35
    if inputs.is_gakju and inputs.cross_start > 0.28 and inputs.rich_pool > 0.0 and not inputs.survival_cash_pressure:
        coin_score += 0.75
        cash_score += 0.25

    if plan_ctx is not None:
        cash_score, shard_score, coin_score, bias_override = apply_turn_plan_lap_bias(
            cash_score,
            shard_score,
            coin_score,
            plan_ctx=plan_ctx,
            cross_start=inputs.cross_start,
            is_lap_engine_character=inputs.is_gakju,
        )
        preferred_override = preferred_override or bias_override

    preferred = preferred_override or max(
        [("cash", cash_score), ("shards", shard_score), ("coins", coin_score)],
        key=lambda item: item[1],
    )[0]
    return cash_score, shard_score, coin_score, preferred


def normalize_lap_reward_scores(
    *,
    cash_score: float,
    shard_score: float,
    coin_score: float,
    lap_reward_cash: float,
    lap_reward_shards: float,
    lap_reward_coins: float,
    preferred_override: str | None = None,
) -> tuple[float, float, float, str]:
    preferred = preferred_override or max(
        [("cash", cash_score), ("shards", shard_score), ("coins", coin_score)],
        key=lambda item: item[1],
    )[0]
    cash_unit = cash_score / max(1.0, float(lap_reward_cash))
    shard_unit = shard_score / max(1.0, float(lap_reward_shards))
    coin_unit = coin_score / max(1.0, float(lap_reward_coins))
    return cash_unit, shard_unit, coin_unit, preferred
