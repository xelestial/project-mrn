from __future__ import annotations

from dataclasses import dataclass

from config import CellKind
from policy.character_traits import is_baksu, is_growth_character, is_token_window_character
from policy.context.survival_context import PolicySurvivalContext


@dataclass(frozen=True, slots=True)
class PurchaseWindowAssessment:
    reserve_floor: float
    safe_low_cost_t3: bool
    safe_growth_buy: bool
    token_preferred: bool
    v3_cleanup_soft_block: bool
    baksu_online_exception: bool


@dataclass(frozen=True, slots=True)
class PurchaseDecisionResult:
    decision: bool
    reserve_floor: float
    shortfall: float
    danger_cash: bool
    cleanup_lock: bool
    token_preferred: bool
    v3_cleanup_soft_block: bool


def build_immediate_win_purchase_result(*, reserve: float) -> PurchaseDecisionResult:
    return PurchaseDecisionResult(
        decision=True,
        reserve_floor=reserve,
        shortfall=0.0,
        danger_cash=False,
        cleanup_lock=False,
        token_preferred=False,
        v3_cleanup_soft_block=False,
    )


@dataclass(frozen=True, slots=True)
class PurchaseDebugContext:
    source: str
    pos: int
    cell_name: str
    cost: int
    cash_before: float
    cash_after: float
    reserve: float
    money_distress: float
    two_turn_lethal_prob: float
    latent_cleanup_cost: float
    cleanup_cash_gap: float
    expected_loss: float
    worst_loss: float
    blocks_enemy_monopoly: bool
    token_window_value: float


@dataclass(frozen=True, slots=True)
class TraitPurchaseDecisionInputs:
    profile: str
    current_character: str | None
    cash_before: float
    remaining_cash: float
    reserve: float
    reserve_floor: float
    benefit: float
    token_window_value: float
    money_distress: float
    complete_monopoly: bool
    blocks_enemy: bool
    hard_reason: str | None
    own_burdens: float
    next_neg: float
    two_neg: float
    negative_cards: float
    downside_cleanup: float
    worst_cleanup: float
    public_cleanup_active: bool
    active_cleanup_cost: float
    latent_cleanup_cost: float
    purchase_window: PurchaseWindowAssessment | None


def build_purchase_debug_context(
    *,
    source: str,
    pos: int,
    cell_name: str,
    cost: int,
    cash_before: float,
    cash_after: float,
    reserve: float,
    money_distress: float,
    two_turn_lethal_prob: float,
    latent_cleanup_cost: float,
    cleanup_cash_gap: float,
    expected_loss: float,
    worst_loss: float,
    blocks_enemy_monopoly: bool,
    token_window_value: float,
) -> PurchaseDebugContext:
    return PurchaseDebugContext(
        source=source,
        pos=pos,
        cell_name=cell_name,
        cost=cost,
        cash_before=cash_before,
        cash_after=cash_after,
        reserve=reserve,
        money_distress=money_distress,
        two_turn_lethal_prob=two_turn_lethal_prob,
        latent_cleanup_cost=latent_cleanup_cost,
        cleanup_cash_gap=cleanup_cash_gap,
        expected_loss=expected_loss,
        worst_loss=worst_loss,
        blocks_enemy_monopoly=blocks_enemy_monopoly,
        token_window_value=token_window_value,
    )


def build_purchase_early_debug_payload(
    *,
    source: str,
    pos: int,
    cell_name: str,
    cost: int,
    decision: bool,
    reason: str,
    reserve: float | None = None,
    cash: float | None = None,
    benefit: float | None = None,
    token_window: float | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": source,
        "pos": pos,
        "cell": cell_name,
        "cost": cost,
        "decision": decision,
        "reason": reason,
    }
    if reserve is not None:
        payload["reserve"] = round(reserve, 3)
    if cash is not None:
        payload["cash"] = cash
    if benefit is not None:
        payload["benefit"] = round(benefit, 3)
    if token_window is not None:
        payload["token_window"] = round(token_window, 3)
    return payload


@dataclass(frozen=True, slots=True)
class PurchaseBenefitInputs:
    cell: CellKind
    profile: str
    complete_monopoly: bool
    blocks_enemy: bool
    owned_in_block: int
    is_unowned_tile: bool = True


@dataclass(frozen=True, slots=True)
class V3PurchaseBenefitAdjustment:
    benefit: float
    safe_low_cost_t3: bool
    safe_growth_buy: bool
    early_token_window_veto: bool


@dataclass(frozen=True, slots=True)
class V3PurchaseBenefitInputs:
    cell: CellKind
    cost: int
    remaining_cash: float
    reserve: float
    cleanup_pressure: float
    money_distress: float
    own_burdens: float
    token_window_value: float
    complete_monopoly: bool
    blocks_enemy: bool
    current_benefit: float
    baksu_online: bool
    growth_character: bool = False
    token_window_character: bool = False


@dataclass(frozen=True, slots=True)
class V3PreparedPurchaseBenefit:
    benefit: float
    safe_low_cost_t3: bool
    safe_growth_buy: bool
    early_token_window_veto: bool


def count_owned_tiles_in_block(
    *,
    block_ids: list[int],
    tile_owner: list[int | None],
    pos: int,
    player_id: int,
) -> int:
    block_id = block_ids[pos]
    if block_id < 0:
        return 0
    return sum(
        1
        for i, bid in enumerate(block_ids)
        if bid == block_id and tile_owner[i] == player_id
    )


def would_purchase_trigger_immediate_win(
    *,
    tiles_owned: int,
    tiles_to_trigger_end: int | None,
    monopolies_to_trigger_end: int | None,
    complete_monopoly: bool,
) -> bool:
    if tiles_to_trigger_end and tiles_owned + 1 >= tiles_to_trigger_end:
        return True
    if monopolies_to_trigger_end and complete_monopoly:
        return True
    return False


def build_purchase_benefit(inputs: PurchaseBenefitInputs) -> float:
    benefit = 0.8
    if inputs.cell == CellKind.T3:
        benefit += 1.4
    elif inputs.cell == CellKind.T2:
        benefit += 0.8
    if inputs.complete_monopoly:
        benefit += 2.4
    if inputs.blocks_enemy:
        benefit += 3.2
    elif inputs.owned_in_block > 0:
        benefit += 0.45 * inputs.owned_in_block
    if inputs.profile in {"growth", "aggressive"}:
        benefit += 0.35
    if inputs.profile == "token_opt" and inputs.is_unowned_tile:
        benefit += 0.25
    return benefit


def apply_v3_purchase_benefit_adjustments(inputs: V3PurchaseBenefitInputs) -> V3PurchaseBenefitAdjustment:
    benefit = inputs.current_benefit
    if inputs.own_burdens > 0.0:
        benefit -= 0.16 * inputs.own_burdens
    safe_low_cost_t3 = inputs.cell == CellKind.T3 and inputs.cost <= 3 and inputs.remaining_cash >= inputs.reserve + 1.0
    safe_growth_buy = (
        inputs.cell in {CellKind.T2, CellKind.T3}
        and inputs.cost <= 4
        and inputs.remaining_cash >= inputs.reserve + 1.0
        and inputs.cleanup_pressure < 1.40
        and inputs.money_distress < 1.0
    )
    early_token_window_veto = (
        inputs.token_window_value >= max(3.35 if safe_low_cost_t3 else 2.85, 1.45 * benefit)
        and not inputs.complete_monopoly
        and not inputs.blocks_enemy
        and not safe_low_cost_t3
        and not safe_growth_buy
    )
    if safe_low_cost_t3:
        benefit += 1.45
    elif inputs.cell == CellKind.T3 and inputs.remaining_cash >= inputs.reserve + 1.0:
        benefit += 0.65
    if safe_growth_buy:
        benefit += 1.10 + (0.45 if inputs.cell == CellKind.T3 else 0.28)
    if inputs.baksu_online and inputs.cleanup_pressure >= 1.0:
        benefit += 0.85
    if inputs.growth_character and inputs.token_window_value >= 1.0:
        benefit += 0.18
    if inputs.token_window_character and inputs.token_window_value >= 1.0:
        benefit += 0.18
    return V3PurchaseBenefitAdjustment(
        benefit=benefit,
        safe_low_cost_t3=safe_low_cost_t3,
        safe_growth_buy=safe_growth_buy,
        early_token_window_veto=early_token_window_veto,
    )


def prepare_v3_purchase_benefit_with_traits(
    *,
    current_character: str | None,
    shards: int,
    cell: CellKind,
    cost: int,
    remaining_cash: float,
    reserve: float,
    cleanup_pressure: float,
    money_distress: float,
    own_burdens: float,
    token_window_value: float,
    complete_monopoly: bool,
    blocks_enemy: bool,
    current_benefit: float,
) -> V3PreparedPurchaseBenefit:
    adjusted = apply_v3_purchase_benefit_adjustments(
        V3PurchaseBenefitInputs(
            cell=cell,
            cost=cost,
            remaining_cash=remaining_cash,
            reserve=reserve,
            cleanup_pressure=cleanup_pressure,
            money_distress=money_distress,
            own_burdens=own_burdens,
            token_window_value=token_window_value,
            complete_monopoly=complete_monopoly,
            blocks_enemy=blocks_enemy,
            current_benefit=current_benefit,
            baksu_online=(is_baksu(current_character) and shards >= 5),
            growth_character=is_growth_character(current_character),
            token_window_character=is_token_window_character(current_character),
        )
    )
    return V3PreparedPurchaseBenefit(
        benefit=adjusted.benefit,
        safe_low_cost_t3=adjusted.safe_low_cost_t3,
        safe_growth_buy=adjusted.safe_growth_buy,
        early_token_window_veto=adjusted.early_token_window_veto,
    )


def build_purchase_reserve_floor(
    *,
    reserve: float,
    remaining_cash: float,
    survival: PolicySurvivalContext,
    public_cleanup_active: bool,
    active_cleanup_cost: float,
    downside_expected_cleanup_cost: float,
    worst_cleanup_cost: float,
    latent_cleanup_cost: float,
    needs_income: bool,
) -> float:
    reserve_floor = reserve + 1.35 * survival.signals.two_turn_lethal_prob + 0.85 * survival.money_distress
    reserve_floor += 0.60 * latent_cleanup_cost
    reserve_floor += 0.55 * survival.expected_cleanup_cost
    reserve_floor += 0.50 * downside_expected_cleanup_cost
    reserve_floor += 0.10 * worst_cleanup_cost
    if public_cleanup_active:
        reserve_floor += 0.65 * active_cleanup_cost
    if needs_income:
        reserve_floor += 1.0
    return reserve_floor


def assess_v3_purchase_window(
    *,
    current_character: str | None,
    shards: int,
    cell: CellKind,
    cost: int,
    remaining_cash: float,
    reserve: float,
    survival: PolicySurvivalContext,
    token_window_value: float,
    benefit: float,
    complete_monopoly: bool,
    blocks_enemy: bool,
) -> PurchaseWindowAssessment:
    benefit_adjustment = apply_v3_purchase_benefit_adjustments(
        V3PurchaseBenefitInputs(
            cell=cell,
            cost=cost,
            remaining_cash=remaining_cash,
            reserve=reserve,
            cleanup_pressure=survival.cleanup_pressure,
            money_distress=survival.money_distress,
            own_burdens=survival.own_burdens,
            token_window_value=token_window_value,
            complete_monopoly=complete_monopoly,
            blocks_enemy=blocks_enemy,
            current_benefit=benefit,
            baksu_online=(is_baksu(current_character) and shards >= 5),
            token_window_character=False,
        )
    )
    safe_low_cost_t3 = benefit_adjustment.safe_low_cost_t3
    safe_growth_buy = benefit_adjustment.safe_growth_buy
    token_preferred = token_window_value >= benefit + 1.2 and not complete_monopoly and not blocks_enemy
    reserve_floor = build_purchase_reserve_floor(
        reserve=reserve,
        remaining_cash=remaining_cash,
        survival=survival,
        public_cleanup_active=survival.signals.public_cleanup_active,
        active_cleanup_cost=survival.signals.active_cleanup_cost,
        downside_expected_cleanup_cost=float(survival.raw.get("downside_expected_cleanup_cost", 0.0)),
        worst_cleanup_cost=float(survival.raw.get("worst_cleanup_cost", 0.0)),
        latent_cleanup_cost=survival.signals.latent_cleanup_cost,
        needs_income=bool(float(survival.raw.get("needs_income", 0.0)) > 0.0),
    )
    baksu_online_exception = (
        is_baksu(current_character)
        and shards >= 5
        and cell == CellKind.T3
        and cost <= 3
        and remaining_cash >= max(reserve - 1.0, 0.0)
    )
    v3_cleanup_soft_block = (
        not complete_monopoly
        and not blocks_enemy
        and not baksu_online_exception
        and (
            survival.cleanup_pressure >= 2.0
            or survival.money_distress >= 1.15
            or survival.signals.two_turn_lethal_prob >= 0.22
        )
        and remaining_cash < reserve_floor + 0.6
    )
    return PurchaseWindowAssessment(
        reserve_floor=reserve_floor,
        safe_low_cost_t3=safe_low_cost_t3,
        safe_growth_buy=safe_growth_buy,
        token_preferred=token_preferred,
        v3_cleanup_soft_block=v3_cleanup_soft_block,
        baksu_online_exception=baksu_online_exception,
    )


def assess_v3_purchase_window_with_traits(
    *,
    current_character: str | None,
    shards: int,
    cell: CellKind,
    cost: int,
    remaining_cash: float,
    reserve: float,
    survival: PolicySurvivalContext,
    token_window_value: float,
    benefit: float,
    complete_monopoly: bool,
    blocks_enemy: bool,
) -> PurchaseWindowAssessment:
    benefit_adjustment = apply_v3_purchase_benefit_adjustments(
        V3PurchaseBenefitInputs(
            cell=cell,
            cost=cost,
            remaining_cash=remaining_cash,
            reserve=reserve,
            cleanup_pressure=survival.cleanup_pressure,
            money_distress=survival.money_distress,
            own_burdens=survival.own_burdens,
            token_window_value=token_window_value,
            complete_monopoly=complete_monopoly,
            blocks_enemy=blocks_enemy,
            current_benefit=benefit,
            baksu_online=(is_baksu(current_character) and shards >= 5),
            growth_character=is_growth_character(current_character),
            token_window_character=is_token_window_character(current_character),
        )
    )
    safe_low_cost_t3 = benefit_adjustment.safe_low_cost_t3
    safe_growth_buy = benefit_adjustment.safe_growth_buy
    token_preferred = token_window_value >= benefit + 1.2 and not complete_monopoly and not blocks_enemy
    reserve_floor = build_purchase_reserve_floor(
        reserve=reserve,
        remaining_cash=remaining_cash,
        survival=survival,
        public_cleanup_active=survival.signals.public_cleanup_active,
        active_cleanup_cost=survival.signals.active_cleanup_cost,
        downside_expected_cleanup_cost=float(survival.raw.get("downside_expected_cleanup_cost", 0.0)),
        worst_cleanup_cost=float(survival.raw.get("worst_cleanup_cost", 0.0)),
        latent_cleanup_cost=survival.signals.latent_cleanup_cost,
        needs_income=bool(float(survival.raw.get("needs_income", 0.0)) > 0.0),
    )
    baksu_online_exception = (
        is_baksu(current_character)
        and shards >= 5
        and cell == CellKind.T3
        and cost <= 3
        and remaining_cash >= max(reserve - 1.0, 0.0)
    )
    v3_cleanup_soft_block = (
        not complete_monopoly
        and not blocks_enemy
        and not baksu_online_exception
        and (
            survival.cleanup_pressure >= 2.0
            or survival.money_distress >= 1.15
            or survival.signals.two_turn_lethal_prob >= 0.22
        )
        and remaining_cash < reserve_floor + 0.6
    )
    return PurchaseWindowAssessment(
        reserve_floor=reserve_floor,
        safe_low_cost_t3=safe_low_cost_t3,
        safe_growth_buy=safe_growth_buy,
        token_preferred=token_preferred,
        v3_cleanup_soft_block=v3_cleanup_soft_block,
        baksu_online_exception=baksu_online_exception,
    )


def assess_purchase_decision(
    *,
    profile: str,
    current_character: str | None,
    cash_before: float,
    remaining_cash: float,
    reserve: float,
    reserve_floor: float,
    benefit: float,
    token_window_value: float,
    money_distress: float,
    complete_monopoly: bool,
    blocks_enemy: bool,
    hard_reason: str | None,
    own_burdens: float,
    next_neg: float,
    two_neg: float,
    negative_cards: float,
    downside_cleanup: float,
    worst_cleanup: float,
    public_cleanup_active: bool,
    active_cleanup_cost: float,
    latent_cleanup_cost: float,
    purchase_window: PurchaseWindowAssessment | None,
) -> PurchaseDecisionResult:
    shortfall = max(0.0, reserve_floor - remaining_cash)
    danger_cash = remaining_cash <= max(6.0, 0.70 * reserve_floor)
    cleanup_lock = (
        public_cleanup_active
        and remaining_cash < active_cleanup_cost
        and not blocks_enemy and not complete_monopoly
    ) or (
        latent_cleanup_cost >= max(8.0, cash_before * 0.8)
        and remaining_cash < reserve_floor
        and not blocks_enemy and not complete_monopoly
    ) or (
        own_burdens >= 1.0 and next_neg >= 0.10 and remaining_cash < max(reserve + 3.0, downside_cleanup + 2.0, 0.60 * worst_cleanup + 1.5)
        and not blocks_enemy and not complete_monopoly
    ) or (
        own_burdens >= 2.0 and negative_cards > 0.0 and (two_neg >= 0.22 or downside_cleanup >= 8.0)
        and remaining_cash < max(reserve + 4.0, downside_cleanup + 2.5, 0.75 * worst_cleanup + 2.0)
        and not blocks_enemy and not complete_monopoly
    ) or (
        own_burdens >= 3.0 and negative_cards > 0.0 and remaining_cash < max(reserve + 5.0, downside_cleanup + 3.0, worst_cleanup + 1.0)
        and not blocks_enemy and not complete_monopoly
    ) or (
        hard_reason is not None and not blocks_enemy and not complete_monopoly
    )
    token_preferred = token_window_value >= benefit + (1.2 if profile == "v3_gpt" else 1.6) and not complete_monopoly and not blocks_enemy
    v3_cleanup_soft_block = False
    if profile == "v3_gpt" and purchase_window is not None:
        token_preferred = purchase_window.token_preferred
        v3_cleanup_soft_block = purchase_window.v3_cleanup_soft_block
    decision = not (
        shortfall > benefit
        or token_preferred
        or (danger_cash and shortfall > 0.15)
        or (
            money_distress >= 1.0
            and not blocks_enemy
            and not complete_monopoly
            and not (
                profile == "v3_gpt"
                and is_baksu(current_character)
                and purchase_window is not None
                and purchase_window.baksu_online_exception
            )
            and remaining_cash < reserve_floor + 1.5
        )
        or cleanup_lock
        or v3_cleanup_soft_block
    )
    if (
        profile == "v3_gpt"
        and purchase_window is not None
        and purchase_window.baksu_online_exception
        and hard_reason is None
    ):
        decision = True
    return PurchaseDecisionResult(
        decision=decision,
        reserve_floor=reserve_floor,
        shortfall=shortfall,
        danger_cash=danger_cash,
        cleanup_lock=cleanup_lock,
        token_preferred=token_preferred,
        v3_cleanup_soft_block=v3_cleanup_soft_block,
    )


def assess_purchase_decision_with_traits(
    *,
    profile: str,
    current_character: str | None,
    cash_before: float,
    remaining_cash: float,
    reserve: float,
    reserve_floor: float,
    benefit: float,
    token_window_value: float,
    money_distress: float,
    complete_monopoly: bool,
    blocks_enemy: bool,
    hard_reason: str | None,
    own_burdens: float,
    next_neg: float,
    two_neg: float,
    negative_cards: float,
    downside_cleanup: float,
    worst_cleanup: float,
    public_cleanup_active: bool,
    active_cleanup_cost: float,
    latent_cleanup_cost: float,
    purchase_window: PurchaseWindowAssessment | None,
) -> PurchaseDecisionResult:
    shortfall = max(0.0, reserve_floor - remaining_cash)
    danger_cash = remaining_cash <= max(6.0, 0.70 * reserve_floor)
    cleanup_lock = (
        public_cleanup_active
        and remaining_cash < active_cleanup_cost
        and not blocks_enemy and not complete_monopoly
    ) or (
        latent_cleanup_cost >= max(8.0, cash_before * 0.8)
        and remaining_cash < reserve_floor
        and not blocks_enemy and not complete_monopoly
    ) or (
        own_burdens >= 1.0 and next_neg >= 0.10 and remaining_cash < max(reserve + 3.0, downside_cleanup + 2.0, 0.60 * worst_cleanup + 1.5)
        and not blocks_enemy and not complete_monopoly
    ) or (
        own_burdens >= 2.0 and negative_cards > 0.0 and (two_neg >= 0.22 or downside_cleanup >= 8.0)
        and remaining_cash < max(reserve + 4.0, downside_cleanup + 2.5, 0.75 * worst_cleanup + 2.0)
        and not blocks_enemy and not complete_monopoly
    ) or (
        own_burdens >= 3.0 and negative_cards > 0.0 and remaining_cash < max(reserve + 5.0, downside_cleanup + 3.0, worst_cleanup + 1.0)
        and not blocks_enemy and not complete_monopoly
    ) or (
        hard_reason is not None and not blocks_enemy and not complete_monopoly
    )
    token_preferred = token_window_value >= benefit + (1.2 if profile == "v3_gpt" else 1.6) and not complete_monopoly and not blocks_enemy
    v3_cleanup_soft_block = False
    if profile == "v3_gpt" and purchase_window is not None:
        token_preferred = purchase_window.token_preferred
        v3_cleanup_soft_block = purchase_window.v3_cleanup_soft_block
    decision = not (
        shortfall > benefit
        or token_preferred
        or (danger_cash and shortfall > 0.15)
        or (
            money_distress >= 1.0
            and not blocks_enemy
            and not complete_monopoly
            and not (
                profile == "v3_gpt"
                and is_baksu(current_character)
                and purchase_window is not None
                and purchase_window.baksu_online_exception
            )
            and remaining_cash < reserve_floor + 1.5
        )
        or cleanup_lock
        or v3_cleanup_soft_block
    )
    if (
        profile == "v3_gpt"
        and purchase_window is not None
        and purchase_window.baksu_online_exception
        and hard_reason is None
    ):
        decision = True
    return PurchaseDecisionResult(
        decision=decision,
        reserve_floor=reserve_floor,
        shortfall=shortfall,
        danger_cash=danger_cash,
        cleanup_lock=cleanup_lock,
        token_preferred=token_preferred,
        v3_cleanup_soft_block=v3_cleanup_soft_block,
    )


def assess_purchase_decision_from_inputs(inputs: TraitPurchaseDecisionInputs) -> PurchaseDecisionResult:
    return assess_purchase_decision_with_traits(
        profile=inputs.profile,
        current_character=inputs.current_character,
        cash_before=inputs.cash_before,
        remaining_cash=inputs.remaining_cash,
        reserve=inputs.reserve,
        reserve_floor=inputs.reserve_floor,
        benefit=inputs.benefit,
        token_window_value=inputs.token_window_value,
        money_distress=inputs.money_distress,
        complete_monopoly=inputs.complete_monopoly,
        blocks_enemy=inputs.blocks_enemy,
        hard_reason=inputs.hard_reason,
        own_burdens=inputs.own_burdens,
        next_neg=inputs.next_neg,
        two_neg=inputs.two_neg,
        negative_cards=inputs.negative_cards,
        downside_cleanup=inputs.downside_cleanup,
        worst_cleanup=inputs.worst_cleanup,
        public_cleanup_active=inputs.public_cleanup_active,
        active_cleanup_cost=inputs.active_cleanup_cost,
        latent_cleanup_cost=inputs.latent_cleanup_cost,
        purchase_window=inputs.purchase_window,
    )


def build_purchase_debug_payload(
    *,
    context: PurchaseDebugContext,
    result: PurchaseDecisionResult,
) -> dict[str, object]:
    return {
        "source": context.source,
        "pos": context.pos,
        "cell": context.cell_name,
        "cost": context.cost,
        "cash_before": context.cash_before,
        "cash_after": context.cash_after,
        "reserve": round(context.reserve, 3),
        "money_distress": round(context.money_distress, 3),
        "two_turn_lethal_prob": round(context.two_turn_lethal_prob, 3),
        "latent_cleanup_cost": round(context.latent_cleanup_cost, 3),
        "cleanup_cash_gap": round(context.cleanup_cash_gap, 3),
        "expected_loss": round(context.expected_loss, 3),
        "worst_loss": round(context.worst_loss, 3),
        "blocks_enemy_monopoly": context.blocks_enemy_monopoly,
        "token_window_value": round(context.token_window_value, 3),
        "decision": result.decision,
    }
