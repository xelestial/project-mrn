"""Phase 4 human-play HTML renderer."""
from __future__ import annotations


def render_play_html(
    session_id: str = "",
    seed: int = 0,
    human_seat: int = 0,
    poll_interval_ms: int = 200,
) -> str:
    return _TEMPLATE.format(
        session_id=session_id or "...",
        seed=seed,
        human_seat=human_seat,
        human_seat_js=human_seat + 1,
        poll_interval_ms=poll_interval_ms,
    )


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Human Play - seed {seed} - P{human_seat}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: "Segoe UI", "Apple SD Gothic Neo", sans-serif;
  background: #141b2d;
  color: #e7eefc;
  min-height: 100vh;
}}
header {{
  background: #0d1324;
  border-bottom: 1px solid #22314f;
  padding: 10px 16px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}}
h1 {{ font-size: 1rem; color: #ffd060; }}
.badge {{
  background: #1c2943;
  border: 1px solid #2e426c;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.75rem;
}}
.badge.human {{ color: #ffd060; border-color: #ffd060; }}
.badge.live {{ color: #ff7a7a; }}
.badge.done {{ color: #72e289; }}
.badge.waiting {{ color: #d8a6ff; border-color: #d8a6ff; }}
.layout {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  min-height: calc(100vh - 53px);
}}
.center {{
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}}
.section {{
  background: #18233a;
  border: 1px solid #263654;
  border-radius: 12px;
  padding: 12px;
}}
.sec-title {{
  font-size: 0.72rem;
  color: #8aa5d8;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 8px;
}}
.turn-header {{
  border-left: 4px solid #4e8ef7;
}}
.turn-title {{ font-size: 1rem; font-weight: 700; }}
.turn-sub {{ font-size: 0.78rem; color: #98aacd; margin-top: 4px; }}
.progress-row {{
  display: flex;
  gap: 10px;
  align-items: center;
}}
.progress-bar {{
  flex: 1;
  height: 6px;
  background: #0f1727;
  border-radius: 999px;
  overflow: hidden;
}}
.progress-fill {{
  height: 100%;
  width: 0%;
  background: #4e8ef7;
}}
.event-feed {{
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 80px;
}}
.event-item {{
  display: grid;
  grid-template-columns: 28px 44px 140px minmax(0, 1fr);
  gap: 8px;
  font-size: 0.8rem;
  align-items: center;
}}
.event-type {{ color: #8aa5d8; }}
.board-grid {{
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 4px;
}}
.tile {{
  aspect-ratio: 1;
  border: 1px solid #31486e;
  border-radius: 8px;
  background: #132035;
  position: relative;
  padding: 4px;
  font-size: 0.65rem;
  overflow: hidden;
}}
.tile.owned {{ border-width: 2px; }}
.tile-index {{ color: #7e95bf; font-size: 0.58rem; }}
.tile-kind {{ display: block; margin-top: 3px; font-weight: 700; }}
.tile-meta {{
  position: absolute;
  left: 4px;
  right: 4px;
  bottom: 3px;
  font-size: 0.55rem;
  color: #c2d2ef;
}}
.tile-pawns {{
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 0.6rem;
}}
.f-row {{
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  font-size: 0.8rem;
}}
.f-bar {{
  flex: 1;
  height: 8px;
  background: #0f1727;
  border-radius: 999px;
  overflow: hidden;
}}
.f-fill {{
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, #4e8ef7, #f0a030);
}}
.players-panel {{
  padding: 12px 10px;
  background: #10192b;
  border-left: 1px solid #22314f;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.player-card {{
  background: #18233a;
  border: 1px solid #304464;
  border-radius: 10px;
  padding: 10px;
  font-size: 0.76rem;
}}
.player-card.active {{ border-width: 2px; }}
.player-card.dead {{ opacity: 0.5; }}
.player-card.human-seat {{
  border-color: #ffd060 !important;
  box-shadow: 0 0 0 1px rgba(255, 208, 96, 0.25);
}}
.player-name {{ font-weight: 700; }}
.player-character {{ color: #9bb0d8; margin-top: 2px; }}
.stat-row {{
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 7px;
}}
.stat {{
  background: #0f1727;
  border-radius: 999px;
  padding: 2px 7px;
  font-size: 0.68rem;
}}
.mark {{
  display: inline-block;
  margin-top: 7px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.68rem;
}}
.mark-clear {{ background: #163321; color: #72e289; }}
.mark-marked {{ background: #3d1920; color: #ff8f8f; }}
.mark-immune {{ background: #1a2340; color: #87a8ff; }}
.tricks-row {{
  margin-top: 6px;
  color: #9bb0d8;
  font-size: 0.68rem;
}}
.empty-msg {{
  font-size: 0.8rem;
  color: #7e95bf;
  font-style: italic;
}}
#decision-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.58);
  z-index: 999;
  align-items: center;
  justify-content: center;
}}
#decision-overlay.visible {{ display: flex; }}
#decision-panel {{
  width: min(92vw, 520px);
  background: #121b2e;
  border: 2px solid #ffd060;
  border-radius: 14px;
  padding: 20px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}}
.dp-title {{ font-size: 1.05rem; font-weight: 700; color: #ffd060; }}
.dp-sub {{ font-size: 0.8rem; color: #a8b9d8; margin-top: 5px; margin-bottom: 14px; }}
.dp-options {{
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.dp-btn {{
  text-align: left;
  border: 1px solid #355188;
  background: #182846;
  color: #e7eefc;
  border-radius: 10px;
  padding: 11px 13px;
  cursor: pointer;
}}
.dp-btn:hover {{ border-color: #ffd060; }}
.dp-btn.selected {{
  border-color: #ffd060;
  color: #ffd060;
  background: #2a280d;
}}
.dp-btn:disabled {{ opacity: 0.55; cursor: not-allowed; }}
.dp-timeout {{
  margin-top: 12px;
  text-align: right;
  font-size: 0.74rem;
  color: #9bb0d8;
}}
@media (max-width: 980px) {{
  .layout {{ grid-template-columns: 1fr; }}
  .players-panel {{ border-left: 0; border-top: 1px solid #22314f; }}
}}
</style>
</head>
<body>
<div id="decision-overlay">
  <div id="decision-panel">
    <div class="dp-title" id="dp-title">Decision</div>
    <div class="dp-sub" id="dp-sub"></div>
    <div class="dp-options" id="dp-options"></div>
    <div class="dp-timeout" id="dp-timeout">Time limit: 300s</div>
  </div>
</div>

<header>
  <h1>Human Play</h1>
  <span class="badge human">P{human_seat}</span>
  <span class="badge" id="status-badge">Waiting</span>
  <span class="badge">seed {seed}</span>
  <span class="badge" id="event-count">0 events</span>
  <span class="badge" id="turn-badge">Turn 0</span>
  <span class="badge waiting" id="decision-badge" style="display:none">Decision pending</span>
</header>

<div class="layout">
  <div class="center">
    <div class="section turn-header" id="turn-header" style="display:none">
      <div class="turn-title" id="turn-title"></div>
      <div class="turn-sub" id="turn-sub"></div>
    </div>

    <div class="section">
      <div class="sec-title">Progress</div>
      <div class="progress-row">
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
        <span id="progress-text">Turn 0</span>
      </div>
    </div>

    <div class="section">
      <div class="sec-title">Recent Events</div>
      <div class="event-feed" id="event-feed">
        <div class="empty-msg">Waiting for events...</div>
      </div>
    </div>

    <div class="section">
      <div class="sec-title">Board</div>
      <div class="f-row">
        <span>F</span>
        <div class="f-bar"><div class="f-fill" id="f-fill"></div></div>
        <span id="f-text">0.00</span>
        <span id="marker-owner">marker -</span>
      </div>
      <div class="board-grid" id="board-grid"></div>
    </div>
  </div>

  <div class="players-panel" id="players-panel">
    <div class="sec-title">Players</div>
    <div class="empty-msg">Waiting for snapshot...</div>
  </div>
</div>

<script>
const HUMAN_SEAT = {human_seat_js};
const POLL_MS = {poll_interval_ms};
const PLAYER_COLORS = ["#4e8ef7", "#e85d5d", "#5dbf5d", "#f0a030"];
const PLAYER_LIGHTS = ["#1d355d", "#56252a", "#214827", "#5a4418"];
const TILE_LABELS = {{ F1: "F1", F2: "F2", S: "S", T2: "T2", T3: "T3", MALICIOUS: "M" }};
const EVENT_ICONS = {{
  session_start: "S",
  round_start: "R",
  turn_start: "T",
  dice_roll: "D",
  player_move: "M",
  landing_resolved: "L",
  rent_paid: "$",
  tile_purchased: "+",
  fortune_drawn: "F",
  weather_reveal: "W",
  lap_reward_chosen: "L",
  final_character_choice: "C",
  draft_pick: "P",
  mark_resolved: "!",
  bankruptcy: "X",
  game_end: "END",
}};

let lastStep = 0;
let isDone = false;
let currentTurn = 0;
let currentActorId = null;
let currentSnapshot = null;
let queue = [];
let draining = false;
let timeoutInterval = null;
let decisionStartedAt = null;

const isDecisionVisible = () =>
  document.getElementById("decision-overlay").classList.contains("visible");

async function pollEvents() {{
  if (isDone) return;
  try {{
    const resp = await fetch(`/events?since=${{lastStep}}`);
    const data = await resp.json();
    if (data.events && data.events.length) {{
      queue.push(...data.events);
      lastStep = data.events[data.events.length - 1].step_index + 1;
      document.getElementById("event-count").textContent = `${{data.total}} events`;
      if (!draining) drainEvents();
    }}
    if (data.done) {{
      isDone = true;
      document.getElementById("status-badge").textContent = "Done";
      document.getElementById("status-badge").className = "badge done";
    }}
  }} catch (e) {{
    console.warn("poll failed:", e);
  }}
}}

function drainEvents() {{
  if (!queue.length) {{
    draining = false;
    return;
  }}
  draining = true;
  const ev = queue.shift();
  processEvent(ev);
  const delay = ev.event_type === "turn_end_snapshot" ? 250 : 30;
  setTimeout(drainEvents, delay);
}}

async function pollPrompt() {{
  if (isDone) return;
  try {{
    const resp = await fetch("/prompt");
    const data = await resp.json();
    const requestType = data.request_type || data.type;
    if (requestType && !isDecisionVisible()) {{
      showDecision(data);
    }} else if (!requestType && isDecisionVisible()) {{
      hideDecision();
    }}
  }} catch (e) {{
    console.warn("prompt poll failed:", e);
  }}
}}

function showDecision(prompt) {{
  const overlay = document.getElementById("decision-overlay");
  const title = document.getElementById("dp-title");
  const sub = document.getElementById("dp-sub");
  const options = document.getElementById("dp-options");
  const badge = document.getElementById("decision-badge");

  const requestType = prompt.request_type || prompt.type;
  title.textContent = decisionTitle(requestType);
  sub.textContent = decisionSubtitle(prompt);
  options.innerHTML = "";
  const legalChoices = prompt.legal_choices || prompt.options || [];
  for (const opt of legalChoices) {{
    const button = document.createElement("button");
    button.className = "dp-btn";
    const choiceId = opt.choice_id || opt.id;
    button.textContent = opt.label || String(choiceId);
    button.onclick = () => submitDecision(choiceId, button, options);
    options.appendChild(button);
  }}

  decisionStartedAt = Date.now();
  clearInterval(timeoutInterval);
  timeoutInterval = setInterval(() => {{
    const remain = Math.max(0, 300 - Math.floor((Date.now() - decisionStartedAt) / 1000));
    document.getElementById("dp-timeout").textContent =
      remain > 0 ? `Time limit: ${{remain}}s` : "Timed out - AI fallback";
    if (remain <= 0) clearInterval(timeoutInterval);
  }}, 500);

  badge.style.display = "";
  overlay.classList.add("visible");
}}

function hideDecision() {{
  document.getElementById("decision-overlay").classList.remove("visible");
  document.getElementById("decision-badge").style.display = "none";
  document.getElementById("dp-timeout").textContent = "Time limit: 300s";
  clearInterval(timeoutInterval);
}}

async function submitDecision(optionId, clicked, container) {{
  for (const btn of container.querySelectorAll(".dp-btn")) btn.disabled = true;
  clicked.classList.add("selected");
  try {{
    const resp = await fetch("/decision", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ choice_id: optionId }}),
    }});
    if (resp.ok) {{
      setTimeout(hideDecision, 180);
    }} else {{
      for (const btn of container.querySelectorAll(".dp-btn")) btn.disabled = false;
      clicked.classList.remove("selected");
    }}
  }} catch (e) {{
    console.warn("decision submit failed:", e);
    for (const btn of container.querySelectorAll(".dp-btn")) btn.disabled = false;
    clicked.classList.remove("selected");
  }}
}}

function decisionTitle(type) {{
  return {{
    movement: "Movement",
    lap_reward: "Lap Reward",
    draft_card: "Draft Card",
    final_character: "Final Character",
    trick_to_use: "Use Trick",
    purchase_tile: "Buy Tile",
    hidden_trick_card: "Hide Trick",
    mark_target: "Mark Target",
    coin_placement: "Place Score Coin",
  }}[type] || type;
}}

function decisionSubtitle(prompt) {{
  const requestType = prompt.request_type || prompt.type;
  const ctx = prompt.public_context || prompt;
  if (requestType === "movement") {{
    return `pos ${{ctx.player_position ?? "?"}} / cash ${{ctx.player_cash ?? "?"}}`;
  }}
  if (requestType === "purchase_tile") {{
    return `tile ${{ctx.tile_index ?? "?"}} / cost ${{ctx.cost ?? "?"}} / cash ${{ctx.player_cash ?? "?"}}`;
  }}
  if (requestType === "lap_reward") {{
    const pools = ctx.pools || {{}};
    return `budget ${{ctx.budget ?? "?"}} / cash ${{pools.cash ?? "?"}} / shards ${{pools.shards ?? "?"}} / coins ${{pools.coins ?? "?"}}`;
  }}
  if (requestType === "mark_target") {{
    return ctx.actor_name || "";
  }}
  return "";
}}

function processEvent(ev) {{
  if (ev.event_type === "session_start") {{
    document.getElementById("status-badge").textContent = "Live";
    document.getElementById("status-badge").className = "badge live";
  }}
  if (ev.event_type === "turn_start") {{
    currentTurn = ev.turn_index;
    currentActorId = ev.acting_player_id;
    document.getElementById("turn-header").style.display = "";
    document.getElementById("turn-title").textContent =
      `Turn ${{ev.turn_index}} - P${{ev.acting_player_id ?? "?"}}`;
    document.getElementById("turn-sub").textContent = `Round ${{ev.round_index}}`;
    document.getElementById("turn-badge").textContent = `Turn ${{ev.turn_index}}`;
    document.getElementById("progress-fill").style.width = `${{Math.min(95, ev.turn_index * 1.5)}}%`;
    document.getElementById("progress-text").textContent = `Turn ${{ev.turn_index}}`;
  }}
  if (ev.event_type === "turn_end_snapshot") {{
    currentSnapshot = {{
      players: ev.players || (ev.snapshot || {{}}).players || [],
      board: ev.board || (ev.snapshot || {{}}).board || {{}},
    }};
    renderBoard(currentSnapshot.board);
    renderPlayers(currentSnapshot.players, currentActorId);
  }}
  if (ev.event_type === "game_end") {{
    document.getElementById("progress-fill").style.width = "100%";
  }}
  if (!new Set(["turn_end_snapshot", "trick_window_open", "trick_window_closed"]).has(ev.event_type)) {{
    appendEvent(ev);
  }}
}}

function appendEvent(ev) {{
  const feed = document.getElementById("event-feed");
  const empty = feed.querySelector(".empty-msg");
  if (empty) empty.remove();

  const actorId = ev.acting_player_id;
  const isHuman = actorId === HUMAN_SEAT;
  const actorColor = actorId != null
    ? (isHuman ? "#ffd060" : PLAYER_COLORS[(actorId - 1) % PLAYER_COLORS.length])
    : "#9bb0d8";
  const row = document.createElement("div");
  row.className = "event-item";
  row.innerHTML = `
    <div>${{EVENT_ICONS[ev.event_type] || ">"}}</div>
    <div style="color:${{actorColor}}">${{actorId != null ? `P${{actorId}}` : "-"}}</div>
    <div class="event-type">${{ev.event_type}}</div>
    <div>${{eventDetail(ev)}}</div>
  `;
  feed.appendChild(row);
  while (feed.children.length > 20) feed.removeChild(feed.firstChild);
}}

function eventDetail(ev) {{
  if (ev.event_type === "player_move") {{
    return `${{ev.from_pos ?? "?"}} -> ${{ev.to_pos ?? "?"}}`;
  }}
  if (ev.event_type === "dice_roll") {{
    const dice = ev.dice || ev.dice_values || [];
    return `${{JSON.stringify(dice)}} => ${{ev.total ?? ev.move ?? ""}}`;
  }}
  if (ev.event_type === "rent_paid") {{
    return `P${{ev.payer_player_id ?? ev.payer ?? "?"}} -> P${{ev.owner_player_id ?? ev.owner ?? "?"}} ${{ev.final_amount ?? ev.amount ?? "?"}}`;
  }}
  if (ev.event_type === "tile_purchased") {{
    return `tile ${{ev.tile_index ?? "?"}} / ${{ev.cost ?? "?"}}`;
  }}
  if (ev.event_type === "final_character_choice") {{
    return ev.character || "";
  }}
  if (ev.event_type === "game_end") {{
    return ev.reason || "";
  }}
  return ev.card_name || ev.weather_name || "";
}}

function renderBoard(board) {{
  const grid = document.getElementById("board-grid");
  grid.innerHTML = "";
  const tiles = board.tiles || [];
  const fValue = Number(board.f_value || 0);
  const fPct = Math.max(0, Math.min(100, (fValue / 10) * 100));
  document.getElementById("f-fill").style.width = `${{fPct}}%`;
  document.getElementById("f-text").textContent = fValue.toFixed(2);
  document.getElementById("marker-owner").textContent =
    board.marker_owner_player_id != null ? `marker P${{board.marker_owner_player_id}}` : "marker -";

  for (let i = 0; i < 40; i++) {{
    const tile = tiles[i] || {{}};
    const owner = tile.owner_player_id;
    const card = document.createElement("div");
    card.className = "tile" + (owner != null ? " owned" : "");
    if (owner != null) {{
      const idx = (owner - 1) % PLAYER_COLORS.length;
      card.style.borderColor = owner === HUMAN_SEAT ? "#ffd060" : PLAYER_COLORS[idx];
      card.style.background = PLAYER_LIGHTS[idx];
    }}
    const pawns = tile.pawn_player_ids || [];
    const pawnText = pawns.map(pid => pid === HUMAN_SEAT ? "*" : "o").join("");
    const costBits = [];
    if (tile.purchase_cost != null) costBits.push(`P${{tile.purchase_cost}}`);
    if (tile.rent_cost != null) costBits.push(`R${{tile.rent_cost}}`);
    if ((tile.score_coin_count || 0) > 0) costBits.push(`C${{tile.score_coin_count}}`);
    card.innerHTML = `
      <div class="tile-index">${{i}}</div>
      <span class="tile-kind">${{TILE_LABELS[tile.tile_kind] || tile.tile_kind || "?"}}</span>
      <div class="tile-pawns">${{pawnText}}</div>
      <div class="tile-meta">${{owner != null ? `P${{owner}} ` : ""}}${{costBits.join(" ")}}</div>
    `;
    grid.appendChild(card);
  }}
}}

function renderPlayers(players, activeId) {{
  const panel = document.getElementById("players-panel");
  panel.innerHTML = `<div class="sec-title">Players</div>`;
  for (const p of players) {{
    const pid = p.player_id;
    const isHuman = pid === HUMAN_SEAT;
    const isActive = pid === activeId;
    const color = isHuman ? "#ffd060" : PLAYER_COLORS[(pid - 1) % PLAYER_COLORS.length];
    const markStatus = p.mark_status || "clear";
    const markLabel = markStatus === "immune"
      ? "Immune"
      : (markStatus === "marked" ? "Marked" : "Clear");
    const tricks = (p.public_tricks || []).join(", ") || "-";
    const hidden = p.hidden_trick_count || 0;

    const card = document.createElement("div");
    card.className =
      "player-card" +
      (isActive ? " active" : "") +
      (isHuman ? " human-seat" : "") +
      (p.alive === false ? " dead" : "");
    card.style.borderColor = isActive ? color : "";
    card.innerHTML = `
      <div class="player-name" style="color:${{color}}">P${{pid}}${{isHuman ? " (Human)" : ""}}</div>
      <div class="player-character">${{p.character || "-"}}</div>
      <div class="stat-row">
        <span class="stat">$ ${{p.cash ?? "?"}}</span>
        <span class="stat">Sh ${{p.shards ?? "?"}}</span>
        <span class="stat">Tiles ${{p.owned_tile_count ?? "?"}}</span>
        <span class="stat">Coins ${{p.placed_score_coins ?? "?"}}</span>
      </div>
      <span class="mark mark-${{markStatus}}">${{markLabel}}</span>
      <div class="tricks-row">Public tricks: ${{tricks}}${{hidden > 0 ? ` (+${{hidden}} hidden)` : ""}}</div>
    `;
    panel.appendChild(card);
  }}
}}

setInterval(pollEvents, POLL_MS);
setInterval(pollPrompt, POLL_MS);
pollEvents();
pollPrompt();
</script>
</body>
</html>
"""
