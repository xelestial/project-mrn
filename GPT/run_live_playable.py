from __future__ import annotations

import argparse
import functools
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config import DEFAULT_CONFIG
from viewer.human_adapter import CLIResponseProvider
from viewer.live_runtime import write_live_viewer_files
from viewer.playable_runtime import run_playable_seed
from viewer.prompting import QueuePromptResponder, RuntimePromptResponse


def _parse_prompt_response_payload(payload: dict[str, Any]) -> RuntimePromptResponse:
    prompt_id = payload.get("prompt_id")
    choice_key = payload.get("choice_key")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise ValueError("prompt_id must be a non-empty string")
    if choice_key is not None and not isinstance(choice_key, str):
        raise ValueError("choice_key must be a string or null")
    return RuntimePromptResponse(prompt_id=prompt_id, choice_key=choice_key)


def _resolve_response_mode(raw: str, *, serve: bool) -> str:
    if raw == "auto":
        return "web" if serve else "cli"
    if raw == "web" and not serve:
        raise ValueError("--response-mode web requires --serve")
    return raw


def _serve_directory(directory: Path, port: int, *, responder: QueuePromptResponder | None) -> ThreadingHTTPServer:
    class PlayableHandler(SimpleHTTPRequestHandler):
        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/api/prompt-response":
                self.send_error(404, "Unsupported endpoint")
                return
            if responder is None:
                self._send_json(503, {"ok": False, "error": "web response provider is not enabled"})
                return
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(content_length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"ok": False, "error": "invalid JSON body"})
                return
            try:
                parsed = _parse_prompt_response_payload(payload)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            responder.submit_response(parsed)
            self._send_json(200, {"ok": True})

    handler = functools.partial(PlayableHandler, directory=str(directory))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def _parse_humans(raw: str) -> set[int]:
    result: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        seat = int(token)
        if seat < 1 or seat > DEFAULT_CONFIG.player_count:
            raise ValueError(f"seat out of range: {seat}")
        result.add(seat)
    if not result:
        raise ValueError("at least one human seat is required")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a live playable game with CLI-backed human prompts.")
    parser.add_argument("--run-seed", type=int, required=True, metavar="SEED")
    parser.add_argument("--humans", default="1", help="Comma-separated 1-based human seats, e.g. 1 or 1,3")
    parser.add_argument("--out-dir", default="GPT/_codex_runs/phase4_playable", metavar="DIR")
    parser.add_argument("--serve", action="store_true", help="Serve the output directory over local HTTP")
    parser.add_argument("--port", type=int, default=8765, help="Port for --serve (default: 8765)")
    parser.add_argument(
        "--response-mode",
        choices=("auto", "cli", "web"),
        default="auto",
        help="Human input backend: auto, cli, web (default: auto)",
    )
    args = parser.parse_args(argv)

    humans = _parse_humans(args.humans)
    out_dir = Path(args.out_dir)
    write_live_viewer_files(out_dir)
    try:
        response_mode = _resolve_response_mode(args.response_mode, serve=args.serve)
    except ValueError as exc:
        parser.error(str(exc))

    if response_mode == "web":
        response_provider = QueuePromptResponder()
        print("Response mode: web (submit choices from index.html prompt panel).")
    else:
        response_provider = CLIResponseProvider()
        print("Response mode: cli (terminal input).")

    server: ThreadingHTTPServer | None = None
    if args.serve:
        server = _serve_directory(
            out_dir,
            args.port,
            responder=response_provider if isinstance(response_provider, QueuePromptResponder) else None,
        )
        print(f"Serving {out_dir} at http://127.0.0.1:{args.port}/index.html")
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

    print(f"Running live playable seed={args.run_seed} humans={sorted(humans)} ...")
    event_stream, _prompt_channel = run_playable_seed(
        seed=args.run_seed,
        out_dir=out_dir,
        human_players=humans,
        response_provider=response_provider,
    )
    summary = event_stream.summary()
    print(f"Completed ({summary['total_events']} events)")
    print(f"  state : {out_dir / 'live_state.json'}")
    print(f"  prompt: {out_dir / 'prompt_state.json'}")
    print(f"  events: {out_dir / 'events.jsonl'}")
    print(f"  html  : {out_dir / 'index.html'}")

    if not args.serve:
        return 0

    print("Game finished. Local server will stay open until Ctrl+C.")
    try:
        while True:
            import time

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()
        return 0


if __name__ == "__main__":
    sys.exit(main())
