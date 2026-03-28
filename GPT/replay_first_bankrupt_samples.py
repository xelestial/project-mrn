from __future__ import annotations

import argparse
import re
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from battle import _runtime_config
from characters import CARD_TO_NAMES
from engine import GameEngine
from multi_agent.agent_loader import make_agent
from multi_agent.dispatcher import MultiAgentDispatcher
from text_encoding import configure_utf8_io


@dataclass(slots=True)
class SampleMeta:
    sample_no: int
    game_id: int
    game_seed: int
    first_bankrupt_player_1: int
    character: str
    cause: str
    bankrupt_turn_index: int
    bankrupt_round_index: int
    position: int
    tile_kind: str
    cash_before_death: int
    required_cost: int
    cash_shortfall: int
    winners: str


@dataclass(slots=True)
class TurnSnapshot:
    round_index: int
    turn_index: int
    phase: str
    player_id_1: int
    character: str
    position: int
    cash: int
    shards: int
    hand_coins: int
    tiles_owned: int
    owned_tiles: list[str]


class SnapshotGameEngine(GameEngine):
    def __init__(self, *args, tracked_player_id_1: int, **kwargs):
        super().__init__(*args, **kwargs)
        self._tracked_player_id_1 = tracked_player_id_1
        self.turn_snapshots: list[TurnSnapshot] = []

    def _take_turn(self, state, player) -> None:
        tracked_zero = self._tracked_player_id_1 - 1
        if player.player_id == tracked_zero and player.alive:
            self.turn_snapshots.append(
                TurnSnapshot(
                    round_index=state.rounds_completed + 1,
                    turn_index=state.turn_index,
                    phase="start",
                    player_id_1=player.player_id + 1,
                    character=player.current_character,
                    position=player.position,
                    cash=player.cash,
                    shards=player.shards,
                    hand_coins=player.hand_coins,
                    tiles_owned=player.tiles_owned,
                    owned_tiles=_owned_tile_labels(state, player.player_id),
                )
            )
        super()._take_turn(state, player)
        if player.player_id == tracked_zero:
            self.turn_snapshots.append(
                TurnSnapshot(
                    round_index=state.rounds_completed + 1,
                    turn_index=state.turn_index,
                    phase="end",
                    player_id_1=player.player_id + 1,
                    character=player.current_character,
                    position=player.position,
                    cash=player.cash,
                    shards=player.shards,
                    hand_coins=player.hand_coins,
                    tiles_owned=player.tiles_owned,
                    owned_tiles=_owned_tile_labels(state, player.player_id),
                )
            )


def _owned_tile_labels(state, owner_id_0: int) -> list[str]:
    labels: list[str] = []
    for tile in state.tiles:
        if tile.owner_id != owner_id_0:
            continue
        labels.append(
            f"{tile.index}:{tile.kind.name}"
            + (f"/B{tile.block_id}" if tile.block_id >= 0 else "")
            + (f"/C{tile.score_coins}" if tile.score_coins else "")
        )
    return labels


def _card_label(card_no: object) -> str:
    try:
        card_int = int(card_no)
    except Exception:
        return str(card_no)
    names = CARD_TO_NAMES.get(card_int)
    if not names:
        return str(card_int)
    return f"{card_int} ({names[0]}/{names[1]})"


def parse_sample_file(path: Path) -> list[SampleMeta]:
    text = path.read_text(encoding="utf-8")
    samples: list[SampleMeta] = []
    current_no: int | None = None
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## Sample "):
            if current_no is not None and current:
                samples.append(_sample_from_meta(current_no, current))
            current_no = int(line.split()[-1])
            current = {}
            continue
        if current_no is None:
            continue
        if line.startswith("### Actions"):
            continue
        if line.startswith("- "):
            match = re.match(r"-\s+([^:]+):\s+`?(.*?)`?$", line)
            if match:
                current[match.group(1).strip()] = match.group(2).strip()
    if current_no is not None and current:
        samples.append(_sample_from_meta(current_no, current))
    return samples


def _sample_from_meta(sample_no: int, meta: dict[str, str]) -> SampleMeta:
    return SampleMeta(
        sample_no=sample_no,
        game_id=int(meta["game_id"]),
        game_seed=int(meta["game_seed"]),
        first_bankrupt_player_1=int(meta["first_bankrupt_player"].replace("P", "")),
        character=meta["character"],
        cause=meta["cause"],
        bankrupt_turn_index=int(meta["bankrupt_turn_index"]),
        bankrupt_round_index=int(meta["bankrupt_round_index"]),
        position=int(meta["position"]),
        tile_kind=meta["tile_kind"],
        cash_before_death=int(meta["cash_before_death"]),
        required_cost=int(meta["required_cost"]),
        cash_shortfall=int(meta["cash_shortfall"]),
        winners=meta["winners"],
    )


def _find_first_bankruptcy(result) -> dict | None:
    events = list(result.bankruptcy_events or [])
    if not events:
        return None
    events.sort(key=lambda evt: (evt.get("turn_index", 10**9), evt.get("player_id", 10**9)))
    return events[0]


def _row_mentions_player(row: dict, player_id_1: int) -> bool:
    if row.get("player") == player_id_1:
        return True
    if row.get("target_player") == player_id_1:
        return True
    if row.get("source_player") == player_id_1:
        return True
    if row.get("active_player_id") == player_id_1:
        return True
    for key in ("players", "args", "kwargs", "results"):
        value = row.get(key)
        if _value_mentions_player(value, player_id_1):
            return True
    return False


def _value_mentions_player(value, player_id_1: int) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        for nested in value.values():
            if _value_mentions_player(nested, player_id_1):
                return True
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_value_mentions_player(item, player_id_1) for item in value)
    return value == player_id_1 or value == f"P{player_id_1}"


def _snapshot_index(turn_snapshots: Iterable[TurnSnapshot]) -> dict[tuple[int, int, str], TurnSnapshot]:
    return {
        (snapshot.round_index, snapshot.turn_index, snapshot.phase): snapshot
        for snapshot in turn_snapshots
    }


def _format_snapshot(snapshot: TurnSnapshot | None) -> str:
    if snapshot is None:
        return "n/a"
    owned = ", ".join(snapshot.owned_tiles) if snapshot.owned_tiles else "-"
    return (
        f"cash {snapshot.cash}, shards {snapshot.shards}, hand_coins {snapshot.hand_coins}, "
        f"pos {snapshot.position}, tiles {snapshot.tiles_owned}, owned [{owned}]"
    )


def _describe_turn_path(
    start_snapshot: TurnSnapshot | None,
    end_snapshot: TurnSnapshot | None,
    board_len: int = 40,
) -> str:
    if start_snapshot is None or end_snapshot is None:
        return "path n/a"
    start_pos = start_snapshot.position
    end_pos = end_snapshot.position
    wrapped = end_pos < start_pos
    distance = (end_pos - start_pos) % board_len
    wrap_text = " | crossed start" if wrapped else ""
    return f"path {start_pos} -> {end_pos} (distance {distance}){wrap_text}"


def _line_for_row(row: dict, player_id_1: int, snapshots: dict[tuple[int, int, str], TurnSnapshot]) -> str:
    event = row.get("event", "?")
    round_index = row.get("round_index", "?")
    turn_index = row.get("turn_index", "?")
    pieces = [f"{event} (R{round_index}/T{turn_index})"]
    round_key = int(round_index) if str(round_index).isdigit() else None
    turn_key = int(turn_index) if str(turn_index).isdigit() else None
    if event == "turn_start":
        snap = snapshots.get((round_key, turn_key, "start")) if round_key is not None and turn_key is not None else None
        pieces.append(_format_snapshot(snap))
    elif event == "turn":
        start_snap = snapshots.get((round_key, turn_key, "start")) if round_key is not None and turn_key is not None else None
        snap = snapshots.get((round_key, turn_key, "end")) if round_key is not None and turn_key is not None else None
        pieces.append(_format_snapshot(snap))
        pieces.append(_describe_turn_path(start_snap, snap))
    elif event == "ai_decision_after":
        decision = row.get("decision")
        result = row.get("result")
        if decision == "choose_movement":
            text = str(result)
            start_snap = snapshots.get((round_key, turn_key, "start")) if round_key is not None and turn_key is not None else None
            end_snap = snapshots.get((round_key, turn_key, "end")) if round_key is not None and turn_key is not None else None
            if "use_cards=False" in text:
                pieces.append("movement: base move only")
            else:
                pieces.append(f"movement: {text}")
            pieces.append(_describe_turn_path(start_snap, end_snap))
        elif decision in {"choose_trick_to_use", "choose_mark_target", "choose_final_character", "choose_purchase_tile", "choose_lap_reward"}:
            pieces.append(f"{decision} -> {result}")
    elif event == "trick_used":
        card = row.get("card") or {}
        if isinstance(card, dict) and card.get("name"):
            pieces.append(f"used trick {card['name']}")
    elif event == "final_character_choice":
        pieces.append(f"character -> {row.get('character')}")
    elif event == "draft_pick":
        pieces.append(f"phase {row.get('phase')} picked {_card_label(row.get('picked_card'))}")
    elif event == "landing.unowned.resolve":
        pieces.append("landed on unowned tile")
    elif event == "rent.payment.resolve":
        pieces.append("rent payment resolved")
    elif event == "payment.resolve":
        cost = row.get("cost")
        if cost is not None:
            pieces.append(f"payment cost {cost}")
    elif event == "assassin_reveal":
        pieces.append("got hit by assassin reveal" if row.get("target_player") == player_id_1 else f"assassin reveal on P{row.get('target_player')}")
    elif event == "bandit_tax":
        if row.get("target_player") == player_id_1:
            pieces.append(f"paid bandit tax {row.get('amount')}")
    elif event == "baksu_transfer":
        if row.get("target_player") == player_id_1:
            pieces.append("received baksu burden transfer")
        elif row.get("player") == player_id_1:
            pieces.append("triggered baksu burden transfer")
    elif event == "bankruptcy.resolve":
        pieces.append("bankruptcy resolved")
    elif event == "failed_mark_fallback_none":
        pieces.append("mark failed / no valid target")
    return " | ".join(str(piece) for piece in pieces if piece not in (None, "None"))


def build_report(
    sample_file: Path,
    output_file: Path,
    player_specs: dict[int, str],
    limit: int | None = None,
) -> None:
    configure_utf8_io()
    samples = parse_sample_file(sample_file)
    if limit is not None:
        samples = samples[:limit]

    agents = {pid: make_agent(spec) for pid, spec in player_specs.items()}
    dispatcher = MultiAgentDispatcher(agents)
    config = _runtime_config()

    lines: list[str] = []
    lines.append("# First Bankrupt Samples Replay Report")
    lines.append("")
    lines.append("This replay report adds turn snapshots so cash and owned tiles are visible.")
    lines.append("")
    lines.append("## Lineup")
    for pid in sorted(player_specs):
        lines.append(f"- P{pid}: `{player_specs[pid]}`")
    lines.append("")

    for sample in samples:
        rng = random.Random(sample.game_seed)
        engine = SnapshotGameEngine(
            config,
            dispatcher,
            rng=rng,
            enable_logging=True,
            tracked_player_id_1=sample.first_bankrupt_player_1,
        )
        result = engine.run()
        first_bankruptcy = _find_first_bankruptcy(result)
        tracked = sample.first_bankrupt_player_1
        relevant_rows = [row for row in result.action_log if _row_mentions_player(row, tracked)]
        snapshots = _snapshot_index(engine.turn_snapshots)

        lines.append(f"## Sample {sample.sample_no}")
        lines.append(f"- game_id: `{sample.game_id}` / seed: `{sample.game_seed}`")
        lines.append(f"- tracked player: `P{tracked}`")
        lines.append(f"- expected first bankruptcy: `{sample.character}` / `{sample.cause}`")
        if first_bankruptcy:
            lines.append(
                "- replay first bankruptcy:"
                f" `P{first_bankruptcy.get('player_id')}` / `{first_bankruptcy.get('character')}`"
                f" / `{first_bankruptcy.get('cause_hint')}`"
            )
        lines.append(
            f"- bankruptcy cash snapshot: cash `{sample.cash_before_death}`,"
            f" required `{sample.required_cost}`, shortfall `{sample.cash_shortfall}`"
        )
        lines.append("")
        lines.append("### Turn snapshots")
        for snapshot in engine.turn_snapshots:
            owned = ", ".join(snapshot.owned_tiles) if snapshot.owned_tiles else "-"
            if snapshot.phase == "start":
                mate = snapshots.get((snapshot.round_index, snapshot.turn_index, "end"))
                path_text = _describe_turn_path(snapshot, mate)
            else:
                mate = snapshots.get((snapshot.round_index, snapshot.turn_index, "start"))
                path_text = _describe_turn_path(mate, snapshot)
            lines.append(
                f"- R{snapshot.round_index}/T{snapshot.turn_index} {snapshot.phase}:"
                f" char `{snapshot.character}`, pos `{snapshot.position}`, cash `{snapshot.cash}`,"
                f" shards `{snapshot.shards}`, hand_coins `{snapshot.hand_coins}`,"
                f" tiles `{snapshot.tiles_owned}`, owned [{owned}], {path_text}"
            )
        lines.append("")
        lines.append("### Relevant events")
        for row in relevant_rows:
            lines.append(f"- {_line_for_row(row, tracked, snapshots)}")
        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay first-bankrupt samples with turn snapshots")
    parser.add_argument("--sample-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--player1", default="claude:heuristic_v2_v3_claude")
    parser.add_argument("--player2", default="gpt:heuristic_v3_gpt")
    parser.add_argument("--player3", default="claude:heuristic_v2_v3_claude")
    parser.add_argument("--player4", default="gpt:heuristic_v3_gpt")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    build_report(
        sample_file=Path(args.sample_file),
        output_file=Path(args.output_file),
        player_specs={
            1: args.player1,
            2: args.player2,
            3: args.player3,
            4: args.player4,
        },
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
