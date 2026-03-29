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

function asString(value: unknown): string {
  return typeof value === "string" ? value : "-";
}

function asNumberText(value: unknown): string {
  return typeof value === "number" ? String(value) : "-";
}

function pickEventLabel(message: InboundMessage): string {
  if (message.type !== "event") {
    return message.type;
  }
  const eventType = message.payload["event_type"];
  return typeof eventType === "string" && eventType.trim() ? eventType : "event";
}

function pickEventDetail(message: InboundMessage): string {
  if (message.type === "heartbeat") {
    const interval = message.payload["interval_ms"];
    return `heartbeat ${typeof interval === "number" ? `${interval}ms` : ""}`.trim();
  }
  if (message.type === "decision_ack") {
    return asString(message.payload["status"]);
  }
  if (message.type === "error") {
    return asString(message.payload["message"]);
  }
  const summary = message.payload["summary"];
  if (typeof summary === "string" && summary.trim()) {
    return summary;
  }
  return JSON.stringify(message.payload);
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
    weather: asString(last.payload["weather_name"]),
  };
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
  const snapshotBoard = isRecord(explicitSnapshot?.["board"]) ? explicitSnapshot?.["board"] : null;

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
