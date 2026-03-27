from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulate_with_logs import RunningSummary, parse_player_character_policy_modes, parse_player_lap_policy_modes, run
from text_encoding import configure_utf8_io


def _load_games(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _chunk_id_from_dir(chunk_dir: Path, fallback_index: int) -> int:
    name = chunk_dir.name
    if name.startswith("chunk_"):
        suffix = name.split("chunk_", 1)[1]
        if suffix.isdigit():
            return int(suffix)
    return fallback_index


def _merge_chunks(root: Path, running: RunningSummary, chunk_dirs: list[Path]) -> dict:
    out_games = root / "games.jsonl"
    out_errors = root / "errors.jsonl"
    out_games.write_text("", encoding="utf-8")
    out_errors.write_text("", encoding="utf-8")
    with out_games.open("a", encoding="utf-8") as gf, out_errors.open("a", encoding="utf-8") as ef:
        next_game_id = 0
        for chunk_index, chunk_dir in enumerate(chunk_dirs, start=1):
            inferred_chunk_id = _chunk_id_from_dir(chunk_dir, chunk_index)
            for local_idx, row in enumerate(_load_games(chunk_dir / "games.jsonl")):
                original_game_id = row.get("game_id")
                original_global_index = row.get("global_game_index")
                row["chunk_id"] = inferred_chunk_id
                row["chunk_game_id"] = row.get("chunk_game_id", original_game_id if original_game_id is not None else local_idx)
                row["original_global_game_index"] = original_global_index
                row["global_game_index"] = next_game_id
                row["game_id"] = next_game_id
                next_game_id += 1
                running.update(row)
                gf.write(json.dumps(row, ensure_ascii=False) + "\n")
            errors_path = chunk_dir / "errors.jsonl"
            if errors_path.exists():
                content = errors_path.read_text(encoding="utf-8")
                if content.strip():
                    ef.write(content)
                    if not content.endswith("\n"):
                        ef.write("\n")
    summary = running.to_dict()
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    configure_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulations", "--games", dest="simulations", type=int, default=100, help="Total number of games to simulate across all chunks.")
    ap.add_argument("--chunk-size", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", type=str, default="chunked_batch_output")
    ap.add_argument("--checkpoint-every", type=int, default=100)
    ap.add_argument("--flush-every", type=int, default=1)
    ap.add_argument("--log-level", choices=["summary", "full", "sampled", "none"], default="summary")
    ap.add_argument("--full-log-every", type=int, default=0)
    ap.add_argument("--policy-mode", type=str, default="arena")
    ap.add_argument("--lap-policy-mode", type=str, default="heuristic_v1")
    ap.add_argument("--player-lap-policies", type=str, default="")
    ap.add_argument("--player-character-policies", type=str, default="")
    ap.add_argument("--starting-cash", type=int, default=None)
    ap.add_argument("--board-layout", type=str, default=None)
    ap.add_argument("--board-layout-meta", type=str, default=None)
    ap.add_argument("--rule-scripts", type=str, default=None)
    ap.add_argument("--ruleset", type=str, default=None)
    args = ap.parse_args()

    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    player_lap_policy_modes = parse_player_lap_policy_modes(args.player_lap_policies)
    player_character_policy_modes = parse_player_character_policy_modes(args.player_character_policies)
    running = RunningSummary(
        policy_mode=args.policy_mode,
        lap_policy_mode=args.lap_policy_mode,
        player_lap_policy_modes=player_lap_policy_modes,
        player_character_policy_modes=player_character_policy_modes,
    )

    chunk_dirs: list[Path] = []
    remaining = args.simulations
    chunk_index = 0
    next_global_game_index = 0
    run_id = f"chunked_seed{args.seed}_games{args.simulations}_chunk{args.chunk_size}_{args.policy_mode}"
    chunk_seed_rng = __import__("random").Random(args.seed ^ 0x9E3779B97F4A7C15)
    chunk_manifest = []
    while remaining > 0:
        chunk_n = min(args.chunk_size, remaining)
        chunk_dir = root / f"chunk_{chunk_index + 1:03d}"
        chunk_seed = chunk_seed_rng.randrange(1 << 61)
        chunk_manifest.append({"chunk_id": chunk_index + 1, "chunk_games": chunk_n, "chunk_seed": chunk_seed, "output_dir": str(chunk_dir)})
        run(
            simulations=chunk_n,
            seed=chunk_seed,
            output_dir=str(chunk_dir),
            checkpoint_every=min(args.checkpoint_every, chunk_n) if args.checkpoint_every > 0 else 0,
            flush_every=args.flush_every,
            log_level=args.log_level,
            full_log_every=args.full_log_every,
            policy_mode=args.policy_mode,
            lap_policy_mode=args.lap_policy_mode,
            player_lap_policy_modes=player_lap_policy_modes,
            player_character_policy_modes=player_character_policy_modes,
            starting_cash=args.starting_cash,
            board_layout_path=args.board_layout,
            board_layout_meta_path=args.board_layout_meta,
            rule_scripts_path=args.rule_scripts,
            ruleset_path=args.ruleset,
            emit_summary=False,
            run_id=run_id,
            root_seed=args.seed,
            chunk_id=chunk_index + 1,
            global_game_index_start=next_global_game_index,
        )
        chunk_dirs.append(chunk_dir)
        remaining -= chunk_n
        next_global_game_index += chunk_n
        chunk_index += 1

    (root / "chunk_manifest.json").write_text(json.dumps(chunk_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = _merge_chunks(root, running, chunk_dirs)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
