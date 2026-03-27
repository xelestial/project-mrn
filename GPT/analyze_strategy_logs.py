from __future__ import annotations

import argparse
import json
from pathlib import Path

from stats_utils import compute_basic_stats_from_games
from text_encoding import configure_utf8_io


def load_games(path: Path):
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def analyze(games_path: str, output: str):
    games = list(load_games(Path(games_path)))
    result = compute_basic_stats_from_games(games)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    configure_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument('--games-jsonl', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    analyze(args.games_jsonl, args.output)
