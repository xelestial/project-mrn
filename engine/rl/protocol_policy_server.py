from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from rl.train_policy import predict_action


MAX_REQUEST_BYTES = 2 * 1024 * 1024


def build_protocol_replay_row_from_policy_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    player_id = _int_or_none(payload.get("player_id"))
    if player_id is None:
        raise ValueError("policy request requires numeric player_id")

    prompt = _record(payload.get("prompt"))
    request_type = _string(prompt.get("request_type")) or "unknown"
    prompt_public_context = _prompt_public_context(payload)
    active_flip_already_flipped_count = _active_flip_already_flipped_count(payload)
    runtime = _record(payload.get("runtime"))
    player_summary = _record(payload.get("player_summary"))
    legal_actions = _legal_actions_from_request(payload.get("legal_choices"))
    if not legal_actions:
        raise ValueError("policy request did not include legal choices")

    observation = {
        "commit_seq": _int_or_none(payload.get("commit_seq")),
        "round_index": _int_or_none(runtime.get("round_index")),
        "turn_index": _int_or_none(runtime.get("turn_index")),
        "player_id": player_id,
        "cash": _number_or_none(player_summary.get("cash")),
        "score": _number_or_none(player_summary.get("score")),
        "total_score": _number_or_none(player_summary.get("total_score")),
        "shards": _number_or_none(player_summary.get("shards")),
        "owned_tile_count": _number_or_none(player_summary.get("owned_tile_count")),
        "position": _number_or_none(player_summary.get("position")),
        "alive": _bool_or_none(player_summary.get("alive")),
        "character": _string(player_summary.get("character")),
    }
    if request_type == "active_flip":
        observation.update(
            {
                "active_flip_already_flipped_count": active_flip_already_flipped_count,
                "active_flip_finish_once": _string(prompt_public_context.get("flip_submit_mode")) == "finish_once",
            }
        )

    return {
        "game_id": _string(payload.get("session_id")) or "",
        "step": None,
        "player_id": player_id,
        "decision_key": request_type,
        "observation": observation,
        "legal_actions": legal_actions,
        "chosen_action_id": "",
        "action_space_source": "full_stack_protocol_http",
        "reward": {"total": 0.0, "components": {}},
        "sample_weight": 1.0,
        "done": False,
        "outcome": {},
    }


def decide_protocol_policy(*, model_dir: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    row = build_protocol_replay_row_from_policy_request(payload)
    prediction = predict_action(model_dir=model_dir, row=row)
    choice_id = _string(prediction.get("action_id"))
    legal_ids = {str(action["action_id"]) for action in row["legal_actions"]}
    if not choice_id:
        raise ValueError("policy did not return an action_id")
    if choice_id not in legal_ids:
        raise ValueError(f"policy predicted illegal action_id {choice_id!r}; legal={sorted(legal_ids)}")
    if (
        _string(_record(payload.get("prompt")).get("request_type")) == "active_flip"
        and _active_flip_already_flipped_count(payload) > 0
    ):
        if "none" in legal_ids:
            choice_id = "none"
    result: dict[str, Any] = {
        "choice_id": choice_id,
        "scores": prediction.get("scores") if isinstance(prediction.get("scores"), list) else [],
    }
    choice_payload = _choice_payload_for_request(payload, choice_id)
    if choice_payload is not None:
        result["choice_payload"] = choice_payload
    return result


def run_server(*, model_dir: str | Path, host: str, port: int) -> None:
    model_path = Path(model_dir)
    _prewarm_model(model_path)
    handler = _handler_class(model_path)
    server = ThreadingHTTPServer((host, int(port)), handler)
    endpoint = f"http://{server.server_address[0]}:{server.server_address[1]}/decide"
    print(json.dumps({"event": "protocol_policy_server_ready", "endpoint": endpoint}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _handler_class(model_dir: Path) -> type[BaseHTTPRequestHandler]:
    class ProtocolPolicyHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self._write_json(200, {"ok": True})
                return
            self._write_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path != "/decide":
                self._write_json(404, {"error": "not_found"})
                return
            try:
                payload = self._read_json_body()
                result = decide_protocol_policy(model_dir=model_dir, payload=payload)
            except ValueError as exc:
                self._write_json(400, {"error": str(exc)})
                return
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._write_json(500, {"error": repr(exc)})
                return
            self._write_json(200, result)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json_body(self) -> Mapping[str, Any]:
            raw_length = self.headers.get("content-length")
            if raw_length is None:
                raise ValueError("missing content-length")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("invalid content-length") from exc
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body is too large")
            body = self.rfile.read(length)
            try:
                parsed = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("request body is not valid JSON") from exc
            if not isinstance(parsed, dict):
                raise ValueError("request body must be a JSON object")
            return parsed

        def _write_json(self, status: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ProtocolPolicyHandler


def _prewarm_model(model_dir: Path) -> None:
    try:
        predict_action(
            model_dir=model_dir,
            row={
                "player_id": 0,
                "decision_key": "__prewarm__",
                "observation": {},
                "legal_actions": [{"action_id": "__prewarm__", "legal": True}],
            },
        )
    except Exception:
        # Startup must still surface real errors on the first request; prewarm is only latency control.
        return


def _legal_actions_from_request(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    actions: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        choice_id = _string(item.get("choice_id"))
        if not choice_id:
            continue
        actions.append(
            {
                "action_id": choice_id,
                "legal": True,
                "label": _string(item.get("title")) or choice_id,
            }
        )
    return actions


def _choice_payload_for_request(payload: Mapping[str, Any], choice_id: str) -> dict[str, Any] | None:
    prompt = _record(payload.get("prompt"))
    if _string(prompt.get("request_type")) != "active_flip" or choice_id != "none":
        return None
    if _active_flip_already_flipped_count(payload) > 0:
        return None
    selected_choice_ids = [
        action["action_id"]
        for action in _legal_actions_from_request(payload.get("legal_choices"))
        if action["action_id"] != "none"
    ]
    if not selected_choice_ids:
        return None
    return {
        "selected_choice_ids": selected_choice_ids,
        "finish_after_selection": True,
    }


def _prompt_public_context(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    prompt = _record(payload.get("prompt"))
    return _record(prompt.get("public_context") or prompt.get("publicContext"))


def _active_flip_already_flipped_count(payload: Mapping[str, Any]) -> int:
    public_context = _prompt_public_context(payload)
    count = _int_or_none(public_context.get("already_flipped_count")) or 0
    cards = public_context.get("already_flipped_cards")
    card_count = len(cards) if isinstance(cards, list) else 0
    return max(0, count, card_count)


def _record(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a trained MRN protocol policy over HTTP.")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args(argv)
    run_server(model_dir=args.model_dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
