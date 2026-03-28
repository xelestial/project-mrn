from __future__ import annotations

import json
import queue
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(slots=True)
class RuntimePromptChoice:
    key: str
    label: str
    value: Any

    def to_public_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
        }


@dataclass(slots=True)
class RuntimePrompt:
    prompt_id: str
    player_id: int
    decision_type: str
    choices: list[RuntimePromptChoice]
    deadline_mode: str
    public_context: dict = field(default_factory=dict)
    can_pass: bool = False

    def to_public_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "player_id": self.player_id,
            "decision_type": self.decision_type,
            "choices": [choice.to_public_dict() for choice in self.choices],
            "deadline_mode": self.deadline_mode,
            "public_context": self.public_context,
            "can_pass": self.can_pass,
        }


@dataclass(slots=True)
class RuntimePromptResponse:
    prompt_id: str
    choice_key: str | None


class PromptResponseProvider(Protocol):
    def get_response(self, prompt: RuntimePrompt) -> RuntimePromptResponse:
        ...


class QueuePromptResponder:
    def __init__(self) -> None:
        self._responses: "queue.Queue[RuntimePromptResponse]" = queue.Queue()

    def submit_response(self, response: RuntimePromptResponse) -> None:
        self._responses.put(response)

    def get_response(self, prompt: RuntimePrompt) -> RuntimePromptResponse:
        while True:
            response = self._responses.get()
            if response.prompt_id == prompt.prompt_id:
                return response


class PromptFileChannel:
    def __init__(self, out_dir: str | Path) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_state_path = self.out_dir / "prompt_state.json"
        self.prompt_history_path = self.out_dir / "prompt_history.jsonl"
        self.clear_prompt()

    def open_prompt(self, prompt: RuntimePrompt) -> None:
        self._write_state(
            {
                "schema": "gpt.phase4.prompt_state.v1",
                "status": "open",
                "prompt": prompt.to_public_dict(),
            }
        )
        with open(self.prompt_history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "prompt_open", "prompt": prompt.to_public_dict()}, ensure_ascii=False) + "\n")

    def close_prompt(self, prompt: RuntimePrompt, response: RuntimePromptResponse) -> None:
        payload = {
            "schema": "gpt.phase4.prompt_state.v1",
            "status": "closed",
            "prompt": prompt.to_public_dict(),
            "response": {"choice_key": response.choice_key},
        }
        self._write_state(payload)
        with open(self.prompt_history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "prompt_close", **payload}, ensure_ascii=False) + "\n")

    def clear_prompt(self) -> None:
        self._write_state(
            {
                "schema": "gpt.phase4.prompt_state.v1",
                "status": "idle",
                "prompt": None,
            }
        )

    def _write_state(self, payload: dict) -> None:
        temp_path = self.prompt_state_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        temp_path.replace(self.prompt_state_path)


def new_prompt(
    *,
    player_id: int,
    decision_type: str,
    choices: list[RuntimePromptChoice],
    deadline_mode: str = "blocking",
    public_context: dict | None = None,
    can_pass: bool = False,
) -> RuntimePrompt:
    return RuntimePrompt(
        prompt_id=str(uuid.uuid4()),
        player_id=player_id,
        decision_type=decision_type,
        choices=choices,
        deadline_mode=deadline_mode,
        public_context=public_context or {},
        can_pass=can_pass,
    )
