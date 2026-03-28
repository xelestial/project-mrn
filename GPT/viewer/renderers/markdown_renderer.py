from __future__ import annotations

from ..replay import ReplayProjection


def _render_event_line(event: dict) -> str:
    event_type = event.get("event_type", "?")
    actor = event.get("acting_player_id")
    actor_label = f"P{actor}" if actor is not None else "-"

    if event_type == "dice_roll":
        values = event.get("dice_values", [])
        total = event.get("total", sum(values) if values else 0)
        return f"- `{event_type}` {actor_label}: {values} -> {total}"

    if event_type == "player_move":
        from_pos = event.get("from_pos", "?")
        to_pos = event.get("to_pos", "?")
        path = event.get("path", [])
        path_note = " -> ".join(str(pos) for pos in path) if path else f"{from_pos} -> {to_pos}"
        return f"- `{event_type}` {actor_label}: {path_note}"

    if event_type == "rent_paid":
        payer = event.get("payer_player_id", "?")
        owner = event.get("owner_player_id", "?")
        amount = event.get("final_amount", event.get("amount", "?"))
        tile_index = event.get("tile_index", "?")
        return f"- `{event_type}` P{payer} -> P{owner}: {amount} on tile {tile_index}"

    if event_type == "tile_purchased":
        tile_index = event.get("tile_index", "?")
        cost = event.get("cost", "?")
        return f"- `{event_type}` {actor_label}: tile {tile_index} for {cost}"

    if event_type == "lap_reward_chosen":
        choice = event.get("choice", "?")
        amount = event.get("amount", "?")
        return f"- `{event_type}` {actor_label}: {choice} x {amount}"

    if event_type == "weather_reveal":
        weather_name = event.get("weather_name", event.get("card", "?"))
        return f"- `{event_type}`: {weather_name}"

    if event_type == "final_character_choice":
        character = event.get("character", "?")
        return f"- `{event_type}` {actor_label}: {character}"

    detail_keys = [
        key
        for key in event
        if key not in {"event_type", "session_id", "round_index", "turn_index", "step_index", "acting_player_id", "public_phase"}
    ]
    detail = ", ".join(f"{key}={event[key]}" for key in detail_keys[:4])
    return f"- `{event_type}` {actor_label}: {detail}"


def _render_player_row(player: dict) -> str:
    tricks = ", ".join(player.get("public_tricks") or []) or "-"
    effects = ", ".join(player.get("public_effects", [])) or "-"
    return (
        f"| P{player.get('player_id', '?')} | {player.get('character', '?')} | "
        f"{'alive' if player.get('alive') else 'dead'} | {player.get('position', '?')} | "
        f"{player.get('cash', 0)} | {player.get('shards', 0)} | "
        f"{player.get('owned_tile_count', 0)} | {player.get('mark_status', 'clear')} | "
        f"{tricks} [{player.get('hidden_trick_count', 0)}H] | {effects} |"
    )


def render_markdown(projection: ReplayProjection) -> str:
    session = projection.session
    total_turns = getattr(projection, "turn_count", len(getattr(projection, "turns", [])))
    total_rounds = getattr(projection, "round_count", len(getattr(projection, "rounds", [])))
    session_prelude = getattr(session, "prelude_events", [])
    lines: list[str] = []

    lines.append("# GPT Visual Replay")
    lines.append("")
    lines.append(f"- Session: `{session.session_id}`")
    lines.append(f"- Total events: `{session.total_events}`")
    lines.append(f"- Total turns: `{total_turns}`")
    lines.append(f"- Total rounds: `{total_rounds}`")
    if session.winner_player_id is not None:
        lines.append(f"- Winner: `P{session.winner_player_id}` ({session.end_reason})")

    if session_prelude:
        lines.append("")
        lines.append("## Session Prelude")
        lines.append("")
        for event in session_prelude:
            lines.append(_render_event_line(event))

    for round_replay in projection.rounds:
        lines.append("")
        weather_name = getattr(round_replay, "weather_name", getattr(round_replay, "weather", ""))
        weather_suffix = f" | weather: `{weather_name}`" if weather_name else ""
        lines.append(f"## Round {round_replay.round_index}{weather_suffix}")
        lines.append("")

        round_prelude = getattr(round_replay, "prelude_events", [])
        if round_prelude:
            lines.append("### Round Prelude")
            lines.append("")
            for event in round_prelude:
                if event.get("event_type") == "round_start":
                    continue
                lines.append(_render_event_line(event))
            lines.append("")

        for turn in round_replay.turns:
            skipped_suffix = " (skipped)" if turn.skipped else ""
            lines.append(f"### Turn {turn.turn_index} | P{turn.acting_player_id}{skipped_suffix}")
            lines.append("")
            if turn.key_events:
                for event in turn.key_events:
                    lines.append(_render_event_line(event))
            else:
                lines.append("- No public key events")
            lines.append("")

            if turn.player_states:
                lines.append("#### Player Snapshot")
                lines.append("")
                lines.append("| Player | Character | Alive | Pos | Cash | Shards | Tiles | Mark | Tricks | Effects |")
                lines.append("|---|---|---|---:|---:|---:|---:|---|---|---|")
                for player in turn.player_states:
                    lines.append(_render_player_row(player))
                lines.append("")

            if turn.board_state:
                board = turn.board_state
                lines.append(
                    f"> F={board.get('f_value', '?')} | marker=P{board.get('marker_owner_player_id', '?')}"
                )
                lines.append("")

    if session.game_end is not None:
        lines.append("## Game End")
        lines.append("")
        lines.append(_render_event_line(session.game_end))

    return "\n".join(lines).strip() + "\n"
