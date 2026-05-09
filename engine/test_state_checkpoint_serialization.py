from __future__ import annotations

import json

from config import GameConfig
from state import ActionEnvelope, GameState


def test_player_hidden_trick_count_requires_matching_hidden_card() -> None:
    state = GameState.create(GameConfig(player_count=2))
    player = state.players[0]
    player.trick_hand = [state.trick_draw_pile.pop(0), state.trick_draw_pile.pop(0)]

    player.hidden_trick_deck_index = None
    assert player.hidden_trick_count() == 0
    assert len(player.public_trick_names()) == 2

    player.hidden_trick_deck_index = 999999
    assert player.hidden_trick_count() == 0
    assert len(player.public_trick_names()) == 2

    player.hidden_trick_deck_index = player.trick_hand[0].deck_index
    assert player.hidden_trick_count() == 1
    assert len(player.public_trick_names()) == 1


def test_game_state_checkpoint_payload_round_trips_runtime_state() -> None:
    config = GameConfig(player_count=3)
    state = GameState.create(config)
    state.turn_index = 4
    state.rounds_completed = 2
    state.current_round_order = [2, 0, 1]
    state.f_value = 7.5
    state.marker_owner_id = 1
    state.active_by_card = {1: "암행어사", 2: "자객"}
    state.fortune_discard_pile.append(state.fortune_draw_pile.pop(0))
    state.fortune_discard_pile.append(state.fortune_draw_pile.pop(0))
    state.current_weather = state.weather_draw_pile.pop(0)
    state.weather_discard_pile.append(state.weather_draw_pile.pop(0))
    state.current_weather_effects = {"test_weather"}
    state.tiles[3].owner_id = 1
    state.tiles[3].score_coins = 2
    state.players[1].position = 9
    state.players[1].cash = 12
    state.players[1].shards = 3
    state.players[1].current_character = "자객"
    state.players[1].visited_owned_tile_indices = {3, 5}
    state.players[1].trick_hand = [state.trick_draw_pile.pop(0), state.trick_draw_pile.pop(0)]
    state.players[1].hidden_trick_deck_index = state.players[1].trick_hand[0].deck_index
    state.trick_discard_pile.append(state.trick_draw_pile.pop(0))
    state.prompt_sequence = 6
    state.pending_prompt_request_id = "sess_1:r2:t4:p2:movement:6"
    state.pending_prompt_type = "movement"
    state.pending_prompt_player_id = 2
    state.pending_prompt_instance_id = 6
    state.pending_actions = [
        ActionEnvelope(
            action_id="act_1",
            type="apply_move",
            actor_player_id=1,
            source="fortune:test",
            payload={"target_pos": 7, "lap_credit": False, "schedule_arrival": True},
        )
    ]
    state.scheduled_actions = [
        ActionEnvelope(
            action_id="mark_1",
            type="resolve_mark",
            actor_player_id=0,
            source="mark:hunter_pull",
            target_player_id=1,
            phase="turn_start",
            priority=10,
            idempotency_key="mark:0:1:hunter_pull:1",
            payload={"mark": {"type": "hunter_pull", "source_pid": 0, "source_pos": 3}},
        )
    ]
    state.pending_action_log = {"actor_player_id": 1, "segments": [{"start_pos": 3, "end_pos": 7}]}
    state.pending_turn_completion = {"player_id": 1, "finisher_before": 2, "disruption_before": {"leader_id": 0}}
    state.rng_state_b64 = "checkpoint-rng-state"
    state.lap_reward_cash_pool_remaining = 17
    state.lap_reward_shards_pool_remaining = 11
    state.lap_reward_coins_pool_remaining = 9
    state.start_reward_cash_pool_remaining = 23
    state.start_reward_shards_pool_remaining = 13
    state.start_reward_coins_pool_remaining = 7

    payload = json.loads(json.dumps(state.to_checkpoint_payload(), ensure_ascii=False))
    restored = GameState.from_checkpoint_payload(config, payload)

    assert restored.turn_index == 4
    assert restored.rounds_completed == 2
    assert restored.current_round_order == [2, 0, 1]
    assert restored.f_value == 7.5
    assert restored.marker_owner_id == 1
    assert restored.active_by_card == {1: "암행어사", 2: "자객"}
    assert restored.current_weather is not None
    assert restored.current_weather.deck_index == payload["current_weather"]
    assert restored.current_weather_effects == {"test_weather"}
    assert restored.tiles[3].owner_id == 1
    assert restored.tiles[3].score_coins == 2
    assert restored.tiles[3].purchase_cost == payload["tiles"][3]["purchase_cost"]
    assert restored.tiles[3].rent_cost == payload["tiles"][3]["rent_cost"]
    assert restored.players[1].position == 9
    assert restored.players[1].cash == 12
    assert restored.players[1].shards == 3
    assert restored.players[1].current_character == "자객"
    assert restored.players[1].visited_owned_tile_indices == {3, 5}
    assert [card.deck_index for card in restored.players[1].trick_hand] == payload["players"][1]["trick_hand"]
    assert restored.players[1].hidden_trick_deck_index == payload["players"][1]["hidden_trick_deck_index"]
    assert [card.deck_index for card in restored.fortune_draw_pile] == payload["fortune_draw_pile"]
    assert [card.deck_index for card in restored.fortune_discard_pile] == payload["fortune_discard_pile"]
    assert [card.deck_index for card in restored.trick_draw_pile] == payload["trick_draw_pile"]
    assert [card.deck_index for card in restored.trick_discard_pile] == payload["trick_discard_pile"]
    assert [card.deck_index for card in restored.weather_draw_pile] == payload["weather_draw_pile"]
    assert [card.deck_index for card in restored.weather_discard_pile] == payload["weather_discard_pile"]
    assert restored.prompt_sequence == 6
    assert restored.pending_prompt_request_id == "sess_1:r2:t4:p2:movement:6"
    assert restored.pending_prompt_type == "movement"
    assert restored.pending_prompt_player_id == 2
    assert restored.pending_prompt_instance_id == 6
    assert len(restored.pending_actions) == 1
    assert restored.pending_actions[0].type == "apply_move"
    assert restored.pending_actions[0].payload == {"target_pos": 7, "lap_credit": False, "schedule_arrival": True}
    assert len(restored.scheduled_actions) == 1
    assert restored.scheduled_actions[0].type == "resolve_mark"
    assert restored.scheduled_actions[0].target_player_id == 1
    assert restored.scheduled_actions[0].phase == "turn_start"
    assert restored.scheduled_actions[0].priority == 10
    assert restored.pending_action_log == {"actor_player_id": 1, "segments": [{"start_pos": 3, "end_pos": 7}]}
    assert restored.pending_turn_completion == {"player_id": 1, "finisher_before": 2, "disruption_before": {"leader_id": 0}}
    assert restored.rng_state_b64 == "checkpoint-rng-state"
    assert restored.lap_reward_cash_pool_remaining == 17
    assert restored.lap_reward_shards_pool_remaining == 11
    assert restored.lap_reward_coins_pool_remaining == 9
    assert restored.start_reward_cash_pool_remaining == 23
    assert restored.start_reward_shards_pool_remaining == 13
    assert restored.start_reward_coins_pool_remaining == 7
