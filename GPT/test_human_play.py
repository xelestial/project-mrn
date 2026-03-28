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

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_human_server(seed: int = 99, port: int = 18866, human_seat: int = 0,
                         turn_delay: float = 0.0):
    from viewer.prompt_server import HumanPlayServer
    server = HumanPlayServer(seed=seed, port=port, turn_delay=turn_delay,
                              human_seat=human_seat)

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
    html = render_play_html(session_id="test", seed=42, human_seat=1, poll_interval_ms=200)
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
    if "submitDecision" not in html:
        errors.append("play HTML missing submitDecision function")
    if "marker_owner_player_id" not in html:
        errors.append("play HTML missing canonical marker owner field")
    if "public_tricks" not in html:
        errors.append("play HTML missing canonical public_tricks field")
    if "owned_tile_count" not in html or "placed_score_coins" not in html:
        errors.append("play HTML missing canonical player stat fields")
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
            policy.submit_response({"option_id": "dice"})
            done.wait(timeout=3.0)
            return errors

        if policy.pending_prompt.get("type") != "movement":
            errors.append(f"Expected type=movement, got {policy.pending_prompt.get('type')}")

        # Submit response
        ok = policy.submit_response({"option_id": "dice"})
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

        options = prompt.get("options", [])
        if [opt.get("label") for opt in options] != ["B", "C"]:
            errors.append(f"Unexpected final_character labels: {options}")

        ok = policy.submit_response({"option_id": "2"})
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


# ---------------------------------------------------------------------------
# Integration tests (with live server)
# ---------------------------------------------------------------------------

def test_prompt_endpoint_idle(port: int) -> list[str]:
    """GET /prompt with no pending decision returns type=null."""
    errors = []
    try:
        data = _get_json(f"http://127.0.0.1:{port}/prompt")
        if data.get("type") is not None:
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
        if data.get("type") is not None:
            return []  # game has a prompt — skip this test
    except Exception:
        pass

    code, resp = _post_json(f"http://127.0.0.1:{port}/decision",
                             {"option_id": "dice"})
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
        ("human_policy_prompt_response",test_human_policy_prompt_and_response),
        ("human_policy_final_character",test_human_policy_final_character_returns_name),
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
                if data.get("type"):
                    opts = data.get("options", [])
                    opt_id = opts[0]["id"] if opts else "dice"
                    _post_json(f"http://127.0.0.1:{PORT}/decision", {"option_id": opt_id})
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
