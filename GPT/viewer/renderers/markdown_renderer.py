"""Phase 2 — Markdown replay renderer.

Produces a human-readable turn-by-turn replay document from a ReplayProjection.

Usage:
    from viewer.replay import ReplayProjection
    from viewer.renderers.markdown_renderer import render_markdown

    proj = ReplayProjection.from_jsonl("replay.jsonl")
    md = render_markdown(proj)
    with open("replay.md", "w", encoding="utf-8") as f:
        f.write(md)
"""
from __future__ import annotations

from ..replay import ReplayProjection, TurnReplay


# ---------------------------------------------------------------------------
# Event → markdown line
# ---------------------------------------------------------------------------

def _event_line(e: dict) -> str:
    etype = e.get("event_type", "?")
    pid = e.get("acting_player_id")
    actor = f"P{pid}" if pid is not None else "—"

    if etype == "dice_roll":
        vals = e.get("dice_values", [])
        total = e.get("total", sum(vals) if vals else 0)
        cards = e.get("cards_used", [])
        card_note = f" (카드 {cards})" if cards else ""
        return f"  🎲 {actor} 주사위: {vals} → 합계 {total}{card_note}"

    if etype == "player_move":
        frm = e.get("from_pos", "?")
        to = e.get("to_pos", "?")
        path = e.get("path", [])
        lapped = " **[랩 통과!]**" if e.get("lapped") else ""
        path_str = " → ".join(str(t) for t in path) if path else f"{frm}→{to}"
        return f"  🚶 {actor} 이동: {path_str}{lapped}"

    if etype == "landing_resolved":
        tile = e.get("tile_index", "?")
        kind = e.get("tile_kind", "?")
        return f"  📍 {actor} 착지: tile {tile} ({kind})"

    if etype == "rent_paid":
        payer = e.get("payer_player_id", e.get("payer", "?"))
        owner = e.get("owner_player_id", e.get("owner", "?"))
        base = e.get("base_amount", "?")
        final = e.get("final_amount", base)
        tile = e.get("tile_index", "?")
        mods = e.get("modifiers", [])
        mod_note = f" [{', '.join(mods)}]" if mods else ""
        amount_note = f"{final}" if final == base else f"{final} (기본 {base}){mod_note}"
        return f"  💸 P{payer} → P{owner} 렌트 {amount_note} (tile {tile})"

    if etype == "tile_purchased":
        tile = e.get("tile_index", "?")
        cost = e.get("cost", "?")
        kind = e.get("kind", e.get("tile_kind", "?"))
        source = e.get("source", "landing")
        return f"  🏠 {actor} 구매: tile {tile} ({kind}) −{cost} [{source}]"

    if etype == "fortune_drawn":
        card = e.get("card_name", "?")
        summary = e.get("card_effect_summary", e.get("public_summary", ""))
        return f"  🃏 {actor} 운수 드로우: **{card}**" + (f" — {summary}" if summary else "")

    if etype == "fortune_resolved":
        summary = e.get("effect_summary", e.get("public_summary", ""))
        return f"  ✨ {actor} 운수 효과 적용" + (f": {summary}" if summary else "")

    if etype == "f_value_change":
        before = e.get("before", "?")
        after = e.get("after", "?")
        delta = e.get("delta", "")
        reason = e.get("reason", "")
        delta_str = f" (Δ{delta:+.1f})" if isinstance(delta, (int, float)) else ""
        return f"  📊 F값: {before} → {after}{delta_str} ({reason})"

    if etype == "lap_reward_chosen":
        choice = e.get("choice", "?")
        amount = e.get("amount", "?")
        return f"  🎁 {actor} 랩 보상: **{choice}** ×{amount}"

    if etype == "mark_resolved":
        src = e.get("source_player_id", e.get("source", "?"))
        tgt = e.get("target_player_id", e.get("target", "?"))
        success = "✓" if e.get("success") else "✗"
        effect = e.get("effect_type", "?")
        summary = e.get("outcome_summary", e.get("public_summary", ""))
        result = f" — {summary}" if summary else ""
        return f"  🎯 P{src}→P{tgt} 지목 {success} ({effect}){result}"

    if etype == "marker_transferred":
        frm = e.get("from_player", e.get("from_player_id", "?"))
        to = e.get("to_player", e.get("to_player_id", "?"))
        reason = e.get("reason", "")
        return f"  🏷️ 징표 이전: P{frm} → P{to} ({reason})"

    if etype == "bankruptcy":
        return f"  💀 **P{pid} 파산**"

    if etype == "weather_reveal":
        weather = e.get("weather_name", e.get("card", "?"))
        effect = e.get("effect_summary", "")
        return f"  🌤️ 날씨: **{weather}**" + (f" — {effect}" if effect else "")

    if etype == "draft_pick":
        character = e.get("character", e.get("choice", "?"))
        return f"  🃏 {actor} 드래프트: {character}"

    if etype == "final_character_choice":
        character = e.get("character", "?")
        return f"  👤 {actor} 최종 캐릭터: **{character}**"

    # fallback
    payload_keys = [k for k in e if k not in {
        "event_type", "session_id", "round_index", "turn_index",
        "step_index", "acting_player_id", "public_phase",
    }]
    kv = ", ".join(f"{k}={e[k]}" for k in payload_keys[:4])
    return f"  [{etype}] {actor} — {kv}"


# ---------------------------------------------------------------------------
# Player state → table row
# ---------------------------------------------------------------------------

def _player_row(p: dict) -> str:
    pid = p.get("player_id", "?")
    char = p.get("character", "?")
    alive_sym = "✓" if p.get("alive") else "💀"
    pos = p.get("position", "?")
    cash = p.get("cash", 0)
    shards = p.get("shards", 0)
    h_coins = p.get("hand_score_coins", 0)
    p_coins = p.get("placed_score_coins", 0)
    tiles = p.get("owned_tile_count", 0)
    pub_tricks = ", ".join(p.get("public_tricks", [])) or "—"
    hidden = p.get("hidden_trick_count", 0)
    mark = p.get("mark_status", "clear")
    effects = ", ".join(p.get("public_effects", [])) or "—"
    return (
        f"| P{pid} ({char}) | {alive_sym} | {pos} | "
        f"💰{cash} 🔮{shards} 🪙{h_coins}+{p_coins} | "
        f"🏠{tiles} | {pub_tricks}[{hidden}H] | {mark} | {effects} |"
    )


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_markdown(proj: ReplayProjection) -> str:
    session = proj.session
    lines: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines += [
        "# 게임 리플레이",
        "",
        f"- **세션 ID**: `{session.session_id}`",
        f"- **총 이벤트**: {session.total_events}",
        f"- **총 턴수**: {len(session.turns)}",
        f"- **라운드**: {len(session.rounds)}",
    ]

    if session.winner_player_id is not None:
        lines.append(f"- **최종 결과**: P{session.winner_player_id} 승리 ({session.end_reason})")
    elif session.game_end:
        lines.append(f"- **최종 결과**: {session.end_reason or '게임 종료'}")

    # Draft summary
    draft_events = proj.events_by_type("final_character_choice")
    if draft_events:
        lines += ["", "## 캐릭터 배정", ""]
        for e in draft_events:
            pid = e.get("acting_player_id", "?")
            char = e.get("character", "?")
            lines.append(f"- P{pid}: **{char}**")

    lines += ["", "---", ""]

    # ── Rounds & Turns ───────────────────────────────────────────────────────
    for rnd in session.rounds:
        weather_note = f" — 날씨: *{rnd.weather}*" if rnd.weather else ""
        lines += [f"## Round {rnd.round_index}{weather_note}", ""]

        for turn in rnd.turns:
            pid = turn.acting_player_id
            skip_note = " *(건너뜀)*" if turn.skipped else ""
            lines += [f"### Turn {turn.turn_index} — P{pid}{skip_note}", ""]

            key = turn.key_events
            if key:
                for e in key:
                    lines.append(_event_line(e))
                lines.append("")

            # Player snapshot table
            if turn.player_states:
                lines += [
                    "**턴 종료 상태**",
                    "",
                    "| 플레이어 | 생존 | 위치 | 자원 | 타일 | 잔꾀 | 지목 | 효과 |",
                    "|---------|------|------|------|------|------|------|------|",
                ]
                for p in turn.player_states:
                    lines.append(_player_row(p))

                board = turn.board_state
                if board:
                    f_val = board.get("f_value", "?")
                    marker = board.get("marker_owner_player_id", "?")
                    lines += ["", f"> F값: **{f_val}** | 징표: **P{marker}**"]

                lines.append("")

    # ── Turns outside any round (edge case) ─────────────────────────────────
    round_turn_set = {id(t) for r in session.rounds for t in r.turns}
    orphan_turns = [t for t in session.turns if id(t) not in round_turn_set]
    if orphan_turns:
        lines += ["## (라운드 미분류 턴)", ""]
        for turn in orphan_turns:
            lines += [f"### Turn {turn.turn_index}", ""]
            for e in turn.key_events:
                lines.append(_event_line(e))
            lines.append("")

    lines += ["---", "", "*리플레이 종료*"]
    return "\n".join(lines)
