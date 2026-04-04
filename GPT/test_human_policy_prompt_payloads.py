import threading
import time
from types import SimpleNamespace

from viewer.human_policy import HumanHttpPolicy


class _DummyAi:
    def choose_draft_card(self, state, player, offered_cards):
        return offered_cards[0]

    def choose_hidden_trick_card(self, state, player, hand):
        return hand[0] if hand else None


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
        active_by_card={1: "어사", 2: "자객"},
        config=SimpleNamespace(characters=SimpleNamespace()),
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
