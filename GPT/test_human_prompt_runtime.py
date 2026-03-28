from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_policy import LapRewardDecision, MovementDecision
from config import DEFAULT_CONFIG
from state import GameState
from viewer.human_adapter import HumanDecisionAdapter
from viewer.playable_runtime import run_playable_seed
from viewer.prompting import PromptFileChannel, RuntimePromptResponse


class ScriptedResponseProvider:
    def __init__(self, responses: list[str | None]) -> None:
        self._responses = list(responses)

    def get_response(self, prompt):
        if not self._responses:
            raise AssertionError(f"no scripted response left for {prompt.decision_type}")
        return RuntimePromptResponse(prompt.prompt_id, self._responses.pop(0))


class AutoFirstResponseProvider:
    def get_response(self, prompt):
        choice_key = prompt.choices[0].key if prompt.choices else None
        return RuntimePromptResponse(prompt.prompt_id, choice_key)


def _build_engine_and_adapter(tmp_dir: str, responses: list[str | None]):
    prompt_channel = PromptFileChannel(tmp_dir)
    adapter = HumanDecisionAdapter(
        human_players={1},
        response_provider=ScriptedResponseProvider(responses),
        prompt_channel=prompt_channel,
    )
    state = GameState.create(DEFAULT_CONFIG)
    return state, adapter, prompt_channel


def test_prompt_file_channel_open_close() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        state, adapter, prompt_channel = _build_engine_and_adapter(tmp_dir, ["0"])
        player = state.players[0]

        decision = adapter.choose_movement(state, player)
        assert decision == MovementDecision(use_cards=False)

        prompt_state = json.loads((Path(tmp_dir) / "prompt_state.json").read_text(encoding="utf-8"))
        assert prompt_state["status"] == "closed"
        assert prompt_state["prompt"]["decision_type"] == "movement"
        assert prompt_state["response"]["choice_key"] == "0"


def test_human_adapter_lap_reward_prompt() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        state, adapter, prompt_channel = _build_engine_and_adapter(tmp_dir, ["shards"])
        player = state.players[0]

        decision = adapter.choose_lap_reward(state, player)
        assert decision == LapRewardDecision(choice="shards")

        prompt_state = json.loads((Path(tmp_dir) / "prompt_state.json").read_text(encoding="utf-8"))
        assert prompt_state["prompt"]["decision_type"] == "lap_reward"
        assert prompt_state["response"]["choice_key"] == "shards"


def test_human_adapter_purchase_prompt() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        state, adapter, prompt_channel = _build_engine_and_adapter(tmp_dir, ["yes"])
        player = state.players[0]

        decision = adapter.choose_purchase_tile(state, player, 5, state.board[5], 3)
        assert decision is True

        prompt_state = json.loads((Path(tmp_dir) / "prompt_state.json").read_text(encoding="utf-8"))
        assert prompt_state["prompt"]["decision_type"] == "purchase_decision"
        assert prompt_state["response"]["choice_key"] == "yes"


def test_playable_runtime_smoke() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        stream, prompt_channel = run_playable_seed(
            seed=42,
            out_dir=tmp_dir,
            human_players={1},
            response_provider=AutoFirstResponseProvider(),
        )
        summary = stream.summary()
        assert summary["total_events"] > 0
        prompt_state = json.loads((Path(tmp_dir) / "prompt_state.json").read_text(encoding="utf-8"))
        assert prompt_state["status"] == "idle"
        history = (Path(tmp_dir) / "prompt_history.jsonl").read_text(encoding="utf-8")
        assert "prompt_open" in history
        assert "prompt_close" in history
