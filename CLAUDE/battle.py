from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8")

"""battle.py — 플레이어별 독립 AI 모듈 대결 실행기."""

import argparse
import json
import random
from pathlib import Path

from board_layout_creator import load_board_config
from config import DEFAULT_CONFIG
from doc_integrity import summarize_integrity
from engine import GameEngine
from game_rules_loader import load_ruleset
from metadata import GAME_VERSION
from simulate_with_logs import RunningSummary, result_to_dict, write_summary

from multi_agent.dispatcher import MultiAgentDispatcher
from multi_agent.agent_loader import make_agent


def _runtime_config(starting_cash=None, board_layout_path=None,
                    board_layout_meta_path=None, rule_scripts_path=None,
                    ruleset_path=None):
    from simulate_with_logs import _runtime_config as _rc
    return _rc(starting_cash, board_layout_path, board_layout_meta_path,
               rule_scripts_path, ruleset_path)


def run_battle(
    player_specs: dict[int, str],   # {1: "claude:v3_claude", 2: "gpt:v3_gpt", ...}
    simulations: int = 100,
    seed: int = 42,
    output_dir: str = "battle_output",
):
    """
    플레이어별 독립 AI 대결을 실행하고 요약 통계를 출력한다.

    player_specs: {player_id(1-4): agent_spec}
      예) {1: "claude:v3_claude", 2: "gpt:v3_gpt", 3: "claude:balanced", 4: "claude:balanced"}
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # agent 생성
    agents = {pid: make_agent(spec) for pid, spec in player_specs.items()}
    # 미지정 플레이어는 claude:balanced 기본값
    for pid in range(1, 5):
        if pid not in agents:
            agents[pid] = make_agent("claude:balanced")

    agent_ids = {pid: agent.agent_id for pid, agent in agents.items()}
    print(f"[battle] lineup: {agent_ids}", flush=True)

    policy = MultiAgentDispatcher(agents)
    integrity = dict(summarize_integrity())
    runtime_config = _runtime_config()

    # RunningSummary는 policy_mode에 agent_id 매핑을 넘긴다
    player_character_policy_modes = {pid: agent.agent_id for pid, agent in agents.items()}
    running = RunningSummary(
        policy_mode="multi_agent",
        lap_policy_mode="multi_agent",
        player_lap_policy_modes=player_character_policy_modes,
        player_character_policy_modes=player_character_policy_modes,
        integrity=integrity,
    )

    outer_rng = random.Random(seed)

    with (out / "games.jsonl").open("w", encoding="utf-8") as f, \
         (out / "errors.jsonl").open("w", encoding="utf-8") as ef:

        for game_id in range(simulations):
            game_seed = outer_rng.randrange(1 << 30)
            try:
                rng = random.Random(game_seed)
                engine = GameEngine(runtime_config, policy, rng=rng, enable_logging=False)
                result = result_to_dict(engine.run(), log_level="summary", integrity=integrity)
                result["game_id"] = game_id
                result["game_seed"] = game_seed
                result["policy_mode"] = "multi_agent"
                result["agent_lineup"] = agent_ids
                running.update(result)
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                if (game_id + 1) % 10 == 0:
                    print(f"  {game_id + 1}/{simulations}", flush=True)
            except Exception as e:
                import traceback
                ef.write(json.dumps({
                    "game_id": game_id, "error": str(e),
                    "traceback": traceback.format_exc()
                }, ensure_ascii=False) + "\n")

    summary = write_summary(out, running)
    summary["agent_lineup"] = agent_ids
    # agent_lineup를 파일에도 반영
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser(description="Per-player independent AI battle runner")
    ap.add_argument("--player1", default="claude:v3_claude")
    ap.add_argument("--player2", default="gpt:v3_gpt")
    ap.add_argument("--player3", default="claude:balanced")
    ap.add_argument("--player4", default="claude:balanced")
    ap.add_argument("--simulations", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", default="battle_output")
    args = ap.parse_args()

    player_specs = {
        1: args.player1,
        2: args.player2,
        3: args.player3,
        4: args.player4,
    }
    run_battle(
        player_specs=player_specs,
        simulations=args.simulations,
        seed=args.seed,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
