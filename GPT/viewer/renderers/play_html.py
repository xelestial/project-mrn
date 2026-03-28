"""Phase 4 — Human Play HTML renderer.

Extends the Phase 3 live spectator page with a Decision Panel that:
  - polls GET /prompt every 200 ms for a pending decision
  - renders the decision options as clickable buttons
  - POSTs the chosen option_id to POST /decision
  - highlights the human player's seat distinctly
"""
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
        poll_interval_ms=poll_interval_ms,
    )


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Human Play — seed {seed} — P{human_seat}</title>
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
header h1 {{ font-size: 1rem; color: #ffd060; font-weight: 700; }}
.badge {{
  background: #0f3460; border-radius: 12px;
  padding: 3px 10px; font-size: 0.75rem; color: #a0b8e0;
}}
.badge.live {{ background: #3a1a1a; color: #ff6060; animation: pulse 1.2s infinite; }}
.badge.done {{ background: #1a3a1a; color: #60ff80; }}
.badge.human {{ background: #2a2a00; color: #ffd060; font-weight: 700; }}
.badge.waiting {{ background: #2a1a3a; color: #c060ff; animation: pulse 0.8s infinite; }}
@keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.4}} }}

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

/* ── Decision Panel ─────────────────────────────────────────────────── */
#decision-overlay {{
  display: none;
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  z-index: 500;
  align-items: center; justify-content: center;
}}
#decision-overlay.visible {{ display: flex; }}
#decision-panel {{
  background: #1a1f3a;
  border: 2px solid #ffd060;
  border-radius: 14px;
  padding: 24px 28px;
  max-width: 480px; width: 92%;
  box-shadow: 0 8px 40px rgba(0,0,0,0.7);
}}
.dp-title {{
  font-size: 1.05rem; font-weight: 700; color: #ffd060;
  margin-bottom: 6px;
}}
.dp-sub {{
  font-size: 0.78rem; color: #8090b0; margin-bottom: 16px;
}}
.dp-options {{
  display: flex; flex-direction: column; gap: 8px;
}}
.dp-btn {{
  background: #0f3460; border: 1px solid #2a4a80;
  color: #d0e4ff; border-radius: 8px;
  padding: 10px 14px; font-size: 0.88rem;
  cursor: pointer; text-align: left;
  transition: background 0.15s, border-color 0.15s;
}}
.dp-btn:hover {{ background: #1a4a80; border-color: #ffd060; color: #fff; }}
.dp-btn.selected {{ background: #2a3a00; border-color: #ffd060; color: #ffd060; }}
.dp-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
.dp-timeout {{
  margin-top: 10px; font-size: 0.72rem; color: #6070a0; text-align: right;
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
.player-card.human-seat {{
  border-color: #ffd060 !important;
  box-shadow: 0 0 6px rgba(255,208,96,0.3);
}}
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
.turn-hdr {{ border-left: 4px solid #4e8ef7; padding: 8px 12px; }}
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

<!-- Decision Overlay -->
<div id="decision-overlay">
  <div id="decision-panel">
    <div class="dp-title" id="dp-title">결정이 필요합니다</div>
    <div class="dp-sub" id="dp-sub"></div>
    <div class="dp-options" id="dp-options"></div>
    <div class="dp-timeout" id="dp-timeout">제한 시간: 5분</div>
  </div>
</div>

<header>
  <h1>Human Play</h1>
  <span class="badge human">P{human_seat} (나)</span>
  <span class="badge" id="status-badge">연결 중...</span>
  <span class="badge">seed {seed}</span>
  <span class="badge" id="event-count">0 events</span>
  <span class="badge" id="turn-badge">Turn 0</span>
  <span class="badge waiting" id="decision-badge" style="display:none">결정 대기 중...</span>
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
const HUMAN_SEAT = {human_seat};
const POLL_MS = {poll_interval_ms};
const PLAYER_COLORS = ["#4e8ef7","#e85d5d","#5dbf5d","#f0a030"];
const PLAYER_COLORS_LIGHT = ["#d0e4ff","#ffd0d0","#d0ffd0","#fff0c8"];
const TILE_ICONS = {{F1:"F1",F2:"F2",S:"★",T2:"T2",T3:"T3",MALICIOUS:"☠"}};
const EV_ICONS = {{
  dice_roll:"🎲", player_move:"→", landing_resolved:"📍",
  rent_paid:"💸", tile_purchased:"🏠", fortune_drawn:"🃏",
  fortune_resolved:"✨", f_value_change:"📊", lap_reward_chosen:"🎁",
  mark_resolved:"🎯", marker_transferred:"🏷", bankruptcy:"💀",
  weather_reveal:"🌤", draft_pick:"🃏", final_character_choice:"👤",
  trick_window_open:"🪄", round_start:"📅", session_start:"🎮", game_end:"🏆",
}};

// ── State ──────────────────────────────────────────────────────────────────
let lastStep = 0;
let currentSnapshot = null;
let currentTurnIdx = 0;
let currentActorId = null;
let isDone = false;
let playQueue = [];
let playing = false;
let pollTimer = null;
let playTimer = null;
let promptPollTimer = null;
let pendingDecision = false;

// ── Speed slider ───────────────────────────────────────────────────────────
const slider = document.getElementById("speed-slider");
const speedLabel = document.getElementById("speed-label");
function getPlayDelay() {{ return parseInt(slider.value); }}
slider.oninput = () => {{
  speedLabel.textContent = (slider.value / 1000).toFixed(1) + "s/턴";
}};

// ── Event polling ──────────────────────────────────────────────────────────
async function pollEvents() {{
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
      clearInterval(pollTimer);
      document.getElementById("status-badge").textContent = "DONE";
      document.getElementById("status-badge").className = "badge done";
    }}
  }} catch(e) {{}}
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

// ── Prompt polling ─────────────────────────────────────────────────────────
async function pollPrompt() {{
  if (isDone) return;
  try {{
    const resp = await fetch("/prompt");
    const data = await resp.json();
    if (data.type && !pendingDecision) {{
      pendingDecision = true;
      showDecision(data);
    }} else if (!data.type && pendingDecision) {{
      // Decision was resolved (timeout or accepted)
      pendingDecision = false;
      hideDecision();
    }}
  }} catch(e) {{}}
}}

function showDecision(prompt) {{
  const overlay = document.getElementById("decision-overlay");
  const title = document.getElementById("dp-title");
  const sub = document.getElementById("dp-sub");
  const optsEl = document.getElementById("dp-options");
  const badge = document.getElementById("decision-badge");

  badge.style.display = "";

  title.textContent = decisionTitle(prompt.type);
  sub.textContent = decisionSub(prompt);
  optsEl.innerHTML = "";

  const opts = prompt.options || [];
  opts.forEach(opt => {{
    const btn = document.createElement("button");
    btn.className = "dp-btn";
    btn.textContent = opt.label || opt.id;
    btn.dataset.optId = opt.id;
    btn.onclick = () => submitDecision(opt.id, btn, optsEl);
    optsEl.appendChild(btn);
  }});

  overlay.classList.add("visible");
}}

function hideDecision() {{
  document.getElementById("decision-overlay").classList.remove("visible");
  document.getElementById("decision-badge").style.display = "none";
  pendingDecision = false;
}}

async function submitDecision(optionId, clickedBtn, container) {{
  // Disable all buttons immediately
  container.querySelectorAll(".dp-btn").forEach(b => b.disabled = true);
  clickedBtn.classList.add("selected");

  try {{
    const resp = await fetch("/decision", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{option_id: optionId}}),
    }});
    if (resp.ok) {{
      // Small visual feedback before hiding
      setTimeout(hideDecision, 300);
    }} else {{
      // Re-enable on failure
      container.querySelectorAll(".dp-btn").forEach(b => b.disabled = false);
      clickedBtn.classList.remove("selected");
    }}
  }} catch(e) {{
    container.querySelectorAll(".dp-btn").forEach(b => b.disabled = false);
    clickedBtn.classList.remove("selected");
  }}
}}

function decisionTitle(type) {{
  const titles = {{
    movement: "이동 방법 선택",
    lap_reward: "출발점 통과 보상 선택",
    draft_card: "캐릭터 드래프트",
    final_character: "최종 캐릭터 선택",
    trick_to_use: "트릭 카드 사용",
    purchase_tile: "타일 구매 여부",
    hidden_trick_card: "숨길 트릭 카드 선택",
    mark_target: "표적 선택",
    coin_placement: "코인 배치 타일 선택",
  }};
  return titles[type] || type;
}}

function decisionSub(prompt) {{
  if (prompt.type === "movement") {{
    return `현재 위치: ${{prompt.player_position ?? "?"}} | 보유 현금: ${{prompt.player_cash ?? "?"}}냥`;
  }}
  if (prompt.type === "purchase_tile") {{
    const zn = prompt.tile_zone ? ` (존: ${{prompt.tile_zone}})` : "";
    return `타일 ${{prompt.tile_index}}${{zn}} — 비용: ${{prompt.cost}}냥 | 보유: ${{prompt.player_cash}}냥`;
  }}
  if (prompt.type === "lap_reward") {{
    const p = prompt.pools || {{}};
    return `예산: ${{prompt.budget}}포인트 | 풀: 현금${{p.cash ?? "?"}} / 조각${{p.shards ?? "?"}} / 코인${{p.coins ?? "?"}}`;
  }}
  if (prompt.type === "trick_to_use") {{
    return "트릭 카드를 이번 턴에 사용하시겠습니까?";
  }}
  if (prompt.type === "mark_target") {{
    return `${{prompt.actor_name || ""}} 효과 — 표적을 선택하세요`;
  }}
  return "";
}}

// ── Event processing ───────────────────────────────────────────────────────
function processEvent(ev) {{
  const etype = ev.event_type;

  if (etype === "session_start") {{
    document.getElementById("status-badge").textContent = "LIVE";
    document.getElementById("status-badge").className = "badge live";
  }}
  if (etype === "game_end") {{
    const w = ev.winner_player_id;
    document.getElementById("status-badge").textContent = w != null ? `P${{w}} 승리` : "게임 종료";
    document.getElementById("status-badge").className = "badge done";
  }}

  if (etype === "turn_start") {{
    currentTurnIdx = ev.turn_index;
    currentActorId = ev.acting_player_id;
    const hdr = document.getElementById("turn-hdr");
    hdr.style.display = "";
    const isHuman = (currentActorId === HUMAN_SEAT);
    const baseColor = currentActorId != null
      ? PLAYER_COLORS[currentActorId % PLAYER_COLORS.length]
      : "#8090b0";
    hdr.style.borderLeftColor = isHuman ? "#ffd060" : baseColor;
    document.getElementById("turn-title").textContent =
      `Turn ${{currentTurnIdx}} — P${{currentActorId ?? "?"}}` +
      (isHuman ? " [나]" : "") +
      (ev.skipped ? " (건너뜀)" : "");
    document.getElementById("turn-sub").textContent = `Round ${{ev.round_index}}`;
    document.getElementById("turn-badge").textContent = `Turn ${{currentTurnIdx}}`;
  }}

  if (etype === "turn_end_snapshot") {{
    const nested = ev.snapshot || {{}};
    currentSnapshot = {{
      players: ev.players || nested.players || [],
      board: ev.board || nested.board || {{}},
    }};
    renderBoard(currentSnapshot.board);
    renderPlayers(currentSnapshot.players, currentActorId);
  }}

  if (currentTurnIdx > 0) {{
    const pct = Math.min(95, currentTurnIdx * 1.5);
    document.getElementById("prog-fill").style.width = pct + "%";
    document.getElementById("prog-text").textContent = `Turn ${{currentTurnIdx}}`;
  }}
  if (etype === "game_end") {{
    document.getElementById("prog-fill").style.width = "100%";
  }}

  const SKIP_FEED = new Set(["turn_end_snapshot","trick_window_open","trick_window_closed"]);
  if (!SKIP_FEED.has(etype)) appendEventFeed(ev);
}}

function appendEventFeed(ev) {{
  const feed = document.getElementById("event-feed");
  const empty = feed.querySelector(".empty-msg");
  if (empty) feed.removeChild(empty);

  const pid = ev.acting_player_id;
  const actor = pid != null ? `P${{pid}}` : "—";
  const isHuman = (pid === HUMAN_SEAT);
  const actorColor = isHuman ? "#ffd060"
    : (pid != null ? PLAYER_COLORS[pid % PLAYER_COLORS.length] : "#8090b0");
  const icon = EV_ICONS[ev.event_type] || ">";
  const detail = buildDetail(ev);

  const row = document.createElement("div");
  row.className = "event-item";
  row.innerHTML = `
    <span class="ev-icon">${{icon}}</span>
    <span class="ev-actor" style="color:${{actorColor}}">${{actor}}${{isHuman?" *":""}}</span>
    <span class="ev-type">${{ev.event_type}}</span>
    <span class="ev-detail">${{detail}}</span>
  `;
  feed.appendChild(row);
  while (feed.children.length > 20) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}}

function buildDetail(ev) {{
  const t = ev.event_type;
  if (t === "dice_roll") {{
    const vals = ev.dice || ev.dice_values || [];
    const total = ev.total || ev.move || vals.reduce((a,b)=>a+b,0);
    return `${{JSON.stringify(vals)}} = ${{total}}`;
  }}
  if (t === "player_move") {{
    const lapped = ev.lapped ? " [랩!]" : "";
    return `${{ev.from_pos ?? "?"}} -> ${{ev.to_pos ?? "?"}}${{lapped}}`;
  }}
  if (t === "rent_paid") {{
    const payer = ev.payer_player_id ?? ev.payer;
    const owner = ev.owner_player_id ?? ev.owner;
    const amt = ev.final_amount ?? ev.amount;
    return `P${{payer}}->P${{owner}} ${{amt}}`;
  }}
  if (t === "tile_purchased") return `tile ${{ev.tile_index}} -${{ev.cost}}`;
  if (t === "fortune_drawn") return ev.card_name || "";
  if (t === "f_value_change") return `F ${{ev.before}}->${{ev.after}}`;
  if (t === "lap_reward_chosen") return `${{ev.choice}} x${{ev.amount}}`;
  if (t === "mark_resolved") {{
    const ok = ev.success ? "성공" : "실패";
    return `P${{ev.source_player_id ?? ev.source}}->P${{ev.target_player_id ?? ev.target}} ${{ok}}`;
  }}
  if (t === "weather_reveal") return ev.weather_name || ev.card || "";
  if (t === "final_character_choice") return ev.character || "";
  if (t === "bankruptcy") return "파산";
  if (t === "game_end") {{
    const w = ev.winner_player_id;
    return w != null ? `P${{w}} 승리` : (ev.reason || "");
  }}
  return "";
}}

// ── Board ──────────────────────────────────────────────────────────────────
function renderBoard(board) {{
  if (!board) return;
  const grid = document.getElementById("board-grid");
  grid.innerHTML = "";
  const tiles = board.tiles || [];

  const ownerMap = {{}};
  const pawnMap = {{}};
  tiles.forEach(t => {{
    if (t.owner_player_id != null) ownerMap[t.tile_index] = t.owner_player_id;
    if (t.pawn_player_ids && t.pawn_player_ids.length) pawnMap[t.tile_index] = t.pawn_player_ids;
  }});

  const fv = board.f_value ?? 0;
  const fPct = Math.min(100, Math.max(0, (fv / 10) * 100));
  document.getElementById("f-fill").style.width = fPct + "%";
  document.getElementById("f-text").textContent = fv.toFixed ? fv.toFixed(2) : fv;
  const mo = board.marker_owner_id;
  document.getElementById("marker-owner").textContent = mo != null ? `P${{mo}}` : "—";

  for (let i = 0; i < 40; i++) {{
    const tile = tiles[i] || {{}};
    const div = document.createElement("div");
    div.className = "tile";
    const ownerId = ownerMap[i];
    if (ownerId != null) {{
      const ci = ownerId % PLAYER_COLORS.length;
      div.style.borderColor = (ownerId === HUMAN_SEAT) ? "#ffd060" : PLAYER_COLORS[ci];
      div.style.background = PLAYER_COLORS_LIGHT[ci];
      div.classList.add("owned");
    }}
    const kind = tile.tile_kind || "?";
    const icon = TILE_ICONS[kind] || "?";
    div.innerHTML = `<span class="tidx">${{i}}</span><span class="tkind">${{icon}}</span>`;

    const pawns = pawnMap[i];
    if (pawns && pawns.length) {{
      const pawnSpan = document.createElement("span");
      pawnSpan.className = "pawn";
      pawnSpan.textContent = pawns.map(p => p === HUMAN_SEAT ? "★" : "●").join("");
      pawnSpan.style.color = pawns.includes(HUMAN_SEAT) ? "#ffd060" : "#e0e0f0";
      div.appendChild(pawnSpan);
    }}

    const tt = document.createElement("span");
    tt.className = "tile-tt";
    const costTxt = tile.rent_cost != null ? ` R${{tile.rent_cost}}` : "";
    const purTxt = tile.purchase_cost != null ? ` P${{tile.purchase_cost}}` : "";
    tt.textContent = `#${{i}} ${{kind}}${{costTxt}}${{purTxt}}` + (ownerId != null ? ` [P${{ownerId}}]` : "");
    div.appendChild(tt);

    grid.appendChild(div);
  }}
}}

// ── Players ────────────────────────────────────────────────────────────────
function renderPlayers(players, activeId) {{
  const panel = document.getElementById("players-panel");
  panel.innerHTML = `<div style="font-size:0.73rem;color:#6080c0;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #1a2a40;padding-bottom:6px;margin-bottom:6px">플레이어</div>`;

  players.forEach(p => {{
    const pid = p.player_id;
    const isHuman = (pid === HUMAN_SEAT);
    const isActive = (pid === activeId);
    const color = isHuman ? "#ffd060" : PLAYER_COLORS[pid % PLAYER_COLORS.length];

    const card = document.createElement("div");
    card.className = "player-card" +
      (p.alive === false ? " dead" : "") +
      (isActive ? " active" : "") +
      (isHuman ? " human-seat" : "");
    card.style.borderColor = isActive ? color : "";
    card.style.background = isActive
      ? `rgba(${{hexToRgb(color)}}, 0.08)`
      : "#16213e";

    const markClass = p.immune_to_marks ? "mark-immune"
      : (p.is_marked ? "mark-marked" : "mark-clear");
    const markTxt = p.immune_to_marks ? "면역"
      : (p.is_marked ? "표적됨" : "안전");

    const tricks = (p.trick_cards_visible || []).join(", ") || "—";
    const hidden = p.hidden_trick_count || 0;

    card.innerHTML = `
      <div class="pname" style="color:${{color}}">P${{pid}}${{isHuman ? " (나)" : ""}}</div>
      <div class="pchar">${{p.character || "—"}}</div>
      <div class="stat-row">
        <span class="stat">💰 ${{p.cash ?? "?"}}</span>
        <span class="stat">🔹 ${{p.shards ?? "?"}}</span>
        <span class="stat">🏠 ${{p.tiles_owned ?? "?"}}</span>
        <span class="stat">⭕ ${{p.score_coins_placed ?? "?"}}</span>
      </div>
      <span class="mark ${{markClass}}">${{markTxt}}</span>
      <div class="tricks-row">트릭: ${{tricks}}${{hidden > 0 ? ` (+${{hidden}}숨김)` : ""}}</div>
    `;
    panel.appendChild(card);
  }});
}}

function hexToRgb(hex) {{
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `${{r}},${{g}},${{b}}`;
}}

// ── Startup ────────────────────────────────────────────────────────────────
pollTimer = setInterval(pollEvents, POLL_MS);
promptPollTimer = setInterval(pollPrompt, POLL_MS);
pollEvents();
pollPrompt();
</script>
</body>
</html>
"""
