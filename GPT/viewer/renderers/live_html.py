"""Phase 3 — Live spectator HTML renderer.

Produces a self-contained HTML page that polls ``/events?since=N`` and
updates the board, player panels, and event feed in real time.

The page shares the same visual design as the Phase 2 offline viewer
(dark theme, 40-tile board, player cards) but:
  - starts empty and fills as events arrive
  - shows a LIVE / DONE status indicator
  - has a speed slider that controls client-side replay pace
  - buffers incoming events into turn groups via turn_end_snapshot anchors
"""
from __future__ import annotations


def render_live_html(
    session_id: str = "",
    seed: int = 0,
    poll_interval_ms: int = 300,
) -> str:
    return _TEMPLATE.format(
        session_id=session_id or "...",
        seed=seed,
        poll_interval_ms=poll_interval_ms,
    )


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Live Spectator — seed {seed}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
  background: #1a1a2e; color: #e0e0f0; min-height: 100vh;
}}
header {{
  background: #16213e; padding: 10px 18px;
  border-bottom: 2px solid #0f3460;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}}
header h1 {{ font-size: 1rem; color: #8eb4ff; font-weight: 700; }}
.badge {{
  background: #0f3460; border-radius: 12px;
  padding: 3px 10px; font-size: 0.75rem; color: #a0b8e0;
}}
.badge.live {{
  background: #3a1a1a; color: #ff6060;
  animation: pulse 1.2s infinite;
}}
.badge.done {{ background: #1a3a1a; color: #60ff80; }}
@keyframes pulse {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:0.4 }} }}

.main-layout {{
  display: grid;
  grid-template-columns: 1fr 220px;
  height: calc(100vh - 48px);
}}
.center {{
  overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px;
}}
.section {{
  background: #16213e; border-radius: 8px; padding: 10px 12px;
}}
.sec-title {{
  font-size: 0.72rem; color: #6080c0; text-transform: uppercase;
  letter-spacing: 1px; margin-bottom: 6px;
}}

/* Event feed */
.event-item {{
  display: flex; gap: 8px; align-items: baseline;
  padding: 3px 0; border-bottom: 1px solid #1f2e50;
  font-size: 0.8rem;
}}
.event-item:last-child {{ border-bottom: none; }}
.ev-icon {{ width: 18px; text-align: center; flex-shrink: 0; }}
.ev-actor {{ font-weight: 600; min-width: 28px; color: #8eb4ff; flex-shrink: 0; }}
.ev-type {{ color: #6080c0; font-size: 0.7rem; min-width: 90px; flex-shrink: 0; }}
.ev-detail {{ color: #c0d0e8; }}

/* Board */
.board-grid {{
  display: grid; grid-template-columns: repeat(10, 1fr); gap: 3px; margin-top: 6px;
}}
.tile {{
  aspect-ratio: 1; border-radius: 4px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; font-size: 0.55rem;
  position: relative; border: 1px solid #2a3a5a; background: #1a2a40;
  cursor: default; transition: transform 0.1s;
}}
.tile:hover {{ transform: scale(1.08); z-index: 10; }}
.tile .tidx {{ color: #4060a0; font-size: 0.48rem; }}
.tile .tkind {{ font-size: 0.55rem; }}
.tile.owned {{ border-width: 2px; }}
.tile .pawn {{
  position: absolute; top: 1px; right: 1px; font-size: 0.5rem; line-height: 1;
}}
.tile-tt {{
  display: none; position: absolute; bottom: 110%; left: 50%;
  transform: translateX(-50%); background: #0a1020;
  border: 1px solid #3050a0; border-radius: 6px;
  padding: 4px 8px; font-size: 0.7rem; color: #c0d0e8;
  white-space: nowrap; z-index: 100; pointer-events: none;
}}
.tile:hover .tile-tt {{ display: block; }}

/* F bar */
.f-wrap {{
  display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 0.76rem;
}}
.f-bg {{ flex: 1; height: 7px; background: #1a2a40; border-radius: 4px; overflow: hidden; }}
.f-fill {{
  height: 100%; background: linear-gradient(90deg, #4e8ef7, #f0a030);
  border-radius: 4px; transition: width 0.4s;
}}

/* Players panel */
.players-panel {{
  background: #13193a; border-left: 1px solid #0f3460;
  overflow-y: auto; padding: 10px 8px;
  display: flex; flex-direction: column; gap: 8px;
}}
.player-card {{
  border-radius: 8px; padding: 8px 10px;
  border: 1px solid #2a3a5a; font-size: 0.76rem;
}}
.player-card.dead {{ opacity: 0.4; }}
.player-card.active {{ border-width: 2px; }}
.pname {{ font-weight: 700; font-size: 0.84rem; margin-bottom: 3px; }}
.pchar {{ font-size: 0.7rem; color: #8090b0; margin-bottom: 3px; }}
.stat-row {{ display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 2px; }}
.stat {{
  background: #1a2a40; border-radius: 10px;
  padding: 1px 7px; font-size: 0.68rem;
}}
.mark {{
  display: inline-block; padding: 1px 6px;
  border-radius: 8px; font-size: 0.65rem; margin-top: 2px;
}}
.mark-clear {{ background: #1a3a1a; color: #60c060; }}
.mark-marked {{ background: #3a1a1a; color: #ff6060; }}
.mark-immune {{ background: #1a1a3a; color: #6080ff; }}
.tricks-row {{ font-size: 0.66rem; color: #6080a0; margin-top: 2px; }}

/* Turn header */
.turn-hdr {{
  border-left: 4px solid #4e8ef7; padding: 8px 12px;
}}
.turn-hdr h2 {{ font-size: 0.95rem; font-weight: 700; }}
.turn-hdr .sub {{ font-size: 0.75rem; color: #8090b0; margin-top: 2px; }}

/* Progress */
.progress-wrap {{
  display: flex; align-items: center; gap: 10px; font-size: 0.76rem;
}}
.prog-bg {{ flex: 1; height: 5px; background: #1a2a40; border-radius: 3px; overflow: hidden; }}
.prog-fill {{ height: 100%; background: #4e8ef7; transition: width 0.3s; }}

/* Speed control */
.speed-wrap {{
  display: flex; align-items: center; gap: 8px; font-size: 0.76rem; color: #8090b0;
}}
input[type=range] {{ accent-color: #4e8ef7; }}

/* Empty state */
.empty-msg {{ color: #4060a0; font-style: italic; font-size: 0.8rem; padding: 8px 0; }}
</style>
</head>
<body>

<header>
  <h1>Live Spectator</h1>
  <span class="badge" id="status-badge">연결 중...</span>
  <span class="badge">seed {seed}</span>
  <span class="badge" id="event-count">0 events</span>
  <span class="badge" id="turn-badge">Turn 0</span>
  <div style="flex:1"></div>
  <div class="speed-wrap">
    <span>재생 속도</span>
    <input type="range" id="speed-slider" min="100" max="2000" step="100" value="600">
    <span id="speed-label">0.6s/턴</span>
  </div>
</header>

<div class="main-layout">
  <div class="center">

    <!-- Turn header -->
    <div class="section turn-hdr" id="turn-hdr" style="display:none">
      <h2 id="turn-title">—</h2>
      <div class="sub" id="turn-sub"></div>
    </div>

    <!-- Progress -->
    <div class="section">
      <div class="sec-title">진행</div>
      <div class="progress-wrap">
        <div class="prog-bg"><div class="prog-fill" id="prog-fill" style="width:0%"></div></div>
        <span id="prog-text">—</span>
      </div>
    </div>

    <!-- Event feed -->
    <div class="section" id="event-section">
      <div class="sec-title">이벤트 피드 (최근 20개)</div>
      <div id="event-feed"><div class="empty-msg">게임 시작 대기 중...</div></div>
    </div>

    <!-- Board -->
    <div class="section">
      <div class="sec-title">보드</div>
      <div class="f-wrap">
        <span>F값</span>
        <div class="f-bg"><div class="f-fill" id="f-fill" style="width:0%"></div></div>
        <span id="f-text">—</span>
        <span style="font-size:0.7rem;color:#8090b0">징표 <span id="marker-owner">—</span></span>
      </div>
      <div class="board-grid" id="board-grid"></div>
    </div>

  </div>

  <div class="players-panel" id="players-panel">
    <div style="font-size:0.73rem;color:#6080c0;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #1a2a40;padding-bottom:6px;margin-bottom:6px">플레이어</div>
    <div class="empty-msg">대기 중...</div>
  </div>
</div>

<script>
const PLAYER_COLORS = ["#4e8ef7","#e85d5d","#5dbf5d","#f0a030"];
const PLAYER_COLORS_LIGHT = ["#d0e4ff","#ffd0d0","#d0ffd0","#fff0c8"];
const TILE_ICONS = {{F1:"🏁",F2:"🏁",S:"⭐",T2:"🏘",T3:"🏛",MALICIOUS:"☠️"}};

const EV_ICONS = {{
  dice_roll:"🎲", player_move:"🚶", landing_resolved:"📍",
  rent_paid:"💸", tile_purchased:"🏠", fortune_drawn:"🃏",
  fortune_resolved:"✨", f_value_change:"📊", lap_reward_chosen:"🎁",
  mark_resolved:"🎯", marker_transferred:"🏷️", bankruptcy:"💀",
  weather_reveal:"🌤️", draft_pick:"🃏", final_character_choice:"👤",
  trick_window_open:"🪄", round_start:"📅", session_start:"🎮", game_end:"🏆",
}};

// ── State ─────────────────────────────────────────────────────────────────
let lastStep = 0;         // next step_index to fetch from
let allEvents = [];       // accumulated raw events
let currentSnapshot = null;  // latest turn_end_snapshot state
let currentTurnIdx = 0;
let currentActorId = null;
let isDone = false;
let playQueue = [];       // events waiting to be displayed
let playing = false;
let pollInterval = null;
let playTimer = null;

// ── Speed slider ──────────────────────────────────────────────────────────
const slider = document.getElementById("speed-slider");
const speedLabel = document.getElementById("speed-label");
function getPlayDelay() {{ return parseInt(slider.value); }}
slider.oninput = () => {{
  speedLabel.textContent = (slider.value / 1000).toFixed(1) + "s/턴";
}};

// ── Polling ───────────────────────────────────────────────────────────────
async function poll() {{
  if (isDone) return;
  try {{
    const resp = await fetch(`/events?since=${{lastStep}}`);
    const data = await resp.json();
    if (data.events && data.events.length > 0) {{
      playQueue.push(...data.events);
      const last = data.events[data.events.length - 1];
      lastStep = last.step_index + 1;
      document.getElementById("event-count").textContent = data.total + " events";
      if (!playing) drainQueue();
    }}
    if (data.done) {{
      isDone = true;
      clearInterval(pollInterval);
      document.getElementById("status-badge").textContent = "DONE";
      document.getElementById("status-badge").className = "badge done";
    }}
  }} catch(e) {{
    // server not ready yet
  }}
}}

function drainQueue() {{
  if (playQueue.length === 0) {{ playing = false; return; }}
  playing = true;
  const ev = playQueue.shift();
  processEvent(ev);
  const isTurnEnd = ev.event_type === "turn_end_snapshot";
  const delay = isTurnEnd ? getPlayDelay() : 40;
  playTimer = setTimeout(drainQueue, delay);
}}

// ── Event processing ──────────────────────────────────────────────────────
function processEvent(ev) {{
  const etype = ev.event_type;

  // Status badge
  if (etype === "session_start") {{
    document.getElementById("status-badge").textContent = "LIVE";
    document.getElementById("status-badge").className = "badge live";
  }}
  if (etype === "game_end") {{
    const w = ev.winner_player_id;
    document.getElementById("status-badge").textContent = w ? `P${{w}} 승리` : "게임 종료";
    document.getElementById("status-badge").className = "badge done";
  }}

  // Turn tracking
  if (etype === "turn_start") {{
    currentTurnIdx = ev.turn_index;
    currentActorId = ev.acting_player_id;
    const hdr = document.getElementById("turn-hdr");
    hdr.style.display = "";
    const color = currentActorId ? PLAYER_COLORS[((currentActorId-1) % PLAYER_COLORS.length)] : "#8090b0";
    hdr.style.borderLeftColor = color;
    document.getElementById("turn-title").textContent =
      `Turn ${{currentTurnIdx}} — P${{currentActorId ?? "?"}}` + (ev.skipped ? " (건너뜀)" : "");
    document.getElementById("turn-sub").textContent = `Round ${{ev.round_index}}`;
    document.getElementById("turn-badge").textContent = `Turn ${{currentTurnIdx}}`;
  }}

  // Snapshot: update board + players
  if (etype === "turn_end_snapshot") {{
    const nested = ev.snapshot || {{}};
    currentSnapshot = {{
      players: ev.players || nested.players || [],
      board: ev.board || nested.board || {{}},
    }};
    renderBoard(currentSnapshot.board);
    renderPlayers(currentSnapshot.players, currentActorId);
  }}

  // Progress (rough: use turn_index as proxy)
  if (currentTurnIdx > 0) {{
    const pct = Math.min(95, currentTurnIdx * 1.5);
    document.getElementById("prog-fill").style.width = pct + "%";
    document.getElementById("prog-text").textContent = `Turn ${{currentTurnIdx}}`;
  }}
  if (etype === "game_end") {{
    document.getElementById("prog-fill").style.width = "100%";
  }}

  // Event feed (skip low-value scaffolding)
  const SKIP_FEED = new Set(["turn_end_snapshot","trick_window_open","trick_window_closed"]);
  if (!SKIP_FEED.has(etype)) appendEventFeed(ev);
}}

function appendEventFeed(ev) {{
  const feed = document.getElementById("event-feed");
  // Remove empty placeholder
  const empty = feed.querySelector(".empty-msg");
  if (empty) feed.removeChild(empty);

  const pid = ev.acting_player_id;
  const actor = pid != null ? `P${{pid}}` : "—";
  const actorColor = pid != null ? PLAYER_COLORS[((pid-1) % PLAYER_COLORS.length)] : "#8090b0";
  const icon = EV_ICONS[ev.event_type] || "▸";
  const detail = buildDetail(ev);

  const row = document.createElement("div");
  row.className = "event-item";
  row.innerHTML = `
    <span class="ev-icon">${{icon}}</span>
    <span class="ev-actor" style="color:${{actorColor}}">${{actor}}</span>
    <span class="ev-type">${{ev.event_type}}</span>
    <span class="ev-detail">${{detail}}</span>
  `;
  feed.appendChild(row);

  // Keep only last 20
  while (feed.children.length > 20) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}}

function buildDetail(ev) {{
  const t = ev.event_type;
  if (t === "dice_roll") {{
    const vals = ev.dice || ev.dice_values || [];
    const total = ev.total || ev.move || vals.reduce((a,b)=>a+b,0);
    return `${{vals}} = ${{total}}`;
  }}
  if (t === "player_move") {{
    const lapped = ev.lapped ? " [랩!]" : "";
    return `${{ev.from_pos ?? "?"}}→${{ev.to_pos ?? "?"}}${{lapped}}`;
  }}
  if (t === "rent_paid") {{
    const payer = ev.payer_player_id ?? ev.payer;
    const owner = ev.owner_player_id ?? ev.owner;
    const amt = ev.final_amount ?? ev.amount;
    return `P${{payer}}→P${{owner}} ${{amt}}냥`;
  }}
  if (t === "tile_purchased") return `tile ${{ev.tile_index}} −${{ev.cost}}`;
  if (t === "fortune_drawn") return ev.card_name || "";
  if (t === "f_value_change") return `F ${{ev.before}}→${{ev.after}}`;
  if (t === "lap_reward_chosen") return `${{ev.choice}} ×${{ev.amount}}`;
  if (t === "mark_resolved") {{
    const ok = ev.success ? "성공" : "실패";
    return `P${{ev.source_player_id ?? ev.source}}→P${{ev.target_player_id ?? ev.target}} ${{ok}}`;
  }}
  if (t === "weather_reveal") return ev.weather_name || ev.card || "";
  if (t === "final_character_choice") return ev.character || "";
  if (t === "bankruptcy") return "파산";
  if (t === "game_end") {{
    const w = ev.winner_player_id;
    return w ? `P${{w}} 승리` : ev.reason || "";
  }}
  return "";
}}

// ── Board ──────────────────────────────────────────────────────────────────
function renderBoard(board) {{
  if (!board) return;
  const grid = document.getElementById("board-grid");
  grid.innerHTML = "";
  const tiles = board.tiles || [];

  // Build owner/pawn maps
  const ownerMap = {{}};
  const pawnMap = {{}};
  tiles.forEach(t => {{
    if (t.owner_player_id != null) ownerMap[t.tile_index] = t.owner_player_id;
    if (t.pawn_player_ids && t.pawn_player_ids.length) pawnMap[t.tile_index] = t.pawn_player_ids;
  }});

  for (let i = 0; i < 40; i++) {{
    const tile = tiles[i] || {{}};
    const div = document.createElement("div");
    div.className = "tile";
    const ownerId = ownerMap[i];
    if (ownerId != null) {{
      const ci = (ownerId - 1) % PLAYER_COLORS.length;
      div.style.borderColor = PLAYER_COLORS[ci];
      div.style.background = PLAYER_COLORS_LIGHT[ci];
      div.classList.add("owned");
    }}
    const kind = tile.tile_kind || "?";
    const icon = TILE_ICONS[kind] || "▪";
    div.innerHTML = `<span class="tidx">${{i}}</span><span class="tkind">${{icon}}</span>`;

    const pawns = pawnMap[i];
    if (pawns && pawns.length) {{
      const ps = document.createElement("span");
      ps.className = "pawn";
      ps.textContent = pawns.map(() => "●").join("");
      div.appendChild(ps);
    }}

    const tt = document.createElement("div");
    tt.className = "tile-tt";
    const on = ownerId ? ` P${{ownerId}}소유` : "";
    const re = tile.rent_cost ? ` 렌트${{tile.rent_cost}}` : "";
    const co = tile.score_coin_count ? ` 🪙${{tile.score_coin_count}}` : "";
    const pa = pawns && pawns.length ? ` P${{pawns.join(",")}}` : "";
    tt.textContent = `[${{i}}] ${{kind}}${{on}}${{re}}${{co}}${{pa}}`;
    div.appendChild(tt);
    grid.appendChild(div);
  }}

  const fv = board.f_value ?? 0;
  document.getElementById("f-fill").style.width = Math.min(100, (fv/10)*100) + "%";
  document.getElementById("f-text").textContent =
    typeof fv === "number" ? fv.toFixed(2) : fv;
  const mo = board.marker_owner_player_id;
  document.getElementById("marker-owner").textContent = mo != null ? `P${{mo}}` : "—";
}}

// ── Players panel ──────────────────────────────────────────────────────────
function renderPlayers(players, actorId) {{
  const panel = document.getElementById("players-panel");
  panel.innerHTML = '<div style="font-size:0.73rem;color:#6080c0;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #1a2a40;padding-bottom:6px;margin-bottom:6px">플레이어</div>';

  players.forEach(p => {{
    const ci = (p.player_id - 1) % PLAYER_COLORS.length;
    const color = PLAYER_COLORS[ci];
    const isActor = p.player_id === actorId;
    const card = document.createElement("div");
    card.className = "player-card" + (p.alive ? "" : " dead") + (isActor ? " active" : "");
    card.style.borderColor = color;

    const markClass = p.mark_status === "marked" ? "mark-marked"
                    : p.mark_status === "immune" ? "mark-immune" : "mark-clear";
    const pub = (p.public_tricks || []).join(", ") || "—";
    const hidden = p.hidden_trick_count || 0;
    const effects = (p.public_effects || []).join(", ");

    card.innerHTML = `
      <div class="pname" style="color:${{color}}">${{isActor ? "▶ " : ""}}P${{p.player_id}} ${{p.alive ? "" : "💀"}}</div>
      <div class="pchar">${{p.character || "?"}} · tile ${{p.position}}</div>
      <div class="stat-row">
        <span class="stat" style="font-size:0.76rem">💰${{p.cash}}</span>
        <span class="stat" style="font-size:0.76rem">🔮${{p.shards}}</span>
        <span class="stat">🪙${{p.hand_score_coins}}+${{p.placed_score_coins}}</span>
        <span class="stat">🏠${{p.owned_tile_count}}</span>
      </div>
      <span class="mark ${{markClass}}">${{p.mark_status}}</span>
      ${{effects ? `<div style="font-size:0.63rem;color:#8090b0;margin-top:2px">⚡ ${{effects}}</div>` : ""}}
      <div class="tricks-row">잔꾀: ${{pub}} [${{hidden}}H]</div>
    `;
    panel.appendChild(card);
  }});
}}

// ── Init ───────────────────────────────────────────────────────────────────
renderBoard({{}}); // render empty 40-tile grid
pollInterval = setInterval(poll, {poll_interval_ms});
poll(); // immediate first poll
</script>
</body>
</html>
"""
