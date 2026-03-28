from policy.decision.active_flip import ActiveFlipDebugPayload, resolve_random_active_flip_choice, resolve_scored_active_flip_choice, build_active_flip_debug_payload
from policy.decision.character_choice import CharacterChoiceCandidate, NamedCharacterChoicePolicy, build_character_choice_debug_payload, build_named_character_choice_policy, build_uniform_random_character_choice_debug_payload, decide_character_choice, evaluate_character_choice, evaluate_named_character_choice, evaluate_named_character_choice_with_policy, run_named_character_choice_with_policy, summarize_character_choice_debug
from policy.decision.coin_placement import choose_coin_placement_tile_id
from policy.decision.hidden_trick import resolve_hidden_trick_choice_run
from policy.decision.scored_choice import run_ranked_choice, run_scored_choice
from characters import CARD_TO_NAMES, CHARACTERS
from policy.context.survival_context import build_policy_survival_context
from policy.context.turn_plan import PlayerIntentState, build_turn_plan_context
from policy.decision.lap_reward import BasicLapRewardInputs, V2ProfileLapRewardInputs, V3LapRewardInputs, apply_turn_plan_lap_bias, apply_v2_profile_lap_reward_bias, evaluate_basic_lap_reward, evaluate_v3_lap_reward, normalize_lap_reward_scores, resolve_lap_reward_bundle
from policy.decision.mark_target import PublicMarkChoiceDebug, build_empty_public_mark_choice_debug_payload, build_public_mark_choice_debug_payload, evaluate_public_mark_candidates, filter_public_mark_candidates, resolve_public_mark_choice, resolve_random_public_mark_choice, run_public_mark_choice
from policy.decision.movement import MovementChoiceResolution, apply_movement_intent_adjustment, resolve_movement_choice
from policy.decision.purchase import PurchaseBenefitInputs, PurchaseDebugContext, TraitPurchaseDecisionInputs, V3PurchaseBenefitInputs, apply_v3_purchase_benefit_adjustments, assess_purchase_decision, assess_purchase_decision_from_inputs, assess_purchase_decision_with_traits, assess_v3_purchase_window, assess_v3_purchase_window_with_traits, build_immediate_win_purchase_result, build_purchase_benefit, build_purchase_debug_context, build_purchase_debug_payload, build_purchase_early_debug_payload, build_purchase_reserve_floor, count_owned_tiles_in_block, prepare_v3_purchase_benefit_with_traits, would_purchase_trigger_immediate_win
from policy.decision.runtime_bridge import choose_active_flip_card_runtime, choose_burden_exchange_on_supply_runtime, choose_coin_placement_tile_runtime, choose_doctrine_relief_target_runtime, choose_hidden_trick_card_runtime, choose_lap_reward_runtime, choose_mark_target_runtime, choose_purchase_tile_runtime, choose_specific_trick_reward_runtime, choose_trick_to_use_runtime
from policy.decision.support_choices import BurdenExchangeDecisionInputs, DistressMarkerInputs, DoctrineReliefCandidateInputs, EscapeSeekInputs, GeoBonusDecisionInputs, build_distress_marker_bonus, choose_doctrine_relief_player_from_inputs, choose_doctrine_relief_player_id, choose_geo_bonus_kind, count_burden_cards, should_exchange_burden_on_supply, should_seek_escape_package_from_inputs
from policy.decision.trick_reward import build_trick_reward_debug_payload, resolve_trick_reward_choice, resolve_trick_reward_choice_run
from policy.decision.trick_usage import apply_trick_preserve_rules, build_trick_use_debug_payload, resolve_trick_use_choice
from policy.environment_traits import count_cleanup_fortunes, fortune_cleanup_deck_profile, has_color_rent_double_weather, is_cleanup_threat_weather, weather_character_adjustment
from policy.evaluator.character_scoring import V1CharacterStructuralInputs, V2EmergencyRiskInputs, V2ExpansionInputs, V2PostRiskInputs, V2ProfileInputs, V2RentTailInputs, V2RouteInputs, V2TailThreatInputs, V2TacticalInputs, V2UhsaTailInputs, V3CharacterInputs, evaluate_v1_character_structural_rules, evaluate_v2_emergency_risk_rules, evaluate_v2_expansion_rules, evaluate_v2_post_risk_rules, evaluate_v2_profile_rules, evaluate_v2_rent_tail_rules, evaluate_v2_route_rules, evaluate_v2_tail_threat_rules, evaluate_v2_tactical_rules, evaluate_v2_uhsa_tail_rules, evaluate_v3_character_rules
from policy.evaluator.runtime_bridge import score_character_v1, score_character_v2, score_target_v1, score_target_v2
from policy.asset.spec import ArenaPolicyAsset, HeuristicPolicyAsset, MultiAgentBattleAsset
from policy.character_traits import active_money_drain_names, escape_package_names, is_active_money_drain_character, is_baksu, is_builder_character, is_cleanup_character, is_direct_denial_character, is_gakju, is_growth_character, is_low_cash_controller_character, is_low_cash_disruptor_character, is_low_cash_escape_character, is_low_cash_income_character, is_mansin, is_route_runner_character, is_shard_hunter_character, is_swindler, is_token_window_character, low_cash_controller_names, low_cash_disruptor_names, low_cash_escape_names, low_cash_income_names, marker_package_names
from policy.factory import PolicyFactory
import ai_policy as ai_policy_module
from ai_policy import HeuristicPolicy
from config import CellKind
from survival_common import CleanupStrategyContext
from trick_cards import TrickCard
from types import SimpleNamespace


def _cleanup_context(*, cleanup_stage: str = "stable", shard_tier: str = "buffered", growth_locked: bool = False) -> CleanupStrategyContext:
    return CleanupStrategyContext(
        burden_count=1.0,
        shard_tier=shard_tier,
        shard_buffer_cash=1.5,
        cleanup_stage=cleanup_stage,
        stage_score=2.0 if cleanup_stage in {"critical", "meltdown"} else 0.0,
        deck_pressure=0.0,
        cash_pressure=0.0,
        controller_bias=0.0,
        lap_cash_preference=0.0,
        lap_shard_preference=0.0,
        growth_locked=growth_locked,
    )


def test_build_turn_plan_context_keeps_intent_and_cleanup_fields() -> None:
    intent = PlayerIntentState(
        plan_key="lap_engine",
        resource_intent="card_preserve",
        reason="gakju_online",
        source_character="source",
        plan_confidence=0.75,
        plan_start_round=3,
        expires_after_round=5,
    )
    ctx = build_turn_plan_context(
        intent,
        _cleanup_context(cleanup_stage="critical", shard_tier="stable", growth_locked=True),
        current_character="current",
        cash=7,
        shards=6,
    )

    assert ctx.plan_key == "lap_engine"
    assert ctx.resource_intent == "card_preserve"
    assert ctx.cleanup_stage == "critical"
    assert ctx.shard_tier == "stable"
    assert ctx.growth_locked is True
    assert ctx.cash == 7
    assert ctx.shards == 6


def test_build_character_choice_debug_payload_keeps_summary_fields() -> None:
    summary = summarize_character_choice_debug(
        [1],
        evaluate_character_choice(
            [1],
            evaluator=lambda key: CharacterChoiceCandidate(
                key=key,
                score=2.5,
                reasons=("why",),
                hard_blocked=True,
                hard_block_detail={"blocked": True},
                metadata={"survival_severity": {"stage": "critical"}},
            ),
        ),
        label_for_key=str,
    )
    payload = build_character_choice_debug_payload(
        policy_name="heuristic_v3_gpt",
        offered_cards=[1],
        debug_summary=summary,
        generic_survival_score=1.25,
        survival_urgency=0.75,
        survival_first=True,
        survival_weight_multiplier=1.4,
        chosen_key=1,
        chosen_name="picked",
        reasons_for_choice=["why"],
        hard_blocked_map={"picked": {"blocked": True}},
        character_names_by_key={"1": "picked"},
    )

    assert payload["candidate_scores"]["1"] == 2.5
    assert payload["survival_hard_blocked_candidates"]["picked"]["blocked"] is True
    assert payload["candidate_characters"]["1"] == "picked"


def test_build_uniform_random_character_choice_debug_payload_marks_zero_scores() -> None:
    payload = build_uniform_random_character_choice_debug_payload(
        policy_name="random",
        offered_cards=[3, 7],
        candidate_labels=["3", "7"],
        chosen_key=7,
        chosen_name="picked",
    )

    assert payload["candidate_scores"] == {"3": 0.0, "7": 0.0}
    assert payload["chosen_card"] == 7
    assert payload["chosen_character"] == "picked"


def test_evaluate_v3_lap_reward_prefers_shards_for_baksu_checkpoint() -> None:
    scores = evaluate_v3_lap_reward(
        V3LapRewardInputs(
            current_character=CARD_TO_NAMES[6][0],
            cash=8,
            shards=3,
            hand_coins=0,
            placeable=False,
            buy_value=0.0,
            cross_start=0.1,
            land_f=0.0,
            land_f_value=0.0,
            own_land=0.0,
            token_window_score=0.2,
            token_window_nearest_distance=6.0,
            token_window_revisit_prob=0.05,
            cleanup_pressure=1.0,
            next_negative_cleanup_prob=0.05,
            two_negative_cleanup_prob=0.10,
            expected_cleanup_cost=1.0,
            survival_cash_pressure=False,
            burden_count=1.0,
            lap_cash_preference=0.0,
            lap_shard_preference=0.0,
            cleanup_growth_locked=False,
            cleanup_stage="stable",
            cleanup_stage_score=0.0,
            is_leader=False,
            rich_pool=0.0,
            is_baksu=True,
            is_mansin=False,
            is_shard_hunter=False,
            is_controller=False,
            is_gakju=False,
        )
    )

    assert scores[3] == "shards"


def test_weather_character_adjustment_uses_trait_backed_rules() -> None:
    score, reasons = weather_character_adjustment({"성물의 날"}, CARD_TO_NAMES[6][0])

    assert score > 0.0
    assert "weather_shard_synergy" in reasons


def test_count_cleanup_fortunes_aggregates_named_cards() -> None:
    counts = count_cleanup_fortunes(
        [
            SimpleNamespace(name="화재 발생"),
            SimpleNamespace(name="산불 발생"),
            SimpleNamespace(name="자원 순환"),
            SimpleNamespace(name="모두의 순환"),
        ]
    )

    assert counts == (1, 1, 1, 1)


def test_is_cleanup_threat_weather_matches_helper_table() -> None:
    assert is_cleanup_threat_weather("긴급 피난") is True


def test_is_direct_denial_character_matches_expected_faces() -> None:
    assert is_direct_denial_character(CARD_TO_NAMES[2][0]) is True
    assert is_direct_denial_character(CARD_TO_NAMES[5][0]) is False


def test_has_color_rent_double_weather_matches_color_rule() -> None:
    assert has_color_rent_double_weather({"검은 달"}, "검은색") is True
    assert has_color_rent_double_weather({"검은 달"}, "빨간색") is False


def test_fortune_cleanup_deck_profile_tracks_cleanup_cards() -> None:
    profile = fortune_cleanup_deck_profile(
        [
            SimpleNamespace(name="산불 발생"),
            SimpleNamespace(name="화재 발생"),
            SimpleNamespace(name="길이 열리다"),
        ],
        [],
    )

    assert profile["remaining_negative_cleanup_cards"] == 2.0
    assert profile["next_draw_negative_cleanup_prob"] > 0.0


def test_resolve_lap_reward_bundle_prefers_requested_resource() -> None:
    choice, cash_units, shard_units, coin_units = resolve_lap_reward_bundle(
        cash_pool=5,
        shards_pool=5,
        coins_pool=5,
        points_budget=3,
        cash_point_cost=1,
        shards_point_cost=1,
        coins_point_cost=1,
        cash_unit_score=1.0,
        shard_unit_score=1.0,
        coin_unit_score=1.0,
        preferred="coins",
    )

    assert choice == "coins"
    assert cash_units + shard_units + coin_units == 3
    assert coin_units >= cash_units
    assert coin_units >= shard_units


def test_evaluate_v3_lap_reward_prefers_coins_in_safe_token_window() -> None:
    scores = evaluate_v3_lap_reward(
        V3LapRewardInputs(
            current_character=CARD_TO_NAMES[7][0],
            cash=12,
            shards=8,
            hand_coins=2,
            placeable=True,
            buy_value=2.0,
            cross_start=0.35,
            land_f=0.0,
            land_f_value=0.0,
            own_land=0.35,
            token_window_score=1.4,
            token_window_nearest_distance=3.0,
            token_window_revisit_prob=0.35,
            cleanup_pressure=0.6,
            next_negative_cleanup_prob=0.04,
            two_negative_cleanup_prob=0.08,
            expected_cleanup_cost=0.5,
            survival_cash_pressure=False,
            burden_count=0.0,
            lap_cash_preference=0.0,
            lap_shard_preference=0.0,
            cleanup_growth_locked=False,
            cleanup_stage="stable",
            cleanup_stage_score=0.0,
            is_leader=True,
            rich_pool=1.0,
            is_baksu=False,
            is_mansin=False,
            is_shard_hunter=False,
            is_controller=False,
            is_gakju=True,
        ),
        plan_ctx=build_turn_plan_context(
            PlayerIntentState(
                plan_key="lap_engine",
                resource_intent="card_preserve",
                reason="gakju_online",
                source_character=CARD_TO_NAMES[7][0],
                plan_confidence=0.8,
                plan_start_round=4,
                expires_after_round=6,
            ),
            _cleanup_context(cleanup_stage="stable"),
            current_character=CARD_TO_NAMES[7][0],
            cash=12,
            shards=8,
        ),
    )

    assert scores[3] == "coins"


def test_evaluate_basic_lap_reward_prefers_shards_for_shard_hunter() -> None:
    scores = evaluate_basic_lap_reward(
        BasicLapRewardInputs(
            current_character=CARD_TO_NAMES[2][1],
            cash=9,
            shards=5,
            placeable=False,
            survival_cash_pressure=False,
            is_shard_hunter=True,
        ),
        balanced=False,
    )

    assert scores[3] == "shards"


def test_choose_coin_placement_tile_id_prefers_token_window_lane() -> None:
    choice = choose_coin_placement_tile_id(
        [3, 7],
        tile_coins=[0, 0, 0, 1, 0, 0, 0, 0],
        board=[CellKind.T2, CellKind.T2, CellKind.T2, CellKind.T3, CellKind.T2, CellKind.T2, CellKind.T2, CellKind.T3],
        player_position=1,
        max_coins_per_tile=3,
        token_opt_profile=True,
    )

    assert choice == 3


def test_resolve_scored_active_flip_choice_keeps_debug_payload() -> None:
    resolution = resolve_scored_active_flip_choice(
        [1, 2],
        scored={1: 1.0, 2: 2.0},
        reasons={1: ["a"], 2: ["b"]},
        policy="heuristic_v3_gpt",
        chosen_to_resolver=lambda _: "flipped",
        generic_survival_score=1.25,
        money_distress=0.5,
        controller_need=0.75,
    )

    assert resolution.choice == 2
    assert resolution.debug_payload["chosen_to"] == "flipped"
    assert resolution.debug_payload["candidate_scores"]["2"] == 2.0


def test_build_purchase_early_debug_payload_rounds_optional_fields() -> None:
    payload = build_purchase_early_debug_payload(
        source="landing",
        pos=7,
        cell_name="T3",
        cost=3,
        decision=False,
        reason="v3_prefers_token_window",
        reserve=4.5678,
        cash=9,
        benefit=2.3456,
        token_window=1.9876,
    )

    assert payload["source"] == "landing"
    assert payload["reserve"] == 4.568
    assert payload["benefit"] == 2.346
    assert payload["token_window"] == 1.988


def test_build_immediate_win_purchase_result_marks_clean_success() -> None:
    result = build_immediate_win_purchase_result(reserve=5.5)

    assert result.decision is True
    assert result.reserve_floor == 5.5
    assert result.shortfall == 0.0
    assert result.cleanup_lock is False


def test_build_purchase_debug_context_preserves_fields() -> None:
    context = build_purchase_debug_context(
        source="landing",
        pos=8,
        cell_name="T3",
        cost=3,
        cash_before=9.0,
        cash_after=6.0,
        reserve=4.0,
        money_distress=0.8,
        two_turn_lethal_prob=0.2,
        latent_cleanup_cost=1.5,
        cleanup_cash_gap=0.3,
        expected_loss=2.0,
        worst_loss=4.0,
        blocks_enemy_monopoly=True,
        token_window_value=1.1,
    )

    assert context.pos == 8
    assert context.cash_after == 6.0
    assert context.blocks_enemy_monopoly is True


def test_build_trick_use_debug_payload_rounds_scores() -> None:
    payload = build_trick_use_debug_payload(
        score_map={"A": 1.2345},
        chosen_name="A",
        generic_survival_score=1.9876,
        survival_urgency=0.4444,
        strategic_mode=2.5555,
    )

    assert payload["chosen"] == "A"
    assert payload["scores"]["A"] == 1.2345
    assert payload["generic_survival_score"] == 1.988
    assert payload["strategic_mode"] == 2.555


def test_resolve_trick_use_choice_keeps_best_card_and_score_map() -> None:
    hand = [
        TrickCard(1, "A", ""),
        TrickCard(2, "B", ""),
    ]
    resolution = resolve_trick_use_choice(
        hand,
        scorer=lambda card: 1.0 if card.name == "A" else 2.5,
    )

    assert resolution.choice == hand[1]
    assert resolution.score_map["B"] == 2.5


def test_resolve_random_active_flip_choice_marks_uniform_random() -> None:
    resolution = resolve_random_active_flip_choice(
        [3, 4],
        policy="random",
        chooser=lambda values: values[-1],
    )

    assert resolution.choice == 4
    assert resolution.debug_payload["reasons"] == ["uniform_random"]


def test_resolve_trick_reward_choice_and_debug_payload() -> None:
    choices = [
        TrickCard(1, "A", ""),
        TrickCard(2, "B", ""),
    ]
    resolution = resolve_trick_reward_choice(
        choices,
        scorer=lambda card: 1.0 if card.name == "A" else 2.0,
    )

    payload = build_trick_reward_debug_payload(
        choices=choices,
        chosen=resolution.choice,
        score_map=resolution.score_map,
        generic_survival_score=1.25,
        survival_urgency=0.75,
    )

    assert resolution.choice == choices[1]
    assert payload["chosen"] == "B"
    assert payload["scores"]["B"] == 2.0


def test_resolve_trick_reward_choice_run_packages_choice_and_debug() -> None:
    choices = [
        TrickCard(1, "A", ""),
        TrickCard(2, "B", ""),
    ]

    choice_run = resolve_trick_reward_choice_run(
        choices=choices,
        scorer=lambda card: 1.0 if card.name == "A" else 2.0,
        generic_survival_score=1.25,
        survival_urgency=0.75,
    )

    assert choice_run.choice == choices[1]


def test_runtime_bridge_character_scoring_matches_live_policy_methods() -> None:
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
    state = SimpleNamespace(
        board=[CellKind.T2] * 40,
        block_ids=[-1] * 40,
        tile_owner=[None] * 40,
        tile_coins=[0] * 40,
        marker_owner_id=0,
        current_weather_effects=set(),
        config=SimpleNamespace(
            rules=SimpleNamespace(
                token=SimpleNamespace(max_coins_per_tile=3),
                dice=SimpleNamespace(values=[1, 2, 3, 4, 5, 6]),
            )
        ),
        tile_at=lambda _i: SimpleNamespace(purchase_cost=3),
    )
    player = SimpleNamespace(
        player_id=0,
        current_character=CARD_TO_NAMES[7][0],
        cash=10,
        shards=3,
        hand_coins=0,
        tiles_owned=1,
        pending_marks=[],
        visited_owned_tile_indices=[],
        trick_hand=[],
        used_dice_cards=[],
        position=0,
        attribute=CHARACTERS[CARD_TO_NAMES[7][0]].attribute,
    )
    policy._alive_enemies = lambda _state, _player: []
    policy._allowed_mark_targets = lambda _state, _player: []
    policy._burden_context = lambda _state, _player, legal_targets=None: {
        "own_burdens": 0.0,
        "cleanup_pressure": 0.0,
        "legal_visible_burden_total": 0.0,
        "legal_visible_burden_peak": 0.0,
        "legal_low_cash_targets": 0.0,
    }
    policy._monopoly_block_metrics = lambda _state, _player: {
        "own_near_complete": 0.0,
        "own_claimable_blocks": 0.0,
        "deny_now": 0.0,
        "enemy_near_complete": 0.0,
        "contested_blocks": 0.0,
    }
    policy._scammer_takeover_metrics = lambda _state, _player: {
        "coin_value": 0.0,
        "best_tile_coins": 0.0,
        "blocks_enemy_monopoly": 0.0,
        "finishes_own_monopoly": 0.0,
    }
    policy._enemy_stack_metrics = lambda _state, _player: {"max_enemy_stack": 0.0, "max_enemy_owned_stack": 0.0}
    policy._lap_engine_context = lambda _state, _player: {"fast_window": 0.0, "mobility": 0.0, "rich_pool": 0.0, "double_lap_threat": 0.0}
    policy._failed_mark_fallback_metrics = lambda _player, _value: (0.0, 0.0)
    policy._reachable_specials_with_one_short = lambda _state, _player: 0
    policy._has_uhsa_alive = lambda _state, exclude_player_id=None: False
    policy._public_mark_risk_breakdown = lambda _state, _player, _name: (0.0, [])
    policy._rent_pressure_breakdown = lambda _state, _player, _name: (0.0, [])
    policy._apply_rent_pressure_adjustment_v1 = lambda _state, _player, _name, _pressure, _reasons: 0.0
    policy._expected_buy_value = lambda _state, _player: 0.0
    policy._matchmaker_adjacent_value = lambda _state, _player: 0.0
    policy._builder_free_purchase_value = lambda _state, _player: 0.0
    policy._will_cross_start = lambda _state, _player: 0.0
    policy._will_land_on_f = lambda _state, _player: 0.0
    policy._f_progress_context = lambda _state, _player: {"land_f_value": 0.0}
    policy._liquidity_risk_metrics = lambda _state, _player, _name: {
        "reserve": 0.0,
        "cash_after_reserve": 10.0,
        "expected_loss": 0.0,
        "worst_loss": 0.0,
        "own_burden_cost": 0.0,
    }
    policy._profile_from_mode = lambda mode=None: "heuristic_v2_control"
    policy._cleanup_strategy_context = lambda _survival, _player: _cleanup_context()
    policy._predicted_opponent_archetypes = lambda _state, _player, _target=None: set()
    policy._leader_pressure = lambda _state, _player, _target=None: 0.0
    policy._leader_denial_snapshot = lambda _state, _player, threat_targets=None, top_threat=None: {"emergency": 0.0, "solo_leader": False, "near_end": False, "top_threat": None}
    policy._early_land_race_context = lambda _state, _player: {"race_pressure": 0.0, "premium_unowned": 0.0, "near_unowned": 0.0, "behind_tiles": 0.0, "early_round": 0.0}
    policy._token_teleport_combo_score = lambda _player: 0.0
    policy._prob_land_on_placeable_own_tile = lambda _state, _player: 0.0
    policy._best_token_window_value = lambda _state, _player: 0.0
    policy._control_finisher_window = lambda _player: (0.0, "")
    policy._leader_marker_flip_plan = lambda _state, _player, _target=None: {"best_score": 0.0}
    policy._generic_survival_context = lambda _state, _player, _name: {}
    policy._weights = lambda: {"expansion": 1.0, "economy": 1.0, "disruption": 1.0, "meta": 1.0, "combo": 1.0, "survival": 1.0}
    policy._exclusive_blocks_owned = lambda _state, _player_id: 0

    assert policy._character_score_breakdown(state, player, CARD_TO_NAMES[7][0]) == score_character_v1(policy, state, player, CARD_TO_NAMES[7][0])
    assert policy._character_score_breakdown_v2(state, player, CARD_TO_NAMES[7][0]) == score_character_v2(policy, state, player, CARD_TO_NAMES[7][0])


def test_runtime_bridge_target_scoring_matches_live_policy_methods() -> None:
    policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
    state = SimpleNamespace(
        board=[CellKind.T2] * 10,
        tile_owner=[None] * 10,
        position=0,
        config=SimpleNamespace(rules=SimpleNamespace(dice=SimpleNamespace(values=[1, 2, 3, 4, 5, 6]))),
    )
    player = SimpleNamespace(
        player_id=0,
        current_character=CARD_TO_NAMES[6][0],
        cash=10,
        shards=4,
        tiles_owned=1,
        position=0,
        trick_hand=[],
    )
    target = SimpleNamespace(
        player_id=1,
        current_character=CARD_TO_NAMES[7][0],
        pending_marks=[],
        attribute=CHARACTERS[CARD_TO_NAMES[7][0]].attribute,
        tiles_owned=1,
        cash=8,
        used_dice_cards=[],
    )
    policy._estimated_threat = lambda _state, _player, _target: 2.0
    policy._predicted_opponent_archetypes = lambda _state, _player, _target: set()
    policy._leader_denial_snapshot = lambda _state, _player: {"top_threat": None, "emergency": 0.0, "solo_leader": False, "near_end": False}
    policy._expected_buy_value = lambda _state, _player: 0.0
    policy._visible_burden_count = lambda _viewer, _target: 0

    assert policy._target_score_breakdown(state, player, CARD_TO_NAMES[6][0], target) == score_target_v1(policy, state, player, CARD_TO_NAMES[6][0], target)
    assert policy._target_score_breakdown_v2(state, player, CARD_TO_NAMES[6][0], target) == score_target_v2(policy, state, player, CARD_TO_NAMES[6][0], target)


def test_runtime_bridge_purchase_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    cell = SimpleNamespace(name="T2")
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _pos, _cell, _cost, *, source="landing"):
        seen["args"] = (_policy, _state, _player, _pos, _cell, _cost, source)
        return False

    monkeypatch.setattr(ai_policy_module, "choose_purchase_tile_runtime", fake_runtime)

    result = policy.choose_purchase_tile(state, player, 7, cell, 3, source="landing")

    assert result is False
    assert seen["args"] == (policy, state, player, 7, cell, 3, "landing")


def test_runtime_bridge_lap_reward_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    sentinel = object()
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player):
        seen["args"] = (_policy, _state, _player)
        return sentinel

    monkeypatch.setattr(ai_policy_module, "choose_lap_reward_runtime", fake_runtime)

    result = policy.choose_lap_reward(state, player)

    assert result is sentinel
    assert seen["args"] == (policy, state, player)


def test_runtime_bridge_trick_use_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(round_index=0, rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    hand = [SimpleNamespace(name="x")]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _hand):
        seen["args"] = (_policy, _state, _player, _hand)
        return None

    monkeypatch.setattr(ai_policy_module, "choose_trick_to_use_runtime", fake_runtime)

    result = policy.choose_trick_to_use(state, player, hand)

    assert result is None
    assert seen["args"] == (policy, state, player, hand)


def test_choose_trick_to_use_runtime_derives_window_signals(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_preserve_rules(**kwargs):
        captured.update(kwargs)
        return 0.0

    monkeypatch.setattr("policy.decision.runtime_bridge.apply_trick_preserve_rules", fake_preserve_rules)

    policy = SimpleNamespace(
        _generic_survival_context=lambda _s, _p, _n: {
            "land_f": 1.0,
            "cross_start": 0.0,
            "survival_urgency": 0.5,
            "money_distress": 0.4,
            "cleanup_cash_gap": 0.0,
            "own_burdens": 0.0,
            "next_draw_negative_cleanup_prob": 0.0,
            "two_draw_negative_cleanup_prob": 0.0,
            "generic_survival_score": 0.0,
        },
        _trick_decisive_context=lambda _s, _p, _ctx: {
            "finish_f_window": 0.0,
            "buy_window": 1.0,
            "strategic_mode": 0.0,
        },
        _current_player_intent=lambda _s, _p, _n: None,
        _predict_trick_cash_cost=lambda _card: 0.0,
        _is_action_survivable=lambda *_args, **_kwargs: True,
        _survival_hard_guard_reason=lambda *_args, **_kwargs: None,
        _trick_survival_adjustment=lambda *_args, **_kwargs: 0.0,
        _trick_decisive_adjustment=lambda *_args, **_kwargs: 0.0,
        _trick_preserve_adjustment=lambda *_args, **_kwargs: 0.0,
        _token_teleport_combo_score=lambda _player: 1.0,
        _expected_buy_value=lambda _state, _player: 1.5,
        _profile_from_mode=lambda *_args, **_kwargs: "v3_gpt",
        _set_debug=lambda *_args, **_kwargs: None,
        character_policy_mode="heuristic_v3_gpt",
    )
    state = SimpleNamespace(
        round_index=1,
        board=[CellKind.T2, CellKind.T3],
        tile_owner=[1, None],
        players=[
            SimpleNamespace(player_id=0, alive=True, position=0),
            SimpleNamespace(player_id=1, alive=True, position=5),
        ],
        tile_at=lambda idx: SimpleNamespace(purchase_cost=3 if idx == 1 else 2),
    )
    player = SimpleNamespace(
        player_id=0,
        current_character=CARD_TO_NAMES[6][0],
        cash=8,
        tiles_owned=1,
        position=0,
    )
    hand = [SimpleNamespace(name="?íš‚???")]

    choose_trick_to_use_runtime(policy, state, player, hand)

    assert captured["has_relic_collector_window"] is True
    assert captured["has_help_run_window"] is True
    assert captured["has_neojeol_chain_window"] is True
    assert captured["short_range_frontier_is_better"] is True


def test_choose_trick_to_use_runtime_requires_forward_encounter_for_help_run(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_preserve_rules(**kwargs):
        captured.update(kwargs)
        return 0.0

    monkeypatch.setattr("policy.decision.runtime_bridge.apply_trick_preserve_rules", fake_preserve_rules)

    policy = SimpleNamespace(
        _generic_survival_context=lambda _s, _p, _n: {
            "land_f": 0.0,
            "cross_start": 0.0,
            "survival_urgency": 0.5,
            "money_distress": 0.4,
            "cleanup_cash_gap": 0.0,
            "own_burdens": 0.0,
            "next_draw_negative_cleanup_prob": 0.0,
            "two_draw_negative_cleanup_prob": 0.0,
            "generic_survival_score": 0.0,
        },
        _trick_decisive_context=lambda _s, _p, _ctx: {
            "finish_f_window": 0.0,
            "buy_window": 1.0,
            "strategic_mode": 0.0,
        },
        _current_player_intent=lambda _s, _p, _n: None,
        _predict_trick_cash_cost=lambda _card: 0.0,
        _is_action_survivable=lambda *_args, **_kwargs: True,
        _survival_hard_guard_reason=lambda *_args, **_kwargs: None,
        _trick_survival_adjustment=lambda *_args, **_kwargs: 0.0,
        _trick_decisive_adjustment=lambda *_args, **_kwargs: 0.0,
        _trick_preserve_adjustment=lambda *_args, **_kwargs: 0.0,
        _token_teleport_combo_score=lambda _player: 1.0,
        _expected_buy_value=lambda _state, _player: 1.5,
        _profile_from_mode=lambda *_args, **_kwargs: "v3_gpt",
        _set_debug=lambda *_args, **_kwargs: None,
        character_policy_mode="heuristic_v3_gpt",
    )
    state = SimpleNamespace(
        round_index=1,
        board=[CellKind.T2, CellKind.T3],
        tile_owner=[1, None],
        players=[
            SimpleNamespace(player_id=0, alive=True, position=0),
            SimpleNamespace(player_id=1, alive=True, position=20),
        ],
        tile_at=lambda idx: SimpleNamespace(purchase_cost=3 if idx == 1 else 2),
    )
    player = SimpleNamespace(
        player_id=0,
        current_character=CARD_TO_NAMES[6][0],
        cash=8,
        tiles_owned=1,
        position=0,
    )
    hand = [SimpleNamespace(name="?íš‚???")]

    choose_trick_to_use_runtime(policy, state, player, hand)

    assert captured["has_help_run_window"] is False


def test_runtime_bridge_mark_target_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _actor_name):
        seen["args"] = (_policy, _state, _player, _actor_name)
        return "picked"

    monkeypatch.setattr(ai_policy_module, "choose_mark_target_runtime", fake_runtime)

    result = policy.choose_mark_target(state, player, "actor")

    assert result == "picked"
    assert seen["args"] == (policy, state, player, "actor")


def test_runtime_bridge_specific_trick_reward_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    choices = [SimpleNamespace(name="x")]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _choices):
        seen["args"] = (_policy, _state, _player, _choices)
        return None

    monkeypatch.setattr(ai_policy_module, "choose_specific_trick_reward_runtime", fake_runtime)

    result = policy.choose_specific_trick_reward(state, player, choices)

    assert result is None
    assert seen["args"] == (policy, state, player, choices)


def test_runtime_bridge_hidden_trick_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0, current_character=CARD_TO_NAMES[7][0])
    hand = [SimpleNamespace(name="x")]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _hand):
        seen["args"] = (_policy, _state, _player, _hand)
        return None

    monkeypatch.setattr(ai_policy_module, "choose_hidden_trick_card_runtime", fake_runtime)

    result = policy.choose_hidden_trick_card(state, player, hand)

    assert result is None
    assert seen["args"] == (policy, state, player, hand)


def test_runtime_bridge_coin_placement_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player):
        seen["args"] = (_policy, _state, _player)
        return 5

    monkeypatch.setattr(ai_policy_module, "choose_coin_placement_tile_runtime", fake_runtime)

    result = policy.choose_coin_placement_tile(state, player)

    assert result == 5
    assert seen["args"] == (policy, state, player)


def test_runtime_bridge_active_flip_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    flippable = [1, 2]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _flippable):
        seen["args"] = (_policy, _state, _player, _flippable)
        return 2

    monkeypatch.setattr(ai_policy_module, "choose_active_flip_card_runtime", fake_runtime)

    result = policy.choose_active_flip_card(state, player, flippable)

    assert result == 2
    assert seen["args"] == (policy, state, player, flippable)


def test_runtime_bridge_burden_exchange_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    card = SimpleNamespace(name="burden", burden_cost=3)
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _card):
        seen["args"] = (_policy, _state, _player, _card)
        return True

    monkeypatch.setattr(ai_policy_module, "choose_burden_exchange_on_supply_runtime", fake_runtime)

    result = policy.choose_burden_exchange_on_supply(state, player, card)

    assert result is True
    assert seen["args"] == (policy, state, player, card)


def test_runtime_bridge_doctrine_relief_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    candidates = [SimpleNamespace(player_id=0), SimpleNamespace(player_id=1)]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _candidates):
        seen["args"] = (_policy, _state, _player, _candidates)
        return 1

    monkeypatch.setattr(ai_policy_module, "choose_doctrine_relief_target_runtime", fake_runtime)

    result = policy.choose_doctrine_relief_target(state, player, candidates)

    assert result == 1
    assert seen["args"] == (policy, state, player, candidates)


def test_choose_doctrine_relief_target_runtime_prefers_distressed_candidate() -> None:
    policy = SimpleNamespace(
        _generic_survival_context=lambda _state, candidate, _name: {
            1: {
                "cleanup_pressure": 0.4,
                "money_distress": 0.1,
                "two_turn_lethal_prob": 0.0,
                "own_burden_cost": 0.0,
            },
            2: {
                "cleanup_pressure": 2.8,
                "money_distress": 1.0,
                "two_turn_lethal_prob": 0.35,
                "own_burden_cost": 5.0,
            },
        }[candidate.player_id]
    )
    state = SimpleNamespace()
    player = SimpleNamespace(player_id=1)
    burden = SimpleNamespace(is_burden=True)
    candidates = [
        SimpleNamespace(player_id=1, current_character=CARD_TO_NAMES[6][0], cash=10.0, trick_hand=[]),
        SimpleNamespace(player_id=2, current_character=CARD_TO_NAMES[7][0], cash=4.0, trick_hand=[burden, burden]),
    ]

    result = choose_doctrine_relief_target_runtime(policy, state, player, candidates)

    assert result == 2


def test_runtime_bridge_movement_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    sentinel = object()
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player):
        seen["args"] = (_policy, _state, _player)
        return sentinel

    monkeypatch.setattr(ai_policy_module, "choose_movement_runtime", fake_runtime)

    result = policy.choose_movement(state, player)

    assert result is sentinel
    assert seen["args"] == (policy, state, player)


def test_runtime_bridge_draft_card_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    offered_cards = [1, 2]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _offered_cards):
        seen["args"] = (_policy, _state, _player, _offered_cards)
        return 2

    monkeypatch.setattr(ai_policy_module, "choose_draft_card_runtime", fake_runtime)

    result = policy.choose_draft_card(state, player, offered_cards)

    assert result == 2
    assert seen["args"] == (policy, state, player, offered_cards)


def test_runtime_bridge_final_character_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    card_choices = [1, 2]
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _card_choices):
        seen["args"] = (_policy, _state, _player, _card_choices)
        return "picked"

    monkeypatch.setattr(ai_policy_module, "choose_final_character_runtime", fake_runtime)

    result = policy.choose_final_character(state, player, card_choices)

    assert result == "picked"
    assert seen["args"] == (policy, state, player, card_choices)


def test_runtime_bridge_geo_bonus_matches_live_policy_delegate(monkeypatch) -> None:
    policy = HeuristicPolicy()
    state = SimpleNamespace(rounds_completed=0)
    player = SimpleNamespace(player_id=0)
    seen: dict[str, object] = {}

    def fake_runtime(_policy, _state, _player, _actor_name):
        seen["args"] = (_policy, _state, _player, _actor_name)
        return "cash"

    monkeypatch.setattr(ai_policy_module, "choose_geo_bonus_runtime", fake_runtime)

    result = policy.choose_geo_bonus(state, player, "actor")

    assert result == "cash"
    assert seen["args"] == (policy, state, player, "actor")


def test_resolve_hidden_trick_choice_run_packages_choice_and_debug() -> None:
    cards = [
        SimpleNamespace(name="plain", is_burden=False, burden_cost=0, is_anytime=False, deck_index=1),
        SimpleNamespace(name="burden", is_burden=True, burden_cost=3, is_anytime=False, deck_index=2),
    ]

    choice_run = resolve_hidden_trick_choice_run(cards, actor_name=CARD_TO_NAMES[7][0])

    assert choice_run.choice is cards[1]
    assert choice_run.debug_payload["chosen"] == "burden"
    assert choice_run.debug_payload["scores"]["burden"] > choice_run.debug_payload["scores"]["plain"]


def test_purchase_structure_helpers_cover_block_count_and_immediate_win() -> None:
    owned = count_owned_tiles_in_block(
        block_ids=[-1, 2, 2, 3],
        tile_owner=[None, 1, 1, 2],
        pos=2,
        player_id=1,
    )
    win = would_purchase_trigger_immediate_win(
        tiles_owned=4,
        tiles_to_trigger_end=5,
        monopolies_to_trigger_end=3,
        complete_monopoly=False,
    )

    assert owned == 2
    assert win is True


def test_prepare_v3_purchase_benefit_with_traits_uses_trait_logic() -> None:
    prepared = prepare_v3_purchase_benefit_with_traits(
        current_character=CARD_TO_NAMES[6][0],
        shards=5,
        cell=CellKind.T3,
        cost=3,
        remaining_cash=7.0,
        reserve=5.0,
        cleanup_pressure=1.2,
        money_distress=0.8,
        own_burdens=1.0,
        token_window_value=1.5,
        complete_monopoly=False,
        blocks_enemy=False,
        current_benefit=2.0,
    )

    assert prepared.safe_low_cost_t3 is True
    assert prepared.benefit > 2.0


def test_prepare_v3_purchase_benefit_with_traits_adds_growth_token_window_bonus() -> None:
    prepared = prepare_v3_purchase_benefit_with_traits(
        current_character=CARD_TO_NAMES[8][1],
        shards=2,
        cell=CellKind.T2,
        cost=3,
        remaining_cash=8.0,
        reserve=5.0,
        cleanup_pressure=0.8,
        money_distress=0.5,
        own_burdens=0.0,
        token_window_value=1.2,
        complete_monopoly=False,
        blocks_enemy=False,
        current_benefit=2.0,
    )

    assert prepared.benefit > 2.0


def test_character_trait_helpers_use_registry_faces() -> None:
    assert is_baksu(CARD_TO_NAMES[6][0]) is True
    assert is_baksu(CARD_TO_NAMES[6][1]) is False
    assert is_gakju(CARD_TO_NAMES[7][0]) is True
    assert is_gakju(CARD_TO_NAMES[7][1]) is False
    assert is_mansin(CARD_TO_NAMES[6][1]) is True
    assert is_mansin(CARD_TO_NAMES[6][0]) is False
    assert is_builder_character(CARD_TO_NAMES[7][1]) is True
    assert is_builder_character(CARD_TO_NAMES[8][1]) is False
    assert is_swindler(CARD_TO_NAMES[8][1]) is True
    assert is_swindler(CARD_TO_NAMES[8][0]) is False
    assert is_growth_character(CARD_TO_NAMES[8][1]) is True
    assert is_growth_character(CARD_TO_NAMES[5][0]) is False
    assert is_cleanup_character(CARD_TO_NAMES[6][0]) is True
    assert is_cleanup_character(CARD_TO_NAMES[5][1]) is True
    assert is_cleanup_character(CARD_TO_NAMES[7][0]) is False
    assert is_route_runner_character(CARD_TO_NAMES[7][0]) is True
    assert is_route_runner_character(CARD_TO_NAMES[8][1]) is False
    assert is_shard_hunter_character(CARD_TO_NAMES[2][1]) is True
    assert is_shard_hunter_character(CARD_TO_NAMES[6][0]) is False
    assert is_token_window_character(CARD_TO_NAMES[7][1]) is True
    assert is_token_window_character(CARD_TO_NAMES[7][0]) is False
    assert is_active_money_drain_character(CARD_TO_NAMES[1][1]) is True
    assert is_active_money_drain_character(CARD_TO_NAMES[1][0]) is False
    assert is_low_cash_income_character(CARD_TO_NAMES[7][0]) is True
    assert is_low_cash_income_character(CARD_TO_NAMES[5][0]) is False
    assert is_low_cash_escape_character(CARD_TO_NAMES[4][0]) is True
    assert is_low_cash_escape_character(CARD_TO_NAMES[8][0]) is False
    assert is_low_cash_controller_character(CARD_TO_NAMES[5][0]) is True
    assert is_low_cash_controller_character(CARD_TO_NAMES[7][0]) is False
    assert is_low_cash_disruptor_character(CARD_TO_NAMES[2][0]) is True
    assert is_low_cash_disruptor_character(CARD_TO_NAMES[7][0]) is False
    assert CARD_TO_NAMES[6][1] in active_money_drain_names()
    assert low_cash_income_names() == {CARD_TO_NAMES[7][0], CARD_TO_NAMES[4][1], CARD_TO_NAMES[6][1]}
    assert low_cash_escape_names() == {CARD_TO_NAMES[7][0], CARD_TO_NAMES[4][0], CARD_TO_NAMES[3][1]}
    assert low_cash_controller_names() == {CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}
    assert low_cash_disruptor_names() == {CARD_TO_NAMES[2][0], CARD_TO_NAMES[4][1], CARD_TO_NAMES[6][1], CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}
    assert escape_package_names() == {CARD_TO_NAMES[6][0], CARD_TO_NAMES[6][1], CARD_TO_NAMES[3][1]}
    assert marker_package_names() == {CARD_TO_NAMES[5][0], CARD_TO_NAMES[5][1]}


def test_purchase_trait_wrappers_match_legacy_results() -> None:
    survival = build_policy_survival_context(
        {
            "money_distress": 1.1,
            "cleanup_pressure": 1.6,
            "own_burdens": 1.0,
            "reserve": 5.0,
            "public_cleanup_active": False,
            "active_cleanup_cost": 0.0,
            "latent_cleanup_cost": 2.0,
            "expected_cleanup_cost": 1.5,
            "downside_expected_cleanup_cost": 2.5,
            "worst_cleanup_cost": 4.0,
            "needs_income": 0.0,
            "next_draw_negative_cleanup_prob": 0.08,
            "two_draw_negative_cleanup_prob": 0.14,
            "remaining_negative_cleanup_cards": 3.0,
            "two_turn_lethal_prob": 0.05,
        },
        cash=8.0,
        shards=5,
    )
    legacy_window = assess_v3_purchase_window(
        current_character=CARD_TO_NAMES[6][0],
        shards=5,
        cell=CellKind.T3,
        cost=3,
        remaining_cash=8.0,
        reserve=5.0,
        survival=survival,
        token_window_value=1.0,
        benefit=2.0,
        complete_monopoly=False,
        blocks_enemy=False,
    )
    trait_window = assess_v3_purchase_window_with_traits(
        current_character=CARD_TO_NAMES[6][0],
        shards=5,
        cell=CellKind.T3,
        cost=3,
        remaining_cash=8.0,
        reserve=5.0,
        survival=survival,
        token_window_value=1.0,
        benefit=2.0,
        complete_monopoly=False,
        blocks_enemy=False,
    )

    assert trait_window.reserve_floor == legacy_window.reserve_floor
    assert trait_window.safe_low_cost_t3 == legacy_window.safe_low_cost_t3
    assert trait_window.safe_growth_buy == legacy_window.safe_growth_buy
    assert trait_window.token_preferred == legacy_window.token_preferred
    assert trait_window.v3_cleanup_soft_block == legacy_window.v3_cleanup_soft_block
    assert trait_window.baksu_online_exception == legacy_window.baksu_online_exception


def test_purchase_decision_trait_wrapper_matches_legacy_result() -> None:
    result = assess_purchase_decision(
        profile="v3_gpt",
        current_character=CARD_TO_NAMES[6][0],
        cash_before=8.0,
        remaining_cash=5.0,
        reserve=4.0,
        reserve_floor=4.5,
        benefit=2.0,
        token_window_value=0.5,
        money_distress=0.9,
        complete_monopoly=False,
        blocks_enemy=False,
        hard_reason=None,
        own_burdens=1.0,
        next_neg=0.05,
        two_neg=0.12,
        negative_cards=2.0,
        downside_cleanup=3.0,
        worst_cleanup=5.0,
        public_cleanup_active=False,
        active_cleanup_cost=0.0,
        latent_cleanup_cost=1.0,
        purchase_window=None,
    )
    trait_result = assess_purchase_decision_with_traits(
        profile="v3_gpt",
        current_character=CARD_TO_NAMES[6][0],
        cash_before=8.0,
        remaining_cash=5.0,
        reserve=4.0,
        reserve_floor=4.5,
        benefit=2.0,
        token_window_value=0.5,
        money_distress=0.9,
        complete_monopoly=False,
        blocks_enemy=False,
        hard_reason=None,
        own_burdens=1.0,
        next_neg=0.05,
        two_neg=0.12,
        negative_cards=2.0,
        downside_cleanup=3.0,
        worst_cleanup=5.0,
        public_cleanup_active=False,
        active_cleanup_cost=0.0,
        latent_cleanup_cost=1.0,
        purchase_window=None,
    )

    assert trait_result == result


def test_assess_purchase_decision_from_inputs_matches_direct_helper() -> None:
    inputs = TraitPurchaseDecisionInputs(
        profile="v3_gpt",
        current_character=CARD_TO_NAMES[6][0],
        cash_before=8.0,
        remaining_cash=5.0,
        reserve=4.0,
        reserve_floor=4.5,
        benefit=2.0,
        token_window_value=0.5,
        money_distress=0.9,
        complete_monopoly=False,
        blocks_enemy=False,
        hard_reason=None,
        own_burdens=1.0,
        next_neg=0.05,
        two_neg=0.12,
        negative_cards=2.0,
        downside_cleanup=3.0,
        worst_cleanup=5.0,
        public_cleanup_active=False,
        active_cleanup_cost=0.0,
        latent_cleanup_cost=1.0,
        purchase_window=None,
    )

    wrapper_result = assess_purchase_decision_from_inputs(inputs)
    direct_result = assess_purchase_decision_with_traits(
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
    assert wrapper_result == direct_result


def test_build_active_flip_debug_payload_rounds_optional_fields() -> None:
    payload = build_active_flip_debug_payload(
        ActiveFlipDebugPayload(
            policy="v3_gpt",
            candidate_scores={"1": 1.234},
            chosen_card=1,
            chosen_to="flip",
            reasons=["best"],
            generic_survival_score=1.234,
            money_distress=0.987,
            controller_need=0.456,
        )
    )

    assert payload["generic_survival_score"] == 1.234
    assert payload["money_distress"] == 0.987
    assert payload["controller_need"] == 0.456


def test_decide_character_choice_prefers_non_blocked_candidate_when_available() -> None:
    decision = decide_character_choice(
        [
            CharacterChoiceCandidate(key=1, score=10.0, reasons=("high",), hard_blocked=True),
            CharacterChoiceCandidate(key=2, score=5.0, reasons=("safe",), hard_blocked=False),
        ],
        tiebreak_desc=False,
    )

    assert decision.choice == 2
    assert decision.candidate_pool == (2,)


def test_decide_character_choice_uses_descending_tiebreak_for_names() -> None:
    decision = decide_character_choice(
        [
            CharacterChoiceCandidate(key="객주", score=3.0, reasons=("a",)),
            CharacterChoiceCandidate(key="교리 감독관", score=3.0, reasons=("b",)),
        ],
        tiebreak_desc=True,
    )

    assert decision.choice == max(["객주", "교리 감독관"])


def test_summarize_character_choice_debug_formats_scores_reasons_and_hard_blocks() -> None:
    evaluation = evaluate_character_choice(
        [1, 2],
        evaluator=lambda key: CharacterChoiceCandidate(
            key=key,
            score=3.5 if key == 1 else 2.0,
            reasons=("pick", str(key)),
            hard_blocked=(key == 2),
            hard_block_detail={"why": "blocked"} if key == 2 else None,
            metadata={"severity": {"weight": key}},
        ),
    )

    summary = summarize_character_choice_debug(
        [1, 2],
        evaluation,
        label_for_key=lambda key: f"card:{key}",
    )

    assert summary.score_map == {"card:1": 3.5, "card:2": 2.0}
    assert summary.reason_map["card:1"] == ["pick", "1"]
    assert summary.hard_blocked_map == {"card:2": {"why": "blocked"}}
    assert summary.metadata_map == {
        "card:1": {"severity": {"weight": 1}},
        "card:2": {"severity": {"weight": 2}},
    }


def test_build_policy_survival_context_wraps_cleanup_and_signal_fields() -> None:
    data = {
        "reserve": 3.0,
        "reserve_gap": 1.0,
        "money_distress": 1.1,
        "survival_urgency": 0.9,
        "latent_cleanup_cost": 5.0,
        "cleanup_pressure": 2.2,
        "cleanup_cash_gap": 2.5,
        "cash_after_reserve": -1.0,
        "own_burdens": 2.0,
        "expected_cleanup_cost": 6.0,
        "expected_cleanup_gap": 1.5,
        "downside_expected_cleanup_cost": 7.0,
        "worst_cleanup_cost": 10.0,
        "next_draw_negative_cleanup_prob": 0.2,
        "two_draw_negative_cleanup_prob": 0.3,
        "cycle_negative_cleanup_prob": 0.4,
        "recovery_score": 1.5,
        "rent_pressure": 1.4,
        "lethal_hit_prob": 0.1,
        "controller_need": 0.8,
        "own_burden_cost": 4.0,
        "public_cleanup_active": 1.0,
        "active_cleanup_cost": 6.0,
        "needs_income": 1.0,
        "cross_start": 0.25,
        "land_f": 0.5,
        "remaining_negative_cleanup_cards": 3.0,
    }

    ctx = build_policy_survival_context(data, cash=4, shards=5)

    assert ctx.reserve == 3.0
    assert ctx.survival_urgency == 0.9
    assert ctx.cleanup_pressure == 2.2
    assert ctx.reserve_gap == 1.0
    assert ctx.cleanup_cash_gap == 2.5
    assert ctx.downside_expected_cleanup_cost == 7.0
    assert ctx.worst_cleanup_cost == 10.0
    assert ctx.cycle_negative_cleanup_prob == 0.4
    assert ctx.public_cleanup_active is True
    assert ctx.active_cleanup_cost == 6.0
    assert ctx.needs_income is True
    assert ctx.cross_start == 0.25
    assert ctx.land_f == 0.5
    assert ctx.remaining_negative_cleanup_cards == 3.0
    assert ctx.cleanup_strategy.cleanup_stage in {"critical", "meltdown"}
    assert ctx.cleanup_strategy.shard_tier == "buffered"
    assert ctx.action_guard.reserve_floor >= 3.0


def test_apply_turn_plan_lap_bias_prefers_cash_under_critical_survival_plan() -> None:
    intent = PlayerIntentState(
        plan_key="survival_recovery",
        resource_intent="cash_first",
        reason="cleanup_window",
        source_character="source",
        plan_confidence=0.9,
        plan_start_round=4,
        expires_after_round=6,
    )
    plan_ctx = build_turn_plan_context(
        intent,
        _cleanup_context(cleanup_stage="critical"),
        current_character="current",
        cash=4,
        shards=5,
    )

    cash, shard, coin, preferred = apply_turn_plan_lap_bias(
        1.0,
        1.0,
        1.0,
        plan_ctx=plan_ctx,
        cross_start=0.3,
        is_lap_engine_character=False,
    )

    assert cash > shard
    assert cash > coin
    assert preferred == "cash"


def test_resolve_movement_choice_prefers_best_double_card_option() -> None:
    resolution = resolve_movement_choice(
        avg_no_cards=1.0,
        remaining_cards=(1, 4, 6),
        single_card_scorer=lambda card_value, die_roll: float(card_value + die_roll),
        double_card_scorer=lambda first, second: 20.0 if (first, second) == (4, 6) else float(first + second),
        leader_trigger_value=lambda best_outcome, baseline: 0.0,
    )

    assert resolution == MovementChoiceResolution(True, (4, 6), 20.0)


def test_apply_v2_profile_lap_reward_bias_aggressive_prefers_coins() -> None:
    cash, shard, coin, preferred = apply_v2_profile_lap_reward_bias(
        1.0,
        1.0,
        1.0,
        inputs=V2ProfileLapRewardInputs(
            profile="aggressive",
            cash=8,
            shards=3,
            hand_coins=1,
            placeable=False,
            buy_value=0.0,
            land_f=0.0,
            land_f_value=0.0,
            own_land=0.0,
            token_combo=0.0,
            token_window_score=0.0,
            token_window_placeable_count=0.0,
            token_window_nearest_distance=9.0,
            token_window_revisit_prob=0.0,
        ),
    )

    assert preferred is None
    assert coin > shard
    assert cash < shard


def test_apply_v2_profile_lap_reward_bias_control_prefers_cash_when_pressed() -> None:
    cash, shard, coin, preferred = apply_v2_profile_lap_reward_bias(
        1.0,
        1.0,
        1.0,
        inputs=V2ProfileLapRewardInputs(
            profile="control",
            cash=4,
            shards=3,
            hand_coins=1,
            placeable=True,
            buy_value=1.5,
            land_f=0.0,
            land_f_value=0.0,
            own_land=0.0,
            token_combo=0.0,
            token_window_score=0.0,
            token_window_placeable_count=0.0,
            token_window_nearest_distance=99.0,
            token_window_revisit_prob=0.0,
            emergency=2.5,
            finisher_window=0.0,
            low_cash=3.0,
            cash_after_reserve=-1.0,
            rent_pressure=2.1,
            burden_count=1.0,
            cleanup_pressure=2.4,
            solo_leader=True,
            near_end=True,
            is_controller_role=False,
        ),
    )

    assert preferred is None
    assert cash > coin
    assert shard > 1.0


def test_normalize_lap_reward_scores_respects_override_and_reward_units() -> None:
    cash_unit, shard_unit, coin_unit, preferred = normalize_lap_reward_scores(
        cash_score=6.0,
        shard_score=4.0,
        coin_score=9.0,
        lap_reward_cash=6.0,
        lap_reward_shards=4.0,
        lap_reward_coins=3.0,
        preferred_override="cash",
    )

    assert (cash_unit, shard_unit, coin_unit) == (1.0, 1.0, 3.0)
    assert preferred == "cash"


def test_filter_public_mark_candidates_removes_faster_priority_names() -> None:
    actor_name = CARD_TO_NAMES[6][0]
    actor_priority = CHARACTERS[actor_name].priority
    faster_name = next(name for name, meta in CHARACTERS.items() if meta.priority < actor_priority)
    legal_name = next(name for name, meta in CHARACTERS.items() if meta.priority >= actor_priority and name != actor_name)

    filtered = filter_public_mark_candidates(
        actor_name,
        [faster_name, legal_name],
        [faster_name, legal_name],
    )

    assert legal_name in filtered
    assert faster_name not in filtered


def test_build_public_mark_choice_debug_payload_formats_optional_fields() -> None:
    payload = build_public_mark_choice_debug_payload(
        PublicMarkChoiceDebug(
            policy="v3_gpt",
            actor_name="actor",
            candidate_scores={"a": 1.2},
            candidate_probabilities={"a": 0.7},
            chosen_target="a",
            top_candidate="a",
            uniform_mix=0.1254,
            ambiguity=0.2254,
            top_probability=0.7,
            second_probability=0.2,
            reasons=["best_guess"],
        )
    )

    assert payload["policy"] == "v3_gpt"
    assert payload["top_candidate"] == "a"
    assert payload["uniform_mix"] == 0.125
    assert payload["ambiguity"] == 0.225
    assert payload["top_probability"] == 0.7
    assert payload["second_probability"] == 0.2


def test_build_empty_public_mark_choice_debug_payload_sets_empty_maps() -> None:
    payload = build_empty_public_mark_choice_debug_payload(
        policy="v3_gpt",
        actor_name="actor",
        reason="no_legal_targets",
    )

    assert payload["candidate_scores"] == {}
    assert payload["candidate_probabilities"] == {}
    assert payload["reasons"] == ["no_legal_targets"]


def test_evaluate_public_mark_candidates_builds_scores_and_distribution() -> None:
    evaluation = evaluate_public_mark_candidates(
        ["a", "b"],
        legal_target_count=2,
        scorer=lambda name: (2.0, ["best"]) if name == "a" else (1.0, ["alt"]),
        distribution_builder=lambda scored, _: (
            {name: (0.7 if name == "a" else 0.3) for name in scored},
            {
                "top_probability": 0.7,
                "second_probability": 0.3,
                "uniform_mix": 0.1,
                "ambiguity": 0.2,
            },
        ),
    )

    assert evaluation.top_candidate == "a"
    assert evaluation.scored == {"a": 2.0, "b": 1.0}
    assert evaluation.probabilities == {"a": 0.7, "b": 0.3}
    assert evaluation.reasons["a"] == ["best"]


def test_resolve_public_mark_choice_returns_choice_and_debug_payload() -> None:
    resolution = resolve_public_mark_choice(
        ["a", "b"],
        policy="v3_gpt",
        actor_name="actor",
        legal_target_count=2,
        scorer=lambda name: (2.0, ["best"]) if name == "a" else (1.0, ["alt"]),
        distribution_builder=lambda scored, _: (
            {name: (0.7 if name == "a" else 0.3) for name in scored},
            {
                "top_probability": 0.7,
                "second_probability": 0.3,
                "uniform_mix": 0.1,
                "ambiguity": 0.2,
            },
        ),
        chooser=lambda options, _: options[0],
    )

    assert resolution.choice == "a"
    assert resolution.debug_payload["chosen_target"] == "a"
    assert resolution.debug_payload["top_candidate"] == "a"


def test_resolve_random_public_mark_choice_uses_uniform_distribution() -> None:
    resolution = resolve_random_public_mark_choice(
        ["a", "b"],
        policy="random",
        actor_name="actor",
        chooser=lambda options: options[1],
    )

    assert resolution.choice == "b"
    assert resolution.debug_payload["candidate_probabilities"] == {"a": 0.5, "b": 0.5}


def test_run_public_mark_choice_handles_empty_random_and_scored_paths() -> None:
    empty_run = run_public_mark_choice(
        [],
        policy="p",
        actor_name="actor",
        legal_target_count=0,
        is_random_mode=False,
        scorer=lambda _: (0.0, []),
        distribution_builder=lambda scores, legal_count: ({}, {"top_probability": 0.0, "second_probability": 0.0, "uniform_mix": 0.0, "ambiguity": 0.0}),
        chooser=lambda options, weights: options[0],
        random_chooser=lambda options: options[0],
    )
    random_run = run_public_mark_choice(
        ["a", "b"],
        policy="p",
        actor_name="actor",
        legal_target_count=2,
        is_random_mode=True,
        scorer=lambda _: (0.0, []),
        distribution_builder=lambda scores, legal_count: ({}, {"top_probability": 0.0, "second_probability": 0.0, "uniform_mix": 0.0, "ambiguity": 0.0}),
        chooser=lambda options, weights: options[0],
        random_chooser=lambda options: options[-1],
    )
    scored_run = run_public_mark_choice(
        ["a", "b"],
        policy="p",
        actor_name="actor",
        legal_target_count=2,
        is_random_mode=False,
        scorer=lambda name: (2.0 if name == "b" else 1.0, [name]),
        distribution_builder=lambda scores, legal_count: (
            {"a": 0.25, "b": 0.75},
            {"top_probability": 0.75, "second_probability": 0.25, "uniform_mix": 0.1, "ambiguity": 0.2},
        ),
        chooser=lambda options, weights: options[weights.index(max(weights))],
        random_chooser=lambda options: options[0],
    )

    assert empty_run.choice is None
    assert empty_run.debug_payload["reasons"] == ["no_legal_targets"]
    assert random_run.choice == "b"
    assert random_run.debug_payload["chosen_target"] == "b"
    assert scored_run.choice == "b"
    assert scored_run.debug_payload["top_candidate"] == "b"


def test_apply_movement_intent_adjustment_penalizes_gakju_two_card_generic_land_grab() -> None:
    intent = PlayerIntentState(
        plan_key="lap_engine",
        resource_intent="card_preserve",
        reason="gakju_online",
        source_character="객주",
        plan_confidence=0.9,
        plan_start_round=2,
        expires_after_round=4,
    )

    adjustment = apply_movement_intent_adjustment(
        current_character="객주",
        rounds_completed=1,
        cell_kind=CellKind.T2,
        owner=None,
        crosses_start=False,
        use_cards=True,
        card_count=2,
        intent=intent,
    )

    assert adjustment <= -7.5


def test_apply_trick_preserve_rules_blocks_relic_collector_without_window() -> None:
    intent = PlayerIntentState(
        plan_key="land_grab",
        resource_intent="card_preserve",
        reason="hold_cards",
        source_character="교리 감독관",
        plan_confidence=0.6,
        plan_start_round=1,
        expires_after_round=2,
    )

    adjustment = apply_trick_preserve_rules(
        card_name="성물 수집가",
        actor_name="교리 감독관",
        hand_names={"성물 수집가"},
        rounds_completed=0,
        strategic_mode=0.0,
        intent=intent,
        survival_urgency=0.0,
        cleanup_cash_gap=0.0,
        has_relic_collector_window=False,
        has_help_run_window=False,
        has_neojeol_chain_window=False,
        short_range_frontier_is_better=False,
    )

    assert adjustment <= -2.4


def test_build_purchase_reserve_floor_reflects_cleanup_and_income_pressure() -> None:
    survival = build_policy_survival_context(
        {
            "reserve": 3.0,
            "money_distress": 1.0,
            "survival_urgency": 0.8,
            "two_turn_lethal_prob": 0.2,
            "latent_cleanup_cost": 5.0,
            "expected_cleanup_cost": 4.0,
            "public_cleanup_active": 1.0,
        },
        cash=5,
        shards=4,
    )

    reserve_floor = build_purchase_reserve_floor(
        reserve=3.0,
        remaining_cash=4.0,
        survival=survival,
        public_cleanup_active=True,
        active_cleanup_cost=6.0,
        downside_expected_cleanup_cost=3.0,
        worst_cleanup_cost=8.0,
        latent_cleanup_cost=5.0,
        needs_income=True,
    )

    assert reserve_floor > 10.0


def test_build_purchase_benefit_accumulates_block_and_profile_pressure() -> None:
    benefit = build_purchase_benefit(
        PurchaseBenefitInputs(
            cell=CellKind.T3,
            profile="growth",
            complete_monopoly=False,
            blocks_enemy=False,
            owned_in_block=2,
        )
    )

    assert benefit == 0.8 + 1.4 + 0.9 + 0.35


def test_apply_v3_purchase_benefit_adjustments_exposes_veto_and_growth_flags() -> None:
    adjustment = apply_v3_purchase_benefit_adjustments(
        V3PurchaseBenefitInputs(
            cell=CellKind.T3,
            cost=3,
            remaining_cash=6.0,
            reserve=2.0,
            cleanup_pressure=1.0,
            money_distress=0.5,
            own_burdens=1.0,
            token_window_value=1.0,
            complete_monopoly=False,
            blocks_enemy=False,
            current_benefit=2.0,
            baksu_online=True,
            token_window_character=False,
        )
    )

    assert adjustment.safe_low_cost_t3 is True
    assert adjustment.safe_growth_buy is True
    assert adjustment.benefit > 2.0


def test_assess_v3_purchase_window_reuses_shared_flag_logic() -> None:
    survival = build_policy_survival_context(
        {
            "reserve": 2.0,
            "money_distress": 0.4,
            "cleanup_pressure": 1.2,
            "own_burdens": 1.0,
        },
        cash=8,
        shards=3,
    )

    assessment = assess_v3_purchase_window(
        current_character=None,
        shards=3,
        cell=CellKind.T3,
        cost=3,
        remaining_cash=6.0,
        reserve=2.0,
        survival=survival,
        token_window_value=1.0,
        benefit=2.0,
        complete_monopoly=False,
        blocks_enemy=False,
    )

    assert assessment.safe_low_cost_t3 is True


def test_assess_v3_purchase_window_exposes_online_baksu_exception() -> None:
    survival = build_policy_survival_context(
        {
            "reserve": 2.0,
            "money_distress": 0.5,
            "survival_urgency": 0.4,
            "cleanup_pressure": 1.2,
            "two_turn_lethal_prob": 0.05,
        },
        cash=8,
        shards=5,
    )

    assessment = assess_v3_purchase_window(
        current_character="박수",
        shards=5,
        cell=CellKind.T3,
        cost=3,
        remaining_cash=6.0,
        reserve=2.0,
        survival=survival,
        token_window_value=1.0,
        benefit=2.0,
        complete_monopoly=False,
        blocks_enemy=False,
    )

    assert assessment.baksu_online_exception is True
    assert assessment.safe_low_cost_t3 is True


def test_assess_purchase_decision_surfaces_cleanup_and_token_blocks() -> None:
    survival = build_policy_survival_context(
        {
            "reserve": 3.0,
            "money_distress": 1.2,
            "survival_urgency": 0.8,
            "cleanup_pressure": 2.2,
            "two_turn_lethal_prob": 0.3,
            "public_cleanup_active": 1.0,
            "active_cleanup_cost": 6.0,
            "latent_cleanup_cost": 7.0,
        },
        cash=7,
        shards=5,
    )
    purchase_window = assess_v3_purchase_window(
        current_character="è«›ëº¤ë‹”",
        shards=5,
        cell=CellKind.T3,
        cost=3,
        remaining_cash=4.0,
        reserve=3.0,
        survival=survival,
        token_window_value=4.5,
        benefit=1.2,
        complete_monopoly=False,
        blocks_enemy=False,
    )
    result = assess_purchase_decision(
        profile="v3_gpt",
        current_character="è«›ëº¤ë‹”",
        cash_before=7.0,
        remaining_cash=4.0,
        reserve=3.0,
        reserve_floor=purchase_window.reserve_floor,
        benefit=1.2,
        token_window_value=4.5,
        money_distress=1.2,
        complete_monopoly=False,
        blocks_enemy=False,
        hard_reason=None,
        own_burdens=1.0,
        next_neg=0.2,
        two_neg=0.3,
        negative_cards=2.0,
        downside_cleanup=7.0,
        worst_cleanup=10.0,
        public_cleanup_active=True,
        active_cleanup_cost=6.0,
        latent_cleanup_cost=7.0,
        purchase_window=purchase_window,
    )

    assert result.reserve_floor >= 3.0
    assert result.shortfall >= 0.0
    assert isinstance(result.token_preferred, bool)
    assert isinstance(result.cleanup_lock, bool)


def test_build_purchase_debug_payload_uses_context_and_result_fields() -> None:
    payload = build_purchase_debug_payload(
        context=PurchaseDebugContext(
            source="landing",
            pos=12,
            cell_name="T3",
            cost=3,
            cash_before=10.0,
            cash_after=7.0,
            reserve=4.5,
            money_distress=1.2,
            two_turn_lethal_prob=0.3,
            latent_cleanup_cost=5.0,
            cleanup_cash_gap=2.0,
            expected_loss=1.5,
            worst_loss=4.0,
            blocks_enemy_monopoly=True,
            token_window_value=3.75,
        ),
        result=assess_purchase_decision(
            profile="v3_gpt",
            current_character=None,
            cash_before=10.0,
            remaining_cash=7.0,
            reserve=4.5,
            reserve_floor=5.0,
            benefit=2.0,
            token_window_value=1.0,
            money_distress=0.2,
            complete_monopoly=False,
            blocks_enemy=True,
            hard_reason=None,
            own_burdens=0.0,
            next_neg=0.0,
            two_neg=0.0,
            negative_cards=0.0,
            downside_cleanup=0.0,
            worst_cleanup=0.0,
            public_cleanup_active=False,
            active_cleanup_cost=0.0,
            latent_cleanup_cost=0.0,
            purchase_window=None,
        ),
    )

    assert payload["source"] == "landing"
    assert payload["pos"] == 12
    assert payload["cell"] == "T3"
    assert payload["blocks_enemy_monopoly"] is True
    assert payload["token_window_value"] == 3.75
    assert isinstance(payload["decision"], bool)


def test_choose_doctrine_relief_player_id_prefers_self_then_first() -> None:
    assert choose_doctrine_relief_player_id(self_player_id=2, candidate_ids=[1, 2, 3]) == 2
    assert choose_doctrine_relief_player_id(self_player_id=4, candidate_ids=[1, 2, 3]) == 1
    assert choose_doctrine_relief_player_id(self_player_id=4, candidate_ids=[]) is None


def test_choose_doctrine_relief_player_from_inputs_prefers_most_distressed_candidate() -> None:
    choice = choose_doctrine_relief_player_from_inputs(
        [
            DoctrineReliefCandidateInputs(
                player_id=1,
                cash=10.0,
                burden_count=0.0,
                cleanup_pressure=0.5,
                money_distress=0.1,
                two_turn_lethal_prob=0.0,
                own_burden_cost=0.0,
                is_self=True,
            ),
            DoctrineReliefCandidateInputs(
                player_id=2,
                cash=4.0,
                burden_count=2.0,
                cleanup_pressure=2.8,
                money_distress=1.1,
                two_turn_lethal_prob=0.3,
                own_burden_cost=5.0,
                is_self=False,
            ),
        ]
    )
    assert choice == 2


def test_should_exchange_burden_on_supply_applies_floor_and_hard_guard() -> None:
    assert should_exchange_burden_on_supply(
        BurdenExchangeDecisionInputs(
            remaining_cash=9.0,
            reserve=4.0,
            target_floor=8.0,
            hard_reason=None,
        )
    ) is True
    assert should_exchange_burden_on_supply(
        BurdenExchangeDecisionInputs(
            remaining_cash=4.0,
            reserve=4.0,
            target_floor=8.0,
            hard_reason=None,
        )
    ) is False
    assert should_exchange_burden_on_supply(
        BurdenExchangeDecisionInputs(
            remaining_cash=10.0,
            reserve=4.0,
            target_floor=8.0,
            hard_reason="cleanup_guard",
        )
    ) is False


def test_choose_geo_bonus_kind_prefers_cash_under_cleanup_pressure() -> None:
    assert choose_geo_bonus_kind(
        GeoBonusDecisionInputs(
            own_burdens=2.0,
            next_neg=0.10,
            two_neg=0.22,
            cleanup_cash_gap=1.0,
            downside_cleanup=7.0,
            cash=8.0,
            cash_score=4.0,
            shard_score=3.0,
            coin_score=2.0,
        )
    ) == "cash"


def test_choose_geo_bonus_kind_returns_highest_scored_bonus_when_safe() -> None:
    assert choose_geo_bonus_kind(
        GeoBonusDecisionInputs(
            own_burdens=0.0,
            next_neg=0.0,
            two_neg=0.0,
            cleanup_cash_gap=0.0,
            downside_cleanup=0.0,
            cash=12.0,
            cash_score=2.0,
            shard_score=3.5,
            coin_score=3.0,
        )
    ) == "shards"


def test_should_seek_escape_package_from_inputs_matches_distress_thresholds() -> None:
    assert should_seek_escape_package_from_inputs(
        EscapeSeekInputs(
            burden_count=1.0,
            cleanup_pressure=1.0,
            rent_pressure=0.0,
            money_distress=1.2,
            two_turn_lethal_prob=0.0,
            cash_after_reserve=1.0,
            front_enemy_density=0.2,
            controller_need=0.0,
            active_drain_pressure=0.0,
            cash=9.0,
        )
    ) is True
    assert should_seek_escape_package_from_inputs(
        EscapeSeekInputs(
            burden_count=0.0,
            cleanup_pressure=1.0,
            rent_pressure=0.0,
            money_distress=0.2,
            two_turn_lethal_prob=0.0,
            cash_after_reserve=2.0,
            front_enemy_density=0.2,
            controller_need=0.0,
            active_drain_pressure=0.0,
            cash=12.0,
        )
    ) is False


def test_build_distress_marker_bonus_prefers_marker_when_escape_pressure_is_live() -> None:
    bonus = build_distress_marker_bonus(
        DistressMarkerInputs(
            rescue_pressure=True,
            urgent_denial=False,
            leader_emergency=0.0,
            controller_need=0.0,
            money_distress=0.6,
            future_rescue_live=True,
            marker_counter=0.0,
            near_end=False,
            marker_owner_id=2,
            player_id=1,
            candidate_names=("marker", "other"),
            marker_names=frozenset({"marker"}),
            rescue_names=frozenset({"escape"}),
            direct_denial_names=frozenset(),
        )
    )

    assert bonus["marker"] > 2.0
    assert bonus["other"] == 0.0


def test_count_burden_cards_counts_visible_burdens() -> None:
    cards = [
        SimpleNamespace(is_burden=True),
        SimpleNamespace(is_burden=False),
        SimpleNamespace(is_burden=True),
    ]

    assert count_burden_cards(cards) == 2


def test_evaluate_character_choice_collects_scores_and_hard_blocks() -> None:
    evaluation = evaluate_character_choice(
        [1, 2],
        evaluator=lambda key: CharacterChoiceCandidate(
            key=key,
            score=float(key),
            reasons=(f"score={key}",),
            hard_blocked=(key == 2),
            hard_block_detail={"reason": "blocked"} if key == 2 else None,
        ),
        tiebreak_desc=False,
    )

    assert evaluation.decision.choice == 1
    assert evaluation.scores == {1: 1.0, 2: 2.0}
    assert evaluation.reasons[1] == ("score=1",)
    assert evaluation.hard_blocked_keys == (2,)
    assert evaluation.hard_block_details[2]["reason"] == "blocked"


def test_evaluate_named_character_choice_applies_marker_and_survival_adjustments() -> None:
    evaluation = evaluate_named_character_choice(
        [1, 2],
        resolve_name=lambda key: {1: "A", 2: "B"}[key],
        base_breakdown=lambda name: (1.0 if name == "A" else 2.0, [f"base={name}"]),
        survival_policy_advice=lambda name: (0.5 if name == "A" else 0.0, ["policy_bonus"] if name == "A" else [], False, {}),
        survival_adjustment=lambda name: (0.25 if name == "A" else 0.0, ["survival_bonus"] if name == "A" else []),
        marker_bonus_by_name={"A": 1.0},
        weighted_marker_names={"A"},
        survival_first=True,
        weight_multiplier=2.0,
        tiebreak_desc=False,
    )

    assert evaluation.decision.choice == 1
    assert evaluation.scores[1] == 3.75
    assert "distress_marker_bonus=2.00" in evaluation.reasons[1]


def test_evaluate_named_character_choice_with_policy_matches_direct_path() -> None:
    policy = NamedCharacterChoicePolicy(
        resolve_name=lambda key: {1: "A", 2: "B"}[key],
        base_breakdown=lambda name: (3.0 if name == "A" else 1.0, [f"base:{name}"]),
        survival_policy_advice=lambda name: (2.0 if name == "A" else 0.0, ["survival"], False, {"sev": name}),
        survival_adjustment=lambda name: (1.0 if name == "B" else 0.0, ["adjust"]),
        marker_bonus_by_name={"A": 0.5, "B": 0.0},
        weighted_marker_names={"A"},
        survival_first=True,
        weight_multiplier=2.0,
    )

    evaluation = evaluate_named_character_choice_with_policy(
        [1, 2],
        policy=policy,
        tiebreak_desc=False,
    )

    assert evaluation.decision.choice == 1
    assert round(evaluation.scores[1], 2) == 6.0
    assert round(evaluation.scores[2], 2) == 2.0
    assert evaluation.metadata[1]["survival_severity"]["sev"] == "A"


def test_build_named_character_choice_policy_preserves_configuration() -> None:
    policy = build_named_character_choice_policy(
        resolve_name=lambda key: {1: "A", 2: "B"}[key],
        base_breakdown=lambda name: (1.0, [name]),
        survival_policy_advice=lambda name: (0.0, [], False, {}),
        survival_adjustment=lambda name: (0.0, []),
        marker_bonus_by_name={"A": 1.5},
        weighted_marker_names={"A"},
        survival_first=True,
        weight_multiplier=1.8,
    )

    assert isinstance(policy, NamedCharacterChoicePolicy)
    assert policy.resolve_name(1) == "A"
    assert policy.marker_bonus_by_name["A"] == 1.5
    assert policy.weighted_marker_names == {"A"}
    assert policy.survival_first is True
    assert policy.weight_multiplier == 1.8


def test_run_named_character_choice_with_policy_returns_choice_and_debug_summary() -> None:
    policy = build_named_character_choice_policy(
        resolve_name=lambda key: {1: "A", 2: "B"}[key],
        base_breakdown=lambda name: (2.0 if name == "A" else 1.0, [f"base:{name}"]),
        survival_policy_advice=lambda name: (0.5 if name == "A" else 0.0, ["policy"], False, {"sev": name}),
        survival_adjustment=lambda name: (0.25 if name == "A" else 0.0, ["adjust"] if name == "A" else []),
        marker_bonus_by_name={"A": 1.0},
        weighted_marker_names={"A"},
        survival_first=True,
        weight_multiplier=2.0,
    )

    run = run_named_character_choice_with_policy(
        [1, 2],
        policy=policy,
        label_for_key=lambda key: f"card:{key}",
        tiebreak_desc=False,
    )

    assert run.choice == 1
    assert run.debug_summary.score_map["card:1"] > run.debug_summary.score_map["card:2"]
    assert "distress_marker_bonus=2.00" in run.debug_summary.reason_map["card:1"]


def test_run_scored_choice_returns_best_option_and_score_map() -> None:
    run = run_scored_choice(
        ["a", "b", "c"],
        scorer=lambda value: {"a": 1.0, "b": 3.0, "c": 2.0}[value],
        label_for_option=lambda value: value,
    )

    assert run.choice == "b"
    assert run.score_map == {"a": 1.0, "b": 3.0, "c": 2.0}


def test_run_scored_choice_respects_minimum_score() -> None:
    run = run_scored_choice(
        ["a", "b"],
        scorer=lambda value: {"a": -1.0, "b": 0.0}[value],
        label_for_option=lambda value: value,
        minimum_score=0.0,
    )

    assert run.choice is None
    assert run.score_map == {"a": -1.0, "b": 0.0}


def test_run_ranked_choice_returns_best_option() -> None:
    run = run_ranked_choice(
        ["a", "b", "c"],
        ranker=lambda value: {"a": (1, 0), "b": (3, 0), "c": (2, 1)}[value],
    )

    assert run.choice == "b"


def test_evaluate_v1_character_structural_rules_captures_expansion_and_monopoly_routes() -> None:
    score, reasons = evaluate_v1_character_structural_rules(
        "중매꾼",
        V1CharacterStructuralInputs(
            low_cash=False,
            very_low_cash=False,
            shards=2,
            near_unowned=2,
            enemy_tiles=5,
            own_near_complete=1.0,
            own_claimable_blocks=2.0,
            enemy_near_complete=0.0,
            contested_blocks=0.0,
            matchmaker_adjacent_value=1.5,
            builder_free_purchase_value=0.0,
            scammer_coin_value=0.0,
            scammer_best_tile_coins=0.0,
            scammer_blocks_enemy_monopoly=0.0,
            scammer_finishes_own_monopoly=0.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            mobility_leverage=0.0,
        ),
    )

    assert round(score, 2) == round((1.10 + 1.5) + (2.05 * 1.0 + 0.55 * 2.0 + 0.30 * 1.5), 2)
    assert "near_unowned_expansion" in reasons
    assert "monopoly_finish_value" in reasons


def test_evaluate_v1_character_structural_rules_captures_swindler_and_clerk_pressure() -> None:
    swindler_score, swindler_reasons = evaluate_v1_character_structural_rules(
        "사기꾼",
        V1CharacterStructuralInputs(
            low_cash=False,
            very_low_cash=False,
            shards=1,
            near_unowned=1,
            enemy_tiles=4,
            own_near_complete=0.0,
            own_claimable_blocks=0.0,
            enemy_near_complete=1.0,
            contested_blocks=2.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
            scammer_coin_value=2.0,
            scammer_best_tile_coins=3.0,
            scammer_blocks_enemy_monopoly=1.0,
            scammer_finishes_own_monopoly=1.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            mobility_leverage=0.0,
        ),
    )
    clerk_score, clerk_reasons = evaluate_v1_character_structural_rules(
        "아전",
        V1CharacterStructuralInputs(
            low_cash=True,
            very_low_cash=True,
            shards=4,
            near_unowned=0,
            enemy_tiles=0,
            own_near_complete=0.0,
            own_claimable_blocks=0.0,
            enemy_near_complete=0.0,
            contested_blocks=0.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
            scammer_coin_value=0.0,
            scammer_best_tile_coins=0.0,
            scammer_blocks_enemy_monopoly=0.0,
            scammer_finishes_own_monopoly=0.0,
            max_enemy_stack=2.0,
            max_enemy_owned_stack=1.0,
            mobility_leverage=1.5,
        ),
    )

    assert swindler_score > 0.0
    assert "enemy_board_pressure" in swindler_reasons
    assert "takeover_coin_swing" in swindler_reasons
    assert "deny_enemy_monopoly" in swindler_reasons
    assert clerk_score > 0.0
    assert "low_cash_economy" in clerk_reasons
    assert "very_low_cash_recovery" in clerk_reasons
    assert "shard_synergy" in clerk_reasons
    assert "stacked_enemy_burst_window" in clerk_reasons


def test_evaluate_v1_character_structural_rules_captures_lap_cleanup_and_control_signals() -> None:
    score, reasons = evaluate_v1_character_structural_rules(
        "객주",
        V1CharacterStructuralInputs(
            low_cash=True,
            very_low_cash=False,
            shards=5,
            near_unowned=0,
            enemy_tiles=0,
            own_near_complete=0.0,
            own_claimable_blocks=2.0,
            enemy_near_complete=0.0,
            contested_blocks=0.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
            scammer_coin_value=0.0,
            scammer_best_tile_coins=0.0,
            scammer_blocks_enemy_monopoly=0.0,
            scammer_finishes_own_monopoly=0.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            mobility_leverage=0.0,
            own_tile_income=2.0,
            lap_fast_window=1.0,
            lap_mobility=1.0,
            lap_rich_pool=1.0,
            lap_double_lap_threat=1.0,
            own_burden=0.0,
            cleanup_pressure=0.0,
            legal_visible_burden_total=0.0,
            legal_visible_burden_peak=0.0,
            legal_low_cash_targets=0.0,
            has_mark_targets=True,
            failed_mark_removed_small=0.0,
            failed_mark_removed_large=0.0,
            failed_mark_payout_small=0.0,
            failed_mark_payout_large=0.0,
            reachable_specials_with_one_short=0,
            marker_owner_is_self=True,
            uroe_blocked=False,
        ),
    )

    assert score > 0.0
    assert "low_cash_economy" in reasons
    assert "own_tile_coin_engine" in reasons
    assert "lap_engine_window" in reasons

    baksu_score, baksu_reasons = evaluate_v1_character_structural_rules(
        "박수",
        V1CharacterStructuralInputs(
            low_cash=False,
            very_low_cash=False,
            shards=2,
            near_unowned=0,
            enemy_tiles=0,
            own_near_complete=0.0,
            own_claimable_blocks=0.0,
            enemy_near_complete=0.0,
            contested_blocks=0.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
            scammer_coin_value=0.0,
            scammer_best_tile_coins=0.0,
            scammer_blocks_enemy_monopoly=0.0,
            scammer_finishes_own_monopoly=0.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            mobility_leverage=0.0,
            own_tile_income=0.0,
            lap_fast_window=0.0,
            lap_mobility=0.0,
            lap_rich_pool=0.0,
            lap_double_lap_threat=0.0,
            own_burden=2.0,
            cleanup_pressure=3.0,
            legal_visible_burden_total=0.0,
            legal_visible_burden_peak=0.0,
            legal_low_cash_targets=1.0,
            has_mark_targets=True,
            failed_mark_removed_small=1.0,
            failed_mark_removed_large=0.0,
            failed_mark_payout_small=4.0,
            failed_mark_payout_large=0.0,
            reachable_specials_with_one_short=0,
            marker_owner_is_self=True,
            uroe_blocked=False,
        ),
    )
    cleaner_score, cleaner_reasons = evaluate_v1_character_structural_rules(
        "만신",
        V1CharacterStructuralInputs(
            low_cash=False,
            very_low_cash=False,
            shards=2,
            near_unowned=0,
            enemy_tiles=0,
            own_near_complete=0.0,
            own_claimable_blocks=0.0,
            enemy_near_complete=0.0,
            contested_blocks=0.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
            scammer_coin_value=0.0,
            scammer_best_tile_coins=0.0,
            scammer_blocks_enemy_monopoly=0.0,
            scammer_finishes_own_monopoly=0.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            mobility_leverage=0.0,
            own_tile_income=0.0,
            lap_fast_window=0.0,
            lap_mobility=0.0,
            lap_rich_pool=0.0,
            lap_double_lap_threat=0.0,
            own_burden=0.0,
            cleanup_pressure=3.0,
            legal_visible_burden_total=2.0,
            legal_visible_burden_peak=1.0,
            legal_low_cash_targets=1.0,
            has_mark_targets=True,
            failed_mark_removed_small=0.0,
            failed_mark_removed_large=1.0,
            failed_mark_payout_small=0.0,
            failed_mark_payout_large=6.0,
            reachable_specials_with_one_short=0,
            marker_owner_is_self=False,
            uroe_blocked=False,
        ),
    )

    assert baksu_score > 0.0
    assert "future_burden_escape" in baksu_reasons
    assert "burden_dump_fragile_target" in baksu_reasons
    assert cleaner_score > 0.0
    assert "public_burden_cleanup" in cleaner_reasons
    assert "cash_fragile_cleanup" in cleaner_reasons


def test_policy_factory_creates_heuristic_and_arena_policies_from_assets() -> None:
    heuristic = PolicyFactory.create_heuristic_policy(
        HeuristicPolicyAsset(
            character_policy_mode="heuristic_v3_gpt",
            lap_policy_mode="heuristic_v3_gpt",
            player_lap_policy_modes={1: "heuristic_v2_control"},
        ),
        rng=None,
    )
    arena = PolicyFactory.create_arena_policy(
        ArenaPolicyAsset(
            player_character_policy_modes={1: "heuristic_v1", 2: "heuristic_v2_control"},
            player_lap_policy_modes={2: "heuristic_v3_gpt"},
        ),
        rng=None,
    )

    assert heuristic.character_policy_mode == "heuristic_v3_gpt"
    assert heuristic.lap_policy_mode == "heuristic_v3_gpt"
    assert heuristic.player_lap_policy_modes[1] == "heuristic_v2_control"
    assert arena.player_character_policy_modes[1] == "heuristic_v1"
    assert arena.player_lap_policy_modes[2] == "heuristic_v3_gpt"


def test_policy_factory_normalize_arena_asset_fills_defaults_and_canonical_modes() -> None:
    asset = PolicyFactory.normalize_arena_asset(
        ArenaPolicyAsset(
            player_character_policy_modes={2: "control"},
            player_lap_policy_modes={4: "v3_gpt"},
        )
    )

    assert asset.player_character_policy_modes[1] == "heuristic_v1"
    assert asset.player_character_policy_modes[2] == "heuristic_v2_control"
    assert asset.player_character_policy_modes[3] == "heuristic_v2_control"
    assert asset.player_character_policy_modes[4] == "heuristic_v2_balanced"
    assert asset.player_lap_policy_modes[2] == "heuristic_v2_control"
    assert asset.player_lap_policy_modes[4] == "heuristic_v3_gpt"


def test_policy_factory_normalize_heuristic_asset_canonicalizes_modes() -> None:
    asset = PolicyFactory.normalize_heuristic_asset(
        HeuristicPolicyAsset(
            character_policy_mode="control",
            lap_policy_mode="v3_gpt",
            player_lap_policy_modes={3: "token_opt"},
        )
    )

    assert asset.character_policy_mode == "heuristic_v2_control"
    assert asset.lap_policy_mode == "heuristic_v3_gpt"
    assert asset.player_lap_policy_modes == {3: "heuristic_v2_token_opt"}


def test_policy_factory_create_heuristic_policy_from_modes_uses_normalized_asset() -> None:
    policy = PolicyFactory.create_heuristic_policy_from_modes(
        character_policy_mode="control",
        lap_policy_mode="v3_gpt",
        player_lap_policy_modes={2: "token_opt"},
        rng=None,
    )

    assert policy.character_policy_mode == "heuristic_v2_control"
    assert policy.lap_policy_mode == "heuristic_v3_gpt"
    assert policy.player_lap_policy_modes == {2: "heuristic_v2_token_opt"}


def test_policy_factory_create_runtime_policy_dispatches_arena_and_heuristic_paths() -> None:
    heuristic = PolicyFactory.create_runtime_policy(
        policy_mode="control",
        lap_policy_mode="v3_gpt",
        player_lap_policy_modes={2: "token_opt"},
        rng=None,
    )
    arena = PolicyFactory.create_runtime_policy(
        policy_mode="arena",
        player_character_policy_modes={1: "control"},
        player_lap_policy_modes={4: "v3_gpt"},
        rng=None,
    )

    assert heuristic.character_policy_mode == "heuristic_v2_control"
    assert heuristic.player_lap_policy_modes == {2: "heuristic_v2_token_opt"}
    assert arena.player_character_policy_modes[1] == "heuristic_v2_control"
    assert arena.player_lap_policy_modes[4] == "heuristic_v3_gpt"


def test_policy_factory_multi_agent_battle_asset_fills_defaults() -> None:
    asset = PolicyFactory.normalize_multi_agent_battle_asset(
        MultiAgentBattleAsset(
            player_specs={1: "claude:v3_claude", 3: "gpt:v3_gpt"},
        )
    )

    assert asset.player_specs[1] == "claude:v3_claude"
    assert asset.player_specs[2] == "gpt:v3_gpt"
    assert asset.player_specs[3] == "gpt:v3_gpt"
    assert asset.player_specs[4] == "gpt:v3_gpt"


def test_policy_factory_create_multi_agent_dispatcher_uses_normalized_specs() -> None:
    dispatcher = PolicyFactory.create_multi_agent_dispatcher(
        MultiAgentBattleAsset(
            player_specs={1: "claude:v3_claude", 2: "gpt:v3_gpt"},
        )
    )

    assert dispatcher.character_policy_mode == "multi_agent"
    assert dispatcher.agent_id_for_player(1).startswith("claude:")
    assert dispatcher.agent_id_for_player(2).startswith("gpt:")
    assert dispatcher.agent_id_for_player(3).startswith("gpt:")


def test_evaluate_v2_expansion_rules_captures_safe_growth_and_leader_denial() -> None:
    expansion, disruption, combo, reasons = evaluate_v2_expansion_rules(
        "중매꾼",
        V2ExpansionInputs(
            buy_value=2.0,
            cleanup_pressure=1.0,
            cash_after_reserve=2.0,
            near_unowned=3.0,
            shards=1,
            enemy_tiles=4,
            leader_pressure=2.0,
            top_threat_tiles_owned=6,
            top_threat_is_expansion=True,
            top_threat_present=True,
            land_f=0.0,
            exclusive_blocks=0,
            scammer_coin_value=0.0,
            scammer_best_tile_coins=0.0,
            matchmaker_adjacent_value=1.5,
            builder_free_purchase_value=0.0,
            combo_has_expansion_trick=True,
            combo_has_arrival_takeover_trick=False,
        ),
        profile="v3_gpt",
    )

    assert expansion > 0.0
    assert disruption > 0.0
    assert combo > 0.0
    assert "v3_safe_expansion_window" in reasons
    assert "v3_safe_growth_convert" in reasons
    assert "deny_leader_expansion" in reasons
    assert "expansion_trick_combo" in reasons


def test_evaluate_v2_expansion_rules_captures_swindler_takeover_lines() -> None:
    expansion, disruption, combo, reasons = evaluate_v2_expansion_rules(
        "사기꾼",
        V2ExpansionInputs(
            buy_value=1.0,
            cleanup_pressure=1.4,
            cash_after_reserve=0.0,
            near_unowned=1.0,
            shards=1,
            enemy_tiles=5,
            leader_pressure=1.5,
            top_threat_tiles_owned=4,
            top_threat_is_expansion=False,
            top_threat_present=True,
            land_f=0.2,
            exclusive_blocks=2,
            scammer_coin_value=2.0,
            scammer_best_tile_coins=3.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
            combo_has_expansion_trick=False,
            combo_has_arrival_takeover_trick=True,
        ),
        profile="v3_gpt",
    )

    assert expansion > 0.0
    assert disruption > 0.0
    assert combo > 0.0
    assert "v3_safe_takeover_window" in reasons
    assert "deny_leader_takeover_lines" in reasons
    assert "arrival_takeover_combo" in reasons
    assert "monopoly_blocks_takeover" in reasons
    assert "takeover_coin_swing" in reasons


def test_evaluate_v2_route_rules_captures_route_and_escape_biases() -> None:
    expansion, economy, disruption, survival, reasons = evaluate_v2_route_rules(
        "중매꾼",
        V2RouteInputs(
            cash=12,
            placeable=False,
            own_near_complete=1.0,
            own_claimable_blocks=2.0,
            enemy_near_complete=0.0,
            contested_blocks=0.0,
            deny_now=0.0,
            matchmaker_adjacent_value=1.5,
            builder_free_purchase_value=0.0,
        ),
    )
    _, runner_economy, _, runner_survival, runner_reasons = evaluate_v2_route_rules(
        "파발꾼",
        V2RouteInputs(
            cash=10,
            placeable=True,
            own_near_complete=0.0,
            own_claimable_blocks=2.0,
            enemy_near_complete=1.0,
            contested_blocks=1.0,
            deny_now=2.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
        ),
    )
    _, _, swindler_disruption, _, swindler_reasons = evaluate_v2_route_rules(
        "사기꾼",
        V2RouteInputs(
            cash=9,
            placeable=False,
            own_near_complete=0.0,
            own_claimable_blocks=0.0,
            enemy_near_complete=2.0,
            contested_blocks=3.0,
            deny_now=1.0,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
        ),
    )

    assert expansion > 0.0
    assert economy > 0.0
    assert "monopoly_finish_value" in reasons
    assert "monopoly_route_value" in reasons
    assert runner_economy > 0.0
    assert runner_survival > 0.0
    assert "monopoly_danger_escape" in runner_reasons
    assert swindler_disruption > 0.0
    assert "preempt_monopoly_takeover" in swindler_reasons


def test_evaluate_v2_profile_rules_captures_control_and_token_paths() -> None:
    expansion, economy, disruption, survival, combo, reasons = evaluate_v2_profile_rules(
        "사기꾼",
        V2ProfileInputs(
            profile="control",
            leading=False,
            has_marks=True,
            leader_emergency=2.0,
            leader_is_solo=True,
            leader_near_end=True,
            top_threat_present=True,
            leader_pressure=3.0,
            buy_value=2.0,
            finisher_window=1.5,
            finisher_reason="mono",
            cross_start=0.3,
            land_f=0.2,
            land_f_value=1.2,
            own_land=0.4,
            token_combo=1.0,
            placeable=True,
            matchmaker_adjacent_value=1.0,
            builder_free_purchase_value=1.0,
        ),
    )

    assert disruption > 0.0
    assert combo > 0.0
    assert "control_efficient_denial" in reasons
    assert "control_endgame_lock" in reasons
    assert "control_finisher_window=mono" in reasons

    _, token_economy, token_disruption, _, token_combo_value, token_reasons = evaluate_v2_profile_rules(
        "객주",
        V2ProfileInputs(
            profile="token_opt",
            leading=False,
            has_marks=False,
            leader_emergency=0.0,
            leader_is_solo=False,
            leader_near_end=False,
            top_threat_present=True,
            leader_pressure=3.0,
            buy_value=1.0,
            finisher_window=0.0,
            finisher_reason="",
            cross_start=0.5,
            land_f=0.5,
            land_f_value=2.0,
            own_land=0.6,
            token_combo=1.2,
            placeable=True,
            matchmaker_adjacent_value=0.0,
            builder_free_purchase_value=0.0,
        ),
    )

    assert token_economy > 0.0
    assert token_combo_value > 0.0
    assert token_disruption == 0.0
    assert "token_route_mobility" in token_reasons
    assert "own_tile_token_arrival" in token_reasons
    assert "token_placeable_pressure" in token_reasons


def test_evaluate_v2_tactical_rules_captures_marker_and_cleanup_pressure() -> None:
    expansion, economy, disruption, meta, combo, survival, reasons = evaluate_v2_tactical_rules(
        "교리 감독관",
        V2TacticalInputs(
            profile="v3_gpt",
            buy_value=1.0,
            cross_start=0.0,
            land_f=0.0,
            land_f_value=0.0,
            player_shards=5,
            burden_count=1.0,
            cleanup_pressure=2.0,
            legal_visible_burden_total=2.0,
            legal_visible_burden_peak=1.0,
            legal_low_cash_targets=1.0,
            has_marks=True,
            leader_pressure=3.0,
            top_threat_present=True,
            top_threat_tiles_owned=6,
            top_threat_cash=12,
            top_threat_cross=0.5,
            top_threat_land_f=0.3,
            top_threat_is_expansion_geo_combo=True,
            top_threat_is_burden=False,
            top_threat_is_shard_attack_counter_target=False,
            land_race_pressure=0.0,
            premium_unowned=0.0,
            near_unowned=0.0,
            behind_tiles=0.0,
            early_round=0.0,
            visited_owned_tile_count=2,
            lap_fast_window=0.0,
            lap_rich_pool=0.0,
            lap_double_lap_threat=0.0,
            mobility_leverage=0.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            reachable_specials_with_one_short=0,
            combo_has_speed_tricks=False,
            combo_has_lap_combo_tricks=False,
            combo_has_relic_collector=False,
            cleanup_growth_locked=False,
            cleanup_stage_score=2.0,
            cleanup_controller_bias=1.5,
            marker_plan_best_score=1.2,
            own_burden_cost=0.0,
        ),
    )

    assert expansion == 0.0
    assert economy == 0.0
    assert disruption > 0.0
    assert meta > 0.0
    assert combo == 0.0
    assert survival > 0.0
    assert "flip_meta_denial" in reasons
    assert "marker_strips_needed_leader_face" in reasons
    assert "cleanup_controller_window" in reasons


def test_evaluate_v2_tactical_rules_captures_innkeeper_engine_and_growth_lock() -> None:
    expansion, economy, disruption, meta, combo, survival, reasons = evaluate_v2_tactical_rules(
        "객주",
        V2TacticalInputs(
            profile="v3_gpt",
            buy_value=1.0,
            cross_start=0.6,
            land_f=0.4,
            land_f_value=1.5,
            player_shards=4,
            burden_count=0.0,
            cleanup_pressure=1.0,
            legal_visible_burden_total=0.0,
            legal_visible_burden_peak=0.0,
            legal_low_cash_targets=0.0,
            has_marks=False,
            leader_pressure=2.0,
            top_threat_present=True,
            top_threat_tiles_owned=5,
            top_threat_cash=10,
            top_threat_cross=0.5,
            top_threat_land_f=0.3,
            top_threat_is_expansion_geo_combo=True,
            top_threat_is_burden=False,
            top_threat_is_shard_attack_counter_target=False,
            land_race_pressure=0.0,
            premium_unowned=0.0,
            near_unowned=0.0,
            behind_tiles=0.0,
            early_round=0.0,
            visited_owned_tile_count=3,
            lap_fast_window=1.0,
            lap_rich_pool=0.8,
            lap_double_lap_threat=0.7,
            mobility_leverage=1.0,
            max_enemy_stack=0.0,
            max_enemy_owned_stack=0.0,
            reachable_specials_with_one_short=0,
            combo_has_speed_tricks=False,
            combo_has_lap_combo_tricks=True,
            combo_has_relic_collector=False,
            cleanup_growth_locked=True,
            cleanup_stage_score=2.0,
            cleanup_controller_bias=0.0,
            marker_plan_best_score=0.0,
            own_burden_cost=2.0,
        ),
    )

    assert expansion == 0.0
    assert economy > 0.0
    assert disruption > 0.0
    assert meta == 0.0
    assert combo > 0.0
    assert survival > 0.0
    assert "v3_lap_engine_convert_window" in reasons
    assert "deny_leader_lap_engine" in reasons
    assert "lap_token_combo" in reasons
    assert "cleanup_growth_lock" in reasons
    assert "burden_liquidity_cover" in reasons


def test_evaluate_v2_emergency_risk_rules_captures_cash_drag_for_innkeeper() -> None:
    expansion, economy, disruption, survival, reasons = evaluate_v2_emergency_risk_rules(
        "객주",
        V2EmergencyRiskInputs(
            profile="control",
            leader_emergency=2.0,
            leader_is_solo=True,
            leader_near_end=True,
            reserve_gap=1.5,
            expected_loss=3.0,
            worst_loss=5.0,
            own_burden_cost=2.0,
            player_shards=4,
        ),
    )

    assert expansion < 0.0
    assert economy < 0.0
    assert disruption == 0.0
    assert survival > 0.0
    assert "leader_race_deprioritized" in reasons
    assert "liquidity_escape_value" in reasons
    assert "expansion_cash_drag" in reasons
    assert "burden_liquidity_cover" in reasons


def test_evaluate_v2_emergency_risk_rules_captures_emergency_disruption_window() -> None:
    expansion, economy, disruption, survival, reasons = evaluate_v2_emergency_risk_rules(
        "박수",
        V2EmergencyRiskInputs(
            profile="control",
            leader_emergency=2.0,
            leader_is_solo=True,
            leader_near_end=True,
            reserve_gap=0.0,
            expected_loss=0.0,
            worst_loss=0.0,
            own_burden_cost=0.0,
            player_shards=4,
        ),
    )

    assert expansion == 0.0
    assert economy == 0.0
    assert disruption > 0.0
    assert survival == 0.0
    assert "emergency_leader_denial" in reasons


def test_evaluate_v2_emergency_risk_rules_captures_control_dry_denial_penalty() -> None:
    expansion, economy, disruption, survival, reasons = evaluate_v2_emergency_risk_rules(
        "자객",
        V2EmergencyRiskInputs(
            profile="control",
            leader_emergency=0.0,
            leader_is_solo=False,
            leader_near_end=False,
            reserve_gap=2.0,
            expected_loss=0.0,
            worst_loss=0.0,
            own_burden_cost=0.0,
            player_shards=2,
        ),
    )

    assert expansion == 0.0
    assert economy == 0.0
    assert disruption < 0.0
    assert survival < 0.0
    assert reasons == ["control_avoids_costly_denial_when_dry"]


def test_evaluate_v2_post_risk_rules_captures_cash_dry_penalty() -> None:
    score, survival, reasons = evaluate_v2_post_risk_rules(
        "산적",
        V2PostRiskInputs(
            has_uhsa_alive=True,
            is_muroe=True,
            reserve_gap=2.0,
        ),
    )

    assert score == 0.0
    assert survival < 0.0
    assert any(reason.startswith("cash_dry=") for reason in reasons)


def test_evaluate_v2_tail_threat_rules_captures_mark_risk_penalty() -> None:
    survival, reasons = evaluate_v2_tail_threat_rules(
        V2TailThreatInputs(mark_risk=1.75),
    )

    assert survival == -1.75
    assert reasons == ["mark_risk=1.75"]


def test_evaluate_v2_rent_tail_rules_surfaces_rent_reason_and_values() -> None:
    economy, combo, survival, reasons = evaluate_v2_rent_tail_rules(
        V2RentTailInputs(
            rent_pressure=2.25,
            rent_economy=1.2,
            rent_combo=0.5,
            rent_survival=2.0,
        ),
    )

    assert economy == 1.2
    assert combo == 0.5
    assert survival == 2.0
    assert reasons == ["rent_pressure=2.25"]


def test_evaluate_v2_uhsa_tail_rules_surfaces_block_penalty() -> None:
    survival, reasons = evaluate_v2_uhsa_tail_rules(
        V2UhsaTailInputs(blocked=True),
    )

    assert survival == -1.8
    assert reasons == ["uhsa_blocks_muroe"]


def test_evaluate_v3_character_rules_captures_lap_and_cleanup_windows() -> None:
    expansion, economy, disruption, survival, combo, meta, reasons = evaluate_v3_character_rules(
        "객주",
        V3CharacterInputs(
            shards=5,
            burden_count=1.0,
            cleanup_pressure=1.2,
            reserve_gap=0.0,
            money_distress=0.4,
            distress_level=0.2,
            cross_start=0.9,
            land_f=0.6,
            land_f_value=1.4,
            own_land=0.3,
            token_combo=1.1,
            token_window=1.6,
            buy_value=1.5,
            legal_visible_burden_total=0.0,
            top_threat_cash=10,
            stack_max_enemy=0.0,
            stack_max_enemy_owned=0.0,
            mobility_leverage=1.0,
            lap_fast_window=1.0,
            lap_rich_pool=0.8,
            lap_double_lap_threat=0.7,
            placeable=True,
        ),
    )

    assert expansion == 0.0
    assert economy > 0.0
    assert disruption == 0.0
    assert survival > 0.0
    assert combo > 0.0
    assert meta == 0.0
    assert "v3_route_loop" in reasons
    assert "v3_gakju_lap_engine" in reasons
    assert "v3_token_window" in reasons


def test_evaluate_v3_character_rules_captures_checkpoint_and_safe_expansion_penalties() -> None:
    _, b_economy, b_disruption, b_survival, b_combo, b_meta, b_reasons = evaluate_v3_character_rules(
        "박수",
        V3CharacterInputs(
            shards=4,
            burden_count=1.0,
            cleanup_pressure=2.0,
            reserve_gap=1.5,
            money_distress=1.1,
            distress_level=1.5,
            cross_start=0.0,
            land_f=0.0,
            land_f_value=0.0,
            own_land=0.0,
            token_combo=0.0,
            token_window=1.3,
            buy_value=0.0,
            legal_visible_burden_total=2.0,
            top_threat_cash=12,
            stack_max_enemy=0.0,
            stack_max_enemy_owned=0.0,
            mobility_leverage=0.0,
            lap_fast_window=0.0,
            lap_rich_pool=0.0,
            lap_double_lap_threat=0.0,
            placeable=False,
        ),
    )
    g_expansion, _, _, g_survival, _, _, g_reasons = evaluate_v3_character_rules(
        "중매꾼",
        V3CharacterInputs(
            shards=2,
            burden_count=0.0,
            cleanup_pressure=2.1,
            reserve_gap=1.0,
            money_distress=1.2,
            distress_level=1.4,
            cross_start=0.0,
            land_f=0.0,
            land_f_value=0.0,
            own_land=0.2,
            token_combo=0.0,
            token_window=1.0,
            buy_value=2.5,
            legal_visible_burden_total=0.0,
            top_threat_cash=9,
            stack_max_enemy=0.0,
            stack_max_enemy_owned=0.0,
            mobility_leverage=0.0,
            lap_fast_window=0.0,
            lap_rich_pool=0.0,
            lap_double_lap_threat=0.0,
            placeable=True,
        ),
    )

    assert b_economy > 0.0
    assert b_disruption > 0.0
    assert b_survival > 0.0
    assert b_combo > 0.0
    assert b_meta > 0.0
    assert "v3_cleanup_anchor" in b_reasons
    assert "v3_baksu_precheckpoint" in b_reasons
    assert "v3_token_window" in b_reasons
    assert "v3_burden_attack_timing" in b_reasons
    assert g_expansion < 0.0
    assert g_survival < 0.0
    assert "v3_safe_expansion_only" in g_reasons


def test_choose_hidden_trick_card_uses_helper_resolution_in_live_policy() -> None:
    policy = HeuristicPolicy()
    player = type("Player", (), {"player_id": 0, "current_character": CARD_TO_NAMES[7][0]})()
    card_type = type("Card", (), {})
    plain = card_type()
    plain.deck_index = 1
    plain.name = "plain"
    plain.is_burden = False
    plain.burden_cost = 0
    plain.is_anytime = False
    burden = card_type()
    burden.deck_index = 2
    burden.name = "burden"
    burden.is_burden = True
    burden.burden_cost = 4
    burden.is_anytime = False
    hand = [
        plain,
        burden,
    ]

    chosen = policy.choose_hidden_trick_card(None, player, hand)
    debug = policy.pop_debug("hide_trick", 0)

    assert chosen is burden
    assert debug is not None
    assert debug["chosen"] == "burden"
    assert debug["scores"]["burden"] > debug["scores"]["plain"]
