"""Phase 3 — Live Spectator Server.

Runs the game engine in a background thread and exposes a lightweight HTTP
server so a browser can poll for events in real time.

Endpoints:
    GET /                   → redirects to /viewer
    GET /viewer             → serves the self-contained live HTML page
    GET /events?since=N     → JSON: {"events": [...], "done": bool, "total": int}
    GET /status             → JSON: {"done": bool, "total": int, "session_id": str}

Usage:
    server = LiveGameServer(seed=42, port=8765, turn_delay=0.15)
    server.start()          # blocks; Ctrl-C to stop
"""
from __future__ import annotations

import json
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from viewer.stream import VisEventStream


# ---------------------------------------------------------------------------
# Speed-controlled policy wrapper
# ---------------------------------------------------------------------------

class _SpeedControlledPolicy:
    """Wraps any policy to inject a per-turn delay before movement resolution.

    The delay is inserted at ``choose_movement`` time so it straddles the
    trick-phase → movement boundary, giving the browser a chance to render
    the trick-phase events before the pawn moves.
    """

    def __init__(self, inner: Any, turn_delay: float) -> None:
        self._inner = inner
        self._turn_delay = turn_delay

    def choose_movement(self, state: Any, player: Any) -> Any:
        if self._turn_delay > 0:
            time.sleep(self._turn_delay)
        return self._inner.choose_movement(state, player)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# LiveGameServer
# ---------------------------------------------------------------------------

class LiveGameServer:
    """HTTP server + background engine thread for live spectating.

    Parameters
    ----------
    seed:
        RNG seed for the game.
    port:
        Local TCP port to listen on (default 8765).
    turn_delay:
        Seconds to pause before each movement resolution (default 0.15).
        Set to 0 to run at full speed.
    host:
        Bind address (default "127.0.0.1").
    """

    def __init__(
        self,
        seed: int = 42,
        port: int = 8765,
        turn_delay: float = 0.15,
        host: str = "127.0.0.1",
    ) -> None:
        self.seed = seed
        self.port = port
        self.turn_delay = turn_delay
        self.host = host

        self._stream = VisEventStream()
        self._done = threading.Event()
        self._game_error: str | None = None
        self._game_thread: threading.Thread | None = None
        self._http_server: ThreadingHTTPServer | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the game thread and HTTP server (blocks until Ctrl-C)."""
        self._game_thread = threading.Thread(
            target=self._run_game, daemon=True, name="live-game"
        )
        self._game_thread.start()

        handler = self._make_handler()
        self._http_server = ThreadingHTTPServer((self.host, self.port), handler)
        url = f"http://{self.host}:{self.port}/viewer"
        print(f"Live spectator: {url}")
        print(f"Seed: {self.seed}  turn_delay: {self.turn_delay}s  port: {self.port}")
        print("Press Ctrl-C to stop.")
        try:
            self._http_server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._http_server.shutdown()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_game(self) -> None:
        try:
            from engine import GameEngine
            from config import DEFAULT_CONFIG
            from ai_policy import HeuristicPolicy

            inner_policy = HeuristicPolicy(
                character_policy_mode="heuristic_v1",
                lap_policy_mode="heuristic_v1",
            )
            policy = _SpeedControlledPolicy(inner_policy, self.turn_delay)
            engine = GameEngine(
                DEFAULT_CONFIG,
                policy,
                rng=random.Random(self.seed),
                event_stream=self._stream,
            )
            engine.run()
        except Exception as exc:
            self._game_error = repr(exc)
            print(f"[live-game] ERROR: {exc}", flush=True)
        finally:
            self._done.set()

    def _make_handler(self) -> type:
        """Return a request handler class bound to this server instance."""
        server_ref = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
                pass

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                if path in ("/", ""):
                    self._redirect("/viewer")
                elif path == "/viewer":
                    self._serve_viewer()
                elif path == "/events":
                    self._serve_events(parsed.query)
                elif path == "/status":
                    self._serve_status()
                else:
                    self.send_response(404)
                    self.end_headers()

            # ── route handlers ──────────────────────────────────────────

            def _redirect(self, to: str) -> None:
                self.send_response(302)
                self.send_header("Location", to)
                self.end_headers()

            def _serve_viewer(self) -> None:
                from viewer.renderers.live_html import render_live_html
                html = render_live_html(
                    session_id=server_ref._stream._events[0].session_id
                    if server_ref._stream._events else "pending",
                    seed=server_ref.seed,
                    poll_interval_ms=300,
                )
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _serve_events(self, query: str) -> None:
                params = parse_qs(query)
                since = int(params.get("since", ["0"])[0])
                events = server_ref._stream.events  # snapshot
                # Events with step_index >= since
                new_events = [
                    e.to_dict() for e in events
                    if e.step_index >= since
                ]
                payload = {
                    "events": new_events,
                    "done": server_ref._done.is_set(),
                    "total": len(events),
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def _serve_status(self) -> None:
                events = server_ref._stream.events
                session_id = events[0].session_id if events else ""
                payload = {
                    "done": server_ref._done.is_set(),
                    "total": len(events),
                    "session_id": session_id,
                    "error": server_ref._game_error,
                }
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return _Handler
