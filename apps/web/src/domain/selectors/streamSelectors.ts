import type { InboundMessage } from "../../core/contracts/stream";
import { eventLabelForCode, nonEventLabelForMessageType } from "../labels/eventLabelCatalog";
import { toneForEventCode } from "../labels/eventToneCatalog";
import { promptLabelForType } from "../labels/promptTypeCatalog";

export type TimelineItem = {
  seq: number;
  label: string;
  detail: string;
};

export type TheaterItem = {
  seq: number;
  label: string;
  detail: string;
  tone: "move" | "economy" | "system" | "critical";
  actor: string;
  eventCode: string;
};

export type AlertItem = {
  seq: number;
  severity: "warning" | "critical";
  title: string;
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

export type ParameterManifestViewModel = {
  manifestHash: string;
  manifestVersion: number;
  version: string;
  sourceFingerprints: Record<string, string>;
  boardTopology: string;
  boardTiles: TileViewModel[];
  seatAllowed: number[];
  labels: Record<string, unknown>;
  dice: {
    values?: number[];
    maxCardsPerTurn?: number;
    useOneCardPlusOneDie?: boolean;
  };
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function messageKindFromPayload(payload: Record<string, unknown>): string {
  const eventType = payload["event_type"];
  return typeof eventType === "string" && eventType.trim() ? eventType : "";
}

function actorFromPayload(payload: Record<string, unknown>): string {
  const actor = payload["actor"];
  if (typeof actor === "string" && actor.trim()) {
    return actor;
  }
  const acting = payload["acting_player_id"] ?? payload["player_id"];
  return typeof acting === "number" ? `P${acting}` : "-";
}

function actorFromMessage(message: InboundMessage): string {
  if (message.type === "event") {
    return actorFromPayload(message.payload);
  }
  const pid = message.payload["player_id"];
  if (typeof pid === "number") {
    return `P${pid}`;
  }
  return "-";
}

function pickMessageLabel(message: InboundMessage): string {
  if (message.type !== "event") {
    return nonEventLabelForMessageType(message.type);
  }
  const code = messageKindFromPayload(message.payload);
  if (!code) {
    return "알 수 없는 이벤트";
  }
  return eventLabelForCode(code);
}

function summarizePlayerMove(payload: Record<string, unknown>): string {
  const from = numberOrNull(payload["from_tile_index"] ?? payload["from_tile"] ?? payload["from_pos"]);
  const to = numberOrNull(payload["to_tile_index"] ?? payload["to_tile"] ?? payload["to_pos"]);
  const fromDisplay = from === null ? "?" : String(from + 1);
  const toDisplay = to === null ? "?" : String(to + 1);
  const path = Array.isArray(payload["path"]) ? payload["path"] : [];
  if (path.length > 0) {
    return `${fromDisplay} -> ${toDisplay} (이동 ${path.length}칸)`;
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
  const dice = Array.isArray(payload["dice_values"]) ? payload["dice_values"] : Array.isArray(payload["dice"]) ? payload["dice"] : [];
  const total = payload["total_move"] ?? payload["total"] ?? payload["move"] ?? "?";
  const cardText = cards.length > 0 ? `카드 ${cards.join("+")}` : "";
  const diceText = dice.length > 0 ? `주사위 ${dice.join("+")}` : "";
  if (cardText && diceText) {
    return `${cardText} + ${diceText} = ${total}`;
  }
  if (cardText) {
    return `${cardText} = ${total}`;
  }
  if (diceText) {
    return `${diceText} = ${total}`;
  }
  return String(total);
}

function pickMessageDetail(message: InboundMessage): string {
  if (message.type === "heartbeat") {
    const interval = message.payload["interval_ms"];
    const backpressure = message.payload["backpressure"];
    if (typeof interval === "number" && backpressure && typeof backpressure === "object") {
      const drop = (backpressure as Record<string, unknown>)["drop_count"];
      return `연결 점검 ${interval}ms / 누락 ${typeof drop === "number" ? drop : 0}`;
    }
    return `연결 점검 ${typeof interval === "number" ? `${interval}ms` : ""}`.trim();
  }
  if (message.type === "prompt") {
    const requestType = asString(message.payload["request_type"]);
    const pid = message.payload["player_id"];
    const actor = typeof pid === "number" ? `P${pid}` : "-";
    return `${actor} / ${promptLabelForType(requestType === "-" ? "" : requestType)}`;
  }
  if (message.type === "decision_ack") {
    const status = asString(message.payload["status"]);
    const reason = asString(message.payload["reason"]);
    return reason !== "-" ? `${status} (${reason})` : status;
  }
  if (message.type === "error") {
    const code = asString(message.payload["code"]);
    const text = asString(message.payload["message"]);
    return code !== "-" ? `${code}: ${text}` : text;
  }

  const payload = message.payload;
  const eventType = messageKindFromPayload(payload);
  if (eventType === "player_move") {
    return summarizePlayerMove(payload);
  }
  if (eventType === "dice_roll") {
    return summarizeDiceRoll(payload);
  }
  if (eventType === "tile_purchased") {
    const tile = numberOrNull(payload["tile_index"]);
    const cost = payload["cost"] ?? payload["purchase_cost"] ?? "?";
    return `${tile === null ? "?" : tile + 1}번 칸 구매 / 비용 ${cost}`;
  }
  if (eventType === "marker_transferred") {
    const from = payload["from_player_id"] ?? payload["from_owner"] ?? "?";
    const to = payload["to_player_id"] ?? payload["to_owner"] ?? "?";
    return `[징표]가 P${from}에서 P${to}로 이동`;
  }
  if (eventType === "weather_reveal") {
    return asString(payload["weather_name"] ?? payload["weather"] ?? payload["card"]);
  }
  if (eventType === "landing_resolved") {
    const raw = asString(payload["result_type"] ?? payload["result_code"] ?? payload["result"] ?? "도착 처리");
    if (raw === "PURCHASE_SKIP_POLICY") {
      return "구매 없이 턴 종료";
    }
    if (raw === "PURCHASE") {
      return "토지 구매";
    }
    if (raw === "RENT_PAID" || raw === "RENT") {
      return "통행료 지불";
    }
    if (raw === "MARK_RESOLVED") {
      return "지목 처리";
    }
    return raw;
  }
  if (eventType === "bankruptcy") {
    const pid = payload["player_id"] ?? payload["target_player_id"] ?? "?";
    return `P${pid} 파산`;
  }
  if (eventType === "game_end") {
    const winner = payload["winner_player_id"];
    if (typeof winner === "number") {
      return `승자 P${winner}`;
    }
    return asString(payload["summary"] ?? "게임 종료");
  }
  if (eventType === "lap_reward_chosen") {
    const amountRaw = payload["amount"];
    if (isRecord(amountRaw)) {
      const cash = typeof amountRaw["cash"] === "number" ? amountRaw["cash"] : 0;
      const shards = typeof amountRaw["shards"] === "number" ? amountRaw["shards"] : 0;
      const coins = typeof amountRaw["coins"] === "number" ? amountRaw["coins"] : 0;
      const parts: string[] = [];
      if (cash > 0) {
        parts.push(`현금 +${cash}`);
      }
      if (shards > 0) {
        parts.push(`조각 +${shards}`);
      }
      if (coins > 0) {
        parts.push(`승점 +${coins}`);
      }
      if (parts.length > 0) {
        return parts.join(" / ");
      }
    }
    const choice = asString(payload["choice"] ?? payload["reward"] ?? payload["summary"]);
    const amount = payload["amount"] ?? payload["cash_amount"] ?? payload["value"];
    if (typeof amount === "number") {
      return `${choice} (${amount})`;
    }
    return choice;
  }
  if (eventType === "parameter_manifest") {
    const manifest = manifestRecordFromPayload(payload);
    const hash = manifest ? manifest["manifest_hash"] : null;
    if (typeof hash === "string" && hash.length >= 8) {
      return `설정 동기화 ${hash.slice(0, 8)}`;
    }
    return "설정 정보 갱신";
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
      label: pickMessageLabel(message),
      detail: pickMessageDetail(message),
    }))
    .reverse();
}

function toneFromMessage(message: InboundMessage): TheaterItem["tone"] {
  if (message.type === "error") {
    return "critical";
  }
  if (message.type === "prompt" || message.type === "decision_ack") {
    return "system";
  }
  if (message.type !== "event") {
    return "system";
  }
  const eventCode = messageKindFromPayload(message.payload) || "event";
  return toneForEventCode(eventCode);
}

function theaterCode(message: InboundMessage): string {
  if (message.type === "event") {
    return messageKindFromPayload(message.payload) || "event";
  }
  return message.type;
}

export function selectTheaterFeed(messages: InboundMessage[], limit = 20): TheaterItem[] {
  const feed: TheaterItem[] = [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type === "heartbeat") {
      continue;
    }
    const eventCode = theaterCode(message);
    feed.push({
      seq: message.seq,
      label: pickMessageLabel(message),
      detail: pickMessageDetail(message),
      tone: toneFromMessage(message),
      actor: actorFromMessage(message),
      eventCode,
    });
    if (feed.length >= limit) {
      break;
    }
  }
  return feed;
}

function alertFromEvent(message: InboundMessage): AlertItem | null {
  if (message.type === "error") {
    const code = asString(message.payload["code"]);
    if (code === "RUNTIME_EXECUTION_FAILED" || code === "RUNTIME_STALLED_WARN") {
      return {
        seq: message.seq,
        severity: code === "RUNTIME_EXECUTION_FAILED" ? "critical" : "warning",
        title: code,
        detail: pickMessageDetail(message),
      };
    }
    return null;
  }
  if (message.type !== "event") {
    return null;
  }
  const eventCode = messageKindFromPayload(message.payload);
  if (eventCode !== "bankruptcy" && eventCode !== "game_end" && eventCode !== "decision_timeout_fallback") {
    return null;
  }
  const severity: AlertItem["severity"] = eventCode === "decision_timeout_fallback" ? "warning" : "critical";
  return {
    seq: message.seq,
    severity,
    title: eventLabelForCode(eventCode),
    detail: pickMessageDetail(message) || "-",
  };
}

export function selectCriticalAlerts(messages: InboundMessage[], limit = 4): AlertItem[] {
  const alerts: AlertItem[] = [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const alert = alertFromEvent(messages[i]);
    if (!alert) {
      continue;
    }
    alerts.push(alert);
    if (alerts.length >= limit) {
      break;
    }
  }
  return alerts;
}

export function selectSituation(messages: InboundMessage[]): SituationViewModel {
  const last = messages.length > 0 ? messages[messages.length - 1] : null;
  if (!last) {
    return { actor: "-", round: "-", turn: "-", eventType: "-", weather: "-" };
  }
  const actorNum = last.payload["acting_player_id"] ?? last.payload["player_id"];
  const actor = asString(last.payload["actor"]);
  return {
    actor: actor !== "-" ? actor : typeof actorNum === "number" ? `P${actorNum}` : "-",
    round: asNumberText(last.payload["round_index"]),
    turn: asNumberText(last.payload["turn_index"]),
    eventType: pickMessageLabel(last),
    weather: asString(last.payload["weather_name"] ?? last.payload["weather"] ?? last.payload["card"]),
  };
}

export function selectLastMove(messages: InboundMessage[]): LastMoveViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event" || messageKindFromPayload(message.payload) !== "player_move") {
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

function toTileViewModel(raw: unknown, fallbackTileIndex: number | null = null): TileViewModel | null {
  if (!isRecord(raw)) {
    return null;
  }
  const rawTileIndex = raw["tile_index"];
  const tileIndex = typeof rawTileIndex === "number" ? rawTileIndex : fallbackTileIndex;
  if (tileIndex === null) {
    return null;
  }
  return {
    tileIndex,
    tileKind: typeof raw["tile_kind"] === "string" ? raw["tile_kind"] : "UNKNOWN",
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
  const playersSource = Array.isArray(snapshotPlayers) ? snapshotPlayers : Array.isArray(rootPlayers) ? rootPlayers : null;
  if (!playersSource) {
    return null;
  }

  const boardTiles = snapshotBoard?.["tiles"];
  const tilesSource = Array.isArray(boardTiles) ? boardTiles : [];
  const players = playersSource.map(toPlayerViewModel).filter((item): item is PlayerViewModel => item !== null);
  const tiles = tilesSource.map((tile, index) => toTileViewModel(tile, index)).filter((item): item is TileViewModel => item !== null);

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

function manifestRecordFromPayload(payload: Record<string, unknown>): Record<string, unknown> | null {
  if (isRecord(payload["parameter_manifest"])) {
    return payload["parameter_manifest"];
  }
  if (messageKindFromPayload(payload) === "parameter_manifest" && typeof payload["manifest_hash"] === "string") {
    return payload;
  }
  return null;
}

function normalizeSeatAllowed(manifestRaw: Record<string, unknown>): number[] {
  const seatsRaw = isRecord(manifestRaw["seats"]) ? manifestRaw["seats"] : null;
  const allowedRaw = Array.isArray(seatsRaw?.["allowed"]) ? seatsRaw["allowed"] : [];
  const allowed = allowedRaw
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v >= 1)
    .map((v) => Math.trunc(v));
  if (allowed.length > 0) {
    return Array.from(new Set(allowed)).sort((a, b) => a - b);
  }
  const maxSeat = seatsRaw && typeof seatsRaw["max"] === "number" ? Math.trunc(seatsRaw["max"] as number) : 0;
  if (maxSeat >= 1) {
    return Array.from({ length: maxSeat }, (_, index) => index + 1);
  }
  return [];
}

function normalizeManifestTiles(manifestRaw: Record<string, unknown>): TileViewModel[] {
  const boardRaw = isRecord(manifestRaw["board"]) ? manifestRaw["board"] : null;
  const tilesRaw = Array.isArray(boardRaw?.["tiles"]) ? boardRaw["tiles"] : [];
  const seen = new Set<number>();
  const parsed: TileViewModel[] = [];
  for (let i = 0; i < tilesRaw.length; i += 1) {
    const tile = toTileViewModel(tilesRaw[i], i);
    if (!tile || seen.has(tile.tileIndex)) {
      continue;
    }
    seen.add(tile.tileIndex);
    parsed.push({ ...tile, ownerPlayerId: null, pawnPlayerIds: [] });
  }
  if (parsed.length > 0) {
    parsed.sort((a, b) => a.tileIndex - b.tileIndex);
    return parsed;
  }
  const tileCount = boardRaw && typeof boardRaw["tile_count"] === "number" ? Math.max(0, Math.trunc(boardRaw["tile_count"] as number)) : 0;
  if (tileCount === 0) {
    return [];
  }
  return Array.from({ length: tileCount }, (_, index) => ({
    tileIndex: index,
    tileKind: "UNKNOWN",
    zoneColor: "",
    purchaseCost: null,
    rentCost: null,
    ownerPlayerId: null,
    pawnPlayerIds: [],
  }));
}

function normalizeBoardTopology(manifestRaw: Record<string, unknown>): string {
  const boardRaw = isRecord(manifestRaw["board"]) ? manifestRaw["board"] : null;
  const topology = boardRaw?.["topology"];
  if (typeof topology === "string" && topology.trim()) {
    return topology;
  }
  return "ring";
}

function normalizeManifestLabels(manifestRaw: Record<string, unknown>): Record<string, unknown> {
  const labels = manifestRaw["labels"];
  if (!isRecord(labels)) {
    return {};
  }
  return { ...labels };
}

function normalizeFingerprints(manifestRaw: Record<string, unknown>): Record<string, string> {
  const raw = manifestRaw["source_fingerprints"];
  if (!isRecord(raw)) {
    return {};
  }
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value === "string" && value.trim()) {
      out[key] = value;
    }
  }
  return out;
}

function normalizeDice(manifestRaw: Record<string, unknown>): ParameterManifestViewModel["dice"] {
  const raw = isRecord(manifestRaw["dice"]) ? manifestRaw["dice"] : null;
  if (!raw) {
    return {};
  }
  return {
    values: Array.isArray(raw["values"]) ? raw["values"].filter((v): v is number => typeof v === "number") : undefined,
    maxCardsPerTurn: typeof raw["max_cards_per_turn"] === "number" ? raw["max_cards_per_turn"] : undefined,
    useOneCardPlusOneDie: typeof raw["use_one_card_plus_one_die"] === "boolean" ? raw["use_one_card_plus_one_die"] : undefined,
  };
}

function manifestFromPayload(payload: Record<string, unknown>): ParameterManifestViewModel | null {
  const manifestRaw = manifestRecordFromPayload(payload);
  if (!manifestRaw) {
    return null;
  }
  const manifestHash = manifestRaw["manifest_hash"];
  if (typeof manifestHash !== "string" || !manifestHash.trim()) {
    return null;
  }
  return {
    manifestHash,
    manifestVersion: typeof manifestRaw["manifest_version"] === "number" ? manifestRaw["manifest_version"] : 1,
    version: typeof manifestRaw["version"] === "string" && manifestRaw["version"].trim() ? manifestRaw["version"] : "v1",
    sourceFingerprints: normalizeFingerprints(manifestRaw),
    boardTopology: normalizeBoardTopology(manifestRaw),
    boardTiles: normalizeManifestTiles(manifestRaw),
    seatAllowed: normalizeSeatAllowed(manifestRaw),
    labels: normalizeManifestLabels(manifestRaw),
    dice: normalizeDice(manifestRaw),
  };
}

export function selectLatestManifest(messages: InboundMessage[]): ParameterManifestViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event") {
      continue;
    }
    const manifest = manifestFromPayload(message.payload);
    if (manifest) {
      return manifest;
    }
  }
  return null;
}
