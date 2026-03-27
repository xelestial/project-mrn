from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Optional, Tuple
import math

from characters import CHARACTERS, CARD_TO_NAMES
from config import CellKind
from policy_groups import MARK_ACTOR_BASE_RISK, MARK_ACTOR_NAMES, RENT_ESCAPE_CHARACTERS, RENT_EXPANSION_CHARACTERS, RENT_FRAGILE_DISRUPTORS
from policy_mark_utils import mark_guess_distribution, mark_guess_policy_params, mark_priority_exposure_factor, mark_target_profile_factor, public_mark_guess_candidates
from state import GameState, PlayerState
from trick_cards import TrickCard
from policy_hooks import PolicyDecisionTraceRecorder, PolicyHookDispatcher
from weather_cards import COLOR_RENT_DOUBLE_WEATHERS
from survival_common import (
    ActionGuardContext,
    SurvivalSignals,
    SurvivalOrchestratorState,
    build_action_guard_context,
    build_survival_orchestrator,
    evaluate_character_survival_priority,
    evaluate_character_survival_advice,
    evaluate_swindle_guard,
    is_action_survivable,
)


ACTIVE_MONEY_DRAIN_CHARACTERS = {"탐관오리", "산적", "아전", "추노꾼", "만신"}
LOW_CASH_INCOME_CHARACTERS = {"객주", "아전", "만신"}
LOW_CASH_ESCAPE_CHARACTERS = {"객주", "파발꾼", "탈출 노비"}
LOW_CASH_CONTROLLER_CHARACTERS = {"교리 연구관", "교리 감독관"}
LOW_CASH_DISRUPTORS = {"자객", "아전", "만신", "교리 연구관", "교리 감독관"}
CLEANUP_THREAT_WEATHERS = {"긴급 피난"}
FORTUNE_CLEANUP_CARD_MULTIPLIERS = {"화재 발생": 1.0, "산불 발생": 2.0}

@dataclass(slots=True)
class MovementDecision:
    use_cards: bool
    card_values: Tuple[int, ...] = ()


@dataclass(slots=True)
class LapRewardDecision:
    choice: str  # cash / shards / coins / mixed / blocked
    cash_units: int = 0
    shard_units: int = 0
    coin_units: int = 0


class BasePolicy:

    def __init__(self) -> None:
        self._debug_choices: dict[tuple[str, int], dict[str, Any]] = {}
        self._policy_hooks = PolicyHookDispatcher()
        recorder = PolicyDecisionTraceRecorder(self._debug_choices)
        self._policy_hooks.register("policy.before_decision", recorder.before_decision)
        self._policy_hooks.register("policy.after_decision", recorder.after_decision)

    def __getattribute__(self, name: str):
        attr = object.__getattribute__(self, name)
        if name.startswith('choose_') and callable(attr) and not name.startswith('_'):
            try:
                hooks = object.__getattribute__(self, '_policy_hooks')
            except AttributeError:
                return attr
            def wrapped(*args, **kwargs):
                state = args[0] if args else kwargs.get('state')
                player = args[1] if len(args) > 1 else kwargs.get('player')
                hooks.emit('policy.before_decision', self, name, state, player, args, kwargs)
                result = attr(*args, **kwargs)
                hooks.emit('policy.after_decision', self, name, state, player, result, args, kwargs)
                return result
            return wrapped
        return attr

    def _ensure_policy_hook_state(self) -> None:
        if not hasattr(self, '_debug_choices'):
            object.__setattr__(self, '_debug_choices', {})
        if not hasattr(self, '_policy_hooks'):
            hooks = PolicyHookDispatcher()
            recorder = PolicyDecisionTraceRecorder(self._debug_choices)
            hooks.register("policy.before_decision", recorder.before_decision)
            hooks.register("policy.after_decision", recorder.after_decision)
            object.__setattr__(self, '_policy_hooks', hooks)

    def register_policy_hook(self, hook_name: str, hook) -> None:
        self._ensure_policy_hook_state()
        self._policy_hooks.register(hook_name, hook)

    def _set_debug(self, category: str, player_id: int, payload: dict[str, Any]) -> None:
        self._ensure_policy_hook_state()
        self._debug_choices[(category, player_id)] = dict(payload)

    def pop_debug(self, category: str, player_id: int) -> Optional[dict[str, Any]]:
        self._ensure_policy_hook_state()
        return self._debug_choices.pop((category, player_id), None)

    def should_attempt_swindle(self, state: GameState, player: PlayerState, pos: int, owner: int, required_cost: float) -> bool:
        return True

    def _character_score_breakdown_v2(self, state: GameState, player: PlayerState, character_name: str) -> tuple[float, list[str]]:
        w = self._weights()
        score = self.character_values.get(character_name, 0.0)
        reasons=[f"base={score:.1f}"]
        expansion = economy = disruption = meta = combo = survival = 0.0
        buy_value = self._expected_buy_value(state, player)
        cross_start = self._will_cross_start(state, player)
        land_f = self._will_land_on_f(state, player)
        f_ctx = self._f_progress_context(state, player)
        land_f_value = float(f_ctx["land_f_value"])
        burden_count = sum(1 for c in player.trick_hand if c.name in {"무거운 짐", "가벼운 짐"})
        legal_marks = self._allowed_mark_targets(state, player)
        has_marks = bool(legal_marks)
        burden_context = self._burden_context(state, player, legal_targets=legal_marks)
        monopoly = self._monopoly_block_metrics(state, player)
        liquidity = self._liquidity_risk_metrics(state, player, character_name)
        cleanup_pressure = burden_context["cleanup_pressure"]
        legal_visible_burden_total = burden_context["legal_visible_burden_total"]
        legal_visible_burden_peak = burden_context["legal_visible_burden_peak"]
        legal_low_cash_targets = burden_context["legal_low_cash_targets"]
        own_near_complete = monopoly["own_near_complete"]
        own_claimable_blocks = monopoly["own_claimable_blocks"]
        deny_now = monopoly["deny_now"]
        enemy_near_complete = monopoly["enemy_near_complete"]
        contested_blocks = monopoly["contested_blocks"]
        scammer = self._scammer_takeover_metrics(state, player)
        threat_targets = sorted(self._alive_enemies(state, player), key=lambda op: self._estimated_threat(state, player, op), reverse=True)
        top_threat = threat_targets[0] if threat_targets else None
        top_tags = self._predicted_opponent_archetypes(state, player, top_threat) if top_threat else set()
        exclusive_blocks = self._exclusive_blocks_owned(state, player.player_id)
        placeable = any(state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile for i in player.visited_owned_tile_indices)
        combo_names = {c.name for c in player.trick_hand}
        leader_pressure = self._leader_pressure(state, player, top_threat)
        denial_snapshot = self._leader_denial_snapshot(state, player, threat_targets=threat_targets, top_threat=top_threat)
        leader_emergency = float(denial_snapshot["emergency"])
        leader_is_solo = bool(denial_snapshot["solo_leader"])
        leader_near_end = bool(denial_snapshot["near_end"])
        top_threat_cross = self._will_cross_start(state, top_threat) if top_threat else 0.0
        top_threat_land_f = self._will_land_on_f(state, top_threat) if top_threat else 0.0

        if character_name == "중매꾼":
            adjacent_value = self._matchmaker_adjacent_value(state, player)
            expansion += 1.15 + 0.75 * buy_value + adjacent_value
            if leader_pressure > 0 and top_threat and ("expansion" in top_tags or top_threat.tiles_owned >= 5):
                disruption += 1.0 + 0.35 * leader_pressure + 0.35 * max(0.0, buy_value) + 0.20 * adjacent_value
                reasons.append("deny_leader_expansion")
            if "무료 증정" in combo_names or "마당발" in combo_names:
                combo += 1.6 + 0.35 * adjacent_value
                reasons.append("expansion_trick_combo")
            if player.shards <= 0:
                expansion -= 0.55
                reasons.append("matchmaker_adjacent_shard_gate")
        if character_name == "건설업자":
            build_value = self._builder_free_purchase_value(state, player)
            expansion += 1.18 + 0.68 * buy_value + 0.90 * build_value
            if leader_pressure > 0 and top_threat and ("expansion" in top_tags or top_threat.tiles_owned >= 5):
                disruption += 1.0 + 0.35 * leader_pressure + 0.30 * max(0.0, buy_value)
                reasons.append("deny_leader_expansion")
            if "무료 증정" in combo_names or "마당발" in combo_names:
                combo += 1.2 + 0.45 * build_value
                reasons.append("expansion_trick_combo")
        if character_name == "사기꾼":
            enemy_tiles = sum(p.tiles_owned for p in self._alive_enemies(state, player))
            expansion += 1.2 + 0.25 * enemy_tiles
            if leader_pressure > 0 and top_threat and top_threat.tiles_owned >= 4:
                disruption += 1.0 + 0.35 * leader_pressure
                reasons.append("deny_leader_takeover_lines")
            if land_f > 0.15 or "극심한 분리불안" in combo_names:
                combo += 1.8
                reasons.append("arrival_takeover_combo")
            if exclusive_blocks >= 2:
                expansion -= 0.9
                reasons.append("monopoly_blocks_takeover")
            if scammer["coin_value"] > 0.0:
                expansion += 0.75 * scammer["coin_value"]
                disruption += 0.55 * scammer["coin_value"]
                reasons.append("takeover_coin_swing")
            if scammer["best_tile_coins"] >= 2:
                combo += 0.9 + 0.25 * scammer["best_tile_coins"]
                reasons.append("rich_tile_takeover")
            if scammer["blocks_enemy_monopoly"] > 0.0:
                disruption += 1.4 * scammer["blocks_enemy_monopoly"]
                reasons.append("blocks_monopoly_with_coin_swing")
            if scammer["finishes_own_monopoly"] > 0.0:
                expansion += 1.2 * scammer["finishes_own_monopoly"]
                reasons.append("finishes_monopoly_via_takeover")
        if character_name == "추노꾼":
            disruption += 0.8
            if buy_value > 0:
                disruption += 2.6
                reasons.append("post_buy_rent_trap")
            if leader_pressure > 0 and top_threat and top_threat.tiles_owned >= 5:
                disruption += 1.0 + 0.45 * leader_pressure
                reasons.append("leader_position_punish")
            if has_marks and any(op.cash >= 8 for op in legal_marks):
                disruption += 1.1
        if character_name == "객주":
            economy += 2.0 * cross_start + 1.2 * land_f * land_f_value + 0.25 * len(player.visited_owned_tile_indices)
            if leader_pressure > 0 and top_threat and (top_threat_cross > 0.3 or top_threat_land_f > 0.2 or "geo" in top_tags):
                disruption += 1.0 + 0.3 * leader_pressure
                reasons.append("deny_leader_lap_engine")
            if cross_start > 0.3:
                reasons.append("near_start_cross")
            if land_f > 0.2:
                reasons.append("f_tile_bonus")
            if any(n in combo_names for n in {"뇌절왕", "극심한 분리불안", "도움 닫기"}):
                combo += 1.6
                reasons.append("lap_token_combo")
        if character_name == "파발꾼":
            economy += 1.0 * cross_start + 0.55 * land_f * land_f_value
            combo += 0.6 * sum(1 for n in combo_names if n in {"과속", "이럇!", "도움 닫기"})
            if combo > 0:
                reasons.append("speed_combo")
        if character_name == "탈출 노비":
            economy += 0.3 * self._reachable_specials_with_one_short(state, player)
            if cross_start > 0.2:
                combo += 0.8
                reasons.append("escape_runner")
        if character_name in {"산적", "아전", "탐관오리"}:
            economy += 0.35 * player.shards
            if "성물 수집가" in combo_names:
                combo += 1.3
                reasons.append("shard_combo")
        if character_name == "자객":
            if has_marks and top_threat and ("expansion" in top_tags or "geo" in top_tags or "combo_ready" in top_tags or top_threat.tiles_owned >= 5):
                disruption += 2.4 + 0.45 * leader_pressure
                reasons.append("prevent_big_turn")
        if character_name == "산적":
            if has_marks and top_threat and (top_threat.cash >= 12 or top_threat.tiles_owned >= 5):
                disruption += 1.8 + 0.15 * player.shards + 0.35 * leader_pressure
                reasons.append("cash_damage_value")
        if character_name == "만신":
            if top_threat and "burden" in top_tags:
                disruption += 2.0
                reasons.append("burden_purge")
            if legal_visible_burden_total > 0:
                disruption += 1.4 + 1.2 * legal_visible_burden_total + 0.45 * legal_visible_burden_peak
                reasons.append("public_burden_cleanup_value")
            if cleanup_pressure >= 2.5:
                survival += 0.45 * cleanup_pressure
                reasons.append("future_fire_insurance")
            if legal_visible_burden_total > 0 and legal_low_cash_targets > 0:
                disruption += 0.35 * legal_low_cash_targets
                reasons.append("cash_fragile_cleanup")
        if character_name == "박수":
            if burden_count >= 1:
                combo += 1.0 + 0.45 * burden_count
                survival += 1.4 + 1.05 * burden_count + 0.55 * cleanup_pressure
                reasons.append("future_burden_escape")
                # [시스템 이해] 조각 5개 이상 + 짐 보유 = 폴백 확정
                # 지목 성공/실패 무관하게 짐 1장 제거 + 비용만큼 현금 획득
                # → 짐 파산 걱정 없이 구매 공격적으로 가능
                if player.shards >= 5:
                    removed, payout = self._failed_mark_fallback_metrics(player, 5)
                    # 폴백 1회로 짐 제거 + 현금 확보 → 이 상태에서 구매 가능해짐
                    survival += 0.8 + 0.15 * payout
                    economy += 0.5  # 현금 회수로 경제 활성화
                    reasons.append(f"baksu_fallback_guaranteed(+{payout}냥)")
                    # 짐 2장 이상 + 조각 10개이면 2회 폴백 가능
                    if burden_count >= 2 and player.shards >= 10:
                        survival += 0.6
                        reasons.append("baksu_double_fallback_possible")
            else:
                if has_marks and legal_visible_burden_total > 0:
                    survival -= 0.5
                    reasons.append("baksu_no_burden_mark_ok")
                else:
                    survival -= 1.2
                    reasons.append("baksu_no_own_burden_waste")
            if burden_count >= 1 and has_marks and legal_low_cash_targets > 0:
                disruption += 0.35 * legal_low_cash_targets
                reasons.append("burden_dump_fragile_target")
        if character_name == "어사":
            if top_threat and ("shard_attack" in top_tags or top_threat.current_character in {"산적", "자객", "탐관오리", "사기꾼"}):
                disruption += 1.8
                reasons.append("muroe_counter")
            # [v3_claude] 어사: 우선권 1 → 지목 위협 없음 + 가장 먼저 이동
            # 어사·탐관오리는 같은 카드(card_no=1, pair 관계) → 동시에 존재 불가
            # 어사 active 시: 무뢰 속성 인물 능력 봉쇄 (탐관오리, 자객, 산적, 사기꾼)
            if self._profile_from_mode() == "v3_claude" and buy_value > 0.0:
                expansion += 0.8 + 0.3 * buy_value
                survival += 0.6
                reasons.append("v3_uhsa_first_mover")
        if character_name == "탐관오리":
            # [v3_claude] 탐관오리: 어사의 반대 면 (card_no=1, pair=어사)
            # → 어사가 active이면 탐관오리는 존재할 수 없음 (드래프트에서 같은 카드)
            # 능력: 관원/상민 속성 플레이어가 이동할 때
            #   - 그 플레이어 자신의 조각 // 2 만큼 탐관오리에게 지급
            #   - 대가로 그 플레이어는 주사위 1개 추가 (이동 버프 → 상대에게 유리할 수 있음)
            # 무뢰 속성 → 어사 active 시 능력 봉쇄 (어사와 같은 카드이므로 공존 불가이긴 함)
            if self._profile_from_mode() == "v3_claude":
                # 우선권 1: 먼저 이동 = 빈 땅 선점
                if buy_value > 0.0:
                    expansion += 0.7 + 0.2 * buy_value
                    reasons.append("v3_tangwan_first_mover")
                survival += 0.5  # 지목 위협 없음
                # 세금 수입: 관원/상민 상대가 자신의 조각 //2 만큼 지불
                # 단 그 대가로 상대 이동이 빨라짐 → 부분 상쇄
                alive_enemies = self._alive_enemies(state, player)
                taxable = [
                    p for p in alive_enemies
                    if p.current_character
                    and CHARACTERS.get(p.current_character)
                    and CHARACTERS[p.current_character].attribute in {"관원", "상민"}
                ]
                if taxable:
                    # 세금 = 상대(관원/상민) 각자의 조각 // 2
                    total_tax = sum(p.shards // 2 for p in taxable)
                    # 상대 이동 버프(주사위 추가) 부작용 약 35% 상쇄 → 순이득 65%
                    net_tax = total_tax * 0.65
                    if net_tax >= 0.5:
                        economy += 0.3 + 0.12 * net_tax
                        reasons.append(f"v3_tangwan_net_tax({total_tax}냥×0.65={net_tax:.1f})")
        if character_name in {"교리 연구관", "교리 감독관"}:
            meta += 1.2
            # [burden_patch] 짐을 들고 있을수록 교리 계열의 짐 제거 가치가 커진다.
            # 턴 시작 시 자기 짐 1장 무료 제거 → 짐 장수/비용에 비례 가산
            own_burden_cost = float(sum(c.burden_cost for c in player.trick_hand if c.is_burden))
            own_burden_count = sum(1 for c in player.trick_hand if c.is_burden)
            if own_burden_count >= 1:
                meta += 1.0 + 0.55 * own_burden_cost
                reasons.append("doctrine_burden_relief_value")
            marker_plan = self._leader_marker_flip_plan(state, player, top_threat) if top_threat else {"best_score": 0.0}
            if top_threat and ("expansion" in top_tags or "geo" in top_tags or top_threat.tiles_owned >= 5):
                meta += 1.6 + 0.35 * leader_pressure
                reasons.append("flip_meta_denial")
            if float(marker_plan["best_score"]) > 0.0:
                meta += 0.95 + 0.85 * float(marker_plan["best_score"])
                disruption += 0.30 * float(marker_plan["best_score"])
                reasons.append("marker_strips_needed_leader_face")
        if character_name in {"객주", "파발꾼", "사기꾼"}:
            economy += 0.15 * player.cash
        elif character_name == "중매꾼":
            economy += 0.10 * player.cash + 0.20 * self._matchmaker_adjacent_value(state, player)
        elif character_name == "건설업자":
            economy += 0.09 * player.cash + 0.28 * self._builder_free_purchase_value(state, player)
        if character_name in {"객주", "파발꾼", "탈출 노비"} and placeable:
            economy += 0.8
        if character_name == "중매꾼" and own_near_complete > 0:
            expansion += 2.25 * own_near_complete + 0.65 * own_claimable_blocks + 0.35 * self._matchmaker_adjacent_value(state, player)
            reasons.append("monopoly_finish_value")
        if character_name == "건설업자" and own_near_complete > 0:
            expansion += 2.05 * own_near_complete + 0.45 * own_claimable_blocks + 0.45 * self._builder_free_purchase_value(state, player)
            reasons.append("monopoly_finish_value")
        if character_name in {"객주", "파발꾼", "탈출 노비"} and own_claimable_blocks > 0:
            economy += 0.65 * own_claimable_blocks
            reasons.append("monopoly_route_value")
        if character_name == "중매꾼" and own_claimable_blocks > 0:
            economy += 0.55 * own_claimable_blocks + 0.20 * self._matchmaker_adjacent_value(state, player)
            reasons.append("monopoly_route_value")
        if character_name == "건설업자" and own_claimable_blocks > 0:
            economy += 0.45 * own_claimable_blocks + 0.25 * self._builder_free_purchase_value(state, player)
            reasons.append("monopoly_route_value")
        if character_name == "사기꾼" and enemy_near_complete > 0:
            disruption += 2.2 * enemy_near_complete + 0.45 * contested_blocks
            reasons.append("preempt_monopoly_takeover")
        if character_name in {"추노꾼", "자객", "산적"} and enemy_near_complete > 0:
            disruption += 1.6 * enemy_near_complete + 0.35 * deny_now
            reasons.append("deny_enemy_monopoly")
        if character_name in {"파발꾼", "탈출 노비"} and deny_now > 0:
            survival += 0.55 * deny_now
            reasons.append("monopoly_danger_escape")
        if leader_emergency > 0.0 and top_threat and top_threat.player_id != player.player_id:
            if character_name in {"자객", "산적", "추노꾼", "사기꾼", "박수", "만신", "어사"}:
                disruption += 1.55 + 0.55 * leader_emergency
                if leader_is_solo:
                    disruption += 0.45
                if leader_near_end:
                    disruption += 0.55
                reasons.append("emergency_leader_denial")
            if character_name in {"교리 연구관", "교리 감독관"}:
                meta += 1.45 + 0.50 * leader_emergency
                disruption += 0.35 * leader_emergency
                reasons.append("emergency_marker_denial")
            if leader_near_end and character_name in {"중매꾼", "건설업자", "객주", "파발꾼"}:
                expansion -= 0.85 + 0.25 * leader_emergency
                economy -= 0.35 * leader_emergency
                if character_name == "건설업자" and player.shards > 0:
                    expansion += 0.20
                reasons.append("leader_race_deprioritized")
        # survival / risk
        leading = sum(1 for op in self._alive_enemies(state, player) if self._estimated_threat(state, player, player) >= self._estimated_threat(state, player, op)) == len(self._alive_enemies(state, player))
        if self._profile_from_mode() == "avoid_control":
            if character_name in {"중매꾼", "건설업자", "사기꾼"} and (leading or top_threat and has_marks):
                survival -= 1.4
                reasons.append("avoid_being_targeted")
            if character_name in {"객주", "아전", "교리 연구관", "교리 감독관"}:
                survival += 1.1
        profile = self._profile_from_mode()
        if profile == "control":
            finisher_window, finisher_reason = self._control_finisher_window(player)
            if leader_emergency > 0.0:
                if character_name in {"사기꾼", "교리 연구관", "교리 감독관", "객주", "탈출 노비", "파발꾼", "어사"}:
                    disruption += 0.55 + 0.30 * leader_emergency
                    meta += 0.15 * leader_emergency
                    reasons.append("control_efficient_denial")
                if leader_near_end and character_name in {"교리 연구관", "교리 감독관", "사기꾼", "객주", "탈출 노비"}:
                    disruption += 0.55
                    survival += 0.25
                    reasons.append("control_endgame_lock")
            elif buy_value > 0.0 and character_name in {"중매꾼", "건설업자", "사기꾼", "객주", "파발꾼"}:
                expansion += 0.45 + 0.20 * buy_value
                economy += 0.20
                if character_name == "중매꾼":
                    expansion += 0.22 + 0.10 * self._matchmaker_adjacent_value(state, player)
                elif character_name == "건설업자":
                    expansion += 0.18 + 0.12 * self._builder_free_purchase_value(state, player)
                reasons.append("control_keeps_pace")
            if finisher_window > 0.0:
                if character_name in {"중매꾼", "건설업자", "사기꾼", "객주", "파발꾼"}:
                    expansion += 0.85 + 0.35 * finisher_window + 0.18 * buy_value
                    economy += 0.35 + 0.18 * finisher_window
                    combo += 0.18 * finisher_window
                    reasons.append(f"control_finisher_window={finisher_reason}")
                if character_name in {"자객", "산적", "추노꾼"}:
                    disruption -= 0.45 + 0.15 * finisher_window
                    survival -= 0.10 * finisher_window
                    reasons.append("control_finisher_avoids_redundant_denial")
        if profile == "aggressive":
            if character_name in {"중매꾼", "건설업자", "사기꾼", "추노꾼", "자객"}:
                combo += 0.9
                reasons.append("aggressive_push")

        if profile == "v3_claude":
            # [v3_claude] 우선권 인식 전략
            char_priority = {"어사":1,"탐관오리":1,"자객":2,"산적":2,"추노꾼":3,"탈출 노비":3,
                             "파발꾼":4,"아전":4,"교리 연구관":5,"교리 감독관":5,"박수":6,"만신":6,
                             "객주":7,"중매꾼":7,"건설업자":8,"사기꾼":8}
            my_priority = char_priority.get(character_name, 5)
            alive_lower_priority = sum(
                1 for p in state.players
                if p.alive and p.player_id != player.player_id
                and char_priority.get(p.current_character or "", 5) > my_priority
            )
            if my_priority <= 3:
                survival += 0.6 + 0.10 * alive_lower_priority
                reasons.append(f"v3_high_priority_safe(p={my_priority})")
            elif my_priority >= 7:
                survival -= 0.4 + 0.08 * alive_lower_priority
                reasons.append(f"v3_low_priority_exposed(p={my_priority})")

            # ② 지목형 인물: 대상 수 실측
            if character_name in {"자객", "산적", "추노꾼", "박수", "만신"}:
                mark_targets = sum(
                    1 for p in state.players
                    if p.alive and p.player_id != player.player_id
                    and char_priority.get(p.current_character or "", 5) > my_priority
                )
                if mark_targets >= 2:
                    disruption += 0.7 + 0.2 * mark_targets
                    reasons.append(f"v3_mark_targets={mark_targets}")
                elif mark_targets == 1:
                    disruption += 0.3
                    reasons.append("v3_mark_target_limited")
                else:
                    disruption -= 0.8
                    reasons.append("v3_mark_target_none")

            # ③ 교리 계열: 리더 종속 + 징표 제어 가치
            if character_name in {"교리 연구관", "교리 감독관"} and top_threat:
                meta += 0.6 + 0.4 * leader_pressure
                reasons.append("v3_marker_control_value")

            # ④ 중매꾼: 빈 구역 많을 때 강화, 조각 없으면 감점
            if character_name == "중매꾼":
                if player.shards >= 1 and buy_value > 0.0:
                    expansion += 1.0 + 0.3 * buy_value
                    reasons.append("v3_matchmaker_expansion")
                elif player.shards == 0:
                    expansion -= 0.6
                    reasons.append("v3_matchmaker_no_shards")

            # ⑤ 건설업자/사기꾼: 구매 기회 있을 때 적극 활용
            if character_name == "건설업자" and buy_value > 0.0:
                expansion += 0.8 + 0.4 * buy_value
                reasons.append("v3_builder_buy_window")
            if character_name == "사기꾼" and buy_value > 0.0:
                expansion += 0.6 + 0.3 * buy_value
                reasons.append("v3_swindler_buy_window")

            # ⑥ 파발꾼 과집중 억제: 랩이 2회 이상 돌았고 구매 기회가 있을 때 감점
            if character_name == "파발꾼":
                rounds_done = getattr(state, 'rounds_completed', 0)
                if rounds_done >= 6 and buy_value > 0.5:
                    expansion -= 0.4
                    reasons.append("v3_pabalkun_overuse_penalty")

            # ⑦ 상황 인식 전략 전환: 상대 타일이 나보다 2개 이상 많으면 견제 우선
            my_tiles = player.tiles_owned
            max_enemy_tiles = max(
                (p.tiles_owned for p in state.players if p.alive and p.player_id != player.player_id),
                default=0
            )
            tile_gap = max_enemy_tiles - my_tiles
            if tile_gap >= 2:
                # 상대가 앞서면 견제/방해형 인물 가산
                if character_name in {"추노꾼", "자객", "만신", "교리 연구관", "교리 감독관"}:
                    disruption += 0.5 + 0.15 * tile_gap
                    reasons.append(f"v3_catch_up_mode(gap={tile_gap})")
                # 구매형 인물도 여전히 가산 (따라잡기 필요)
                if character_name in {"중매꾼", "건설업자", "사기꾼"} and buy_value > 0.0:
                    expansion += 0.4 + 0.1 * tile_gap
                    reasons.append("v3_catch_up_buy")
        if profile == "token_opt":
            own_land = self._prob_land_on_placeable_own_tile(state, player)
            token_combo = self._token_teleport_combo_score(player)
            if character_name in {"객주", "파발꾼", "탈출 노비"}:
                economy += 1.2 * cross_start + 0.7 * land_f * land_f_value
                combo += token_combo
                reasons.append("token_route_mobility")
            if character_name in {"객주", "중매꾼", "건설업자", "사기꾼"}:
                economy += 1.4 * own_land
                reasons.append("own_tile_token_arrival")
            if character_name in {"자객", "추노꾼", "산적"} and top_threat and leader_pressure >= 2.5:
                disruption += 0.8 + 0.25 * leader_pressure
                reasons.append("token_threshold_counter")
            if placeable:
                combo += 0.8 + 1.4 * own_land + token_combo
                reasons.append("token_placeable_pressure")

        if self._has_uhsa_alive(state, exclude_player_id=player.player_id) and CHARACTERS[character_name].attribute == "무뢰":
            survival -= 1.8
            reasons.append("uhsa_blocks_muroe")
        reserve_gap = max(0.0, liquidity["reserve"] - player.cash)
        if reserve_gap > 0.0:
            survival -= 0.55 * reserve_gap
            reasons.append(f"cash_dry={reserve_gap:.2f}")
        if profile == "control":
            if reserve_gap > 0.0 and character_name in {"자객", "산적", "추노꾼"}:
                disruption -= 0.35 * reserve_gap
                survival -= 0.20 * reserve_gap
                reasons.append("control_avoids_costly_denial_when_dry")
            if reserve_gap <= 1.0 and character_name in {"사기꾼", "객주", "파발꾼", "탈출 노비"}:
                survival += 0.20
                economy += 0.15
                reasons.append("control_low_cost_stability")
        if character_name in RENT_ESCAPE_CHARACTERS:
            survival += 0.22 * liquidity["expected_loss"] + 0.10 * liquidity["worst_loss"]
            reasons.append("liquidity_escape_value")
        if character_name in RENT_EXPANSION_CHARACTERS and reserve_gap > 0.0:
            expansion -= 0.45 * reserve_gap
            survival -= 0.25 * reserve_gap
            reasons.append("expansion_cash_drag")
        if character_name in {"박수", "만신", "객주"} and liquidity["own_burden_cost"] > 0.0:
            survival += 0.25 * liquidity["own_burden_cost"]
            reasons.append("burden_liquidity_cover")
        mark_risk, mark_reasons = self._public_mark_risk_breakdown(state, player, character_name)
        if mark_risk > 0.0:
            survival -= mark_risk
            reasons.append(f"mark_risk={mark_risk:.2f}")
            reasons.extend(mark_reasons)
        rent_pressure, rent_reasons = self._rent_pressure_breakdown(state, player, character_name)
        if rent_pressure > 0.0:
            rent_economy, rent_combo, rent_survival = self._apply_rent_pressure_adjustment_v2(state, player, character_name, cross_start, land_f, rent_pressure, reasons)
            economy += rent_economy
            combo += rent_combo
            survival += rent_survival
            reasons.append(f"rent_pressure={rent_pressure:.2f}")
            reasons.extend(rent_reasons)
        # [burden_patch] 짐 보유 시 프로파일별 survival 가중치 동적 보정.
        # PROFILE_WEIGHTS의 고정값은 유지하되, 짐을 들고 있을수록
        # 생존 신호가 실제 결정에 더 강하게 반영되도록 가중치를 일시 상향한다.
        # 보정량은 프로파일 기본 가중치가 낮을수록 크게 적용한다.
        own_burden_count = sum(1 for c in player.trick_hand if c.is_burden)
        if own_burden_count >= 1:
            base_sw = w["survival"]
            # 목표: 짐 1장당 최소 1.1 수준의 유효 생존 가중치를 보장
            # 부족분을 own_burden_count 에 비례해 보정
            # v3_claude는 expansion 1.6으로 구매 많아 현금이 얇아짐
            # → 짐 보유 시 목표 survival 가중치를 더 높게 설정해 짐 청산 인물 선호 강화
            if profile == "v3_claude":
                target_sw = min(1.6, base_sw + 0.7 * own_burden_count)
            else:
                target_sw = min(1.4, base_sw + 0.5 * own_burden_count)
            burden_sw_boost = max(0.0, target_sw - base_sw)
            if burden_sw_boost > 0.0:
                total = score + w["expansion"]*expansion + w["economy"]*economy + w["disruption"]*disruption + w["meta"]*meta + w["combo"]*combo + (base_sw + burden_sw_boost)*survival
                reasons.append(f"burden_survival_boost={burden_sw_boost:.2f}(sw {base_sw:.1f}→{base_sw+burden_sw_boost:.1f})")
            else:
                total = score + w["expansion"]*expansion + w["economy"]*economy + w["disruption"]*disruption + w["meta"]*meta + w["combo"]*combo + w["survival"]*survival
        else:
            total = score + w["expansion"]*expansion + w["economy"]*economy + w["disruption"]*disruption + w["meta"]*meta + w["combo"]*combo + w["survival"]*survival
        reasons.append(f"mix=e{economy:.1f}/x{expansion:.1f}/d{disruption:.1f}/m{meta:.1f}/c{combo:.1f}/s{survival:.1f}")
        return total, reasons

    def _target_score_breakdown_v2(self, state: GameState, player: PlayerState, actor_name: str, target: PlayerState) -> tuple[float, list[str]]:
        score = self._estimated_threat(state, player, target)
        reasons = [f"threat={score:.1f}"]
        tags = self._predicted_opponent_archetypes(state, player, target)
        denial_snapshot = self._leader_denial_snapshot(state, player)
        top_threat = denial_snapshot["top_threat"]
        if top_threat is not None and target.player_id == top_threat.player_id and denial_snapshot["emergency"] > 0.0:
            score += 2.4 + 0.65 * float(denial_snapshot["emergency"])
            reasons.append("urgent_leader_target")
            if denial_snapshot["solo_leader"]:
                score += 0.8
                reasons.append("solo_leader_target")
            if denial_snapshot["near_end"]:
                score += 1.0
                reasons.append("near_end_target")
        if actor_name == "자객":
            if "expansion" in tags or "geo" in tags or "combo_ready" in tags:
                score += 3.0
                reasons.append("prevent_big_turn")
        elif actor_name == "산적":
            score += 0.25 * target.cash + 0.5 * player.shards
            if target.cash <= max(0, player.shards + 3):
                score += 1.5
                reasons.append("near_bankrupt_after_raid")
        elif actor_name == "추노꾼":
            score += 0.8 * self._expected_buy_value(state, player)
            landing_owner = state.tile_owner[player.position]
            if landing_owner is not None and landing_owner != target.player_id:
                score += 1.8
                reasons.append("force_into_rent")
            if state.board[player.position] in {CellKind.F1, CellKind.F2, CellKind.S, CellKind.MALICIOUS}:
                score += 1.2
                reasons.append("force_special_tile")
        elif actor_name == "박수":
            burden = sum(1 for c in player.trick_hand if c.name in {"무거운 짐", "가벼운 짐"})
            target_burden = self._visible_burden_count(player, target)
            score += 1.1 * burden + 0.9 * target_burden + 0.16 * max(0, 12 - target.cash)
            reasons.append("dump_burdens")
        elif actor_name == "만신":
            burden = self._visible_burden_count(player, target)
            score += 2.1 * burden + 0.14 * max(0, 14 - target.cash)
            reasons.append("clear_target_burdens")
        return score, reasons

    def choose_trick_to_use(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        supported = {
            "성물 수집가": 1.8, "건강 검진": 1.2, "우대권": 1.4, "무료 증정": 1.6,
            "신의뜻": 1.0, "가벼운 분리불안": 0.9, "극심한 분리불안": 1.2, "마당발": 1.4, "뇌고왕": 1.1, "뇌절왕": 1.3,
            "재뿌리기": 1.2, "긴장감 조성": 1.3, "무역의 선물": 1.0, "도움 닫기": 1.1, "번뜩임": 0.8,
            "느슨함 혐오자": 0.9, "극도의 느슨함 혐오자": 1.5,
            "과속": 0.8, "저속": 0.3, "이럇!": 0.7, "아주 큰 화목 난로": 1.0, "거대한 산불": 1.3,
            "무거운 짐": -0.6, "가벼운 짐": -0.3,
        }
        best = None
        best_score = 0.0
        details = {}
        monopoly = self._monopoly_block_metrics(state, player)
        own_near_complete = monopoly["own_near_complete"]
        enemy_near_complete = monopoly["enemy_near_complete"]
        deny_now = monopoly["deny_now"]
        combo_names = {c.name for c in hand}
        token_profile = self._profile_from_mode() == "token_opt"
        placeable_tiles = self._placeable_own_tiles(state, player)
        token_place_bias = 1.0 if (token_profile and player.hand_coins > 0 and placeable_tiles) else 0.0
        for card in hand:
            score = supported.get(card.name, -99.0)
            if token_profile and card.name in {"극심한 분리불안", "도움 닫기", "과속", "이럇!", "뇌절왕"}:
                score += 0.9 + token_place_bias
            if token_profile and card.name in {"무료 증정", "마당발"} and player.current_character in {"중매꾼", "건설업자"}:
                score += 0.8
            if token_profile and card.name in {"재뿌리기", "긴장감 조성"} and player.hand_coins >= 2:
                score += 0.5
            if card.name == "무료 증정" and player.cash >= 3:
                score += 0.6
            if card.name == "과속" and player.cash >= 2:
                score += 0.4
            if card.name == "저속":
                score += 0.2 if player.cash < 6 else -0.5
            if card.name == "재뿌리기":
                score += 0.4 if any(state.tile_owner[i] not in {None, player.player_id} for i in range(len(state.board)) if state.tile_at(i).purchase_cost is not None) else -1.0
            if card.name == "긴장감 조성":
                score += 0.5 if player.tiles_owned > 0 else -1.0
            if card.name in {"무료 증정", "마당발", "우대권"} and own_near_complete > 0:
                score += 1.1 + 0.5 * own_near_complete
            if card.name in {"과속", "이럇!", "도움 닫기", "극심한 분리불안", "가벼운 분리불안"} and (own_near_complete > 0 or deny_now > 0):
                score += 0.7 + 0.35 * max(own_near_complete, deny_now)
            if card.name in {"재뿌리기", "무역의 선물", "무료 증정"} and enemy_near_complete > 0:
                score += 0.9 + 0.35 * enemy_near_complete
            if card.name == "긴장감 조성" and enemy_near_complete > 0:
                score += 0.5 * enemy_near_complete
            if card.name in {"무거운 짐", "가벼운 짐"}:
                score = -1.0
            if self._is_v2_mode():
                current = player.current_character
                if card.name in {"무료 증정", "마당발"} and current in {"중매꾼", "건설업자"}:
                    score += 2.0
                if card.name == "극심한 분리불안" and current in {"사기꾼", "객주"}:
                    score += 2.0
                if card.name in {"과속", "이럇!", "도움 닫기"} and current == "파발꾼":
                    score += 1.6
                if card.name == "성물 수집가" and current in {"산적", "아전", "탐관오리"}:
                    score += 1.7
                if card.name == "번뜩임" and (sum(1 for c in hand if c.name in {"무거운 짐", "가벼운 짐"}) >= 2 or any(c.name not in {"무거운 짐", "가벼운 짐"} for c in hand)):
                    score += 1.0
                if card.name in {"재뿌리기", "긴장감 조성"} and current in {"자객", "산적", "추노꾼"}:
                    score += 1.2
            details[card.name] = round(score, 3)
            if score > best_score:
                best = card
                best_score = score
        self._set_debug("trick_use", player.player_id, {"scores": details, "chosen": None if best is None else best.name})
        return best

    def choose_specific_trick_reward(self, state: GameState, player: PlayerState, choices: list[TrickCard]) -> TrickCard | None:
        if not choices:
            return None
        def score(card: TrickCard) -> float:
            if card.name in {"무거운 짐", "가벼운 짐"}:
                return -10.0
            base = {"무료 증정": 4.0, "우대권": 3.4, "성물 수집가": 3.0, "건강 검진": 2.5, "극도의 느슨함 혐오자": 2.0}.get(card.name, 1.0)
            return base
        pick = max(choices, key=score)
        self._set_debug("trick_reward", player.player_id, {"choices": [c.name for c in choices], "chosen": pick.name})
        return pick

    def choose_burden_exchange_on_supply(self, state: GameState, player: PlayerState, card: TrickCard) -> bool:
        # [burden_patch] 단순 cash >= cost 체크 대신, 청산 후 생존선 유지 여부까지 확인한다.
        # 짐을 지우는 것 자체는 좋지만, 청산 비용을 낸 뒤 렌트/오프턴 과금을 버틸 여유가
        # 없으면 청산이 오히려 파산을 앞당긴다.
        if player.cash < card.burden_cost:
            return False
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        post_cash = player.cash - card.burden_cost
        reserve = float(survival_ctx.get("reserve", 0.0))
        # 청산 후 즉사 위험 또는 극단적 자금 부족이면 보류
        two_turn_lethal = float(survival_ctx.get("two_turn_lethal_prob", 0.0))
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        # 잔존 부담 비용(다른 짐 카드): 이 청산 외에 남은 짐도 함께 고려
        other_burden_cost = sum(
            float(c.burden_cost) for c in player.trick_hand
            if c.is_burden and c.deck_index != card.deck_index
        )
        # 청산 후 현금이 reserve + 나머지 짐 비용 + 렌트 여유보다 낮으면 위험
        safety_floor = reserve + other_burden_cost + max(0.0, 3.0 * two_turn_lethal) + max(0.0, 2.0 * money_distress)
        if post_cash < safety_floor and money_distress >= 0.4:
            return False
        return True

    def choose_hidden_trick_card(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        return None

    def choose_purchase_tile(self, state: GameState, player: PlayerState, pos: int, cell: CellKind, cost: int, *, source: str = "landing") -> bool:
        return True

    def choose_movement(self, state: GameState, player: PlayerState) -> MovementDecision:
        raise NotImplementedError

    def choose_lap_reward(self, state: GameState, player: PlayerState) -> LapRewardDecision:
        raise NotImplementedError

    def choose_coin_placement_tile(self, state: GameState, player: PlayerState) -> Optional[int]:
        raise NotImplementedError

    def _escape_package_names(self) -> set[str]:
        return {"박수", "만신", "탈출 노비"}

    def _marker_package_names(self) -> set[str]:
        return {"교리 연구관", "교리 감독관"}

    def _lap_reward_bundle(self, state: GameState, cash_unit_score: float, shard_unit_score: float, coin_unit_score: float, preferred: str | None = None) -> LapRewardDecision:
        rules = state.config.rules.lap_reward
        rem_cash = max(0, int(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool)))
        rem_shards = max(0, int(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool)))
        rem_coins = max(0, int(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool)))
        best: tuple[float, int, int, int, str] | None = None
        preferred_bonus = {preferred: 0.08} if preferred else {}
        for cash_units in range(0, min(rem_cash, rules.points_budget // max(1, rules.cash_point_cost)) + 1):
            cash_points = cash_units * rules.cash_point_cost
            if cash_points > rules.points_budget:
                break
            shard_cap = min(rem_shards, (rules.points_budget - cash_points) // max(1, rules.shards_point_cost))
            for shard_units in range(0, shard_cap + 1):
                spent = cash_points + shard_units * rules.shards_point_cost
                coin_cap = min(rem_coins, (rules.points_budget - spent) // max(1, rules.coins_point_cost))
                for coin_units in range(0, coin_cap + 1):
                    total_spent = spent + coin_units * rules.coins_point_cost
                    if total_spent <= 0 or total_spent > rules.points_budget:
                        continue
                    utility = (
                        cash_units * cash_unit_score
                        + shard_units * shard_unit_score
                        + coin_units * coin_unit_score
                        + 0.02 * total_spent
                    )
                    if preferred:
                        dominant = max(((cash_units, "cash"), (shard_units, "shards"), (coin_units, "coins")), key=lambda item: (item[0], preferred_bonus.get(item[1], 0.0)))[1]
                        utility += preferred_bonus.get(dominant, 0.0)
                    candidate = (utility, cash_units, shard_units, coin_units, preferred or "mixed")
                    if best is None or candidate > best:
                        best = candidate
        if best is None:
            return LapRewardDecision("blocked")
        _, cash_units, shard_units, coin_units, _ = best
        components = [(cash_units, "cash"), (shard_units, "shards"), (coin_units, "coins")]
        choice = max(components, key=lambda item: item[0])[1] if sum(v for v, _ in components) > 0 else "blocked"
        if preferred == "cash" and cash_units > 0:
            choice = "cash"
        elif preferred == "shards" and shard_units > 0:
            choice = "shards"
        elif preferred == "coins" and coin_units > 0:
            choice = "coins"
        return LapRewardDecision(choice=choice, cash_units=cash_units, shard_units=shard_units, coin_units=coin_units)


    def _should_seek_escape_package(self, state: GameState, player: PlayerState) -> bool:
        burden_count = sum(1 for c in player.trick_hand if c.name in {"무거운 짐", "가벼운 짐"})
        legal_marks = self._allowed_mark_targets(state, player)
        burden_context = self._burden_context(state, player, legal_targets=legal_marks)
        cleanup_pressure = burden_context["cleanup_pressure"]
        liquidity = self._liquidity_risk_metrics(state, player, player.current_character)
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        rent_pressure, _ = self._rent_pressure_breakdown(state, player, player.current_character or "")
        if rent_pressure >= 1.9 or float(survival_ctx.get("two_turn_lethal_prob", 0.0)) >= 0.18:
            return True
        if player.cash <= 8 and (burden_count >= 1 or liquidity["cash_after_reserve"] <= 0.0):
            return True
        if burden_count >= 1 and cleanup_pressure >= 2.5:
            return True
        if float(survival_ctx.get("cleanup_cash_gap", 0.0)) > 0.0 or float(survival_ctx.get("latent_cleanup_cost", 0.0)) >= max(8.0, player.cash * 0.9):
            return True
        return liquidity["cash_after_reserve"] <= -2.0 or float(survival_ctx.get("money_distress", 0.0)) >= 1.15

    def _distress_marker_bonus(self, state: GameState, player: PlayerState, candidate_names: list[str]) -> dict[str, float]:
        bonus = {name: 0.0 for name in candidate_names}
        if not candidate_names:
            return bonus
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        rescue_pressure = self._should_seek_escape_package(state, player)
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        denial_snapshot = self._leader_denial_snapshot(state, player) if self._is_v2_mode() else {"emergency": 0.0, "near_end": False, "top_threat": None}
        leader_emergency = float(denial_snapshot["emergency"])
        urgent_denial = self._is_v2_mode() and leader_emergency >= 2.0
        if not rescue_pressure and not urgent_denial and controller_need <= 0.0:
            return bonus
        rescue_names = self._escape_package_names()
        direct_denial_names = {"자객", "산적", "추노꾼", "사기꾼", "박수", "만신", "어사"}
        marker_names = self._marker_package_names()
        available_markers = [name for name in candidate_names if name in marker_names]
        if not available_markers:
            return bonus
        active_names = {name for name in state.active_by_card.values() if name}
        future_rescue_live = bool(active_names & rescue_names)
        direct_options = [name for name in candidate_names if name in direct_denial_names]
        marker_plan = self._leader_marker_flip_plan(state, player, denial_snapshot.get("top_threat")) if urgent_denial else {"best_score": 0.0}
        marker_counter = float(marker_plan["best_score"])
        base = 0.0
        if rescue_pressure and not any(name in rescue_names for name in candidate_names):
            base = max(base, 2.35 if future_rescue_live else 1.55)
        if controller_need > 0.0:
            base = max(base, 1.35 + 0.75 * controller_need + 0.20 * float(survival_ctx.get("money_distress", 0.0)))
        if urgent_denial:
            base = max(base, 1.55 + 0.30 * leader_emergency + 0.70 * marker_counter + (0.30 if denial_snapshot["near_end"] else 0.0))
            if direct_options:
                base -= 0.35
            if marker_counter <= 0.0 and direct_options and controller_need <= 0.0:
                return bonus
        for name in available_markers:
            bonus[name] = max(0.0, base)
            if state.marker_owner_id != player.player_id:
                bonus[name] += 0.55
        return bonus

    def choose_draft_card(self, state: GameState, player: PlayerState, offered_cards: list[int]) -> int:
        raise NotImplementedError

        raise NotImplementedError

    def choose_final_character(self, state: GameState, player: PlayerState, card_choices: list[int]) -> str:
        raise NotImplementedError

    def choose_mark_target(self, state: GameState, player: PlayerState, actor_name: str) -> Optional[str]:
        raise NotImplementedError

    def choose_doctrine_relief_target(self, state: GameState, player: PlayerState, candidates: list[PlayerState]) -> Optional[int]:
        if not candidates:
            return None
        for candidate in candidates:
            if candidate.player_id == player.player_id:
                return candidate.player_id
        return candidates[0].player_id

    def choose_geo_bonus(self, state: GameState, player: PlayerState, actor_name: str) -> str:
        raise NotImplementedError


    def choose_geo_bonus(self, state: GameState, player: PlayerState, actor_name: str) -> str:
        survival_ctx = self._generic_survival_context(state, player, actor_name)
        f_ctx = self._f_progress_context(state, player)
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        two_turn_lethal = float(survival_ctx.get("two_turn_lethal_prob", 0.0))
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))
        cleanup_cash_gap = float(survival_ctx.get("cleanup_cash_gap", 0.0))
        latent_cleanup_cost = float(survival_ctx.get("latent_cleanup_cost", 0.0))
        expected_cleanup_cost = float(survival_ctx.get("expected_cleanup_cost", 0.0))
        if self._is_v2_mode():
            cross_start = self._will_cross_start(state, player)
            land_f = self._will_land_on_f(state, player)
            coin_score = (1.8 if actor_name in {"객주"} else 0.8) + 0.8 * cross_start
            if actor_name == "중매꾼":
                coin_score += 0.55 + 0.25 * self._matchmaker_adjacent_value(state, player)
            elif actor_name == "건설업자":
                coin_score += 0.70 + 0.40 * self._builder_free_purchase_value(state, player)
            shard_score = (1.8 if actor_name in {"산적", "탐관오리", "아전"} else 0.6) + max(0.0, 0.7 * land_f * float(f_ctx["land_f_value"]))
            if actor_name == "중매꾼" and player.shards < 2:
                shard_score += 0.80
            if actor_name == "박수":
                # 폴백 임계(5개) 미달: 조각 선호. 임계 달성 후엔 현금/코인으로 전환 유도
                if player.shards < 5:
                    shard_score += 0.70 + 0.10 * (5 - player.shards)
                else:
                    shard_score -= 0.20  # 임계 달성 후 조각 선호 억제
            if actor_name == "만신":
                # 폴백 임계(7개) 미달이고 상대 짐이 있을 때 조각 선호
                # 임계 달성 후엔 현금/코인으로 전환 유도
                visible_enemy_burdens_geo = sum(
                    self._visible_burden_count(state.players[player.player_id], p)
                    for p in state.players
                    if p.alive and p.player_id != player.player_id
                )
                if player.shards < 7:
                    shard_score += 0.55 + 0.08 * (7 - player.shards)
                else:
                    shard_score -= 0.15  # 임계 달성 후 억제
                shard_score += 0.15 * min(2, visible_enemy_burdens_geo)  # 상대 짐 보너스 소폭만
            cash_score = 0.5 + 0.25 * max(0, 9 - player.cash)
            # [burden_patch] latent_cleanup_cost 가중치 0.12 → 0.45, expected 0.20 → 0.42
            # 짐을 들고 있을 때 랩 보상을 현금으로 전환하는 임계값을 낮춘다.
            # 짐 보유 수(own_burdens)가 많을수록 현금 선택 보너스 추가.
            own_burdens_count = float(survival_ctx.get("own_burdens", 0.0))
            burden_hold_bonus = 0.80 * own_burdens_count  # 짐 1장당 +0.80 현금 선호
            cash_score += 1.25 * money_distress + 2.10 * two_turn_lethal + 0.35 * controller_need + 0.15 * burden_cost + 0.55 * cleanup_cash_gap + 0.45 * latent_cleanup_cost + 0.42 * expected_cleanup_cost + burden_hold_bonus
            if not bool(f_ctx["is_leader"]):
                cash_score += 0.55 + 0.35 * float(f_ctx["avoid_f_acceleration"])
                shard_score -= 0.45 + 0.25 * float(f_ctx["avoid_f_acceleration"])
            if self._profile_from_mode() == "aggressive":
                coin_score += 1.0
            elif self._profile_from_mode() == "avoid_control":
                cash_score += 0.7
            elif self._profile_from_mode() == "token_opt":
                coin_score += 2.2 + 0.8 * cross_start + 0.5 * land_f
                shard_score += 0.3
            return max([("cash", cash_score), ("shards", shard_score), ("coins", coin_score)], key=lambda x: x[1])[0]
        if player.cash < 8 or money_distress >= 0.95 or two_turn_lethal >= 0.16 or not bool(f_ctx["is_leader"]):
            return "cash"
        if actor_name in {"산적", "탐관오리", "아전"}:
            return "shards"
        return "coins"

    def choose_active_flip_card(self, state: GameState, player: PlayerState, flippable_cards: list[int]) -> Optional[int]:
        raise NotImplementedError


class HeuristicPolicy(BasePolicy):
    character_values = {
        "어사": 6.0,
        "탐관오리": 7.5,
        "자객": 7.2,
        "산적": 7.0,
        "추노꾼": 6.8,
        "탈출 노비": 6.2,
        "파발꾼": 7.9,
        "아전": 7.0,
        "교리 연구관": 6.4,
        "교리 감독관": 6.4,
        "박수": 7.2,
        "만신": 6.9,
        "객주": 7.6,
        "중매꾼": 7.4,
        "건설업자": 7.8,
        "사기꾼": 7.7,
    }

    V2_PROFILES = {"control", "growth", "balanced", "avoid_control", "aggressive", "token_opt", "v3_claude"}
    VALID_CHARACTER_POLICIES = {"random", "arena", "heuristic_v1", *(f"heuristic_v2_{p}" for p in V2_PROFILES)}
    VALID_LAP_POLICIES = {"heuristic_v1", "cash_focus", "shard_focus", "coin_focus", "balanced", *(f"heuristic_v2_{p}" for p in V2_PROFILES)}
    PROFILE_WEIGHTS = {
        "control": {"expansion": 1.0, "economy": 1.1, "disruption": 1.7, "meta": 1.6, "combo": 1.0, "survival": 1.4},
        "growth": {"expansion": 1.8, "economy": 1.7, "disruption": 0.7, "meta": 0.9, "combo": 1.2, "survival": 1.0},
        "balanced": {"expansion": 1.2, "economy": 1.2, "disruption": 1.2, "meta": 1.1, "combo": 1.1, "survival": 1.1},
        "avoid_control": {"expansion": 1.0, "economy": 1.4, "disruption": 0.7, "meta": 1.0, "combo": 1.0, "survival": 1.8},
        "aggressive": {"expansion": 2.0, "economy": 1.0, "disruption": 1.3, "meta": 0.8, "combo": 1.5, "survival": 0.6},
        "token_opt": {"expansion": 1.5, "economy": 1.4, "disruption": 1.0, "meta": 1.0, "combo": 1.9, "survival": 0.9},
        # [v3_claude] 전략 원칙:
        #   ① 생존 최우선 + 우선권 인식 — 높은 우선권 인물로 지목 위협 회피,
        #      낮은 우선권 대상을 적극 지목해 상대 파산 유도
        #   ② 정보 기반 견제 — 덱 고갈 파악(짐 청산 이벤트 소진 후 짐 보유 허용),
        #      징표 제어로 리더 필수 인물을 inactive 처리
        #   ③ 자원 효율 — 조각은 임계까지만 적립, 초과 시 현금/코인 전환
        #      코인은 재방문 가능할 때만 투자, 그 외엔 현금 우선
        #   ④ 주사위 카드 절약 — 파산 회피 / 게임 종료 트리거에만 사용
        #   ⑤ 구매 + 견제 균형 — expansion을 balanced 수준으로 높여
        #      구매 기반 없이 생존만 추구하는 함정을 방지
        #   [v2 패치] expansion 1.1→1.6, survival 1.5→1.2, combo 1.0→1.3
        #            economy 1.3→1.4: 구매 기반이 없으면 메타/견제도 무의미
        "v3_claude": {"expansion": 1.6, "economy": 1.4, "disruption": 1.4, "meta": 1.5, "combo": 1.3, "survival": 1.2},
    }

    def __init__(self, character_policy_mode: str = "heuristic_v1", lap_policy_mode: str = "heuristic_v1", rng=None, player_lap_policy_modes: Optional[dict[int, str]] = None):
        super().__init__()
        if character_policy_mode not in self.VALID_CHARACTER_POLICIES:
            raise ValueError(f"Unsupported character_policy_mode: {character_policy_mode}")
        if lap_policy_mode not in self.VALID_LAP_POLICIES:
            raise ValueError(f"Unsupported lap_policy_mode: {lap_policy_mode}")
        self.character_policy_mode = character_policy_mode
        self.lap_policy_mode = lap_policy_mode
        self.player_lap_policy_modes = dict(player_lap_policy_modes or {})
        for pid, mode in self.player_lap_policy_modes.items():
            if mode not in self.VALID_LAP_POLICIES:
                raise ValueError(f"Unsupported lap policy for player {pid}: {mode}")
        self.rng = rng

    def set_rng(self, rng) -> None:
        self.rng = rng

    def _choice(self, values):
        values = list(values)
        if self.rng is not None:
            return self.rng.choice(values)
        import random
        return random.choice(values)

    def _rand_float(self) -> float:
        if self.rng is not None:
            return self.rng.random()
        import random
        return random.random()

    def _weighted_choice(self, values, weights):
        values = list(values)
        weights = [max(0.0, float(w)) for w in weights]
        total = sum(weights)
        if total <= 0.0:
            return self._choice(values)
        roll = self._rand_float() * total
        running = 0.0
        for value, weight in zip(values, weights):
            running += weight
            if roll <= running:
                return value
        return values[-1]

    def _set_debug(self, action: str, player_id: int, payload: dict[str, Any]) -> None:
        self._debug_choices[(action, player_id)] = payload

    def pop_debug(self, action: str, player_id: int) -> Optional[dict[str, Any]]:
        return self._debug_choices.pop((action, player_id), None)

    def choose_hidden_trick_card(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        if not hand:
            return None
        combo_priority = {"무료 증정", "마당발", "극심한 분리불안", "과속", "이럇!", "도움 닫기", "거대한 산불", "극도의 느슨함 혐오자", "성물 수집가"}
        def hide_score(card: TrickCard) -> tuple[float, int, int]:
            score = 0.0
            # [burden_patch v2] 짐 카드는 숨기면 안 된다.
            # 숨긴 짐은 supply 때 공개되어 청산 선택 기회가 생기지만,
            # 더 중요한 것은 짐을 상대에게 넘기거나(박수) 버릴 기회를 잃는다.
            # → 짐 점수를 강한 음수로 처리해 절대 숨기지 않도록.
            if card.is_burden:
                score -= 8.0 - card.burden_cost  # 무거운 짐: -4, 가벼운 짐: -6
            if card.name in combo_priority:
                score += 3.5
            if player.current_character in {"중매꾼", "건설업자"} and card.name in {"무료 증정", "마당발"}:
                score += 2.0
            if player.current_character == "파발꾼" and card.name in {"과속", "이럇!", "도움 닫기"}:
                score += 1.5
            if player.current_character in {"산적", "아전", "탐관오리"} and card.name == "성물 수집가":
                score += 1.5
            if card.is_anytime:
                score += 0.5
            return (score, card.burden_cost, card.deck_index)
        return max(hand, key=hide_score)

    def _remaining_cards(self, player: PlayerState) -> list[int]:
        return [v for v in range(1, 7) if v not in player.used_dice_cards]

    def _landing_score(self, state: GameState, player: PlayerState, pos: int) -> float:
        cell = state.board[pos]
        owner = state.tile_owner[pos]
        if cell == CellKind.T3:
            if owner is None:
                return 8.0
            if owner == player.player_id:
                return 4.0
            return -6.0
        if cell == CellKind.T2:
            if owner is None:
                return 6.5
            if owner == player.player_id:
                return 3.0
            return -4.0
        if cell == CellKind.MALICIOUS:
            return -8.0
        if cell == CellKind.F1:
            return 0.8
        if cell == CellKind.F2:
            return 1.1
        if cell == CellKind.S:
            return 0.8
        return 0.0

    def _is_random_mode(self) -> bool:
        return self.character_policy_mode == "random"

    def _is_v2_mode(self) -> bool:
        return self.character_policy_mode.startswith("heuristic_v2_")

    def _profile_from_mode(self, mode: str | None = None) -> str:
        mode = mode or self.character_policy_mode
        if mode.startswith("heuristic_v2_"):
            return mode.split("heuristic_v2_", 1)[1]
        return "balanced"

    def _lap_mode_for_player(self, player_id: int) -> str:
        return self.player_lap_policy_modes.get(player_id, self.lap_policy_mode)

    def _weights(self, mode: str | None = None) -> dict[str, float]:
        return self.PROFILE_WEIGHTS[self._profile_from_mode(mode)]

    def _moves_for_turn(self, player: PlayerState) -> list[int]:
        remaining = self._remaining_cards(player)
        moves = {2,3,4,5,6,7,8,9,10,11,12}
        moves.update(remaining)
        for a,b in combinations(remaining,2):
            moves.add(a+b)
        return sorted(moves)

    def _action_survival_guard_context(self, state: GameState, player: PlayerState, survival_ctx: dict[str, float] | None = None) -> dict[str, float]:
        survival_ctx = survival_ctx or self._generic_survival_context(state, player, player.current_character)
        signals = SurvivalSignals.from_mapping(survival_ctx)
        guard = build_action_guard_context(signals)
        return {
            "reserve_floor": float(guard.reserve_floor),
            "money_distress": float(guard.money_distress),
            "survival_urgency": float(guard.survival_urgency),
            "two_turn_lethal_prob": float(guard.two_turn_lethal_prob),
        }

    def _predict_tile_landing_cost(self, state: GameState, player: PlayerState, pos: int) -> float:
        owner = state.tile_owner[pos]
        cell = state.board[pos]
        if cell in {CellKind.T2, CellKind.T3}:
            if owner is None or owner == player.player_id:
                return 0.0
            if player.current_character == "사기꾼" and not self._takeover_protected(state, pos):
                return float(state.config.rules.economy.rent_cost_for(state, pos) * 2)
            return float(state.config.rules.economy.rent_cost_for(state, pos))
        if cell == CellKind.MALICIOUS:
            return float(state.config.rules.special_tiles.malicious_cost_for(state, pos))
        return 0.0

    def _is_action_survivable(self, state: GameState, player: PlayerState, *, immediate_cost: float = 0.0, post_action_cash: float | None = None, survival_ctx: dict[str, float] | None = None, reserve_floor: float | None = None, buffer: float = 0.0) -> bool:
        survival_ctx = survival_ctx or self._generic_survival_context(state, player, player.current_character)
        guard = self._action_survival_guard_context(state, player, survival_ctx=survival_ctx)
        effective_floor = float(guard["reserve_floor"] if reserve_floor is None else reserve_floor)
        return is_action_survivable(
            cash=float(player.cash),
            immediate_cost=float(immediate_cost),
            post_action_cash=None if post_action_cash is None else float(post_action_cash),
            reserve_floor=effective_floor,
            buffer=float(buffer),
        )

    def _predict_trick_cash_cost(self, card: TrickCard) -> float:
        if card.name == "무료 증정":
            return 3.0
        if card.name == "과속":
            return 2.0
        return 0.0


    def _perf_cache_bucket(self, state: GameState, bucket: str, signature: tuple[Any, ...]) -> dict[str, Any]:
        cache = getattr(self, "_perf_cache", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_perf_cache", cache)
        bucket_entry = cache.get(bucket)
        if bucket_entry is None or bucket_entry.get("signature") != signature:
            bucket_entry = {"signature": signature, "values": {}}
            cache[bucket] = bucket_entry
        return bucket_entry["values"]

    def _board_control_signature(self, state: GameState) -> tuple[Any, ...]:
        return (tuple(state.tile_owner), tuple(state.board), tuple(state.block_ids))

    def _race_signature(self, state: GameState) -> tuple[Any, ...]:
        return (
            float(state.f_value),
            tuple((p.player_id, p.alive, p.cash, p.shards, p.tiles_owned, p.position, p.current_character, float(state.total_score(p.player_id))) for p in state.players),
            tuple(state.tile_owner),
            tuple(state.board),
            tuple(state.block_ids),
        )

    def _movement_signature(self, state: GameState) -> tuple[Any, ...]:
        return tuple((p.player_id, p.position, p.cash) for p in state.players)

    def _board_control_stats(self, state: GameState) -> dict[str, Any]:
        cache = self._perf_cache_bucket(state, "board_control", self._board_control_signature(state))
        stats = cache.get("stats")
        if stats is not None:
            return stats
        block_tiles: dict[int, list[int]] = {}
        block_property_tiles: dict[int, list[int]] = {}
        own_counts: dict[int, dict[int, int]] = {}
        has_malicious_only: dict[int, bool] = {}
        valid_cells = {CellKind.T2, CellKind.T3, CellKind.MALICIOUS}
        property_cells = {CellKind.T2, CellKind.T3}
        for idx, bid in enumerate(state.block_ids):
            if bid < 0:
                continue
            cell = state.board[idx]
            if cell not in valid_cells:
                continue
            block_tiles.setdefault(bid, []).append(idx)
            if cell in property_cells:
                block_property_tiles.setdefault(bid, []).append(idx)
            owner = state.tile_owner[idx]
            if owner is not None:
                owner_map = own_counts.setdefault(bid, {})
                owner_map[owner] = owner_map.get(owner, 0) + 1
        exclusive_blocks_by_owner: dict[int, int] = {}
        for bid, idxs in block_tiles.items():
            property_idxs = block_property_tiles.get(bid, [])
            if not property_idxs:
                continue
            owners = {state.tile_owner[i] for i in idxs if state.tile_owner[i] is not None}
            if len(owners) == 1:
                owner = next(iter(owners))
                exclusive_blocks_by_owner[owner] = exclusive_blocks_by_owner.get(owner, 0) + 1
        stats = {
            "block_tiles": block_tiles,
            "block_property_tiles": block_property_tiles,
            "owner_counts": own_counts,
            "exclusive_blocks_by_owner": exclusive_blocks_by_owner,
        }
        cache["stats"] = stats
        return stats

    def _race_snapshot(self, state: GameState) -> dict[str, Any]:
        cache = self._perf_cache_bucket(state, "race", self._race_signature(state))
        snapshot = cache.get("snapshot")
        if snapshot is not None:
            return snapshot
        f_threshold = float(state.config.rules.end.f_threshold or 0.0)
        f_remaining = max(0.0, f_threshold - float(state.f_value)) if f_threshold > 0 else 0.0
        alive = [p for p in state.players if p.alive]
        if not alive:
            snapshot = {
                "f_remaining": float(f_remaining),
                "board_scores": {},
                "contexts": {},
                "leader_score": 0.0,
                "second_score": 0.0,
                "alive_count": 0,
            }
            cache["snapshot"] = snapshot
            return snapshot
        board_scores: dict[int, float] = {}
        monopolies_by_owner = self._board_control_stats(state)["exclusive_blocks_by_owner"]
        t3_owned_by_owner: dict[int, int] = {}
        for idx, owner in enumerate(state.tile_owner):
            if owner is not None and state.board[idx] == CellKind.T3:
                t3_owned_by_owner[owner] = t3_owned_by_owner.get(owner, 0) + 1
        for p in alive:
            score = float(state.total_score(p.player_id))
            score += 0.60 * float(p.tiles_owned)
            score += 0.10 * float(p.cash)
            score += 0.22 * float(p.shards)
            score += 0.70 * float(t3_owned_by_owner.get(p.player_id, 0))
            score += 1.80 * float(monopolies_by_owner.get(p.player_id, 0))
            if p.tiles_owned >= 5:
                score += 0.85 + 0.35 * float(p.tiles_owned - 5)
            board_scores[p.player_id] = score
        scored = sorted(((score, pid) for pid, score in board_scores.items()), reverse=True)
        leader_score = float(scored[0][0])
        second_score = float(scored[1][0]) if len(scored) >= 2 else leader_score
        contexts: dict[int, dict[str, float | int | bool]] = {}
        for score, pid in scored:
            rank = 1 + sum(1 for other_score, other_pid in scored if other_pid != pid and other_score > score + 1e-9)
            is_leader = score >= leader_score - 0.35
            leader_gap = max(0.0, leader_score - score)
            lead_margin = max(0.0, score - second_score) if is_leader else 0.0
            near_leader = is_leader or leader_gap <= 0.75
            contexts[pid] = {
                "is_leader": bool(is_leader),
                "rank": int(rank),
                "leader_gap": float(leader_gap),
                "lead_margin": float(lead_margin),
                "f_remaining": float(f_remaining),
                "near_leader": bool(near_leader),
            }
        snapshot = {
            "f_remaining": float(f_remaining),
            "board_scores": board_scores,
            "contexts": contexts,
            "leader_score": leader_score,
            "second_score": second_score,
            "alive_count": len(alive),
        }
        cache["snapshot"] = snapshot
        return snapshot

    def _will_cross_start(self, state: GameState, player: PlayerState) -> float:
        cache = self._perf_cache_bucket(state, "movement_eval", self._movement_signature(state))
        key = ("cross_start", player.player_id)
        if key in cache:
            return float(cache[key])
        moves = self._moves_for_turn(player)
        if not moves:
            cache[key] = 0.0
            return 0.0
        board_len = len(state.board)
        cnt = sum(1 for m in moves if player.position + m >= board_len)
        cache[key] = cnt / len(moves)
        return float(cache[key])

    def _will_land_on_f(self, state: GameState, player: PlayerState) -> float:
        cache = self._perf_cache_bucket(state, "movement_eval", self._movement_signature(state))
        key = ("land_on_f", player.player_id)
        if key in cache:
            return float(cache[key])
        moves = self._moves_for_turn(player)
        if not moves:
            cache[key] = 0.0
            return 0.0
        board_len = len(state.board)
        cnt = 0
        for m in moves:
            pos = (player.position + m) % board_len
            if state.board[pos] in {CellKind.F1, CellKind.F2}:
                cnt += 1
        cache[key] = cnt / len(moves)
        return float(cache[key])

    def _board_race_score(self, state: GameState, player: PlayerState) -> float:
        snapshot = self._race_snapshot(state)
        board_scores = snapshot["board_scores"]
        if player.player_id in board_scores:
            return float(board_scores[player.player_id])
        score = float(state.total_score(player.player_id))
        score += 0.60 * float(player.tiles_owned)
        score += 0.10 * float(player.cash)
        score += 0.22 * float(player.shards)
        return score

    def _race_position_context(self, state: GameState, player: PlayerState) -> dict[str, float | int | bool]:
        snapshot = self._race_snapshot(state)
        contexts = snapshot["contexts"]
        if player.player_id in contexts:
            return dict(contexts[player.player_id])
        f_remaining = float(snapshot["f_remaining"])
        leader_score = float(snapshot["leader_score"])
        return {
            "is_leader": False,
            "rank": int(snapshot["alive_count"]) + 1,
            "leader_gap": max(0.0, leader_score - float(self._board_race_score(state, player))),
            "lead_margin": 0.0,
            "f_remaining": f_remaining,
            "near_leader": False,
        }

    def _f_progress_context(self, state: GameState, player: PlayerState) -> dict[str, float | bool | int]:
        race = self._race_position_context(state, player)
        f_remaining = float(race["f_remaining"])
        is_leader = bool(race["is_leader"])
        near_leader = bool(race["near_leader"])
        leader_gap = float(race["leader_gap"])
        lead_margin = float(race["lead_margin"])

        land_f_value = 0.10
        card_f_penalty = 0.0
        if is_leader:
            land_f_value = 0.35
            if f_remaining <= 6.0:
                land_f_value += 0.45
            if f_remaining <= 3.0:
                land_f_value += 0.35
            if lead_margin >= 1.0:
                land_f_value += 0.15
            card_f_penalty = -0.15 if f_remaining <= 5.0 else 0.10
        elif near_leader and f_remaining <= 2.0:
            land_f_value = 0.05
            card_f_penalty = 0.20
        else:
            land_f_value = -0.65
            if f_remaining <= 3.0:
                land_f_value = -0.45
            card_f_penalty = 1.25
            if f_remaining > 5.0:
                card_f_penalty += 0.30
            if leader_gap >= 1.0:
                card_f_penalty += 0.25

        return {
            "is_leader": is_leader,
            "near_leader": near_leader,
            "rank": int(race["rank"]),
            "leader_gap": leader_gap,
            "lead_margin": lead_margin,
            "f_remaining": f_remaining,
            "land_f_value": float(land_f_value),
            "card_f_penalty": float(card_f_penalty),
            "avoid_f_acceleration": 0.0 if is_leader else max(0.0, -float(land_f_value)),
        }

    def _expected_buy_value(self, state: GameState, player: PlayerState) -> float:
        cache = self._perf_cache_bucket(state, "movement_eval", self._movement_signature(state))
        key = ("expected_buy_value", player.player_id, player.cash)
        if key in cache:
            return float(cache[key])
        moves = self._moves_for_turn(player)
        board_len = len(state.board)
        vals=[]
        for m in moves:
            pos=(player.position+m)%board_len
            cell=state.board[pos]
            if cell not in {CellKind.T2, CellKind.T3}:
                continue
            if state.tile_owner[pos] is None and player.cash >= state.config.rules.economy.purchase_cost_for(state, pos):
                vals.append(2.0 if cell==CellKind.T2 else 3.4)
        cache[key] = max(vals) if vals else 0.0
        return float(cache[key])

    def _estimated_threat(self, state: GameState, viewer: PlayerState, opponent: PlayerState) -> float:
        score = self._board_race_score(state, opponent)
        race = self._race_position_context(state, opponent)
        geo_factor = 0.15
        if bool(race["is_leader"]):
            geo_factor = 1.0
        elif bool(race["near_leader"]) and float(race["f_remaining"]) <= 2.0:
            geo_factor = 0.35
        score += geo_factor * (1.10 * self._will_cross_start(state, opponent) + 0.85 * self._will_land_on_f(state, opponent))
        if state.config.rules.end.tiles_to_trigger_end and opponent.tiles_owned >= state.config.rules.end.tiles_to_trigger_end - 1:
            score += 3.5
        if self._exclusive_blocks_owned(state, opponent.player_id) >= max(1, state.config.rules.end.monopolies_to_trigger_end - 1):
            score += 2.5
        if opponent.current_character in {"중매꾼", "건설업자", "객주", "사기꾼"}:
            score += 1.8
        if self._visible_burden_count(viewer, opponent) >= 2:
            score -= 0.6
        return score

    def _predicted_opponent_archetypes(self, state: GameState, viewer: PlayerState, opponent: PlayerState) -> set[str]:
        tags=set()
        race = self._race_position_context(state, opponent)
        if bool(race["is_leader"]) and (self._will_cross_start(state, opponent) > 0.35 or self._will_land_on_f(state, opponent) > 0.2):
            tags.add("geo")
        elif bool(race["near_leader"]) and float(race["f_remaining"]) <= 2.0 and self._will_land_on_f(state, opponent) > 0.25:
            tags.add("geo")
        if self._expected_buy_value(state, opponent) > 0:
            tags.add("expansion")
        if opponent.shards >= 4:
            tags.add("shard_attack")
        visible_names = self._visible_trick_names(viewer, opponent)
        if self._visible_burden_count(viewer, opponent) > 0:
            tags.add("burden")
        if opponent.cash >= 16:
            tags.add("cash_rich")
        if visible_names & {"과속", "이럇!", "도움 닫기", "극심한 분리불안", "무료 증정", "마당발"}:
            tags.add("combo_ready")
        if opponent.tiles_owned >= 5:
            tags.add("leader")
        if self._exclusive_blocks_owned(state, opponent.player_id) > 0:
            tags.add("monopoly")
        return tags

    def _exclusive_blocks_owned(self, state: GameState, player_id: int) -> int:
        stats = self._board_control_stats(state)
        return int(stats["exclusive_blocks_by_owner"].get(player_id, 0))

    def _alive_enemies(self, state: GameState, player: PlayerState) -> list[PlayerState]:
        return [p for p in state.players if p.alive and p.player_id != player.player_id]

    def _visible_tricks(self, viewer: PlayerState, target: PlayerState) -> list[TrickCard]:
        if viewer.player_id == target.player_id:
            return list(target.trick_hand)
        return list(target.public_trick_cards())

    def _visible_trick_names(self, viewer: PlayerState, target: PlayerState) -> set[str]:
        return {c.name for c in self._visible_tricks(viewer, target)}

    def _visible_burden_count(self, viewer: PlayerState, target: PlayerState) -> int:
        return sum(1 for c in self._visible_tricks(viewer, target) if c.name in {"무거운 짐", "가벼운 짐"})



    def _monopoly_block_metrics(self, state: GameState, player: PlayerState) -> dict[str, float]:
        own_complete_now = 0
        own_near_complete = 0
        own_progress_peak = 0
        own_claimable_blocks = 0
        deny_now = 0
        enemy_near_complete = 0
        enemy_progress_peak = 0
        enemy_claimable_blocks = 0
        contested_blocks = 0
        my_id = player.player_id
        alive_enemy_ids = {p.player_id for p in state.players if p.alive and p.player_id != my_id}
        for bid in sorted(set(b for b in state.block_ids if b >= 0)):
            idxs = [i for i, b in enumerate(state.block_ids) if b == bid and state.board[i] in {CellKind.T2, CellKind.T3}]
            if len(idxs) < 2:
                continue
            owners = [state.tile_owner[i] for i in idxs]
            my_owned = sum(1 for own in owners if own == my_id)
            unowned = sum(1 for own in owners if own is None)
            enemy_owned_by = {own for own in owners if own is not None and own != my_id}
            own_progress_peak = max(own_progress_peak, my_owned)
            if my_owned == len(idxs):
                own_complete_now += 1
            elif my_owned == len(idxs) - 1 and unowned == 1 and not enemy_owned_by:
                own_near_complete += 1
            if my_owned > 0 and unowned > 0 and not enemy_owned_by:
                own_claimable_blocks += 1
            if my_owned > 0 and enemy_owned_by:
                contested_blocks += 1
            for enemy_id in alive_enemy_ids:
                enemy_owned = sum(1 for own in owners if own == enemy_id)
                enemy_progress_peak = max(enemy_progress_peak, enemy_owned)
                if enemy_owned == len(idxs) - 1 and unowned == 1 and my_owned == 0 and len(enemy_owned_by) == 1:
                    enemy_near_complete += 1
                    if state.tile_owner[next(i for i in idxs if state.tile_owner[i] is None)] is None:
                        deny_now += 1
                if enemy_owned > 0 and unowned > 0 and my_owned == 0 and (enemy_owned_by == {enemy_id}):
                    enemy_claimable_blocks += 1
        return {
            "own_complete_now": float(own_complete_now),
            "own_near_complete": float(own_near_complete),
            "own_progress_peak": float(own_progress_peak),
            "own_claimable_blocks": float(own_claimable_blocks),
            "deny_now": float(deny_now),
            "enemy_near_complete": float(enemy_near_complete),
            "enemy_progress_peak": float(enemy_progress_peak),
            "enemy_claimable_blocks": float(enemy_claimable_blocks),
            "contested_blocks": float(contested_blocks),
        }

    def _scammer_takeover_metrics(self, state: GameState, player: PlayerState) -> dict[str, float]:
        my_id = player.player_id
        coin_value = 0.0
        best_tile_coins = 0.0
        blocks_enemy_monopoly = 0.0
        finishes_own_monopoly = 0.0
        for pos, owner in enumerate(state.tile_owner):
            if owner is None or owner == my_id:
                continue
            if state.board[pos] not in {CellKind.T2, CellKind.T3}:
                continue
            if self._takeover_protected(state, pos):
                continue
            coins = float(state.tile_coins[pos])
            coin_value += coins
            best_tile_coins = max(best_tile_coins, coins)
            if self._would_block_enemy_monopoly_with_takeover(state, player, pos):
                blocks_enemy_monopoly += 1.0 + 0.4 * coins
            if self._would_finish_own_monopoly_with_takeover(state, player, pos):
                finishes_own_monopoly += 1.0 + 0.4 * coins
        return {
            "coin_value": coin_value,
            "best_tile_coins": best_tile_coins,
            "blocks_enemy_monopoly": blocks_enemy_monopoly,
            "finishes_own_monopoly": finishes_own_monopoly,
        }

    def _takeover_protected(self, state: GameState, pos: int) -> bool:
        block_id = state.block_ids[pos]
        if block_id < 0:
            return False
        idxs = [i for i, b in enumerate(state.block_ids) if b == block_id and state.board[i] in {CellKind.T2, CellKind.T3}]
        owners = {state.tile_owner[i] for i in idxs if state.tile_owner[i] is not None}
        return len(owners) == 1 and len(idxs) > 0 and len([i for i in idxs if state.tile_owner[i] == next(iter(owners))]) == len(idxs)

    def _would_block_enemy_monopoly_with_takeover(self, state: GameState, player: PlayerState, pos: int) -> bool:
        owner = state.tile_owner[pos]
        block_id = state.block_ids[pos]
        if owner is None or owner == player.player_id or block_id < 0:
            return False
        idxs = [i for i, b in enumerate(state.block_ids) if b == block_id and state.board[i] in {CellKind.T2, CellKind.T3}]
        if len(idxs) < 2:
            return False
        owners = [state.tile_owner[i] for i in idxs]
        enemy_owned = sum(1 for own in owners if own == owner)
        my_owned = sum(1 for own in owners if own == player.player_id)
        unowned = sum(1 for own in owners if own is None)
        return enemy_owned == len(idxs) - 1 and my_owned == 0 and unowned <= 1 and pos in idxs

    def _would_finish_own_monopoly_with_takeover(self, state: GameState, player: PlayerState, pos: int) -> bool:
        owner = state.tile_owner[pos]
        block_id = state.block_ids[pos]
        if owner is None or owner == player.player_id or block_id < 0:
            return False
        idxs = [i for i, b in enumerate(state.block_ids) if b == block_id and state.board[i] in {CellKind.T2, CellKind.T3}]
        if len(idxs) < 2:
            return False
        owners = [state.tile_owner[i] for i in idxs]
        my_owned = sum(1 for own in owners if own == player.player_id)
        enemy_owned = sum(1 for own in owners if own == owner)
        others = {own for own in owners if own is not None and own not in {player.player_id, owner}}
        return my_owned == len(idxs) - 1 and enemy_owned == 1 and not others and pos in idxs

    def _would_block_enemy_monopoly_with_purchase(self, state: GameState, player: PlayerState, pos: int) -> bool:
        block_id = state.block_ids[pos]
        if block_id < 0 or state.tile_owner[pos] is not None:
            return False
        idxs = [i for i, bid in enumerate(state.block_ids) if bid == block_id and state.board[i] in {CellKind.T2, CellKind.T3}]
        if len(idxs) < 2:
            return False
        owners = [state.tile_owner[i] for i in idxs if i != pos]
        enemy_ids = {own for own in owners if own is not None and own != player.player_id}
        if len(enemy_ids) != 1:
            return False
        enemy_id = next(iter(enemy_ids))
        enemy_owned = sum(1 for own in owners if own == enemy_id)
        others = sum(1 for own in owners if own not in {None, enemy_id})
        unowned_other = sum(1 for i in idxs if i != pos and state.tile_owner[i] is None)
        return others == 0 and enemy_owned == len(idxs) - 1 and unowned_other == 0

    def _fortune_cleanup_deck_profile(self, state: GameState) -> dict[str, float]:
        def _count_cleanup(cards: list[Any]) -> tuple[int, int]:
            fire = 0
            wildfire = 0
            for card in cards:
                name = getattr(card, "name", "")
                if name == "화재 발생":
                    fire += 1
                elif name == "산불 발생":
                    wildfire += 1
            return fire, wildfire

        def _at_least_one_prob(total_cards: int, success_cards: int, draws: int) -> float:
            if total_cards <= 0 or success_cards <= 0 or draws <= 0:
                return 0.0
            draws = min(draws, total_cards)
            failures = total_cards - success_cards
            if draws > failures:
                return 1.0
            try:
                no_success = math.comb(failures, draws) / math.comb(total_cards, draws)
            except ValueError:
                return 0.0
            return max(0.0, min(1.0, 1.0 - no_success))

        draw_pile = list(getattr(state, "fortune_draw_pile", []) or [])
        discard_pile = list(getattr(state, "fortune_discard_pile", []) or [])
        source = draw_pile if draw_pile else discard_pile
        remaining_draws = len(source)
        fire_count, wildfire_count = _count_cleanup(source)
        cleanup_cards = fire_count + wildfire_count

        total_cycle_cards = len(draw_pile) + len(discard_pile)
        cycle_fire_count, cycle_wildfire_count = _count_cleanup(draw_pile + discard_pile)
        total_cleanup_cards = cycle_fire_count + cycle_wildfire_count

        next_draw_cleanup_prob = (cleanup_cards / remaining_draws) if remaining_draws > 0 else 0.0
        two_draw_cleanup_prob = _at_least_one_prob(remaining_draws, cleanup_cards, 2)
        three_draw_cleanup_prob = _at_least_one_prob(remaining_draws, cleanup_cards, 3)
        cycle_cleanup_prob = (total_cleanup_cards / total_cycle_cards) if total_cycle_cards > 0 else 0.0

        conditional_multiplier = (
            ((1.0 * cycle_fire_count) + (2.0 * cycle_wildfire_count)) / total_cleanup_cards
            if total_cleanup_cards > 0
            else 0.0
        )
        next_draw_expected_factor = next_draw_cleanup_prob * conditional_multiplier
        persistent_expected_factor = cycle_cleanup_prob * conditional_multiplier
        two_draw_expected_factor = two_draw_cleanup_prob * conditional_multiplier
        three_draw_expected_factor = three_draw_cleanup_prob * conditional_multiplier
        worst_multiplier = 2.0 if cycle_wildfire_count > 0 else 1.0 if cycle_fire_count > 0 else 0.0
        return {
            "remaining_draws": float(remaining_draws),
            "remaining_fire_count": float(fire_count),
            "remaining_wildfire_count": float(wildfire_count),
            "remaining_cleanup_cards": float(cleanup_cards),
            "next_draw_cleanup_prob": float(next_draw_cleanup_prob),
            "two_draw_cleanup_prob": float(two_draw_cleanup_prob),
            "three_draw_cleanup_prob": float(three_draw_cleanup_prob),
            "cycle_cleanup_prob": float(cycle_cleanup_prob),
            "conditional_cleanup_multiplier": float(conditional_multiplier),
            "expected_cleanup_multiplier": float(next_draw_expected_factor),
            "persistent_expected_cleanup_multiplier": float(persistent_expected_factor),
            "two_draw_expected_cleanup_multiplier": float(two_draw_expected_factor),
            "three_draw_expected_cleanup_multiplier": float(three_draw_expected_factor),
            "worst_cleanup_multiplier": float(worst_multiplier),
            "reshuffle_imminent": 1.0 if (not draw_pile and bool(discard_pile)) else 0.0,
        }

    def _project_end_turn_cash(self, state: GameState, player: PlayerState, *, immediate_cost: float = 0.0, crosses_start: bool = False) -> float:
        cash = float(player.cash) - max(0.0, float(immediate_cost))
        if crosses_start:
            cash += float(getattr(state.config.rules.economy, "lap_cash_reward", 0) or 0)
        return max(0.0, cash)

    def _end_turn_cleanup_pressure(self, state: GameState, player: PlayerState, projected_cash: float, burden_context: Optional[dict[str, float]] = None) -> dict[str, float]:
        burden_context = burden_context or self._burden_context(state, player)
        own_burden_cost = float(burden_context.get("own_burden_cost", 0.0))
        immediate_factor = float(burden_context.get("deck_expected_cleanup_multiplier", 0.0))
        persistent_factor = float(burden_context.get("deck_persistent_cleanup_multiplier", 0.0))
        two_draw_factor = float(burden_context.get("deck_two_draw_expected_cleanup_multiplier", 0.0))
        worst_multiplier = float(burden_context.get("deck_worst_cleanup_multiplier", 0.0))
        cleanup_prob = float(burden_context.get("deck_next_draw_cleanup_prob", 0.0))
        two_draw_prob = float(burden_context.get("deck_two_draw_cleanup_prob", 0.0))
        cycle_prob = float(burden_context.get("deck_cycle_cleanup_prob", 0.0))
        immediate_cost = own_burden_cost * immediate_factor
        expected_cost = own_burden_cost * max(persistent_factor, two_draw_factor)
        worst_cost = own_burden_cost * worst_multiplier
        immediate_gap = max(0.0, immediate_cost - projected_cash)
        expected_gap = max(0.0, expected_cost - projected_cash)
        worst_gap = max(0.0, worst_cost - projected_cash)
        lethal_prob = 0.0
        if own_burden_cost > projected_cash and worst_cost > 0.0:
            lethal_prob = max(cleanup_prob, 0.7 * two_draw_prob, 0.45 * cycle_prob)
        return {
            "projected_cash": float(projected_cash),
            "immediate_cleanup_cost": float(immediate_cost),
            "expected_cleanup_cost": float(expected_cost),
            "worst_cleanup_cost": float(worst_cost),
            "immediate_cleanup_gap": float(immediate_gap),
            "expected_cleanup_gap": float(expected_gap),
            "worst_cleanup_gap": float(worst_gap),
            "next_draw_cleanup_prob": float(cleanup_prob),
            "two_draw_cleanup_prob": float(two_draw_prob),
            "cycle_cleanup_prob": float(cycle_prob),
            "projected_cleanup_lethal": float(lethal_prob),
        }

    def _burden_context(self, state: GameState, viewer: PlayerState, legal_targets: Optional[list[PlayerState]] = None) -> dict[str, float]:
        own_burden = sum(1 for c in viewer.trick_hand if c.is_burden)
        own_burden_cost = sum(float(c.burden_cost) for c in viewer.trick_hand if c.is_burden)
        alive_players = [p for p in state.players if p.alive]
        visible_other_burdens = sum(self._visible_burden_count(viewer, p) for p in alive_players if p.player_id != viewer.player_id)
        visible_all_burdens = own_burden + visible_other_burdens
        burden_holders = 0
        for p in alive_players:
            burden = own_burden if p.player_id == viewer.player_id else self._visible_burden_count(viewer, p)
            if burden > 0:
                burden_holders += 1
        other_hidden_slots = sum(p.hidden_trick_count() for p in alive_players if p.player_id != viewer.player_id and p.trick_hand)
        visible_cards = len(viewer.trick_hand) + sum(len(self._visible_tricks(viewer, p)) for p in alive_players if p.player_id != viewer.player_id)
        burden_density = visible_all_burdens / max(1, visible_cards)
        hidden_burden_estimate = other_hidden_slots * min(0.45, max(0.08, burden_density * 1.15))
        cleanup_pressure = visible_all_burdens + 0.35 * burden_holders + hidden_burden_estimate
        supply_gap = max(0.0, float(state.next_supply_f_threshold) - float(state.f_value))
        if supply_gap >= 2.0:
            cleanup_pressure *= 1.15
        elif supply_gap <= 0.5:
            cleanup_pressure *= 0.9
        public_cleanup_active = any(name in CLEANUP_THREAT_WEATHERS for name in state.current_weather_effects)
        deck_cleanup = self._fortune_cleanup_deck_profile(state)
        if public_cleanup_active:
            cleanup_pressure *= 1.15
        cleanup_pressure += (
            0.36 * float(deck_cleanup["next_draw_cleanup_prob"])
            + 0.24 * float(deck_cleanup["two_draw_cleanup_prob"])
            + 0.18 * float(deck_cleanup["cycle_cleanup_prob"])
            + 0.14 * float(deck_cleanup["conditional_cleanup_multiplier"])
        )
        legal_targets = list(legal_targets if legal_targets is not None else self._allowed_mark_targets(state, viewer))
        legal_visible_burden_total = sum(self._visible_burden_count(viewer, p) for p in legal_targets)
        legal_visible_burden_peak = max((self._visible_burden_count(viewer, p) for p in legal_targets), default=0)
        legal_low_cash_targets = sum(1 for p in legal_targets if p.cash <= 12)
        deck_expected_cleanup_multiplier = float(deck_cleanup["expected_cleanup_multiplier"])
        deck_persistent_cleanup_multiplier = float(deck_cleanup["persistent_expected_cleanup_multiplier"])
        deck_two_draw_expected_cleanup_multiplier = float(deck_cleanup["two_draw_expected_cleanup_multiplier"])
        deck_worst_cleanup_multiplier = float(deck_cleanup["worst_cleanup_multiplier"])
        deck_next_draw_cleanup_prob = float(deck_cleanup["next_draw_cleanup_prob"])
        deck_two_draw_cleanup_prob = float(deck_cleanup["two_draw_cleanup_prob"])
        deck_cycle_cleanup_prob = float(deck_cleanup["cycle_cleanup_prob"])
        latent_cleanup_factor = max(deck_expected_cleanup_multiplier, deck_two_draw_expected_cleanup_multiplier, deck_persistent_cleanup_multiplier)
        latent_cleanup_cost = own_burden_cost * latent_cleanup_factor if own_burden_cost > 0.0 else 0.0
        expected_cleanup_cost = own_burden_cost * max(deck_two_draw_expected_cleanup_multiplier, deck_persistent_cleanup_multiplier) if own_burden_cost > 0.0 else 0.0
        active_cleanup_cost = own_burden_cost * max(float(deck_cleanup["conditional_cleanup_multiplier"]), 1.0) if public_cleanup_active and own_burden_cost > 0.0 else 0.0
        cleanup_cash_gap = max(0.0, active_cleanup_cost - float(viewer.cash))
        latent_cleanup_gap = max(0.0, latent_cleanup_cost - float(viewer.cash))
        expected_cleanup_gap = max(0.0, expected_cleanup_cost - float(viewer.cash))
        return {
            "own_burdens": float(own_burden),
            "own_burden_cost": float(own_burden_cost),
            "visible_all_burdens": float(visible_all_burdens),
            "cleanup_pressure": float(cleanup_pressure),
            "burden_holders": float(burden_holders),
            "hidden_burden_estimate": float(hidden_burden_estimate),
            "legal_visible_burden_total": float(legal_visible_burden_total),
            "legal_visible_burden_peak": float(legal_visible_burden_peak),
            "legal_low_cash_targets": float(legal_low_cash_targets),
            "public_cleanup_active": 1.0 if public_cleanup_active else 0.0,
            "active_cleanup_cost": float(active_cleanup_cost),
            "latent_cleanup_cost": float(latent_cleanup_cost),
            "expected_cleanup_cost": float(expected_cleanup_cost),
            "cleanup_cash_gap": float(cleanup_cash_gap),
            "latent_cleanup_gap": float(latent_cleanup_gap),
            "expected_cleanup_gap": float(expected_cleanup_gap),
            "deck_expected_cleanup_multiplier": float(deck_expected_cleanup_multiplier),
            "deck_persistent_cleanup_multiplier": float(deck_persistent_cleanup_multiplier),
            "deck_two_draw_expected_cleanup_multiplier": float(deck_two_draw_expected_cleanup_multiplier),
            "deck_worst_cleanup_multiplier": float(deck_worst_cleanup_multiplier),
            "deck_next_draw_cleanup_prob": float(deck_next_draw_cleanup_prob),
            "deck_two_draw_cleanup_prob": float(deck_two_draw_cleanup_prob),
            "deck_cycle_cleanup_prob": float(deck_cycle_cleanup_prob),
        }

    def _leader_pressure(self, state: GameState, player: PlayerState, opponent: PlayerState | None) -> float:
        if opponent is None:
            return 0.0
        gap = max(0, opponent.tiles_owned - player.tiles_owned)
        pressure = 0.8 * gap + 1.0 * self._exclusive_blocks_owned(state, opponent.player_id)
        if opponent.tiles_owned >= 5:
            pressure += 2.0
        if state.config.rules.end.tiles_to_trigger_end and opponent.tiles_owned >= state.config.rules.end.tiles_to_trigger_end - 1:
            pressure += 2.5
        if self._exclusive_blocks_owned(state, opponent.player_id) >= max(1, state.config.rules.end.monopolies_to_trigger_end - 1):
            pressure += 2.0
        return pressure

    def _leader_denial_snapshot(
        self,
        state: GameState,
        player: PlayerState,
        threat_targets: Optional[list[PlayerState]] = None,
        top_threat: Optional[PlayerState] = None,
    ) -> dict[str, Any]:
        threat_targets = list(threat_targets) if threat_targets is not None else sorted(
            self._alive_enemies(state, player),
            key=lambda op: self._estimated_threat(state, player, op),
            reverse=True,
        )
        top_threat = top_threat or (threat_targets[0] if threat_targets else None)
        if top_threat is None:
            return {
                "top_threat": None,
                "leader_margin": 0.0,
                "solo_leader": False,
                "near_end": False,
                "emergency": 0.0,
            }
        top_score = self._estimated_threat(state, player, top_threat)
        second_score = self._estimated_threat(state, player, threat_targets[1]) if len(threat_targets) >= 2 else 0.0
        second_tiles = threat_targets[1].tiles_owned if len(threat_targets) >= 2 else 0
        viewer_score = self._board_race_score(state, player)
        leader_margin = max(0.0, top_score - second_score)
        solo_leader = leader_margin >= 2.0 or top_threat.tiles_owned >= second_tiles + 2
        end_tiles = state.config.rules.end.tiles_to_trigger_end or 0
        near_end = bool(end_tiles and top_threat.tiles_owned >= end_tiles - 3)
        emergency = 0.0
        if top_score <= viewer_score + 0.5 and not near_end and top_threat.tiles_owned < 6:
            solo_leader = False
            leader_margin = 0.0
        if top_threat.tiles_owned >= 6:
            emergency += 1.2 + 0.7 * (top_threat.tiles_owned - 6)
        if near_end:
            emergency += 1.1 + 0.45 * max(0, top_threat.tiles_owned - (end_tiles - 3))
        if solo_leader:
            emergency += 1.15
        if self._exclusive_blocks_owned(state, top_threat.player_id) >= max(1, state.config.rules.end.monopolies_to_trigger_end - 1):
            emergency += 0.8
        return {
            "top_threat": top_threat,
            "leader_margin": float(leader_margin),
            "solo_leader": solo_leader,
            "near_end": near_end,
            "emergency": float(emergency),
        }


    def _control_finisher_window(self, player: PlayerState) -> tuple[float, str]:
        turns = float(getattr(player, "control_finisher_turns", 0) or 0)
        if turns <= 0.0:
            return 0.0, ""
        reason = getattr(player, "control_finisher_reason", "") or "leader_disrupted"
        return min(2.0, turns), reason

    def _leader_needed_character_weights(self, state: GameState, viewer: PlayerState, leader: Optional[PlayerState]) -> tuple[dict[str, float], list[str]]:
        weights: dict[str, float] = {}
        reasons: list[str] = []
        if leader is None or not leader.alive:
            return weights, reasons

        def add(names: set[str] | list[str] | tuple[str, ...], amount: float, reason: str) -> None:
            if amount <= 0.0:
                return
            for name in names:
                weights[name] = weights.get(name, 0.0) + amount
            reasons.append(f"{reason}={amount:.2f}")

        buy_value = self._expected_buy_value(state, leader)
        monopoly = self._monopoly_block_metrics(state, leader)
        cross_start = self._will_cross_start(state, leader)
        land_f = self._will_land_on_f(state, leader)
        leader_liquidity = self._liquidity_risk_metrics(state, leader, leader.current_character or "")
        leader_rent_pressure, _ = self._rent_pressure_breakdown(state, leader, leader.current_character or "")
        leader_marks = self._allowed_mark_targets(state, leader)
        leader_burden = self._burden_context(state, leader, legal_targets=leader_marks)

        expansion_need = 0.0
        if buy_value > 0.0:
            expansion_need += 1.0 + 0.65 * buy_value
        if monopoly["own_near_complete"] > 0.0:
            expansion_need += 1.35 * monopoly["own_near_complete"]
        if monopoly["own_claimable_blocks"] > 0.0:
            expansion_need += 0.45 * monopoly["own_claimable_blocks"]
        if leader.tiles_owned >= 6:
            expansion_need += 0.35 * max(1.0, leader.tiles_owned - 5.0)
        add({"중매꾼", "건설업자"}, expansion_need, "leader_needs_expansion")
        if expansion_need > 0.0:
            add({"사기꾼"}, 0.65 * expansion_need + 0.35 * monopoly["contested_blocks"], "leader_needs_takeover")

        escape_need = 0.0
        if cross_start > 0.22 or land_f > 0.16:
            escape_need += 0.95 + 1.1 * cross_start + 0.7 * land_f
        if leader_rent_pressure >= 1.45:
            escape_need += 0.55 * leader_rent_pressure
        if leader_liquidity["cash_after_reserve"] <= 0.0:
            escape_need += 0.22 * max(0.0, -leader_liquidity["cash_after_reserve"])
        add({"객주"}, escape_need, "leader_needs_lap_cash")
        add({"파발꾼", "탈출 노비"}, 0.82 * escape_need, "leader_needs_mobility_escape")

        burden_need = 0.0
        own_burdens = leader_burden["own_burdens"]
        cleanup_pressure = leader_burden["cleanup_pressure"]
        if own_burdens > 0.0:
            burden_need += 0.95 + 0.95 * own_burdens
        if cleanup_pressure >= 2.5:
            burden_need += 0.35 * cleanup_pressure
        if burden_need > 0.0:
            add({"박수"}, burden_need, "leader_needs_burden_dump")
            add({"만신"}, 0.7 * burden_need + 0.2 * leader_burden["legal_visible_burden_total"], "leader_needs_burden_cleanup")
            add({"객주", "탈출 노비"}, 0.18 * burden_need, "leader_needs_buffer_after_burden")

        if leader.shards >= 4:
            shard_need = 0.45 + 0.12 * leader.shards
            add({"산적", "탐관오리", "아전"}, shard_need, "leader_needs_shard_conversion")

        return weights, reasons

    def _leader_marker_flip_plan(self, state: GameState, viewer: PlayerState, leader: Optional[PlayerState]) -> dict[str, Any]:
        weights, reasons = self._leader_needed_character_weights(state, viewer, leader)
        opportunities: dict[int, dict[str, float | str]] = {}
        best_score = 0.0
        best_card: Optional[int] = None
        denial_faces = {"자객", "산적", "추노꾼", "어사", "교리 연구관", "교리 감독관"}
        for card_no, (a, b) in CARD_TO_NAMES.items():
            current = state.active_by_card[card_no]
            flipped = b if current == a else a
            current_need = float(weights.get(current, 0.0))
            flipped_need = float(weights.get(flipped, 0.0))
            delta = current_need - flipped_need
            score = delta
            if score > 0.0 and flipped in denial_faces:
                score += 0.45 if flipped in {"자객", "산적", "추노꾼", "어사"} else 0.25
            opportunities[card_no] = {
                "current": current,
                "flipped": flipped,
                "current_need": current_need,
                "flipped_need": flipped_need,
                "score": float(score),
            }
            if score > best_score:
                best_score = float(score)
                best_card = card_no
        return {
            "weights": weights,
            "reasons": reasons,
            "opportunities": opportunities,
            "best_score": float(best_score),
            "best_card": best_card,
        }

    def _allowed_mark_targets(self, state: GameState, player: PlayerState) -> list[PlayerState]:
        try:
            my_order_idx = state.current_round_order.index(player.player_id)
        except ValueError:
            return []
        allowed_pids = set(state.current_round_order[my_order_idx + 1 :])
        return [
            p for p in state.players
            if p.alive
            and p.player_id != player.player_id
            and p.player_id in allowed_pids
            and p.current_character
            and not p.revealed_this_round
        ]

    def _public_mark_guess_candidates(self, state: GameState, player: PlayerState) -> list[str]:
        return public_mark_guess_candidates(state, player)

    def _mark_guess_policy_params(self) -> tuple[float, float]:
        return mark_guess_policy_params(self._profile_from_mode(), self.character_policy_mode)

    def _mark_guess_distribution(self, candidate_scores: dict[str, float], legal_target_count: int) -> tuple[dict[str, float], dict[str, float]]:
        return mark_guess_distribution(candidate_scores, legal_target_count)

    def _public_target_name_score_breakdown(self, state: GameState, player: PlayerState, actor_name: str, target_name: str) -> tuple[float, list[str]]:
        score = self.character_values.get(target_name, 0.0)
        reasons = [f"public_base={score:.1f}"]
        target_attr = CHARACTERS[target_name].attribute if target_name in CHARACTERS else ""
        growth_like = {"객주", "중매꾼", "건설업자", "파발꾼", "사기꾼"}
        economy_like = {"탐관오리", "아전", "객주", "중매꾼", "건설업자"}
        disruption_like = {"자객", "산적", "추노꾼", "박수", "만신", "어사"}
        if actor_name == "자객":
            if target_attr == "무뢰":
                score += 0.8
                reasons.append("reveal_muroe")
            if target_name in growth_like:
                score += 1.4
                reasons.append("public_growth_threat")
        elif actor_name == "산적":
            score += 0.2 * player.shards
            reasons.append("bandit_shard_scale")
            if target_name in economy_like:
                score += 1.2
                reasons.append("public_economy_target")
        elif actor_name == "추노꾼":
            if target_name in growth_like | economy_like:
                score += 1.0
                reasons.append("public_pull_value")
            if state.board[player.position] in {CellKind.F1, CellKind.F2, CellKind.S, CellKind.MALICIOUS}:
                score += 0.8
                reasons.append("force_special_tile")
        elif actor_name == "박수":
            if target_name in growth_like:
                score += 0.8
                reasons.append("public_burden_dump_target")
        elif actor_name == "만신":
            if target_name in disruption_like:
                score += 0.8
                reasons.append("public_cleanup_target")
        if self._profile_from_mode() == "control":
            if actor_name == "산적":
                if target_name in economy_like | growth_like:
                    score += 1.0
                    reasons.append("control_profit_bandit_target")
            elif actor_name == "박수":
                if target_name in growth_like | economy_like:
                    score += 1.2
                    reasons.append("control_profit_burden_target")
            elif actor_name == "만신":
                if target_name in growth_like | economy_like:
                    score += 1.0
                    reasons.append("control_profit_cleanup_target")
            elif actor_name == "추노꾼":
                if target_name in growth_like | economy_like:
                    score += 0.9
                    reasons.append("control_profit_pull_target")
        return score, reasons

    def _has_uhsa_alive(self, state: GameState, exclude_player_id: Optional[int] = None) -> bool:
        return any(
            p.alive and p.current_character == "어사" and (exclude_player_id is None or p.player_id != exclude_player_id)
            for p in state.players
        )

    def _same_block_unowned_count(self, state: GameState, pos: int) -> int:
        block_id = state.block_ids[pos]
        if block_id < 0:
            return 0
        return sum(
            1
            for idx, bid in enumerate(state.block_ids)
            if bid == block_id and idx != pos and state.tile_owner[idx] is None and state.board[idx] in (CellKind.T2, CellKind.T3)
        )

    def _reachable_specials_with_one_short(self, state: GameState, player: PlayerState) -> int:
        board_len = len(state.board)
        count = 0
        for move in range(2, 13):
            target_pos = (player.position + move + 1) % board_len
            if state.board[target_pos] in {CellKind.F1, CellKind.F2, CellKind.S}:
                count += 1
        return count

    def _expected_own_tile_income(self, state: GameState, player: PlayerState) -> int:
        return len(player.visited_owned_tile_indices)

    def _placeable_own_tiles(self, state: GameState, player: PlayerState) -> list[int]:
        return [
            i for i in player.visited_owned_tile_indices
            if state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
        ]

    def _prob_land_on_placeable_own_tile(self, state: GameState, player: PlayerState) -> float:
        placeable = set(self._placeable_own_tiles(state, player))
        if not placeable:
            return 0.0
        moves = self._moves_for_turn(player)
        if not moves:
            return 0.0
        board_len = len(state.board)
        hits = sum(1 for m in moves if ((player.position + m) % board_len) in placeable)
        return hits / len(moves)

    def _token_teleport_combo_score(self, player: PlayerState) -> float:
        combo = {c.name for c in player.trick_hand}
        score = 0.0
        if "극심한 분리불안" in combo:
            score += 1.3
        if "뇌절왕" in combo:
            score += 1.0
        if "도움 닫기" in combo:
            score += 0.9
        if any(n in combo for n in {"과속", "이럇!"}):
            score += 0.6
        return score

    def _token_placement_window_metrics(self, state: GameState, player: PlayerState) -> dict[str, float]:
        placeable = self._placeable_own_tiles(state, player)
        board_len = len(state.board)
        if not placeable:
            return {
                "placeable_count": 0.0,
                "nearest_distance": float(board_len),
                "revisit_prob": 0.0,
                "loaded_placeable_count": 0.0,
                "loaded_tile_coins": 0.0,
                "window_score": 0.0,
            }
        moves = self._moves_for_turn(player)
        reachable = [((player.position + m) % board_len) for m in moves]
        revisit_hits = sum(1 for pos in reachable if pos in placeable)
        nearest = min(((pos - player.position) % board_len) or board_len for pos in placeable)
        loaded_placeable_count = sum(1 for pos in placeable if state.tile_coins[pos] > 0)
        loaded_tile_coins = float(sum(state.tile_coins[pos] for pos in placeable))
        revisit_prob = (revisit_hits / len(reachable)) if reachable else 0.0
        window_score = (
            1.4 * revisit_prob
            + 0.45 * min(3.0, len(placeable))
            + 0.20 * loaded_placeable_count
            + 0.10 * loaded_tile_coins
            + (1.2 if nearest <= 4 else 0.6 if nearest <= 7 else 0.0)
        )
        return {
            "placeable_count": float(len(placeable)),
            "nearest_distance": float(nearest),
            "revisit_prob": float(revisit_prob),
            "loaded_placeable_count": float(loaded_placeable_count),
            "loaded_tile_coins": float(loaded_tile_coins),
            "window_score": float(window_score),
        }

    def _control_mark_profit_signal(self, state: GameState, player: PlayerState, actor_name: str) -> dict[str, float]:
        legal_targets = self._allowed_mark_targets(state, player)
        if not legal_targets:
            return {"best": 0.0, "avg": 0.0, "count": 0.0}
        values = []
        for target in legal_targets:
            value = 0.0
            visible_burden = self._visible_burden_count(player, target)
            if actor_name == "산적":
                value += 0.18 * target.cash + 0.55 * player.shards + 0.35 * max(0.0, target.tiles_owned - 2.0)
            elif actor_name == "박수":
                value += 1.15 * visible_burden + 0.22 * max(0.0, 10.0 - target.cash) + 0.18 * max(0.0, target.tiles_owned - 2.0)
            elif actor_name == "만신":
                value += 1.45 * visible_burden + 0.18 * max(0.0, 12.0 - target.cash) + 0.14 * target.tiles_owned
            elif actor_name == "추노꾼":
                value += 0.45 * target.tiles_owned + 0.18 * target.cash
                if state.board[player.position] in {CellKind.F1, CellKind.F2, CellKind.S, CellKind.MALICIOUS}:
                    value += 0.75
            elif actor_name == "자객":
                value += 0.20 * target.tiles_owned + 0.12 * target.cash + 0.55 * len(target.pending_marks)
            values.append(value)
        best = max(values) if values else 0.0
        avg = (sum(values) / len(values)) if values else 0.0
        return {"best": float(best), "avg": float(avg), "count": float(len(values))}

    def _mark_priority_exposure_factor(self, actor_name: str, target_name: str) -> float:
        return mark_priority_exposure_factor(actor_name, target_name)

    def _mark_target_profile_factor(self, actor_name: str, target_name: str) -> float:
        return mark_target_profile_factor(actor_name, target_name)

    def _public_mark_risk_breakdown(self, state: GameState, player: PlayerState, character_name: str) -> tuple[float, list[str]]:
        risk = 0.0
        reasons: list[str] = []
        active_names = {name for name in state.active_by_card.values() if name}
        seen_actors = sorted(name for name in active_names if name in MARK_ACTOR_NAMES and name != character_name)
        for actor_name in seen_actors:
            exposure = self._mark_priority_exposure_factor(actor_name, character_name)
            if exposure <= 0.0:
                continue
            profile = self._mark_target_profile_factor(actor_name, character_name)
            if profile <= 0.0:
                continue
            contribution = MARK_ACTOR_BASE_RISK[actor_name] * exposure * profile
            risk += contribution
            reasons.append(f"{actor_name}:{contribution:.2f}")
        if risk > 0.0 and CHARACTERS[character_name].priority >= 7:
            tail_exposure = 0.35 + 0.05 * (CHARACTERS[character_name].priority - 7)
            risk += tail_exposure
            reasons.append(f"late_turn:{tail_exposure:.2f}")
        return risk, reasons

    def _enemy_rent_costs(self, state: GameState, player: PlayerState) -> list[int]:
        costs: list[int] = []
        for pos, owner in enumerate(state.tile_owner):
            if owner is None or owner == player.player_id:
                continue
            cell = state.board[pos]
            if cell in {CellKind.T2, CellKind.T3}:
                costs.append(state.config.rules.economy.rent_cost_for(state, pos))
            elif cell == CellKind.MALICIOUS:
                costs.append(state.config.rules.special_tiles.malicious_cost_for(state, pos))
        return costs

    def _rent_exposure_metrics(self, state: GameState, player: PlayerState) -> dict[str, float]:
        moves = self._moves_for_turn(player)
        if not moves:
            return {
                "hit_prob": 0.0,
                "avg_cost": 0.0,
                "peak_cost": 0.0,
                "high_hit_prob": 0.0,
                "lethal_hit_prob": 0.0,
                "corridor_density": 0.0,
            }
        board_len = len(state.board)
        hit_costs: list[int] = []
        corridor_hits = 0
        corridor_steps = 0
        for step in range(2, 9):
            pos = (player.position + step) % board_len
            cell = state.board[pos]
            owner = state.tile_owner[pos]
            if cell in {CellKind.T2, CellKind.T3, CellKind.MALICIOUS}:
                corridor_steps += 1
                if owner is not None and owner != player.player_id:
                    corridor_hits += 1
        for move in moves:
            pos = (player.position + move) % board_len
            owner = state.tile_owner[pos]
            if owner is None or owner == player.player_id:
                continue
            cell = state.board[pos]
            if cell in {CellKind.T2, CellKind.T3}:
                hit_costs.append(state.config.rules.economy.rent_cost_for(state, pos))
            elif cell == CellKind.MALICIOUS:
                hit_costs.append(state.config.rules.special_tiles.malicious_cost_for(state, pos))
        if not hit_costs:
            return {
                "hit_prob": 0.0,
                "avg_cost": 0.0,
                "peak_cost": 0.0,
                "high_hit_prob": 0.0,
                "lethal_hit_prob": 0.0,
                "corridor_density": (corridor_hits / corridor_steps) if corridor_steps else 0.0,
            }
        high_threshold = max(10.0, player.cash * 0.55)
        avg_cost = sum(hit_costs) / len(hit_costs)
        peak_cost = max(hit_costs)
        hit_prob = len(hit_costs) / len(moves)
        high_hit_prob = sum(1 for cost in hit_costs if cost >= high_threshold) / len(moves)
        lethal_hit_prob = sum(1 for cost in hit_costs if cost >= player.cash) / len(moves)
        return {
            "hit_prob": hit_prob,
            "avg_cost": avg_cost,
            "peak_cost": float(peak_cost),
            "high_hit_prob": high_hit_prob,
            "lethal_hit_prob": lethal_hit_prob,
            "corridor_density": (corridor_hits / corridor_steps) if corridor_steps else 0.0,
        }

    def _liquidity_risk_metrics(self, state: GameState, player: PlayerState, character_name: str | None = None) -> dict[str, float]:
        character_name = character_name or player.current_character or ""
        known_character = character_name in CHARACTERS
        rent_metrics = self._rent_exposure_metrics(state, player)
        expected_loss = rent_metrics["hit_prob"] * rent_metrics["avg_cost"]
        worst_loss = rent_metrics["peak_cost"]
        active_names = {name for name in state.active_by_card.values() if name}
        if known_character and "추노꾼" in active_names and character_name != "추노꾼":
            exposure = self._mark_priority_exposure_factor("추노꾼", character_name)
            profile = max(0.55, self._mark_target_profile_factor("추노꾼", character_name))
            if exposure > 0.0:
                enemy_peak = max(self._enemy_rent_costs(state, player) or [0])
                expected_loss += enemy_peak * 0.28 * exposure * profile
                worst_loss = max(worst_loss, enemy_peak * exposure)
        if known_character and "산적" in active_names and character_name != "산적":
            exposure = self._mark_priority_exposure_factor("산적", character_name)
            profile = max(0.55, self._mark_target_profile_factor("산적", character_name))
            if exposure > 0.0:
                enemy_bandit_shards = max((p.shards for p in state.players if p.alive and p.current_character == "산적" and p.player_id != player.player_id), default=0)
                expected_loss += enemy_bandit_shards * 0.35 * exposure * profile
                worst_loss = max(worst_loss, float(enemy_bandit_shards))
        own_burdens = sum(card.burden_cost for card in player.trick_hand if card.is_burden)
        burden_context = self._burden_context(state, player)
        if own_burdens > 0:
            # [burden_patch v3] reserve에 짐 청산 예상 비용을 실제 배수로 반영한다.
            # 청산 이벤트는 대부분 multiplier=2 (화재/산불/보급 등)
            # 따라서 reserve에 own_burdens * 2.0 을 적립해야 청산 시 파산을 막는다.
            # 기존 0.28 가중치는 너무 낮아서 reserve 증가 효과가 미미했다.
            expected_cleanup = own_burdens * float(max(
                burden_context.get("deck_expected_cleanup_multiplier", 0.0),
                burden_context.get("deck_two_draw_expected_cleanup_multiplier", 0.0),
                1.0,  # 최소 1배 이상으로 보수적으로
            ))
            expected_loss += 0.70 * expected_cleanup + 0.10 * burden_context["cleanup_pressure"]
            worst_loss = max(worst_loss, float(own_burdens) * 2.0)  # worst case: 2배 청산
        reserve = max(6.0, expected_loss + 0.55 * worst_loss)
        if player.cash <= 18:
            reserve += 1.0
        if player.cash <= 10:
            reserve += 1.5
        return {
            "expected_loss": float(expected_loss),
            "worst_loss": float(worst_loss),
            "reserve": float(reserve),
            "cash_after_reserve": float(player.cash - reserve),
            "own_burden_cost": float(own_burdens),
        }

    def _public_effective_tile_cost(self, state: GameState, player: PlayerState, pos: int) -> float:
        cell = state.board[pos]
        if cell == CellKind.MALICIOUS:
            return float(state.config.rules.special_tiles.malicious_cost_for(state, pos))
        if cell not in {CellKind.T2, CellKind.T3}:
            return 0.0
        base = float(state.config.rules.economy.rent_cost_for(state, pos))
        mod = float(state.tile_rent_modifiers_this_turn.get(pos, 1))
        block_id = state.block_ids[pos]
        tile_color = state.block_color_map.get(block_id)
        if tile_color is not None and any(COLOR_RENT_DOUBLE_WEATHERS.get(name) == tile_color for name in state.current_weather_effects):
            mod *= 2.0
        if mod <= 0.0:
            return 0.0
        rent = base * mod
        if state.global_rent_double_permanent:
            rent *= 2.0
        if state.global_rent_double_this_turn:
            rent *= 2.0
        if state.global_rent_half_this_turn:
            rent = float(math.ceil(rent / 2.0))
        if player.trick_personal_rent_half_this_turn:
            rent = float(math.floor(rent / 2.0))
        return max(0.0, rent)

    def _front_tile_pressure(self, state: GameState, player: PlayerState, horizon: int = 10) -> dict[str, float]:
        board_len = len(state.board)
        enemy_weight = 0.0
        recovery_weight = 0.0
        lethal_weight = 0.0
        weighted_cost = 0.0
        peak_cost = 0.0
        total_weight = 0.0
        for step in range(1, horizon + 1):
            pos = (player.position + step) % board_len
            weight = 1.35 if step <= 4 else 1.0 if step <= 8 else 0.65
            total_weight += weight
            cell = state.board[pos]
            owner = state.tile_owner[pos]
            if cell == CellKind.MALICIOUS:
                cost = float(state.config.rules.special_tiles.malicious_cost_for(state, pos))
                enemy_weight += weight
                weighted_cost += weight * cost
                peak_cost = max(peak_cost, cost)
                if cost >= player.cash:
                    lethal_weight += weight
            elif cell in {CellKind.T2, CellKind.T3} and owner is not None and owner != player.player_id:
                cost = self._public_effective_tile_cost(state, player, pos)
                enemy_weight += weight
                weighted_cost += weight * cost
                peak_cost = max(peak_cost, cost)
                if cost >= player.cash:
                    lethal_weight += weight
            elif cell in {CellKind.F1, CellKind.F2, CellKind.S} or (cell in {CellKind.T2, CellKind.T3} and owner == player.player_id):
                recovery_weight += weight
        if total_weight <= 0.0:
            return {"enemy_density": 0.0, "recovery_density": 0.0, "weighted_cost": 0.0, "peak_cost": 0.0, "lethal_density": 0.0}
        return {
            "enemy_density": float(enemy_weight / total_weight),
            "recovery_density": float(recovery_weight / total_weight),
            "weighted_cost": float(weighted_cost / total_weight),
            "peak_cost": float(peak_cost),
            "lethal_density": float(lethal_weight / total_weight),
        }

    def _two_turn_exposure_metrics(self, state: GameState, player: PlayerState) -> dict[str, float]:
        first_moves = self._moves_for_turn(player)
        if not first_moves:
            return {"hit_prob": 0.0, "avg_cost": 0.0, "peak_cost": 0.0, "lethal_hit_prob": 0.0, "recovery_prob": 0.0}
        second_moves = list(first_moves)
        board_len = len(state.board)
        costs: list[float] = []
        recovery_hits = 0
        total = 0
        for move1 in first_moves:
            pos1 = (player.position + move1) % board_len
            for move2 in second_moves:
                total += 1
                pos2 = (pos1 + move2) % board_len
                cell = state.board[pos2]
                owner = state.tile_owner[pos2]
                if cell == CellKind.MALICIOUS:
                    costs.append(float(state.config.rules.special_tiles.malicious_cost_for(state, pos2)))
                elif cell in {CellKind.T2, CellKind.T3} and owner is not None and owner != player.player_id:
                    costs.append(self._public_effective_tile_cost(state, player, pos2))
                elif cell in {CellKind.F1, CellKind.F2, CellKind.S} or (cell in {CellKind.T2, CellKind.T3} and owner == player.player_id):
                    recovery_hits += 1
        if total <= 0:
            return {"hit_prob": 0.0, "avg_cost": 0.0, "peak_cost": 0.0, "lethal_hit_prob": 0.0, "recovery_prob": 0.0}
        if not costs:
            return {"hit_prob": 0.0, "avg_cost": 0.0, "peak_cost": 0.0, "lethal_hit_prob": 0.0, "recovery_prob": float(recovery_hits / total)}
        return {
            "hit_prob": float(len(costs) / total),
            "avg_cost": float(sum(costs) / len(costs)),
            "peak_cost": float(max(costs)),
            "lethal_hit_prob": float(sum(1 for cost in costs if cost >= player.cash) / total),
            "recovery_prob": float(recovery_hits / total),
        }

    def _active_money_drain_pressure(self, state: GameState, player: PlayerState, character_name: str | None = None) -> tuple[float, list[str]]:
        actor_name = character_name or player.current_character or ""
        my_attr = CHARACTERS[actor_name].attribute if actor_name in CHARACTERS else player.attribute
        own_burden_cost = sum(card.burden_cost for card in player.trick_hand if card.is_burden)
        enemy_peak_cost = max(self._enemy_rent_costs(state, player) or [0])
        pressure = 0.0
        reasons: list[str] = []
        for opponent in self._alive_enemies(state, player):
            name = opponent.current_character
            if name not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                continue
            if name == "탐관오리" and my_attr in {"관원", "상민"}:
                contribution = 0.55 + 0.18 * max(1.0, float(opponent.shards)) + 0.08 * max(0.0, float(player.shards))
                pressure += contribution
                reasons.append(f"탐관오리:{contribution:.2f}")
            elif name == "산적":
                exposure = self._mark_priority_exposure_factor("산적", actor_name) if actor_name in CHARACTERS else 0.65
                profile = max(0.55, self._mark_target_profile_factor("산적", actor_name)) if actor_name in CHARACTERS else 0.70
                contribution = (0.45 + 0.16 * float(opponent.shards) + 0.08 * max(0.0, float(player.cash) - 6.0)) * exposure * profile
                pressure += contribution
                reasons.append(f"산적:{contribution:.2f}")
            elif name == "추노꾼":
                exposure = self._mark_priority_exposure_factor("추노꾼", actor_name) if actor_name in CHARACTERS else 0.65
                profile = max(0.55, self._mark_target_profile_factor("추노꾼", actor_name)) if actor_name in CHARACTERS else 0.70
                contribution = (0.65 + 0.04 * float(enemy_peak_cost)) * exposure * profile
                pressure += contribution
                reasons.append(f"추노꾼:{contribution:.2f}")
            elif name == "아전":
                same_tile_others = sum(1 for p in state.players if p.alive and p.player_id not in {player.player_id, opponent.player_id} and p.position == player.position)
                contribution = 0.30 + 0.10 * float(opponent.shards) + 0.18 * float(same_tile_others)
                pressure += contribution
                reasons.append(f"아전:{contribution:.2f}")
            elif name == "만신" and own_burden_cost > 0:
                exposure = self._mark_priority_exposure_factor("만신", actor_name) if actor_name in CHARACTERS else 0.60
                profile = max(0.55, self._mark_target_profile_factor("만신", actor_name)) if actor_name in CHARACTERS else 0.70
                contribution = (0.35 + 0.20 * float(own_burden_cost)) * exposure * profile
                pressure += contribution
                reasons.append(f"만신:{contribution:.2f}")
            visible = self._visible_trick_names(player, opponent)
            if visible & {"느슨함 혐오자", "극도의 느슨함 혐오자"}:
                pressure += 0.25
                reasons.append("enemy_public_rent_amp:0.25")
            if visible & {"긴장감 조성"} and opponent.tiles_owned > 0:
                pressure += 0.18
                reasons.append("enemy_public_tile_amp:0.18")
        return pressure, reasons

    def _table_cash_context(self, state: GameState, player: PlayerState) -> dict[str, float]:
        alive_cash = sorted(float(p.cash) for p in state.players if p.alive)
        if not alive_cash:
            return {"median_cash": float(player.cash), "cash_gap_to_table": 0.0, "poor_ratio": 0.0}
        median_cash = alive_cash[len(alive_cash) // 2]
        richer = sum(1 for p in state.players if p.alive and p.player_id != player.player_id and p.cash >= player.cash + 3)
        poorer = sum(1 for p in state.players if p.alive and p.player_id != player.player_id and p.cash + 3 <= player.cash)
        opp_count = max(1, state.alive_count() - 1)
        poor_ratio = max(0.0, (richer - poorer) / opp_count)
        return {
            "median_cash": float(median_cash),
            "cash_gap_to_table": float(player.cash - median_cash),
            "poor_ratio": float(poor_ratio),
        }

    def _generic_survival_context(self, state: GameState, player: PlayerState, character_name: str | None = None) -> dict[str, float]:
        actor_name = character_name or player.current_character or ""
        liquidity = self._liquidity_risk_metrics(state, player, actor_name)
        rent_pressure, _ = self._rent_pressure_breakdown(state, player, actor_name)
        rent_metrics = self._rent_exposure_metrics(state, player)
        two_turn = self._two_turn_exposure_metrics(state, player)
        front = self._front_tile_pressure(state, player)
        drain_pressure, _ = self._active_money_drain_pressure(state, player, actor_name)
        burden_context = self._burden_context(state, player)
        table_cash = self._table_cash_context(state, player)
        cross_start = self._will_cross_start(state, player)
        land_f = self._will_land_on_f(state, player)
        specials = float(self._reachable_specials_with_one_short(state, player))
        reserve = float(liquidity["reserve"])
        reserve_gap = max(0.0, reserve - float(player.cash))
        recovery_score = 1.45 * cross_start + 1.25 * land_f + 0.28 * float(two_turn["recovery_prob"]) + 0.18 * float(front["recovery_density"]) + 0.08 * specials
        if player.visited_owned_tile_indices:
            recovery_score += 0.20
        hazard_score = (
            0.95 * rent_pressure
            + 1.15 * float(rent_metrics["lethal_hit_prob"])
            + 0.80 * float(two_turn["hit_prob"])
            + 1.35 * float(two_turn["lethal_hit_prob"])
            + 0.65 * float(front["enemy_density"])
            + 0.85 * float(front["lethal_density"])
            + 0.55 * float(drain_pressure)
            + 0.22 * max(0.0, -float(liquidity["cash_after_reserve"]))
            + 0.16 * float(liquidity["own_burden_cost"])
            + 0.18 * max(0.0, float(burden_context.get("cleanup_pressure", 0.0)) - 1.2)
            + 0.42 * max(0.0, float(burden_context.get("latent_cleanup_cost", 0.0)) - max(0.0, float(player.cash) - reserve)) / 4.0
            + 0.26 * max(0.0, float(burden_context.get("expected_cleanup_cost", 0.0)) - max(0.0, float(player.cash) - reserve)) / 4.0
            + 0.60 * float(burden_context.get("public_cleanup_active", 0.0)) * max(0.0, float(burden_context.get("active_cleanup_cost", 0.0)) - float(player.cash)) / 3.0
            + 0.16 * reserve_gap
            + 0.22 * max(0.0, -float(table_cash["cash_gap_to_table"]) / 4.0)
            + 0.25 * max(0.0, float(table_cash["poor_ratio"]))
        )
        if player.cash <= 6:
            hazard_score += 0.40
        if player.cash <= 3:
            hazard_score += 0.75
        cleanup_distress = (
            0.30 * max(0.0, float(burden_context.get("cleanup_pressure", 0.0)) - 1.0)
            + 0.45 * max(0.0, float(burden_context.get("latent_cleanup_gap", 0.0)) / 4.0)
            + 0.25 * max(0.0, float(burden_context.get("expected_cleanup_gap", 0.0)) / 4.0)
            + 0.90 * max(0.0, float(burden_context.get("cleanup_cash_gap", 0.0)) / 4.0)
        )
        money_distress = (
            0.65 * reserve_gap
            + 0.55 * float(drain_pressure)
            + 0.40 * float(front["enemy_density"])
            + 0.55 * float(two_turn["lethal_hit_prob"])
            + cleanup_distress
            + 0.18 * max(0.0, -float(table_cash["cash_gap_to_table"]) / 3.0)
        )
        survival_score = recovery_score - hazard_score
        urgency = max(0.0, -survival_score) + 0.15 * reserve_gap + 0.30 * float(two_turn["lethal_hit_prob"]) + 0.20 * cleanup_distress
        controller_need = 0.75 * float(drain_pressure) + 0.25 * float(burden_context.get("own_burdens", 0.0))
        needs_income = (
            money_distress >= 1.15
            or (player.cash <= max(6.0, liquidity["reserve"] - 1.0) and float(two_turn["hit_prob"]) > 0.0)
            or float(burden_context.get("cleanup_cash_gap", 0.0)) > 0.0
            or (float(burden_context.get("latent_cleanup_cost", 0.0)) >= max(8.0, player.cash * 0.8) and float(burden_context.get("own_burdens", 0.0)) >= 2.0)
        )
        return {
            "generic_survival_score": float(survival_score),
            "survival_urgency": float(urgency),
            "hazard_score": float(hazard_score),
            "recovery_score": float(recovery_score),
            "rent_pressure": float(rent_pressure),
            "lethal_hit_prob": float(rent_metrics["lethal_hit_prob"]),
            "reserve": float(liquidity["reserve"]),
            "reserve_gap": float(reserve_gap),
            "cash_after_reserve": float(liquidity["cash_after_reserve"]),
            "cross_start": float(cross_start),
            "land_f": float(land_f),
            "special_reach": float(specials),
            "cleanup_pressure": float(burden_context.get("cleanup_pressure", 0.0)),
            "own_burden_cost": float(liquidity["own_burden_cost"]),
            "active_cleanup_cost": float(burden_context.get("active_cleanup_cost", 0.0)),
            "latent_cleanup_cost": float(burden_context.get("latent_cleanup_cost", 0.0)),
            "expected_cleanup_cost": float(burden_context.get("expected_cleanup_cost", 0.0)),
            "cleanup_cash_gap": float(burden_context.get("cleanup_cash_gap", 0.0)),
            "latent_cleanup_gap": float(burden_context.get("latent_cleanup_gap", 0.0)),
            "expected_cleanup_gap": float(burden_context.get("expected_cleanup_gap", 0.0)),
            "public_cleanup_active": float(burden_context.get("public_cleanup_active", 0.0)),
            "front_enemy_density": float(front["enemy_density"]),
            "front_recovery_density": float(front["recovery_density"]),
            "front_peak_cost": float(front["peak_cost"]),
            "two_turn_hit_prob": float(two_turn["hit_prob"]),
            "two_turn_lethal_prob": float(two_turn["lethal_hit_prob"]),
            "two_turn_recovery_prob": float(two_turn["recovery_prob"]),
            "active_drain_pressure": float(drain_pressure),
            "controller_need": float(controller_need),
            "money_distress": float(money_distress),
            "needs_income": 1.0 if needs_income else 0.0,
            "median_cash": float(table_cash["median_cash"]),
            "cash_gap_to_table": float(table_cash["cash_gap_to_table"]),
            "poor_ratio": float(table_cash["poor_ratio"]),
        }

    def _reachable_purchase_floor(self, state: GameState, player: PlayerState) -> float | None:
        board_len = len(state.board)
        costs: list[float] = []
        for move in self._moves_for_turn(player):
            pos = (player.position + move) % board_len
            if state.board[pos] not in {CellKind.T2, CellKind.T3}:
                continue
            if state.tile_owner[pos] is not None:
                continue
            costs.append(float(state.config.rules.economy.purchase_cost_for(state, pos)))
        return min(costs) if costs else None

    def _reachable_swindle_floor(self, state: GameState, player: PlayerState) -> float | None:
        board_len = len(state.board)
        costs: list[float] = []
        for move in self._moves_for_turn(player):
            pos = (player.position + move) % board_len
            owner = state.tile_owner[pos]
            if owner is None or owner == player.player_id:
                continue
            if state.board[pos] not in {CellKind.T2, CellKind.T3}:
                continue
            if self._takeover_protected(state, pos):
                continue
            costs.append(float(state.config.rules.economy.rent_cost_for(state, pos) * 2))
        return min(costs) if costs else None

    def _swindle_operating_reserve(self, state: GameState, player: PlayerState, survival_ctx: dict[str, float] | None = None) -> float:
        survival_ctx = survival_ctx or self._generic_survival_context(state, player)
        return float(evaluate_swindle_guard(
            cash=float(player.cash),
            required_cost=0.0,
            signals=SurvivalSignals.from_mapping(survival_ctx),
            is_leader=False,
            near_end=False,
        ).reserve)

    def _build_survival_orchestrator(self, state: GameState, player: PlayerState, character_name: str | None = None) -> tuple[dict[str, float], SurvivalOrchestratorState]:
        survival_ctx = self._generic_survival_context(state, player, character_name)
        orchestrator = build_survival_orchestrator(SurvivalSignals.from_mapping(survival_ctx))
        return survival_ctx, orchestrator

    def _survival_policy_character_advice(self, state: GameState, player: PlayerState, character_name: str, orchestrator: SurvivalOrchestratorState) -> tuple[float, list[str], bool, dict[str, object]]:
        purchase_floor = self._reachable_purchase_floor(state, player)
        swindle_floor = self._reachable_swindle_floor(state, player) if character_name == "사기꾼" else None
        advice = evaluate_character_survival_advice(
            state=orchestrator,
            is_growth=character_name in {"중매꾼", "건설업자", "사기꾼"},
            is_income=character_name in LOW_CASH_INCOME_CHARACTERS | LOW_CASH_ESCAPE_CHARACTERS,
            is_controller=character_name in LOW_CASH_CONTROLLER_CHARACTERS,
            is_cleanup=character_name in {"박수", "만신", "교리 연구관", "교리 감독관"},
            cash=float(player.cash),
            purchase_floor=purchase_floor,
            swindle_floor=swindle_floor,
        )
        reasons = [r for r in advice.reason.split(',') if r]
        policy_score = float(advice.bias_score)
        if advice.hard_block:
            policy_score -= 1000.0
            reasons.append('survival_hard_block_hint')
        detail = {
            'severity': advice.severity,
            'bias_score': round(advice.bias_score, 3),
            'hard_block': bool(advice.hard_block),
            'recommended_biases': list(advice.recommended_biases),
            'purchase_floor': None if purchase_floor is None else round(float(purchase_floor), 3),
            'swindle_floor': None if swindle_floor is None else round(float(swindle_floor), 3),
        }
        return policy_score, reasons, bool(advice.hard_block), detail


    def should_attempt_swindle(self, state: GameState, player: PlayerState, pos: int, owner: int, required_cost: float) -> bool:
        if required_cost <= 0:
            return True
        survival_ctx = self._generic_survival_context(state, player)
        f_ctx = self._f_progress_context(state, player)
        decision = evaluate_swindle_guard(
            cash=float(player.cash),
            required_cost=float(required_cost),
            signals=SurvivalSignals.from_mapping(survival_ctx),
            is_leader=bool(f_ctx.get("is_leader", False)),
            near_end=bool(f_ctx.get("near_end", False)),
        )
        return bool(decision.allowed)


    def _failed_mark_fallback_metrics(self, player: PlayerState, threshold: int) -> tuple[int, int]:
        if threshold <= 0:
            return 0, 0
        removable = player.shards // threshold
        if removable <= 0:
            return 0, 0
        burdens = sorted((c for c in player.trick_hand if c.is_burden), key=lambda c: (c.burden_cost, c.deck_index), reverse=True)
        picked = burdens[:removable]
        return len(picked), sum(int(c.burden_cost) for c in picked)

    def _matchmaker_adjacent_value(self, state: GameState, player: PlayerState) -> float:
        board_len = len(state.board)
        open_adjacent = 0
        near_complete_bonus = 0.0
        for step in range(2, 8):
            pos = (player.position + step) % board_len
            if state.board[pos] not in (CellKind.T2, CellKind.T3):
                continue
            block_id = state.block_ids[pos]
            if block_id < 0:
                continue
            owned = 0
            has_open_adjacent = False
            for idx, bid in enumerate(state.block_ids):
                if bid != block_id or idx == pos:
                    continue
                if state.tile_owner[idx] == player.player_id:
                    owned += 1
                if state.tile_owner[idx] is None and abs(idx - pos) == 1 and state.board[idx] in (CellKind.T2, CellKind.T3):
                    has_open_adjacent = True
            if has_open_adjacent:
                open_adjacent += 1
                near_complete_bonus += 0.4 * owned
        if open_adjacent <= 0:
            return 0.0
        shard_gate = 1.0 if player.shards >= 1 else 0.35
        return shard_gate * (0.75 * open_adjacent + near_complete_bonus)

    def _builder_free_purchase_value(self, state: GameState, player: PlayerState) -> float:
        board_len = len(state.board)
        purchase_windows = 0
        t3_windows = 0
        for step in range(2, 8):
            pos = (player.position + step) % board_len
            if state.tile_owner[pos] is not None:
                continue
            if state.board[pos] == CellKind.T3:
                purchase_windows += 1
                t3_windows += 1
            elif state.board[pos] == CellKind.T2:
                purchase_windows += 1
        if purchase_windows <= 0:
            return 0.25
        return 0.55 * purchase_windows + 0.35 * t3_windows

    def _character_survival_adjustment(self, state: GameState, player: PlayerState, character_name: str, survival_ctx: dict[str, float]) -> tuple[float, list[str]]:
        urgency = float(survival_ctx["survival_urgency"])
        reserve = float(survival_ctx["reserve"])
        reserve_gap = float(survival_ctx["reserve_gap"])
        cash_after_reserve = float(survival_ctx["cash_after_reserve"])
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        needs_income = bool(survival_ctx.get("needs_income", 0.0) > 0.0)
        adjustment = 0.0
        reasons: list[str] = []
        public_mark_risk, _ = self._public_mark_risk_breakdown(state, player, character_name)
        growth_floor = self._reachable_purchase_floor(state, player)
        swindle_floor = self._reachable_swindle_floor(state, player)

        if character_name in {"중매꾼", "건설업자"}:
            operating_floor = reserve + (growth_floor if growth_floor is not None else 4.0)
            shortage = max(0.0, operating_floor - player.cash)
            if shortage > 0.0:
                penalty = 2.4 + 0.85 * shortage + 0.65 * urgency
                adjustment -= penalty
                reasons.append(f"growth_cash_shortage={penalty:.2f}")
            if urgency > 0.0:
                penalty = 0.9 * urgency + 0.25 * public_mark_risk
                adjustment -= penalty
                reasons.append(f"growth_survival_gate={penalty:.2f}")
            if money_distress > 0.0:
                penalty = 1.10 * money_distress + (0.55 if needs_income else 0.0)
                adjustment -= penalty
                reasons.append(f"growth_money_distress={penalty:.2f}")
            if character_name == "중매꾼":
                adjacent_value = self._matchmaker_adjacent_value(state, player)
                if adjacent_value > 0.0:
                    bonus = 0.55 * adjacent_value
                    if player.shards <= 0:
                        bonus *= 0.45
                    adjustment += bonus
                    reasons.append(f"matchmaker_adjacent_value={bonus:.2f}")
                elif player.shards <= 0 and growth_floor is not None and growth_floor > 0.0:
                    penalty = 0.45 + 0.10 * min(5.0, growth_floor)
                    adjustment -= penalty
                    reasons.append(f"matchmaker_no_shard_adjacent={penalty:.2f}")
            elif character_name == "건설업자":
                build_value = self._builder_free_purchase_value(state, player)
                if build_value > 0.0:
                    bonus = 0.90 + 0.65 * build_value
                    adjustment += bonus
                    reasons.append(f"builder_free_build_value={bonus:.2f}")
                else:
                    penalty = 0.30
                    adjustment -= penalty
                    reasons.append(f"builder_no_free_build={penalty:.2f}")
        elif character_name == "사기꾼":
            if swindle_floor is None:
                penalty = 1.4 + 0.60 * urgency
                adjustment -= penalty
                reasons.append(f"swindle_no_reachable_line={penalty:.2f}")
            else:
                operating_floor = reserve + swindle_floor
                shortage = max(0.0, operating_floor - player.cash)
                if shortage > 0.0:
                    penalty = 2.7 + 0.95 * shortage + 0.75 * urgency
                    adjustment -= penalty
                    reasons.append(f"swindle_cash_shortage={penalty:.2f}")
            if money_distress > 0.0:
                penalty = 1.20 * money_distress + 0.45 * float(survival_ctx.get("two_turn_lethal_prob", 0.0))
                adjustment -= penalty
                reasons.append(f"swindle_money_distress={penalty:.2f}")
        if character_name in LOW_CASH_ESCAPE_CHARACTERS and urgency > 0.0:
            bonus = 1.15 + 1.10 * urgency + 0.20 * survival_ctx["recovery_score"]
            adjustment += bonus
            reasons.append(f"survival_escape_bonus={bonus:.2f}")
        if character_name in LOW_CASH_DISRUPTORS and (urgency > 0.6 or cash_after_reserve <= 0.0 or money_distress > 0.8):
            bonus = 0.55 + 0.35 * urgency + 0.35 * money_distress + (0.40 if player.cash <= reserve + 1.5 else 0.0)
            adjustment += bonus
            reasons.append(f"survival_lowcash_actor={bonus:.2f}")
        if character_name in LOW_CASH_INCOME_CHARACTERS and needs_income:
            bonus = 0.95 + 0.55 * money_distress + 0.25 * max(0.0, -cash_after_reserve)
            adjustment += bonus
            reasons.append(f"income_recovery_bias={bonus:.2f}")
        if character_name in LOW_CASH_CONTROLLER_CHARACTERS and controller_need > 0.0:
            bonus = 0.85 + 0.70 * controller_need + 0.25 * urgency
            adjustment += bonus
            reasons.append(f"controller_drain_relief={bonus:.2f}")
        burden_cleanup_gap = float(survival_ctx.get("cleanup_cash_gap", 0.0))
        latent_cleanup_cost = float(survival_ctx.get("latent_cleanup_cost", 0.0))
        expected_cleanup_cost = float(survival_ctx.get("expected_cleanup_cost", 0.0))
        own_burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))
        if character_name == "박수" and own_burden_cost > 0.0:
            bonus = 1.20 + 0.35 * own_burden_cost + 0.55 * min(3.0, burden_cleanup_gap) + 0.30 * float(survival_ctx.get("public_cleanup_active", 0.0))
            removed, payout = self._failed_mark_fallback_metrics(player, 5)
            if removed > 0:
                bonus += 0.55 * removed + 0.12 * payout
            adjustment += bonus
            reasons.append(f"burden_escape_value={bonus:.2f}")
        if character_name == "만신" and own_burden_cost > 0.0:
            bonus = 0.80 + 0.22 * own_burden_cost + 0.35 * min(3.0, burden_cleanup_gap)
            removed, payout = self._failed_mark_fallback_metrics(player, 7)
            if removed > 0:
                bonus += 0.45 * removed + 0.10 * payout
            adjustment += bonus
            reasons.append(f"burden_cleanup_value={bonus:.2f}")
        if latent_cleanup_cost >= max(8.0, reserve + 2.0) and character_name in {"중매꾼", "건설업자", "사기꾼"}:
            penalty = 0.90 + 0.12 * latent_cleanup_cost + 0.30 * urgency
            adjustment -= penalty
            reasons.append(f"cleanup_growth_lock={penalty:.2f}")
        if urgency >= 2.0 and character_name in {"중매꾼", "건설업자", "사기꾼"}:
            panic_penalty = 1.85 + 0.35 * urgency
            adjustment -= panic_penalty
            reasons.append(f"panic_growth_lock={panic_penalty:.2f}")
        if urgency >= 1.0 and character_name in LOW_CASH_ESCAPE_CHARACTERS and reserve_gap > 0.0:
            reserve_bonus = 0.30 * reserve_gap
            adjustment += reserve_bonus
            reasons.append(f"reserve_escape_bias={reserve_bonus:.2f}")
        if float(survival_ctx.get("two_turn_lethal_prob", 0.0)) >= 0.18 and character_name in {"중매꾼", "건설업자"}:
            penalty = 0.80 + 1.80 * float(survival_ctx["two_turn_lethal_prob"])
            adjustment -= penalty
            reasons.append(f"two_turn_growth_lock={penalty:.2f}")
        return adjustment, reasons

    def _trick_survival_adjustment(self, state: GameState, player: PlayerState, card: TrickCard, survival_ctx: dict[str, float]) -> float:
        urgency = float(survival_ctx["survival_urgency"])
        reserve = float(survival_ctx["reserve"])
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        adjustment = 0.0
        if card.is_burden:
            return -4.0 - 0.60 * urgency - 0.20 * card.burden_cost
        if urgency <= 0.0 and survival_ctx["cash_after_reserve"] > 0.0 and money_distress <= 0.0:
            return 0.0
        if card.name in {"건강 검진", "우대권", "뇌고왕"}:
            adjustment += 1.40 + 0.85 * urgency + 0.30 * survival_ctx["rent_pressure"] + 0.20 * money_distress
        if card.name == "강제 매각":
            adjustment += 0.75 + 0.55 * urgency + 0.30 * money_distress + (0.45 if player.tiles_owned > 0 else -0.25)
        if card.name == "저속":
            adjustment += 0.90 + 0.45 * urgency + 0.30 * survival_ctx["lethal_hit_prob"] + 0.45 * money_distress
        if card.name in {"극심한 분리불안", "도움 닫기", "가벼운 분리불안", "신의뜻"}:
            adjustment += 0.40 + 0.35 * urgency + 0.20 * survival_ctx["recovery_score"] + 0.18 * money_distress
        if card.name == "과속":
            if player.cash <= reserve + 2.0 or money_distress > 0.8:
                adjustment -= 1.10 + 0.30 * urgency + 0.40 * money_distress
            else:
                adjustment += 0.25 * survival_ctx["cross_start"] + 0.20 * survival_ctx["land_f"]
        if card.name in {"무료 증정", "마당발", "무역의 선물", "긴장감 조성"} and (urgency > 1.0 or money_distress > 0.8):
            adjustment -= 0.65 + 0.45 * urgency + 0.35 * money_distress
        if card.name in {"도움 닫기", "극심한 분리불안"} and controller_need > 0.0:
            adjustment += 0.20 * controller_need
        return adjustment

    def _movement_survival_adjustment(self, state: GameState, player: PlayerState, pos: int, move_total: int, survival_ctx: dict[str, float], *, projected_cash: float | None = None) -> float:
        urgency = float(survival_ctx["survival_urgency"])
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        if urgency <= 0.0 and survival_ctx["cash_after_reserve"] > 0.0 and money_distress <= 0.0:
            return 0.0
        cell = state.board[pos]
        owner = state.tile_owner[pos]
        adjustment = 0.0
        if player.position + move_total >= len(state.board):
            adjustment += 1.55 * max(0.6, urgency) + 0.30 * money_distress
        if cell in {CellKind.F1, CellKind.F2}:
            crosses_start = player.position + move_total >= len(state.board)
            if crosses_start and (float(survival_ctx.get("needs_income", 0.0)) > 0.0 or money_distress > 0.8):
                adjustment += 0.80 + 0.85 * urgency + 0.55 * money_distress
            else:
                adjustment += 0.10 + 0.20 * urgency
        elif cell == CellKind.S:
            adjustment += 0.60 + 0.55 * urgency + 0.30 * money_distress
        elif cell == CellKind.MALICIOUS:
            malicious_cost = state.config.rules.special_tiles.malicious_cost_for(state, pos)
            adjustment -= 0.95 + 0.30 * urgency + 0.20 * money_distress + (0.85 if malicious_cost >= player.cash else 0.0)
        elif cell in {CellKind.T2, CellKind.T3}:
            if owner == player.player_id:
                adjustment += 0.45 + 0.40 * urgency + 0.25 * money_distress
            elif owner is None:
                cost = state.config.rules.economy.purchase_cost_for(state, pos)
                if player.cash >= survival_ctx["reserve"] + cost - 1.0 and money_distress < 1.0:
                    adjustment += 0.20 + 0.18 * urgency
                elif money_distress >= 1.0:
                    adjustment -= 0.45 + 0.25 * money_distress
            else:
                rent = self._public_effective_tile_cost(state, player, pos)
                adjustment -= 0.75 + 0.35 * urgency + 0.25 * money_distress + (1.05 if rent >= player.cash else 0.10 * rent)
        if projected_cash is not None and float(survival_ctx.get("own_burden_cost", 0.0)) > 0.0:
            # [burden_patch] 균일 페널티 대신 F/S 회복 동선 가산으로 교체.
            # 이전 로직(expected_cleanup_gap 페널티)은 모든 착지에 일괄 감점을 줘서
            # 오히려 F/S칸 진입 동기가 약해지는 부작용이 있었다.
            # → 짐 보유 중 F칸/S칸 착지에 추가 보너스를 주는 방식이 더 직관적.
            burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))
            cell = state.board[pos]
            if cell in {CellKind.F1, CellKind.F2}:
                # F칸 착지: 조각+F 획득으로 랩 가속 → 현금 회복 기회 포함
                adjustment += 0.60 + 0.20 * burden_cost
            elif cell == CellKind.S:
                # S칸 착지: 현금 획득 기대값
                adjustment += 0.45 + 0.15 * burden_cost
        return adjustment

    def _f_move_adjustment(self, state: GameState, player: PlayerState, pos: int, move_total: int, survival_ctx: dict[str, float], f_ctx: dict[str, float | bool | int], *, use_cards: bool, card_count: int) -> float:
        cell = state.board[pos]
        if cell not in {CellKind.F1, CellKind.F2}:
            return 0.0
        adjustment = 1.00 * float(f_ctx["land_f_value"])
        if cell == CellKind.F2:
            adjustment += 0.20 * float(f_ctx["land_f_value"])
        crosses_start = player.position + move_total >= len(state.board)
        needs_income = float(survival_ctx.get("needs_income", 0.0)) > 0.0
        # [v3_claude] F 레이스 능동화: F칸 착지에 추가 가산
        # 데이터: F 승리 시 F방문 1.9회 vs 패배 1.3회 → F 방문 빈도가 승패 가름
        if self._profile_from_mode() == "v3_claude":
            f_value = float(f_ctx["land_f_value"])
            adjustment += 0.50 + 0.30 * f_value
            if cell == CellKind.F2:
                adjustment += 0.30  # F2는 +2조각 추가 보상
        if use_cards:
            card_penalty = float(f_ctx["card_f_penalty"]) + 0.30 * max(0, card_count - 1)
            if cell == CellKind.F2:
                card_penalty += 0.20
            if crosses_start and needs_income:
                card_penalty -= 0.55
            adjustment -= card_penalty
        elif not bool(f_ctx["is_leader"]) and not (crosses_start and needs_income):
            adjustment -= 0.25 * float(f_ctx["avoid_f_acceleration"])
        return adjustment

    def _rent_pressure_breakdown(self, state: GameState, player: PlayerState, character_name: str) -> tuple[float, list[str]]:
        known_character = character_name in CHARACTERS
        metrics = self._rent_exposure_metrics(state, player)
        hit_prob = metrics["hit_prob"]
        if hit_prob <= 0.0 and metrics["corridor_density"] <= 0.0:
            return 0.0, []
        reasons: list[str] = []
        pressure = 0.0
        cash_scale = max(8.0, float(player.cash) + 2.0)
        if hit_prob > 0.0:
            pressure += 1.55 * hit_prob
            pressure += 0.85 * metrics["high_hit_prob"]
            pressure += 1.25 * metrics["lethal_hit_prob"]
            pressure += 0.65 * (metrics["avg_cost"] / cash_scale)
            if metrics["peak_cost"] >= player.cash:
                pressure += 0.55
                reasons.append("rent_can_bankrupt")
            reasons.append(f"rent_hit={hit_prob:.2f}")
            reasons.append(f"rent_avg={metrics['avg_cost']:.1f}")
        if metrics["corridor_density"] > 0.0:
            corridor_term = 0.55 * metrics["corridor_density"]
            pressure += corridor_term
            reasons.append(f"rent_corridor={metrics['corridor_density']:.2f}")
        active_names = {name for name in state.active_by_card.values() if name}
        if known_character and "추노꾼" in active_names and character_name != "추노꾼":
            exposure = self._mark_priority_exposure_factor("추노꾼", character_name)
            profile = max(0.55, self._mark_target_profile_factor("추노꾼", character_name))
            if exposure > 0.0:
                enemy_peak = max(self._enemy_rent_costs(state, player) or [0])
                hunter_term = exposure * profile * (0.30 + min(1.15, enemy_peak / cash_scale))
                pressure += hunter_term
                reasons.append(f"hunter_pull={hunter_term:.2f}")
        if player.cash <= 12:
            low_cash_term = 0.18 * max(0.0, 12.0 - player.cash) / 4.0
            pressure += low_cash_term
            if low_cash_term > 0.0:
                reasons.append(f"low_cash={low_cash_term:.2f}")
        return pressure, reasons

    def _apply_rent_pressure_adjustment_v2(self, state: GameState, player: PlayerState, character_name: str, cross_start: float, land_f: float, pressure: float, reasons: list[str]) -> tuple[float, float, float]:
        economy = combo = survival = 0.0
        if pressure <= 0.0:
            return economy, combo, survival
        specials = self._reachable_specials_with_one_short(state, player)
        if character_name == "파발꾼":
            survival += 2.35 * pressure + 0.45 * cross_start
            economy += 0.95 * pressure + 0.20 * land_f
            combo += 0.20 * pressure
            reasons.append("rent_escape_courier")
        elif character_name == "탈출 노비":
            survival += 2.05 * pressure + 0.12 * specials
            economy += 0.55 * pressure + 0.10 * specials
            combo += 0.15 * pressure
            reasons.append("rent_escape_slave")
        elif character_name == "객주":
            survival += 1.70 * pressure + 0.40 * cross_start
            economy += 0.75 * pressure + 0.20 * land_f
            reasons.append("rent_escape_lap")
        elif character_name in RENT_EXPANSION_CHARACTERS:
            survival -= 1.25 * pressure
            reasons.append("rent_growth_penalty")
        elif character_name in RENT_FRAGILE_DISRUPTORS and player.cash < 12:
            survival -= 0.55 * pressure
            reasons.append("rent_fragile_disruptor")
        return economy, combo, survival

    def _apply_rent_pressure_adjustment_v1(self, state: GameState, player: PlayerState, character_name: str, pressure: float, reasons: list[str]) -> float:
        if pressure <= 0.0:
            return 0.0
        score_delta = 0.0
        specials = self._reachable_specials_with_one_short(state, player)
        if character_name == "파발꾼":
            score_delta += 4.0 * pressure
            reasons.append("rent_escape_courier")
        elif character_name == "탈출 노비":
            score_delta += 3.4 * pressure + 0.15 * specials
            reasons.append("rent_escape_slave")
        elif character_name == "객주":
            score_delta += 2.8 * pressure
            reasons.append("rent_escape_lap")
        elif character_name in RENT_EXPANSION_CHARACTERS:
            score_delta -= 2.2 * pressure
            reasons.append("rent_growth_penalty")
        elif character_name in RENT_FRAGILE_DISRUPTORS and player.cash < 12:
            score_delta -= 1.0 * pressure
            reasons.append("rent_fragile_disruptor")
        return score_delta

    def _character_score_breakdown(self, state: GameState, player: PlayerState, character_name: str) -> tuple[float, list[str]]:
        score = self.character_values.get(character_name, 0.0)
        reasons: list[str] = [f"base={score:.1f}"]

        low_cash = player.cash < 8
        very_low_cash = player.cash < 5
        legal_mark_targets = self._allowed_mark_targets(state, player)
        has_mark_targets = bool(legal_mark_targets)
        burden_context = self._burden_context(state, player, legal_targets=legal_mark_targets)
        monopoly = self._monopoly_block_metrics(state, player)
        scammer = self._scammer_takeover_metrics(state, player)
        own_burden = burden_context["own_burdens"]
        cleanup_pressure = burden_context["cleanup_pressure"]
        legal_visible_burden_total = burden_context["legal_visible_burden_total"]
        legal_visible_burden_peak = burden_context["legal_visible_burden_peak"]
        legal_low_cash_targets = burden_context["legal_low_cash_targets"]
        own_near_complete = monopoly["own_near_complete"]
        own_claimable_blocks = monopoly["own_claimable_blocks"]
        deny_now = monopoly["deny_now"]
        enemy_near_complete = monopoly["enemy_near_complete"]
        contested_blocks = monopoly["contested_blocks"]
        enemy_tiles = sum(p.tiles_owned for p in self._alive_enemies(state, player))
        own_tile_income = self._expected_own_tile_income(state, player)
        near_unowned = 0
        board_len = len(state.board)
        for step in range(2, 8):
            pos = (player.position + step) % board_len
            if state.board[pos] in (CellKind.T2, CellKind.T3) and state.tile_owner[pos] is None:
                near_unowned += 1
        uroe_blocked = self._has_uhsa_alive(state, exclude_player_id=player.player_id) and CHARACTERS[character_name].attribute == "무뢰"

        if low_cash and character_name in {"객주", "아전", "박수", "만신"}:
            score += 1.8
            reasons.append("low_cash_economy")
        if very_low_cash and character_name in {"객주", "아전"}:
            score += 1.4
            reasons.append("very_low_cash_recovery")
        if character_name == "건설업자" and very_low_cash and player.shards >= 1:
            score += 1.0
            reasons.append("very_low_cash_free_build")
        if near_unowned >= 2 and character_name == "중매꾼":
            score += 1.10 + self._matchmaker_adjacent_value(state, player)
            reasons.append("near_unowned_expansion")
        elif near_unowned >= 1 and character_name == "중매꾼":
            score += 0.55 + 0.50 * self._matchmaker_adjacent_value(state, player)
            reasons.append("some_expansion_value")
        if near_unowned >= 2 and character_name == "건설업자":
            score += 0.95 + 0.75 * self._builder_free_purchase_value(state, player)
            reasons.append("near_unowned_expansion")
        elif near_unowned >= 1 and character_name == "건설업자":
            score += 0.45 + 0.45 * self._builder_free_purchase_value(state, player)
            reasons.append("some_expansion_value")
        elif near_unowned >= 1 and character_name == "사기꾼":
            score += 0.8
            reasons.append("some_expansion_value")
        if enemy_tiles >= 4 and character_name in {"사기꾼", "산적", "자객", "추노꾼"}:
            score += 1.2
            reasons.append("enemy_board_pressure")
        if character_name == "사기꾼" and scammer["coin_value"] > 0.0:
            score += 1.1 * scammer["coin_value"] + 0.35 * scammer["best_tile_coins"]
            reasons.append("takeover_coin_swing")
        if character_name == "사기꾼" and scammer["blocks_enemy_monopoly"] > 0.0:
            score += 1.6 * scammer["blocks_enemy_monopoly"]
            reasons.append("blocks_monopoly_with_coin_swing")
        if character_name == "사기꾼" and scammer["finishes_own_monopoly"] > 0.0:
            score += 1.4 * scammer["finishes_own_monopoly"]
            reasons.append("finishes_monopoly_via_takeover")
        if own_near_complete > 0 and character_name == "중매꾼":
            score += 2.05 * own_near_complete + 0.55 * own_claimable_blocks + 0.30 * self._matchmaker_adjacent_value(state, player)
            reasons.append("monopoly_finish_value")
        if own_near_complete > 0 and character_name == "건설업자":
            score += 1.85 * own_near_complete + 0.40 * own_claimable_blocks + 0.45 * self._builder_free_purchase_value(state, player)
            reasons.append("monopoly_finish_value")
        elif own_claimable_blocks > 0 and character_name in {"객주", "파발꾼", "탈출 노비"}:
            score += 0.8 * own_claimable_blocks
            reasons.append("monopoly_route_value")
        if enemy_near_complete > 0 and character_name in {"사기꾼", "산적", "자객", "추노꾼"}:
            score += 1.8 * enemy_near_complete + 0.35 * contested_blocks
            reasons.append("deny_enemy_monopoly")
        if player.shards >= 4 and character_name in {"산적", "아전"}:
            score += 1.0
            reasons.append("shard_synergy")
        if own_tile_income >= 2 and character_name == "객주":
            score += 1.2
            reasons.append("own_tile_coin_engine")
        if character_name == "박수" and own_burden >= 1:
            removed, payout = self._failed_mark_fallback_metrics(player, 5)
            score += 1.7 + 1.20 * own_burden + 0.55 * cleanup_pressure + 0.45 * removed + 0.10 * payout
            reasons.append("future_burden_escape")
            if legal_low_cash_targets > 0:
                score += 0.35 * legal_low_cash_targets
                reasons.append("burden_dump_fragile_target")
        elif character_name == "박수" and own_burden == 0:
            # [fallback_patch] 짐이 없으면 박수의 핵심 능력(내 짐 넘기기+잔꾀 획득)을 쓸 수 없다.
            # 지목 실패 폴백도 짐 없으면 아무 효과 없음. 명시적 감점.
            score -= 1.2
            reasons.append("baksu_no_own_burden_waste")
        if character_name == "만신" and legal_visible_burden_total > 0:
            removed, payout = self._failed_mark_fallback_metrics(player, 7)
            score += 1.4 + 1.15 * legal_visible_burden_total + 0.35 * legal_visible_burden_peak + 0.35 * removed + 0.08 * payout
            reasons.append("public_burden_cleanup")
            if legal_low_cash_targets > 0:
                score += 0.35 * legal_low_cash_targets
                reasons.append("cash_fragile_cleanup")
        elif character_name == "만신" and cleanup_pressure >= 2.5 and has_mark_targets:
            score += 0.9
            reasons.append("future_fire_insurance")
        if not has_mark_targets and character_name in {"자객", "산적", "추노꾼", "박수", "만신"}:
            score -= 2.8
            reasons.append("no_mark_targets")
        if self._reachable_specials_with_one_short(state, player) >= 4 and character_name == "탈출 노비":
            score += 1.0
            reasons.append("special_tile_reach")
        if state.marker_owner_id != player.player_id and character_name in {"교리 연구관", "교리 감독관"}:
            score += 0.4
            reasons.append("marker_control_value")
        if uroe_blocked:
            score -= 2.2
            reasons.append("uhsa_blocks_muroe")
        mark_risk, mark_reasons = self._public_mark_risk_breakdown(state, player, character_name)
        if mark_risk > 0.0:
            score -= mark_risk
            reasons.append(f"mark_risk=-{mark_risk:.2f}")
            reasons.extend(mark_reasons)
        rent_pressure, rent_reasons = self._rent_pressure_breakdown(state, player, character_name)
        if rent_pressure > 0.0:
            score += self._apply_rent_pressure_adjustment_v1(state, player, character_name, rent_pressure, reasons)
            reasons.append(f"rent_pressure={rent_pressure:.2f}")
            reasons.extend(rent_reasons)
        return score, reasons

    def _target_score_breakdown(self, state: GameState, player: PlayerState, actor_name: str, target: PlayerState) -> tuple[float, list[str]]:
        score = self.character_values.get(target.current_character, 0.0)
        reasons = [f"target_base={score:.1f}"]
        if actor_name == "자객":
            score += 0.9 * len(target.pending_marks)
            if target.attribute == "무뢰":
                score += 0.8
                reasons.append("reveal_muroe")
            if target.tiles_owned >= 2:
                score += 0.5
                reasons.append("stall_owner")
        elif actor_name == "산적":
            score += 0.7 * player.shards
            score += 0.15 * target.cash
            reasons.append("bandit_shard_scale")
        elif actor_name == "추노꾼":
            landing_owner = state.tile_owner[player.position]
            if landing_owner is not None and landing_owner != target.player_id:
                score += 1.6
                reasons.append("force_into_rent")
            if state.board[player.position] in {CellKind.F1, CellKind.F2, CellKind.S, CellKind.MALICIOUS}:
                score += 1.0
                reasons.append("force_special_tile")
        elif actor_name == "박수":
            remaining = len(state.config.rules.dice.values) - len(target.used_dice_cards)
            burden = self._visible_burden_count(player, target)
            score += 0.4 * remaining + 0.9 * burden + 0.14 * max(0, 12 - target.cash)
            reasons.append("target_many_cards")
        elif actor_name == "만신":
            remaining = len(state.config.rules.dice.values) - len(target.used_dice_cards)
            burden = self._visible_burden_count(player, target)
            score += 0.3 * max(0, 5 - remaining) + 2.0 * burden + 0.12 * max(0, 14 - target.cash)
            reasons.append("target_few_cards")
        return score, reasons


    def choose_trick_to_use(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        supported = {
            "성물 수집가": 1.8, "건강 검진": 1.2, "우대권": 1.4, "무료 증정": 1.6,
            "신의뜻": 1.0, "가벼운 분리불안": 0.9, "극심한 분리불안": 1.2, "마당발": 1.4, "뇌고왕": 1.1, "뇌절왕": 1.3,
            "재뿌리기": 1.2, "긴장감 조성": 1.3, "무역의 선물": 1.0, "도움 닫기": 1.1, "번뜩임": 0.8,
            "느슨함 혐오자": 0.9, "극도의 느슨함 혐오자": 1.5,
            "과속": 0.8, "저속": 0.3, "이럇!": 0.7, "아주 큰 화목 난로": 1.0, "거대한 산불": 1.3,
            "무거운 짐": -0.6, "가벼운 짐": -0.3,
        }
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        best = None
        best_score = 0.0
        details = {}
        for card in hand:
            immediate_cost = self._predict_trick_cash_cost(card)
            if immediate_cost > 0.0 and not self._is_action_survivable(state, player, immediate_cost=immediate_cost, survival_ctx=survival_ctx, buffer=0.5):
                details[card.name] = -999.0
                continue
            score = supported.get(card.name, -99.0)
            if card.name == "무료 증정" and player.cash >= 3:
                score += 0.6
            if card.name == "과속" and player.cash >= 2:
                score += 0.4
            if card.name == "저속":
                score += 0.2 if player.cash < 6 else -0.5
            if card.name == "재뿌리기":
                score += 0.4 if any(state.tile_owner[i] not in {None, player.player_id} for i in range(len(state.board)) if state.tile_at(i).purchase_cost is not None) else -1.0
            if card.name == "긴장감 조성":
                score += 0.5 if player.tiles_owned > 0 else -1.0
            if card.name == "무역의 선물":
                score += 0.4 if player.tiles_owned > 0 and any(own is not None and own != player.player_id for own in state.tile_owner) else -1.0
            if card.name in {"무거운 짐", "가벼운 짐"}:
                score = -1.0
            score += self._trick_survival_adjustment(state, player, card, survival_ctx)
            details[card.name] = round(score, 3)
            if score > best_score:
                best = card
                best_score = score
        self._set_debug("trick_use", player.player_id, {
            "scores": details,
            "chosen": None if best is None else best.name,
            "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
            "survival_urgency": round(survival_ctx["survival_urgency"], 3),
        })
        return best

    def choose_specific_trick_reward(self, state: GameState, player: PlayerState, choices: list[TrickCard]) -> TrickCard | None:
        if not choices:
            return None
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        def score(card: TrickCard) -> float:
            if card.name in {"무거운 짐", "가벼운 짐"}:
                return -10.0
            immediate_cost = self._predict_trick_cash_cost(card)
            if immediate_cost > 0.0 and not self._is_action_survivable(state, player, immediate_cost=immediate_cost, survival_ctx=survival_ctx, buffer=0.5):
                return -999.0
            base = {"무료 증정": 4.0, "우대권": 3.4, "성물 수집가": 3.0, "건강 검진": 2.5, "극도의 느슨함 혐오자": 2.0}.get(card.name, 1.0)
            return base + self._trick_survival_adjustment(state, player, card, survival_ctx)
        pick = max(choices, key=score)
        self._set_debug("trick_reward", player.player_id, {
            "choices": [c.name for c in choices],
            "chosen": pick.name,
            "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
            "survival_urgency": round(survival_ctx["survival_urgency"], 3),
        })
        return pick

    def choose_burden_exchange_on_supply(self, state: GameState, player: PlayerState, card: TrickCard) -> bool:
        # [burden_patch v2] 짐은 들고 있을수록 다음 청산 때 비용이 복리로 커진다.
        # 원칙: 청산 비용을 낼 수 있으면 최대한 빨리 청산한다.
        # 예외: 이번 청산 후 다른 짐까지 합산한 총 청산 비용을 낼 여력이 전혀 없을 때만 보류.
        # (어차피 이번 청산을 거부해도 다음에 더 비싸게 터지므로 "차라리 지금")
        if player.cash < card.burden_cost:
            return False
        if self._is_random_mode():
            return True
        remaining_cash = player.cash - card.burden_cost
        # 이 카드 외 다른 짐 카드들의 총 비용
        other_burden_total = sum(
            float(c.burden_cost) for c in player.trick_hand
            if c.is_burden and c.deck_index != card.deck_index
        )
        # 청산 후 다른 짐 비용까지 낼 수 있거나, 아예 짐이 이것 하나뿐이면 → 무조건 청산
        if remaining_cash >= other_burden_total:
            return True
        # 청산 후 다른 짐도 못 내는 극빈 상황: 그래도 지금 청산하는 게 낫다.
        # (보류하면 다음 청산 이벤트 때 이 카드 + 나머지 카드 전부 한꺼번에 터짐)
        # → 현금 >= 이 카드 비용 + 최소 생존선(3냥)이면 청산
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        min_floor = 3.0 + float(survival_ctx.get("two_turn_lethal_prob", 0.0)) * 4.0
        return remaining_cash >= min_floor

    def choose_hidden_trick_card(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        return None

    def choose_movement(self, state: GameState, player: PlayerState) -> MovementDecision:
        best_score = -10**9
        best = MovementDecision(False, ())
        board_len = len(state.board)
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        f_ctx = self._f_progress_context(state, player)

        token_profile = self._profile_from_mode() == "token_opt"
        v3_profile = self._profile_from_mode() == "v3_claude"
        placeable_tiles = set(self._placeable_own_tiles(state, player))

        def _move_bonus(pos: int) -> float:
            bonus = 0.0
            if token_profile and pos in placeable_tiles and player.hand_coins > 0:
                revisit_gap = (pos - player.position) % board_len
                bonus += 8.5 + 0.9 * state.tile_coins[pos] + (1.2 if revisit_gap <= 4 else 0.4)
            if token_profile and state.tile_owner[pos] == player.player_id:
                bonus += 2.2 + 0.25 * state.tile_coins[pos]
            if token_profile and state.board[pos] in {CellKind.F1, CellKind.F2}:
                bonus += max(0.0, 0.35 * float(f_ctx["land_f_value"]))
            # [v3_claude] 탐관오리 전략: 상대가 내 칸으로 오면 조각 2개당 1냥 수취
            # 탐관오리는 이동 방향이 아니라 '머물 위치'가 중요
            # → 상대 플레이어들이 자주 지나가는 칸(교통량 높은 칸)에 위치하는 게 유리
            # → 이동 결정: 상대 뒤쪽(상대가 지나쳐갈 위치)보다는 빈 타일 매입이 우선
            # (별도 이동 보너스 없음 - 탐관오리의 이동 우선순위는 일반 구매/F칸 논리를 따름)
            return bonus

        def _eval_move(pos: int, move_total: int, *, use_cards: bool = False, card_count: int = 0) -> float:
            predicted_cost = self._predict_tile_landing_cost(state, player, pos)
            cell = state.board[pos]
            # [burden_patch v3] 악성 타일 강화 회피:
            # 카드 사용 여부와 무관하게, 악성 타일 비용이 생존선을 침범하면 하드 블록
            if cell == CellKind.MALICIOUS and predicted_cost > 0.0:
                if not self._is_action_survivable(state, player, immediate_cost=predicted_cost, survival_ctx=survival_ctx, buffer=0.0):
                    return -10**8
            if use_cards and predicted_cost > 0.0 and not self._is_action_survivable(state, player, immediate_cost=predicted_cost, survival_ctx=survival_ctx, buffer=0.5 * card_count):
                return -10**8
            projected_cash = self._project_end_turn_cash(state, player, immediate_cost=predicted_cost, crosses_start=(player.position + move_total >= len(state.board)))
            score = self._landing_score(state, player, pos)
            score += _move_bonus(pos)
            score += self._movement_survival_adjustment(state, player, pos, move_total, survival_ctx, projected_cash=projected_cash)
            score += self._f_move_adjustment(state, player, pos, move_total, survival_ctx, f_ctx, use_cards=use_cards, card_count=card_count)
            if use_cards and predicted_cost > 0.0 and not self._is_action_survivable(state, player, immediate_cost=predicted_cost, survival_ctx=survival_ctx, buffer=0.0):
                score -= 8.0
            return score

        base_scores = []
        for d1 in range(1, 7):
            for d2 in range(1, 7):
                move_total = d1 + d2
                pos = (player.position + move_total) % board_len
                base_scores.append(_eval_move(pos, move_total, use_cards=False, card_count=0))
        avg_no_cards = sum(base_scores) / len(base_scores)
        best_score = avg_no_cards

        # [burden_patch v3] 악성 타일 회피 우선: 카드 없이 가면 악성 타일이 불가피할 때
        # 주사위 카드로 악성 타일을 피할 수 있으면 평균 점수 비교 대신 우선 선택
        no_card_malicious_unavoidable = all(
            state.board[(player.position + d1 + d2) % board_len] == CellKind.MALICIOUS
            or not self._is_action_survivable(
                state, player,
                immediate_cost=self._predict_tile_landing_cost(state, player, (player.position + d1 + d2) % board_len),
                survival_ctx=survival_ctx, buffer=0.0,
            )
            for d1 in range(1, 7) for d2 in range(1, 7)
        )

        remaining = self._remaining_cards(player)
        for c in remaining:
            vals = []
            for d in range(1, 7):
                move_total = c + d
                pos = (player.position + move_total) % board_len
                vals.append(_eval_move(pos, move_total, use_cards=True, card_count=1))
            score = sum(vals) / len(vals)
            # 카드로 악성 타일을 일부 피할 수 있고, 카드 없인 불가피하면 보너스
            if no_card_malicious_unavoidable:
                safe_count = sum(
                    1 for d in range(1, 7)
                    if state.board[(player.position + c + d) % board_len] != CellKind.MALICIOUS
                    and self._is_action_survivable(
                        state, player,
                        immediate_cost=self._predict_tile_landing_cost(state, player, (player.position + c + d) % board_len),
                        survival_ctx=survival_ctx, buffer=0.0,
                    )
                )
                if safe_count > 0:
                    score += 4.0 + 0.8 * safe_count  # 악성 회피 가능성에 강한 보너스
            if score > best_score:
                best_score = score
                best = MovementDecision(True, (c,))
        for a, b in combinations(remaining, 2):
            move_total = a + b
            pos = (player.position + move_total) % board_len
            score = _eval_move(pos, move_total, use_cards=True, card_count=2)
            if score > best_score:
                best_score = score
                best = MovementDecision(True, (a, b))
        return best

    def choose_lap_reward(self, state: GameState, player: PlayerState) -> LapRewardDecision:
        mode = self._lap_mode_for_player(player.player_id)
        if mode == "cash_focus":
            return self._lap_reward_bundle(state, 1.0, 0.01, 0.01, preferred="cash")
        if mode == "shard_focus":
            return self._lap_reward_bundle(state, 0.01, 1.0, 0.01, preferred="shards")
        if mode == "coin_focus":
            return self._lap_reward_bundle(state, 0.01, 0.01, 1.0, preferred="coins")
        placeable = any(state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile for i in player.visited_owned_tile_indices)
        buy_value = self._expected_buy_value(state, player)
        cross_start = self._will_cross_start(state, player)
        land_f = self._will_land_on_f(state, player)
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        f_ctx = self._f_progress_context(state, player)
        # [burden_patch] survival_urgency >= 1.0 이 너무 늦은 트리거였음.
        # 짐 2장 이상이거나 latent_cleanup_cost 가 현금 50% 초과면 urgency 무관하게 현금 압박 상태로 본다.
        _scp_burdens = sum(1 for c in player.trick_hand if c.is_burden)
        _scp_latent = float(survival_ctx.get("latent_cleanup_cost", 0.0))
        survival_cash_pressure = (
            (
                survival_ctx["survival_urgency"] >= 1.0
                and (
                    player.cash <= 4
                    or survival_ctx["rent_pressure"] >= 1.2
                    or survival_ctx["lethal_hit_prob"] > 0.0
                    or survival_ctx["own_burden_cost"] > 0.0
                    or survival_ctx["cleanup_pressure"] >= 2.0
                )
            )
            or (_scp_burdens >= 2)
            or (_scp_burdens >= 1 and _scp_latent >= player.cash * 0.5)
        )
        if mode.startswith("heuristic_v2_"):
            profile = self._profile_from_mode(mode)
            preferred_override: str | None = None
            current_char = player.current_character
            coin_score = (2.5 if placeable else -0.5) + (1.6 if current_char in {"객주", "사기꾼"} else 0.0) + 1.2 * cross_start
            if current_char == "중매꾼":
                coin_score += 0.9 + 0.35 * self._matchmaker_adjacent_value(state, player)
            elif current_char == "건설업자":
                coin_score += 1.00 + 0.55 * self._builder_free_purchase_value(state, player)
            shard_score = 0.8 + (1.9 if current_char in {"산적", "탐관오리", "아전"} else 0.0) + 0.35 * max(0, 6 - player.shards) + max(0.0, 0.7 * land_f * float(f_ctx["land_f_value"]))
            if current_char == "중매꾼" and player.shards < 2:
                shard_score += 0.75 + 0.20 * max(0, 2 - player.shards)
            if current_char == "박수":
                # 폴백 임계(5개) 미달: 조각 적극 모으기. 임계 달성 후: 현금/코인 전환
                if player.shards < 5:
                    shard_score += 0.80 + 0.12 * (5 - player.shards)
                else:
                    shard_score -= 0.30  # 임계 달성 후 조각 선호 억제 → 현금/코인으로
            if current_char == "만신":
                # 폴백 임계(7개) 미달: 적극 모으기. 임계 달성 후: 현금/코인 전환
                visible_enemy_burdens = sum(
                    self._visible_burden_count(state.players[player.player_id], p)
                    for p in state.players
                    if p.alive and p.player_id != player.player_id
                )
                if player.shards < 7:
                    base_shard = 0.70 + 0.10 * (7 - player.shards)
                else:
                    base_shard = -0.20  # 임계 달성 후 억제
                shard_score += base_shard + 0.15 * min(2, visible_enemy_burdens)
            cash_score = 1.2 + 0.4 * max(0, 10 - player.cash)
            if survival_cash_pressure:
                cash_score += 1.35 + 0.95 * survival_ctx["survival_urgency"] + 0.25 * max(0.0, -survival_ctx["cash_after_reserve"])
                coin_score -= 0.55 * survival_ctx["survival_urgency"]
                shard_score -= 0.40 * survival_ctx["survival_urgency"]
                if placeable and survival_ctx["recovery_score"] >= 1.2:
                    coin_score += 0.25
            # [burden_patch] 짐 보유 시 랩보상에서 현금 선택 압력 추가
            # latent_cleanup_cost 가 크거나 짐을 여러 장 들고 있으면 현금으로 유동성을 확보해야 한다.
            _lap_latent = float(survival_ctx.get("latent_cleanup_cost", 0.0))
            _lap_burdens = float(survival_ctx.get("own_burdens", 0.0))
            _lap_expected = float(survival_ctx.get("expected_cleanup_cost", 0.0))
            if _lap_burdens >= 1.0:
                # 짐 1장당 +0.70, latent_cleanup / expected_cleanup 가중치 반영
                cash_score += 0.70 * _lap_burdens + 0.40 * _lap_latent + 0.35 * _lap_expected
                coin_score -= 0.30 * _lap_burdens
                shard_score -= 0.20 * _lap_burdens
            if not bool(f_ctx["is_leader"]):
                cash_score += 0.45 + 0.30 * float(f_ctx["avoid_f_acceleration"])
                shard_score -= 0.35 + 0.20 * float(f_ctx["avoid_f_acceleration"])
            if current_char == "객주":
                shard_score += max(0.0, 0.9 * land_f * float(f_ctx["land_f_value"]))
                coin_score += 0.8 * cross_start
            if profile == "control":
                denial_snapshot = self._leader_denial_snapshot(state, player)
                emergency = float(denial_snapshot["emergency"])
                liquidity = self._liquidity_risk_metrics(state, player, player.current_character)
                rent_pressure, _ = self._rent_pressure_breakdown(state, player, player.current_character or "")
                burden_count = sum(1 for c in player.trick_hand if c.is_burden)
                burden_context = self._burden_context(state, player)
                cleanup_pressure = float(burden_context.get("cleanup_pressure", 0.0))
                low_cash = max(0.0, 7.0 - player.cash)
                finisher_window, _ = self._control_finisher_window(player)
                shard_score += 1.1 + 0.55 * emergency
                cash_score += 0.1
                if denial_snapshot.get("solo_leader"):
                    shard_score += 0.45
                if denial_snapshot.get("near_end"):
                    shard_score += 0.55
                if player.current_character in {"교리 연구관", "교리 감독관", "산적", "탐관오리", "아전", "어사", "사기꾼"}:
                    shard_score += 0.4
                if placeable:
                    coin_score += 0.45
                if finisher_window > 0.0 and placeable and liquidity["cash_after_reserve"] >= 0.5:
                    coin_score += 1.85 + 0.55 * finisher_window
                    cash_score += 0.25 * finisher_window
                    preferred_override = "coins"
                if finisher_window > 0.0 and buy_value > 0.0 and liquidity["cash_after_reserve"] >= 0.0:
                    cash_score += 0.35 + 0.15 * finisher_window
                if low_cash > 0.0:
                    cash_score += 0.55 * low_cash
                if liquidity["cash_after_reserve"] <= 0.0:
                    cash_score += 0.9 + 0.2 * max(0.0, -float(liquidity["cash_after_reserve"]))
                if rent_pressure >= 1.7:
                    cash_score += 0.45 + 0.18 * rent_pressure
                if burden_count >= 1 and cleanup_pressure >= 2.2:
                    cash_score += 0.5 + 0.18 * burden_count + 0.08 * max(0.0, cleanup_pressure - 2.2)
                if player.cash <= 3:
                    cash_score += 2.0
                elif player.cash <= 5 and liquidity["cash_after_reserve"] <= -0.5 and emergency < 3.0:
                    cash_score += 1.5
                elif player.cash <= 6 and rent_pressure >= 2.0 and emergency < 2.6:
                    cash_score += 1.25
            elif profile == "growth":
                shard_score += 0.4
                coin_score += 0.8
            elif profile == "avoid_control":
                cash_score += 0.8
            elif profile == "aggressive":
                coin_score += 1.8
                cash_score -= 0.2
            elif profile == "token_opt":
                own_land = self._prob_land_on_placeable_own_tile(state, player)
                token_combo = self._token_teleport_combo_score(player)
                token_window = self._token_placement_window_metrics(state, player)
                coin_score += 1.8 + 2.1 * own_land + 0.9 * token_combo + 0.75 * token_window["window_score"]
                if token_window["placeable_count"] <= 0.0:
                    coin_score -= 2.1
                    cash_score += 0.55
                if token_window["nearest_distance"] <= 4.0:
                    coin_score += 0.9
                if token_window["revisit_prob"] >= 0.28:
                    coin_score += 0.8
                if player.hand_coins >= 3 and token_window["revisit_prob"] < 0.12:
                    cash_score += 0.9
                shard_score += max(0.0, 0.20 * land_f * float(f_ctx["land_f_value"]))
                cash_score -= 0.2
            elif profile == "v3_claude":
                # [v3_claude v2] 랩보상 원칙:
                # 초반(랩 1회 이하): 코인 투자 가능 (타일 기반 구축)
                # 중반(랩 2회+): 현금 우선 전환
                # 조각: 인물별 임계까지만, 항상 산적/탐관오리/아전 보정 포함
                laps_done = getattr(state, 'rounds_completed', 0) // max(1, sum(1 for p in state.players if p.alive))
                char = current_char or ""

                # 조각 임계
                shard_threshold = 5 if char == "박수" else 7 if char == "만신" else 4
                gap = shard_threshold - player.shards
                if gap > 0:
                    # 임계까지 부족한 만큼 강하게 선호
                    # 특히 임계 바로 1개 아래(gap=1)일 때 강제에 가깝게
                    urgency_bonus = 2.0 if gap == 1 else (0.8 + 0.12 * gap)
                    shard_score += urgency_bonus
                    if gap == 1 and char in {"박수", "만신"}:
                        # 조각 1개만 더 있으면 폴백 확정 → 현금/코인 억제
                        cash_score -= 0.8
                        coin_score -= 0.8
                        reasons_lap = f"shard_one_away_from_fallback({char})"
                elif char in {"산적", "탐관오리", "아전"}:
                    shard_score += 0.5  # 조각 현금환전 인물은 계속 유지
                else:
                    shard_score -= 0.3  # 임계 초과 억제

                # 코인: 초반 + 타일 있고 재방문 가능할 때만
                if laps_done <= 1 and placeable:
                    token_window = self._token_placement_window_metrics(state, player)
                    if token_window["revisit_prob"] >= 0.18:
                        coin_score += 1.0 + 0.6 * token_window["revisit_prob"]
                    else:
                        coin_score -= 0.2
                elif placeable and player.hand_coins < 1:
                    token_window = self._token_placement_window_metrics(state, player)
                    if token_window["revisit_prob"] >= 0.25:
                        coin_score += 0.6
                    else:
                        coin_score -= 0.4
                else:
                    coin_score -= 0.5

                # 현금: 중후반 강화 + 생존 압박 시
                cash_score += 0.5 + 0.2 * max(0, laps_done - 1)
                if player.cash < 10:
                    cash_score += 0.8
            cash_unit = cash_score / max(1.0, float(state.config.coins.lap_reward_cash))
            shard_unit = shard_score / max(1.0, float(state.config.shards.lap_reward_shards))
            coin_unit = coin_score / max(1.0, float(state.config.coins.lap_reward_coins))
            preferred = preferred_override or max([("cash", cash_score), ("shards", shard_score), ("coins", coin_score)], key=lambda x: x[1])[0]
            return self._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
        if mode == "balanced":
            if survival_cash_pressure:
                return self._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
            if placeable and player.hand_coins < 2:
                return self._lap_reward_bundle(state, 0.2, 0.1, 1.0, preferred="coins")
            if player.cash < 8:
                return self._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
            if player.current_character in {"산적", "탐관오리", "아전"} or player.shards < 4:
                return self._lap_reward_bundle(state, 0.2, 1.0, 0.1, preferred="shards")
            return self._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
        if survival_cash_pressure:
            return self._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
        if player.cash < 8:
            return self._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
        if player.current_character in {"산적", "탐관오리", "아전"}:
            return LapRewardDecision("shards")
        if placeable:
            return LapRewardDecision("coins")
        return self._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")

    def choose_coin_placement_tile(self, state: GameState, player: PlayerState) -> Optional[int]:
        candidates = [
            i for i in player.visited_owned_tile_indices
            if state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
        ]
        if not candidates:
            return None
        if self._profile_from_mode() == "token_opt":
            board_len = len(state.board)
            return max(candidates, key=lambda i: (
                state.tile_coins[i],
                state.board[i] == CellKind.T3,
                -(((i - player.position) % board_len) or board_len),
                state.config.rules.token.max_coins_per_tile - state.tile_coins[i],
                -i,
            ))
        return max(candidates, key=lambda i: (state.config.rules.token.max_coins_per_tile - state.tile_coins[i], state.board[i] == CellKind.T3, -i))

    def _would_complete_monopoly_with_purchase(self, state: GameState, player: PlayerState, pos: int) -> bool:
        block_id = state.block_ids[pos]
        if block_id < 0:
            return False
        idxs = [i for i, bid in enumerate(state.block_ids) if bid == block_id and state.board[i] in {CellKind.T2, CellKind.T3}]
        if not idxs:
            return False
        for idx in idxs:
            if idx == pos:
                continue
            if state.tile_owner[idx] != player.player_id:
                return False
        return True

    def choose_purchase_tile(self, state: GameState, player: PlayerState, pos: int, cell: CellKind, cost: int, *, source: str = "landing") -> bool:
        if cost <= 0 or self._is_random_mode():
            return True
        liquidity = self._liquidity_risk_metrics(state, player, player.current_character)
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        remaining_cash = player.cash - cost
        reserve = max(float(liquidity["reserve"]), float(survival_ctx["reserve"]))
        if not self._is_action_survivable(state, player, immediate_cost=float(cost), survival_ctx=survival_ctx, reserve_floor=reserve, buffer=0.5):
            self._set_debug("purchase_decision", player.player_id, {
                "source": source,
                "pos": pos,
                "cell": cell.name,
                "cost": cost,
                "decision": False,
                "reason": "global_action_survival_guard",
                "reserve": round(float(reserve), 3),
                "cash": player.cash,
            })
            return False
        complete_monopoly = self._would_complete_monopoly_with_purchase(state, player, pos)
        blocks_enemy = self._would_block_enemy_monopoly_with_purchase(state, player, pos)
        immediate_win = False
        if state.config.rules.end.tiles_to_trigger_end and player.tiles_owned + 1 >= state.config.rules.end.tiles_to_trigger_end:
            immediate_win = True
        if state.config.rules.end.monopolies_to_trigger_end and complete_monopoly:
            immediate_win = True
        if immediate_win:
            decision = True
        else:
            benefit = 0.8
            if cell == CellKind.T3:
                benefit += 1.4
            elif cell == CellKind.T2:
                benefit += 0.8
            if complete_monopoly:
                benefit += 2.4
            if blocks_enemy:
                benefit += 3.2
            elif state.block_ids[pos] >= 0:
                owned_in_block = sum(1 for i, bid in enumerate(state.block_ids) if bid == state.block_ids[pos] and state.tile_owner[i] == player.player_id)
                benefit += 0.45 * owned_in_block
            profile = self._profile_from_mode()
            if profile in {"growth", "aggressive"}:
                benefit += 0.35
            if profile == "token_opt" and state.tile_owner[pos] is None:
                benefit += 0.25
            # [burden_patch] aggressive/token_opt/growth는 기본 survival 가중치가 낮아
            # 짐 보유 중에도 구매를 강행하는 경향이 있다.
            # 짐 보유 시 benefit을 프로파일별로 추가 감산해 구매 억제를 보완한다.
            own_burden_count_purchase = sum(1 for c in player.trick_hand if c.is_burden)
            if own_burden_count_purchase >= 1:
                burden_benefit_penalty = {
                    "aggressive": 0.55,
                    "token_opt":  0.35,
                    "growth":     0.30,
                    "balanced":   0.10,
                    "control":    0.05,
                    "avoid_control": 0.0,
                    "v3_claude":  0.45,  # 짐 보유 중 구매 강하게 억제 (생존 우선)
                }.get(profile, 0.10)
                benefit -= burden_benefit_penalty * own_burden_count_purchase
            money_distress = float(survival_ctx.get("money_distress", 0.0))
            reserve_floor = reserve + 1.25 * float(survival_ctx.get("two_turn_lethal_prob", 0.0)) + 0.65 * money_distress
            # [burden_patch] 짐 보유 중 구매 억제 강화: latent/expected 가중치를 0.28/0.22 → 0.65/0.50 으로 상향
            # 짐을 들고 있는 상태에서 구매로 현금을 소진하면 청산 시 파산 위험이 크게 높아진다.
            latent_cleanup = float(survival_ctx.get("latent_cleanup_cost", 0.0))
            expected_cleanup = float(survival_ctx.get("expected_cleanup_cost", 0.0))
            # [v3_claude] 짐 없을 때 reserve_floor 경감 (구매 억제 과잉 해소)
            #             짐 있을 때 reserve_floor 강화 (파산 방지)
            if profile == "v3_claude":
                if own_burden_count_purchase == 0:
                    # 짐 없으면 latent/expected 반영 비율을 낮춰 구매 문턱 낮춤
                    reserve_floor += 0.30 * latent_cleanup
                    reserve_floor += 0.20 * expected_cleanup
                else:
                    # 짐 보유 중엔 기존보다 더 강하게 reserve 확보
                    reserve_floor += 0.85 * latent_cleanup
                    reserve_floor += 0.70 * expected_cleanup
            else:
                reserve_floor += 0.65 * latent_cleanup
                reserve_floor += 0.50 * expected_cleanup
            if float(survival_ctx.get("public_cleanup_active", 0.0)) > 0.0:
                reserve_floor += 0.65 * float(survival_ctx.get("active_cleanup_cost", 0.0))
            if float(survival_ctx.get("needs_income", 0.0)) > 0.0:
                reserve_floor += 1.0
            shortfall = max(0.0, reserve_floor - remaining_cash)
            danger_cash = remaining_cash <= max(5.0, 0.60 * reserve_floor)
            own_burdens = float(survival_ctx.get("own_burdens", 0.0))
            cleanup_lock = (
                float(survival_ctx.get("public_cleanup_active", 0.0)) > 0.0
                and remaining_cash < float(survival_ctx.get("active_cleanup_cost", 0.0))
                and not blocks_enemy and not complete_monopoly
            ) or (
                float(survival_ctx.get("latent_cleanup_cost", 0.0)) >= max(8.0, player.cash * 0.8)
                and remaining_cash < reserve_floor
                and not blocks_enemy and not complete_monopoly
            ) or (
                # [burden_patch] 짐 2장 이상 보유 중 현금이 빠듯하면 구매 차단
                own_burdens >= 2.0
                and float(survival_ctx.get("expected_cleanup_cost", 0.0)) >= player.cash * 0.45
                and remaining_cash < reserve_floor
                and not blocks_enemy and not complete_monopoly
            )
            # [v3_claude + 시스템 이해] 박수 + 조각 5개 이상 + 짐 있으면
            # 폴백이 확정되어 짐 파산 위험이 없으므로 cleanup_lock 해제
            if profile == "v3_claude" and cleanup_lock and own_burden_count_purchase >= 1:
                if player.current_character == "박수" and player.shards >= 5:
                    cleanup_lock = False  # 폴백으로 짐 해소 확정 → 구매 허용
            decision = not (
                shortfall > benefit
                or (danger_cash and shortfall > 0.25)
                or (money_distress >= 1.1 and not blocks_enemy and not complete_monopoly and remaining_cash < reserve_floor + 1.0)
                or cleanup_lock
            )
        self._set_debug("purchase_decision", player.player_id, {
            "source": source,
            "pos": pos,
            "cell": cell.name,
            "cost": cost,
            "cash_before": player.cash,
            "cash_after": remaining_cash,
            "reserve": round(reserve, 3),
            "money_distress": round(float(survival_ctx.get("money_distress", 0.0)), 3),
            "two_turn_lethal_prob": round(float(survival_ctx.get("two_turn_lethal_prob", 0.0)), 3),
            "latent_cleanup_cost": round(float(survival_ctx.get("latent_cleanup_cost", 0.0)), 3),
            "cleanup_cash_gap": round(float(survival_ctx.get("cleanup_cash_gap", 0.0)), 3),
            "expected_loss": round(liquidity["expected_loss"], 3),
            "worst_loss": round(liquidity["worst_loss"], 3),
            "blocks_enemy_monopoly": blocks_enemy,
            "decision": decision,
        })
        return decision

    def _escape_package_names(self) -> set[str]:
        return {"박수", "만신", "탈출 노비"}

    def _marker_package_names(self) -> set[str]:
        return {"교리 연구관", "교리 감독관"}

    def _lap_reward_bundle(self, state: GameState, cash_unit_score: float, shard_unit_score: float, coin_unit_score: float, preferred: str | None = None) -> LapRewardDecision:
        rules = state.config.rules.lap_reward
        rem_cash = max(0, int(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool)))
        rem_shards = max(0, int(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool)))
        rem_coins = max(0, int(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool)))
        best: tuple[float, int, int, int, str] | None = None
        preferred_bonus = {preferred: 0.08} if preferred else {}
        for cash_units in range(0, min(rem_cash, rules.points_budget // max(1, rules.cash_point_cost)) + 1):
            cash_points = cash_units * rules.cash_point_cost
            if cash_points > rules.points_budget:
                break
            shard_cap = min(rem_shards, (rules.points_budget - cash_points) // max(1, rules.shards_point_cost))
            for shard_units in range(0, shard_cap + 1):
                spent = cash_points + shard_units * rules.shards_point_cost
                coin_cap = min(rem_coins, (rules.points_budget - spent) // max(1, rules.coins_point_cost))
                for coin_units in range(0, coin_cap + 1):
                    total_spent = spent + coin_units * rules.coins_point_cost
                    if total_spent <= 0 or total_spent > rules.points_budget:
                        continue
                    utility = (
                        cash_units * cash_unit_score
                        + shard_units * shard_unit_score
                        + coin_units * coin_unit_score
                        + 0.02 * total_spent
                    )
                    if preferred:
                        dominant = max(((cash_units, "cash"), (shard_units, "shards"), (coin_units, "coins")), key=lambda item: (item[0], preferred_bonus.get(item[1], 0.0)))[1]
                        utility += preferred_bonus.get(dominant, 0.0)
                    candidate = (utility, cash_units, shard_units, coin_units, preferred or "mixed")
                    if best is None or candidate > best:
                        best = candidate
        if best is None:
            return LapRewardDecision("blocked")
        _, cash_units, shard_units, coin_units, _ = best
        components = [(cash_units, "cash"), (shard_units, "shards"), (coin_units, "coins")]
        choice = max(components, key=lambda item: item[0])[1] if sum(v for v, _ in components) > 0 else "blocked"
        if preferred == "cash" and cash_units > 0:
            choice = "cash"
        elif preferred == "shards" and shard_units > 0:
            choice = "shards"
        elif preferred == "coins" and coin_units > 0:
            choice = "coins"
        return LapRewardDecision(choice=choice, cash_units=cash_units, shard_units=shard_units, coin_units=coin_units)


    def _should_seek_escape_package(self, state: GameState, player: PlayerState) -> bool:
        burden_count = sum(1 for c in player.trick_hand if c.name in {"무거운 짐", "가벼운 짐"})
        legal_marks = self._allowed_mark_targets(state, player)
        burden_context = self._burden_context(state, player, legal_targets=legal_marks)
        cleanup_pressure = float(burden_context.get("cleanup_pressure", 0.0))
        rent_pressure, _ = self._rent_pressure_breakdown(state, player, player.current_character or "")
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        two_turn_lethal_prob = float(survival_ctx.get("two_turn_lethal_prob", 0.0))
        cash_after_reserve = float(survival_ctx.get("cash_after_reserve", 0.0))
        front_enemy_density = float(survival_ctx.get("front_enemy_density", 0.0))
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        if two_turn_lethal_prob >= 0.18:
            return True
        if money_distress >= 1.15:
            return True
        if controller_need >= 0.85 and float(survival_ctx.get("active_drain_pressure", 0.0)) > 0.0:
            return True
        if rent_pressure >= 1.9:
            return True
        if player.cash <= 8 and (burden_count >= 1 or cash_after_reserve <= 0.0):
            return True
        if burden_count >= 1 and cleanup_pressure >= 2.5:
            return True
        if front_enemy_density >= 0.70 and player.cash <= 10:
            return True
        return cash_after_reserve <= -2.0

    def _distress_marker_bonus(self, state: GameState, player: PlayerState, candidate_names: list[str]) -> dict[str, float]:
        bonus = {name: 0.0 for name in candidate_names}
        if not candidate_names:
            return bonus
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        rescue_pressure = self._should_seek_escape_package(state, player)
        denial_snapshot = self._leader_denial_snapshot(state, player) if self._is_v2_mode() else {"emergency": 0.0, "near_end": False, "top_threat": None}
        leader_emergency = float(denial_snapshot["emergency"])
        urgent_denial = self._is_v2_mode() and leader_emergency >= 2.0
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        if not rescue_pressure and not urgent_denial and controller_need <= 0.0:
            return bonus
        rescue_names = self._escape_package_names()
        direct_denial_names = {"자객", "산적", "추노꾼", "사기꾼", "박수", "만신", "어사"}
        marker_names = self._marker_package_names()
        available_markers = [name for name in candidate_names if name in marker_names]
        if not available_markers:
            return bonus
        active_names = {name for name in state.active_by_card.values() if name}
        future_rescue_live = bool(active_names & rescue_names)
        direct_options = [name for name in candidate_names if name in direct_denial_names]
        marker_plan = self._leader_marker_flip_plan(state, player, denial_snapshot.get("top_threat")) if urgent_denial else {"best_score": 0.0}
        marker_counter = float(marker_plan["best_score"])
        base = 0.0
        if rescue_pressure and not any(name in rescue_names for name in candidate_names):
            base = max(base, 2.35 if future_rescue_live else 1.55)
        if controller_need > 0.0:
            base = max(base, 1.35 + 0.75 * controller_need + 0.20 * float(survival_ctx.get("money_distress", 0.0)))
        if urgent_denial:
            base = max(base, 1.55 + 0.30 * leader_emergency + 0.70 * marker_counter + (0.30 if denial_snapshot["near_end"] else 0.0))
            if direct_options:
                base -= 0.35
            if marker_counter <= 0.0 and direct_options and controller_need <= 0.0:
                return bonus
        for name in available_markers:
            bonus[name] = max(0.0, base)
            if state.marker_owner_id != player.player_id:
                bonus[name] += 0.55
        return bonus

    def choose_draft_card(self, state: GameState, player: PlayerState, offered_cards: list[int]) -> int:
        if self._is_random_mode():
            choice = self._choice(offered_cards)
            self._set_debug("draft_card", player.player_id, {
                "policy": self.character_policy_mode,
                "offered_cards": offered_cards,
                "candidate_scores": {str(c): 0.0 for c in offered_cards},
                "chosen_card": choice,
                "reasons": ["uniform_random"],
            })
            return choice
        scored = {}
        reasons = {}
        survival_ctx, survival_orchestrator = self._build_survival_orchestrator(state, player, player.current_character)
        marker_bonus = self._distress_marker_bonus(state, player, [state.active_by_card[c] for c in offered_cards])
        for card_no in offered_cards:
            active_name = state.active_by_card[card_no]
            score, why = (self._character_score_breakdown_v2(state, player, active_name) if self._is_v2_mode() else self._character_score_breakdown(state, player, active_name))
            survival_policy_bonus, survival_policy_why, survival_hard_block, survival_detail = self._survival_policy_character_advice(state, player, active_name, survival_orchestrator)
            if survival_policy_bonus != 0.0:
                score += survival_policy_bonus
                why = [*why, *survival_policy_why]
            bonus = marker_bonus.get(active_name, 0.0)
            if bonus > 0.0:
                bonus *= max(1.0, survival_orchestrator.weight_multiplier if survival_orchestrator.survival_first and active_name in LOW_CASH_INCOME_CHARACTERS | LOW_CASH_ESCAPE_CHARACTERS | LOW_CASH_CONTROLLER_CHARACTERS | {"박수", "만신"} else 1.0)
                score += bonus
                why = [*why, f"distress_marker_bonus={bonus:.2f}"]
            survival_bonus, survival_why = self._character_survival_adjustment(state, player, active_name, survival_ctx)
            if survival_bonus != 0.0:
                score += survival_bonus
                why = [*why, *survival_why]
            scored[card_no] = score
            reasons[card_no] = why
        choice = max(offered_cards, key=lambda c: (scored[c], -c))
        self._set_debug("draft_card", player.player_id, {
            "policy": self.character_policy_mode,
            "offered_cards": offered_cards,
            "candidate_scores": {str(c): round(scored[c], 3) for c in offered_cards},
            "candidate_characters": {str(c): state.active_by_card[c] for c in offered_cards},
            "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
            "survival_urgency": round(survival_ctx["survival_urgency"], 3),
            "survival_first": survival_orchestrator.survival_first,
            "survival_weight_multiplier": round(survival_orchestrator.weight_multiplier, 3),
            "survival_severity_by_candidate": {state.active_by_card[c]: self._survival_policy_character_advice(state, player, state.active_by_card[c], survival_orchestrator)[3] for c in offered_cards},
            "chosen_card": choice,
            "chosen_character": state.active_by_card[choice],
            "reasons": reasons[choice],
        })
        return choice

    def choose_final_character(self, state: GameState, player: PlayerState, card_choices: list[int]) -> str:
        options = [state.active_by_card[c] for c in card_choices]
        if self._is_random_mode():
            choice = self._choice(options)
            self._set_debug("final_character", player.player_id, {
                "policy": self.character_policy_mode,
                "offered_cards": card_choices,
                "candidate_scores": {name: 0.0 for name in options},
                "chosen_character": choice,
                "reasons": ["uniform_random"],
            })
            return choice
        scored = {}
        reasons = {}
        survival_ctx, survival_orchestrator = self._build_survival_orchestrator(state, player, player.current_character)
        marker_bonus = self._distress_marker_bonus(state, player, options)
        for name in options:
            score, why = (self._character_score_breakdown_v2(state, player, name) if self._is_v2_mode() else self._character_score_breakdown(state, player, name))
            survival_policy_bonus, survival_policy_why, survival_hard_block, survival_detail = self._survival_policy_character_advice(state, player, name, survival_orchestrator)
            if survival_policy_bonus != 0.0:
                score += survival_policy_bonus
                why = [*why, *survival_policy_why]
            bonus = marker_bonus.get(name, 0.0)
            if bonus > 0.0:
                bonus *= max(1.0, survival_orchestrator.weight_multiplier if survival_orchestrator.survival_first and name in LOW_CASH_INCOME_CHARACTERS | LOW_CASH_ESCAPE_CHARACTERS | LOW_CASH_CONTROLLER_CHARACTERS | {"박수", "만신"} else 1.0)
                score += bonus
                why = [*why, f"distress_marker_bonus={bonus:.2f}"]
            survival_bonus, survival_why = self._character_survival_adjustment(state, player, name, survival_ctx)
            if survival_bonus != 0.0:
                score += survival_bonus
                why = [*why, *survival_why]
            scored[name] = score
            reasons[name] = why
        choice = max(options, key=lambda n: (scored[n], n))
        self._set_debug("final_character", player.player_id, {
            "policy": self.character_policy_mode,
            "offered_cards": card_choices,
            "candidate_scores": {name: round(scored[name], 3) for name in options},
            "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
            "survival_urgency": round(survival_ctx["survival_urgency"], 3),
            "survival_first": survival_orchestrator.survival_first,
            "survival_weight_multiplier": round(survival_orchestrator.weight_multiplier, 3),
            "survival_severity_by_candidate": {name: self._survival_policy_character_advice(state, player, name, survival_orchestrator)[3] for name in options},
            "chosen_character": choice,
            "reasons": reasons[choice],
        })
        return choice

    def choose_mark_target(self, state: GameState, player: PlayerState, actor_name: str) -> Optional[str]:
        legal_targets = self._allowed_mark_targets(state, player)
        candidates = self._public_mark_guess_candidates(state, player)
        if not legal_targets or not candidates:
            self._set_debug("mark_target", player.player_id, {
                "policy": self.character_policy_mode,
                "actor_name": actor_name,
                "candidate_scores": {},
                "candidate_probabilities": {},
                "chosen_target": None,
                "reasons": ["no_public_guess_candidates" if legal_targets else "no_legal_targets"],
            })
            return None
        if self._is_random_mode():
            choice = self._choice(candidates)
            self._set_debug("mark_target", player.player_id, {
                "policy": self.character_policy_mode,
                "actor_name": actor_name,
                "candidate_scores": {c: 0.0 for c in candidates},
                "candidate_probabilities": {c: round(1.0 / len(candidates), 3) for c in candidates},
                "chosen_target": choice,
                "reasons": ["uniform_random_public_guess"],
            })
            return choice
        scored = {}
        reasons = {}
        for target_name in candidates:
            score, why = self._public_target_name_score_breakdown(state, player, actor_name, target_name)
            scored[target_name] = score
            reasons[target_name] = why
        probabilities, dist_meta = self._mark_guess_distribution(scored, len(legal_targets))
        ordered = sorted(candidates, key=lambda name: (probabilities[name], scored[name], name), reverse=True)
        top_name = ordered[0]
        top_probability = dist_meta["top_probability"]
        choice = self._weighted_choice(candidates, [probabilities[name] for name in candidates])
        self._set_debug("mark_target", player.player_id, {
            "policy": self.character_policy_mode,
            "actor_name": actor_name,
            "candidate_scores": {name: round(val, 3) for name, val in scored.items()},
            "candidate_probabilities": {name: round(probabilities[name], 3) for name in candidates},
            "chosen_target": choice,
            "top_candidate": top_name,
            "uniform_mix": round(dist_meta["uniform_mix"], 3),
            "ambiguity": round(dist_meta["ambiguity"], 3),
            "top_probability": round(top_probability, 3),
            "second_probability": round(dist_meta["second_probability"], 3),
            "reasons": reasons[choice],
        })
        return choice

    def choose_active_flip_card(self, state: GameState, player: PlayerState, flippable_cards: list[int]) -> Optional[int]:
        if not flippable_cards:
            return None
        if self._is_random_mode():
            choice = self._choice(flippable_cards)
            self._set_debug("marker_flip", player.player_id, {
                "policy": self.character_policy_mode,
                "candidate_scores": {str(c): 0.0 for c in flippable_cards},
                "chosen_card": choice,
                "reasons": ["uniform_random"],
            })
            return choice
        scored = {}
        reasons = {}
        denial_snapshot = self._leader_denial_snapshot(state, player) if self._is_v2_mode() else None
        marker_plan = self._leader_marker_flip_plan(state, player, denial_snapshot.get("top_threat") if denial_snapshot else None) if self._is_v2_mode() else None
        opportunities = marker_plan["opportunities"] if marker_plan else {}
        survival_ctx = self._generic_survival_context(state, player, player.current_character)
        controller_need = float(survival_ctx.get("controller_need", 0.0))
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        own_burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))
        for card_no in flippable_cards:
            current = state.active_by_card[card_no]
            a, b = CARD_TO_NAMES[card_no]
            flipped = b if current == a else a
            if self._is_v2_mode():
                current_score, _ = self._character_score_breakdown_v2(state, player, current)
                flipped_score, flipped_reasons = self._character_score_breakdown_v2(state, player, flipped)
                deny = 0.0
                for op in self._alive_enemies(state, player):
                    tags = self._predicted_opponent_archetypes(state, player, op)
                    if flipped in {"자객", "산적", "객주", "중매꾼", "건설업자"} and ("expansion" in tags or "geo" in tags or "cash_rich" in tags):
                        deny += 0.6
                    if current in {"중매꾼", "건설업자", "객주", "자객"} and ("expansion" in tags or "geo" in tags):
                        deny += 0.6
                if denial_snapshot and denial_snapshot["emergency"] > 0.0:
                    if flipped in {"자객", "산적", "추노꾼", "사기꾼", "박수", "만신", "어사"}:
                        deny += 0.9 + 0.25 * float(denial_snapshot["emergency"])
                    if flipped in {"교리 연구관", "교리 감독관"}:
                        deny += 0.8 + 0.3 * float(denial_snapshot["emergency"])
                    if current in {"중매꾼", "건설업자", "객주", "파발꾼"} and denial_snapshot["near_end"]:
                        deny += 0.7
                card_plan = opportunities.get(card_no, {})
                counter_delta = float(card_plan.get("score", 0.0))
                if counter_delta != 0.0:
                    deny += 1.15 * counter_delta
                    flipped_need = float(card_plan.get("flipped_need", 0.0))
                    current_need = float(card_plan.get("current_need", 0.0))
                    if current_need > flipped_need:
                        flipped_reasons = [f"counter_leader_needed_face={current_need - flipped_need:.2f}", *flipped_reasons]
                    elif flipped_need > current_need:
                        flipped_reasons = [f"avoid_feeding_leader={flipped_need - current_need:.2f}", *flipped_reasons]
                if controller_need > 0.0 or money_distress > 0.0:
                    if current in ACTIVE_MONEY_DRAIN_CHARACTERS and flipped not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                        relief = 0.95 + 0.75 * controller_need + 0.35 * money_distress
                        if current == "만신" and own_burden_cost > 0.0:
                            relief += 0.25 * own_burden_cost
                        deny += relief
                        flipped_reasons = [f"money_relief_flip={relief:.2f}", *flipped_reasons]
                    elif flipped in ACTIVE_MONEY_DRAIN_CHARACTERS and current not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                        deny -= 0.80 + 0.55 * controller_need + 0.25 * money_distress
                        flipped_reasons = ["avoid_enable_money_drain", *flipped_reasons]
                scored[card_no] = (flipped_score - current_score) + deny
                reasons[card_no] = [f"flip_to={flipped}", f"deny={deny:.1f}", *flipped_reasons]
            else:
                current_score, _ = self._character_score_breakdown(state, player, current)
                flipped_score, flipped_reasons = self._character_score_breakdown(state, player, flipped)
                score = flipped_score - current_score
                if (controller_need > 0.0 or money_distress > 0.0) and current in ACTIVE_MONEY_DRAIN_CHARACTERS and flipped not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                    score += 0.90 + 0.70 * controller_need + 0.30 * money_distress
                    flipped_reasons = ["money_relief_flip", *flipped_reasons]
                elif (controller_need > 0.0 or money_distress > 0.0) and flipped in ACTIVE_MONEY_DRAIN_CHARACTERS and current not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                    score -= 0.75 + 0.50 * controller_need + 0.20 * money_distress
                    flipped_reasons = ["avoid_enable_money_drain", *flipped_reasons]
                scored[card_no] = score
                reasons[card_no] = [f"flip_to={flipped}", *flipped_reasons]
        choice = max(flippable_cards, key=lambda c: (scored[c], -c))
        self._set_debug("marker_flip", player.player_id, {
            "policy": self.character_policy_mode,
            "candidate_scores": {str(c): round(scored[c], 3) for c in flippable_cards},
            "chosen_card": choice,
            "chosen_to": (CARD_TO_NAMES[choice][1] if state.active_by_card[choice] == CARD_TO_NAMES[choice][0] else CARD_TO_NAMES[choice][0]),
            "reasons": reasons[choice],
            "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
            "money_distress": round(money_distress, 3),
            "controller_need": round(controller_need, 3),
        })
        return choice

class ArenaPolicy:
    """Routes decisions to per-player HeuristicPolicy instances for mixed-policy arena tests."""

    DEFAULT_LINEUP = [
        "heuristic_v2_aggressive",
        "heuristic_v2_token_opt",
        "heuristic_v2_control",
        "heuristic_v2_balanced",
    ]

    def __init__(self, player_character_policy_modes: Optional[dict[int, str]] = None, player_lap_policy_modes: Optional[dict[int, str]] = None, rng=None):
        super().__init__()
        self.character_policy_mode = "arena"
        self.lap_policy_mode = "arena"
        src_modes = dict(player_character_policy_modes or {})
        if not src_modes:
            src_modes = {i + 1: mode for i, mode in enumerate(self.DEFAULT_LINEUP)}
        self.player_character_policy_modes = {int(pid): mode for pid, mode in src_modes.items()}
        self.player_lap_policy_modes = {int(pid): mode for pid, mode in dict(player_lap_policy_modes or {}).items()}
        for pid, mode in self.player_character_policy_modes.items():
            if mode not in HeuristicPolicy.VALID_CHARACTER_POLICIES or mode == "arena":
                raise ValueError(f"Unsupported arena character policy for player {pid}: {mode}")
        for pid, mode in self.player_lap_policy_modes.items():
            if mode not in HeuristicPolicy.VALID_LAP_POLICIES:
                raise ValueError(f"Unsupported arena lap policy for player {pid}: {mode}")
        self.rng = rng
        self._policies: dict[int, HeuristicPolicy] = {}
        for pid in range(1, 5):
            char_mode = self.player_character_policy_modes.get(pid, self.DEFAULT_LINEUP[(pid - 1) % len(self.DEFAULT_LINEUP)])
            lap_mode = self.player_lap_policy_modes.get(pid, char_mode if char_mode in HeuristicPolicy.VALID_LAP_POLICIES else "heuristic_v1")
            self._policies[pid - 1] = HeuristicPolicy(character_policy_mode=char_mode, lap_policy_mode=lap_mode, rng=rng)

    def set_rng(self, rng) -> None:
        self.rng = rng
        for policy in self._policies.values():
            policy.set_rng(rng)

    def character_mode_for_player(self, player_id: int) -> str:
        return self.player_character_policy_modes.get(player_id + 1, self._policies[player_id].character_policy_mode)

    def lap_mode_for_player(self, player_id: int) -> str:
        if player_id + 1 in self.player_lap_policy_modes:
            return self.player_lap_policy_modes[player_id + 1]
        policy = self._policies[player_id]
        return policy.lap_policy_mode

    def _policy_for_player(self, player: PlayerState) -> HeuristicPolicy:
        return self._policies[player.player_id]

    def pop_debug(self, action: str, player_id: int):
        return self._policies[player_id].pop_debug(action, player_id)

    def choose_movement(self, state: GameState, player: PlayerState):
        return self._policy_for_player(player).choose_movement(state, player)

    def choose_purchase_tile(self, state: GameState, player: PlayerState, pos: int, cell: CellKind, cost: int, *, source: str = "landing") -> bool:
        return self._policy_for_player(player).choose_purchase_tile(state, player, pos, cell, cost, source=source)

    def choose_lap_reward(self, state: GameState, player: PlayerState):
        return self._policy_for_player(player).choose_lap_reward(state, player)

    def choose_coin_placement_tile(self, state: GameState, player: PlayerState):
        return self._policy_for_player(player).choose_coin_placement_tile(state, player)

    def choose_trick_to_use(self, state: GameState, player: PlayerState, hand: list[TrickCard]):
        return self._policy_for_player(player).choose_trick_to_use(state, player, hand)

    def choose_specific_trick_reward(self, state: GameState, player: PlayerState, choices: list[TrickCard]):
        return self._policy_for_player(player).choose_specific_trick_reward(state, player, choices)

    def choose_burden_exchange_on_supply(self, state: GameState, player: PlayerState, card: TrickCard) -> bool:
        return self._policy_for_player(player).choose_burden_exchange_on_supply(state, player, card)

    def choose_hidden_trick_card(self, state: GameState, player: PlayerState, hand: list[TrickCard]):
        return self._policy_for_player(player).choose_hidden_trick_card(state, player, hand)

    def choose_draft_card(self, state: GameState, player: PlayerState, offered_cards: list[int]):
        return self._policy_for_player(player).choose_draft_card(state, player, offered_cards)

    def choose_final_character(self, state: GameState, player: PlayerState, card_choices: list[int]):
        return self._policy_for_player(player).choose_final_character(state, player, card_choices)

    def choose_mark_target(self, state: GameState, player: PlayerState, actor_name: str):
        return self._policy_for_player(player).choose_mark_target(state, player, actor_name)

    def choose_doctrine_relief_target(self, state: GameState, player: PlayerState, candidates: list[PlayerState]):
        return self._policy_for_player(player).choose_doctrine_relief_target(state, player, candidates)

    def choose_geo_bonus(self, state: GameState, player: PlayerState, actor_name: str):
        return self._policy_for_player(player).choose_geo_bonus(state, player, actor_name)

    def choose_active_flip_card(self, state: GameState, player: PlayerState, flippable_cards: list[int]):
        return self._policy_for_player(player).choose_active_flip_card(state, player, flippable_cards)
