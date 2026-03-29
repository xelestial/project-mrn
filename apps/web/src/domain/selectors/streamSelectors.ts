import type { InboundMessage } from "../../core/contracts/stream";

export type TimelineItem = {
  seq: number;
  label: string;
  detail: string;
};

export type SituationViewModel = {
  actor: string;
  round: string;
  turn: string;
  eventType: string;
  weather: string;
};

export type LastMoveViewModel = {
  playerId: number | null;
  fromTileIndex: number | null;
  toTileIndex: number | null;
};

export type PlayerViewModel = {
  playerId: number;
  displayName: string;
  character: string;
  alive: boolean;
  position: number;
  cash: number;
  shards: number;
  hiddenTrickCount: number;
  ownedTileCount: number;
};

export type TileViewModel = {
  tileIndex: number;
  tileKind: string;
  zoneColor: string;
  purchaseCost: number | null;
  rentCost: number | null;
  ownerPlayerId: number | null;
  pawnPlayerIds: number[];
};

export type SnapshotViewModel = {
  round: number;
  turn: number;
  markerOwnerPlayerId: number | null;
  fValue: number;
  players: PlayerViewModel[];
  tiles: TileViewModel[];
};

const EVENT_LABELS: Record<string, string> = {
  session_start: "세션 시작",
  round_start: "라운드 시작",
  weather_reveal: "날씨 공개",
  draft_pick: "드래프트 선택",
  final_character_choice: "최종 캐릭터 선택",
  turn_start: "턴 시작",
  dice_roll: "이동값 결정",
  player_move: "말 이동",
  landing_resolved: "도착 칸 처리",
  tile_purchased: "토지 구매",
  marker_transferred: "징표 이동",
  lap_reward_chosen: "랩 보상 선택",
  fortune_drawn: "운수 공개",
  fortune_resolved: "운수 처리",
  turn_end_snapshot: "턴 종료 스냅샷",
  decision_timeout_fallback: "시간 초과 자동 처리",
  bankruptcy: "파산",
  game_end: "게임 종료",
};

function asString(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "-";
}

function asNumberText(value: unknown): string {
  return typeof value === "number" ? String(value) : "-";
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pickEventLabel(message: InboundMessage): string {
  if (message.type !== "event") {
    if (message.type === "prompt") {
      return "선택 요청";
    }
    if (message.type === "decision_ack") {
      return "선택 응답";
    }
    if (message.type === "heartbeat") {
      return "연결 상태";
    }
    if (message.type === "error") {
      return "오류";
    }
    return "알 수 없음";
  }
  const eventType = message.payload["event_type"];
  if (typeof eventType === "string" && eventType.trim()) {
    return EVENT_LABELS[eventType] ?? eventType;
  }
  return "이벤트";
}

function summarizePlayerMove(payload: Record<string, unknown>): string {
  const from = numberOrNull(payload["from_tile_index"] ?? payload["from_tile"] ?? payload["from_pos"]);
  const to = numberOrNull(payload["to_tile_index"] ?? payload["to_tile"] ?? payload["to_pos"]);
  const fromDisplay = from === null ? "?" : String(from + 1);
  const toDisplay = to === null ? "?" : String(to + 1);
  const path = Array.isArray(payload["path"]) ? payload["path"] : [];
  if (path.length > 0) {
    return `${fromDisplay} -> ${toDisplay} (${path.length}칸)`;
  }
  return `${fromDisplay} -> ${toDisplay}`;
}

function summarizeDiceRoll(payload: Record<string, unknown>): string {
  const cards = Array.isArray(payload["cards_used"])
    ? payload["cards_used"]
    : Array.isArray(payload["used_cards"])
      ? payload["used_cards"]
      : Array.isArray(payload["card_values"])
        ? payload["card_values"]
        : [];
  const dice = Array.isArray(payload["dice_values"])
    ? payload["dice_values"]
    : Array.isArray(payload["dice"])
      ? payload["dice"]
      : [];
  const total = payload["total_move"] ?? payload["total"] ?? payload["move"] ?? "?";
  if (cards.length > 0) {
    return `주사위 카드 ${cards.join(", ")} 사용 -> ${total}`;
  }
  if (dice.length > 0) {
    return `${dice.join(" + ")} = ${total}`;
  }
  return String(total);
}

function pickEventDetail(message: InboundMessage): string {
  if (message.type === "heartbeat") {
    const interval = message.payload["interval_ms"];
    const backpressure = message.payload["backpressure"];
    if (typeof interval === "number" && backpressure && typeof backpressure === "object") {
      const drop = (backpressure as Record<string, unknown>)["drop_count"];
      return `heartbeat ${interval}ms / drop ${typeof drop === "number" ? drop : 0}`;
    }
    return `heartbeat ${typeof interval === "number" ? `${interval}ms` : ""}`.trim();
  }
  if (message.type === "decision_ack") {
    const status = asString(message.payload["status"]);
    const reason = asString(message.payload["reason"]);
    return reason !== "-" ? `${status} (${reason})` : status;
  }
  if (message.type === "error") {
    return asString(message.payload["message"]);
  }

  const payload = message.payload;
  const eventType = payload["event_type"];
  if (eventType === "player_move") {
    return summarizePlayerMove(payload);
  }
  if (eventType === "dice_roll") {
    return summarizeDiceRoll(payload);
  }
  if (eventType === "tile_purchased") {
    const tile = numberOrNull(payload["tile_index"]);
    const cost = payload["cost"] ?? "?";
    return `${tile === null ? "?" : tile + 1}번 칸 구매 / ${cost}냥`;
  }
  if (eventType === "marker_transferred") {
    const from = payload["from_player_id"] ?? payload["from_owner"] ?? "?";
    const to = payload["to_player_id"] ?? payload["to_owner"] ?? "?";
    return `[징표] P${from} -> P${to}`;
  }
  if (eventType === "weather_reveal") {
    return asString(payload["weather_name"] ?? payload["weather"] ?? payload["card"]);
  }
  if (eventType === "landing_resolved") {
    return asString(payload["result_type"] ?? payload["result_code"] ?? payload["result"] ?? "도착 칸 처리");
  }
  if (eventType === "bankruptcy") {
    const pid = payload["player_id"] ?? payload["target_player_id"] ?? "?";
    return `P${pid} 파산`;
  }
  if (eventType === "lap_reward_chosen") {
    return asString(payload["choice"] ?? payload["reward"] ?? payload["summary"]);
  }

  const summary = payload["summary"];
  if (typeof summary === "string" && summary.trim()) {
    return summary;
  }
  return "";
}

export function selectTimeline(messages: InboundMessage[], limit = 12): TimelineItem[] {
  return messages
    .slice(-limit)
    .map((message) => ({
      seq: message.seq,
      label: pickEventLabel(message),
      detail: pickEventDetail(message),
    }))
    .reverse();
}

export function selectSituation(messages: InboundMessage[]): SituationViewModel {
  const last = messages.length > 0 ? messages[messages.length - 1] : null;
  if (!last) {
    return { actor: "-", round: "-", turn: "-", eventType: "-", weather: "-" };
  }
  return {
    actor:
      asString(last.payload["actor"]) !== "-"
        ? asString(last.payload["actor"])
        : asNumberText(last.payload["acting_player_id"] ?? last.payload["player_id"]),
    round: asNumberText(last.payload["round_index"]),
    turn: asNumberText(last.payload["turn_index"]),
    eventType: pickEventLabel(last),
    weather: asString(last.payload["weather_name"] ?? last.payload["weather"] ?? last.payload["card"]),
  };
}

export function selectLastMove(messages: InboundMessage[]): LastMoveViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event" || message.payload["event_type"] !== "player_move") {
      continue;
    }
    return {
      playerId: numberOrNull(message.payload["acting_player_id"] ?? message.payload["player_id"]),
      fromTileIndex: numberOrNull(message.payload["from_tile_index"] ?? message.payload["from_tile"] ?? message.payload["from_pos"]),
      toTileIndex: numberOrNull(message.payload["to_tile_index"] ?? message.payload["to_tile"] ?? message.payload["to_pos"]),
    };
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function toPlayerViewModel(raw: unknown): PlayerViewModel | null {
  if (!isRecord(raw)) {
    return null;
  }
  const playerId = raw["player_id"];
  if (typeof playerId !== "number") {
    return null;
  }
  return {
    playerId,
    displayName: typeof raw["display_name"] === "string" ? raw["display_name"] : `P${playerId}`,
    character: typeof raw["character"] === "string" ? raw["character"] : "-",
    alive: typeof raw["alive"] === "boolean" ? raw["alive"] : true,
    position: typeof raw["position"] === "number" ? raw["position"] : 0,
    cash: typeof raw["cash"] === "number" ? raw["cash"] : 0,
    shards: typeof raw["shards"] === "number" ? raw["shards"] : 0,
    hiddenTrickCount: typeof raw["hidden_trick_count"] === "number" ? raw["hidden_trick_count"] : 0,
    ownedTileCount: typeof raw["owned_tile_count"] === "number" ? raw["owned_tile_count"] : 0,
  };
}

function toTileViewModel(raw: unknown): TileViewModel | null {
  if (!isRecord(raw)) {
    return null;
  }
  const tileIndex = raw["tile_index"];
  if (typeof tileIndex !== "number") {
    return null;
  }
  return {
    tileIndex,
    tileKind: typeof raw["tile_kind"] === "string" ? raw["tile_kind"] : "?",
    zoneColor: typeof raw["zone_color"] === "string" ? raw["zone_color"] : "",
    purchaseCost: typeof raw["purchase_cost"] === "number" ? raw["purchase_cost"] : null,
    rentCost: typeof raw["rent_cost"] === "number" ? raw["rent_cost"] : null,
    ownerPlayerId: typeof raw["owner_player_id"] === "number" ? raw["owner_player_id"] : null,
    pawnPlayerIds: Array.isArray(raw["pawn_player_ids"])
      ? raw["pawn_player_ids"].filter((v): v is number => typeof v === "number")
      : [],
  };
}

function snapshotFromMessage(message: InboundMessage): SnapshotViewModel | null {
  if (message.type !== "event") {
    return null;
  }

  const round = typeof message.payload["round_index"] === "number" ? message.payload["round_index"] : 0;
  const turn = typeof message.payload["turn_index"] === "number" ? message.payload["turn_index"] : 0;

  const explicitSnapshot = isRecord(message.payload["snapshot"]) ? message.payload["snapshot"] : null;
  const snapshotPlayers = explicitSnapshot?.["players"];
  const snapshotBoard = isRecord(explicitSnapshot?.["board"]) ? explicitSnapshot["board"] : null;

  const rootPlayers = message.payload["players"];
  const playersSource = Array.isArray(snapshotPlayers)
    ? snapshotPlayers
    : Array.isArray(rootPlayers)
      ? rootPlayers
      : null;
  if (!playersSource) {
    return null;
  }

  const boardTiles = snapshotBoard?.["tiles"];
  const tilesSource = Array.isArray(boardTiles) ? boardTiles : [];
  const players = playersSource.map(toPlayerViewModel).filter((item): item is PlayerViewModel => item !== null);
  const tiles = tilesSource.map(toTileViewModel).filter((item): item is TileViewModel => item !== null);

  const markerOwner = snapshotBoard?.["marker_owner_player_id"];
  const fValue = snapshotBoard?.["f_value"];
  return {
    round,
    turn,
    markerOwnerPlayerId: typeof markerOwner === "number" ? markerOwner : null,
    fValue: typeof fValue === "number" ? fValue : 0,
    players,
    tiles,
  };
}

export function selectLatestSnapshot(messages: InboundMessage[]): SnapshotViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const snapshot = snapshotFromMessage(messages[i]);
    if (snapshot) {
      return snapshot;
    }
  }
  return null;
}
