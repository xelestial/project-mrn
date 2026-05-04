from __future__ import annotations

from characters import CARD_TO_NAMES
from .phrase_dict import EVENT_LABELS_KO, LANDING_TYPE_LABELS_KO
from ..replay import ReplayProjection


def _tile_label(value: object) -> str:
    if isinstance(value, int):
        return f"{value + 1}번 칸"
    return str(value or "?")


def _draft_label(card_no: object) -> str:
    if not isinstance(card_no, int):
        return str(card_no or "?")
    names = CARD_TO_NAMES.get(card_no)
    if not names:
        return str(card_no)
    return f"{names[0]} / {names[1]}"


def _event_title(event_type: str) -> str:
    return EVENT_LABELS_KO.get(event_type, event_type.replace("_", " "))


def _landing_summary(event: dict) -> str:
    landing = event.get("landing") or {}
    ltype = str(landing.get("type", "") or "")
    return LANDING_TYPE_LABELS_KO.get(ltype, ltype or "도착 처리")


def _render_event_line(event: dict) -> str:
    event_type = event.get("event_type", "?")
    title = _event_title(event_type)
    actor = event.get("acting_player_id")
    actor_label = f"P{actor}" if actor is not None else "-"

    if event_type == "session_start":
        return f"- {title}: 플레이어 {event.get('player_count', '?')}명"

    if event_type == "weather_reveal":
        weather_name = event.get("weather_name") or event.get("weather") or event.get("card", "?")
        return f"- {title}: {weather_name}"

    if event_type == "draft_pick":
        return f"- {title} {actor_label}: {_draft_label(event.get('picked_card'))}"

    if event_type == "final_character_choice":
        return f"- {title} {actor_label}: {event.get('character', '?')}"

    if event_type == "turn_start":
        return f"- {title}: {event.get('turn_index', '?')}턴 / {actor_label}"

    if event_type == "trick_used":
        card_name = event.get("card_name", "?")
        description = str(event.get("card_description", "") or "").strip()
        if description:
            return f"- {title} {actor_label}: {card_name} - {description}"
        return f"- {title} {actor_label}: {card_name}"

    if event_type == "dice_roll":
        dice = event.get("dice_values") or event.get("dice") or []
        used_cards = event.get("cards_used") or event.get("used_cards") or []
        formula = event.get("formula") or ""
        total = event.get("total_move", event.get("move", event.get("total", "?")))
        if used_cards and not dice:
            return f"- {title} {actor_label}: 주사위 카드 {', '.join(map(str, used_cards))} 사용 -> {total}"
        if dice:
            return f"- {title} {actor_label}: 주사위 {', '.join(map(str, dice))} -> {total}"
        if formula:
            return f"- {title} {actor_label}: {formula} -> {total}"
        return f"- {title} {actor_label}: {total}"

    if event_type == "player_move":
        from_pos = event.get("from_tile_index", event.get("from_tile", event.get("from_pos", "?")))
        to_pos = event.get("to_tile_index", event.get("to_tile", event.get("to_pos", "?")))
        return f"- {title} {actor_label}: {_tile_label(from_pos)} -> {_tile_label(to_pos)}"

    if event_type == "landing_resolved":
        return f"- {title} {actor_label}: {_landing_summary(event)}"

    if event_type == "rent_paid":
        payer = event.get("payer_player_id", "?")
        owner = event.get("owner_player_id", "?")
        amount = event.get("final_amount", event.get("amount", "?"))
        tile_index = event.get("tile_index", "?")
        return f"- {title}: P{payer} -> P{owner} / {amount}냥 / {_tile_label(tile_index)}"

    if event_type == "tile_purchased":
        tile_index = event.get("tile_index", "?")
        cost = event.get("cost", "?")
        return f"- {title} {actor_label}: {_tile_label(tile_index)} / {cost}냥"

    if event_type == "fortune_drawn":
        return f"- {title}: {event.get('card_name', '?')}"

    if event_type == "fortune_resolved":
        resolution = event.get("resolution") or {}
        return f"- {title}: {resolution.get('type', 'resolved')}"

    if event_type == "mark_resolved":
        return f"- {title}: {event.get('effect_type', 'mark')}"

    if event_type == "marker_transferred":
        src = event.get("from_player_id", event.get("from_owner", "?"))
        dst = event.get("to_player_id", event.get("to_owner", event.get("new_owner_player_id", event.get("owner_player_id", "?"))))
        pending = event.get("marker_flip_pending_for")
        note = f"[징표]가 P{src}에서 P{dst}에게 이동함"
        if pending is not None:
            note += f" (P{pending}가 카드 Flip 대기)"
        return f"- {title}: {note}"

    if event_type == "marker_flip":
        card_no = event.get("card_no", "?")
        before = event.get("from_character", "?")
        after = event.get("to_character", "?")
        return f"- {title}: [징표]로 카드 {card_no}번이 {before}에서 {after}로 뒤집힘"

    if event_type == "lap_reward_chosen":
        amount = event.get("amount") or {}
        pieces = []
        if int(amount.get("cash", 0) or 0):
            pieces.append(f"현금 +{int(amount.get('cash', 0) or 0)}")
        if int(amount.get("shards", 0) or 0):
            pieces.append(f"조각 +{int(amount.get('shards', 0) or 0)}")
        if int(amount.get("coins", 0) or 0):
            pieces.append(f"승점 +{int(amount.get('coins', 0) or 0)}")
        return f"- {title} {actor_label}: {' / '.join(pieces) if pieces else event.get('choice', '?')}"

    if event_type == "f_value_change":
        before = float(event.get("before", 0.0) or 0.0)
        after = float(event.get("after", 0.0) or 0.0)
        return f"- {title}: {15 - before:.2f} -> {15 - after:.2f}"

    if event_type == "bankruptcy":
        return f"- {title}: {actor_label}"

    if event_type == "game_end":
        return f"- {title}: {event.get('reason', event.get('end_reason', '게임 종료'))}"

    detail_keys = [
        key
        for key in event
        if key
        not in {
            "event_type",
            "session_id",
            "round_index",
            "turn_index",
            "step_index",
            "acting_player_id",
            "public_phase",
        }
    ]
    detail = ", ".join(f"{key}={event[key]}" for key in detail_keys[:4])
    return f"- {title} {actor_label}: {detail}"


def _render_player_row(player: dict) -> str:
    tricks = ", ".join(player.get("public_tricks") or []) or "-"
    effects = ", ".join(player.get("public_effects", [])) or "-"
    hidden = int(player.get("hidden_trick_count", 0) or 0)
    remaining_dice = ", ".join(str(v) for v in (player.get("remaining_dice_cards") or [])) or "-"
    return (
        f"| P{player.get('player_id', '?')} | {player.get('character', '?')} | "
        f"{'생존' if player.get('alive') else '탈락'} | {_tile_label(player.get('position', '?'))} | "
        f"{player.get('cash', 0)} | {player.get('shards', 0)} | "
        f"{player.get('owned_tile_count', 0)} | {player.get('mark_status', 'clear')} | "
        f"{tricks} / 비공개 {hidden}장 | {remaining_dice} | {effects} |"
    )


def render_markdown(projection: ReplayProjection) -> str:
    session = projection.session
    total_turns = getattr(projection, "turn_count", len(getattr(projection, "turns", [])))
    total_rounds = getattr(projection, "round_count", len(getattr(projection, "rounds", [])))
    session_prelude = getattr(session, "prelude_events", [])
    lines: list[str] = []

    lines.append("# Engine 시각 리플레이")
    lines.append("")
    lines.append(f"- 세션: `{session.session_id}`")
    lines.append(f"- 전체 이벤트 수: `{session.total_events}`")
    lines.append(f"- 전체 턴 수: `{total_turns}`")
    lines.append(f"- 전체 라운드 수: `{total_rounds}`")
    if session.winner_player_id is not None:
        lines.append(f"- 승자: `P{session.winner_player_id}` ({session.end_reason})")

    if session_prelude:
        lines.append("")
        lines.append("## 게임 시작 전 공개 정보")
        lines.append("")
        for event in session_prelude:
            lines.append(_render_event_line(event))

    for round_replay in projection.rounds:
        lines.append("")
        weather_name = getattr(round_replay, "weather_name", getattr(round_replay, "weather", ""))
        weather_suffix = f" | 날씨: `{weather_name}`" if weather_name else ""
        lines.append(f"## {round_replay.round_index} 라운드{weather_suffix}")
        lines.append("")

        round_prelude = getattr(round_replay, "prelude_events", [])
        if round_prelude:
            lines.append("### 라운드 시작 공개 정보")
            lines.append("")
            for event in round_prelude:
                if event.get("event_type") == "round_start":
                    continue
                lines.append(_render_event_line(event))
            lines.append("")

        for turn in round_replay.turns:
            skipped_suffix = " (건너뜀)" if turn.skipped else ""
            lines.append(f"### {turn.turn_index} 턴 | P{turn.acting_player_id}{skipped_suffix}")
            lines.append("")
            if turn.key_events:
                for event in turn.key_events:
                    lines.append(_render_event_line(event))
            else:
                lines.append("- 공개된 핵심 이벤트 없음")
            lines.append("")

            if turn.player_states:
                lines.append("#### 플레이어 공개 상태")
                lines.append("")
                lines.append("| 플레이어 | 캐릭터 | 상태 | 위치 | 현금 | 조각 | 토지 수 | 지목 상태 | 공개/비공개 잔꾀 | 남은 주사위 카드 | 공개 효과 |")
                lines.append("|---|---|---|---|---:|---:|---:|---|---|---|---|")
                for player in turn.player_states:
                    lines.append(_render_player_row(player))
                lines.append("")

            if turn.board_state:
                board = turn.board_state
                lines.append(
                    f"> 종료 시간 {15 - float(board.get('f_value', 0.0) or 0.0):.2f} | "
                    f"징표 소유자 P{board.get('marker_owner_player_id', '?')}"
                )
                lines.append("")

    if session.game_end is not None:
        lines.append("## 게임 종료")
        lines.append("")
        lines.append(_render_event_line(session.game_end))

    return "\n".join(lines).strip() + "\n"
