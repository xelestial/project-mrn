from __future__ import annotations

import random
import unittest
from unittest.mock import patch

from ai_policy import LapRewardDecision, MovementDecision
from config import DEFAULT_CONFIG, CellKind
from engine import DecisionRequest, GameEngine
from state import GameState
from test_event_effects import DummyPolicy
from trick_cards import TrickCard


def _strategy_stats(player_count: int) -> list[dict]:
    return [
        {
            "purchases": 0,
            "purchase_t2": 0,
            "purchase_t3": 0,
            "rent_paid": 0,
            "own_tile_visits": 0,
            "f1_visits": 0,
            "f2_visits": 0,
            "s_visits": 0,
            "s_cash_plus1": 0,
            "s_cash_plus2": 0,
            "s_cash_minus1": 0,
            "malicious_visits": 0,
            "bankruptcies": 0,
            "cards_used": 0,
            "card_turns": 0,
            "single_card_turns": 0,
            "pair_card_turns": 0,
            "tricks_used": 0,
            "anytime_tricks_used": 0,
            "regular_tricks_used": 0,
            "lap_cash_choices": 0,
            "lap_coin_choices": 0,
            "lap_shard_choices": 0,
            "coins_gained_own_tile": 0,
            "coins_placed": 0,
            "mark_attempts": 0,
            "mark_successes": 0,
            "mark_fail_no_target": 0,
            "mark_fail_missing": 0,
            "mark_fail_blocked": 0,
            "character": "",
            "shards_gained_f": 0,
            "shards_gained_lap": 0,
            "shard_income_cash": 0,
            "draft_cards": [],
            "marked_target_names": [],
        }
        for _ in range(player_count)
    ]


class RecordingDecisionPort:
    def __init__(self) -> None:
        self.requests: list[DecisionRequest] = []

    def request(self, request: DecisionRequest):
        self.requests.append(request)
        if request.decision_name == "choose_draft_card":
            return request.args[0][0]
        if request.decision_name == "choose_final_character":
            return request.state.active_by_card[request.args[0][0]]
        if request.decision_name == "choose_movement":
            return MovementDecision(False, ())
        if request.decision_name == "choose_trick_to_use":
            return request.args[0][0] if request.args and request.args[0] else None
        if request.decision_name == "choose_purchase_tile":
            return False
        if request.decision_name == "choose_mark_target":
            return "선비"
        if request.decision_name == "choose_lap_reward":
            return LapRewardDecision("cash")
        if request.decision_name == "choose_active_flip_card":
            return None
        if request.decision_name == "choose_runaway_slave_step":
            return False
        raise AssertionError(f"unexpected decision request: {request.decision_name}")


class DecisionPortContractTests(unittest.TestCase):
    def test_run_draft_routes_draft_and_final_character_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=True, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        state.players[3].alive = False
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)

        engine._run_draft(state)

        decision_names = [request.decision_name for request in port.requests]
        self.assertIn("choose_draft_card", decision_names)
        self.assertIn("choose_final_character", decision_names)

    def test_take_turn_routes_movement_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)

        with patch.object(engine, "_resolve_pending_marks", return_value=None), patch.object(
            engine, "_apply_character_start", return_value=None
        ), patch.object(engine, "_use_trick_phase", return_value=None), patch.object(
            engine,
            "_resolve_move",
            return_value=(0, {"dice": [], "used_cards": [], "formula": "", "mode": "dice"}),
        ), patch.object(engine, "_advance_player", return_value=None), patch.object(
            engine, "_leader_disruption_snapshot", return_value={"leader_id": None}
        ), patch.object(engine, "_maybe_award_control_finisher_window", return_value=False):
            engine._take_turn(state, player)

        self.assertIn("choose_movement", [request.decision_name for request in port.requests])

    def test_use_trick_phase_routes_trick_decision_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.trick_hand = [TrickCard(deck_index=999, name="테스트 잔꾀", description="test")]
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)

        with patch.object(engine, "_apply_trick_card", return_value={"type": "TEST"}), patch.object(
            engine, "_discard_trick", return_value=None
        ):
            engine._use_trick_phase(state, player)

        self.assertIn("choose_trick_to_use", [request.decision_name for request in port.requests])

    def test_try_purchase_tile_routes_purchase_decision_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)
        land_pos = next(i for i, cell in enumerate(state.board) if cell.name in {"T2", "T3"})
        cell = state.board[land_pos]

        result = engine._try_purchase_tile(state, player, land_pos, cell)

        self.assertEqual(result["type"], "PURCHASE_SKIP_POLICY")
        purchase_request = next(request for request in port.requests if request.decision_name == "choose_purchase_tile")
        self.assertEqual(purchase_request.kwargs["source"], "landing_purchase")
        self.assertEqual(purchase_request.args[0], land_pos)

    def test_apply_character_start_routes_mark_target_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "아전"
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)

        with patch.object(engine, "_character_card_no", return_value=2), patch.object(
            engine, "_is_character_front_face", return_value=True
        ), patch.object(engine, "_coerce_mark_target_character", return_value=("선비", False)), patch.object(
            engine, "_queue_mark", return_value=None
        ), patch.object(engine, "_find_player_by_character", return_value=None):
            engine._apply_character_start(state, player)

        self.assertIn("choose_mark_target", [request.decision_name for request in port.requests])

    def test_apply_lap_reward_routes_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)

        result = engine._apply_lap_reward(state, player)

        self.assertEqual(result["choice"], "cash")
        self.assertIn("choose_lap_reward", [request.decision_name for request in port.requests])

    def test_handle_marker_flip_routes_active_flip_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        state.pending_marker_flip_owner_id = 0
        owner = state.players[0]
        owner.current_character = "아전"
        engine._strategy_stats = _strategy_stats(DEFAULT_CONFIG.player_count)

        result = engine.effect_handlers.handle_marker_flip(state)

        self.assertEqual(result["event"], "marker_flip_skip")
        self.assertIn("choose_active_flip_card", [request.decision_name for request in port.requests])

    def test_resolve_move_routes_runaway_step_choice_through_decision_port(self) -> None:
        port = RecordingDecisionPort()
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), rng=random.Random(0), enable_logging=False, decision_port=port)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.current_character = "탈출 노비"
        target_pos = next(i for i, cell in enumerate(state.board) if cell in {CellKind.F1, CellKind.F2, CellKind.S})
        player.position = (target_pos - 3) % len(state.board)

        move, meta = engine._resolve_move(state, player, MovementDecision(True, (1, 1)))

        self.assertEqual(move, 2)
        self.assertEqual(meta["runaway_choice"], "stay")
        self.assertIn("choose_runaway_slave_step", [request.decision_name for request in port.requests])


if __name__ == "__main__":
    unittest.main()
