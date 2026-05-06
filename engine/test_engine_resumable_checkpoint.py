from __future__ import annotations

import random

from ai_policy import HeuristicPolicy
from config import CellKind, GameConfig
from engine import GameEngine
from fortune_cards import build_fortune_deck
from policy.environment_traits import (
    FORTUNE_CUT_IN_LINE_ID,
    FORTUNE_DONATION_ANGEL_ID,
    FORTUNE_IRRESISTIBLE_DEAL_ID,
    FORTUNE_LAND_THIEF_ID,
    FORTUNE_PIOUS_MARKER_ID,
    FORTUNE_SHORT_TRIP_ID,
    FORTUNE_SUBSCRIPTION_WIN_ID,
    FORTUNE_TAKEOVER_BACK_2_ID,
    fortune_card_id_for_name,
)
from state import ActionEnvelope, GameState
from trick_cards import TrickCard
from viewer.stream import VisEventStream


def _run_standard_move_action_path(
    engine: GameEngine,
    state: GameState,
    player_index: int,
    move: int,
    movement_meta: dict,
) -> None:
    player = state.players[player_index]
    engine._enqueue_standard_move_action(
        state,
        player,
        move,
        dict(movement_meta),
        emit_move_event=False,
    )
    while _checkpoint_pending_actions(state):
        engine.run_next_transition(state)


def _checkpoint_pending_actions(state: GameState) -> list[ActionEnvelope]:
    return [
        ActionEnvelope.from_payload(action)
        for action in state.to_checkpoint_payload().get("pending_actions", [])
    ]


def _checkpoint_pending_action_types(state: GameState) -> list[str]:
    return [action.type for action in _checkpoint_pending_actions(state)]


_NO_HIDDEN_TRICK_SELECTION = object()


def _hidden_trick_selection_for_test(request):  # noqa: ANN001
    if request.decision_name != "choose_hidden_trick_card":
        return _NO_HIDDEN_TRICK_SELECTION
    fallback = getattr(request, "fallback", None)
    if callable(fallback):
        return fallback()
    hand = request.args[2] if len(request.args) > 2 else []
    return hand[0] if hand else None


def _assert_core_move_state_matches(action_state: GameState, legacy_state: GameState, player_index: int = 0) -> None:
    action_player = action_state.players[player_index]
    legacy_player = legacy_state.players[player_index]
    assert action_player.position == legacy_player.position
    assert action_player.total_steps == legacy_player.total_steps
    assert action_player.cash == legacy_player.cash
    assert action_player.shards == legacy_player.shards
    assert action_player.hand_coins == legacy_player.hand_coins
    assert action_player.trick_encounter_boost_this_turn == legacy_player.trick_encounter_boost_this_turn
    assert action_state.f_value == legacy_state.f_value


def _last_turn_log(engine: GameEngine) -> dict:
    return next(row for row in reversed(engine._action_log) if row.get("event") == "turn")


def _fortune_card_by_id(card_id: int):
    return next(card for card in build_fortune_deck() if fortune_card_id_for_name(card.name) == card_id)


def test_engine_run_accepts_hydrated_checkpoint_state() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    state.rounds_completed = 1
    state.turn_index = 0
    state.current_round_order = []
    state.winner_ids = [0]
    state.end_reason = "checkpoint_test"
    restored = GameState.from_checkpoint_payload(config, state.to_checkpoint_payload())
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(1))

    result = engine.run(initial_state=restored)

    assert result.total_turns == 0
    assert result.alive_count == 2


def test_engine_next_transition_commits_one_turn_boundary() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(2))
    state = engine.prepare_run()

    step = engine.run_next_transition(state)
    payload = state.to_checkpoint_payload()

    assert step["status"] in {"committed", "completed"}
    assert payload["schema_version"] == 1
    assert (
        payload["turn_index"] >= 1
        or payload["pending_actions"]
        or payload["pending_turn_completion"]
        or payload["runtime_frame_stack"]
        or step["status"] == "completed"
    )
    assert len(payload["players"]) == 2

    for _ in range(50):
        if step["status"] == "completed" or state.turn_index >= 1:
            break
        step = engine.run_next_transition(state)

    assert state.turn_index >= 1 or step["status"] == "completed"


def test_engine_next_transition_drains_one_pending_action_before_turn() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(3))
    state = engine.prepare_run()
    player = state.players[0]
    player.position = 1
    target = state.first_tile_position(kinds=[CellKind.F1])
    before_turn = state.turn_index
    before_f = state.f_value
    state.pending_actions = [
        ActionEnvelope(
            action_id="act_move_to_f1",
            type="apply_move",
            actor_player_id=0,
            source="test",
            payload={
                "target_pos": target,
                "lap_credit": False,
                "schedule_arrival": True,
                "emit_move_event": False,
                "trigger": "test_action",
            },
        )
    ]

    first = engine.run_next_transition(state)

    assert first["status"] == "committed"
    assert first["action_type"] == "apply_move"
    assert state.turn_index == before_turn
    assert player.position == target
    assert state.f_value == before_f
    assert _checkpoint_pending_action_types(state) == ["resolve_arrival"]

    second = engine.run_next_transition(state)

    assert second["status"] == "committed"
    assert second["action_type"] == "resolve_arrival"
    assert state.turn_index == before_turn
    assert state.f_value > before_f
    assert _checkpoint_pending_action_types(state) == []


def test_scheduled_turn_start_mark_materializes_before_target_turn() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(12))
    state = engine.prepare_run()
    source = state.players[0]
    target = state.players[1]
    state.current_round_order = [target.player_id, source.player_id]
    state.turn_index = 0
    source.shards = 3
    target.cash = 10
    mark = {"type": "bandit_tax", "source_pid": source.player_id}
    target.pending_marks.append(mark)
    engine._schedule_action(
        state,
        "resolve_mark",
        source,
        "mark:bandit_tax",
        {"mark": dict(mark), "target_player_id": target.player_id},
        target_player_id=target.player_id,
        phase="turn_start",
        priority=10,
    )

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_mark"
    assert target.cash == 7
    assert target.pending_marks == []
    assert state.turn_index == 0
    assert _checkpoint_pending_action_types(state) == []
    assert state.scheduled_actions == []
    assert target.turns_taken == 0


def test_scheduled_hunter_mark_queues_move_before_target_turn() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(13))
    state = engine.prepare_run()
    source = state.players[0]
    target = state.players[1]
    state.current_round_order = [target.player_id, source.player_id]
    state.turn_index = 0
    source.position = 8
    target.position = 2
    mark = {"type": "hunter_pull", "source_pid": source.player_id, "source_pos": source.position}
    target.pending_marks.append(mark)
    engine._schedule_action(
        state,
        "resolve_mark",
        source,
        "mark:hunter_pull",
        {"mark": dict(mark), "target_player_id": target.player_id},
        target_player_id=target.player_id,
        phase="turn_start",
        priority=10,
    )

    first = engine.run_next_transition(state)

    assert first["action_type"] == "resolve_mark"
    assert target.position == 2
    assert target.pending_marks == []
    pending = _checkpoint_pending_actions(state)
    assert [action.type for action in pending] == ["apply_move"]
    assert pending[0].source == "forced_move"

    second = engine.run_next_transition(state)

    assert second["action_type"] == "apply_move"
    assert target.position == source.position
    assert _checkpoint_pending_action_types(state) == ["resolve_arrival"]
    assert target.turns_taken == 0


def test_fortune_arrival_card_produces_followup_move_action() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(14))
    state = engine.prepare_run()
    player = state.players[0]
    other = state.players[1]
    player.position = 2
    other.position = 9
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_SHORT_TRIP_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_ARRIVAL"
    assert result["resolution"]["target_pos"] == other.position
    assert player.position == 2
    pending = _checkpoint_pending_actions(state)
    assert [action.type for action in pending] == ["apply_move"]
    assert pending[0].payload["schedule_arrival"] is True

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert player.position == other.position
    assert _checkpoint_pending_action_types(state) == ["resolve_arrival"]


def test_fortune_move_only_card_produces_move_without_arrival_action() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(15))
    state = engine.prepare_run()
    player = state.players[0]
    other = state.players[1]
    player.position = 2
    other.position = 9
    before_f = state.f_value
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_CUT_IN_LINE_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_MOVE_ONLY"
    assert player.position == 2
    pending = _checkpoint_pending_actions(state)
    assert [action.type for action in pending] == ["apply_move"]
    assert pending[0].payload["schedule_arrival"] is False

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert player.position == other.position
    assert _checkpoint_pending_action_types(state) == []
    assert state.f_value == before_f


def test_fortune_takeover_backward_produces_move_then_takeover_actions() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(16))
    state = engine.prepare_run()
    player = state.players[0]
    owner = state.players[1]
    target_pos = state.first_tile_position(kinds=[CellKind.T3])
    player.position = (target_pos + 2) % len(state.board)
    owner.tiles_owned = 1
    state.tile_owner[target_pos] = owner.player_id
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_TAKEOVER_BACK_2_ID)]
    start_pos = player.position

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_TAKEOVER_BACKWARD"
    assert player.position == start_pos
    assert _checkpoint_pending_action_types(state) == ["apply_move", "resolve_fortune_takeover_backward"]

    first = engine.run_next_transition(state)
    second = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert second["action_type"] == "resolve_fortune_takeover_backward"
    assert player.position == target_pos
    assert state.tile_owner[target_pos] == player.player_id
    assert player.tiles_owned == 1
    assert owner.tiles_owned == 0


def test_fortune_subscription_produces_decision_action() -> None:
    class YesDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                return request.args[1][0]
            if request.decision_name == "choose_purchase_tile":
                return True
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=YesDecisionPort(), rng=random.Random(22))
    state = GameState.create(config)
    player = state.players[0]
    player.cash = 20
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_SUBSCRIPTION_WIN_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_SUBSCRIPTION"
    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_subscription"]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_fortune_subscription"
    assert _checkpoint_pending_action_types(state) == ["request_purchase_tile"]

    purchase = engine.run_next_transition(state)

    assert purchase["action_type"] == "request_purchase_tile"
    assert _checkpoint_pending_action_types(state) == ["resolve_purchase_tile"]

    commit = engine.run_next_transition(state)

    assert commit["action_type"] == "resolve_purchase_tile"
    assert any(owner == player.player_id for owner in state.tile_owner)


def test_fortune_subscription_decision_prompt_keeps_action_queued() -> None:
    class WaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                raise RuntimeError("prompt_required_for_test")
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=WaitingDecisionPort(), rng=random.Random(23))
    state = GameState.create(config)
    player = state.players[0]
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_SUBSCRIPTION_WIN_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_SUBSCRIPTION"
    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "prompt_required_for_test"
    else:
        raise AssertionError("fortune subscription target prompt should have interrupted the action")

    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_subscription"]


def test_fortune_subscription_purchase_prompt_does_not_restart_target_selection() -> None:
    calls: list[str] = []

    class PurchaseWaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            calls.append(request.decision_name)
            if request.decision_name == "choose_trick_tile_target":
                return request.args[1][0]
            if request.decision_name == "choose_purchase_tile":
                raise RuntimeError("purchase_prompt_required_for_test")
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=PurchaseWaitingDecisionPort(), rng=random.Random(231))
    state = GameState.create(config)
    player = state.players[0]
    player.cash = 20
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_SUBSCRIPTION_WIN_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_SUBSCRIPTION"
    target_step = engine.run_next_transition(state)

    assert target_step["action_type"] == "resolve_fortune_subscription"
    assert calls == ["choose_trick_tile_target"]
    assert _checkpoint_pending_action_types(state) == ["request_purchase_tile"]

    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "purchase_prompt_required_for_test"
    else:
        raise AssertionError("subscription purchase prompt should have interrupted the purchase action")

    assert calls == ["choose_trick_tile_target", "choose_purchase_tile"]
    assert _checkpoint_pending_action_types(state) == ["request_purchase_tile"]


def test_fortune_land_thief_produces_decision_action() -> None:
    class PickFirstDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                return request.args[1][0]
            return request.args[0][0]

    config = GameConfig(player_count=2)
    stream = VisEventStream()
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=PickFirstDecisionPort(), rng=random.Random(24), event_stream=stream)
    state = GameState.create(config)
    player = state.players[0]
    owner = state.players[1]
    target = state.first_tile_position(kinds=[CellKind.T2])
    state.tile_owner[target] = owner.player_id
    owner.tiles_owned = 1
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_LAND_THIEF_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_LAND_THIEF"
    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_land_thief"]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_fortune_land_thief"
    assert state.tile_owner[target] == player.player_id
    assert player.tiles_owned == 1
    assert owner.tiles_owned == 0
    result_events = [event for event in stream.events if event.event_type == "fortune_resolved" and event.payload.get("action_result")]
    assert result_events[-1].payload["resolution"]["type"] == "STEAL_TILE"
    assert result_events[-1].payload["resolution"]["transfer"] == {
        "pos": target,
        "from": owner.player_id + 1,
        "to": player.player_id + 1,
        "coins": 0,
        "changed": True,
    }
    assert result_events[-1].payload["summary"] == f"땅 도둑: P1이 P2의 {target + 1}번 칸을 가져감"


def test_fortune_donation_angel_produces_decision_action() -> None:
    class PickFirstDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                return request.args[1][0]
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=PickFirstDecisionPort(), rng=random.Random(25))
    state = GameState.create(config)
    player = state.players[0]
    marker_owner = state.players[1]
    state.marker_owner_id = marker_owner.player_id
    target = state.first_tile_position(kinds=[CellKind.T2])
    state.tile_owner[target] = player.player_id
    player.tiles_owned = 1
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_DONATION_ANGEL_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_DONATION_ANGEL"
    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_donation_angel"]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_fortune_donation_angel"
    assert state.tile_owner[target] == marker_owner.player_id
    assert player.tiles_owned == 0
    assert marker_owner.tiles_owned == 1


def test_fortune_forced_trade_produces_decision_action() -> None:
    class TradeDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                return request.args[1][0]
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=TradeDecisionPort(), rng=random.Random(26))
    state = GameState.create(config)
    player = state.players[0]
    other = state.players[1]
    own_tile = state.first_tile_position(kinds=[CellKind.T2])
    other_tile = next(
        idx
        for idx in state.tile_positions(kinds=[CellKind.T2, CellKind.T3])
        if idx != own_tile and state.block_ids[idx] != state.block_ids[own_tile]
    )
    state.tile_owner[own_tile] = player.player_id
    state.tile_owner[other_tile] = other.player_id
    player.tiles_owned = 1
    other.tiles_owned = 1
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_IRRESISTIBLE_DEAL_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_FORCED_TRADE"
    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_forced_trade"]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_fortune_forced_trade"
    assert state.tile_owner[own_tile] == other.player_id
    assert state.tile_owner[other_tile] == player.player_id
    assert player.tiles_owned == 1
    assert other.tiles_owned == 1


def test_fortune_pious_marker_produces_decision_action_for_marker_owner() -> None:
    class PickFirstDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                return request.args[1][0]
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=PickFirstDecisionPort(), rng=random.Random(27))
    state = GameState.create(config)
    player = state.players[0]
    state.marker_owner_id = player.player_id
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_PIOUS_MARKER_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_PIOUS_MARKER"
    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_pious_marker"]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_fortune_pious_marker"
    assert any(owner == player.player_id for owner in state.tile_owner)
    assert player.tiles_owned == 1


def test_fortune_forced_trade_prompt_keeps_action_queued() -> None:
    class WaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                raise RuntimeError("prompt_required_for_test")
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=WaitingDecisionPort(), rng=random.Random(28))
    state = GameState.create(config)
    player = state.players[0]
    other = state.players[1]
    own_tile = state.first_tile_position(kinds=[CellKind.T2])
    other_tile = next(idx for idx in state.tile_positions(kinds=[CellKind.T2, CellKind.T3]) if idx != own_tile)
    state.tile_owner[own_tile] = player.player_id
    state.tile_owner[other_tile] = other.player_id
    player.tiles_owned = 1
    other.tiles_owned = 1
    state.fortune_draw_pile = [_fortune_card_by_id(FORTUNE_IRRESISTIBLE_DEAL_ID)]

    result = engine._resolve_fortune_tile_single(state, player)

    assert result["resolution"]["type"] == "QUEUED_FORTUNE_FORCED_TRADE"
    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "prompt_required_for_test"
    else:
        raise AssertionError("forced trade target prompt should have interrupted the action")

    assert _checkpoint_pending_action_types(state) == ["resolve_fortune_forced_trade"]


def test_prompt_action_remains_queued_when_decision_waits() -> None:
    class WaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            hidden_selection = _hidden_trick_selection_for_test(request)
            if hidden_selection is not _NO_HIDDEN_TRICK_SELECTION:
                return hidden_selection
            if request.decision_name == "choose_draft_card":
                return request.args[0][0]
            if request.decision_name == "choose_final_character":
                return request.state.active_by_card[request.args[0][0]]
            raise RuntimeError("prompt_required_for_test")

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=WaitingDecisionPort(), rng=random.Random(17))
    state = engine.prepare_run()
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.free_purchase_this_turn = True
    state.pending_actions = [
        ActionEnvelope(
            action_id="purchase_wait",
            type="request_purchase_tile",
            actor_player_id=player.player_id,
            source="test_purchase",
            payload={"tile_index": tile_index, "purchase_source": "test_purchase"},
        )
    ]

    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "prompt_required_for_test"
    else:
        raise AssertionError("purchase prompt should have interrupted the transition")

    pending = _checkpoint_pending_actions(state)
    assert len(pending) == 1
    assert pending[0].action_id == "purchase_wait"
    assert state.tile_owner[tile_index] is None
    assert player.free_purchase_this_turn is True


def test_extreme_separation_trick_queues_target_move_action() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(29))
    state = GameState.create(config)
    player = state.players[0]
    other = state.players[1]
    player.position = 1
    other.position = 12

    result = engine._apply_trick_card(
        state,
        player,
        TrickCard(deck_index=999, name="극심한 분리불안", description=""),
    )

    assert result["type"] == "QUEUED_TRICK_TARGET_MOVE"
    assert result["target_pos"] == other.position
    assert player.position == 1
    pending = _checkpoint_pending_actions(state)
    assert [action.type for action in pending] == ["apply_move"]
    assert pending[0].source == "trick_extreme_separation"
    assert pending[0].payload["schedule_arrival"] is True
    assert pending[0].payload["lap_credit"] is False

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert player.position == other.position
    assert _checkpoint_pending_action_types(state) == ["resolve_arrival"]


def test_trick_tile_rent_modifier_queues_target_decision_action() -> None:
    class TargetDecisionPort:
        def __init__(self, target: int) -> None:
            self.target = target

        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                return self.target
            return request.args[0][0]

    config = GameConfig(player_count=2)
    state = GameState.create(config)
    player = state.players[0]
    owner = state.players[1]
    target = state.first_tile_position(kinds=[CellKind.T2])
    state.tile_owner[target] = owner.player_id
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=TargetDecisionPort(target), rng=random.Random(31))

    result = engine._apply_trick_card(
        state,
        player,
        TrickCard(deck_index=1001, name="재뿌리기", description=""),
    )

    assert result["type"] == "QUEUED_TRICK_TILE_RENT_MODIFIER"
    assert state.tile_rent_modifiers_this_turn == {}
    assert _checkpoint_pending_action_types(state) == ["resolve_trick_tile_rent_modifier"]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "resolve_trick_tile_rent_modifier"
    assert state.tile_rent_modifiers_this_turn[target] == 0


def test_trick_tile_rent_modifier_prompt_keeps_action_queued() -> None:
    class WaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_trick_tile_target":
                raise RuntimeError("prompt_required_for_test")
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=WaitingDecisionPort(), rng=random.Random(32))
    state = GameState.create(config)
    player = state.players[0]
    target = state.first_tile_position(kinds=[CellKind.T2])
    state.tile_owner[target] = player.player_id
    state.pending_actions = [
        ActionEnvelope(
            action_id="trick_rent_double_prompt",
            type="resolve_trick_tile_rent_modifier",
            actor_player_id=player.player_id,
            source="trick_tile_rent_modifier",
            payload={
                "card_name": "긴장감 조성",
                "target_scope": "owned",
                "selection_mode": "owned_highest",
                "modifier_kind": "rent_double",
            },
        )
    ]

    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "prompt_required_for_test"
    else:
        raise AssertionError("trick tile target prompt should have interrupted the queued action")

    assert _checkpoint_pending_action_types(state) == ["resolve_trick_tile_rent_modifier"]
    assert state.tile_rent_modifiers_this_turn == {}


def test_request_purchase_tile_action_can_resume_and_purchase() -> None:
    class YesDecisionPort:
        def request(self, request):  # noqa: ANN001
            hidden_selection = _hidden_trick_selection_for_test(request)
            if hidden_selection is not _NO_HIDDEN_TRICK_SELECTION:
                return hidden_selection
            if request.decision_name == "choose_draft_card":
                return request.args[0][0]
            if request.decision_name == "choose_final_character":
                return request.state.active_by_card[request.args[0][0]]
            return True

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=YesDecisionPort(), rng=random.Random(18))
    state = engine.prepare_run()
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    starting_cash = player.cash
    cost = state.config.rules.economy.purchase_cost_for(state, tile_index)
    state.pending_actions = [
        ActionEnvelope(
            action_id="purchase_resume",
            type="request_purchase_tile",
            actor_player_id=player.player_id,
            source="test_purchase",
            payload={"tile_index": tile_index, "purchase_source": "test_purchase"},
        )
    ]

    step = engine.run_next_transition(state)

    assert step["action_type"] == "request_purchase_tile"
    assert _checkpoint_pending_action_types(state) == ["resolve_purchase_tile"]
    assert state.tile_owner[tile_index] is None
    assert player.cash == starting_cash

    resolve = engine.run_next_transition(state)

    assert resolve["action_type"] == "resolve_purchase_tile"
    assert _checkpoint_pending_action_types(state) == []
    assert state.tile_owner[tile_index] == player.player_id
    assert player.cash == starting_cash - cost
    assert player.tiles_owned == 1


def test_purchase_resolution_queues_score_token_placement() -> None:
    class YesDecisionPort:
        def request(self, request):  # noqa: ANN001
            hidden_selection = _hidden_trick_selection_for_test(request)
            if hidden_selection is not _NO_HIDDEN_TRICK_SELECTION:
                return hidden_selection
            if request.decision_name == "choose_draft_card":
                return request.args[0][0]
            if request.decision_name == "choose_final_character":
                return request.state.active_by_card[request.args[0][0]]
            return True

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=YesDecisionPort(), rng=random.Random(181))
    state = engine.prepare_run()
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.hand_coins = 2
    state.pending_actions = [
        ActionEnvelope(
            action_id="purchase_score_token",
            type="request_purchase_tile",
            actor_player_id=player.player_id,
            source="test_purchase",
            payload={"tile_index": tile_index, "purchase_source": "test_purchase"},
        )
    ]

    request = engine.run_next_transition(state)
    purchase = engine.run_next_transition(state)

    assert request["action_type"] == "request_purchase_tile"
    assert purchase["action_type"] == "resolve_purchase_tile"
    assert _checkpoint_pending_action_types(state) == ["resolve_score_token_placement"]
    assert state.tile_owner[tile_index] == player.player_id
    assert state.tile_coins[tile_index] == 0
    assert player.hand_coins == 2

    placement = engine.run_next_transition(state)

    assert placement["action_type"] == "resolve_score_token_placement"
    assert _checkpoint_pending_action_types(state) == []
    assert state.tile_coins[tile_index] == 1
    assert player.hand_coins == 1


def test_queued_arrival_on_unowned_tile_splits_purchase_followups() -> None:
    class YesDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_purchase_tile":
                return True
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=YesDecisionPort(), rng=random.Random(19), enable_logging=True)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.position = tile_index
    state.pending_actions = [
        ActionEnvelope(
            action_id="arrival_purchase_split",
            type="resolve_arrival",
            actor_player_id=player.player_id,
            source="test_arrival",
            payload={"trigger": "test_arrival"},
        )
    ]

    first = engine.run_next_transition(state)

    assert first["action_type"] == "resolve_arrival"
    assert state.tile_owner[tile_index] is None
    assert _checkpoint_pending_action_types(state) == ["request_purchase_tile", "resolve_unowned_post_purchase"]

    second = engine.run_next_transition(state)
    third = engine.run_next_transition(state)
    fourth = engine.run_next_transition(state)
    last_action_log = next(row for row in reversed(engine._action_log) if row.get("event") == "action_transition")

    assert second["action_type"] == "request_purchase_tile"
    assert third["action_type"] == "resolve_purchase_tile"
    assert fourth["action_type"] == "resolve_unowned_post_purchase"
    assert _checkpoint_pending_action_types(state) == []
    assert state.tile_owner[tile_index] == player.player_id
    assert last_action_log["result"]["type"] == "PURCHASE"


def test_queued_arrival_purchase_places_score_token_before_post_followup() -> None:
    class YesDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_purchase_tile":
                return True
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=YesDecisionPort(), rng=random.Random(191), enable_logging=True)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.position = tile_index
    player.hand_coins = 2
    state.pending_actions = [
        ActionEnvelope(
            action_id="arrival_purchase_token_split",
            type="resolve_arrival",
            actor_player_id=player.player_id,
            source="test_arrival",
            payload={"trigger": "test_arrival"},
        )
    ]

    actions = [engine.run_next_transition(state)["action_type"] for _ in range(5)]
    last_action_log = next(row for row in reversed(engine._action_log) if row.get("event") == "action_transition")

    assert actions == [
        "resolve_arrival",
        "request_purchase_tile",
        "resolve_purchase_tile",
        "resolve_score_token_placement",
        "resolve_unowned_post_purchase",
    ]
    assert _checkpoint_pending_action_types(state) == []
    assert state.tile_owner[tile_index] == player.player_id
    assert state.tile_coins[tile_index] == 1
    assert player.hand_coins == 1
    assert last_action_log["result"]["type"] == "PURCHASE"
    assert last_action_log["result"]["placed"]["amount"] == 1


def test_queued_arrival_purchase_prompt_keeps_purchase_action_queued() -> None:
    class WaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_purchase_tile":
                raise RuntimeError("prompt_required_for_test")
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=WaitingDecisionPort(), rng=random.Random(20))
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.position = tile_index
    state.pending_actions = [
        ActionEnvelope(
            action_id="arrival_purchase_prompt",
            type="resolve_arrival",
            actor_player_id=player.player_id,
            source="test_arrival",
            payload={"trigger": "test_arrival"},
        )
    ]

    engine.run_next_transition(state)

    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "prompt_required_for_test"
    else:
        raise AssertionError("purchase prompt should have interrupted the queued purchase action")

    pending = _checkpoint_pending_actions(state)
    assert [action.type for action in pending] == ["request_purchase_tile", "resolve_unowned_post_purchase"]
    assert pending[0].payload["tile_index"] == tile_index
    assert state.tile_owner[tile_index] is None


def test_queued_own_tile_visit_splits_score_token_choice_and_placement() -> None:
    class CoinDecisionPort:
        def __init__(self, target: int) -> None:
            self.target = target

        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_coin_placement_tile":
                return self.target
            return request.args[0][0]

    config = GameConfig(player_count=2)
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.position = tile_index
    player.hand_coins = 0
    player.tiles_owned = 1
    state.tile_owner[tile_index] = player.player_id
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=CoinDecisionPort(tile_index), rng=random.Random(201), enable_logging=True)
    state.pending_actions = [
        ActionEnvelope(
            action_id="arrival_own_tile_token_split",
            type="resolve_arrival",
            actor_player_id=player.player_id,
            source="test_arrival",
            payload={"trigger": "test_arrival"},
        )
    ]

    first = engine.run_next_transition(state)

    assert first["action_type"] == "resolve_arrival"
    assert _checkpoint_pending_action_types(state) == ["request_score_token_placement"]
    assert state.tile_coins[tile_index] == 0
    assert player.hand_coins == state.config.rules.token.coins_from_visiting_own_tile

    second = engine.run_next_transition(state)
    third = engine.run_next_transition(state)
    last_action_log = next(row for row in reversed(engine._action_log) if row.get("event") == "action_transition")

    assert second["action_type"] == "request_score_token_placement"
    assert third["action_type"] == "resolve_score_token_placement"
    assert _checkpoint_pending_action_types(state) == []
    assert state.tile_coins[tile_index] == 1
    assert player.hand_coins == state.config.rules.token.coins_from_visiting_own_tile - 1
    assert last_action_log["result"]["type"] == "OWN_TILE"
    assert last_action_log["result"]["placed"]["amount"] == 1


def test_queued_own_tile_score_token_prompt_keeps_request_queued() -> None:
    class WaitingDecisionPort:
        def request(self, request):  # noqa: ANN001
            if request.decision_name == "choose_coin_placement_tile":
                raise RuntimeError("prompt_required_for_test")
            return request.args[0][0]

    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), decision_port=WaitingDecisionPort(), rng=random.Random(202))
    state = GameState.create(config)
    player = state.players[0]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.position = tile_index
    player.tiles_owned = 1
    state.tile_owner[tile_index] = player.player_id
    state.pending_actions = [
        ActionEnvelope(
            action_id="arrival_own_tile_token_prompt",
            type="resolve_arrival",
            actor_player_id=player.player_id,
            source="test_arrival",
            payload={"trigger": "test_arrival"},
        )
    ]

    engine.run_next_transition(state)

    try:
        engine.run_next_transition(state)
    except RuntimeError as exc:
        assert str(exc) == "prompt_required_for_test"
    else:
        raise AssertionError("coin placement prompt should have interrupted the queued request action")

    assert _checkpoint_pending_action_types(state) == ["request_score_token_placement"]
    assert state.tile_coins[tile_index] == 0


def test_queued_arrival_on_rent_tile_splits_rent_and_post_landing_effects() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(21), enable_logging=True)
    state = GameState.create(config)
    player = state.players[0]
    owner = state.players[1]
    tile_index = state.first_tile_position(kinds=[CellKind.T2])
    player.position = tile_index
    owner.position = tile_index
    owner.tiles_owned = 1
    state.tile_owner[tile_index] = owner.player_id
    player.cash = 20
    player.trick_same_tile_cash2_this_turn = True
    state.pending_actions = [
        ActionEnvelope(
            action_id="arrival_rent_post_split",
            type="resolve_arrival",
            actor_player_id=player.player_id,
            source="test_arrival",
            payload={"trigger": "test_arrival"},
        )
    ]

    first = engine.run_next_transition(state)

    assert first["action_type"] == "resolve_arrival"
    assert _checkpoint_pending_action_types(state) == ["resolve_rent_payment"]
    assert player.cash == 20

    second = engine.run_next_transition(state)

    assert second["action_type"] == "resolve_rent_payment"
    assert _checkpoint_pending_action_types(state) == ["resolve_landing_post_effects"]
    assert player.cash == 20 - state.config.rules.economy.rent_cost_for(state, tile_index)

    third = engine.run_next_transition(state)
    last_action_log = next(row for row in reversed(engine._action_log) if row.get("event") == "action_transition")

    assert third["action_type"] == "resolve_landing_post_effects"
    assert _checkpoint_pending_action_types(state) == []
    assert last_action_log["result"]["type"] == "RENT"
    assert last_action_log["result"]["trick_same_tile_cash_gain"] == 2


def test_engine_queued_step_move_separates_lap_reward_from_arrival() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(4))
    state = engine.prepare_run()
    player = state.players[0]
    player.position = len(state.board) - 1
    start_cash = player.cash
    start_shards = player.shards
    start_hand_coins = player.hand_coins
    before_f = state.f_value
    state.pending_actions = [
        ActionEnvelope(
            action_id="act_step_to_f1",
            type="apply_move",
            actor_player_id=0,
            source="test_step",
            payload={
                "move_value": 1,
                "lap_credit": True,
                "schedule_arrival": True,
                "emit_move_event": False,
                "trigger": "test_step_move",
            },
        )
    ]

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert player.position == 0
    assert player.total_steps == 1
    assert (player.cash, player.shards, player.hand_coins) == (start_cash, start_shards, start_hand_coins)
    assert state.f_value == before_f
    assert _checkpoint_pending_action_types(state) == ["resolve_lap_reward", "resolve_arrival"]

    second = engine.run_next_transition(state)

    assert second["action_type"] == "resolve_lap_reward"
    assert (player.cash, player.shards, player.hand_coins) != (start_cash, start_shards, start_hand_coins)
    assert state.f_value == before_f
    assert _checkpoint_pending_action_types(state) == ["resolve_arrival"]

    third = engine.run_next_transition(state)

    assert third["action_type"] == "resolve_arrival"
    assert _checkpoint_pending_action_types(state) == []
    assert state.f_value > before_f


def test_engine_queued_step_move_without_arrival_still_queues_lap_reward() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(4))
    state = engine.prepare_run()
    player = state.players[0]
    player.position = len(state.board) - 1
    start_cash = player.cash
    start_shards = player.shards
    start_hand_coins = player.hand_coins
    state.pending_actions = [
        ActionEnvelope(
            action_id="act_step_to_f1_no_arrival",
            type="apply_move",
            actor_player_id=0,
            source="test_step",
            payload={
                "move_value": 1,
                "lap_credit": True,
                "schedule_arrival": False,
                "emit_move_event": False,
                "trigger": "test_step_move",
            },
        )
    ]

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert player.position == 0
    assert (player.cash, player.shards, player.hand_coins) == (start_cash, start_shards, start_hand_coins)
    assert _checkpoint_pending_action_types(state) == ["resolve_lap_reward"]

    second = engine.run_next_transition(state)

    assert second["action_type"] == "resolve_lap_reward"
    assert (player.cash, player.shards, player.hand_coins) != (start_cash, start_shards, start_hand_coins)
    assert _checkpoint_pending_action_types(state) == []


def test_standard_move_action_adapter_matches_simple_advance_player_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_standard", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(5))
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    legacy_player.position = len(legacy_state.board) - 1
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(5))
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = len(action_state.board) - 1
    action = action_engine._enqueue_standard_move_action(
        action_state,
        action_player,
        1,
        dict(movement_meta),
        emit_move_event=False,
    )

    first = action_engine.run_next_transition(action_state)
    second = action_engine.run_next_transition(action_state)
    third = action_engine.run_next_transition(action_state)

    assert action.type == "apply_move"
    assert first["action_type"] == "apply_move"
    assert second["action_type"] == "resolve_lap_reward"
    assert third["action_type"] == "resolve_arrival"
    assert _checkpoint_pending_action_types(action_state) == []
    assert action_player.position == legacy_player.position
    assert action_player.total_steps == legacy_player.total_steps
    assert action_player.cash == legacy_player.cash
    assert action_player.shards == legacy_player.shards
    assert action_player.hand_coins == legacy_player.hand_coins
    assert action_state.f_value == legacy_state.f_value


def test_standard_move_action_adapter_preserves_card_movement_meta_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "card_pair_fixed", "formula": "2+3", "used_cards": [2, 3]}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(6))
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    legacy_player.position = 2
    legacy_engine._advance_player(legacy_state, legacy_player, 5, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(6))
    action_state = action_engine.prepare_run()
    action_state.players[0].position = 2
    _run_standard_move_action_path(action_engine, action_state, 0, 5, movement_meta)

    _assert_core_move_state_matches(action_state, legacy_state)


def test_standard_move_action_adapter_matches_obstacle_slowdown_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_obstacle", "formula": "4"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(7))
    legacy_state = legacy_engine.prepare_run()
    legacy_mover = legacy_state.players[1]
    legacy_blocker = legacy_state.players[0]
    legacy_mover.position = 0
    legacy_blocker.position = 2
    legacy_blocker.trick_obstacle_this_round = True
    legacy_engine._advance_player(legacy_state, legacy_mover, 4, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(7))
    action_state = action_engine.prepare_run()
    action_mover = action_state.players[1]
    action_blocker = action_state.players[0]
    action_mover.position = 0
    action_blocker.position = 2
    action_blocker.trick_obstacle_this_round = True
    action = action_engine._enqueue_standard_move_action(
        action_state,
        action_mover,
        4,
        dict(movement_meta),
        emit_move_event=False,
    )
    assert action.payload["obstacle_slowdown"]["effective_move"] == 3
    while _checkpoint_pending_actions(action_state):
        action_engine.run_next_transition(action_state)

    _assert_core_move_state_matches(action_state, legacy_state, player_index=1)


def test_standard_move_action_adapter_matches_encounter_boost_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_encounter", "formula": "2"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(8))
    legacy_state = legacy_engine.prepare_run()
    legacy_mover = legacy_state.players[0]
    legacy_other = legacy_state.players[1]
    legacy_mover.position = 0
    legacy_mover.trick_encounter_boost_this_turn = True
    legacy_other.position = 1
    legacy_engine._advance_player(legacy_state, legacy_mover, 2, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(8))
    action_state = action_engine.prepare_run()
    action_mover = action_state.players[0]
    action_other = action_state.players[1]
    action_mover.position = 0
    action_mover.trick_encounter_boost_this_turn = True
    action_other.position = 1
    action = action_engine._enqueue_standard_move_action(
        action_state,
        action_mover,
        2,
        dict(movement_meta),
        emit_move_event=False,
    )
    assert action.payload["encounter_bonus"]["met_at"] == 1
    while _checkpoint_pending_actions(action_state):
        action_engine.run_next_transition(action_state)

    _assert_core_move_state_matches(action_state, legacy_state)


def test_zone_chain_arrival_queues_followup_move_and_matches_advance_player() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_zone_chain", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(9))
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    chain_pos = legacy_state.first_tile_position(kinds=[CellKind.T3])
    legacy_player.position = (chain_pos - 1) % len(legacy_state.board)
    legacy_player.trick_zone_chain_this_turn = True
    legacy_player.rolled_dice_count_this_turn = 1
    legacy_player.tiles_owned = 1
    legacy_state.tile_owner[chain_pos] = legacy_player.player_id
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(9))
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = (chain_pos - 1) % len(action_state.board)
    action_player.trick_zone_chain_this_turn = True
    action_player.rolled_dice_count_this_turn = 1
    action_player.tiles_owned = 1
    action_state.tile_owner[chain_pos] = action_player.player_id
    action_engine._enqueue_standard_move_action(
        action_state,
        action_player,
        1,
        dict(movement_meta),
        emit_move_event=False,
    )

    first = action_engine.run_next_transition(action_state)
    second = action_engine.run_next_transition(action_state)

    assert first["action_type"] == "apply_move"
    assert second["action_type"] == "resolve_arrival"
    pending = _checkpoint_pending_actions(action_state)
    assert pending
    assert pending[0].type == "apply_move"
    assert pending[0].source == "zone_chain"

    while _checkpoint_pending_actions(action_state):
        action_engine.run_next_transition(action_state)

    _assert_core_move_state_matches(action_state, legacy_state)


def test_standard_move_action_adapter_emits_action_move_visual_event() -> None:
    config = GameConfig(player_count=2)
    stream = VisEventStream()
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(10), event_stream=stream)
    state = engine.prepare_run()
    player = state.players[0]
    player.position = 2
    engine._vis_session_id = "resumable-action-test"
    engine._enqueue_standard_move_action(
        state,
        player,
        3,
        {"mode": "test_visual_action", "formula": "3"},
        emit_move_event=True,
    )

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    movement_events = [event for event in stream.events if event.event_type in {"player_move", "action_move"}]
    assert [event.event_type for event in movement_events] == ["action_move"]
    event = movement_events[0]
    assert event.payload["from_tile_index"] == 2
    assert event.payload["to_tile_index"] == 5
    assert event.payload["movement_source"] == "test_visual_action"
    assert event.payload["path"] == [3, 4, 5]


def test_standard_move_action_adapter_emits_turn_log_summary_like_advance_player() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_log", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(10), enable_logging=True)
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    legacy_player.position = len(legacy_state.board) - 1
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))
    legacy_row = _last_turn_log(legacy_engine)

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(10), enable_logging=True)
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = len(action_state.board) - 1
    _run_standard_move_action_path(action_engine, action_state, 0, 1, movement_meta)
    action_row = _last_turn_log(action_engine)

    for key in (
        "event",
        "player",
        "start_pos",
        "end_pos",
        "cell",
        "move",
        "movement",
        "laps_gained",
        "landing",
        "cash_before",
        "cash_after",
        "shards_before",
        "shards_after",
        "f_before",
        "f_after",
        "alive_before",
        "alive_after",
    ):
        assert action_row.get(key) == legacy_row.get(key)


def test_standard_move_action_adapter_emits_chain_turn_log_summary_like_advance_player() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_chain_log", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(11), enable_logging=True)
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    chain_pos = legacy_state.first_tile_position(kinds=[CellKind.T3])
    legacy_player.position = (chain_pos - 1) % len(legacy_state.board)
    legacy_player.trick_zone_chain_this_turn = True
    legacy_player.rolled_dice_count_this_turn = 1
    legacy_player.tiles_owned = 1
    legacy_state.tile_owner[chain_pos] = legacy_player.player_id
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))
    legacy_row = _last_turn_log(legacy_engine)

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(11), enable_logging=True)
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = (chain_pos - 1) % len(action_state.board)
    action_player.trick_zone_chain_this_turn = True
    action_player.rolled_dice_count_this_turn = 1
    action_player.tiles_owned = 1
    action_state.tile_owner[chain_pos] = action_player.player_id
    _run_standard_move_action_path(action_engine, action_state, 0, 1, movement_meta)
    action_row = _last_turn_log(action_engine)

    for key in (
        "event",
        "player",
        "start_pos",
        "end_pos",
        "cell",
        "move",
        "movement",
        "laps_gained",
        "landing",
        "chain_segments",
        "cash_before",
        "cash_after",
        "shards_before",
        "shards_after",
        "f_before",
        "f_after",
        "alive_before",
        "alive_after",
    ):
        assert action_row.get(key) == legacy_row.get(key)
