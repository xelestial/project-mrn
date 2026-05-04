"""Phase 3 — Live Spectator CLI.

Runs a game and opens a local HTTP server so you can watch it in a browser.

Usage:
    python run_live_spectator.py                        # seed=42, port=8765
    python run_live_spectator.py --seed 137             # different seed
    python run_live_spectator.py --turn-delay 0.3       # slower (0.3s per turn)
    python run_live_spectator.py --turn-delay 0         # full speed
    python run_live_spectator.py --port 9000            # different port
    python run_live_spectator.py --no-browser           # don't auto-open browser

Press Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live game spectator — watch a simulation in your browser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument(
        "--turn-delay", type=float, default=0.15, metavar="SECS",
        help="Pause before each turn's movement (default: 0.15s). 0 = full speed.",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Do not automatically open the browser",
    )
    args = parser.parse_args(argv)

    from viewer.live_server import LiveGameServer

    server = LiveGameServer(
        seed=args.seed,
        port=args.port,
        turn_delay=args.turn_delay,
    )

    url = f"http://127.0.0.1:{args.port}/viewer"
    if not args.no_browser:
        import threading
        def _open() -> None:
            import time
            time.sleep(0.4)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    server.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
