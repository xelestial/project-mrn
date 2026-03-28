"""Phase 2 HTML replay renderer with event-first playback."""
from __future__ import annotations

from copy import deepcopy
import json

from characters import CARD_TO_NAMES
from weather_cards import load_weather_definitions
from ..replay import ReplayProjection


_PLAYER_COLORS = ["#4e8ef7", "#e85d5d", "#5dbf5d", "#f0a030"]
_PLAYER_LIGHTS = ["#1d355d", "#56252a", "#214827", "#5a4418"]
_TILE_LABELS = {"F1": "F", "F2": "F", "S": "S", "T2": "2", "T3": "3", "MALICIOUS": "M"}
_WEATHER_EFFECTS = {card.name: card.effect for card in load_weather_definitions()}
_DEFAULT_END_TIME_LIMIT = 15.0
_VISIBLE_FRAME_EVENTS = {
    "session_start",
    "round_start",
    "weather_reveal",
    "draft_pick",
    "final_character_choice",
    "turn_start",
    "dice_roll",
    "trick_used",
    "player_move",
    "landing_resolved",
    "rent_paid",
    "tile_purchased",
    "fortune_drawn",
    "fortune_resolved",
    "mark_resolved",
    "marker_transferred",
    "marker_flip",
    "lap_reward_chosen",
    "f_value_change",
    "bankruptcy",
    "turn_end_snapshot",
    "game_end",
}


def _draft_card_label(card_no: object) -> str:
    if not isinstance(card_no, int):
        return str(card_no or "")
    names = CARD_TO_NAMES.get(card_no)
    if not names:
        return str(card_no)
    left, right = names
    return f"{card_no}: {left} / {right}"


def _draft_card_names(card_no: object) -> str:
    if not isinstance(card_no, int):
        return str(card_no or "")
    names = CARD_TO_NAMES.get(card_no)
    if not names:
        return str(card_no)
    left, right = names
    return f"{left} / {right}"


def _remaining_end_time(f_value: float | int | None, threshold: float = _DEFAULT_END_TIME_LIMIT) -> float:
    return max(0.0, float(threshold) - float(f_value or 0.0))


def _format_end_time(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.2f}"


def _landing_summary(landing: dict | None) -> str:
    info = landing or {}
    ltype = str(info.get("type", "") or "")
    labels = {
        "PURCHASE": "토지 구매",
        "PURCHASE_FAIL": "토지 구매 실패",
        "PURCHASE_SKIP_POLICY": "구매 없이 턴 종료",
        "PURCHASE_BLOCKED_THIS_TURN": "토지 구매 불가",
        "RENT": "통행료 정산",
        "RENT_FAILSAFE": "통행료 정산",
        "FORTUNE": "운수 처리",
        "MARK": "지목 처리",
        "FORCE_SALE": "강제 매각",
        "NO_EFFECT": "효과 없음",
    }
    if ltype in labels:
        return labels[ltype]
    if "PURCHASE" in ltype:
        return "토지 구매 처리"
    if "RENT" in ltype:
        return "통행료 정산"
    if "FORTUNE" in ltype:
        return "운수 처리"
    if "MARK" in ltype:
        return "지목 처리"
    return ltype or "도착 처리"


def _frame_nav_subtitle(event: dict, shown: dict) -> str:
    etype = event.get("event_type")
    detail = str(shown.get("detail", "") or "").strip()
    if etype in {"dice_roll", "player_move", "trick_used", "marker_transferred", "marker_flip", "lap_reward_chosen", "fortune_drawn", "fortune_resolved", "rent_paid", "tile_purchased", "f_value_change"}:
        return detail
    if etype == "landing_resolved":
        return detail
    if etype == "turn_start":
        actor = event.get("acting_player_id")
        return f"P{actor} 행동 시작" if actor is not None else ""
    if etype == "turn_end_snapshot":
        return "턴 종료 스냅샷"
    if etype == "weather_reveal":
        return detail
    if etype == "round_start":
        return "새 라운드 시작"
    if etype == "session_start":
        return detail
    return detail


def _event_display(event: dict) -> dict:
    etype = event.get("event_type", "?")
    actor_id = event.get("acting_player_id")
    icons = {
        "session_start": "S",
        "round_start": "R",
        "weather_reveal": "W",
        "draft_pick": "D",
        "final_character_choice": "C",
        "turn_start": "T",
        "dice_roll": "R",
        "trick_used": "Z",
        "player_move": "M",
        "landing_resolved": "L",
        "rent_paid": "$",
        "tile_purchased": "+",
        "fortune_drawn": "F",
        "fortune_resolved": "F",
        "mark_resolved": "!",
        "marker_transferred": "K",
        "marker_flip": "V",
        "lap_reward_chosen": "P",
        "f_value_change": "F",
        "bankruptcy": "X",
        "turn_end_snapshot": "E",
        "game_end": "G",
    }
    detail = ""
    if etype == "session_start":
        detail = f"플레이어 {event.get('player_count', '?')}명"
    elif etype == "round_start":
        detail = f"{event.get('round_index', '?')} 라운드"
    elif etype == "weather_reveal":
        detail = event.get("weather_name") or event.get("weather") or event.get("card", "")
    elif etype == "draft_pick":
        detail = _draft_card_label(event.get("picked_card"))
    elif etype == "final_character_choice":
        detail = event.get("character", "")
    elif etype == "turn_start":
        detail = f"{event.get('turn_index', '?')} 턴"
    elif etype == "dice_roll":
        dice = event.get("dice_values") or event.get("dice") or []
        used_cards = event.get("used_cards") or []
        formula = event.get("formula") or ""
        total = event.get("total_move", event.get("move", event.get("total", "?")))
        if formula:
            if used_cards and not dice:
                detail = f"주사위 카드 {', '.join(map(str, used_cards))} 사용 -> {total}"
            elif dice and not used_cards:
                detail = f"주사위 {', '.join(map(str, dice))} -> {total}"
            else:
                detail = f"{formula} -> {total}"
        elif dice:
            detail = f"주사위 {', '.join(map(str, dice))} -> {total}"
        else:
            detail = f"{total}"
    elif etype == "trick_used":
        card_name = event.get("card_name", "?")
        description = str(event.get("card_description", "") or "").strip()
        resolution = event.get("resolution") or {}
        resolution_type = resolution.get("type")
        detail = f"{card_name}"
        if description:
            detail += f" - {description}"
        if resolution_type:
            detail += f" [{resolution_type}]"
    elif etype == "player_move":
        src = event.get("from_tile_index", event.get("from_tile", event.get("from_pos", "?")))
        dst = event.get("to_tile_index", event.get("to_tile", event.get("to_pos", "?")))
        src = src + 1 if isinstance(src, int) else src
        dst = dst + 1 if isinstance(dst, int) else dst
        detail = f"{src} -> {dst}"
    elif etype == "landing_resolved":
        detail = _landing_summary(event.get("landing"))
    elif etype == "rent_paid":
        payer = event.get("payer_player_id", event.get("payer", "?"))
        owner = event.get("owner_player_id", event.get("owner", "?"))
        amount = event.get("final_amount", event.get("amount", "?"))
        detail = f"P{payer} -> P{owner} {amount}"
    elif etype == "tile_purchased":
        tile_index = event.get("tile_index", "?")
        tile_label = tile_index + 1 if isinstance(tile_index, int) else tile_index
        detail = f"tile {tile_label} cost {event.get('cost', '?')}"
    elif etype == "fortune_drawn":
        detail = event.get("card_name", "")
    elif etype == "fortune_resolved":
        detail = str((event.get("resolution") or {}).get("type", "resolved"))
    elif etype == "mark_resolved":
        detail = str(event.get("effect_type", "mark"))
    elif etype == "marker_transferred":
        from_owner = event.get("from_owner", "?")
        to_owner = event.get("to_owner", event.get("new_owner_player_id", event.get("owner_player_id", "?")))
        pending = event.get("marker_flip_pending_for")
        detail = f"[징표]가 P{from_owner}에서 P{to_owner}에게 이동함"
        if pending is not None:
            detail += f" (P{pending}가 카드 Flip 대기)"
    elif etype == "marker_flip":
        card_no = event.get("card_no", "?")
        before = event.get("from_character", "?")
        after = event.get("to_character", "?")
        detail = f"[징표]로 카드 {card_no}번이 {before}에서 {after}로 뒤집힘"
    elif etype == "lap_reward_chosen":
        amount = event.get("amount") or {}
        cash = int(amount.get("cash", 0) or 0)
        shards = int(amount.get("shards", 0) or 0)
        coins = int(amount.get("coins", 0) or 0)
        pieces = []
        if cash:
            pieces.append(f"현금 +{cash}")
        if shards:
            pieces.append(f"조각 +{shards}")
        if coins:
            pieces.append(f"승점 +{coins}")
        detail = " / ".join(pieces) if pieces else str(event.get("choice", event.get("resource_delta", "")))
    elif etype == "f_value_change":
        before_remaining = _remaining_end_time(event.get("before", 0.0))
        after_remaining = _remaining_end_time(event.get("after", 0.0))
        detail = f"{_format_end_time(before_remaining)} -> {_format_end_time(after_remaining)}"
    elif etype == "bankruptcy":
        detail = "파산"
    elif etype == "turn_end_snapshot":
        detail = "턴 종료 스냅샷"
    elif etype == "game_end":
        detail = event.get("end_reason", event.get("reason", "게임 종료"))
    return {
        "event_type": etype,
        "event_label": _event_type_korean(etype),
        "icon": icons.get(etype, ">"),
        "actor": f"P{actor_id}" if actor_id is not None else "-",
        "actor_id": actor_id,
        "detail": detail,
    }


def _normalize_board(board: dict | None) -> dict:
    raw = deepcopy(board or {})
    tiles = list(raw.get("tiles", []))
    by_index = {int(tile.get("tile_index", idx)): deepcopy(tile) for idx, tile in enumerate(tiles)}
    fixed = []
    for idx in range(40):
        tile = by_index.get(idx, {"tile_index": idx, "tile_kind": "?"})
        tile.setdefault("tile_index", idx)
        tile.setdefault("tile_kind", "?")
        tile.setdefault("zone_color", "")
        tile.setdefault("owner_player_id", None)
        tile.setdefault("purchase_cost", None)
        tile.setdefault("rent_cost", None)
        tile.setdefault("score_coin_count", 0)
        fixed.append(tile)
    raw["tiles"] = fixed
    raw.setdefault("f_value", 0.0)
    raw.setdefault("marker_owner_player_id", None)
    raw.setdefault("round_index", 1)
    raw.setdefault("turn_index", 1)
    return raw


def _initial_board(proj: ReplayProjection) -> dict:
    for turn in proj.turns:
        if turn.board_state:
            board = _normalize_board(turn.board_state)
            for tile in board["tiles"]:
                tile["owner_player_id"] = None
                tile["score_coin_count"] = 0
                tile["pawn_player_ids"] = []
            board["f_value"] = 0.0
            return board
    return _normalize_board(None)


def _session_players(session_start: dict) -> list[dict]:
    players = deepcopy(session_start.get("players", []))
    for player in players:
        player.setdefault("player_id", 0)
        player.setdefault("display_name", f"Player {player.get('player_id', '?')}")
        player.setdefault("alive", True)
        player.setdefault("character", "")
        player.setdefault("position", 0)
        player.setdefault("cash", 0)
        player.setdefault("shards", 0)
        player.setdefault("hand_score_coins", 0)
        player.setdefault("placed_score_coins", 0)
        player.setdefault("owned_tile_count", 0)
        player.setdefault("public_tricks", [])
        player.setdefault("hidden_trick_count", 0)
        player.setdefault("mark_status", "clear")
        player.setdefault("public_effects", [])
        player.setdefault("burden_summary", [])
        player.setdefault("remaining_dice_cards", [1, 2, 3, 4, 5, 6])
    return players


def _apply_known_updates(event: dict, players: list[dict], board: dict) -> tuple[list[dict], dict]:
    players = deepcopy(players)
    board = _normalize_board(board)
    etype = event.get("event_type")
    if etype == "session_start" and event.get("players"):
        return _session_players(event), board
    if etype == "final_character_choice":
        pid = event.get("acting_player_id")
        for player in players:
            if player.get("player_id") == pid:
                player["character"] = event.get("character", player.get("character", ""))
                break
        return players, board
    if etype == "tile_purchased":
        tile_index = event.get("tile_index")
        if isinstance(tile_index, int) and 0 <= tile_index < 40:
            board["tiles"][tile_index]["owner_player_id"] = event.get("player_id", event.get("acting_player_id"))
        return players, board
    if etype == "marker_transferred":
        board["marker_owner_player_id"] = event.get(
            "to_owner",
            event.get("new_owner_player_id", event.get("owner_player_id")),
        )
        return players, board
    if etype == "f_value_change" and event.get("after") is not None:
        board["f_value"] = event["after"]
        return players, board
    if etype in {"turn_end_snapshot", "game_end"}:
        nested = event.get("snapshot") or {}
        snap_players = event.get("players") or nested.get("players")
        snap_board = event.get("board") or nested.get("board")
        if snap_players is not None:
            players = deepcopy(snap_players)
        if snap_board is not None:
            board = _normalize_board(snap_board)
        return players, board
    return players, board


def _frame_title(event: dict) -> str:
    etype = event.get("event_type")
    if etype == "session_start":
        return "게임 시작"
    if etype == "round_start":
        return f"{event.get('round_index', '?')} 라운드 시작"
    if etype == "weather_reveal":
        weather_name = event.get("weather_name") or event.get("weather") or event.get("card", "-")
        return f"날씨 공개 - {weather_name}"
    if etype == "draft_pick":
        return f"P{event.get('acting_player_id', '?')} 드래프트 선택"
    if etype == "final_character_choice":
        return f"P{event.get('acting_player_id', '?')} 최종 캐릭터 선택"
    if etype == "turn_start":
        return f"{event.get('turn_index', '?')} 턴 시작"
    if etype == "turn_end_snapshot":
        return f"{event.get('turn_index', '?')} 턴 종료"
    if etype == "marker_transferred":
        return "징표 이동"
    if etype == "marker_flip":
        return "징표 카드 뒤집기"
    if etype == "game_end":
        return "게임 종료"
    return _event_type_korean(etype)


def _event_type_korean(etype: str | None) -> str:
    labels = {
        "session_start": "게임 시작",
        "round_start": "라운드 시작",
        "weather_reveal": "날씨 공개",
        "draft_pick": "드래프트 선택",
        "final_character_choice": "최종 캐릭터 선택",
        "turn_start": "턴 시작",
        "trick_used": "잔꾀 사용",
        "dice_roll": "이동값 결정",
        "player_move": "말 이동",
        "landing_resolved": "도착 칸 처리",
        "rent_paid": "통행료 지불",
        "tile_purchased": "토지 구매",
        "fortune_drawn": "운수 카드 공개",
        "fortune_resolved": "운수 효과 처리",
        "mark_resolved": "지목 처리",
        "marker_transferred": "징표 이동",
        "marker_flip": "징표 카드 뒤집기",
        "lap_reward_chosen": "랩 보상 선택",
        "f_value_change": "종료 시간 변화",
        "bankruptcy": "파산",
        "turn_end_snapshot": "턴 종료",
        "game_end": "게임 종료",
    }
    return labels.get(etype or "", (etype or "").replace("_", " "))


def _frame_nav_label(event: dict) -> str:
    etype = event.get("event_type")
    if etype == "session_start":
        return "게임 시작"
    if etype == "round_start":
        return f"{event.get('round_index', '?')} 라운드 시작"
    if etype == "weather_reveal":
        return f"{event.get('round_index', '?')} 라운드, 날씨 공개"
    if etype == "draft_pick":
        return f"P{event.get('acting_player_id', '?')} 드래프트 선택 ({_draft_card_names(event.get('picked_card'))})"
    if etype == "final_character_choice":
        return f"P{event.get('acting_player_id', '?')} 최종 캐릭터 선택"
    if etype == "turn_start":
        return f"{event.get('turn_index', '?')} 턴 시작"
    if etype == "trick_used":
        return "잔꾀 사용"
    if etype == "dice_roll":
        return "이동값 결정"
    if etype == "landing_resolved":
        return "도착 칸 처리"
    if etype == "player_move":
        return "말 이동"
    if etype == "tile_purchased":
        return "토지 구매"
    if etype == "lap_reward_chosen":
        return "랩 보상 선택"
    if etype == "turn_end_snapshot":
        return f"{event.get('turn_index', '?')} 턴 종료"
    if etype == "marker_transferred":
        return "징표 이동"
    if etype == "marker_flip":
        return "징표 카드 뒤집기"
    if etype == "game_end":
        return "게임 종료"
    return _event_type_korean(etype)


def _build_turn_data(proj: ReplayProjection) -> list[dict]:
    data = []
    for turn in proj.turns:
        data.append(
            {
                "turn_index": turn.turn_index,
                "round_index": turn.round_index,
                "acting_player_id": turn.acting_player_id,
                "skipped": turn.skipped,
                "players": deepcopy(turn.player_states),
                "board": _normalize_board(turn.board_state),
                "events": [_event_display(event) for event in turn.key_events],
            }
        )
    return data


def _build_frames(proj: ReplayProjection) -> list[dict]:
    frames = []
    players = _session_players(proj.session.session_start)
    board = _initial_board(proj)
    recent = []
    current_weather = ""
    for event in proj.raw_events():
        if event.get("event_type") not in _VISIBLE_FRAME_EVENTS:
            continue
        current_weather = _frame_weather(event, current_weather)
        players, board = _apply_known_updates(event, players, board)
        shown = _event_display(event)
        recent.append(shown)
        recent = recent[-8:]
        frames.append(
            {
                "frame_index": len(frames),
                "event_type": event.get("event_type"),
                "round_index": event.get("round_index", 0),
                "turn_index": event.get("turn_index", 0),
                "acting_player_id": event.get("acting_player_id"),
                "title": _frame_title(event),
                "subtitle": shown["detail"],
                "nav_label": _frame_nav_label(event),
                "nav_subtitle": _frame_nav_subtitle(event, shown),
                "event": shown,
                "recent_events": deepcopy(recent),
                "players": deepcopy(players),
                "board": _normalize_board(board),
                "weather": current_weather,
                "weather_effect": _weather_effect_text(current_weather),
            }
        )
    return frames


def _build_meta(proj: ReplayProjection, frames: list[dict]) -> dict:
    session = proj.session
    return {
        "session_id": session.session_id,
        "total_events": session.total_events,
        "total_turns": len(session.turns),
        "total_rounds": len(session.rounds),
        "total_frames": len(frames),
        "winner_player_id": session.winner_player_id,
        "end_reason": session.end_reason,
        "end_time_limit": _DEFAULT_END_TIME_LIMIT,
    }


def _frame_weather(event: dict, current_weather: str) -> str:
    if event.get("event_type") == "weather_reveal":
        return event.get("weather_name") or event.get("weather") or event.get("card", "") or current_weather
    return current_weather


def _weather_effect_text(weather_name: str) -> str:
    return _WEATHER_EFFECTS.get(weather_name, "")


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Replay {session_id_short}</title>
<style>
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:"Segoe UI","Apple SD Gothic Neo",sans-serif; background:linear-gradient(180deg,#0a1020,#0c1322); color:#e7eefc; min-height:100vh; overflow:hidden; }
header { background:rgba(10,18,33,.96); border-bottom:1px solid #273755; padding:10px 16px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
h1 { font-size:1rem; color:#ffd060; }
.badge { background:#1c2943; border:1px solid #32486f; border-radius:999px; padding:3px 10px; font-size:.75rem; color:#c9d7f4; }
.badge.winner { color:#72e289; border-color:#72e289; }
.layout { display:grid; grid-template-columns:260px minmax(0,1fr) 290px; height:calc(100vh - 54px); }
.nav-panel,.players-panel { background:rgba(24,35,58,.96); padding:12px 10px; overflow-y:auto; }
.nav-panel { border-right:1px solid #273755; }
.players-panel { border-left:1px solid #273755; }
.main-panel { padding:10px; display:flex; flex-direction:column; gap:10px; min-height:0; overflow:hidden; }
.section,.legend-box,.player-card { background:rgba(24,35,58,.96); border:1px solid #273755; border-radius:14px; padding:10px; }
.sec-title { font-size:.72rem; color:#8aa5d8; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; }
.round-label { font-size:.7rem; color:#8aa5d8; text-transform:uppercase; letter-spacing:.08em; padding:6px 4px 4px; }
.frame-btn { width:100%; text-align:left; border:1px solid transparent; background:transparent; color:#c8d7f2; border-radius:10px; padding:6px 8px; cursor:pointer; margin-bottom:3px; font-size:.74rem; }
.frame-btn:hover { background:#15233c; border-color:#294067; }
.frame-btn.active { background:#243454; border-color:#ffd060; color:#ffd060; }
.frame-btn small { display:block; color:#93a7ce; margin-top:1px; font-size:.66rem; }
.frame-header,.progress-row,.legend-row,.stat-row,.chip-row,.controls { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.frame-header { justify-content:space-between; }
.frame-title { font-size:1rem; font-weight:700; }
.frame-sub,.status-sub { color:#93a7ce; font-size:.78rem; margin-top:4px; }
.progress-bar,.f-bar { flex:1; height:8px; background:#0c1525; border-radius:999px; overflow:hidden; }
.progress-fill { height:100%; width:0; background:linear-gradient(90deg,#4e8ef7,#73d0ff); }
.f-fill { height:100%; width:0; background:linear-gradient(90deg,#4e8ef7,#f0a030); }
.center-grid { display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:10px; min-height:0; }
.board-shell { background:linear-gradient(180deg,#10203a,#0f1830); border-radius:18px; border:1px solid #294067; padding:10px; min-height:0; display:flex; flex-direction:column; overflow:hidden; }
.board-track { display:grid; grid-template-columns:repeat(11,minmax(0,1fr)); grid-template-rows:repeat(11,minmax(0,1fr)); gap:4px; width:min(100%, calc(100vh - 190px)); height:min(100%, calc(100vh - 190px)); aspect-ratio:1; margin:0 auto; }
.board-center { grid-column:3 / span 7; grid-row:3 / span 7; border-radius:16px; border:1px solid #31507d; background:linear-gradient(180deg,rgba(17,31,52,.96),rgba(11,20,34,.96)); padding:10px; display:flex; flex-direction:column; gap:6px; overflow:hidden; }
.status-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; }
.status-card { background:rgba(15,23,39,.86); border:1px solid #294067; border-radius:12px; padding:7px; }
.status-label { font-size:.62rem; color:#93a7ce; text-transform:uppercase; letter-spacing:.08em; margin-bottom:4px; }
.status-value { font-size:.9rem; font-weight:700; }
.tile { border:1px solid #31486e; border-radius:10px; background:linear-gradient(180deg,rgba(16,26,42,.98),rgba(11,18,30,.96)); position:relative; padding:5px; overflow:hidden; min-width:0; min-height:0; }
.tile.owned { border-width:2px; }
.tile.special { box-shadow:inset 0 0 0 1px rgba(255,255,255,.08); }
.tile.current-event { box-shadow:0 0 0 3px rgba(255,208,96,.30); }
.tile-number { color:#f4f8ff; font-size:.58rem; font-weight:700; }
.tile-kind { display:block; margin-top:1px; font-size:.82rem; font-weight:700; line-height:1; }
.tile-center-label { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:16px 8px 14px; font-size:1rem; font-weight:800; color:#f4f8ff; text-align:center; pointer-events:none; }
.tile-s-fortune .tile-center-label,
.tile-finish .tile-center-label { font-size:1.02rem; letter-spacing:.02em; }
.tile-zone { margin-top:1px; font-size:.5rem; color:#89a1c9; }
.tile-meta { position:absolute; left:5px; right:5px; bottom:4px; font-size:.48rem; color:#c2d2ef; }
.tile-pawns { position:absolute; top:4px; right:4px; display:flex; gap:4px; flex-wrap:wrap; justify-content:flex-end; max-width:64px; }
.pawn-dot { width:18px; height:18px; border-radius:50%; border:2px solid rgba(255,255,255,.82); display:inline-flex; align-items:center; justify-content:center; font-size:10px; font-weight:800; line-height:1; color:#f7fbff; text-shadow:0 1px 2px rgba(0,0,0,.7); box-shadow:0 2px 8px rgba(0,0,0,.3); }
.pawn-dot.actor { width:22px; height:22px; border-color:#ffd060; box-shadow:0 0 0 2px rgba(255,208,96,.28), 0 2px 10px rgba(0,0,0,.35); }
.event-feed { display:flex; flex-direction:column; gap:4px; min-height:72px; }
.event-item { display:grid; grid-template-columns:18px 30px 96px minmax(0,1fr); gap:6px; align-items:center; font-size:.72rem; }
.event-type { color:#8aa5d8; }
.player-card.active { border-width:2px; }
.player-card.dead { opacity:.55; }
.player-name { font-weight:700; display:flex; align-items:center; justify-content:space-between; gap:8px; }
.player-character { color:#9bb0d8; margin-top:2px; font-size:.78rem; }
.chip,.mark { border-radius:999px; padding:2px 6px; font-size:.62rem; background:#0f1727; border:1px solid #355188; }
.mark-clear { background:#163321; color:#72e289; }
.mark-marked { background:#3d1920; color:#ff8f8f; }
.mark-immune { background:#1a2340; color:#87a8ff; }
.ctrl-btn { border:1px solid #355188; background:#182846; color:#e7eefc; border-radius:10px; padding:8px 10px; cursor:pointer; }
.ctrl-btn:disabled { opacity:.45; cursor:default; }
@media (max-width:1240px) { body { overflow:auto; } .layout { grid-template-columns:240px 1fr; height:auto; } .players-panel { grid-column:1 / span 2; border-left:none; border-top:1px solid #273755; } .center-grid { grid-template-columns:1fr; } .board-track { width:min(100%, calc(100vw - 320px)); height:auto; } }
@media (max-width:980px) { .layout { grid-template-columns:1fr; } .nav-panel { border-right:none; border-bottom:1px solid #273755; max-height:240px; } .players-panel { grid-column:auto; } }
</style>
</head>
<body>
<header>
  <h1>리플레이</h1>
  <span class="badge">세션 {session_id_short}</span>
  <span class="badge" id="frame-counter">0 / 0</span>
  <span class="badge">턴 {total_turns}</span>
  <span class="badge">라운드 {total_rounds}</span>
  {winner_badge}
</header>
<div class="layout">
  <aside class="nav-panel"><div class="sec-title">타임라인</div><div id="nav-list"></div></aside>
  <main class="main-panel">
    <section class="section">
      <div class="frame-header">
        <div><div class="frame-title" id="frame-title"></div><div class="frame-sub" id="frame-sub"></div></div>
        <div class="controls">
          <button class="ctrl-btn" id="btn-first" onclick="goToFrame(0)">처음</button>
          <button class="ctrl-btn" id="btn-prev" onclick="prevFrame()">이전</button>
          <button class="ctrl-btn" id="btn-next" onclick="nextFrame()">다음</button>
          <button class="ctrl-btn" id="btn-last" onclick="goToFrame(FRAMES.length - 1)">마지막</button>
        </div>
      </div>
      <div class="progress-row" style="margin-top:10px"><div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div><span id="progress-text">0%</span></div>
    </section>
    <div class="center-grid">
      <section class="board-shell"><div class="sec-title">보드</div><div class="board-track" id="board-track"></div></section>
      <div style="display:flex;flex-direction:column;gap:12px">
        <section class="legend-box">
          <div class="sec-title">현재 상황</div>
          <div class="legend-row"><span>날씨</span><strong id="legend-weather">-</strong></div>
          <div class="legend-row"><span>프레임</span><strong id="legend-frame">-</strong></div>
          <div class="legend-row"><span>라운드</span><strong id="legend-round">-</strong></div>
          <div class="legend-row"><span>턴</span><strong id="legend-turn">-</strong></div>
          <div class="legend-row"><span>행동 플레이어</span><strong id="legend-actor">-</strong></div>
          <div class="legend-row"><span>이벤트</span><strong id="legend-type">-</strong></div>
          <div class="legend-row"><span>징표 소유자</span><strong id="legend-marker">-</strong></div>
          <div class="legend-row"><span>종료 시간</span><strong id="legend-f">15</strong></div>
          <div class="f-bar" style="margin-top:8px"><div class="f-fill" id="f-fill"></div></div>
        </section>
        <section class="legend-box"><div class="sec-title">최근 이벤트</div><div class="event-feed" id="event-feed"></div></section>
      </div>
    </div>
  </main>
  <aside class="players-panel" id="players-panel"></aside>
</div>
<script>
const META = {meta_json};
const TURNS = {turns_json};
const FRAMES = {frames_json};
const END_TIME_LIMIT = Number(META.end_time_limit || 15);
const PLAYER_COLORS = {player_colors_json};
const PLAYER_LIGHTS = {player_lights_json};
const TILE_LABELS = {tile_labels_json};
let currentFrameIdx = 0;
function tilePosition(i) { if (i <= 10) return {row:1,col:i + 1}; if (i <= 19) return {row:i - 9,col:11}; if (i <= 30) return {row:11,col:31 - i}; return {row:41 - i,col:1}; }
function playerColor(id) { return id == null ? "#9bb0d8" : PLAYER_COLORS[(id - 1) % PLAYER_COLORS.length]; }
function remainingEndTime(value) { return Math.max(0, END_TIME_LIMIT - Number(value || 0)); }
function formatEndTime(value) { return Number.isInteger(value) ? String(value) : value.toFixed(2); }
function buildNav() {
  const host = document.getElementById("nav-list"); host.innerHTML = ""; let lastRound = null;
  FRAMES.forEach((frame, idx) => {
    const roundIndex = frame.round_index || 0;
    if (roundIndex !== lastRound) { lastRound = roundIndex; const label = document.createElement("div"); label.className = "round-label"; label.textContent = roundIndex > 0 ? `${roundIndex} 라운드` : "게임 시작"; host.appendChild(label); }
    const btn = document.createElement("button"); btn.className = "frame-btn"; btn.id = `frame-btn-${idx}`; btn.innerHTML = `${frame.nav_label}<small>${frame.nav_subtitle || frame.event_type}</small>`; btn.onclick = () => goToFrame(idx); host.appendChild(btn);
  });
}
function renderEventFeed(frame) {
  const feed = document.getElementById("event-feed"); const items = frame.recent_events || [];
  feed.innerHTML = items.length ? items.map((event) => `<div class="event-item"><div>${event.icon}</div><div style="color:${playerColor(event.actor_id)}">${event.actor}</div><div class="event-type">${event.event_label || event.event_type}</div><div>${event.detail}</div></div>`).join("") : '<div class="status-sub">아직 공개된 이벤트가 없습니다.</div>';
}
function renderBoard(frame) {
  const track = document.getElementById("board-track"); const board = frame.board || {}; const tiles = board.tiles || []; const players = frame.players || []; const pawnMap = new Map();
  players.forEach((player) => { if (player.alive === false) return; const pos = Number(player.position ?? 0); if (!pawnMap.has(pos)) pawnMap.set(pos, []); pawnMap.get(pos).push(player.player_id); });
  track.innerHTML = "";
  const weatherText = frame.weather || "-";
  const weatherEffect = frame.weather_effect || "";
  const remaining = remainingEndTime(board.f_value);
  const center = document.createElement("div"); center.className = "board-center"; center.innerHTML = `<div class="status-value">${frame.title}</div><div class="status-sub">${frame.subtitle || "-"}</div><div class="status-grid"><div class="status-card"><div class="status-label">현재 이벤트</div><div class="status-value">${frame.event.icon} ${frame.event.actor}</div><div class="status-sub">${frame.event.detail || "-"}</div></div><div class="status-card"><div class="status-label">프레임</div><div class="status-value">${frame.frame_index + 1} / ${FRAMES.length}</div><div class="status-sub">${frame.event.event_label || frame.event_type}</div></div><div class="status-card"><div class="status-label">라운드 / 턴 / 날씨</div><div class="status-value">${frame.round_index || "-"} 라운드 / ${frame.turn_index || "-"} 턴</div><div class="status-sub">${weatherText}</div><div class="status-sub">${weatherEffect || "-"}</div></div><div class="status-card"><div class="status-label">징표 소유자 / 종료 시간</div><div class="status-value">${board.marker_owner_player_id ? `P${board.marker_owner_player_id}` : "-"} / ${formatEndTime(remaining)}</div><div class="status-sub">공개 보드 상태</div></div></div>`; track.appendChild(center);
  let highlightedTile = null; if (frame.event_type === "player_move") { const parts = String(frame.event.detail || "").split("->"); if (parts.length === 2) highlightedTile = Number(parts[1].trim()) - 1; } if (frame.event_type === "tile_purchased") { const match = String(frame.event.detail || "").match(/tile\\s+(\\d+)/); if (match) highlightedTile = Number(match[1]) - 1; }
  for (let idx = 0; idx < 40; idx += 1) {
    const tile = tiles[idx] || {}; const pos = tilePosition(idx); const owner = tile.owner_player_id; const card = document.createElement("div"); card.className = "tile"; card.style.gridColumn = String(pos.col); card.style.gridRow = String(pos.row);
    if (owner != null) { const ci = (owner - 1) % PLAYER_COLORS.length; card.classList.add("owned"); card.style.borderColor = PLAYER_COLORS[ci]; card.style.background = `linear-gradient(180deg, ${PLAYER_LIGHTS[ci]}, #101a2d)`; }
    if (["F1", "F2", "S"].includes(tile.tile_kind)) card.classList.add("special");
    if (highlightedTile === idx) card.classList.add("current-event");
    const pawns = pawnMap.get(idx) || [];
    const pawnMarkup = pawns
      .map((pid) => `<span class="pawn-dot${pid === frame.acting_player_id ? " actor" : ""}" style="background:${playerColor(pid)}" title="P${pid}">${pid}</span>`)
      .join("");
    const meta = []; if (owner != null) meta.push(`P${owner}`); if (tile.rent_cost != null) meta.push(`R${tile.rent_cost}`); if ((tile.score_coin_count || 0) > 0) meta.push(`C${tile.score_coin_count}`);
    const isFortune = tile.tile_kind === "S";
    const isFinish = tile.tile_kind === "F1" || tile.tile_kind === "F2";
    if (isFortune) card.classList.add("tile-s-fortune");
    if (isFinish) card.classList.add("tile-finish");
    const centerText = isFortune ? "운수" : tile.tile_kind === "F1" ? "종료 - 1" : tile.tile_kind === "F2" ? "종료 - 2" : "";
    const centerLabel = centerText ? `<div class="tile-center-label">${centerText}</div>` : "";
    const zoneMarkup = (isFortune || isFinish) ? "" : `<div class="tile-zone">${tile.zone_color || "-"}</div>`;
    const metaMarkup = (isFortune || isFinish) ? "" : `<div class="tile-meta">${meta.join(" ") || "-"}</div>`;
    card.innerHTML = `<div class="tile-number">${idx + 1}</div>${centerLabel}${zoneMarkup}<div class="tile-pawns">${pawnMarkup}</div>${metaMarkup}`; track.appendChild(card);
  }
}
function renderPlayers(frame) {
  const panel = document.getElementById("players-panel"); panel.innerHTML = '<div class="sec-title">플레이어</div>'; const actorId = frame.acting_player_id;
  (frame.players || []).forEach((player) => {
    const pid = player.player_id; const color = playerColor(pid); const markStatus = player.mark_status || "clear"; const publicTricks = (player.public_tricks || []).join(", ") || "-"; const hiddenCount = Number(player.hidden_trick_count || 0); const effects = player.public_effects || []; const remainingDice = (player.remaining_dice_cards || []).join(", ") || "-"; const card = document.createElement("div");
    card.className = "player-card" + (pid === actorId ? " active" : "") + (player.alive === false ? " dead" : ""); if (pid === actorId) card.style.borderColor = color;
    card.innerHTML = `<div class="player-name" style="color:${color}"><span>P${pid}</span><span>${player.alive === false ? "탈락" : `타일 ${Number(player.position || 0) + 1}`}</span></div><div class="player-character">${player.character || "-"}</div><div class="status-sub">${player.display_name || `Player ${pid}`}</div><div class="stat-row" style="margin-top:6px"><span class="chip">$ ${player.cash ?? "?"}</span><span class="chip">Sh ${player.shards ?? "?"}</span><span class="chip">승점 보유 ${player.hand_score_coins ?? "?"}</span><span class="chip">승점 배치 ${player.placed_score_coins ?? "?"}</span><span class="chip">타일 ${player.owned_tile_count ?? "?"}</span></div><div style="margin-top:6px"><span class="mark mark-${markStatus}">${markStatus}</span></div><div class="status-sub" style="margin-top:6px">공개 잔꾀: ${publicTricks}</div><div class="status-sub">비공개 잔꾀: ${hiddenCount}장</div><div class="status-sub">남은 주사위 카드: ${remainingDice}</div>${player.pending_mark_source ? `<div class="status-sub">지목 출처: P${player.pending_mark_source}</div>` : ""}${effects.length ? `<div class="chip-row" style="margin-top:6px">${effects.map((name) => `<span class="chip">${name}</span>`).join("")}</div>` : ""}`; panel.appendChild(card);
  });
}
function renderFrame(idx) {
  currentFrameIdx = idx; const frame = FRAMES[idx];
  document.getElementById("frame-title").textContent = frame.title; document.getElementById("frame-sub").textContent = frame.subtitle || ""; document.getElementById("frame-counter").textContent = `${idx + 1} / ${FRAMES.length}`;
  const remaining = remainingEndTime(frame.board.f_value);
  document.getElementById("legend-weather").textContent = frame.weather || "-"; document.getElementById("legend-frame").textContent = `${idx + 1} / ${FRAMES.length}`; document.getElementById("legend-round").textContent = frame.round_index || "-"; document.getElementById("legend-turn").textContent = frame.turn_index || "-"; document.getElementById("legend-actor").textContent = frame.acting_player_id ? `P${frame.acting_player_id}` : "-"; document.getElementById("legend-type").textContent = frame.event.event_label || frame.event_type; document.getElementById("legend-marker").textContent = frame.board.marker_owner_player_id ? `P${frame.board.marker_owner_player_id}` : "-"; document.getElementById("legend-f").textContent = formatEndTime(remaining); document.getElementById("f-fill").style.width = `${Math.max(0, Math.min(100, (remaining / END_TIME_LIMIT) * 100))}%`; document.getElementById("progress-fill").style.width = `${FRAMES.length > 1 ? (idx / (FRAMES.length - 1)) * 100 : 0}%`; document.getElementById("progress-text").textContent = `${Math.round(FRAMES.length > 1 ? (idx / (FRAMES.length - 1)) * 100 : 0)}%`;
  renderEventFeed(frame); renderBoard(frame); renderPlayers(frame);
  document.querySelectorAll(".frame-btn").forEach((button) => button.classList.remove("active")); const active = document.getElementById(`frame-btn-${idx}`); if (active) { active.classList.add("active"); active.scrollIntoView({ block: "nearest" }); }
  document.getElementById("btn-first").disabled = idx === 0; document.getElementById("btn-prev").disabled = idx === 0; document.getElementById("btn-next").disabled = idx === FRAMES.length - 1; document.getElementById("btn-last").disabled = idx === FRAMES.length - 1;
}
function goToFrame(idx) { if (idx >= 0 && idx < FRAMES.length) renderFrame(idx); }
function prevFrame() { goToFrame(currentFrameIdx - 1); }
function nextFrame() { goToFrame(currentFrameIdx + 1); }
document.addEventListener("keydown", (event) => { if (event.key === "ArrowRight" || event.key === "ArrowDown") nextFrame(); if (event.key === "ArrowLeft" || event.key === "ArrowUp") prevFrame(); if (event.key === "Home") goToFrame(0); if (event.key === "End") goToFrame(FRAMES.length - 1); });
buildNav(); if (FRAMES.length > 0) renderFrame(0);
</script>
</body>
</html>
"""


def render_html(proj: ReplayProjection) -> str:
    """Render the replay as a self-contained HTML timeline."""
    session = proj.session
    session_id_short = session.session_id[:8] if session.session_id else "unknown"
    turns = _build_turn_data(proj)
    frames = _build_frames(proj)
    meta = _build_meta(proj, frames)
    winner_badge = (
        f'<span class="badge winner">P{session.winner_player_id} 승리</span>'
        if session.winner_player_id is not None
        else ""
    )
    replacements = {
        "{session_id_short}": session_id_short,
        "{total_turns}": str(meta["total_turns"]),
        "{total_rounds}": str(meta["total_rounds"]),
        "{winner_badge}": winner_badge,
        "{meta_json}": json.dumps(meta, ensure_ascii=False),
        "{turns_json}": json.dumps(turns, ensure_ascii=False),
        "{frames_json}": json.dumps(frames, ensure_ascii=False),
        "{player_colors_json}": json.dumps(_PLAYER_COLORS, ensure_ascii=False),
        "{player_lights_json}": json.dumps(_PLAYER_LIGHTS, ensure_ascii=False),
        "{tile_labels_json}": json.dumps(_TILE_LABELS, ensure_ascii=False),
    }
    html = _HTML_TEMPLATE
    for needle, value in replacements.items():
        html = html.replace(needle, value)
    return html

