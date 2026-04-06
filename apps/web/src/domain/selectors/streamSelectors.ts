import type { InboundMessage } from "../../core/contracts/stream";
import {
  DEFAULT_EVENT_LABEL_TEXT,
  DEFAULT_PROMPT_TYPE_TEXT,
  DEFAULT_STREAM_TEXT,
  DEFAULT_TURN_STAGE_TEXT,
} from "../../i18n/defaultText";
import type { LocaleMessages } from "../../i18n/types";
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
  lane: "core" | "prompt" | "system";
  actor: string;
  eventCode: string;
};

export type CoreActionItem = {
  seq: number;
  actor: string;
  eventCode: string;
  round: number | null;
  turn: number | null;
  label: string;
  detail: string;
  isLocalActor: boolean;
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
  weatherEffect: string;
};

export type TurnStageViewModel = {
  turnStartSeq: number | null;
  actorPlayerId: number | null;
  actor: string;
  round: number | null;
  turn: number | null;
  character: string;
  weatherName: string;
  weatherEffect: string;
  currentBeatKind: "move" | "economy" | "effect" | "decision" | "system";
  focusTileIndex: number | null;
  diceSummary: string;
  moveSummary: string;
  trickSummary: string;
  landingSummary: string;
  purchaseSummary: string;
  rentSummary: string;
  turnEndSummary: string;
  fortuneDrawSummary: string;
  fortuneResolvedSummary: string;
  fortuneSummary: string;
  lapRewardSummary: string;
  markSummary: string;
  flipSummary: string;
  weatherSummary: string;
  effectSummary: string;
  promptSummary: string;
  latestActionLabel: string;
  latestActionDetail: string;
  currentBeatLabel: string;
  currentBeatDetail: string;
  externalAiWorkerId: string;
  externalAiFailureCode: string;
  externalAiFallbackMode: string;
  externalAiResolutionStatus: string;
  externalAiAttemptCount: number | null;
  externalAiAttemptLimit: number | null;
  externalAiReadyState: string;
  progressTrail: string[];
};

export type LastMoveViewModel = {
  playerId: number | null;
  fromTileIndex: number | null;
  toTileIndex: number | null;
  pathTileIndices: number[];
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

export type StreamSelectorTextResources = Pick<LocaleMessages, "eventLabel" | "promptType" | "stream" | "turnStage">;

const DEFAULT_STREAM_SELECTOR_TEXT: StreamSelectorTextResources = {
  eventLabel: DEFAULT_EVENT_LABEL_TEXT,
  promptType: DEFAULT_PROMPT_TYPE_TEXT,
  stream: DEFAULT_STREAM_TEXT,
  turnStage: DEFAULT_TURN_STAGE_TEXT,
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

function decisionProviderFromPayload(payload: Record<string, unknown>): string {
  const provider = payload["provider"];
  return typeof provider === "string" && provider.trim() ? provider : "";
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

function pickMessageLabel(message: InboundMessage, text: StreamSelectorTextResources): string {
  if (message.type !== "event") {
    return nonEventLabelForMessageType(message.type, text.eventLabel);
  }
  const code = messageKindFromPayload(message.payload);
  if (!code) {
    return text.stream.genericEvent;
  }
  return eventLabelForCode(code, text.eventLabel);
}

function weatherEffectFallbackText(weatherName: string, streamText: StreamSelectorTextResources["stream"]): string {
  const normalized = weatherName.trim();
  if (!normalized || normalized === "-") {
    return "-";
  }
  const mapped = streamText.weatherEffectFallback[normalized as keyof typeof streamText.weatherEffectFallback];
  if (typeof mapped === "string" && mapped.trim()) {
    return mapped;
  }
  return streamText.genericEffect(normalized);
}

function summarizePlayerMove(payload: Record<string, unknown>, streamText: StreamSelectorTextResources["stream"]): string {
  const from = numberOrNull(payload["from_tile_index"] ?? payload["from_tile"] ?? payload["from_pos"]);
  const to = numberOrNull(payload["to_tile_index"] ?? payload["to_tile"] ?? payload["to_pos"]);
  const fromDisplay = from === null ? "?" : String(from + 1);
  const toDisplay = to === null ? "?" : String(to + 1);
  const path = Array.isArray(payload["path"]) ? payload["path"] : [];
  return streamText.moveSummary(fromDisplay, toDisplay, path.length);
}

function summarizeDiceRoll(payload: Record<string, unknown>, streamText: StreamSelectorTextResources["stream"]): string {
  const cards = Array.isArray(payload["cards_used"])
    ? payload["cards_used"]
    : Array.isArray(payload["used_cards"])
      ? payload["used_cards"]
      : Array.isArray(payload["card_values"])
        ? payload["card_values"]
        : [];
  const dice = Array.isArray(payload["dice_values"]) ? payload["dice_values"] : Array.isArray(payload["dice"]) ? payload["dice"] : [];
  const total = payload["total_move"] ?? payload["total"] ?? payload["move"] ?? "?";
  const cardText = cards.length > 0 ? streamText.diceCard(cards.join("+")) : "";
  const diceText = dice.length > 0 ? streamText.diceRoll(dice.join("+")) : "";
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

function summarizeLandingResult(raw: string, streamText: StreamSelectorTextResources["stream"]): string {
  if (raw === "PURCHASE_SKIP_POLICY") {
    return streamText.landing.purchaseSkip;
  }
  if (raw === "PURCHASE") {
    return streamText.landing.purchase;
  }
  if (raw === "RENT_PAID" || raw === "RENT") {
    return streamText.landing.rent;
  }
  if (raw === "MARK_RESOLVED") {
    return streamText.landing.markResolved;
  }
  return raw;
}

function turnBeatKindFromEventCode(eventCode: string): TurnStageViewModel["currentBeatKind"] {
  if (eventCode === "dice_roll" || eventCode === "player_move") {
    return "move";
  }
  if (eventCode === "tile_purchased" || eventCode === "rent_paid" || eventCode === "lap_reward_chosen") {
    return "economy";
  }
  if (
    eventCode === "weather_reveal" ||
    eventCode === "fortune_drawn" ||
    eventCode === "fortune_resolved" ||
    eventCode === "trick_used" ||
    eventCode === "marker_flip" ||
    eventCode === "marker_transferred" ||
    eventCode === "landing_resolved"
  ) {
    return "effect";
  }
  if (
    eventCode === "draft_pick" ||
    eventCode === "final_character_choice" ||
    eventCode === "decision_requested" ||
    eventCode === "decision_resolved" ||
    eventCode === "decision_timeout_fallback"
  ) {
    return "decision";
  }
  return "system";
}

function focusTileIndexFromPayload(payload: Record<string, unknown>, eventCode: string): number | null {
  if (eventCode === "player_move") {
    return numberOrNull(payload["to_tile_index"] ?? payload["to_tile"] ?? payload["to_pos"]);
  }
  if (eventCode === "landing_resolved") {
    return numberOrNull(payload["position"] ?? payload["tile_index"] ?? payload["tile"]);
  }
  if (eventCode === "tile_purchased" || eventCode === "rent_paid") {
    return numberOrNull(payload["tile_index"] ?? payload["position"] ?? payload["tile"]);
  }
  if (eventCode === "fortune_drawn" || eventCode === "fortune_resolved") {
    return numberOrNull(
      payload["tile_index"] ?? payload["position"] ?? payload["end_pos"] ?? payload["target_pos"] ?? payload["tile"]
    );
  }
  if (eventCode === "trick_used") {
    return numberOrNull(payload["tile_index"] ?? payload["position"] ?? payload["target_pos"] ?? payload["tile"]);
  }
  return null;
}

function pickMessageDetail(message: InboundMessage, text: StreamSelectorTextResources): string {
  if (message.type === "heartbeat") {
    const interval = message.payload["interval_ms"];
    const backpressure = message.payload["backpressure"];
    if (typeof interval === "number" && backpressure && typeof backpressure === "object") {
      const drop = (backpressure as Record<string, unknown>)["drop_count"];
      return text.stream.heartbeat.detail(interval, typeof drop === "number" ? drop : 0);
    }
    return text.stream.heartbeat.interval(typeof interval === "number" ? `${interval}ms` : "-");
  }
  if (message.type === "prompt") {
    const requestType = asString(message.payload["request_type"]);
    const pid = message.payload["player_id"];
    const actor = typeof pid === "number" ? `P${pid}` : "-";
    return text.stream.promptDetail(actor, promptLabelForType(requestType === "-" ? "" : requestType, text.promptType));
  }
  if (message.type === "decision_ack") {
    const status = asString(message.payload["status"]);
    const reason = asString(message.payload["reason"]);
    return text.stream.decisionAckDetail(status, reason);
  }
  if (message.type === "error") {
    const code = asString(message.payload["code"]);
    const errorText = asString(message.payload["message"]);
    if (code === "RUNTIME_STALLED_WARN") {
      return text.stream.stalledWarning(errorText);
    }
    return text.stream.errorDetail(code, errorText);
  }

  const payload = message.payload;
  const eventType = messageKindFromPayload(payload);
  if (eventType === "turn_start") {
    return text.turnStage.turnStartDetail(actorFromPayload(payload));
  }
  if (eventType === "player_move") {
    return summarizePlayerMove(payload, text.stream);
  }
  if (eventType === "dice_roll") {
    return summarizeDiceRoll(payload, text.stream);
  }
  if (eventType === "tile_purchased") {
    const tile = numberOrNull(payload["tile_index"]);
    const cost = payload["cost"] ?? payload["purchase_cost"] ?? "?";
    return text.stream.actorDetail(
      actorFromPayload(payload),
      text.stream.tilePurchased(tile === null ? "?" : String(tile + 1), cost)
    );
  }
  if (eventType === "rent_paid") {
    const payer = payload["payer_player_id"] ?? payload["payer"] ?? "?";
    const owner = payload["owner_player_id"] ?? payload["owner"] ?? "?";
    const amount = payload["final_amount"] ?? payload["amount"] ?? payload["base_amount"] ?? "?";
    const tile = numberOrNull(payload["tile_index"]);
    return text.stream.rentPaid(payer, owner, amount, tile === null ? "?" : String(tile + 1));
  }
  if (eventType === "marker_transferred") {
    const from = payload["from_player_id"] ?? payload["from_owner"] ?? "?";
    const to = payload["to_player_id"] ?? payload["to_owner"] ?? "?";
    const flipped = payload["flip_player_id"];
    return text.stream.markerTransferred(from, to, flipped);
  }
  if (eventType === "weather_reveal") {
    const weather = asString(payload["weather_name"] ?? payload["weather"] ?? payload["card"]);
    const effects = Array.isArray(payload["effects"])
      ? payload["effects"].filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
    const effectsSummary = effects.length > 0 ? effects.join(", ") : "-";
    const explicitEffect = asString(payload["weather_effect"] ?? payload["effect_text"] ?? payload["effect"] ?? payload["description"]);
    const effect =
      explicitEffect !== "-"
        ? explicitEffect
        : effectsSummary !== "-" && effectsSummary !== weather
          ? effectsSummary
          : weatherEffectFallbackText(weather, text.stream);
    return text.stream.weatherDetail(weather, effect);
  }
  if (eventType === "decision_requested") {
    const requestType = asString(payload["request_type"]);
    const pid = payload["player_id"];
    const actor = typeof pid === "number" ? `P${pid}` : "-";
    return text.stream.decisionRequestedDetail(
      actor,
      promptLabelForType(requestType === "-" ? "" : requestType, text.promptType),
      promptTileDisplay(payload),
      legalChoiceCount(payload),
      workerSummaryFromPayload(payload, text)
    );
  }
  if (eventType === "decision_resolved") {
    const resolution = asString(payload["resolution"]);
    const choice = asString(payload["choice_id"]);
    return text.stream.decisionResolvedDetail(resolution, choice, workerSummaryFromPayload(payload, text));
  }
  if (eventType === "decision_timeout_fallback") {
    const summary = asString(payload["summary"]);
    const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
    return text.stream.decisionTimeoutFallbackDetail(
      summary,
      asString(publicContext?.["external_ai_worker_id"]),
      asString(publicContext?.["external_ai_failure_code"]),
      asString(publicContext?.["external_ai_fallback_mode"]),
      numberOrNull(publicContext?.["external_ai_attempt_count"]),
      numberOrNull(publicContext?.["external_ai_attempt_limit"])
    );
  }
  if (eventType === "landing_resolved") {
    const raw = asString(payload["result_type"] ?? payload["result_code"] ?? payload["result"] ?? text.stream.landing.default);
    const summary = summarizeLandingResult(raw, text.stream);
    const position = numberOrNull(payload["position"] ?? payload["tile_index"] ?? payload["tile"]);
    return position === null ? summary : text.stream.landingResultAt(summary, String(position + 1));
  }
  if (eventType === "bankruptcy") {
    const pid = payload["player_id"] ?? payload["target_player_id"] ?? "?";
    return text.stream.bankruptcy(pid);
  }
  if (eventType === "game_end") {
    const winner = payload["winner_player_id"];
    if (typeof winner === "number") {
      return text.stream.winner(winner);
    }
    return asString(payload["summary"] ?? text.stream.gameEndDefault);
  }
  if (eventType === "lap_reward_chosen") {
    const amountRaw = payload["amount"];
    if (isRecord(amountRaw)) {
      const cash = typeof amountRaw["cash"] === "number" ? amountRaw["cash"] : 0;
      const shards = typeof amountRaw["shards"] === "number" ? amountRaw["shards"] : 0;
      const coins = typeof amountRaw["coins"] === "number" ? amountRaw["coins"] : 0;
      const parts: string[] = [];
      if (cash > 0) {
        parts.push(text.stream.lapReward.cash(cash));
      }
      if (shards > 0) {
        parts.push(text.stream.lapReward.shards(shards));
      }
      if (coins > 0) {
        parts.push(text.stream.lapReward.coins(coins));
      }
      if (parts.length > 0) {
        return text.stream.lapRewardChosen(actorFromPayload(payload), parts.join(" / "));
      }
    }
    const choice = asString(payload["choice"] ?? payload["reward"] ?? payload["summary"]);
    const amount = payload["amount"] ?? payload["cash_amount"] ?? payload["value"];
    if (typeof amount === "number") {
      return text.stream.lapRewardChosen(actorFromPayload(payload), `${choice} (${amount})`);
    }
    return text.stream.lapRewardChosen(actorFromPayload(payload), choice);
  }
  if (eventType === "parameter_manifest") {
    const manifest = manifestRecordFromPayload(payload);
    const hash = manifest ? manifest["manifest_hash"] : null;
    if (typeof hash === "string" && hash.length >= 8) {
      return text.stream.manifestSyncHash(hash.slice(0, 8));
    }
    return text.stream.manifestSync;
  }
  if (eventType === "mark_resolved") {
    const source = payload["source_player_id"];
    const target = payload["target_player_id"];
    if (typeof source === "number" && typeof target === "number") {
      return text.stream.markResolved(source, target);
    }
    return text.stream.landing.markResolved;
  }
  if (eventType === "marker_flip") {
    const from = asString(payload["from_character"] ?? payload["from"]);
    const to = asString(payload["to_character"] ?? payload["to"]);
    if (from !== "-" && to !== "-") {
      return text.stream.markerFlipDetail(from, to);
    }
    return text.stream.markerFlip;
  }
  if (eventType === "f_value_change") {
    const before = payload["before"];
    const delta = payload["delta"];
    const after = payload["after"];
    if (typeof before === "number" && typeof delta === "number" && typeof after === "number") {
      return text.stream.fValueChange.detail(before, delta, after);
    }
    return text.stream.fValueChange.label;
  }
  if (eventType === "fortune_drawn") {
    const cardName = asString(payload["card_name"] ?? payload["card"] ?? payload["summary"]);
    return text.stream.actorDetail(actorFromPayload(payload), text.stream.fortuneDrawn(cardName));
  }
  if (eventType === "fortune_resolved") {
    const summary = asString(payload["summary"] ?? payload["resolution"] ?? payload["card_name"]);
    return text.stream.actorDetail(actorFromPayload(payload), text.stream.fortuneResolved(summary));
  }

  const summary = payload["summary"];
  if (typeof summary === "string" && summary.trim()) {
    return summary;
  }
  return "";
}

export function selectTimeline(
  messages: InboundMessage[],
  limit = 12,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): TimelineItem[] {
  return messages
    .slice(-limit)
    .map((message) => ({
      seq: message.seq,
      label: pickMessageLabel(message, text),
      detail: pickMessageDetail(message, text),
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

const CORE_EVENT_CODES = new Set<string>([
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
  "marker_transferred",
  "marker_flip",
  "lap_reward_chosen",
  "fortune_drawn",
  "fortune_resolved",
  "bankruptcy",
  "game_end",
  "turn_end_snapshot",
]);

const PROMPT_EVENT_CODES = new Set<string>(["decision_requested", "decision_resolved", "decision_timeout_fallback"]);

function laneFromMessage(message: InboundMessage): TheaterItem["lane"] {
  if (message.type === "decision_ack") {
    return "prompt";
  }
  if (message.type === "prompt") {
    return "system";
  }
  if (message.type !== "event") {
    return "system";
  }
  const eventCode = messageKindFromPayload(message.payload);
  if (PROMPT_EVENT_CODES.has(eventCode)) {
    if (decisionProviderFromPayload(message.payload) === "ai") {
      return "system";
    }
    return "prompt";
  }
  if (CORE_EVENT_CODES.has(eventCode)) {
    return "core";
  }
  return "system";
}

function theaterCode(message: InboundMessage): string {
  if (message.type === "event") {
    return messageKindFromPayload(message.payload) || "event";
  }
  return message.type;
}

export function selectTheaterFeed(
  messages: InboundMessage[],
  limit = 20,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): TheaterItem[] {
  const safeLimit = Math.max(1, limit);
  const coreCap = Math.max(1, Math.floor(safeLimit * 0.5));
  const promptCap = Math.max(1, Math.floor(safeLimit * 0.3));
  const systemCap = Math.max(1, safeLimit - coreCap - promptCap);
  const caps: Record<TheaterItem["lane"], number> = { core: coreCap, prompt: promptCap, system: systemCap };
  const laneCounts: Record<TheaterItem["lane"], number> = { core: 0, prompt: 0, system: 0 };
  const feed: TheaterItem[] = [];
  const pickedSeq = new Set<number>();

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type === "heartbeat") {
      continue;
    }
    const lane = laneFromMessage(message);
    if (laneCounts[lane] >= caps[lane]) {
      continue;
    }
    feed.push({
      seq: message.seq,
      label: pickMessageLabel(message, text),
      detail: pickMessageDetail(message, text),
      tone: toneFromMessage(message),
      lane,
      actor: actorFromMessage(message),
      eventCode: theaterCode(message),
    });
    pickedSeq.add(message.seq);
    laneCounts[lane] += 1;
    if (feed.length >= safeLimit) {
      break;
    }
  }

  if (feed.length < safeLimit) {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const message = messages[i];
      if (message.type === "heartbeat" || pickedSeq.has(message.seq)) {
        continue;
      }
      feed.push({
        seq: message.seq,
        label: pickMessageLabel(message, text),
        detail: pickMessageDetail(message, text),
        tone: toneFromMessage(message),
        lane: laneFromMessage(message),
        actor: actorFromMessage(message),
        eventCode: theaterCode(message),
      });
      pickedSeq.add(message.seq);
      if (feed.length >= safeLimit) {
        break;
      }
    }
  }
  return feed.sort((a, b) => b.seq - a.seq);
}

function alertFromEvent(message: InboundMessage, text: StreamSelectorTextResources): AlertItem | null {
  if (message.type === "error") {
    const code = asString(message.payload["code"]);
    if (code === "RUNTIME_EXECUTION_FAILED") {
      return {
        seq: message.seq,
        severity: "critical",
        title: text.stream.runtimeError,
        detail: pickMessageDetail(message, text),
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
    title: eventLabelForCode(eventCode, text.eventLabel),
    detail: pickMessageDetail(message, text) || "-",
  };
}

export function selectCriticalAlerts(
  messages: InboundMessage[],
  limit = 4,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): AlertItem[] {
  const alerts: AlertItem[] = [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const alert = alertFromEvent(messages[i], text);
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

function findLatestField(messages: InboundMessage[], keys: string[]): unknown {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = messages[i].payload;
    for (const key of keys) {
      if (payload[key] !== undefined && payload[key] !== null) {
        return payload[key];
      }
    }
  }
  return undefined;
}

function findPersistedWeather(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): { name: string; effect: string } {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event") {
      continue;
    }
    const payload = message.payload;
    const eventType = messageKindFromPayload(payload);
    if (eventType !== "weather_reveal" && eventType !== "turn_start" && eventType !== "round_start") {
      continue;
    }
    const weather = payload["weather_name"] ?? payload["weather"] ?? payload["card"];
    const effects = payload["effects"];
    const effectsSummary =
      Array.isArray(effects) && effects.length > 0 && typeof effects[0] === "string" && effects[0].trim()
        ? effects
            .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
            .join(", ")
        : "-";
    let weatherEffect =
      effectsSummary !== "-"
        ? effectsSummary
        : typeof payload["weather_effect"] === "string"
          ? payload["weather_effect"]
          : typeof payload["effect_text"] === "string"
            ? payload["effect_text"]
          : typeof payload["effect"] === "string"
            ? payload["effect"]
            : typeof payload["description"] === "string"
              ? payload["description"]
              : "-";
    if (typeof weather === "string" && weather.trim()) {
      if (weatherEffect === "-" || weatherEffect === weather) {
        weatherEffect = weatherEffectFallbackText(weather, text.stream);
      }
      return { name: weather, effect: weatherEffect };
    }
  }
  return { name: "-", effect: "-" };
}

function isCoreActionMessage(message: InboundMessage): boolean {
  if (message.type !== "event") {
    return false;
  }
  const eventCode = messageKindFromPayload(message.payload);
  return CORE_EVENT_CODES.has(eventCode);
}

export function selectCoreActionFeed(
  messages: InboundMessage[],
  focusPlayerId: number | null = null,
  limit = 10,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): CoreActionItem[] {
  const safeLimit = Math.max(1, limit);
  const rows: CoreActionItem[] = [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (!isCoreActionMessage(message)) {
      continue;
    }
    const actor = actorFromMessage(message);
    rows.push({
      seq: message.seq,
      actor,
      eventCode: messageKindFromPayload(message.payload),
      round: numberOrNull(message.payload["round_index"]),
      turn: numberOrNull(message.payload["turn_index"]),
      label: pickMessageLabel(message, text),
      detail: pickMessageDetail(message, text),
      isLocalActor: focusPlayerId !== null && actor === `P${focusPlayerId}`,
    });
    if (rows.length >= safeLimit) {
      break;
    }
  }
  return rows;
}

function isSituationNoise(message: InboundMessage): boolean {
  if (message.type === "heartbeat") {
    return true;
  }
  if (message.type === "prompt" || message.type === "decision_ack") {
    return true;
  }
  if (message.type === "error") {
    return true;
  }
  if (message.type === "event") {
    const eventCode = messageKindFromPayload(message.payload);
    if (PROMPT_EVENT_CODES.has(eventCode) || eventCode === "parameter_manifest") {
      return true;
    }
  }
  return false;
}

function latestSituationMessage(messages: InboundMessage[]): InboundMessage | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (!isSituationNoise(messages[i])) {
      return messages[i];
    }
  }
  return messages.length > 0 ? messages[messages.length - 1] : null;
}

export function selectSituation(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): SituationViewModel {
  const last = latestSituationMessage(messages);
  if (!last) {
    return { actor: "-", round: "-", turn: "-", eventType: "-", weather: "-", weatherEffect: "-" };
  }
  const actorNum = findLatestField(messages, ["acting_player_id", "player_id"]);
  const actorField = findLatestField(messages, ["actor"]);
  const actor =
    typeof actorField === "string" && actorField.trim()
      ? actorField
      : typeof actorNum === "number"
        ? `P${actorNum}`
        : "-";
  const round = asNumberText(findLatestField(messages, ["round_index"]));
  const turn = asNumberText(findLatestField(messages, ["turn_index"]));
  const weather = findPersistedWeather(messages, text);
  return {
    actor,
    round,
    turn,
    eventType: pickMessageLabel(last, text),
    weather: weather.name,
    weatherEffect: weather.effect,
  };
}

function roundTurnOfPayload(payload: Record<string, unknown>): { round: number | null; turn: number | null } {
  return {
    round: numberOrNull(payload["round_index"]),
    turn: numberOrNull(payload["turn_index"]),
  };
}

function sameRoundTurn(payload: Record<string, unknown>, targetRound: number | null, targetTurn: number | null): boolean {
  if (targetRound === null || targetTurn === null) {
    return false;
  }
  const current = roundTurnOfPayload(payload);
  return current.round === targetRound && current.turn === targetTurn;
}

function detailFromEventCode(
  payload: Record<string, unknown>,
  eventCode: string,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  const stub: InboundMessage = {
    type: "event",
    seq: 0,
    session_id: "",
    payload: {
      ...payload,
      event_type: eventCode,
    },
  };
  return pickMessageDetail(stub, text);
}

function externalAiPublicContext(payload: Record<string, unknown>): Record<string, unknown> | null {
  const publicContext = payload["public_context"];
  return isRecord(publicContext) ? publicContext : null;
}

function externalAiStatusFromPayload(payload: Record<string, unknown>): {
  workerId: string;
  failureCode: string;
  fallbackMode: string;
  resolutionStatus: string;
  attemptCount: number | null;
  attemptLimit: number | null;
  readyState: string;
} {
  const publicContext = externalAiPublicContext(payload);
  return {
    workerId: asString(publicContext?.["external_ai_worker_id"]),
    failureCode: asString(publicContext?.["external_ai_failure_code"]),
    fallbackMode: asString(publicContext?.["external_ai_fallback_mode"]),
    resolutionStatus: asString(publicContext?.["external_ai_resolution_status"]),
    attemptCount: numberOrNull(publicContext?.["external_ai_attempt_count"]),
    attemptLimit: numberOrNull(publicContext?.["external_ai_attempt_limit"]),
    readyState: asString(publicContext?.["external_ai_ready_state"]),
  };
}

function legalChoiceCount(payload: Record<string, unknown>): number | null {
  return Array.isArray(payload["legal_choices"]) ? payload["legal_choices"].length : null;
}

function promptTileDisplay(payload: Record<string, unknown>): string {
  const tileIndex = promptFocusTileIndex(payload);
  return tileIndex === null ? "-" : String(tileIndex + 1);
}

function workerSummaryFromPayload(payload: Record<string, unknown>, text: StreamSelectorTextResources): string {
  const status = externalAiStatusFromPayload(payload);
  return text.turnStage.workerStatusSummary(
    status.resolutionStatus,
    status.workerId,
    status.failureCode,
    status.fallbackMode,
    status.attemptCount,
    status.attemptLimit,
    status.readyState
  );
}

function promptFocusTileIndex(payload: Record<string, unknown>): number | null {
  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
  const contextTileIndex = numberOrNull(publicContext?.["tile_index"]);
  if (contextTileIndex !== null) {
    return contextTileIndex;
  }

  const legalChoices = Array.isArray(payload["legal_choices"]) ? payload["legal_choices"] : [];
  for (const choice of legalChoices) {
    if (!isRecord(choice)) {
      continue;
    }
    const value = isRecord(choice["value"]) ? choice["value"] : null;
    const choiceTileIndex = numberOrNull(value?.["tile_index"]);
    if (choiceTileIndex !== null) {
      return choiceTileIndex;
    }
  }

  return null;
}

export function selectTurnStage(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): TurnStageViewModel {
  const weather = findPersistedWeather(messages, text);
  const fallback: TurnStageViewModel = {
    turnStartSeq: null,
    actorPlayerId: null,
    actor: "-",
    round: null,
    turn: null,
    character: "-",
    weatherName: weather.name,
    weatherEffect: weather.effect,
    currentBeatKind: "system",
    focusTileIndex: null,
    diceSummary: "-",
    moveSummary: "-",
    trickSummary: "-",
    landingSummary: "-",
    purchaseSummary: "-",
    rentSummary: "-",
    turnEndSummary: "-",
    fortuneDrawSummary: "-",
    fortuneResolvedSummary: "-",
    fortuneSummary: "-",
    lapRewardSummary: "-",
    markSummary: "-",
    flipSummary: "-",
    weatherSummary: weather.name === "-" ? "-" : text.stream.weatherDetail(weather.name, weather.effect),
    effectSummary: "-",
    promptSummary: "-",
    latestActionLabel: "-",
    latestActionDetail: "-",
    currentBeatLabel: "-",
    currentBeatDetail: "-",
    externalAiWorkerId: "-",
    externalAiFailureCode: "-",
    externalAiFallbackMode: "-",
    externalAiResolutionStatus: "-",
    externalAiAttemptCount: null,
    externalAiAttemptLimit: null,
    externalAiReadyState: "-",
    progressTrail: [],
  };

  let turnStartIndex = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event") {
      continue;
    }
    if (messageKindFromPayload(message.payload) === "turn_start") {
      turnStartIndex = i;
      break;
    }
  }
  if (turnStartIndex < 0) {
    return fallback;
  }

  const startMessage = messages[turnStartIndex];
  if (startMessage.type !== "event") {
    return fallback;
  }
  const actorPlayerId = numberOrNull(startMessage.payload["acting_player_id"] ?? startMessage.payload["player_id"]);
  const roundTurn = roundTurnOfPayload(startMessage.payload);
  const model: TurnStageViewModel = {
    ...fallback,
    turnStartSeq: startMessage.seq,
    actorPlayerId,
    actor: actorPlayerId === null ? "-" : `P${actorPlayerId}`,
    round: roundTurn.round,
    turn: roundTurn.turn,
    character: asString(startMessage.payload["character"] ?? startMessage.payload["actor_name"]),
    currentBeatKind: "system",
    focusTileIndex: null,
    currentBeatLabel: eventLabelForCode("turn_start", text.eventLabel),
    currentBeatDetail: actorPlayerId === null ? "-" : text.turnStage.turnStartDetail(`P${actorPlayerId}`),
  };
  const trail: string[] = [eventLabelForCode("turn_start", text.eventLabel)];

  const updateBeat = (
    label: string,
    detail: string,
    kind: TurnStageViewModel["currentBeatKind"],
    focusTileIndex: number | null
  ) => {
    model.latestActionLabel = label;
    model.latestActionDetail = detail || "-";
    model.currentBeatKind = kind;
    if (focusTileIndex !== null) {
      model.focusTileIndex = focusTileIndex;
    }
    model.currentBeatLabel = label;
    model.currentBeatDetail = detail || "-";
    trail.push(label);
  };

  const updateExternalAiStatus = (payload: Record<string, unknown>) => {
    const status = externalAiStatusFromPayload(payload);
    if (status.workerId !== "-") {
      model.externalAiWorkerId = status.workerId;
    }
    if (status.failureCode !== "-") {
      model.externalAiFailureCode = status.failureCode;
    }
    if (status.fallbackMode !== "-") {
      model.externalAiFallbackMode = status.fallbackMode;
    }
    if (status.resolutionStatus !== "-") {
      model.externalAiResolutionStatus = status.resolutionStatus;
    }
    if (status.attemptCount !== null) {
      model.externalAiAttemptCount = status.attemptCount;
    }
    if (status.attemptLimit !== null) {
      model.externalAiAttemptLimit = status.attemptLimit;
    }
    if (status.readyState !== "-") {
      model.externalAiReadyState = status.readyState;
    }
  };

  for (let i = turnStartIndex + 1; i < messages.length; i += 1) {
    const message = messages[i];
    if (message.type === "prompt") {
      const requestType = asString(message.payload["request_type"]);
      const promptActor = numberOrNull(message.payload["player_id"]);
      if (requestType !== "-" && (model.actorPlayerId === null || model.actorPlayerId === promptActor)) {
        model.promptSummary = text.stream.promptWaiting(promptLabelForType(requestType, text.promptType));
        model.currentBeatKind = "decision";
        model.currentBeatLabel = promptLabelForType(requestType, text.promptType);
        model.currentBeatDetail = model.promptSummary;
        const promptTileIndex = promptFocusTileIndex(message.payload);
        if (promptTileIndex !== null) {
          model.focusTileIndex = promptTileIndex;
        }
      }
      continue;
    }
    if (message.type !== "event") {
      continue;
    }
    if (!sameRoundTurn(message.payload, model.round, model.turn)) {
      continue;
    }
    const eventCode = messageKindFromPayload(message.payload);
    if (eventCode === "turn_start") {
      continue;
    }
    if (CORE_EVENT_CODES.has(eventCode) && eventCode !== "turn_end_snapshot") {
      updateBeat(
        pickMessageLabel(message, text),
        detailFromEventCode(message.payload, eventCode, text) || "-",
        turnBeatKindFromEventCode(eventCode),
        focusTileIndexFromPayload(message.payload, eventCode)
      );
    }
    if (eventCode === "trick_used") {
      model.trickSummary = detailFromEventCode(message.payload, eventCode, text);
      model.effectSummary = model.trickSummary;
      continue;
    }
    if (eventCode === "dice_roll") {
      model.diceSummary = detailFromEventCode(message.payload, eventCode, text);
      continue;
    }
    if (eventCode === "player_move") {
      model.moveSummary = detailFromEventCode(message.payload, eventCode, text);
      continue;
    }
    if (eventCode === "landing_resolved") {
      model.landingSummary = detailFromEventCode(message.payload, eventCode, text);
      continue;
    }
    if (eventCode === "decision_requested") {
      updateExternalAiStatus(message.payload);
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.promptSummary = detail;
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "decision",
        promptFocusTileIndex({ public_context: message.payload["public_context"], legal_choices: message.payload["legal_choices"] })
      );
      continue;
    }
    if (eventCode === "decision_resolved") {
      updateExternalAiStatus(message.payload);
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.promptSummary = detail;
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "decision",
        promptFocusTileIndex({ public_context: message.payload["public_context"], legal_choices: message.payload["legal_choices"] })
      );
      continue;
    }
    if (eventCode === "decision_timeout_fallback") {
      updateExternalAiStatus(message.payload);
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.promptSummary = detail;
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "system",
        promptFocusTileIndex({ public_context: message.payload["public_context"], legal_choices: message.payload["legal_choices"] })
      );
      continue;
    }
    if (eventCode === "tile_purchased") {
      model.purchaseSummary = detailFromEventCode(message.payload, eventCode, text);
      continue;
    }
    if (eventCode === "rent_paid") {
      model.rentSummary = detailFromEventCode(message.payload, eventCode, text);
      continue;
    }
    if (eventCode === "turn_end_snapshot") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.turnEndSummary = detail;
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "system",
        focusTileIndexFromPayload(message.payload, eventCode)
      );
      continue;
    }
    if (eventCode === "weather_reveal") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.weatherSummary = detail;
      model.effectSummary = detail;
      continue;
    }
    if (eventCode === "fortune_drawn") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.fortuneDrawSummary = detail;
      if (model.fortuneSummary === "-") {
        model.fortuneSummary = detail;
      }
      model.effectSummary = detail;
      continue;
    }
    if (eventCode === "fortune_resolved") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.fortuneResolvedSummary = detail;
      model.fortuneSummary = detail;
      model.effectSummary = detail;
      continue;
    }
    if (eventCode === "lap_reward_chosen") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.lapRewardSummary = detail;
      model.effectSummary = detail;
      continue;
    }
    if (eventCode === "mark_resolved") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.markSummary = detail;
      model.effectSummary = detail;
      continue;
    }
    if (eventCode === "marker_flip") {
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.flipSummary = detail;
      model.effectSummary = detail;
      continue;
    }
  }

  model.progressTrail = trail.slice(-6);

  return model;
}

export function selectLastMove(messages: InboundMessage[]): LastMoveViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event" || messageKindFromPayload(message.payload) !== "player_move") {
      continue;
    }
    const rawPath = Array.isArray(message.payload["path"]) ? message.payload["path"] : [];
    const pathTileIndices = rawPath.filter((value): value is number => typeof value === "number");
    return {
      playerId: numberOrNull(message.payload["acting_player_id"] ?? message.payload["player_id"]),
      fromTileIndex: numberOrNull(message.payload["from_tile_index"] ?? message.payload["from_tile"] ?? message.payload["from_pos"]),
      toTileIndex: numberOrNull(message.payload["to_tile_index"] ?? message.payload["to_tile"] ?? message.payload["to_pos"]),
      pathTileIndices,
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
    displayName: typeof raw["display_name"] === "string" ? raw["display_name"] : `Player ${playerId}`,
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
  const tileCount =
    boardRaw && typeof boardRaw["tile_count"] === "number" ? Math.max(0, Math.trunc(boardRaw["tile_count"] as number)) : 0;
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
