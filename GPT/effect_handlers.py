from __future__ import annotations

from typing import Optional

from characters import CARD_TO_NAMES
from config import CellKind
from policy.character_traits import (
    is_ajeon,
    is_builder,
    is_doctrine_character,
    is_gakju,
    is_matchmaker,
    is_swindler,
)
from policy.environment_traits import (
    WEATHER_ALL_TO_RESOURCES_ID,
    WEATHER_BETRAYAL_MARKER_ID,
    WEATHER_BRIGHT_NIGHT_ID,
    WEATHER_CLEAR_WARM_DAY_ID,
    WEATHER_COLD_WINTER_DAY_ID,
    WEATHER_EMERGENCY_EVACUATION_ID,
    WEATHER_FOREIGN_INVASION_ID,
    WEATHER_HARVEST_AUTUMN_ID,
    WEATHER_HOLY_RELIC_DAY_ID,
    WEATHER_LEAD_BY_EXAMPLE_ID,
    WEATHER_LONG_WINTER_ID,
    WEATHER_MASS_UPRISING_ID,
    WEATHER_RAINMAKING_ID,
    WEATHER_RELIEF_SYMBOL_ID,
    WEATHER_STRATEGY_SHIFT_ID,
    WEATHER_TRICKSTER_DAY_ID,
    has_weather_id,
    weather_id_for_name,
)
from state import GameState, PlayerState
from trick_cards import (
    TRICK_FLASH_ID,
    TRICK_FREE_GIFT_ID,
    TRICK_HEALTH_CHECK_ID,
    TRICK_HEAVY_BURDEN_ID,
    TRICK_LIGHT_BURDEN_ID,
    TRICK_PREFERENTIAL_PASS_ID,
    TRICK_RELIC_COLLECTOR_ID,
    TRICK_WILDFIRE_ID,
    trick_card_id_for_name,
)
from viewer.events import Phase


class EngineEffectHandlers:
    """Default game-effect handlers wired into the engine event bus.

    These handlers intentionally keep the old engine behavior, but move
    effect bodies behind event dispatch boundaries to reduce coupling inside
    GameEngine and create extension points for future customization.
    """

    def __init__(self, engine) -> None:
        self.engine = engine

    def register_default_handlers(self, dispatcher) -> None:
        dispatcher.register('weather.round.apply', self.apply_round_weather)
        dispatcher.register('fortune.draw.resolve', self.resolve_fortune_draw)
        dispatcher.register('fortune.cleanup.resolve', self.handle_fortune_cleanup)
        dispatcher.register('fortune.card.apply', self.handle_fortune_card_apply)
        dispatcher.register('fortune.movement.resolve', self.handle_fortune_movement)
        dispatcher.register('game.end.evaluate', self.handle_game_end_evaluate)
        dispatcher.register('landing.f.resolve', self.handle_f_landing)
        dispatcher.register('landing.s.resolve', self.handle_s_landing)
        dispatcher.register('landing.malicious.resolve', self.handle_malicious_landing)
        dispatcher.register('landing.force_sale.resolve', self.handle_force_sale_landing)
        dispatcher.register('landing.unowned.resolve', self.handle_unowned_landing)
        dispatcher.register('landing.own_tile.resolve', self.handle_own_tile_landing)
        dispatcher.register('tile.purchase.attempt', self.handle_purchase_attempt)
        dispatcher.register('rent.payment.resolve', self.handle_rent_payment)
        dispatcher.register('tile.character.effect', self.handle_tile_character_effect)
        dispatcher.register('marker.management.apply', self.handle_marker_management)
        dispatcher.register('marker.flip.resolve', self.handle_marker_flip)
        dispatcher.register('lap.reward.resolve', self.handle_lap_reward)
        dispatcher.register('payment.resolve', self.handle_payment)
        dispatcher.register('bankruptcy.resolve', self.handle_bankruptcy)
        dispatcher.register('trick.card.resolve', self.handle_trick_card)

    def apply_round_weather(self, state: GameState) -> dict:
        engine = self.engine
        card = engine._draw_weather_card(state)
        card_id = weather_id_for_name(card.name)
        engine._weather_history.append(card.name)
        state.current_weather = card
        state.current_weather_effects = {card.name}
        state.weather_discard_pile.append(card)
        event = {'event': 'weather_round', 'round_index': state.rounds_completed + 1, 'weather': card.name, 'effect': card.effect}
        details = []
        if card_id == WEATHER_FOREIGN_INVASION_ID:
            for p in state.players:
                if p.alive:
                    out = engine._pay_or_bankrupt(state, p, 2, None)
                    details.append({'player': p.player_id + 1, **out})
        elif card_id == WEATHER_LEAD_BY_EXAMPLE_ID:
            owner = engine._weather_marker_owner(state)
            if owner is not None:
                details.append({'player': owner.player_id + 1, **engine._pay_or_bankrupt(state, owner, 3, None)})
        elif card_id == WEATHER_RAINMAKING_ID:
            owner = engine._weather_marker_owner(state)
            if owner is not None:
                owner.shards += 1
                engine._strategy_stats[owner.player_id]['shards_gained_lap'] += 1
                engine._change_f(state, -1, reason='weather_effect', source=card.name)
                details.append({'player': owner.player_id + 1, 'shards_delta': 1, 'f_delta': -1})
        elif card_id == WEATHER_RELIEF_SYMBOL_ID:
            owner = engine._weather_marker_owner(state)
            if owner is not None:
                owner.cash += 4
                details.append({'player': owner.player_id + 1, 'cash_delta': 4})
        elif card_id == WEATHER_TRICKSTER_DAY_ID:
            for p in state.players:
                if p.alive:
                    redraw_card = engine._choose_trick_redraw_card(state, p, list(p.trick_hand), card.name)
                    if redraw_card is not None:
                        engine._discard_trick(state, p, redraw_card)
                    details.append(engine._weather_gain_tricks(state, p, 1, redraw=False))
        elif card_id == WEATHER_STRATEGY_SHIFT_ID:
            for p in state.players:
                if p.alive:
                    max_redraws = len(p.trick_hand)
                    for _ in range(max_redraws):
                        redraw_card = engine._choose_trick_redraw_card(state, p, list(p.trick_hand), card.name)
                        if redraw_card is None:
                            break
                        engine._discard_trick(state, p, redraw_card)
                        engine._weather_gain_tricks(state, p, 1, redraw=False)
                    need = max(0, 5 - len(p.trick_hand))
                    details.append(engine._weather_gain_tricks(state, p, need, redraw=False))
        elif card_id == WEATHER_ALL_TO_RESOURCES_ID:
            details.append(
                engine._fortune_burden_cleanup(
                    state,
                    [p for p in state.players if p.alive],
                    multiplier=2,
                    payout=True,
                    name=card.name,
                )
            )
        elif card_id == WEATHER_EMERGENCY_EVACUATION_ID:
            details.append(
                engine._fortune_burden_cleanup(
                    state,
                    [p for p in state.players if p.alive],
                    multiplier=2,
                    payout=False,
                    name=card.name,
                )
            )
        elif card_id == WEATHER_BETRAYAL_MARKER_ID:
            # 룰 정합성 업데이트: 해당 날씨는 현재 버전에서 효과를 적용하지 않는다.
            details.append({'effect': 'disabled_no_op'})
        elif card_id == WEATHER_BRIGHT_NIGHT_ID:
            engine._change_f(state, -3, reason='weather_effect', source=card.name)
            details.append({'f_delta': -3})
        elif card_id == WEATHER_LONG_WINTER_ID:
            engine._change_f(state, -1, reason='weather_effect', source=card.name)
            details.append({'f_delta': -1})
        elif card_id == WEATHER_CLEAR_WARM_DAY_ID:
            ordered = engine._alive_ids_from_marker_direction(state)
            for pid in ordered:
                p = state.players[pid]
                recovered = engine._recover_dice_cards(state, p, 1, card.name)
                if not recovered:
                    details.append({'player': p.player_id + 1, 'recovered': None})
                    continue
                details.append({'player': p.player_id + 1, 'recovered': recovered[0]})
        if details:
            event['details'] = details
        engine._log(event)
        return {'type': 'WEATHER', 'name': card.name, 'effect': card.effect, 'details': details}


    def _ensure_stats(self, state: GameState) -> None:
        engine = self.engine
        if len(engine._strategy_stats) > 0:
            return
        engine._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "tricks_used": 0, "anytime_tricks_used": 0, "regular_tricks_used": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "marked_target_names": [],
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0, "shard_income_cash": 0,
                "character_policy_mode": "",
            }
            for _ in range(state.config.player_count)
        ]

    def handle_f_landing(self, state: GameState, player: PlayerState, pos: int, cell: CellKind) -> dict:
        self._ensure_stats(state)
        engine = self.engine
        scripted = engine.rule_scripts.execute('landing.f.resolve', state, player, pos, cell.name)
        if scripted is not None:
            extra_gain = max(0, int(player.extra_shard_gain_this_turn))
            if (
                extra_gain > 0
                and isinstance(scripted, dict)
                and scripted.get("type") in {"F1", "F2"}
                and isinstance(scripted.get("shards"), int)
            ):
                base_shards = int(scripted.get("shards", 0))
                bonus_shards = base_shards * extra_gain
                if bonus_shards > 0:
                    player.shards += bonus_shards
                    self._ensure_stats(state)
                    self.engine._strategy_stats[player.player_id]["shards_gained_f"] += bonus_shards
                    scripted = dict(scripted)
                    scripted["shards"] = base_shards + bonus_shards
            return scripted
        stats = engine._strategy_stats[player.player_id]
        if cell == CellKind.F1:
            shard_gain = state.config.rules.special_tiles.f1_shards * (1 + max(0, player.extra_shard_gain_this_turn))
            stats['f1_visits'] += 1
            engine._change_f(state, state.config.rules.special_tiles.f1_increment, reason="f_tile_landing", source="F1", actor_pid=player.player_id, extra={"position": pos, "tile_kind": cell.name})
            player.shards += shard_gain
            stats['shards_gained_f'] += shard_gain
            base = {'type': 'F1', 'f_delta': state.config.rules.special_tiles.f1_increment, 'shards': shard_gain}
        else:
            shard_gain = state.config.rules.special_tiles.f2_shards * (1 + max(0, player.extra_shard_gain_this_turn))
            stats['f2_visits'] += 1
            engine._change_f(state, state.config.rules.special_tiles.f2_increment, reason="f_tile_landing", source="F2", actor_pid=player.player_id, extra={"position": pos, "tile_kind": cell.name})
            player.shards += shard_gain
            stats['shards_gained_f'] += shard_gain
            base = {'type': 'F2', 'f_delta': state.config.rules.special_tiles.f2_increment, 'shards': shard_gain}
        return engine._apply_weather_same_tile_bonus(state, player, base)

    def handle_s_landing(self, state: GameState, player: PlayerState, pos: int) -> dict:
        self._ensure_stats(state)
        engine = self.engine
        engine._strategy_stats[player.player_id]['s_visits'] += 1
        return engine._apply_weather_same_tile_bonus(state, player, engine._resolve_fortune_tile(state, player))

    def handle_malicious_landing(self, state: GameState, player: PlayerState, pos: int) -> dict:
        self._ensure_stats(state)
        engine = self.engine
        engine._strategy_stats[player.player_id]['malicious_visits'] += 1
        cost = state.config.rules.special_tiles.malicious_cost_for(state, pos)
        outcome = engine._pay_or_bankrupt(state, player, cost, None)
        base = {
            'type': 'MALICIOUS',
            'face_value': state.config.rules.economy.purchase_cost_for(state, pos),
            'multiplier': state.config.rules.special_tiles.malicious_land_multiplier,
            **outcome,
        }
        return engine._apply_weather_same_tile_bonus(state, player, base)

    def handle_force_sale_landing(self, state: GameState, player: PlayerState, pos: int, cell: CellKind) -> dict:
        engine = self.engine
        return engine._apply_force_sale(state, player, pos)

    def handle_unowned_landing(self, state: GameState, player: PlayerState, pos: int, cell: CellKind) -> dict:
        engine = self.engine
        purchase = None
        disputed = None
        if has_weather_id(state.current_weather_effects, WEATHER_MASS_UPRISING_ID) and cell in (CellKind.T2, CellKind.T3):
            disputed_rent = state.config.rules.economy.rent_cost_for(state, pos)
            disputed = engine._pay_or_bankrupt(state, player, disputed_rent, None)
            if not player.alive:
                return engine._apply_weather_same_tile_bonus(
                    state,
                    player,
                    {'type': 'DISPUTED_BANKRUPTCY', 'tile_kind': cell.name, 'rent': disputed_rent, **disputed},
                )
        purchase = engine._try_purchase_tile(state, player, pos, cell)
        if disputed is not None:
            purchase['weather_disputed_rent'] = {'rent': disputed_rent, **disputed}
        if (
            is_matchmaker(player.current_character)
            and player.alive
            and purchase.get('type') != 'DISPUTED_BANKRUPTCY'
        ):
            extra = engine._matchmaker_buy_adjacent(state, player, pos)
            if extra is not None:
                purchase.setdefault('adjacent_bought', []).append(extra)
        elif player.trick_one_extra_adjacent_buy_this_turn and player.alive:
            extra = engine._buy_one_adjacent_same_block(state, player, pos)
            if extra is not None:
                purchase['trick_adjacent_bought'] = extra
            player.trick_one_extra_adjacent_buy_this_turn = False
        co = [p for p in state.players if p.alive and p.player_id != player.player_id and p.position == pos]
        if co:
            if player.trick_same_tile_cash2_this_turn:
                gain = 2 * len(co)
                player.cash += gain
                purchase['trick_same_tile_cash_gain'] = gain
            if player.trick_same_tile_shard_rake_this_turn:
                total = 0
                details = []
                for op in co:
                    amt = player.shards
                    out = engine._pay_or_bankrupt(state, op, amt, player.player_id) if amt > 0 else {'paid': True, 'amount': 0}
                    total += amt if out.get('paid') else 0
                    details.append({'player': op.player_id + 1, 'amount': amt, 'paid': out.get('paid', True)})
                purchase['trick_same_tile_shard_rake'] = {'total': total, 'details': details}
        return engine._apply_weather_same_tile_bonus(state, player, purchase)

    def handle_own_tile_landing(self, state: GameState, player: PlayerState, pos: int, cell: CellKind) -> dict:
        self._ensure_stats(state)
        engine = self.engine
        stats = engine._strategy_stats[player.player_id]
        stats['own_tile_visits'] += 1
        if player.trick_one_extra_adjacent_buy_this_turn:
            extra = engine._buy_one_adjacent_same_block(state, player, pos)
            player.trick_one_extra_adjacent_buy_this_turn = False
        else:
            extra = None
        if (
            is_matchmaker(player.current_character)
            and player.alive
        ):
            matchmaker_extra = engine._matchmaker_buy_adjacent(state, player, pos)
        else:
            matchmaker_extra = None
        before_hand = player.hand_coins
        gain = state.config.rules.token.coins_from_visiting_own_tile
        if is_gakju(player.current_character):
            gain += 1
        player.hand_coins += gain
        stats['coins_gained_own_tile'] += gain
        player.visited_owned_tile_indices.add(pos)
        placed = engine._place_hand_coins_if_possible(state, player)
        event = {'type': 'OWN_TILE', 'tile_kind': cell.name, 'coin_gain': gain, 'hand_before_gain': before_hand, 'placed': placed}
        if extra is not None:
            event['trick_adjacent_bought'] = extra
        if matchmaker_extra is not None:
            event.setdefault('adjacent_bought', []).append(matchmaker_extra)
        co = [p for p in state.players if p.alive and p.player_id != player.player_id and p.position == pos]
        if co:
            if player.trick_same_tile_cash2_this_turn:
                gain_cash = 2 * len(co)
                player.cash += gain_cash
                event['trick_same_tile_cash_gain'] = gain_cash
            if player.trick_same_tile_shard_rake_this_turn:
                total = 0
                details = []
                for op in co:
                    amt = player.shards
                    out = engine._pay_or_bankrupt(state, op, amt, player.player_id) if amt > 0 else {'paid': True, 'amount': 0}
                    total += amt if out.get('paid') else 0
                    details.append({'player': op.player_id + 1, 'amount': amt, 'paid': out.get('paid', True)})
                event['trick_same_tile_shard_rake'] = {'total': total, 'details': details}
        return engine._apply_weather_same_tile_bonus(state, player, event)

    def handle_marker_management(self, state: GameState, player: PlayerState) -> dict | None:
        engine = self.engine
        previous_owner = state.marker_owner_id
        previous_direction = bool(getattr(state, "marker_draft_clockwise", True))
        if not is_doctrine_character(player.current_character):
            return None
        state.marker_owner_id = player.player_id
        state.marker_draft_clockwise = bool(player.current_character and player.current_character == CARD_TO_NAMES[5][1])
        # Rules: selecting doctrine manager can trigger a flip sequence even when marker owner does not change.
        state.pending_marker_flip_owner_id = state.marker_owner_id
        direction_label = "clockwise" if state.marker_draft_clockwise else "counterclockwise"
        event = {
            "event": "marker_moved",
            "by_player": player.player_id + 1,
            "character": player.current_character,
            "from_owner": previous_owner + 1,
            "to_owner": state.marker_owner_id + 1,
            "marker_changed": previous_owner != state.marker_owner_id,
            "draft_direction": direction_label,
            "direction_changed": previous_direction != state.marker_draft_clockwise,
            "marker_flip_pending_for": None if state.pending_marker_flip_owner_id is None else state.pending_marker_flip_owner_id + 1,
        }
        engine._log(event)
        engine._emit_vis(
            "marker_transferred",
            Phase.MARK,
            player.player_id + 1,
            state,
            from_owner=previous_owner + 1,
            to_owner=state.marker_owner_id + 1,
            from_player_id=previous_owner + 1,
            to_player_id=state.marker_owner_id + 1,
            reason="round_end_doctrine_effect",
            draft_direction=direction_label,
            marker_flip_pending_for=None if state.pending_marker_flip_owner_id is None else state.pending_marker_flip_owner_id + 1,
        )
        return event

    def handle_marker_flip(self, state: GameState) -> dict | None:
        engine = self.engine
        owner_id = state.pending_marker_flip_owner_id
        if owner_id is None:
            return None
        owner = state.players[owner_id]
        if not owner.alive:
            event = {
                "event": "marker_flip_skip",
                "player": owner.player_id + 1,
                "character": owner.current_character,
                "reason": "owner_dead",
                "decision": None,
            }
            engine._log(event)
            state.pending_marker_flip_owner_id = None
            return event
        flippable_cards = list(engine.CARD_TO_NAMES.keys()) if hasattr(engine, 'CARD_TO_NAMES') else []
        if not flippable_cards:
            from characters import CARD_TO_NAMES
            flippable_cards = list(CARD_TO_NAMES.keys())
            card_names = CARD_TO_NAMES
        else:
            card_names = engine.CARD_TO_NAMES
        remaining_cards = list(flippable_cards)
        flipped_events: list[dict] = []
        while remaining_cards:
            chosen_card = engine._request_decision("choose_active_flip_card", state, owner, list(remaining_cards))
            flip_debug = engine.policy.pop_debug("marker_flip", owner.player_id) if hasattr(engine.policy, "pop_debug") else None
            batch_flip_requested = isinstance(chosen_card, (list, tuple, set))
            if chosen_card is None:
                if not flipped_events:
                    engine._record_ai_decision(
                        state,
                        owner,
                        "marker_flip",
                        flip_debug,
                        result={"chosen_card": None, "skipped": True},
                        source_event="marker_flip",
                    )
                    event = {
                        "event": "marker_flip_skip",
                        "player": owner.player_id + 1,
                        "character": owner.current_character,
                        "decision": flip_debug,
                    }
                    engine._log(event)
                    state.pending_marker_flip_owner_id = None
                    return event
                break
            chosen_cards: list[int]
            if batch_flip_requested:
                chosen_cards = []
                seen_cards: set[int] = set()
                for raw_card in chosen_card:
                    try:
                        card_index = int(raw_card)
                    except (TypeError, ValueError):
                        chosen_cards = []
                        break
                    if card_index in seen_cards:
                        continue
                    seen_cards.add(card_index)
                    chosen_cards.append(card_index)
                if not chosen_cards:
                    break
            else:
                chosen_cards = [chosen_card]
            if any(card_index not in remaining_cards for card_index in chosen_cards):
                engine._log(
                    {
                        "event": "marker_flip_invalid_choice",
                        "player": owner.player_id + 1,
                        "chosen_card": list(chosen_cards) if batch_flip_requested else chosen_cards[0],
                        "remaining_cards": list(remaining_cards),
                    }
                )
                break

            for chosen_card_index in chosen_cards:
                a, b = card_names[chosen_card_index]
                current = state.active_by_card[chosen_card_index]
                flipped = b if current == a else a
                state.active_by_card[chosen_card_index] = flipped
                event = {
                    "event": "marker_flip",
                    "player": owner.player_id + 1,
                    "card_no": chosen_card_index,
                    "from_character": current,
                    "to_character": flipped,
                    "decision": flip_debug,
                }
                flipped_events.append(event)
                engine._record_ai_decision(
                    state,
                    owner,
                    "marker_flip",
                    flip_debug,
                    result={
                        "chosen_card": chosen_card_index,
                        "chosen_cards": list(chosen_cards),
                        "from_character": current,
                        "to_character": flipped,
                        "flip_index": len(flipped_events),
                        "finish_after_selection": batch_flip_requested,
                    },
                    source_event="marker_flip",
                )
                engine._log(event)
                engine._emit_vis(
                    "marker_flip",
                    Phase.WEATHER,
                    owner.player_id + 1,
                    state,
                    card_no=chosen_card_index,
                    from_character=current,
                    to_character=flipped,
                    flip_index=len(flipped_events),
                    remaining_flip_candidates=len(remaining_cards) - 1,
                )
                remaining_cards.remove(chosen_card_index)
            if batch_flip_requested:
                break

        state.pending_marker_flip_owner_id = None
        if not flipped_events:
            return None
        return {
            "event": "marker_flip_sequence",
            "player": owner.player_id + 1,
            "flip_count": len(flipped_events),
            "cards": [row["card_no"] for row in flipped_events],
        }

    def handle_lap_reward(self, state: GameState, player: PlayerState) -> dict:
        engine = self.engine
        if player.block_start_reward_this_turn or has_weather_id(state.current_weather_effects, WEATHER_COLD_WINTER_DAY_ID):
            if has_weather_id(state.current_weather_effects, WEATHER_COLD_WINTER_DAY_ID):
                outcome = engine._pay_or_bankrupt(state, player, 2, None)
                return {"choice": "blocked_by_weather", "cash_penalty": 2, **outcome}
            return {"choice": "blocked"}
        decision = engine._request_decision("choose_lap_reward", state, player)
        lap_debug = engine.policy.pop_debug("lap_reward", player.player_id) if hasattr(engine.policy, "pop_debug") else None
        stats = engine._strategy_stats[player.player_id]
        rules = state.config.rules.lap_reward
        shard_bonus = 0
        if has_weather_id(state.current_weather_effects, WEATHER_HARVEST_AUTUMN_ID):
            shard_bonus += 1
        if has_weather_id(state.current_weather_effects, WEATHER_HOLY_RELIC_DAY_ID):
            shard_bonus += 1

        cash_units = max(0, int(getattr(decision, "cash_units", 0)))
        shard_units = max(0, int(getattr(decision, "shard_units", 0)))
        coin_units = max(0, int(getattr(decision, "coin_units", 0)))
        if cash_units == shard_units == coin_units == 0:
            if decision.choice == "cash":
                cash_units = min(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool), rules.cash)
            elif decision.choice == "shards":
                shard_units = min(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool), rules.shards)
            elif decision.choice == "coins":
                coin_units = min(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool), rules.coins)
        requested_points = (
            cash_units * max(1, int(rules.cash_point_cost))
            + shard_units * max(1, int(rules.shards_point_cost))
            + coin_units * max(1, int(rules.coins_point_cost))
        )
        if requested_points > int(rules.points_budget):
            unit_map = {"cash": cash_units, "shards": shard_units, "coins": coin_units}
            preferred = decision.choice if decision.choice in {"cash", "shards", "coins"} else None
            trim_order = [k for k in ("cash", "shards", "coins") if k != preferred]
            if preferred is not None:
                trim_order.append(preferred)
            guard = 0
            while requested_points > int(rules.points_budget) and guard < 64:
                guard += 1
                trimmed = False
                for key in trim_order:
                    if unit_map[key] <= 0:
                        continue
                    unit_map[key] -= 1
                    trimmed = True
                    break
                if not trimmed:
                    break
                requested_points = (
                    unit_map["cash"] * max(1, int(rules.cash_point_cost))
                    + unit_map["shards"] * max(1, int(rules.shards_point_cost))
                    + unit_map["coins"] * max(1, int(rules.coins_point_cost))
                )
            cash_units = unit_map["cash"]
            shard_units = unit_map["shards"]
            coin_units = unit_map["coins"]

        granted_cash = cash_units if cash_units <= state.lap_reward_cash_pool_remaining else 0
        granted_shards = shard_units if shard_units <= state.lap_reward_shards_pool_remaining else 0
        granted_coins = coin_units if coin_units <= state.lap_reward_coins_pool_remaining else 0
        granted_points = (
            granted_cash * max(1, int(rules.cash_point_cost))
            + granted_shards * max(1, int(rules.shards_point_cost))
            + granted_coins * max(1, int(rules.coins_point_cost))
        )

        state.lap_reward_cash_pool_remaining -= granted_cash
        state.lap_reward_shards_pool_remaining -= granted_shards
        state.lap_reward_coins_pool_remaining -= granted_coins

        total_shards = granted_shards
        bonus_shards = min(shard_bonus, state.lap_reward_shards_pool_remaining) if granted_shards > 0 else 0
        if bonus_shards > 0:
            state.lap_reward_shards_pool_remaining -= bonus_shards
            total_shards += bonus_shards

        player.cash += granted_cash
        player.shards += total_shards
        player.hand_coins += granted_coins
        stats["lap_cash_choices"] += 1 if granted_cash > 0 else 0
        stats["lap_shard_choices"] += 1 if granted_shards > 0 else 0
        stats["lap_coin_choices"] += 1 if granted_coins > 0 else 0
        stats["shards_gained_lap"] += total_shards
        choice = decision.choice if decision.choice != "blocked" else "blocked"
        result = {
            "choice": choice,
            "cash_delta": granted_cash,
            "shards_delta": total_shards,
            "coins_delta": granted_coins,
            "weather_bonus_shards": bonus_shards,
            "requested_points": requested_points,
            "granted_points": granted_points,
            "remaining_pool": {
                "cash": state.lap_reward_cash_pool_remaining,
                "shards": state.lap_reward_shards_pool_remaining,
                "coins": state.lap_reward_coins_pool_remaining,
            },
            "requested": {"cash": cash_units, "shards": shard_units, "coins": coin_units},
        }
        engine._record_ai_decision(
            state,
            player,
            "lap_reward",
            lap_debug,
            result=result,
            source_event="lap_reward",
        )
        engine._emit_vis(
            "lap_reward_chosen",
            Phase.LAP_REWARD,
            player.player_id + 1,
            state,
            choice=choice,
            amount={"cash": granted_cash, "shards": total_shards, "coins": granted_coins},
            resource_delta=result,
        )
        return result

    def handle_payment(self, state: GameState, player: PlayerState, cost: int, receiver: int | None) -> dict:
        engine = self.engine
        if cost <= 0:
            return {"cost": cost, "receiver": None if receiver is None else receiver + 1, "paid": True, "bankrupt": False}
        if player.cash < cost:
            engine.events.emit_first_non_none('bankruptcy.resolve', state, player)
            return {"cost": cost, "receiver": None if receiver is None else receiver + 1, "paid": False, "bankrupt": True}
        player.cash -= cost
        if receiver is not None and state.players[receiver].alive:
            state.players[receiver].cash += cost
        return {"cost": cost, "receiver": None if receiver is None else receiver + 1, "paid": True, "bankrupt": False}

    def handle_bankruptcy(self, state: GameState, player: PlayerState) -> dict | None:
        engine = self.engine
        if not player.alive:
            return None
        payment = dict(engine._last_payment_attempt_by_player.get(player.player_id) or {})
        engine._strategy_stats[player.player_id]["bankruptcies"] += 1
        player.alive = False
        state.bankrupt_players += 1
        event = {
            "player_id": player.player_id + 1,
            "character": player.current_character,
            "position": player.position,
            "turn_index": state.turn_index,
            "round_index": state.rounds_completed + 1,
            "cash_before_death": payment.get("cash_before", player.cash),
            "required_cost": payment.get("required_cost"),
            "cash_after_death": player.cash,
            "cash_shortfall": None if payment.get("required_cost") is None else max(0, payment.get("required_cost", 0) - payment.get("cash_before", player.cash)),
            "receiver_player_id": payment.get("receiver_player_id"),
            "cause_hint": payment.get("caller_function") or "unknown",
            "last_semantic_event": payment.get("last_semantic_event"),
            "active_player_id": payment.get("active_player_id"),
            "is_offturn_death": bool(payment.get("is_offturn_payment", False)),
            "tile_kind": payment.get("tile_kind"),
        }
        for idx, owner in enumerate(state.tile_owner):
            if owner == player.player_id:
                state.tile_owner[idx] = None
                state.board[idx] = CellKind.MALICIOUS
                state.malicious_tiles += 1
                if state.tile_coins[idx] > 0:
                    player.score_coins_placed -= state.tile_coins[idx]
                    state.tile_coins[idx] = 0
        player.tiles_owned = 0
        engine._bankruptcy_events.append(dict(event))
        engine._player_bankruptcy_info[player.player_id] = dict(event)
        return {"event": "bankruptcy", "player": player.player_id + 1, "forensic": event}


    def handle_fortune_cleanup(self, state: GameState, targets: list[PlayerState], multiplier: int, payout: bool, name: str) -> dict:
        engine = self.engine
        scripted = engine.rule_scripts.execute('fortune.cleanup.resolve', state, targets, multiplier, payout, name)
        if scripted is not None:
            return scripted
        return engine._default_fortune_burden_cleanup(state, targets, multiplier, payout, name)

    def handle_trick_card(self, state: GameState, player: PlayerState, card) -> dict:
        engine = self.engine
        name = card.name
        card_id = trick_card_id_for_name(name)
        if card_id == TRICK_RELIC_COLLECTOR_ID:
            player.extra_shard_gain_this_turn += 1
            return {"type": "TURN_BUFF", "extra_shards": 1}
        if card_id == TRICK_HEALTH_CHECK_ID:
            state.global_rent_half_this_turn = True
            engine._log({"event": "trick_global_rent_halved", "player": player.player_id + 1})
            return {"type": "GLOBAL_RENT_HALF_THIS_TURN"}
        if card_id == TRICK_PREFERENTIAL_PASS_ID:
            player.trick_all_rent_waiver_this_turn = True
            return {"type": "RENT_WAIVER_ALL_TURN"}
        if name == "뇌고왕":
            player.trick_personal_rent_half_this_turn = True
            return {"type": "PERSONAL_RENT_HALF_THIS_TURN"}
        if name == "뇌절왕":
            player.trick_zone_chain_this_turn = True
            return {"type": "ZONE_CHAIN_THIS_TURN"}
        if card_id == TRICK_FREE_GIFT_ID:
            player.trick_free_purchase_this_turn = True
            return {"type": "FREE_PURCHASE_ONCE"}
        if name == "신의뜻":
            player.trick_same_tile_shard_rake_this_turn = True
            return {"type": "SAME_TILE_SHARD_RAKE"}
        if name == "가벼운 분리불안":
            player.trick_same_tile_cash2_this_turn = True
            return {"type": "SAME_TILE_CASH2"}
        if name == "마당발":
            player.trick_one_extra_adjacent_buy_this_turn = True
            return {"type": "ONE_EXTRA_ADJACENT_BUY"}
        if name == "극심한 분리불안":
            target_pos = engine._find_extreme_player_position(state, player, nearest=False)
            if target_pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_player"}
            arrival = engine._apply_fortune_arrival(state, player, target_pos, "trick_extreme_separation", name)
            return {"type": "ARRIVAL_THEN_MOVE", "arrival": arrival}
        if name == "도움 닫기":
            player.trick_encounter_boost_this_turn = True
            return {"type": "ENCOUNTER_BOOST_THIS_TURN"}
        if card_id == TRICK_FLASH_ID:
            return engine._apply_flash_trade(state, player)
        if name == "재뿌리기":
            candidates = [i for i, owner in enumerate(state.tile_owner) if owner is not None and owner != player.player_id]
            if not candidates:
                return {"type": "NO_EFFECT", "reason": "no_target_tile"}
            pos = engine._request_decision(
                "choose_trick_tile_target",
                state,
                player,
                name,
                list(candidates),
                "other_owned_highest",
                fallback=lambda: engine._select_other_player_tile(state, player, highest=True),
            )
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_target_tile"}
            state.tile_rent_modifiers_this_turn[pos] = 0
            return {"type": "TILE_RENT_ZERO", "pos": pos}
        if name == "긴장감 조성":
            candidates = [i for i, owner in enumerate(state.tile_owner) if owner == player.player_id]
            if not candidates:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            pos = engine._request_decision(
                "choose_trick_tile_target",
                state,
                player,
                name,
                list(candidates),
                "owned_highest",
                fallback=lambda: engine._select_owned_tile(state, player.player_id, highest=True),
            )
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            state.tile_rent_modifiers_this_turn[pos] = max(2, state.tile_rent_modifiers_this_turn.get(pos, 1) * 2)
            return {"type": "TILE_RENT_DOUBLE", "pos": pos}
        if name == "느슨함 혐오자":
            state.global_rent_double_this_turn = True
            engine._log({"event": "trick_global_rent_double", "player": player.player_id + 1})
            return {"type": "GLOBAL_RENT_DOUBLE_THIS_TURN"}
        if name == "극도의 느슨함 혐오자":
            state.global_rent_double_permanent = True
            engine._log({"event": "trick_global_rent_double_permanent", "player": player.player_id + 1})
            return {"type": "GLOBAL_RENT_DOUBLE_PERMANENT"}
        if name == "과속":
            if player.cash < 2:
                return {"type": "FAIL", "reason": "insufficient_cash"}
            player.cash -= 2
            player.trick_dice_delta_this_turn += 1
            return {"type": "BUY_EXTRA_DIE", "cash_delta": -2, "dice_delta": 1}
        if name == "저속":
            player.cash += 2
            player.trick_dice_delta_this_turn -= 1
            return {"type": "SELL_DIE", "cash_delta": 2, "dice_delta": -1}
        if name == "이럇!":
            for op in state.players:
                if op.alive:
                    op.trick_dice_delta_this_turn += 1
            return {"type": "ALL_EXTRA_DIE", "count": len([p for p in state.players if p.alive])}
        if name == "아주 큰 화목 난로":
            player.shards += 1
            engine._change_f(state, 1, reason="trick_effect", source="아주 큰 화목 난로", actor_pid=player.player_id)
            return {"type": "SHARD_AND_F", "shards": 1, "f_delta": 1}
        if card_id == TRICK_WILDFIRE_ID:
            player.shards += 2
            engine._change_f(state, 2, reason="trick_effect", source="거대한 산불", actor_pid=player.player_id)
            return {"type": "SHARD_AND_F", "shards": 2, "f_delta": 2}
        if name == "무역의 선물":
            own = engine._select_owned_tile(state, player.player_id, highest=False)
            other = engine._select_other_player_tile(state, player, highest=True)
            if own is None or other is None:
                return {"type": "NO_EFFECT", "reason": "missing_trade_target"}
            other_owner = state.tile_owner[other]
            t1 = engine._transfer_tile(state, own, other_owner)
            t2 = engine._transfer_tile(state, other, player.player_id)
            return {"type": "TILE_SWAP", "own_to_other": t1, "other_to_self": t2}
        if name == "강제 매각":
            player.trick_force_sale_landing_this_turn = True
            return {"type": "FORCE_SALE_THIS_TURN"}
        if name == "뭘리권":
            player.trick_reroll_budget_this_turn = max(player.trick_reroll_budget_this_turn, 1)
            player.trick_reroll_label_this_turn = name
            return {"type": "REROLL_ARMED", "name": name, "reroll_budget": 1}
        if name == "뭔칙휜":
            player.trick_reroll_budget_this_turn = max(player.trick_reroll_budget_this_turn, 2)
            player.trick_reroll_label_this_turn = name
            return {"type": "REROLL_ARMED", "name": name, "reroll_budget": 2}
        if name == "호객꾼":
            player.trick_obstacle_this_round = True
            return {"type": "OBSTACLE_THIS_ROUND"}
        if card_id in {TRICK_HEAVY_BURDEN_ID, TRICK_LIGHT_BURDEN_ID}:
            if player.cash < card.burden_cost:
                return {"type": "FAIL", "reason": "insufficient_cash", "cost": card.burden_cost}
            player.cash -= card.burden_cost
            return {"type": "DISCARD_BURDEN", "cost": card.burden_cost}
        return {"type": "NOT_YET_IMPLEMENTED", "name": name}

    def resolve_fortune_draw(self, state: GameState, player: PlayerState) -> dict:
        engine = self.engine
        card = engine._draw_fortune_card(state)
        engine._emit_vis(
            "fortune_drawn",
            Phase.FORTUNE,
            player.player_id + 1,
            state,
            card_name=card.name,
            deck_index=card.deck_index,
        )
        event = engine._apply_fortune_card(state, player, card)
        engine._emit_vis(
            "fortune_resolved",
            Phase.FORTUNE,
            player.player_id + 1,
            state,
            card_name=card.name,
            resolution=event,
        )
        state.fortune_discard_pile.append(card)
        return {'type': 'FORTUNE', 'card': {'deck_index': card.deck_index, 'name': card.name, 'effect': card.effect}, 'resolution': event}

    def handle_fortune_card_apply(self, state: GameState, player: PlayerState, card) -> dict:
        engine = self.engine
        return engine._apply_fortune_card_impl(state, player, card)

    def handle_fortune_movement(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str, movement_type: str) -> dict:
        engine = self.engine
        if movement_type == 'arrival':
            return engine._apply_fortune_arrival_impl(state, player, target_pos, trigger, card_name)
        return engine._apply_fortune_move_only_impl(state, player, target_pos, trigger, card_name)

    def handle_game_end_evaluate(self, state: GameState) -> bool:
        engine = self.engine
        scripted = engine.rule_scripts.execute('game.end.evaluate', state)
        if scripted is None:
            end_reason = engine._evaluate_end_rules(state)
            if end_reason is None:
                return False
            state.end_reason = end_reason
        elif not state.end_reason:
            return False
        state.winner_ids = engine._determine_winners(state)
        engine._log({"event": "game_end", "end_reason": state.end_reason, "winner_ids": [pid + 1 for pid in state.winner_ids]})
        return True

    def handle_purchase_attempt(self, state: GameState, player: PlayerState, pos: int, cell: CellKind) -> dict:
        engine = self.engine
        self._ensure_stats(state)
        stats = engine._strategy_stats[player.player_id]
        if state.tile_purchase_blocked_turn_index.get(pos) == state.turn_index:
            return {'type': 'PURCHASE_BLOCKED_THIS_TURN', 'tile_kind': cell.name}
        builder_free_purchase = is_builder(player.current_character)
        cost = 0 if (player.free_purchase_this_turn or player.trick_free_purchase_this_turn or builder_free_purchase) else state.config.rules.economy.purchase_cost_for(state, pos)
        player.free_purchase_this_turn = False
        player.trick_free_purchase_this_turn = False
        shard_cost = 0
        if player.cash < cost:
            return {'type': 'PURCHASE_FAIL', 'tile_kind': cell.name, 'cost': cost, 'shard_cost': shard_cost, 'bankrupt': False, 'skipped': True}
        wants_purchase = engine._request_decision(
            "choose_purchase_tile",
            state,
            player,
            pos,
            cell,
            cost,
            source="landing_purchase",
            fallback=lambda: True,
        )
        purchase_debug = engine.policy.pop_debug("purchase_decision", player.player_id) if hasattr(engine.policy, "pop_debug") else None
        if not wants_purchase:
            engine._record_ai_decision(
                state,
                player,
                "purchase_decision",
                purchase_debug,
                result={"tile_index": pos, "purchased": False, "reason": "policy_skip", "cost": cost},
                source_event="landing_purchase",
            )
            return {'type': 'PURCHASE_SKIP_POLICY', 'tile_kind': cell.name, 'cost': cost, 'shard_cost': shard_cost, 'bankrupt': False, 'skipped': True}
        stats['purchases'] += 1
        if cell == CellKind.T2:
            stats['purchase_t2'] += 1
        elif cell == CellKind.T3:
            stats['purchase_t3'] += 1
        shards_before = player.shards
        player.cash -= cost
        if shard_cost > 0:
            player.shards -= shard_cost
        state.tile_owner[pos] = player.player_id
        player.tiles_owned += 1
        player.first_purchase_turn_by_tile[pos] = player.turns_taken
        placed = None
        if state.config.rules.token.can_place_on_first_purchase:
            player.visited_owned_tile_indices.add(pos)
            placed = engine._place_hand_coins_on_tile(state, player, pos, max_place=state.config.rules.token.place_limit_on_purchase(state, player, pos), source="purchase")
        result = {'type': 'PURCHASE', 'tile_kind': cell.name, 'cost': cost, 'shard_cost': shard_cost, 'shards_before': shards_before, 'shards_after': player.shards, 'placed': placed}
        engine._record_ai_decision(
            state,
            player,
            "purchase_decision",
            purchase_debug,
            result={"tile_index": pos, "purchased": True, "cost": cost, "placed": placed},
            source_event="landing_purchase",
        )
        engine._emit_vis(
            "tile_purchased",
            Phase.ECONOMY,
            player.player_id + 1,
            state,
            player_id=player.player_id + 1,
            tile_index=pos,
            cost=cost,
            purchase_source="landing_purchase",
            result=result,
        )
        return result

    def handle_rent_payment(self, state: GameState, player: PlayerState, pos: int, owner: int) -> dict:
        engine = self.engine
        self._ensure_stats(state)
        stats = engine._strategy_stats[player.player_id]
        rent = engine._effective_rent(state, pos, player, owner)
        if player.trick_all_rent_waiver_this_turn:
            rent = 0
        elif player.rent_waiver_count_this_turn > 0:
            player.rent_waiver_count_this_turn -= 1
            rent = 0
        stats['rent_paid'] += 1
        outcome = engine._pay_or_bankrupt(state, player, rent, owner)
        event = {'type': 'RENT', 'tile_kind': state.board[pos].name, 'owner': owner + 1, 'rent': rent, **outcome}
        if player.trick_one_extra_adjacent_buy_this_turn and player.alive and outcome.get('paid'):
            extra = engine._buy_one_adjacent_same_block(state, player, pos)
            if extra is not None:
                event['trick_adjacent_bought'] = extra
            player.trick_one_extra_adjacent_buy_this_turn = False
        if (
            is_matchmaker(player.current_character)
            and player.alive
            and outcome.get('paid')
        ):
            extra = engine._matchmaker_buy_adjacent(state, player, pos)
            if extra is not None:
                event.setdefault('adjacent_bought', []).append(extra)
        co = [p for p in state.players if p.alive and p.player_id != player.player_id and p.position == pos]
        if co:
            if player.trick_same_tile_cash2_this_turn:
                gain_cash = 2 * len(co)
                player.cash += gain_cash
                event['trick_same_tile_cash_gain'] = gain_cash
            if player.trick_same_tile_shard_rake_this_turn:
                total = 0
                details = []
                for op in co:
                    amt = player.shards
                    out = engine._pay_or_bankrupt(state, op, amt, player.player_id) if amt > 0 else {'paid': True, 'amount': 0}
                    total += amt if out.get('paid') else 0
                    details.append({'player': op.player_id + 1, 'amount': amt, 'paid': out.get('paid', True)})
                event['trick_same_tile_shard_rake'] = {'total': total, 'details': details}
        result = engine._apply_weather_same_tile_bonus(state, player, event)
        engine._emit_vis(
            "rent_paid",
            Phase.ECONOMY,
            player.player_id + 1,
            state,
            payer_player_id=player.player_id + 1,
            owner_player_id=owner + 1,
            tile_index=pos,
            base_amount=rent,
            final_amount=rent if outcome.get('paid') else 0,
            modifiers=result,
        )
        return result

    def handle_tile_character_effect(self, state: GameState, player: PlayerState, pos: int, owner: Optional[int]) -> Optional[dict]:
        engine = self.engine
        cell = state.board[pos]
        if owner is not None and is_ajeon(player.current_character) and owner != player.player_id:
            others = [p for p in state.players if p.alive and p.player_id != player.player_id and p.position == pos]
            if others:
                total = 0
                for op in others:
                    engine._pay_or_bankrupt(state, op, player.shards, player.player_id)
                    total += player.shards
                engine._strategy_stats[player.player_id]['shard_income_cash'] += total
                return engine._apply_weather_same_tile_bonus(state, player, {'type': 'AJEON_LAND', 'others': [p.player_id + 1 for p in others], 'collected_per_player': player.shards, 'total': total})
        if owner is not None and is_swindler(player.current_character) and not engine._is_muroe_skill_blocked(state, player):
            base_rent = engine._effective_rent(state, pos, player, owner)
            swindle_multiplier = 2 if player.shards >= 8 else 3
            rent = base_rent * swindle_multiplier
            if rent > 0 and hasattr(engine.policy, "should_attempt_swindle") and not engine.policy.should_attempt_swindle(state, player, pos, owner, float(rent)):
                engine._log({
                    "event": "policy_action",
                    "event_kind": "policy_action",
                    "type": "SWINDLE_SKIP_POLICY",
                    "reason": "survival_gate",
                    "player": player.player_id + 1,
                    "target_owner": owner + 1,
                    "required_cost": float(rent),
                    "position": pos,
                    "tile_kind": cell.name,
                    "turn_index": state.turn_index,
                    "round_index": state.rounds_completed,
                })
                return None
            outcome = engine._pay_or_bankrupt(state, player, rent, owner)
            if outcome['paid']:
                if engine._takeover_blocked(state, pos, player.player_id):
                    return engine._apply_weather_same_tile_bonus(state, player, {'type': 'SWINDLE_BLOCKED', 'tile_kind': cell.name, 'from': owner + 1, 'reason': 'monopoly_protected', 'swindle_multiplier': swindle_multiplier, **outcome})
                prev_owner = owner
                state.tile_owner[pos] = player.player_id
                state.players[prev_owner].tiles_owned -= 1
                player.tiles_owned += 1
                transferred = state.tile_coins[pos]
                state.players[prev_owner].score_coins_placed -= transferred
                player.score_coins_placed += transferred
                return engine._apply_weather_same_tile_bonus(state, player, {'type': 'SWINDLE_TAKEOVER', 'tile_kind': cell.name, 'from': prev_owner + 1, 'swindle_multiplier': swindle_multiplier, **outcome, 'coins_taken': transferred})
            return engine._apply_weather_same_tile_bonus(state, player, {'type': 'SWINDLE_FAIL', 'tile_kind': cell.name, 'swindle_multiplier': swindle_multiplier, **outcome})
        return None
