"""Phase 4 — Human Play Server.

Extends LiveGameServer with two extra endpoints:

    GET  /prompt    → JSON: current decision prompt, or {"type": null} if idle
    POST /decision  → JSON: {"option_id": "..."}, returns 200/400
    GET  /play      → serves the extended play HTML page

The game uses HumanHttpPolicy for one designated player seat; the rest of
the seats are controlled by HeuristicPolicy.

Usage:
    server = HumanPlayServer(seed=42, port=8765, human_seat=0)
    server.start()   # blocks; Ctrl-C to stop
"""
from __future__ import annotations

import json
import random
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from viewer.live_server import LiveGameServer, _SpeedControlledPolicy


class HumanPlayServer(LiveGameServer):
    """LiveGameServer extended with human-input endpoints.

    Parameters
    ----------
    human_seat:
        player_id of the human player (0-based, default 0).
    All other parameters are forwarded to LiveGameServer.
    """

    def __init__(
        self,
        seed: int = 42,
        port: int = 8765,
        turn_delay: float = 0.10,
        host: str = "127.0.0.1",
        human_seat: int = 0,
    ) -> None:
        super().__init__(seed=seed, port=port, turn_delay=turn_delay, host=host)
        self.human_seat = human_seat
        self._human_policy: Any = None  # set in _run_game before engine starts

    # ------------------------------------------------------------------
    # Override game thread — inject HumanHttpPolicy
    # ------------------------------------------------------------------

    def _run_game(self) -> None:
        try:
            from engine import GameEngine
            from config import DEFAULT_CONFIG
            from ai_policy import HeuristicPolicy
            from viewer.human_policy import HumanHttpPolicy

            ai_fallback = HeuristicPolicy(
                character_policy_mode="heuristic_v1",
                lap_policy_mode="heuristic_v1",
            )
            human_policy = HumanHttpPolicy(
                human_seat=self.human_seat,
                ai_fallback=ai_fallback,
            )
            self._human_policy = human_policy

            policy = _SpeedControlledPolicy(human_policy, self.turn_delay)
            engine = GameEngine(
                DEFAULT_CONFIG,
                policy,
                rng=random.Random(self.seed),
                event_stream=self._stream,
            )
            engine.run()
        except Exception as exc:
            import traceback
            print(f"[human-game] ERROR: {exc}", flush=True)
            traceback.print_exc()
        finally:
            self._done.set()

    # ------------------------------------------------------------------
    # Override handler factory — add /prompt, /decision, /play
    # ------------------------------------------------------------------

    def _make_handler(self) -> type:
        server_ref = self
        base_handler = super()._make_handler()

        class _HumanHandler(base_handler):  # type: ignore[valid-type,misc]

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/prompt":
                    self._serve_prompt()
                elif path == "/play":
                    self._serve_play()
                elif path in ("/", ""):
                    self._redirect("/play")
                else:
                    super().do_GET()

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/decision":
                    self._handle_decision()
                else:
                    self.send_response(404)
                    self.end_headers()

            # ── route handlers ─────────────────────────────────────────

            def _serve_prompt(self) -> None:
                policy = server_ref._human_policy
                if policy is None:
                    payload = {"type": None}
                else:
                    prompt = policy.pending_prompt
                    payload = prompt if prompt is not None else {"type": None}
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def _handle_decision(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                try:
                    raw = self.rfile.read(length)
                    data = json.loads(raw)
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"bad json")
                    return

                policy = server_ref._human_policy
                if policy is None:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b"game not started")
                    return

                accepted = policy.submit_response(data)
                if accepted:
                    body = json.dumps({"ok": True}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    body = json.dumps({"ok": False, "error": "no pending prompt"}).encode()
                    self.send_response(409)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def _serve_play(self) -> None:
                from viewer.renderers.play_html import render_play_html
                session_id = (
                    server_ref._stream._events[0].session_id
                    if server_ref._stream._events
                    else "pending"
                )
                html = render_play_html(
                    session_id=session_id,
                    seed=server_ref.seed,
                    human_seat=server_ref.human_seat,
                    poll_interval_ms=200,
                )
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return _HumanHandler
