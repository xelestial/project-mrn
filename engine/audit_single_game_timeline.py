from __future__ import annotations

import argparse
import copy
import random
from pathlib import Path
from typing import Any

from config import DEFAULT_CONFIG
from engine import GameResult, GameEngine
from policy.factory import PolicyFactory
from text_encoding import configure_utf8_io


def _fmt_landing(landing: dict[str, Any] | None) -> str:
    if not isinstance(landing, dict):
        return "-"
    kind = str(landing.get("type", "-"))
    if kind in {"PURCHASE", "PURCHASE_SKIP_POLICY"}:
        return (
            f"{kind}(cost={landing.get('cost')}, shard={landing.get('shard_cost')}, "
            f"skipped={landing.get('skipped', False)})"
        )
    if kind == "RENT":
        return (
            f"RENT(amount={landing.get('amount')}, owner=P{landing.get('owner')}, "
            f"shard={landing.get('shard_cost')})"
        )
    return kind


def _fmt_turn_movement(turn_row: dict[str, Any]) -> str:
    movement = turn_row.get("movement") or {}
    mode = movement.get("mode")
    used_cards = movement.get("used_cards") or []
    dice = movement.get("dice") or []
    formula = movement.get("formula")
    if used_cards:
        return f"mode={mode} cards={used_cards} formula={formula}"
    if dice:
        return f"mode={mode} dice={dice} formula={formula}"
    return f"mode={mode} formula={formula}"


def _fmt_trick_card_name(event_row: dict[str, Any]) -> str:
    card = event_row.get("card")
    if isinstance(card, dict):
        return str(card.get("name") or card.get("deck_index") or card)
    return str(card)


def _fmt_game_end_winner_consistency(result: GameResult, action_log: list[dict[str, Any]]) -> str:
    expected = [winner_id + 1 for winner_id in result.winner_ids]
    game_end = next((row for row in reversed(action_log) if row.get("event") == "game_end"), None)
    if not isinstance(game_end, dict):
        return "UNKNOWN(no game_end row)"
    actual = game_end.get("winner_ids")
    return "PASS" if actual == expected else f"FAIL(log={actual}, result={expected})"


def _check_marker_order(action_log: list[dict[str, Any]]) -> bool:
    marker_indices = [i for i, row in enumerate(action_log) if row.get("event") == "marker_moved"]
    round_end_indices = set(i for i, row in enumerate(action_log) if row.get("event") == "round_end_marker_management")
    return all((idx - 1) in round_end_indices for idx in marker_indices)


def _check_weather_then_draft_segment(action_log: list[dict[str, Any]]) -> bool:
    weather_indices = [i for i, row in enumerate(action_log) if row.get("event") == "weather_round"]
    draft_indices = [i for i, row in enumerate(action_log) if row.get("event") == "draft_pick"]
    for weather_pos, start in enumerate(weather_indices):
        end = weather_indices[weather_pos + 1] if weather_pos + 1 < len(weather_indices) else len(action_log)
        if not any(start < draft_i < end for draft_i in draft_indices):
            return False
    return True


def _check_turn_index_monotonic(action_log: list[dict[str, Any]]) -> bool:
    turns = [int(row.get("turn_index_global")) for row in action_log if row.get("event") == "turn"]
    if not turns:
        return True
    if any(turn <= 0 for turn in turns):
        return False
    return all(turns[i] <= turns[i + 1] for i in range(len(turns) - 1))


def _fmt_fortune_draw(row: dict[str, Any]) -> str:
    result0 = ((row.get("results") or [None])[0] or {})
    if not isinstance(result0, dict):
        return "-"
    card = result0.get("card") or {}
    resolution = result0.get("resolution") or {}
    return f"card={card.get('name')} type={resolution.get('type')}"


def _fmt_fortune_apply(row: dict[str, Any]) -> str:
    result0 = ((row.get("results") or [None])[0] or {})
    if not isinstance(result0, dict):
        return "-"
    fortune_type = result0.get("type")
    if fortune_type == "BLESS_DICE":
        return f"type=BLESS_DICE dice={result0.get('dice')} cash_delta={result0.get('cash_delta')}"
    if fortune_type == "CURSE_DICE":
        return f"type=CURSE_DICE dice={result0.get('dice')} cost={result0.get('cost')} paid={result0.get('paid')}"
    if fortune_type == "LOSE_TILE":
        transfer = result0.get("transfer") or {}
        return f"type=LOSE_TILE pos={transfer.get('pos')} from={transfer.get('from')} to={transfer.get('to')}"
    return f"type={fortune_type} detail={result0}"


def _fmt_fortune_move(row: dict[str, Any]) -> str:
    result0 = ((row.get("results") or [None])[0] or {})
    if not isinstance(result0, dict):
        return "-"
    return (
        f"trigger={result0.get('trigger')} card={result0.get('card_name')} "
        f"{result0.get('start_pos')}->{result0.get('end_pos')} no_lap_credit={result0.get('no_lap_credit')}"
    )


def _fmt_lap_reward(row: dict[str, Any]) -> str:
    result0 = ((row.get("results") or [None])[0] or {})
    if not isinstance(result0, dict):
        return "-"
    return (
        f"choice={result0.get('choice')} cash+={result0.get('cash_delta')} "
        f"shard+={result0.get('shards_delta')} coin+={result0.get('coins_delta')} "
        f"granted_points={result0.get('granted_points')}"
    )


def _fmt_bankruptcy(row: dict[str, Any]) -> str:
    result0 = ((row.get("results") or [None])[0] or {})
    if not isinstance(result0, dict):
        return "-"
    forensic = result0.get("forensic") or {}
    return (
        f"player=P{result0.get('player')} cause={forensic.get('cause_hint')} "
        f"tile={forensic.get('tile_kind')} shortfall={forensic.get('cash_shortfall')} "
        f"required={forensic.get('required_cost')}"
    )


def build_timeline_report(seed: int, result: GameResult, action_log: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("=== 1 GAME FULL VALIDATION (STRICT TIMELINE) ===")
    lines.append(f"seed={seed}")
    lines.append(
        "summary: "
        f"winner={[winner + 1 for winner in result.winner_ids]} "
        f"reason={result.end_reason} turns={result.total_turns} rounds={result.rounds_completed} "
        f"action_log={len(action_log)}"
    )
    lines.append("checks:")
    lines.append(
        f"  - marker_move_after_round_end_management={'PASS' if _check_marker_order(action_log) else 'FAIL'}"
    )
    lines.append(
        f"  - weather_segment_contains_draft={'PASS' if _check_weather_then_draft_segment(action_log) else 'FAIL'}"
    )
    lines.append(
        f"  - turn_index_global_monotonic={'PASS' if _check_turn_index_monotonic(action_log) else 'FAIL'}"
    )
    lines.append(
        f"  - game_end_winner_ids_consistent={_fmt_game_end_winner_consistency(result, action_log)}"
    )
    lines.append("")
    lines.append("[TIMELINE]")

    current_round: int | None = None
    round_local_turn = 0
    game_turn_counter = 0

    for idx, row in enumerate(action_log, start=1):
        event = row.get("event")
        round_index = row.get("round_index")
        if isinstance(round_index, int) and round_index != current_round:
            current_round = round_index
            round_local_turn = 0
            lines.append("")
            lines.append(f"R{current_round}")

        prefix = f"  [#{idx:04d}]"

        if event == "weather_round":
            lines.append(
                f"{prefix} WEATHER name={row.get('weather')} effect={row.get('effect')} details={row.get('details')}"
            )
            continue

        if event == "draft_pick":
            lines.append(
                f"{prefix} DRAFT phase={row.get('phase')} player=P{row.get('player')} picked={row.get('picked_card')}"
            )
            continue

        if event == "final_character_choice":
            lines.append(
                f"{prefix} FINAL_CHARACTER player=P{row.get('player')} character={row.get('character')}"
            )
            continue

        if event == "round_order":
            lines.append(
                f"{prefix} ROUND_ORDER order={row.get('order')} marker_owner=P{row.get('marker_owner')} "
                f"direction={row.get('marker_draft_direction')}"
            )
            continue

        if event == "turn":
            round_local_turn += 1
            game_turn_counter += 1
            lines.append(
                f"{prefix} TURN R{row.get('round_index')}T{round_local_turn} G{row.get('turn_index_global')} "
                f"player=P{row.get('player')} char={row.get('character')} "
                f"move={row.get('move')} {row.get('start_pos')}->{row.get('end_pos')}"
            )
            lines.append(f"           movement: {_fmt_turn_movement(row)}")
            lines.append(f"           landing: {_fmt_landing(row.get('landing'))}")
            lines.append(
                "           resources: "
                f"cash {row.get('cash_before')}->{row.get('cash_after')} | "
                f"shards {row.get('shards_before')}->{row.get('shards_after')} | "
                f"tiles {row.get('tiles_before')}->{row.get('tiles_after')} | "
                f"f {row.get('f_before')}->{row.get('f_after')}"
            )
            continue

        if event == "trick_used":
            lines.append(
                f"{prefix} TRICK_USED player=P{row.get('player')} card={_fmt_trick_card_name(row)} timing={row.get('timing')}"
            )
            continue

        if event == "mark_queued":
            payload = row.get("payload") or {}
            lines.append(
                f"{prefix} MARK_QUEUED src=P{row.get('source_player')} "
                f"target=P{row.get('target_player')}({row.get('target_character')}) "
                f"type={payload.get('type')}"
            )
            continue

        if event == "mark_blocked":
            lines.append(
                f"{prefix} MARK_BLOCKED player=P{row.get('player')} reason={row.get('reason')}"
            )
            continue

        if event in {"mark_target_none", "mark_target_missing", "mark_target_immune", "mark_target_empty"}:
            lines.append(f"{prefix} {event} actor=P{row.get('player')}")
            continue

        if event == "round_end_marker_management":
            lines.append(
                f"{prefix} ROUND_END_MARKER candidates={row.get('candidates')} chosen=P{row.get('chosen_player')} "
                f"character={row.get('character')}"
            )
            continue

        if event == "marker_moved":
            lines.append(
                f"{prefix} MARKER_MOVED P{row.get('from_owner')}->P{row.get('to_owner')} "
                f"direction={row.get('draft_direction')} flip_pending=P{row.get('marker_flip_pending_for')}"
            )
            continue

        if event == "marker_flip":
            decision = row.get("decision") or {}
            lines.append(
                f"{prefix} MARKER_FLIP owner=P{row.get('player')} chosen_card={decision.get('chosen_card')} "
                f"chosen_to={decision.get('chosen_to')}"
            )
            continue

        if event == "fortune_cleanup_before":
            lines.append(
                f"{prefix} FORTUNE_CLEANUP_BEFORE fortune={row.get('fortune')} "
                f"multiplier={row.get('multiplier')} payout={row.get('payout')} targets={row.get('targets')}"
            )
            continue

        if event == "fortune_cleanup_after":
            lines.append(
                f"{prefix} FORTUNE_CLEANUP_AFTER fortune={row.get('fortune')} "
                f"result={row.get('result_type')} affected={row.get('affected')}"
            )
            continue

        if event == "fortune.draw.resolve":
            lines.append(f"{prefix} FORTUNE_DRAW {_fmt_fortune_draw(row)}")
            continue

        if event == "fortune.card.apply":
            lines.append(f"{prefix} FORTUNE_APPLY {_fmt_fortune_apply(row)}")
            continue

        if event == "fortune.movement.resolve":
            lines.append(f"{prefix} FORTUNE_MOVE {_fmt_fortune_move(row)}")
            continue

        if event == "lap.reward.resolve":
            lines.append(f"{prefix} LAP_REWARD {_fmt_lap_reward(row)}")
            continue

        if event == "resource_f_change":
            lines.append(
                f"{prefix} F_CHANGE reason={row.get('reason')} source={row.get('source')} "
                f"{row.get('before')}->{row.get('after')} (delta={row.get('delta')})"
            )
            continue

        if event == "bankruptcy.resolve":
            lines.append(f"{prefix} BANKRUPTCY {_fmt_bankruptcy(row)}")
            continue

        if event == "game_end":
            lines.append(
                f"{prefix} GAME_END reason={row.get('end_reason')} winner_ids(log,1-based)={row.get('winner_ids')}"
            )
            continue

    lines.append("")
    lines.append(f"TOTAL_TURN_ROWS={game_turn_counter} / result.total_turns={result.total_turns}")
    lines.append(
        "NOTE result.total_turns counts global turn index progression; turn rows can differ when "
        "a base turn emits extra movement rows or skipped/dead players advance the cursor without a turn row."
    )
    return "\n".join(lines)


def run_single_game(
    seed: int,
    policy_mode: str,
    lap_policy_mode: str,
    player_count: int = DEFAULT_CONFIG.player_count,
) -> tuple[GameResult, str]:
    rng = random.Random(seed)
    policy = PolicyFactory.create_runtime_policy(
        policy_mode=policy_mode,
        lap_policy_mode=lap_policy_mode,
        rng=rng,
    )
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.player_count = player_count
    engine = GameEngine(config, policy, rng=rng, enable_logging=True)
    result = engine.run()
    report = build_timeline_report(seed, result, result.action_log)
    return result, report


def main() -> None:
    configure_utf8_io()
    parser = argparse.ArgumentParser(description="Run and validate one full game with strict timeline output.")
    parser.add_argument("--seed", type=int, default=424242)
    parser.add_argument(
        "--policy-mode",
        choices=["arena", "heuristic_v1", "heuristic_v2_token_opt", "heuristic_v2_control", "heuristic_v2_balanced"],
        default="arena",
    )
    parser.add_argument(
        "--lap-policy-mode",
        choices=["heuristic_v1", "heuristic_v2", "heuristic_v3_engine"],
        default="heuristic_v3_engine",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(
            Path("result")
            / "single_game_validation"
            / "strict_timeline_seed424242.txt"
        ),
    )
    parser.add_argument("--player-count", type=int, default=DEFAULT_CONFIG.player_count)
    args = parser.parse_args()

    _, report = run_single_game(
        seed=args.seed,
        policy_mode=args.policy_mode,
        lap_policy_mode=args.lap_policy_mode,
        player_count=args.player_count,
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"WROTE: {out_path.resolve()}")
    print(report)


if __name__ == "__main__":
    main()
