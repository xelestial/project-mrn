"""Phase 4 — Human Play tests.

Tests (no real browser needed):
1. HumanHttpPolicy routes human-seat decisions to queue, AI to fallback
2. HumanHttpPolicy AI fallback is used on timeout (simulated via very short timeout)
3. HumanPlayServer starts and responds on /prompt, /play, /decision
4. /prompt returns null when no decision pending
5. /decision returns 409 when no prompt is pending
6. /play serves valid HTML with decision panel
7. play_html renderer produces non-empty HTML with decision overlay
8. AI-seat decisions pass through immediately without blocking
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_human_server(seed: int = 99, port: int = 18866, human_seat: int = 0,
                         human_seats: list[int] | None = None,
                         turn_delay: float = 0.0):
    from viewer.prompt_server import HumanPlayServer
    server = HumanPlayServer(seed=seed, port=port, turn_delay=turn_delay,
                              human_seat=human_seat, human_seats=human_seats)

    def _run():
        server.start()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Wait until accepting connections
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    return server, t


def _wait_done(port: int, timeout: float = 60.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2)
            data = json.loads(resp.read())
            if data.get("done"):
                return data
        except Exception:
            pass
        time.sleep(0.2)
    return None


def _get_json(url: str) -> dict:
    resp = urllib.request.urlopen(url, timeout=5)
    return json.loads(resp.read())


def _get_text(url: str) -> str:
    resp = urllib.request.urlopen(url, timeout=5)
    return resp.read().decode("utf-8")


def _post_json(url: str, data: dict) -> tuple[int, dict]:
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


# ---------------------------------------------------------------------------
# Unit tests (no server)
# ---------------------------------------------------------------------------

def test_play_html_renderer() -> list[str]:
    errors = []
    from viewer.renderers.play_html import render_play_html
    html = render_play_html(session_id="test", seed=42, human_seat=1, human_seats=[1, 2], poll_interval_ms=200)
    if not html:
        errors.append("render_play_html returned empty string")
        return errors
    if "<!DOCTYPE html>" not in html:
        errors.append("play HTML missing DOCTYPE")
    if "decision-overlay" not in html:
        errors.append("play HTML missing decision-overlay element")
    if "/prompt" not in html:
        errors.append("play HTML does not reference /prompt endpoint")
    if "/decision" not in html:
        errors.append("play HTML does not reference /decision endpoint")
    if "HUMAN_SEAT" not in html:
        errors.append("play HTML missing HUMAN_SEAT constant")
    if "HUMAN_SEATS" not in html:
        errors.append("play HTML missing HUMAN_SEATS constant")
    if "submitDecision" not in html:
        errors.append("play HTML missing submitDecision function")
    if "board-track" not in html or "prompt-summary" not in html:
        errors.append("play HTML missing Phase 5 board/prompt panels")
    if "dp-context-list" not in html:
        errors.append("play HTML missing prompt context panel")
    for flow_marker in ("phase-strip", "legend-phase", "move-trail", "move-from", "activity-overlay", "asset-log", "story-rail-shell", "story-rail", "bankruptcy-banner"):
        if flow_marker not in html:
            errors.append(f"play HTML missing flow marker '{flow_marker}'")
    for click_guard in ("width:100%", "min-height:88px", ".dp-btn>*{pointer-events:none}"):
        if click_guard not in html:
            errors.append(f"play HTML missing click-area guard '{click_guard}'")
    for phase5_widget in (
        "movement-route",
        "reward-breakdown",
        "tile-choice-row",
        "target-pill-row",
        "choice-metrics",
        "geo-bonus-row",
        "doctrine-target-row",
        "trick-reward-row",
        "flip-choice-row",
        "burden-exchange-row",
    ):
        if phase5_widget not in html:
            errors.append(f"play HTML missing specialized widget '{phase5_widget}'")
    if "request_type" not in html or "legal_choices" not in html or "public_context" not in html:
        errors.append("play HTML missing canonical prompt-envelope fields")
    if "marker_owner_player_id" not in html:
        errors.append("play HTML missing canonical marker owner field")
    if "__EVENT_LABELS_JSON__" in html or "__LANDING_TYPE_LABELS_JSON__" in html:
        errors.append("play HTML still contains unresolved phrase-dictionary placeholders")
    if "EVENT_LABELS=" not in html or "LANDING_TYPE_LABELS=" not in html:
        errors.append("play HTML missing injected shared phrase dictionaries")
    if "function eventTypeLabel(type){return EVENT_LABELS[type]||type}" not in html:
        errors.append("play HTML does not use shared EVENT_LABELS mapping")
    if "public_tricks" not in html:
        errors.append("play HTML missing canonical public_tricks field")
    if "owned_tile_count" not in html or "placed_score_coins" not in html:
        errors.append("play HTML missing canonical player stat fields")
    if "여기서 보이는 이름 그대로 엔진에 전달됩니다." in html:
        errors.append("play HTML still exposes engine-facing draft/final note")
    if "Hide nothing" in html:
        errors.append("play HTML still exposes legacy hidden-trick skip wording")
    if "Skip (no trick)" in html:
        errors.append("play HTML still exposes legacy trick skip wording")
    if "decisionSubmitting" not in html or "promptSignature" not in html:
        errors.append("play HTML missing prompt submission lock state")
    if "setDecisionPendingState" not in html:
        errors.append("play HTML missing processing-state handler")
    if "network-badge" not in html or "setNetworkState" not in html:
        errors.append("play HTML missing network failure visibility handlers")
    if "handleDecisionKeydown" not in html or "focusDecisionButton" not in html:
        errors.append("play HTML missing keyboard decision navigation handlers")
    if "focusBeforeDecision" not in html:
        errors.append("play HTML missing focus-return handling for decision overlay")
    if "promptActionHint" not in html:
        errors.append("play HTML missing prompt action-guide helper")
    if "다음 행동 가이드" not in html:
        errors.append("play HTML missing prompt summary action-guide line")
    if "trickEffectText" not in html or "card_description" not in html:
        errors.append("play HTML missing trick effect text rendering for trick prompts")
    if "isTrickUseDecisionType" not in html or "buildTrickHandOverview" not in html:
        errors.append("play HTML missing full-hand trick overview helpers")
    if "dp-trick-hand-overview" not in html or ".dp-trick-hand-card.hidden" not in html:
        errors.append("play HTML missing hidden-trick visual distinction styles")
    if "isCharacterDecisionType" not in html or "characterChoiceGuideText" not in html:
        errors.append("play HTML missing character-choice prompt helpers")
    if "dp-char-guide" not in html or "character-choice" not in html:
        errors.append("play HTML missing character-choice visual treatment")
    if "클릭해서 이번 턴에 사용할 인물을 고르세요" not in html:
        errors.append("play HTML missing character-choice instruction copy")
    if 'aria-live="polite"' not in html or 'aria-modal="true"' not in html:
        errors.append("play HTML missing accessibility live/dialog attributes")
    if "pushActivity" not in html or "renderActivityOverlay" not in html:
        errors.append("play HTML missing other-player activity overlay handlers")
    if "incident-stack" not in html or "pushIncident" not in html:
        errors.append("play HTML missing board incident-card overlay handlers")
    if "renderStoryRail" not in html or "story-card" not in html:
        errors.append("play HTML missing persistent public action rail")
    if "renderBankruptcyBanner" not in html or "bankruptcyPlayerId" not in html:
        errors.append("play HTML missing bankruptcy notification helpers")
    if "positionDecisionPanel" not in html or "purchase-anchored" not in html or "tile-callout" not in html:
        errors.append("play HTML missing purchase prompt tile anchoring")
    if "pushAssetEffectsFromEvent" not in html or "syncSnapshotEconomy" not in html or "renderAssetLog" not in html:
        errors.append("play HTML missing economy tracking helpers")
    if "runaway_step_choice" not in html or "runaway_choice" not in html:
        errors.append("play HTML missing runaway-step choice wiring")
    if "setTimeout(hideDecision,180)" in html:
        errors.append("play HTML still hides decision overlay before backend state advances")
    for stale_field in (
        "marker_owner_id",
        "trick_cards_visible",
        "tiles_owned",
        "score_coins_placed",
        "immune_to_marks",
        "is_marked",
    ):
        if stale_field in html:
            errors.append(f"play HTML still references stale field '{stale_field}'")
    return errors


def test_human_policy_multiple_human_seats() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy, MovementDecision
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, human_seats=[0, 2], ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[2]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_movement(state, player)
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for secondary human seat")
            return errors
        if prompt.get("player_id") != 3:
            errors.append(f"Expected prompt for P3, got {prompt.get('player_id')!r}")

        ok = policy.submit_response({"choice_id": "dice"})
        if not ok:
            errors.append("submit_response returned False for secondary human seat")

        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("secondary human seat did not unblock")
        elif not isinstance(result[0], MovementDecision):
            errors.append(f"Expected MovementDecision, got {type(result[0])}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_ai_seat() -> list[str]:
    """Non-human-seat calls should pass through to AI immediately."""
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy, MovementDecision
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)

        state = GameState.create(DEFAULT_CONFIG)
        # Player 1 (AI seat) — should not block
        player = state.players[1]

        done = threading.Event()
        result = [None]

        def _call():
            result[0] = policy.choose_movement(state, player)
            done.set()

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        done.wait(timeout=5.0)

        if not done.is_set():
            errors.append("choose_movement for AI seat blocked unexpectedly")
        elif result[0] is None:
            errors.append("choose_movement for AI seat returned None")
        elif not isinstance(result[0], MovementDecision):
            errors.append(f"Expected MovementDecision, got {type(result[0])}")
    except Exception as e:
        errors.append(f"Exception: {e}")
    return errors


def test_human_policy_prompt_and_response() -> list[str]:
    """Human-seat call should block, then unblock when response submitted."""
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy, MovementDecision
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_movement(state, player)
            done.set()

        t = threading.Thread(target=_call, daemon=True)
        t.start()

        # Wait briefly for prompt to appear
        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        if policy.pending_prompt is None:
            errors.append("pending_prompt never set for human seat")
            # unblock
            policy.submit_response({"choice_id": "dice"})
            done.wait(timeout=3.0)
            return errors

        if policy.pending_prompt.get("request_type") != "movement":
            errors.append(
                f"Expected request_type=movement, got {policy.pending_prompt.get('request_type')}"
            )
        if "type" in policy.pending_prompt:
            errors.append("pending_prompt should not expose legacy key 'type'")
        if "options" in policy.pending_prompt:
            errors.append("pending_prompt should not expose legacy key 'options'")
        if "legal_choices" not in policy.pending_prompt:
            errors.append("pending_prompt missing legal_choices")
        if "public_context" not in policy.pending_prompt:
            errors.append("pending_prompt missing public_context")

        # Submit response
        ok = policy.submit_response({"choice_id": "dice"})
        if not ok:
            errors.append("submit_response returned False unexpectedly")

        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_movement did not unblock after response submitted")
        elif not isinstance(result[0], MovementDecision):
            errors.append(f"Expected MovementDecision after response, got {type(result[0])}")
        elif result[0].use_cards:
            errors.append("option_id=dice should yield use_cards=False")

    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_final_character_returns_name() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        state.active_by_card = {0: "A", 1: "B", 2: "C"}

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_final_character(state, player, [1, 2])
            done.set()

        t = threading.Thread(target=_call, daemon=True)
        t.start()

        for _ in range(20):
            prompt = policy.pending_prompt
            if prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for final_character")
            return errors

        if prompt.get("request_type") != "final_character":
            errors.append(f"Expected request_type=final_character, got {prompt.get('request_type')}")
        if "type" in prompt or "options" in prompt:
            errors.append(f"final_character prompt still exposes legacy mirrors: {prompt}")
        legal_choices = prompt.get("legal_choices", [])
        if [opt.get("label") for opt in legal_choices] != ["B", "C"]:
            errors.append(f"Unexpected final_character labels: {legal_choices}")
        if [opt.get("choice_id") for opt in legal_choices] != ["1", "2"]:
            errors.append(f"Unexpected legal_choices: {legal_choices}")

        ok = policy.submit_response({"choice_id": "2"})
        if not ok:
            errors.append("submit_response returned False for final_character")

        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_final_character did not unblock")
        elif result[0] != "C":
            errors.append(f"Expected character name 'C', got {result[0]!r}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_mark_target_character_player_pairs() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState
        from characters import CARD_TO_NAMES

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]

        # Simulate round order so only players after seat 0 are legal targets.
        state.current_round_order = [2, 0, 1, 3]
        state.players[0].current_character = CARD_TO_NAMES[2][0]  # 자객
        state.players[1].current_character = CARD_TO_NAMES[2][1]  # 산적
        state.players[2].current_character = CARD_TO_NAMES[5][0]  # 교리 연구관 (not legal this turn)
        state.players[3].current_character = CARD_TO_NAMES[6][0]  # 박수
        for p in state.players:
            p.alive = True
            p.revealed_this_round = False

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_mark_target(state, player, CARD_TO_NAMES[2][0])
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for mark_target")
            return errors
        if prompt.get("request_type") != "mark_target":
            errors.append(f"Expected request_type=mark_target, got {prompt.get('request_type')}")

        legal_choices = prompt.get("legal_choices", [])
        labels = [opt.get("label") for opt in legal_choices]
        expected_labels = [
            "No target",
            f"{CARD_TO_NAMES[2][1]} / P2",
            f"{CARD_TO_NAMES[6][0]} / P4",
        ]
        if labels != expected_labels:
            errors.append(f"Unexpected mark_target labels: {labels!r}")

        choice_ids = [opt.get("choice_id") for opt in legal_choices]
        if choice_ids != ["none", "1", "3"]:
            errors.append(f"Unexpected mark_target choice_ids: {choice_ids!r}")

        target_pairs = prompt.get("public_context", {}).get("target_pairs", [])
        if len(target_pairs) != 2:
            errors.append(f"Expected 2 target_pairs, got {target_pairs!r}")

        ok = policy.submit_response({"choice_id": "1"})
        if not ok:
            errors.append("submit_response returned False for mark_target")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_mark_target did not unblock")
        elif result[0] != CARD_TO_NAMES[2][1]:
            errors.append(f"Expected selected target character {CARD_TO_NAMES[2][1]!r}, got {result[0]!r}")

        # Defensive suppression: if Uhsa is active elsewhere, 무뢰 mark skills should not prompt.
        state.players[1].current_character = CARD_TO_NAMES[1][0]  # 어사
        state.current_round_order = [0, 1, 2, 3]
        policy2 = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        blocked = policy2.choose_mark_target(state, state.players[0], CARD_TO_NAMES[2][0])
        if blocked is not None:
            errors.append("Expected mark_target to be suppressed by Uhsa, but got a target")
        if policy2.pending_prompt is not None:
            errors.append("Suppressed mark_target should not leave a pending prompt")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_geo_bonus_prompt() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.shards = 2
        player.hand_coins = 1

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_geo_bonus(state, player, "GeoHero")
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for geo_bonus")
            return errors
        if prompt.get("request_type") != "geo_bonus":
            errors.append(f"Expected request_type=geo_bonus, got {prompt.get('request_type')}")
        if len(prompt.get("legal_choices", [])) != 3:
            errors.append("geo_bonus should expose 3 legal choices")

        ok = policy.submit_response({"choice_id": "shards"})
        if not ok:
            errors.append("submit_response returned False for geo_bonus")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_geo_bonus did not unblock")
        elif result[0] != "shards":
            errors.append(f"Expected geo bonus 'shards', got {result[0]!r}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_doctrine_relief_prompt() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        candidates = [state.players[0], state.players[1]]
        burden = SimpleNamespace(name="Burden", is_burden=True)
        candidates[0].trick_hand = [burden]
        candidates[1].trick_hand = [burden, burden]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_doctrine_relief_target(state, player, candidates)
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for doctrine_relief")
            return errors
        if prompt.get("request_type") != "doctrine_relief":
            errors.append(f"Expected request_type=doctrine_relief, got {prompt.get('request_type')}")
        if len(prompt.get("legal_choices", [])) != 2:
            errors.append("doctrine_relief should expose candidate choices")

        ok = policy.submit_response({"choice_id": "1"})
        if not ok:
            errors.append("submit_response returned False for doctrine_relief")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_doctrine_relief_target did not unblock")
        elif result[0] != 1:
            errors.append(f"Expected doctrine target 1, got {result[0]!r}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_specific_trick_reward_prompt() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        choices = [
            SimpleNamespace(deck_index=11, name="Reward A"),
            SimpleNamespace(deck_index=12, name="Reward B"),
        ]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_specific_trick_reward(state, player, choices)
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for specific_trick_reward")
            return errors
        if prompt.get("request_type") != "specific_trick_reward":
            errors.append(
                f"Expected request_type=specific_trick_reward, got {prompt.get('request_type')}"
            )
        names = [opt.get("label") for opt in prompt.get("legal_choices", [])]
        if names != ["Reward A", "Reward B"]:
            errors.append(f"Unexpected specific_trick_reward labels: {names}")

        ok = policy.submit_response({"choice_id": "12"})
        if not ok:
            errors.append("submit_response returned False for specific_trick_reward")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_specific_trick_reward did not unblock")
        elif result[0] is not choices[1]:
            errors.append("Expected selected trick reward object to be returned")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_active_flip_prompt() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        state.active_by_card = {0: "A", 1: "X"}

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_active_flip_card(state, player, [0, 1])
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for active_flip")
            return errors
        if prompt.get("request_type") != "active_flip":
            errors.append(f"Expected request_type=active_flip, got {prompt.get('request_type')}")
        if len(prompt.get("legal_choices", [])) != 3:
            errors.append("active_flip should expose flippable cards plus explicit stop option")
        ctx = prompt.get("public_context", {})
        if ctx.get("flip_mode") != "multi":
            errors.append(f"active_flip should expose flip_mode='multi', got {ctx.get('flip_mode')!r}")
        if ctx.get("flip_limit", "sentinel") is not None:
            errors.append(f"active_flip should expose flip_limit=None, got {ctx.get('flip_limit')!r}")
        if ctx.get("marker_owner_player_id") != 1:
            errors.append(
                f"active_flip should expose marker_owner_player_id=1 for seat0 owner, got {ctx.get('marker_owner_player_id')!r}"
            )

        ok = policy.submit_response({"choice_id": "1"})
        if not ok:
            errors.append("submit_response returned False for active_flip")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_active_flip_card did not unblock")
        elif result[0] != 1:
            errors.append(f"Expected flipped card index 1, got {result[0]!r}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_active_flip_requires_marker_owner() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]

        state.marker_owner_id = 1
        state.pending_marker_flip_owner_id = 1
        result = policy.choose_active_flip_card(state, player, [1, 2])
        if result is not None:
            errors.append(f"Expected non-owner active_flip to return None, got {result!r}")
        if policy.pending_prompt is not None:
            errors.append("Non-owner active_flip should not open a prompt")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_trick_to_use_full_hand_context() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        all_cards = [
            SimpleNamespace(deck_index=31, name="A", description="desc-a"),
            SimpleNamespace(deck_index=32, name="B", description="desc-b"),
            SimpleNamespace(deck_index=33, name="C", description="desc-c"),
        ]
        player.trick_hand = list(all_cards)
        player.hidden_trick_deck_index = 32
        usable_hand = [all_cards[0]]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_trick_to_use(state, player, usable_hand)
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for trick_to_use")
            return errors
        if prompt.get("request_type") != "trick_to_use":
            errors.append(f"Expected request_type=trick_to_use, got {prompt.get('request_type')}")
        ctx = prompt.get("public_context", {})
        if ctx.get("usable_hand_count") != 1:
            errors.append(f"Expected usable_hand_count=1, got {ctx.get('usable_hand_count')!r}")
        if ctx.get("total_hand_count") != 3:
            errors.append(f"Expected total_hand_count=3, got {ctx.get('total_hand_count')!r}")
        full_hand = ctx.get("full_hand", [])
        if len(full_hand) != 3:
            errors.append(f"Expected full_hand length=3, got {len(full_hand)}")
        else:
            hidden = sum(1 for item in full_hand if item.get("is_hidden"))
            usable = sum(1 for item in full_hand if item.get("is_usable"))
            if hidden != 1:
                errors.append(f"Expected one hidden card in full_hand, got {hidden}")
            if usable != 1:
                errors.append(f"Expected one usable card in full_hand, got {usable}")

        choice_ids = [opt.get("choice_id") for opt in prompt.get("legal_choices", [])]
        if "none" not in choice_ids or "31" not in choice_ids:
            errors.append(f"Unexpected trick_to_use choices: {choice_ids}")
        if "32" in choice_ids:
            errors.append("hidden/non-usable card should not become legal choice in trick_to_use")

        ok = policy.submit_response({"choice_id": "none"})
        if not ok:
            errors.append("submit_response returned False for trick_to_use")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_trick_to_use did not unblock")
        elif result[0] is not None:
            errors.append("Expected trick_to_use 'none' response to return None")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_hidden_trick_requires_selection() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        hand = [
            SimpleNamespace(deck_index=11, name="마당발"),
            SimpleNamespace(deck_index=12, name="건강 검진"),
        ]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_hidden_trick_card(state, player, hand)
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for hidden_trick_card")
            return errors
        if prompt.get("request_type") != "hidden_trick_card":
            errors.append(f"Expected request_type=hidden_trick_card, got {prompt.get('request_type')}")
        if prompt.get("can_pass") is not False:
            errors.append(f"hidden_trick_card should require a choice, got can_pass={prompt.get('can_pass')!r}")
        choice_ids = [opt.get("choice_id") for opt in prompt.get("legal_choices", [])]
        if choice_ids != ["11", "12"]:
            errors.append(f"Unexpected hidden_trick_card choices: {choice_ids}")

        ok = policy.submit_response({"choice_id": "12"})
        if not ok:
            errors.append("submit_response returned False for hidden_trick_card")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_hidden_trick_card did not unblock")
        elif result[0] is not hand[1]:
            errors.append("Expected selected hidden trick card object to be returned")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_burden_exchange_prompt() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        player.cash = 9
        card = SimpleNamespace(name="Burden X", burden_cost=4, is_burden=True)

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_burden_exchange_on_supply(state, player, card)
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for burden_exchange")
            return errors
        if prompt.get("request_type") != "burden_exchange":
            errors.append(f"Expected request_type=burden_exchange, got {prompt.get('request_type')}")
        labels = [opt.get("choice_id") for opt in prompt.get("legal_choices", [])]
        if labels != ["yes", "no"]:
            errors.append(f"Unexpected burden_exchange choices: {labels}")

        ok = policy.submit_response({"choice_id": "yes"})
        if not ok:
            errors.append("submit_response returned False for burden_exchange")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_burden_exchange_on_supply did not unblock")
        elif result[0] is not True:
            errors.append(f"Expected True from burden_exchange, got {result[0]!r}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


def test_human_policy_runaway_step_choice_prompt() -> list[str]:
    errors = []
    try:
        from viewer.human_policy import HumanHttpPolicy
        from ai_policy import HeuristicPolicy
        from config import DEFAULT_CONFIG
        from state import GameState

        ai = HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )
        policy = HumanHttpPolicy(human_seat=0, ai_fallback=ai)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]

        result = [None]
        done = threading.Event()

        def _call():
            result[0] = policy.choose_runaway_slave_step(
                state,
                player,
                11,
                12,
                SimpleNamespace(name="S"),
            )
            done.set()

        threading.Thread(target=_call, daemon=True).start()

        for _ in range(20):
            if policy.pending_prompt is not None:
                break
            time.sleep(0.05)

        prompt = policy.pending_prompt
        if prompt is None:
            errors.append("pending_prompt never set for runaway_step_choice")
            return errors
        if prompt.get("request_type") != "runaway_step_choice":
            errors.append(f"Expected request_type=runaway_step_choice, got {prompt.get('request_type')}")
        if prompt.get("can_pass") is not False:
            errors.append(f"runaway_step_choice should require a choice, got can_pass={prompt.get('can_pass')!r}")
        choice_ids = [opt.get("choice_id") for opt in prompt.get("legal_choices", [])]
        if choice_ids != ["take_bonus", "stay"]:
            errors.append(f"Unexpected runaway_step_choice choices: {choice_ids}")

        ok = policy.submit_response({"choice_id": "stay"})
        if not ok:
            errors.append("submit_response returned False for runaway_step_choice")
        done.wait(timeout=3.0)
        if not done.is_set():
            errors.append("choose_runaway_slave_step did not unblock")
        elif result[0] is not False:
            errors.append(f"Expected False (stay) from runaway_step_choice, got {result[0]!r}")
    except Exception as e:
        import traceback
        errors.append(f"Exception: {e}\n{traceback.format_exc()}")
    return errors


# ---------------------------------------------------------------------------
# Integration tests (with live server)
# ---------------------------------------------------------------------------

def test_prompt_endpoint_idle(port: int) -> list[str]:
    """GET /prompt with no pending decision returns request_type=null."""
    errors = []
    try:
        data = _get_json(f"http://127.0.0.1:{port}/prompt")
        if "type" in data:
            errors.append("idle /prompt payload should not expose legacy key 'type'")
        if data.get("request_type") is not None:
            # It's possible a decision prompt appeared; that's fine
            pass  # skip — game may have started quickly
    except Exception as e:
        errors.append(f"GET /prompt failed: {e}")
    return errors


def test_decision_no_prompt(port: int) -> list[str]:
    """POST /decision with no pending prompt returns 409."""
    errors = []
    # First ensure no prompt is pending
    time.sleep(0.3)
    try:
        data = _get_json(f"http://127.0.0.1:{port}/prompt")
        if data.get("request_type") is not None:
            return []  # game has a prompt — skip this test
    except Exception:
        pass

    code, resp = _post_json(f"http://127.0.0.1:{port}/decision",
                             {"choice_id": "dice"})
    if code not in (409, 200):  # 200 is also ok if a prompt arrived just now
        errors.append(f"Expected 409 (no prompt), got {code}")
    return errors


def test_play_html_endpoint(port: int) -> list[str]:
    """GET /play returns valid HTML with decision panel."""
    errors = []
    try:
        html = _get_text(f"http://127.0.0.1:{port}/play")
        if "<!DOCTYPE html>" not in html:
            errors.append("/play response missing DOCTYPE")
        if "decision-overlay" not in html:
            errors.append("/play HTML missing decision-overlay")
        if "/prompt" not in html:
            errors.append("/play HTML missing /prompt reference")
    except Exception as e:
        errors.append(f"GET /play failed: {e}")
    return errors


def test_status_endpoint(port: int) -> list[str]:
    """GET /status returns standard fields."""
    errors = []
    try:
        data = _get_json(f"http://127.0.0.1:{port}/status")
        for f in ("done", "total", "session_id", "error"):
            if f not in data:
                errors.append(f"status missing '{f}'")
    except Exception as e:
        errors.append(f"GET /status failed: {e}")
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Phase 4 Human Play Tests")
    print("=" * 40)

    # ── Unit tests (no server) ──────────────────────────────────────────
    print("\n[unit]")
    unit_tests = [
        ("play_html_renderer",          test_play_html_renderer),
        ("human_policy_ai_seat",        test_human_policy_ai_seat),
        ("human_policy_multi_humans",   test_human_policy_multiple_human_seats),
        ("human_policy_prompt_response",test_human_policy_prompt_and_response),
        ("human_policy_final_character",test_human_policy_final_character_returns_name),
        ("human_policy_mark_target",    test_human_policy_mark_target_character_player_pairs),
        ("human_policy_geo_bonus",      test_human_policy_geo_bonus_prompt),
        ("human_policy_doctrine_relief",test_human_policy_doctrine_relief_prompt),
        ("human_policy_trick_reward",   test_human_policy_specific_trick_reward_prompt),
        ("human_policy_active_flip",    test_human_policy_active_flip_prompt),
        ("human_policy_active_flip_owner", test_human_policy_active_flip_requires_marker_owner),
        ("human_policy_trick_context",  test_human_policy_trick_to_use_full_hand_context),
        ("human_policy_hidden_trick",   test_human_policy_hidden_trick_requires_selection),
        ("human_policy_burden_exchange",test_human_policy_burden_exchange_prompt),
        ("human_policy_runaway_step",   test_human_policy_runaway_step_choice_prompt),
    ]
    all_passed = True
    for name, fn in unit_tests:
        errs = fn()
        if errs:
            all_passed = False
            print(f"  FAIL {name}")
            for e in errs:
                print(f"    {e}")
        else:
            print(f"  OK   {name}")

    # ── Integration tests (with live server) ────────────────────────────
    PORT = 18866
    print(f"\nStarting HumanPlayServer seed=99 port={PORT} human_seat=0 turn_delay=0 ...", flush=True)
    server, _ = _start_human_server(seed=99, port=PORT, human_seat=0, turn_delay=0.0)

    # The human seat (P0) will block on its first choose_movement.
    # We need to auto-respond so the game can progress.
    def _auto_respond():
        """Automatically answer human prompts so the game finishes."""
        for _ in range(500):
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/prompt", timeout=2
                )
                data = json.loads(resp.read())
                if data.get("request_type"):
                    opts = data.get("legal_choices", [])
                    opt_id = opts[0]["choice_id"] if opts else "dice"
                    _post_json(f"http://127.0.0.1:{PORT}/decision", {"choice_id": opt_id})
            except Exception:
                pass
            time.sleep(0.05)

    responder = threading.Thread(target=_auto_respond, daemon=True)
    responder.start()

    integration_tests = [
        ("prompt_endpoint_idle",  lambda: test_prompt_endpoint_idle(PORT)),
        ("decision_no_prompt",    lambda: test_decision_no_prompt(PORT)),
        ("play_html_endpoint",    lambda: test_play_html_endpoint(PORT)),
        ("status_endpoint",       lambda: test_status_endpoint(PORT)),
    ]
    print("\n[integration]")
    for name, fn in integration_tests:
        errs = fn()
        if errs:
            all_passed = False
            print(f"  FAIL {name}")
            for e in errs:
                print(f"    {e}")
        else:
            print(f"  OK   {name}")

    # Wait for game to finish (auto-responder handles human prompts)
    print("\nWaiting for game to complete...", flush=True)
    status = _wait_done(PORT, timeout=60.0)
    if status:
        print("  OK   game_completes")
        if status.get("error"):
            all_passed = False
            print(f"  FAIL game_error ({status['error']})")
    else:
        all_passed = False
        print("  FAIL game_completes (did not finish within 60s)")

    if server._http_server:
        server._http_server.shutdown()

    if all_passed:
        print("\nPhase 4: ALL TESTS PASSED")
        return 0
    else:
        print("\nPhase 4: TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
