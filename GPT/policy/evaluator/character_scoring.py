from __future__ import annotations

from dataclasses import dataclass

from characters import CARD_TO_NAMES


MATCHMAKER = CARD_TO_NAMES[7][1]
BUILDER = CARD_TO_NAMES[8][0]
SWINDLER = CARD_TO_NAMES[8][1]
INNKEEPER = CARD_TO_NAMES[7][0]
RUNNER = CARD_TO_NAMES[4][0]
CLERK = CARD_TO_NAMES[4][1]
ESCAPE_SLAVE = CARD_TO_NAMES[3][1]
BANDIT = CARD_TO_NAMES[2][1]
ASSASSIN = CARD_TO_NAMES[2][0]
TRACKER = CARD_TO_NAMES[3][0]
SHAKEDOWN_MARKER = CARD_TO_NAMES[6][0]
PUBLIC_CLEANER = CARD_TO_NAMES[6][1]
EOSA = CARD_TO_NAMES[1][0]
TAMGWANORI = CARD_TO_NAMES[1][1]
DOCTRINE_RESEARCHER = CARD_TO_NAMES[5][0]
DOCTRINE_MANAGER = CARD_TO_NAMES[5][1]

LOW_CASH_ECONOMY = {INNKEEPER, CLERK, SHAKEDOWN_MARKER, PUBLIC_CLEANER}
VERY_LOW_CASH_RECOVERY = {INNKEEPER, CLERK}
TAKEOVER_DISRUPTORS = {SWINDLER, BANDIT, ASSASSIN, TRACKER}
MONOPOLY_ROUTE_CHARACTERS = {INNKEEPER, RUNNER, ESCAPE_SLAVE}
SHARD_SYNERGY_CHARACTERS = {BANDIT, CLERK}
DOCTRINE_CONTROLLERS = {DOCTRINE_RESEARCHER, DOCTRINE_MANAGER}


@dataclass(frozen=True, slots=True)
class V1CharacterStructuralInputs:
    low_cash: bool
    very_low_cash: bool
    shards: int
    near_unowned: int
    enemy_tiles: int
    own_near_complete: float
    own_claimable_blocks: float
    enemy_near_complete: float
    contested_blocks: float
    matchmaker_adjacent_value: float
    builder_free_purchase_value: float
    scammer_coin_value: float
    scammer_best_tile_coins: float
    scammer_blocks_enemy_monopoly: float
    scammer_finishes_own_monopoly: float
    max_enemy_stack: float
    max_enemy_owned_stack: float
    mobility_leverage: float
    own_tile_income: float = 0.0
    lap_fast_window: float = 0.0
    lap_mobility: float = 0.0
    lap_rich_pool: float = 0.0
    lap_double_lap_threat: float = 0.0
    own_burden: float = 0.0
    cleanup_pressure: float = 0.0
    legal_visible_burden_total: float = 0.0
    legal_visible_burden_peak: float = 0.0
    legal_low_cash_targets: float = 0.0
    has_mark_targets: bool = False
    failed_mark_removed_small: float = 0.0
    failed_mark_removed_large: float = 0.0
    failed_mark_payout_small: float = 0.0
    failed_mark_payout_large: float = 0.0
    reachable_specials_with_one_short: int = 0
    marker_owner_is_self: bool = True
    uroe_blocked: bool = False


@dataclass(frozen=True, slots=True)
class V2ExpansionInputs:
    buy_value: float
    cleanup_pressure: float
    cash_after_reserve: float
    near_unowned: float
    shards: int
    enemy_tiles: int
    leader_pressure: float
    top_threat_tiles_owned: int
    top_threat_is_expansion: bool
    top_threat_present: bool
    land_f: float
    exclusive_blocks: int
    scammer_coin_value: float
    scammer_best_tile_coins: float
    matchmaker_adjacent_value: float
    builder_free_purchase_value: float
    combo_has_expansion_trick: bool
    combo_has_arrival_takeover_trick: bool


@dataclass(frozen=True, slots=True)
class V2RouteInputs:
    cash: int
    placeable: bool
    own_near_complete: float
    own_claimable_blocks: float
    enemy_near_complete: float
    contested_blocks: float
    deny_now: float
    matchmaker_adjacent_value: float
    builder_free_purchase_value: float


@dataclass(frozen=True, slots=True)
class V2ProfileInputs:
    profile: str
    leading: bool
    has_marks: bool
    leader_emergency: float
    leader_is_solo: bool
    leader_near_end: bool
    top_threat_present: bool
    top_threat_tiles_owned: int
    top_threat_cash: int
    leader_pressure: float
    buy_value: float
    finisher_window: float
    finisher_reason: str
    cross_start: float
    land_f: float
    land_f_value: float
    own_land: float
    token_combo: float
    placeable: bool
    matchmaker_adjacent_value: float
    builder_free_purchase_value: float


@dataclass(frozen=True, slots=True)
class V3CharacterInputs:
    shards: int
    burden_count: float
    cleanup_pressure: float
    reserve_gap: float
    money_distress: float
    distress_level: float
    cross_start: float
    land_f: float
    land_f_value: float
    own_land: float
    token_combo: float
    token_window: float
    buy_value: float
    legal_visible_burden_total: float
    top_threat_cash: int
    stack_max_enemy: float
    stack_max_enemy_owned: float
    mobility_leverage: float
    lap_fast_window: float
    lap_rich_pool: float
    lap_double_lap_threat: float
    placeable: bool


@dataclass(frozen=True, slots=True)
class V2TacticalInputs:
    profile: str
    buy_value: float
    cross_start: float
    land_f: float
    land_f_value: float
    player_shards: int
    burden_count: float
    cleanup_pressure: float
    legal_visible_burden_total: float
    legal_visible_burden_peak: float
    legal_low_cash_targets: float
    has_marks: bool
    leader_pressure: float
    top_threat_present: bool
    top_threat_tiles_owned: int
    top_threat_cash: int
    top_threat_cross: float
    top_threat_land_f: float
    top_threat_is_expansion_geo_combo: bool
    top_threat_is_burden: bool
    top_threat_is_shard_attack_counter_target: bool
    land_race_pressure: float
    premium_unowned: float
    near_unowned: float
    behind_tiles: float
    early_round: float
    visited_owned_tile_count: int
    lap_fast_window: float
    lap_rich_pool: float
    lap_double_lap_threat: float
    mobility_leverage: float
    max_enemy_stack: float
    max_enemy_owned_stack: float
    reachable_specials_with_one_short: int
    combo_has_speed_tricks: bool
    combo_has_lap_combo_tricks: bool
    combo_has_relic_collector: bool
    cleanup_growth_locked: bool
    cleanup_stage_score: float
    cleanup_controller_bias: float
    marker_plan_best_score: float
    own_burden_cost: float


@dataclass(frozen=True, slots=True)
class V2EmergencyRiskInputs:
    profile: str
    leader_emergency: float
    leader_is_solo: bool
    leader_near_end: bool
    reserve_gap: float
    expected_loss: float
    worst_loss: float
    own_burden_cost: float
    player_shards: int


@dataclass(frozen=True, slots=True)
class V2PostRiskInputs:
    has_uhsa_alive: bool
    is_muroe: bool
    reserve_gap: float


@dataclass(frozen=True, slots=True)
class V2TailThreatInputs:
    mark_risk: float


@dataclass(frozen=True, slots=True)
class V2RentTailInputs:
    rent_pressure: float
    rent_economy: float
    rent_combo: float
    rent_survival: float


@dataclass(frozen=True, slots=True)
class V2UhsaTailInputs:
    blocked: bool


def evaluate_v1_character_structural_rules(
    character_name: str,
    inputs: V1CharacterStructuralInputs,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if inputs.low_cash and character_name in LOW_CASH_ECONOMY:
        score += 1.8
        reasons.append("low_cash_economy")
    if inputs.very_low_cash and character_name in VERY_LOW_CASH_RECOVERY:
        score += 1.4
        reasons.append("very_low_cash_recovery")
    if character_name == BUILDER and inputs.very_low_cash and inputs.shards >= 1:
        score += 1.0
        reasons.append("very_low_cash_free_build")

    if inputs.near_unowned >= 2 and character_name == MATCHMAKER:
        score += 1.10 + inputs.matchmaker_adjacent_value
        reasons.append("near_unowned_expansion")
    elif inputs.near_unowned >= 1 and character_name == MATCHMAKER:
        score += 0.55 + 0.50 * inputs.matchmaker_adjacent_value
        reasons.append("some_expansion_value")

    if inputs.near_unowned >= 2 and character_name == BUILDER:
        score += 0.95 + 0.75 * inputs.builder_free_purchase_value
        reasons.append("near_unowned_expansion")
    elif inputs.near_unowned >= 1 and character_name == BUILDER:
        score += 0.45 + 0.45 * inputs.builder_free_purchase_value
        reasons.append("some_expansion_value")
    elif inputs.near_unowned >= 1 and character_name == SWINDLER:
        score += 0.8
        reasons.append("some_expansion_value")

    if inputs.enemy_tiles >= 4 and character_name in TAKEOVER_DISRUPTORS:
        score += 1.2
        reasons.append("enemy_board_pressure")
    if character_name == SWINDLER and inputs.scammer_coin_value > 0.0:
        score += 1.1 * inputs.scammer_coin_value + 0.35 * inputs.scammer_best_tile_coins
        reasons.append("takeover_coin_swing")
    if character_name == SWINDLER and inputs.scammer_blocks_enemy_monopoly > 0.0:
        score += 1.6 * inputs.scammer_blocks_enemy_monopoly
        reasons.append("blocks_monopoly_with_coin_swing")
    if character_name == SWINDLER and inputs.scammer_finishes_own_monopoly > 0.0:
        score += 1.4 * inputs.scammer_finishes_own_monopoly
        reasons.append("finishes_monopoly_via_takeover")

    if inputs.own_near_complete > 0 and character_name == MATCHMAKER:
        score += 2.05 * inputs.own_near_complete + 0.55 * inputs.own_claimable_blocks + 0.30 * inputs.matchmaker_adjacent_value
        reasons.append("monopoly_finish_value")
    if inputs.own_near_complete > 0 and character_name == BUILDER:
        score += 1.85 * inputs.own_near_complete + 0.40 * inputs.own_claimable_blocks + 0.45 * inputs.builder_free_purchase_value
        reasons.append("monopoly_finish_value")
    elif inputs.own_claimable_blocks > 0 and character_name in MONOPOLY_ROUTE_CHARACTERS:
        score += 0.8 * inputs.own_claimable_blocks
        reasons.append("monopoly_route_value")

    if inputs.enemy_near_complete > 0 and character_name in TAKEOVER_DISRUPTORS:
        score += 1.8 * inputs.enemy_near_complete + 0.35 * inputs.contested_blocks
        reasons.append("deny_enemy_monopoly")
    if inputs.shards >= 4 and character_name in SHARD_SYNERGY_CHARACTERS:
        score += 1.0
        reasons.append("shard_synergy")
    if character_name == CLERK:
        ajeon_burst = 0.55 * inputs.max_enemy_stack + 0.85 * inputs.max_enemy_owned_stack + 0.40 * inputs.mobility_leverage
        if ajeon_burst > 0.0:
            score += ajeon_burst
            reasons.append("stacked_enemy_burst_window")

    if inputs.own_tile_income >= 2 and character_name == INNKEEPER:
        score += 1.2
        reasons.append("own_tile_coin_engine")
    if character_name == INNKEEPER:
        lap_burst = (
            1.15 * inputs.lap_fast_window
            + 0.75 * inputs.lap_mobility
            + 1.25 * inputs.lap_rich_pool
            + 0.55 * inputs.lap_double_lap_threat
        )
        if lap_burst > 0.0:
            score += lap_burst
            reasons.append("lap_engine_window")

    if character_name == SHAKEDOWN_MARKER and inputs.own_burden >= 1:
        score += (
            1.7
            + 1.20 * inputs.own_burden
            + 0.55 * inputs.cleanup_pressure
            + 0.45 * inputs.failed_mark_removed_small
            + 0.10 * inputs.failed_mark_payout_small
        )
        reasons.append("future_burden_escape")
        if inputs.legal_low_cash_targets > 0:
            score += 0.35 * inputs.legal_low_cash_targets
            reasons.append("burden_dump_fragile_target")

    if character_name == PUBLIC_CLEANER and inputs.legal_visible_burden_total > 0:
        score += (
            1.4
            + 1.15 * inputs.legal_visible_burden_total
            + 0.35 * inputs.legal_visible_burden_peak
            + 0.35 * inputs.failed_mark_removed_large
            + 0.08 * inputs.failed_mark_payout_large
        )
        reasons.append("public_burden_cleanup")
        if inputs.legal_low_cash_targets > 0:
            score += 0.35 * inputs.legal_low_cash_targets
            reasons.append("cash_fragile_cleanup")
    elif character_name == PUBLIC_CLEANER and inputs.cleanup_pressure >= 2.5 and inputs.has_mark_targets:
        score += 0.9
        reasons.append("future_fire_insurance")

    if not inputs.has_mark_targets and character_name in {ASSASSIN, BANDIT, TRACKER, SHAKEDOWN_MARKER, PUBLIC_CLEANER}:
        score -= 2.8
        reasons.append("no_mark_targets")
    if inputs.reachable_specials_with_one_short >= 4 and character_name == ESCAPE_SLAVE:
        score += 1.0
        reasons.append("special_tile_reach")
    if not inputs.marker_owner_is_self and character_name in DOCTRINE_CONTROLLERS:
        score += 0.4
        reasons.append("marker_control_value")
    if inputs.uroe_blocked:
        score -= 2.2
        reasons.append("uhsa_blocks_muroe")

    return score, reasons


def evaluate_v2_expansion_rules(
    character_name: str,
    inputs: V2ExpansionInputs,
    *,
    profile: str,
) -> tuple[float, float, float, list[str]]:
    expansion = 0.0
    disruption = 0.0
    combo = 0.0
    reasons: list[str] = []

    if character_name == MATCHMAKER:
        adjacent_value = inputs.matchmaker_adjacent_value
        expansion += 1.15 + 0.75 * inputs.buy_value + adjacent_value
        if profile == "v3_gpt" and inputs.cleanup_pressure < 1.6 and inputs.cash_after_reserve >= 0.0:
            expansion += 0.95 + 0.20 * inputs.near_unowned
            reasons.append("v3_safe_expansion_window")
        if profile == "v3_gpt" and inputs.cleanup_pressure < 1.25 and inputs.cash_after_reserve >= 1.0:
            expansion += 0.70 + 0.18 * max(0.0, inputs.buy_value)
            combo += 0.20 * adjacent_value
            reasons.append("v3_safe_growth_convert")
        if inputs.leader_pressure > 0 and inputs.top_threat_present and inputs.top_threat_is_expansion:
            disruption += 1.0 + 0.35 * inputs.leader_pressure + 0.35 * max(0.0, inputs.buy_value) + 0.20 * adjacent_value
            reasons.append("deny_leader_expansion")
        if inputs.combo_has_expansion_trick:
            combo += 1.6 + 0.35 * adjacent_value
            reasons.append("expansion_trick_combo")
        if inputs.shards <= 0:
            expansion -= 0.55
            reasons.append("matchmaker_adjacent_shard_gate")

    if character_name == BUILDER:
        build_value = inputs.builder_free_purchase_value
        expansion += 1.18 + 0.68 * inputs.buy_value + 0.90 * build_value
        if profile == "v3_gpt" and inputs.cleanup_pressure < 1.6 and inputs.cash_after_reserve >= 0.0:
            expansion += 0.90 + 0.18 * inputs.near_unowned
            reasons.append("v3_safe_expansion_window")
        if profile == "v3_gpt" and inputs.cleanup_pressure < 1.25 and inputs.cash_after_reserve >= 1.0:
            expansion += 0.72 + 0.22 * build_value
            reasons.append("v3_safe_growth_convert")
        if inputs.leader_pressure > 0 and inputs.top_threat_present and inputs.top_threat_is_expansion:
            disruption += 1.0 + 0.35 * inputs.leader_pressure + 0.30 * max(0.0, inputs.buy_value)
            reasons.append("deny_leader_expansion")
        if inputs.combo_has_expansion_trick:
            combo += 1.2 + 0.45 * build_value
            reasons.append("expansion_trick_combo")

    if character_name == SWINDLER:
        expansion += 1.2 + 0.25 * inputs.enemy_tiles
        if profile == "v3_gpt" and inputs.cleanup_pressure < 1.8 and inputs.cash_after_reserve >= -0.5:
            expansion += 0.65
            reasons.append("v3_safe_takeover_window")
        if inputs.leader_pressure > 0 and inputs.top_threat_present and inputs.top_threat_tiles_owned >= 4:
            disruption += 1.0 + 0.35 * inputs.leader_pressure
            reasons.append("deny_leader_takeover_lines")
        if inputs.land_f > 0.15 or inputs.combo_has_arrival_takeover_trick:
            combo += 1.8
            reasons.append("arrival_takeover_combo")
        if inputs.exclusive_blocks >= 2:
            expansion -= 0.9
            reasons.append("monopoly_blocks_takeover")
        if inputs.scammer_coin_value > 0.0:
            expansion += 0.75 * inputs.scammer_coin_value
            disruption += 0.55 * inputs.scammer_coin_value
            reasons.append("takeover_coin_swing")
        if inputs.scammer_best_tile_coins >= 2:
            combo += 0.9 + 0.25 * inputs.scammer_best_tile_coins
            reasons.append("takeover_big_coin_target")

    return expansion, disruption, combo, reasons


def evaluate_v2_route_rules(
    character_name: str,
    inputs: V2RouteInputs,
) -> tuple[float, float, float, float, list[str]]:
    expansion = 0.0
    economy = 0.0
    disruption = 0.0
    survival = 0.0
    reasons: list[str] = []

    if character_name in {INNKEEPER, RUNNER, SWINDLER}:
        economy += 0.15 * inputs.cash
    elif character_name == MATCHMAKER:
        economy += 0.10 * inputs.cash + 0.20 * inputs.matchmaker_adjacent_value
    elif character_name == BUILDER:
        economy += 0.09 * inputs.cash + 0.28 * inputs.builder_free_purchase_value

    if character_name in {INNKEEPER, RUNNER, ESCAPE_SLAVE} and inputs.placeable:
        economy += 0.8
    if character_name == MATCHMAKER and inputs.own_near_complete > 0:
        expansion += 2.25 * inputs.own_near_complete + 0.65 * inputs.own_claimable_blocks + 0.35 * inputs.matchmaker_adjacent_value
        reasons.append("monopoly_finish_value")
    if character_name == BUILDER and inputs.own_near_complete > 0:
        expansion += 2.05 * inputs.own_near_complete + 0.45 * inputs.own_claimable_blocks + 0.45 * inputs.builder_free_purchase_value
        reasons.append("monopoly_finish_value")
    if character_name in {INNKEEPER, RUNNER, ESCAPE_SLAVE} and inputs.own_claimable_blocks > 0:
        economy += 0.65 * inputs.own_claimable_blocks
        reasons.append("monopoly_route_value")
    if character_name == MATCHMAKER and inputs.own_claimable_blocks > 0:
        economy += 0.55 * inputs.own_claimable_blocks + 0.20 * inputs.matchmaker_adjacent_value
        reasons.append("monopoly_route_value")
    if character_name == BUILDER and inputs.own_claimable_blocks > 0:
        economy += 0.45 * inputs.own_claimable_blocks + 0.25 * inputs.builder_free_purchase_value
        reasons.append("monopoly_route_value")
    if character_name == SWINDLER and inputs.enemy_near_complete > 0:
        disruption += 2.2 * inputs.enemy_near_complete + 0.45 * inputs.contested_blocks
        reasons.append("preempt_monopoly_takeover")
    if character_name in {TRACKER, ASSASSIN, BANDIT} and inputs.enemy_near_complete > 0:
        disruption += 1.6 * inputs.enemy_near_complete + 0.35 * inputs.deny_now
        reasons.append("deny_enemy_monopoly")
    if character_name in {RUNNER, ESCAPE_SLAVE} and inputs.deny_now > 0:
        survival += 0.55 * inputs.deny_now
        reasons.append("monopoly_danger_escape")

    return expansion, economy, disruption, survival, reasons


def evaluate_v2_profile_rules(
    character_name: str,
    inputs: V2ProfileInputs,
) -> tuple[float, float, float, float, float, list[str]]:
    expansion = 0.0
    economy = 0.0
    disruption = 0.0
    survival = 0.0
    combo = 0.0
    reasons: list[str] = []

    if inputs.profile == "avoid_control":
        if character_name in {MATCHMAKER, BUILDER, SWINDLER} and (inputs.leading or (inputs.top_threat_present and inputs.has_marks)):
            survival -= 1.4
            reasons.append("avoid_being_targeted")
        if character_name in {INNKEEPER, CLERK, *DOCTRINE_CONTROLLERS}:
            survival += 1.1

    if inputs.profile == "control":
        if inputs.leader_emergency > 0.0:
            if character_name in {SWINDLER, *DOCTRINE_CONTROLLERS, INNKEEPER, ESCAPE_SLAVE, RUNNER, CARD_TO_NAMES[1][0]}:
                disruption += 0.55 + 0.30 * inputs.leader_emergency
                combo += 0.15 * inputs.leader_emergency
                reasons.append("control_efficient_denial")
            if inputs.leader_near_end and character_name in {*DOCTRINE_CONTROLLERS, SWINDLER, INNKEEPER, ESCAPE_SLAVE}:
                disruption += 0.55
                survival += 0.25
                reasons.append("control_endgame_lock")
        elif inputs.buy_value > 0.0 and character_name in {MATCHMAKER, BUILDER, SWINDLER, INNKEEPER, RUNNER}:
            expansion += 0.80 + 0.30 * inputs.buy_value
            economy += 0.30
            if character_name == MATCHMAKER:
                expansion += 0.28 + 0.12 * inputs.matchmaker_adjacent_value
            elif character_name == BUILDER:
                expansion += 0.24 + 0.15 * inputs.builder_free_purchase_value
            reasons.append("control_keeps_pace")
        elif character_name in {ASSASSIN, TRACKER}:
            disruption -= 1.05
            survival -= 0.15
            reasons.append("control_deprioritizes_raw_denial")
        if character_name == BANDIT and inputs.has_marks and inputs.top_threat_present:
            profit_window = max(
                0.0,
                min(6.0, float(inputs.top_threat_cash) / 4.0) + 0.35 * float(inputs.top_threat_tiles_owned),
            )
            disruption += 0.55 + 0.20 * profit_window
            economy += 0.20 + 0.12 * profit_window
            reasons.append("control_profit_mark_window")
        if inputs.finisher_window > 0.0:
            if character_name in {MATCHMAKER, BUILDER, SWINDLER, INNKEEPER, RUNNER}:
                expansion += 1.00 + 0.42 * inputs.finisher_window + 0.22 * inputs.buy_value
                economy += 0.42 + 0.20 * inputs.finisher_window
                combo += 0.22 * inputs.finisher_window
                reasons.append(f"control_finisher_window={inputs.finisher_reason}")
            if character_name in {ASSASSIN, TRACKER}:
                disruption -= 0.70 + 0.22 * inputs.finisher_window
                survival -= 0.12 * inputs.finisher_window
                reasons.append("control_finisher_avoids_redundant_denial")

    if inputs.profile == "aggressive":
        if character_name in {MATCHMAKER, BUILDER, SWINDLER, TRACKER, ASSASSIN}:
            combo += 0.9
            reasons.append("aggressive_push")

    if inputs.profile == "token_opt":
        if character_name in {INNKEEPER, RUNNER, ESCAPE_SLAVE}:
            economy += 1.2 * inputs.cross_start + 0.7 * inputs.land_f * inputs.land_f_value
            combo += inputs.token_combo
            reasons.append("token_route_mobility")
        if character_name in {INNKEEPER, MATCHMAKER, BUILDER, SWINDLER}:
            economy += 1.4 * inputs.own_land
            reasons.append("own_tile_token_arrival")
        if character_name in {ASSASSIN, TRACKER, BANDIT} and inputs.top_threat_present and inputs.leader_pressure >= 2.5:
            disruption += 0.8 + 0.25 * inputs.leader_pressure
            reasons.append("token_threshold_counter")
        if inputs.placeable:
            combo += 0.8 + 1.4 * inputs.own_land + inputs.token_combo
            reasons.append("token_placeable_pressure")

    return expansion, economy, disruption, survival, combo, reasons


def evaluate_v3_character_rules(
    character_name: str,
    inputs: V3CharacterInputs,
) -> tuple[float, float, float, float, float, float, list[str]]:
    expansion = 0.0
    economy = 0.0
    disruption = 0.0
    survival = 0.0
    combo = 0.0
    meta = 0.0
    reasons: list[str] = []

    if character_name in {RUNNER, INNKEEPER, ESCAPE_SLAVE}:
        economy += 1.15 * inputs.cross_start + 0.70 * inputs.land_f * inputs.land_f_value
        survival += 0.18 * inputs.distress_level
        combo += 0.35 * inputs.token_combo
        reasons.append("v3_route_loop")
    if character_name in {SHAKEDOWN_MARKER, PUBLIC_CLEANER, *DOCTRINE_CONTROLLERS}:
        survival += 0.55 + 0.18 * inputs.shards + 0.14 * inputs.burden_count + 0.18 * inputs.distress_level
        meta += 0.22 * inputs.cleanup_pressure
        reasons.append("v3_cleanup_anchor")
    if character_name == SHAKEDOWN_MARKER:
        if inputs.shards >= 5:
            combo += 0.95
            reasons.append("v3_baksu_checkpoint")
        elif inputs.shards >= 4 and inputs.burden_count > 0:
            combo += 1.25
            survival += 1.10
            economy += 0.35
            reasons.append("v3_baksu_precheckpoint")
        else:
            economy += 0.10 * max(0, 5 - inputs.shards)
            survival += 0.08 * max(0, 5 - inputs.shards)
    if character_name == CLERK:
        combo += 0.30 * inputs.stack_max_enemy + 0.55 * inputs.stack_max_enemy_owned + 0.12 * inputs.mobility_leverage
        if inputs.stack_max_enemy_owned > 0:
            reasons.append("v3_ajeon_burst_window")
    if character_name == INNKEEPER:
        economy += 0.55 * inputs.lap_fast_window + 0.45 * inputs.lap_rich_pool
        combo += 0.28 * inputs.lap_double_lap_threat + 0.10 * inputs.mobility_leverage
        if inputs.lap_fast_window > 0.0 or inputs.lap_double_lap_threat > 0.0:
            reasons.append("v3_gakju_lap_engine")
    if character_name == PUBLIC_CLEANER:
        if inputs.shards >= 7:
            combo += 0.85
            reasons.append("v3_manshin_checkpoint")
        else:
            economy += 0.08 * max(0, 7 - inputs.shards)
            survival += 0.10 * max(0, 7 - inputs.shards)
    if character_name in {MATCHMAKER, BUILDER, SWINDLER}:
        expansion += 0.20 * max(0.0, inputs.buy_value)
        if inputs.reserve_gap > 0.0 or inputs.cleanup_pressure >= 1.8 or inputs.money_distress >= 1.0:
            expansion -= 0.85 + 0.24 * inputs.reserve_gap + 0.16 * inputs.cleanup_pressure + 0.20 * max(0.0, inputs.money_distress - 1.0)
            survival -= 0.08 * inputs.distress_level
            reasons.append("v3_safe_expansion_only")
        elif inputs.own_land > 0.15 or inputs.token_window >= 1.25:
            combo += 0.35
            reasons.append("v3_expand_into_revisit")
    if inputs.token_window >= 1.20 and character_name in {INNKEEPER, RUNNER, *DOCTRINE_CONTROLLERS, SHAKEDOWN_MARKER}:
        combo += 0.48 + 0.14 * inputs.token_window + 0.10 * inputs.distress_level
        reasons.append("v3_token_window")
    if inputs.legal_visible_burden_total > 0.0 and inputs.top_threat_cash >= 0:
        if character_name in {SHAKEDOWN_MARKER, PUBLIC_CLEANER, BANDIT, ASSASSIN, TRACKER}:
            disruption += 0.35 + 0.10 * inputs.legal_visible_burden_total + 0.06 * inputs.distress_level
            reasons.append("v3_burden_attack_timing")

    return expansion, economy, disruption, survival, combo, meta, reasons


def evaluate_v2_tactical_rules(
    character_name: str,
    inputs: V2TacticalInputs,
) -> tuple[float, float, float, float, float, float, list[str]]:
    expansion = 0.0
    economy = 0.0
    disruption = 0.0
    meta = 0.0
    combo = 0.0
    survival = 0.0
    reasons: list[str] = []

    if character_name == EOSA:
        race_bonus = 1.35 * inputs.land_race_pressure + 0.55 * inputs.premium_unowned
        if inputs.profile == "v3_gpt" and inputs.early_round > 0.0:
            race_bonus += 0.95 + 0.25 * inputs.behind_tiles
        disruption += race_bonus
        expansion += 0.35 * inputs.near_unowned
        if race_bonus > 0.0:
            reasons.append("early_turn_order_land_race")
        if inputs.top_threat_is_shard_attack_counter_target:
            disruption += 1.8
            reasons.append("muroe_counter")

    if character_name == TAMGWANORI:
        race_bonus = 1.42 * inputs.land_race_pressure + 0.32 * max(0.0, inputs.player_shards - 2.0)
        if inputs.profile == "v3_gpt" and inputs.early_round > 0.0:
            race_bonus += 1.05 + 0.20 * inputs.premium_unowned
        expansion += race_bonus
        economy += 0.18 * inputs.premium_unowned
        if race_bonus > 0.0:
            reasons.append("early_turn_order_land_race")

    if character_name == TRACKER:
        disruption += 0.8
        if inputs.buy_value > 0:
            disruption += 2.6
            reasons.append("post_buy_rent_trap")
        if inputs.leader_pressure > 0 and inputs.top_threat_tiles_owned >= 5:
            disruption += 1.0 + 0.45 * inputs.leader_pressure
            reasons.append("leader_position_punish")
        if inputs.has_marks and inputs.top_threat_cash >= 8:
            disruption += 1.1

    if character_name == INNKEEPER:
        economy += 2.0 * inputs.cross_start + 1.2 * inputs.land_f * inputs.land_f_value + 0.25 * inputs.visited_owned_tile_count
        economy += 0.65 * inputs.lap_fast_window + 0.45 * inputs.lap_rich_pool
        combo += 0.40 * inputs.lap_double_lap_threat
        if inputs.profile == "v3_gpt" and inputs.cleanup_pressure < 1.4:
            economy += 0.85 + 0.35 * inputs.lap_fast_window + 0.30 * inputs.lap_rich_pool
            combo += 0.20 * inputs.lap_double_lap_threat
            reasons.append("v3_lap_engine_convert_window")
        if inputs.leader_pressure > 0 and (inputs.top_threat_cross > 0.3 or inputs.top_threat_land_f > 0.2 or inputs.top_threat_is_expansion_geo_combo):
            disruption += 1.0 + 0.3 * inputs.leader_pressure
            reasons.append("deny_leader_lap_engine")
        if inputs.cross_start > 0.3:
            reasons.append("near_start_cross")
        if inputs.land_f > 0.2:
            reasons.append("f_tile_bonus")
        if inputs.combo_has_lap_combo_tricks:
            combo += 1.6
            reasons.append("lap_token_combo")
        if inputs.cleanup_growth_locked:
            penalty = 0.70 + 0.32 * inputs.cleanup_stage_score
            economy -= penalty
            combo -= 0.18 * inputs.cleanup_stage_score
            reasons.append("cleanup_growth_lock")

    if character_name == RUNNER:
        economy += 1.0 * inputs.cross_start + 0.55 * inputs.land_f * inputs.land_f_value
        combo += 0.6 * float(inputs.combo_has_speed_tricks)
        if inputs.combo_has_speed_tricks:
            reasons.append("speed_combo")

    if character_name == ESCAPE_SLAVE:
        economy += 0.3 * inputs.reachable_specials_with_one_short
        if inputs.cross_start > 0.2:
            combo += 0.8
            reasons.append("escape_runner")

    if character_name in {BANDIT, CLERK, TAMGWANORI}:
        economy += 0.35 * inputs.player_shards
        if inputs.combo_has_relic_collector:
            combo += 1.3
            reasons.append("shard_combo")

    if character_name == CLERK:
        disruption += 0.35 * inputs.max_enemy_stack + 0.70 * inputs.max_enemy_owned_stack + 0.18 * inputs.mobility_leverage
        if inputs.max_enemy_owned_stack > 0:
            reasons.append("stacked_enemy_burst_window")

    if character_name == ASSASSIN:
        if inputs.has_marks and inputs.top_threat_is_expansion_geo_combo:
            disruption += 2.4 + 0.45 * inputs.leader_pressure
            reasons.append("prevent_big_turn")

    if character_name == BANDIT:
        if inputs.has_marks and (inputs.top_threat_cash >= 12 or inputs.top_threat_tiles_owned >= 5):
            disruption += 1.8 + 0.15 * inputs.player_shards + 0.35 * inputs.leader_pressure
            reasons.append("cash_damage_value")

    if character_name == PUBLIC_CLEANER:
        if inputs.top_threat_is_burden:
            disruption += 2.0
            reasons.append("burden_purge")
        if inputs.legal_visible_burden_total > 0:
            disruption += 1.4 + 1.2 * inputs.legal_visible_burden_total + 0.45 * inputs.legal_visible_burden_peak
            reasons.append("public_burden_cleanup_value")
        if inputs.cleanup_pressure >= 2.5:
            survival += 0.45 * inputs.cleanup_pressure
            reasons.append("future_fire_insurance")
        if inputs.legal_visible_burden_total > 0 and inputs.legal_low_cash_targets > 0:
            disruption += 0.35 * inputs.legal_low_cash_targets
            reasons.append("cash_fragile_cleanup")

    if character_name == SHAKEDOWN_MARKER:
        if inputs.burden_count >= 1:
            combo += 1.0 + 0.45 * inputs.burden_count
            survival += 1.4 + 1.05 * inputs.burden_count + 0.55 * inputs.cleanup_pressure
            reasons.append("future_burden_escape")
        if inputs.burden_count >= 1 and inputs.has_marks and inputs.legal_low_cash_targets > 0:
            disruption += 0.35 * inputs.legal_low_cash_targets
            reasons.append("burden_dump_fragile_target")
        if inputs.player_shards < 5:
            if inputs.burden_count >= 1 and inputs.has_marks and (inputs.legal_visible_burden_peak > 0 or inputs.legal_low_cash_targets > 0):
                combo += 0.45 + 0.20 * inputs.cleanup_stage_score
                reasons.append("precheckpoint_baksu_window")
            else:
                penalty = 1.35 + 0.35 * inputs.cleanup_stage_score
                survival -= penalty
                combo -= 0.25
                reasons.append("precheckpoint_baksu_needs_certainty")

    if character_name in DOCTRINE_CONTROLLERS:
        meta += 1.2
        if inputs.top_threat_is_expansion_geo_combo or inputs.top_threat_tiles_owned >= 5:
            meta += 1.6 + 0.35 * inputs.leader_pressure
            reasons.append("flip_meta_denial")
        if inputs.marker_plan_best_score > 0.0:
            meta += 0.95 + 0.85 * inputs.marker_plan_best_score
            disruption += 0.30 * inputs.marker_plan_best_score
            reasons.append("marker_strips_needed_leader_face")
        if inputs.cleanup_controller_bias > 0.0:
            survival += 0.30 + 0.28 * inputs.cleanup_controller_bias
            meta += 0.10 * inputs.cleanup_stage_score
            reasons.append("cleanup_controller_window")

    if character_name in {SHAKEDOWN_MARKER, PUBLIC_CLEANER, INNKEEPER} and inputs.own_burden_cost > 0.0:
        survival += 0.25 * inputs.own_burden_cost
        reasons.append("burden_liquidity_cover")

    return expansion, economy, disruption, meta, combo, survival, reasons


def evaluate_v2_emergency_risk_rules(
    character_name: str,
    inputs: V2EmergencyRiskInputs,
) -> tuple[float, float, float, float, list[str]]:
    expansion = 0.0
    economy = 0.0
    disruption = 0.0
    survival = 0.0
    reasons: list[str] = []

    if inputs.leader_emergency > 0.0:
        if character_name in {ASSASSIN, BANDIT, TRACKER, SWINDLER, SHAKEDOWN_MARKER, PUBLIC_CLEANER, CARD_TO_NAMES[1][0]}:
            disruption += 1.55 + 0.55 * inputs.leader_emergency
            if inputs.leader_is_solo:
                disruption += 0.45
            if inputs.leader_near_end:
                disruption += 0.55
            reasons.append("emergency_leader_denial")
        if character_name in DOCTRINE_CONTROLLERS:
            disruption += 0.35 * inputs.leader_emergency
            reasons.append("emergency_marker_denial")
        if inputs.leader_near_end and character_name in {MATCHMAKER, BUILDER, INNKEEPER, RUNNER}:
            expansion -= 0.85 + 0.25 * inputs.leader_emergency
            economy -= 0.35 * inputs.leader_emergency
            if character_name == BUILDER and inputs.player_shards > 0:
                expansion += 0.20
            reasons.append("leader_race_deprioritized")

    if inputs.reserve_gap > 0.0 and character_name in {ASSASSIN, BANDIT, TRACKER}:
        if inputs.profile == "control":
            disruption -= 0.35 * inputs.reserve_gap
            survival -= 0.20 * inputs.reserve_gap
            reasons.append("control_avoids_costly_denial_when_dry")
    if inputs.reserve_gap <= 1.0 and character_name in {SWINDLER, INNKEEPER, RUNNER, ESCAPE_SLAVE}:
        if inputs.profile == "control":
            survival += 0.20
            economy += 0.15
            reasons.append("control_low_cost_stability")

    if character_name in {INNKEEPER, RUNNER, ESCAPE_SLAVE}:
        survival += 0.22 * inputs.expected_loss + 0.10 * inputs.worst_loss
        reasons.append("liquidity_escape_value")
    if character_name in {MATCHMAKER, BUILDER, SWINDLER, INNKEEPER, RUNNER} and inputs.reserve_gap > 0.0:
        expansion -= 0.45 * inputs.reserve_gap
        survival -= 0.25 * inputs.reserve_gap
        reasons.append("expansion_cash_drag")
    if character_name in {SHAKEDOWN_MARKER, PUBLIC_CLEANER, INNKEEPER} and inputs.own_burden_cost > 0.0:
        survival += 0.25 * inputs.own_burden_cost
        reasons.append("burden_liquidity_cover")

    return expansion, economy, disruption, survival, reasons


def evaluate_v2_post_risk_rules(
    character_name: str,
    inputs: V2PostRiskInputs,
) -> tuple[float, float, list[str]]:
    score = 0.0
    survival = 0.0
    reasons: list[str] = []

    if inputs.reserve_gap > 0.0:
        survival -= 0.55 * inputs.reserve_gap
        reasons.append(f"cash_dry={inputs.reserve_gap:.2f}")

    return score, survival, reasons


def evaluate_v2_tail_threat_rules(
    inputs: V2TailThreatInputs,
) -> tuple[float, list[str]]:
    survival = 0.0
    reasons: list[str] = []

    if inputs.mark_risk > 0.0:
        survival -= inputs.mark_risk
        reasons.append(f"mark_risk={inputs.mark_risk:.2f}")

    return survival, reasons


def evaluate_v2_rent_tail_rules(
    inputs: V2RentTailInputs,
) -> tuple[float, float, float, list[str]]:
    reasons: list[str] = []
    if inputs.rent_pressure > 0.0:
        reasons.append(f"rent_pressure={inputs.rent_pressure:.2f}")
    return inputs.rent_economy, inputs.rent_combo, inputs.rent_survival, reasons


def evaluate_v2_uhsa_tail_rules(
    inputs: V2UhsaTailInputs,
) -> tuple[float, list[str]]:
    survival = 0.0
    reasons: list[str] = []
    if inputs.blocked:
        survival -= 1.8
        reasons.append("uhsa_blocks_muroe")
    return survival, reasons
