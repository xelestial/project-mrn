from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

import threading
import time
from types import SimpleNamespace

from viewer.human_policy import HumanHttpPolicy


class _DummyAi:
    def choose_draft_card(self, state, player, offered_cards):
        return offered_cards[0]

    def choose_hidden_trick_card(self, state, player, hand):
        return hand[0] if hand else None

    def choose_lap_reward(self, state, player):
        return SimpleNamespace(choice="cash", cash_units=1, shard_units=0, coin_units=0)

    def choose_trick_tile_target(self, state, player, card_name, candidate_tiles, target_scope="any"):
        return candidate_tiles[0] if candidate_tiles else None


def _wait_pending(policy: HumanHttpPolicy, timeout_s: float = 1.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pending = policy.pending_prompt
        if pending is not None:
            return pending
        time.sleep(0.01)
    raise AssertionError("pending prompt was not published in time")


def _fake_state() -> SimpleNamespace:
    return SimpleNamespace(
        rounds_completed=0,
        turn_index=0,
        active_by_card={1: "어사", 2: "자객"},
        config=SimpleNamespace(
            characters=SimpleNamespace(),
            rules=SimpleNamespace(
                lap_reward=SimpleNamespace(
                    points_budget=10,
                    cash_pool=5,
                    shards_pool=3,
                    coins_pool=3,
                    cash_point_cost=2,
                    shards_point_cost=3,
                    coins_point_cost=3,
                )
            ),
        ),
        lap_reward_cash_pool_remaining=4,
        lap_reward_shards_pool_remaining=2,
        lap_reward_coins_pool_remaining=3,
    )


def _fake_player(player_id: int = 0):
    return SimpleNamespace(
        player_id=player_id,
        cash=20,
        position=0,
        trick_hand=[],
        hidden_trick_deck_index=None,
    )


def test_draft_prompt_contains_character_ability_payload():
    policy = HumanHttpPolicy(human_seat=0, ai_fallback=_DummyAi())
    state = _fake_state()
    player = _fake_player(0)
    result_holder = {}

    thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", policy.choose_draft_card(state, player, [1, 2])),
        daemon=True,
    )
    thread.start()
    pending = _wait_pending(policy)

    assert pending["request_type"] == "draft_card"
    legal_choices = pending["legal_choices"]
    assert legal_choices
    for choice in legal_choices:
        value = choice.get("value") or {}
        assert "character_ability" in value
        assert isinstance(value["character_ability"], str)
        assert value["character_ability"].strip()

    first_choice_id = legal_choices[0]["choice_id"]
    assert policy.submit_response({"choice_id": first_choice_id})
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert result_holder["result"] in (1, 2)
    assert pending["public_context"]["draft_phase"] == 1
    assert pending["public_context"]["offered_names"] == ["어사", "자객"]


def test_hidden_trick_prompt_contains_full_hand_context():
    policy = HumanHttpPolicy(human_seat=0, ai_fallback=_DummyAi())
    state = _fake_state()
    player = _fake_player(0)
    hand = [
        SimpleNamespace(deck_index=11, name="마당발", description="설명A"),
        SimpleNamespace(deck_index=12, name="건강 검진", description="설명B"),
        SimpleNamespace(deck_index=13, name="긴장감 조성", description="설명C"),
    ]
    player.trick_hand = list(hand)
    player.hidden_trick_deck_index = 12
    result_holder = {}

    thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", policy.choose_hidden_trick_card(state, player, list(hand))),
        daemon=True,
    )
    thread.start()
    pending = _wait_pending(policy)

    assert pending["request_type"] == "hidden_trick_card"
    public_context = pending["public_context"]
    assert public_context["round_index"] == 1
    assert public_context["turn_index"] == 1
    full_hand = public_context.get("full_hand")
    assert isinstance(full_hand, list)
    assert len(full_hand) == 3
    assert {item.get("name") for item in full_hand} == {"마당발", "건강 검진", "긴장감 조성"}
    hidden_items = [item for item in full_hand if item.get("is_hidden")]
    assert len(hidden_items) == 1
    assert hidden_items[0].get("deck_index") == 12

    assert policy.submit_response({"choice_id": "11"})
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert getattr(result_holder["result"], "deck_index", None) == 11


def test_lap_reward_prompt_contains_budget_bundles_and_status_context():
    policy = HumanHttpPolicy(human_seat=0, ai_fallback=_DummyAi())
    state = _fake_state()
    player = _fake_player(0)
    player.shards = 4
    player.hand_coins = 2
    player.score_coins_placed = 3
    player.tiles_owned = 5
    result_holder = {}

    thread = threading.Thread(target=lambda: result_holder.setdefault("result", policy.choose_lap_reward(state, player)), daemon=True)
    thread.start()
    pending = _wait_pending(policy)

    assert pending["request_type"] == "lap_reward"
    assert pending["public_context"]["budget"] == 10
    assert pending["public_context"]["pools"] == {"cash": 4, "shards": 2, "coins": 3}
    assert pending["public_context"]["player_total_score"] == 5
    mixed_choices = [choice for choice in pending["legal_choices"] if (choice.get("value") or {}).get("cash_units", 0) > 0 and (choice.get("value") or {}).get("coin_units", 0) > 0]
    assert mixed_choices

    assert policy.submit_response({"choice_id": pending["legal_choices"][0]["choice_id"]})
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert getattr(result_holder["result"], "choice", None) in {"cash", "shards", "coins", "mixed"}


def test_trick_tile_target_prompt_contains_candidate_tiles():
    policy = HumanHttpPolicy(human_seat=0, ai_fallback=_DummyAi())
    state = _fake_state()
    player = _fake_player(0)
    result_holder = {}

    thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", policy.choose_trick_tile_target(state, player, "재뿌리기", [4, 9, 12], "other_owned_highest")),
        daemon=True,
    )
    thread.start()
    pending = _wait_pending(policy)

    assert pending["request_type"] == "trick_tile_target"
    assert pending["public_context"]["candidate_count"] == 3
    assert pending["public_context"]["candidate_tiles"] == [4, 9, 12]
    assert pending["public_context"]["target_scope"] == "other_owned_highest"

    assert policy.submit_response({"choice_id": "9"})
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert result_holder["result"] == 9
