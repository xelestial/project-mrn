from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from run_live_playable import _parse_prompt_response_payload, _resolve_response_mode, _serve_directory
from viewer.prompting import QueuePromptResponder


def test_parse_prompt_response_payload_accepts_valid_choice() -> None:
    response = _parse_prompt_response_payload({"prompt_id": "abc-123", "choice_key": "yes"})
    assert response.prompt_id == "abc-123"
    assert response.choice_key == "yes"


def test_parse_prompt_response_payload_accepts_pass() -> None:
    response = _parse_prompt_response_payload({"prompt_id": "abc-123", "choice_key": None})
    assert response.prompt_id == "abc-123"
    assert response.choice_key is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"prompt_id": ""},
        {"prompt_id": 123},
        {"prompt_id": "ok", "choice_key": 7},
    ],
)
def test_parse_prompt_response_payload_rejects_invalid_payload(payload: dict) -> None:
    with pytest.raises(ValueError):
        _parse_prompt_response_payload(payload)


def test_resolve_response_mode_auto() -> None:
    assert _resolve_response_mode("auto", serve=False) == "cli"
    assert _resolve_response_mode("auto", serve=True) == "web"


def test_resolve_response_mode_web_requires_serve() -> None:
    with pytest.raises(ValueError):
        _resolve_response_mode("web", serve=False)


def test_prompt_response_endpoint_enqueues_response() -> None:
    class PromptStub:
        def __init__(self, prompt_id: str) -> None:
            self.prompt_id = prompt_id

    with tempfile.TemporaryDirectory() as tmp_dir:
        Path(tmp_dir, "index.html").write_text("<html>ok</html>", encoding="utf-8")
        responder = QueuePromptResponder()
        server = _serve_directory(Path(tmp_dir), 0, responder=responder)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            payload = json.dumps({"prompt_id": "prompt-1", "choice_key": "yes"}).encode("utf-8")
            req = request.Request(
                f"http://127.0.0.1:{port}/api/prompt-response",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with request.urlopen(req, timeout=2.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            assert body["ok"] is True

            queued = responder.get_response(PromptStub("prompt-1"))
            assert queued.choice_key == "yes"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)
