"""Phase 4 — Human Play CLI.

Runs a game with one human-controlled player seat.  The human makes
decisions through a browser UI that polls the local HTTP server.

Usage:
    python run_human_play.py                          # human=P0, seed=42, port=8765
    python run_human_play.py --human-seat 1          # control P1 instead
    python run_human_play.py --seed 137              # different seed
    python run_human_play.py --turn-delay 0.2        # slower AI turns
    python run_human_play.py --port 9000             # different port
    python run_human_play.py --no-browser            # don't auto-open browser

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
        description="Human play — control one seat in your browser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument(
        "--human-seat", type=int, default=0, metavar="SEAT",
        help="Player ID to control (0-based, default: 0)",
    )
    parser.add_argument(
        "--turn-delay", type=float, default=0.10, metavar="SECS",
        help="Pause before AI movement resolution (default: 0.10s). 0 = full speed.",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Do not automatically open the browser",
    )
    args = parser.parse_args(argv)

    from viewer.prompt_server import HumanPlayServer

    server = HumanPlayServer(
        seed=args.seed,
        port=args.port,
        turn_delay=args.turn_delay,
        human_seat=args.human_seat,
    )

    url = f"http://127.0.0.1:{args.port}/play"
    print(f"Human Play: {url}")
    print(f"Seed: {args.seed}  human_seat: P{args.human_seat}  port: {args.port}")
    print("You control P{} — watch the Decision Panel for prompts.".format(args.human_seat))
    print("Press Ctrl-C to stop.")

    if not args.no_browser:
        import threading
        import time
        def _open() -> None:
            time.sleep(0.4)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    server.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
