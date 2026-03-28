"""Phase 2 — HTML replay renderer.

Produces a self-contained single-file HTML page that embeds all turn data as
JSON and uses vanilla JavaScript for step-through navigation.

Usage:
    from viewer.replay import ReplayProjection
    from viewer.renderers.html_renderer import render_html

    proj = ReplayProjection.from_jsonl("replay.jsonl")
    html = render_html(proj)
    with open("replay.html", "w", encoding="utf-8") as f:
        f.write(html)
"""
from __future__ import annotations

import json

from ..replay import ReplayProjection


# ---------------------------------------------------------------------------
# Event → display text (for JS consumption via pre-serialised strings)
# ---------------------------------------------------------------------------

def _event_display(e: dict) -> dict:
    """Return a compact display dict for one event (used in JS event feed)."""
    etype = e.get("event_type", "?")
    pid = e.get("acting_player_id")
    actor = f"P{pid}" if pid is not None else "—"

    icons = {
        "dice_roll": "🎲",
        "player_move": "🚶",
        "landing_resolved": "📍",
        "rent_paid": "💸",
        "tile_purchased": "🏠",
        "fortune_drawn": "🃏",
        "fortune_resolved": "✨",
        "f_value_change": "📊",
        "lap_reward_chosen": "🎁",
        "mark_resolved": "🎯",
        "marker_transferred": "🏷️",
        "bankruptcy": "💀",
        "weather_reveal": "🌤️",
        "draft_pick": "🃏",
        "final_character_choice": "👤",
    }
    icon = icons.get(etype, "▸")

    detail = ""
    if etype == "dice_roll":
        vals = e.get("dice_values", [])
        total = e.get("total", sum(vals) if vals else 0)
        detail = f"주사위 {vals} = {total}"
    elif etype == "player_move":
        frm = e.get("from_pos", "?")
        to = e.get("to_pos", "?")
        lapped = " [랩!]" if e.get("lapped") else ""
        detail = f"이동 {frm}→{to}{lapped}"
    elif etype == "landing_resolved":
        tile = e.get("tile_index", "?")
        kind = e.get("tile_kind", "?")
        detail = f"착지 tile {tile} ({kind})"
    elif etype == "rent_paid":
        payer = e.get("payer_player_id", e.get("payer", "?"))
        owner = e.get("owner_player_id", e.get("owner", "?"))
        amount = e.get("final_amount", e.get("amount", "?"))
        detail = f"P{payer}→P{owner} 렌트 {amount}"
    elif etype == "tile_purchased":
        tile = e.get("tile_index", "?")
        cost = e.get("cost", "?")
        detail = f"tile {tile} 구매 −{cost}"
    elif etype == "fortune_drawn":
        card = e.get("card_name", "?")
        detail = f"{card}"
    elif etype == "f_value_change":
        before = e.get("before", "?")
        after = e.get("after", "?")
        detail = f"F {before}→{after}"
    elif etype == "lap_reward_chosen":
        choice = e.get("choice", "?")
        amount = e.get("amount", "?")
        detail = f"{choice} ×{amount}"
    elif etype == "mark_resolved":
        src = e.get("source_player_id", e.get("source", "?"))
        tgt = e.get("target_player_id", e.get("target", "?"))
        ok = "✓" if e.get("success") else "✗"
        detail = f"P{src}→P{tgt} {ok}"
    elif etype == "bankruptcy":
        detail = f"파산"
    elif etype == "weather_reveal":
        detail = e.get("weather_name", e.get("card", ""))
    elif etype == "final_character_choice":
        detail = e.get("character", "?")

    return {
        "icon": icon,
        "actor": actor,
        "type": etype,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Build serialisable turn data
# ---------------------------------------------------------------------------

def _build_turn_data(proj: ReplayProjection) -> list[dict]:
    """Convert all TurnReplays into plain dicts for JSON embedding."""
    result = []
    for turn in proj.turns:
        board = turn.board_state or {}
        result.append({
            "turn_index": turn.turn_index,
            "round_index": turn.round_index,
            "acting_player_id": turn.acting_player_id,
            "skipped": turn.skipped,
            "players": turn.player_states,
            "board": board,
            "events": [_event_display(e) for e in turn.key_events],
            # tiles with owners for quick board rendering
            "owned_tiles": _owned_tiles(board),
            "pawn_positions": _pawn_positions(board),
        })
    return result


def _owned_tiles(board: dict) -> dict:
    """Return {tile_index: owner_player_id} for tiles with owners."""
    result: dict[str, int] = {}
    for tile in board.get("tiles", []):
        owner = tile.get("owner_player_id")
        if owner is not None:
            result[str(tile.get("tile_index", 0))] = owner
    return result


def _pawn_positions(board: dict) -> dict:
    """Return {tile_index: [player_ids]} for tiles with pawns."""
    result: dict[str, list[int]] = {}
    for tile in board.get("tiles", []):
        pawns = tile.get("pawn_player_ids", [])
        if pawns:
            result[str(tile.get("tile_index", 0))] = pawns
    return result


def _build_meta(proj: ReplayProjection) -> dict:
    session = proj.session
    draft = [
        {"player_id": e.get("acting_player_id"), "character": e.get("character", "?")}
        for e in proj.events_by_type("final_character_choice")
    ]
    return {
        "session_id": session.session_id,
        "total_events": session.total_events,
        "total_turns": len(session.turns),
        "total_rounds": len(session.rounds),
        "winner_player_id": session.winner_player_id,
        "end_reason": session.end_reason,
        "draft": draft,
    }


# ---------------------------------------------------------------------------
# Player colours
# ---------------------------------------------------------------------------

_PLAYER_COLORS = ["#4e8ef7", "#e85d5d", "#5dbf5d", "#f0a030"]
_PLAYER_COLORS_LIGHT = ["#d0e4ff", "#ffd0d0", "#d0ffd0", "#fff0c8"]


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>게임 리플레이 — {session_id_short}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
  background: #1a1a2e;
  color: #e0e0f0;
  min-height: 100vh;
}}
header {{
  background: #16213e;
  padding: 12px 20px;
  border-bottom: 2px solid #0f3460;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}}
header h1 {{ font-size: 1.1rem; color: #8eb4ff; font-weight: 700; }}
.meta-badge {{
  background: #0f3460;
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 0.75rem;
  color: #a0b8e0;
}}
.meta-badge.winner {{ background: #1a4a1a; color: #80ff80; }}

.main-layout {{
  display: grid;
  grid-template-columns: 260px 1fr 220px;
  grid-template-rows: auto 1fr;
  gap: 0;
  height: calc(100vh - 54px);
}}

/* ── Navigation panel ────────────────────────────────────────── */
.nav-panel {{
  background: #16213e;
  border-right: 1px solid #0f3460;
  overflow-y: auto;
  padding: 12px 8px;
  grid-row: 1 / 3;
}}
.nav-panel h2 {{
  font-size: 0.8rem;
  color: #6080c0;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 0 6px 8px;
  border-bottom: 1px solid #0f3460;
  margin-bottom: 8px;
}}
.round-group {{ margin-bottom: 6px; }}
.round-label {{
  font-size: 0.72rem;
  color: #8090b0;
  padding: 2px 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
.turn-btn {{
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 0.8rem;
  color: #a0b4d0;
  cursor: pointer;
  transition: background 0.15s;
}}
.turn-btn:hover {{ background: #1f3060; }}
.turn-btn.active {{ background: #0f3460; color: #8eb4ff; font-weight: 600; }}
.turn-btn.skipped {{ opacity: 0.45; font-style: italic; }}

/* ── Center: board + events ─────────────────────────────────── */
.center-panel {{
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}

.turn-header {{
  background: #16213e;
  border-radius: 8px;
  padding: 10px 14px;
  border-left: 4px solid #4e8ef7;
}}
.turn-header h2 {{ font-size: 1rem; font-weight: 700; }}
.turn-header .sub {{ font-size: 0.78rem; color: #8090b0; margin-top: 2px; }}

.section-title {{
  font-size: 0.75rem;
  color: #6080c0;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}}

/* Event feed */
.event-feed {{
  background: #16213e;
  border-radius: 8px;
  padding: 10px 12px;
}}
.event-item {{
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 4px 0;
  border-bottom: 1px solid #1f2e50;
  font-size: 0.82rem;
}}
.event-item:last-child {{ border-bottom: none; }}
.event-icon {{ width: 18px; text-align: center; flex-shrink: 0; }}
.event-actor {{
  font-weight: 600;
  min-width: 28px;
  color: #8eb4ff;
  flex-shrink: 0;
}}
.event-type {{
  color: #6080c0;
  font-size: 0.72rem;
  min-width: 80px;
  flex-shrink: 0;
}}
.event-detail {{ color: #c0d0e8; }}
.event-feed.empty {{ color: #4060a0; font-style: italic; font-size: 0.82rem; }}

/* Board */
.board-section {{
  background: #16213e;
  border-radius: 8px;
  padding: 10px 12px;
}}
.board-grid {{
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 3px;
  margin-top: 6px;
}}
.tile {{
  aspect-ratio: 1;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 0.55rem;
  position: relative;
  border: 1px solid #2a3a5a;
  background: #1a2a40;
  cursor: default;
  transition: transform 0.1s;
}}
.tile:hover {{ transform: scale(1.08); z-index: 10; }}
.tile .tile-idx {{ color: #4060a0; font-size: 0.5rem; }}
.tile .tile-kind {{ font-size: 0.58rem; }}
.tile.owned {{ border-width: 2px; }}
.tile .pawn {{
  position: absolute;
  top: 1px;
  right: 1px;
  font-size: 0.55rem;
  line-height: 1;
}}
.tile-tooltip {{
  display: none;
  position: absolute;
  bottom: 110%;
  left: 50%;
  transform: translateX(-50%);
  background: #0a1020;
  border: 1px solid #3050a0;
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 0.72rem;
  color: #c0d0e8;
  white-space: nowrap;
  z-index: 100;
  pointer-events: none;
}}
.tile:hover .tile-tooltip {{ display: block; }}

/* F value bar */
.f-bar-wrap {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  font-size: 0.78rem;
}}
.f-bar-bg {{
  flex: 1;
  height: 8px;
  background: #1a2a40;
  border-radius: 4px;
  overflow: hidden;
}}
.f-bar-fill {{
  height: 100%;
  background: linear-gradient(90deg, #4e8ef7, #f0a030);
  border-radius: 4px;
  transition: width 0.3s;
}}

/* ── Right: player panels ───────────────────────────────────── */
.players-panel {{
  background: #13193a;
  border-left: 1px solid #0f3460;
  overflow-y: auto;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  grid-row: 1 / 3;
}}
.player-card {{
  border-radius: 8px;
  padding: 8px 10px;
  border: 1px solid #2a3a5a;
  font-size: 0.78rem;
}}
.player-card.dead {{ opacity: 0.45; }}
.player-card.active-actor {{ border-width: 2px; }}
.player-name {{
  font-weight: 700;
  font-size: 0.85rem;
  margin-bottom: 4px;
}}
.player-char {{ font-size: 0.72rem; color: #8090b0; margin-bottom: 4px; }}
.player-stat-row {{
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 2px;
}}
.stat {{
  background: #1a2a40;
  border-radius: 10px;
  padding: 1px 7px;
  font-size: 0.7rem;
}}
.stat.big {{ font-size: 0.78rem; padding: 2px 8px; }}
.mark-badge {{
  display: inline-block;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 0.67rem;
  margin-top: 2px;
}}
.mark-clear {{ background: #1a3a1a; color: #60c060; }}
.mark-marked {{ background: #3a1a1a; color: #ff6060; }}
.mark-immune {{ background: #1a1a3a; color: #6080ff; }}
.tricks-row {{ font-size: 0.68rem; color: #6080a0; margin-top: 2px; }}

/* ── Controls bar ───────────────────────────────────────────── */
.controls {{
  background: #10192e;
  border-top: 1px solid #0f3460;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  grid-column: 2 / 3;
}}
.ctrl-btn {{
  background: #1f3060;
  color: #a0b8e0;
  border: 1px solid #2a4080;
  border-radius: 6px;
  padding: 5px 14px;
  font-size: 0.82rem;
  cursor: pointer;
  transition: background 0.15s;
}}
.ctrl-btn:hover {{ background: #2a4080; }}
.ctrl-btn:disabled {{ opacity: 0.35; cursor: default; }}
.turn-counter {{ font-size: 0.8rem; color: #6080a0; }}
.progress-bar-bg {{
  flex: 1;
  height: 6px;
  background: #1a2a40;
  border-radius: 3px;
  overflow: hidden;
}}
.progress-bar-fill {{
  height: 100%;
  background: #4e8ef7;
  transition: width 0.2s;
}}
</style>
</head>
<body>

<header>
  <h1>🎮 게임 리플레이</h1>
  <span class="meta-badge">세션 {session_id_short}</span>
  <span class="meta-badge">이벤트 {total_events}개</span>
  <span class="meta-badge">턴 {total_turns}개</span>
  <span class="meta-badge">라운드 {total_rounds}개</span>
  {winner_badge}
</header>

<div class="main-layout">

  <!-- Nav panel -->
  <div class="nav-panel">
    <h2>턴 목록</h2>
    <div id="nav-list"></div>
  </div>

  <!-- Center: turn view + controls -->
  <div class="center-panel" id="center-panel">
    <div class="turn-header" id="turn-header">
      <h2 id="turn-title">—</h2>
      <div class="sub" id="turn-sub"></div>
    </div>

    <div class="event-feed" id="event-feed">
      <div class="section-title">이벤트</div>
      <div id="event-list"></div>
    </div>

    <div class="board-section">
      <div class="section-title">보드 상태</div>
      <div class="f-bar-wrap">
        <span>F값</span>
        <div class="f-bar-bg"><div class="f-bar-fill" id="f-bar" style="width:0%"></div></div>
        <span id="f-value-text">—</span>
        <span style="font-size:0.72rem;color:#8090b0">징표: <span id="marker-owner">—</span></span>
      </div>
      <div class="board-grid" id="board-grid"></div>
    </div>
  </div>

  <!-- Controls bar -->
  <div class="controls">
    <button class="ctrl-btn" id="btn-first" onclick="goToTurn(0)">⏮</button>
    <button class="ctrl-btn" id="btn-prev" onclick="prevTurn()">◀</button>
    <div class="progress-bar-bg">
      <div class="progress-bar-fill" id="progress-bar" style="width:0%"></div>
    </div>
    <span class="turn-counter" id="turn-counter">—</span>
    <button class="ctrl-btn" id="btn-next" onclick="nextTurn()">▶</button>
    <button class="ctrl-btn" id="btn-last" onclick="goToTurn(TURNS.length-1)">⏭</button>
  </div>

  <!-- Players panel -->
  <div class="players-panel" id="players-panel"></div>

</div>

<script>
const META = {meta_json};
const TURNS = {turns_json};
const PLAYER_COLORS = {player_colors_json};
const PLAYER_COLORS_LIGHT = {player_colors_light_json};

let currentTurnIdx = 0;

// ── Build nav list ─────────────────────────────────────────────────────────
function buildNav() {{
  const container = document.getElementById('nav-list');
  let currentRound = -1;
  let roundDiv = null;

  TURNS.forEach((turn, i) => {{
    if (turn.round_index !== currentRound) {{
      currentRound = turn.round_index;
      const label = document.createElement('div');
      label.className = 'round-label';
      label.textContent = `Round ${{currentRound}}`;
      roundDiv = document.createElement('div');
      roundDiv.className = 'round-group';
      roundDiv.appendChild(label);
      container.appendChild(roundDiv);
    }}
    const btn = document.createElement('button');
    btn.className = 'turn-btn' + (turn.skipped ? ' skipped' : '');
    btn.id = `nav-turn-${{i}}`;
    const pid = turn.acting_player_id;
    btn.textContent = `T${{turn.turn_index}} P${{pid ?? '?'}}` + (turn.skipped ? ' (skip)' : '');
    btn.onclick = () => goToTurn(i);
    if (roundDiv) roundDiv.appendChild(btn);
  }});
}}

// ── Render a turn ──────────────────────────────────────────────────────────
function renderTurn(idx) {{
  currentTurnIdx = idx;
  const turn = TURNS[idx];
  const pid = turn.acting_player_id;
  const color = pid !== null ? PLAYER_COLORS[((pid - 1) % PLAYER_COLORS.length)] : '#8090b0';

  // Header
  document.getElementById('turn-title').textContent =
    `Turn ${{turn.turn_index}} — P${{pid ?? '?'}}` + (turn.skipped ? ' (건너뜀)' : '');
  document.getElementById('turn-header').style.borderLeftColor = color;
  document.getElementById('turn-sub').textContent = `Round ${{turn.round_index}}`;

  // Event feed
  const listEl = document.getElementById('event-list');
  listEl.innerHTML = '';
  if (turn.events.length === 0) {{
    listEl.innerHTML = '<div style="color:#4060a0;font-style:italic;font-size:0.82rem">이벤트 없음</div>';
  }} else {{
    turn.events.forEach(e => {{
      const row = document.createElement('div');
      row.className = 'event-item';
      const actorColor = e.actor.startsWith('P') ?
        PLAYER_COLORS[((parseInt(e.actor.slice(1)) - 1) % PLAYER_COLORS.length)] : '#8090b0';
      row.innerHTML = `
        <span class="event-icon">${{e.icon}}</span>
        <span class="event-actor" style="color:${{actorColor}}">${{e.actor}}</span>
        <span class="event-type">${{e.type}}</span>
        <span class="event-detail">${{e.detail}}</span>
      `;
      listEl.appendChild(row);
    }});
  }}

  // Board
  renderBoard(turn);

  // Players
  renderPlayers(turn);

  // Controls
  document.getElementById('btn-prev').disabled = idx === 0;
  document.getElementById('btn-first').disabled = idx === 0;
  document.getElementById('btn-next').disabled = idx === TURNS.length - 1;
  document.getElementById('btn-last').disabled = idx === TURNS.length - 1;
  const pct = TURNS.length > 1 ? (idx / (TURNS.length - 1) * 100) : 0;
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('turn-counter').textContent = `${{idx + 1}} / ${{TURNS.length}}`;

  // Nav highlight
  document.querySelectorAll('.turn-btn').forEach(b => b.classList.remove('active'));
  const navBtn = document.getElementById(`nav-turn-${{idx}}`);
  if (navBtn) {{
    navBtn.classList.add('active');
    navBtn.scrollIntoView({{ block: 'nearest' }});
  }}
}}

// ── Board rendering ────────────────────────────────────────────────────────
const TILE_KIND_ICONS = {{
  F1: '🏁', F2: '🏁', S: '⭐', T2: '🏘', T3: '🏛', MALICIOUS: '☠️',
}};

function renderBoard(turn) {{
  const grid = document.getElementById('board-grid');
  grid.innerHTML = '';
  const board = turn.board || {{}};
  const tiles = board.tiles || [];
  const ownedMap = turn.owned_tiles || {{}};
  const pawnMap = turn.pawn_positions || {{}};

  for (let i = 0; i < 40; i++) {{
    const tile = tiles[i] || {{}};
    const tileDiv = document.createElement('div');
    tileDiv.className = 'tile';

    const ownerId = ownedMap[String(i)];
    if (ownerId != null) {{
      const ci = (ownerId - 1) % PLAYER_COLORS.length;
      tileDiv.style.borderColor = PLAYER_COLORS[ci];
      tileDiv.style.background = PLAYER_COLORS_LIGHT[ci];
      tileDiv.classList.add('owned');
    }}

    const kind = tile.tile_kind || '?';
    const icon = TILE_KIND_ICONS[kind] || '▪';
    tileDiv.innerHTML = `<span class="tile-idx">${{i}}</span><span class="tile-kind">${{icon}}</span>`;

    const pawns = pawnMap[String(i)];
    if (pawns && pawns.length > 0) {{
      const pawnSpan = document.createElement('span');
      pawnSpan.className = 'pawn';
      pawnSpan.textContent = pawns.map(p => `👤`).join('');
      tileDiv.appendChild(pawnSpan);
    }}

    // Tooltip
    const tt = document.createElement('div');
    tt.className = 'tile-tooltip';
    const ownerNote = ownerId ? ` | P${{ownerId}}소유` : '';
    const rentNote = tile.rent_cost ? ` | 렌트${{tile.rent_cost}}` : '';
    const coinNote = tile.score_coin_count ? ` | 🪙${{tile.score_coin_count}}` : '';
    const pawnNote = pawns && pawns.length ? ` | P${{pawns.join(',')}}` : '';
    tt.textContent = `[${{i}}] ${{kind}}${{ownerNote}}${{rentNote}}${{coinNote}}${{pawnNote}}`;
    tileDiv.appendChild(tt);

    grid.appendChild(tileDiv);
  }}

  // F bar
  const fVal = board.f_value ?? 0;
  const fPct = Math.min(100, Math.max(0, (fVal / 10) * 100));
  document.getElementById('f-bar').style.width = fPct + '%';
  document.getElementById('f-value-text').textContent = typeof fVal === 'number' ? fVal.toFixed(2) : fVal;
  const marker = board.marker_owner_player_id;
  document.getElementById('marker-owner').textContent = marker != null ? `P${{marker}}` : '—';
}}

// ── Player panels ──────────────────────────────────────────────────────────
function renderPlayers(turn) {{
  const panel = document.getElementById('players-panel');
  panel.innerHTML = '<div style="font-size:0.75rem;color:#6080c0;text-transform:uppercase;letter-spacing:1px;padding:0 4px 8px;border-bottom:1px solid #1a2a40;margin-bottom:8px">플레이어</div>';

  const players = turn.players || [];
  const actorId = turn.acting_player_id;

  players.forEach((p, i) => {{
    const ci = ((p.player_id - 1) % PLAYER_COLORS.length);
    const color = PLAYER_COLORS[ci];
    const colorLight = PLAYER_COLORS_LIGHT[ci];
    const isActor = p.player_id === actorId;

    const card = document.createElement('div');
    card.className = 'player-card' + (p.alive ? '' : ' dead') + (isActor ? ' active-actor' : '');
    card.style.borderColor = color;
    if (isActor) card.style.background = colorLight.replace(')', ', 0.08)').replace('rgb', 'rgba');

    const markClass = p.mark_status === 'marked' ? 'mark-marked' :
                      p.mark_status === 'immune' ? 'mark-immune' : 'mark-clear';

    const effects = (p.public_effects || []).join(', ');
    const pubTricks = (p.public_tricks || []).join(', ') || '—';
    const hidden = p.hidden_trick_count || 0;

    card.innerHTML = `
      <div class="player-name" style="color:${{color}}">
        ${{isActor ? '▶ ' : ''}}P${{p.player_id}} ${{p.alive ? '' : '💀'}}
      </div>
      <div class="player-char">${{p.character || '?'}} · tile ${{p.position}}</div>
      <div class="player-stat-row">
        <span class="stat big">💰${{p.cash}}</span>
        <span class="stat big">🔮${{p.shards}}</span>
        <span class="stat">🪙${{p.hand_score_coins}}+${{p.placed_score_coins}}</span>
        <span class="stat">🏠${{p.owned_tile_count}}</span>
      </div>
      <span class="mark-badge ${{markClass}}">${{p.mark_status}}</span>
      ${{effects ? `<div style="font-size:0.65rem;color:#8090b0;margin-top:3px">⚡ ${{effects}}</div>` : ''}}
      <div class="tricks-row">잔꾀: ${{pubTricks}} [${{hidden}}H]</div>
    `;
    panel.appendChild(card);
  }});
}}

// ── Navigation helpers ─────────────────────────────────────────────────────
function goToTurn(idx) {{
  if (idx >= 0 && idx < TURNS.length) renderTurn(idx);
}}
function prevTurn() {{ goToTurn(currentTurnIdx - 1); }}
function nextTurn() {{ goToTurn(currentTurnIdx + 1); }}

// Keyboard navigation
document.addEventListener('keydown', e => {{
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') nextTurn();
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') prevTurn();
  if (e.key === 'Home') goToTurn(0);
  if (e.key === 'End') goToTurn(TURNS.length - 1);
}});

// ── Init ───────────────────────────────────────────────────────────────────
buildNav();
if (TURNS.length > 0) renderTurn(0);
</script>
</body>
</html>
"""


def render_html(proj: ReplayProjection) -> str:
    """Render the full game replay as a self-contained HTML page."""
    session = proj.session
    session_id_short = session.session_id[:8] if session.session_id else "unknown"

    meta = _build_meta(proj)
    turns_data = _build_turn_data(proj)

    winner = session.winner_player_id
    if winner is not None:
        ci = (winner - 1) % len(_PLAYER_COLORS)
        bg = _PLAYER_COLORS[ci]
        winner_badge = f'<span class="meta-badge winner">P{winner} 승리</span>'
    else:
        winner_badge = ""

    html = _HTML_TEMPLATE.format(
        session_id_short=session_id_short,
        total_events=session.total_events,
        total_turns=len(session.turns),
        total_rounds=len(session.rounds),
        winner_badge=winner_badge,
        meta_json=json.dumps(meta, ensure_ascii=False),
        turns_json=json.dumps(turns_data, ensure_ascii=False),
        player_colors_json=json.dumps(_PLAYER_COLORS),
        player_colors_light_json=json.dumps(_PLAYER_COLORS_LIGHT),
    )
    return html
