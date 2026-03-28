from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from doc_integrity import summarize_integrity
from engine import GameEngine
from policy.asset.spec import MultiAgentBattleAsset
from policy.factory import PolicyFactory
from simulate_with_logs import RunningSummary, result_to_dict, write_summary
from text_encoding import configure_utf8_io


def _runtime_config(
    starting_cash=None,
    board_layout_path=None,
    board_layout_meta_path=None,
    rule_scripts_path=None,
    ruleset_path=None,
):
    from simulate_with_logs import _runtime_config as _shared_runtime_config

    return _shared_runtime_config(
        starting_cash,
        board_layout_path,
        board_layout_meta_path,
        rule_scripts_path,
        ruleset_path,
    )


def run_battle(
    player_specs: dict[int, str],
    simulations: int = 100,
    seed: int = 42,
    output_dir: str = "battle_output",
):
    """Run a per-player AI battle using the dispatcher-based wrapper structure."""

    configure_utf8_io()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    battle_asset = PolicyFactory.normalize_multi_agent_battle_asset(
        MultiAgentBattleAsset(player_specs=player_specs)
    )
    policy = PolicyFactory.create_multi_agent_dispatcher(battle_asset)
    agent_ids = {
        pid: policy.agent_id_for_player(pid)
        for pid in range(1, 5)
    }
    integrity = dict(summarize_integrity())
    runtime_config = _runtime_config()

    player_modes = dict(agent_ids)
    running = RunningSummary(
        policy_mode="multi_agent",
        lap_policy_mode="multi_agent",
        player_lap_policy_modes=player_modes,
        player_character_policy_modes=player_modes,
        integrity=integrity,
    )

    outer_rng = random.Random(seed)

    with (out / "games.jsonl").open("w", encoding="utf-8") as game_file, (
        out / "errors.jsonl"
    ).open("w", encoding="utf-8") as error_file:
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
                game_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            except Exception as exc:
                import traceback

                error_file.write(
                    json.dumps(
                        {
                            "game_id": game_id,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    summary = write_summary(out, running)
    summary["agent_lineup"] = agent_ids
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Claude vs GPT multi-agent battle runner")
    ap.add_argument("--player1", default="claude:v3_claude")
    ap.add_argument("--player2", default="gpt:v3_gpt")
    ap.add_argument("--player3", default="gpt:v3_gpt")
    ap.add_argument("--player4", default="gpt:v3_gpt")
    ap.add_argument("--simulations", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", default="battle_output")
    args = ap.parse_args()

    run_battle(
        player_specs={
            1: args.player1,
            2: args.player2,
            3: args.player3,
            4: args.player4,
        },
        simulations=args.simulations,
        seed=args.seed,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
