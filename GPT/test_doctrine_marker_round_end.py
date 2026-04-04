import random

from ai_policy import BasePolicy, LapRewardDecision, MovementDecision
from config import DEFAULT_CONFIG
from engine import GameEngine
from state import GameState


class _StubPolicy(BasePolicy):
    def choose_movement(self, state, player):
        return MovementDecision(False, ())

    def choose_lap_reward(self, state, player):
        return LapRewardDecision("cash")

    def choose_coin_placement_tile(self, state, player):
        return None

    def choose_draft_card(self, state, player, offered_cards):
        return offered_cards[0]

    def choose_final_character(self, state, player, card_choices):
        return ""

    def choose_mark_target(self, state, player, actor_name):
        return None


def _make_engine_and_state():
    engine = GameEngine(DEFAULT_CONFIG, _StubPolicy(), rng=random.Random(0), enable_logging=True)
    state = GameState.create(DEFAULT_CONFIG)
    return engine, state


def test_round_end_marker_moves_to_doctrine_supervisor():
    engine, state = _make_engine_and_state()
    state.marker_owner_id = 0
    state.marker_draft_clockwise = False
    state.pending_marker_flip_owner_id = None
    state.current_round_order = [3, 2, 1, 0]
    state.players[2].current_character = "교리 감독관"

    engine._apply_round_end_marker_management(state)

    assert state.marker_owner_id == 2
    assert state.marker_draft_clockwise is True
    assert state.pending_marker_flip_owner_id == 2


def test_round_end_marker_moves_to_doctrine_researcher():
    engine, state = _make_engine_and_state()
    state.marker_owner_id = 3
    state.marker_draft_clockwise = True
    state.pending_marker_flip_owner_id = None
    state.current_round_order = [0, 1, 2, 3]
    state.players[1].current_character = "교리 연구관"

    engine._apply_round_end_marker_management(state)

    assert state.marker_owner_id == 1
    assert state.marker_draft_clockwise is False
    assert state.pending_marker_flip_owner_id == 1


def test_round_end_marker_no_doctrine_keeps_state():
    engine, state = _make_engine_and_state()
    state.marker_owner_id = 1
    state.marker_draft_clockwise = True
    state.pending_marker_flip_owner_id = None
    state.current_round_order = [0, 1, 2, 3]
    for player in state.players:
        player.current_character = "산적"

    engine._apply_round_end_marker_management(state)

    assert state.marker_owner_id == 1
    assert state.marker_draft_clockwise is True
    assert state.pending_marker_flip_owner_id is None


def test_draft_order_follows_marker_direction():
    engine, state = _make_engine_and_state()
    state.marker_owner_id = 1
    state.marker_draft_clockwise = True

    clockwise = engine._alive_ids_from_marker_direction(state)
    assert clockwise == [1, 2, 3, 0]

    state.marker_draft_clockwise = False
    counterclockwise = engine._alive_ids_from_marker_direction(state)
    assert counterclockwise == [1, 0, 3, 2]
