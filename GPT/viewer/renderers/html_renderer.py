from __future__ import annotations

import json

from ..replay import ReplayProjection


PLAYER_COLORS = ["#4e8ef7", "#e85d5d", "#5dbf5d", "#f0a030"]


def _event_display(event: dict) -> dict:
    event_type = event.get("event_type", "?")
    actor = event.get("acting_player_id")
    actor_label = f"P{actor}" if actor is not None else "-"

    if event_type == "dice_roll":
        detail = f"{event.get('dice_values', [])} -> {event.get('total', '?')}"
    elif event_type == "player_move":
        detail = f"{event.get('from_pos', '?')} -> {event.get('to_pos', '?')}"
    elif event_type == "rent_paid":
        detail = (
            f"P{event.get('payer_player_id', '?')} -> "
            f"P{event.get('owner_player_id', '?')} "
            f"{event.get('final_amount', event.get('amount', '?'))}"
        )
    elif event_type == "tile_purchased":
        detail = f"tile {event.get('tile_index', '?')} for {event.get('cost', '?')}"
    elif event_type == "lap_reward_chosen":
        detail = f"{event.get('choice', '?')} x {event.get('amount', '?')}"
    elif event_type == "weather_reveal":
        detail = event.get("weather_name", event.get("card", "?"))
    elif event_type == "final_character_choice":
        detail = event.get("character", "?")
    else:
        detail = event.get("public_summary", "") or event.get("summary", "") or event_type

    return {
        "type": event_type,
        "actor": actor_label,
        "detail": detail,
    }


def _turn_payload(projection: ReplayProjection) -> list[dict]:
    turns: list[dict] = []
    for turn in projection.turns:
        round_replay = projection.get_round(turn.round_index)
        turns.append(
            {
                "turn_index": turn.turn_index,
                "round_index": turn.round_index,
                "acting_player_id": turn.acting_player_id,
                "skipped": turn.skipped,
                "players": turn.player_states,
                "board": turn.board_state or {},
                "events": [_event_display(event) for event in turn.key_events],
                "round_weather_name": round_replay.weather_name if round_replay else "",
                "round_prelude_events": [
                    _event_display(event)
                    for event in (round_replay.prelude_events if round_replay else [])
                    if event.get("event_type") != "round_start"
                ],
            }
        )
    return turns


def _meta_payload(projection: ReplayProjection) -> dict:
    session = projection.session
    return {
        "session_id": session.session_id,
        "total_events": session.total_events,
        "total_turns": projection.turn_count,
        "total_rounds": projection.round_count,
        "winner_player_id": session.winner_player_id,
        "end_reason": session.end_reason,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GPT Replay Viewer</title>
<style>
body {{
  margin: 0;
  font-family: "Segoe UI", sans-serif;
  background: #101726;
  color: #e8eefc;
}}
.layout {{
  display: grid;
  grid-template-columns: 280px 1fr 280px;
  min-height: 100vh;
}}
.nav, .players {{
  background: #16213a;
  padding: 16px;
  overflow-y: auto;
}}
.center {{
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}}
.turn-button {{
  display: block;
  width: 100%;
  text-align: left;
  margin: 4px 0;
  padding: 8px 10px;
  border: 1px solid #2f4168;
  border-radius: 8px;
  background: #1a2744;
  color: #d8e6ff;
  cursor: pointer;
}}
.turn-button.active {{
  background: #2b4f9d;
}}
.panel {{
  background: #16213a;
  border-radius: 10px;
  padding: 14px;
}}
.board-grid {{
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 4px;
  margin-top: 10px;
}}
.tile {{
  aspect-ratio: 1;
  border: 1px solid #31466f;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #c2d2ee;
  position: relative;
}}
.pawn {{
  position: absolute;
  bottom: 3px;
  right: 4px;
  font-size: 10px;
}}
.event {{
  padding: 6px 0;
  border-bottom: 1px solid #22304f;
  font-size: 14px;
}}
.event:last-child {{
  border-bottom: none;
}}
.player-card {{
  border: 1px solid #31466f;
  border-left-width: 4px;
  border-radius: 10px;
  padding: 10px;
  margin-bottom: 10px;
  background: #1a2744;
}}
.meta {{
  color: #8ea6d8;
  font-size: 12px;
}}
.controls {{
  display: flex;
  gap: 8px;
}}
button.ctrl {{
  border: 1px solid #39538a;
  background: #22365e;
  color: #e8eefc;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
}}
</style>
</head>
<body>
<div class="layout">
  <div class="nav">
    <h2>Turns</h2>
    <div id="turn-list"></div>
  </div>
  <div class="center">
    <div class="panel">
      <h1 id="title">Replay</h1>
      <div class="meta" id="subtitle"></div>
      <div class="controls">
        <button class="ctrl" onclick="goFirst()">First</button>
        <button class="ctrl" onclick="goPrev()">Prev</button>
        <button class="ctrl" onclick="goNext()">Next</button>
        <button class="ctrl" onclick="goLast()">Last</button>
      </div>
    </div>
    <div class="panel">
      <h2>Event Feed</h2>
      <div id="events"></div>
    </div>
    <div class="panel">
      <h2>Board</h2>
      <div class="meta" id="board-meta"></div>
      <div class="board-grid" id="board"></div>
    </div>
  </div>
  <div class="players">
    <h2>Players</h2>
    <div id="players"></div>
  </div>
</div>
<script>
const META = {meta_json};
const TURNS = {turns_json};
const PLAYER_COLORS = {colors_json};
let currentIndex = 0;

function turnLabel(turn) {{
  return `Turn ${{turn.turn_index}} / Round ${{turn.round_index}} / P${{turn.acting_player_id ?? '-'}}`;
}}

function renderTurnList() {{
  const root = document.getElementById('turn-list');
  root.innerHTML = '';
  TURNS.forEach((turn, index) => {{
    const btn = document.createElement('button');
    btn.className = 'turn-button' + (index === currentIndex ? ' active' : '');
    btn.textContent = turnLabel(turn);
    btn.onclick = () => goTo(index);
    root.appendChild(btn);
  }});
}}

function renderCurrent() {{
  if (!TURNS.length) return;
  const turn = TURNS[currentIndex];
  document.getElementById('title').textContent = turnLabel(turn);
  document.getElementById('subtitle').textContent =
    `Session ${{META.session_id}} | events=${{META.total_events}} | winner=${{META.winner_player_id ?? '-'}}`;

  const eventsRoot = document.getElementById('events');
  eventsRoot.innerHTML = '';
  if (turn.round_prelude_events && turn.round_prelude_events.length) {{
    const preludeTitle = document.createElement('div');
    preludeTitle.className = 'meta';
    preludeTitle.style.marginBottom = '8px';
    preludeTitle.textContent = `Round Prelude | weather=${{turn.round_weather_name || '-'}}`;
    eventsRoot.appendChild(preludeTitle);
    turn.round_prelude_events.forEach((event) => {{
      const row = document.createElement('div');
      row.className = 'event';
      row.textContent = `[${event.actor}] ${event.type}: ${event.detail}`;
      eventsRoot.appendChild(row);
    }});
  }
  if (!turn.events.length) {{
    const empty = document.createElement('div');
    empty.className = 'meta';
    empty.textContent = 'No public key events.';
    eventsRoot.appendChild(empty);
  }} else {{
    turn.events.forEach((event) => {{
      const row = document.createElement('div');
      row.className = 'event';
      row.textContent = `[${event.actor}] ${event.type}: ${event.detail}`;
      eventsRoot.appendChild(row);
    }});
  }}

  const boardMeta = document.getElementById('board-meta');
  const board = turn.board || {{}};
  boardMeta.textContent = `F=${{board.f_value ?? '?'}} | marker=P${{board.marker_owner_player_id ?? '-'}}`;

  const boardRoot = document.getElementById('board');
  boardRoot.innerHTML = '';
  const tiles = board.tiles || [];
  for (let i = 0; i < 40; i++) {{
    const tile = tiles[i] || {{}};
    const owner = tile.owner_player_id;
    const el = document.createElement('div');
    el.className = 'tile';
    el.textContent = `${{i}}:${{tile.tile_kind ?? '?'}}`;
    if (owner != null) {{
      el.style.borderColor = PLAYER_COLORS[(owner - 1) % PLAYER_COLORS.length];
    }}
    const pawns = tile.pawn_player_ids || [];
    if (pawns.length) {{
      const pawn = document.createElement('div');
      pawn.className = 'pawn';
      pawn.textContent = pawns.map((id) => `P${id}`).join(',');
      el.appendChild(pawn);
    }}
    boardRoot.appendChild(el);
  }}

  const playersRoot = document.getElementById('players');
  playersRoot.innerHTML = '';
  (turn.players || []).forEach((player) => {{
    const card = document.createElement('div');
    card.className = 'player-card';
    card.style.borderLeftColor = PLAYER_COLORS[(player.player_id - 1) % PLAYER_COLORS.length];
    const tricks = (player.public_tricks || []).join(', ') || '-';
    const effects = (player.public_effects || []).join(', ') || '-';
    card.innerHTML = `
      <div><strong>P${player.player_id}</strong> ${player.character || '?'}</div>
      <div class="meta">cash=${player.cash} | shards=${player.shards} | pos=${player.position} | tiles=${player.owned_tile_count}</div>
      <div class="meta">mark=${player.mark_status} | tricks=${tricks} [${player.hidden_trick_count}H]</div>
      <div class="meta">effects=${effects}</div>
    `;
    playersRoot.appendChild(card);
  }});

  renderTurnList();
}}

function goTo(index) {{
  if (index < 0 || index >= TURNS.length) return;
  currentIndex = index;
  renderCurrent();
}}
function goFirst() {{ goTo(0); }}
function goPrev() {{ goTo(currentIndex - 1); }}
function goNext() {{ goTo(currentIndex + 1); }}
function goLast() {{ goTo(TURNS.length - 1); }}
renderCurrent();
</script>
</body>
</html>
"""


def render_html(projection: ReplayProjection) -> str:
    html = HTML_TEMPLATE
    html = html.replace("{meta_json}", json.dumps(_meta_payload(projection), ensure_ascii=False))
    html = html.replace("{turns_json}", json.dumps(_turn_payload(projection), ensure_ascii=False))
    html = html.replace("{colors_json}", json.dumps(PLAYER_COLORS))
    html = html.replace("{{", "{").replace("}}", "}")
    return html
