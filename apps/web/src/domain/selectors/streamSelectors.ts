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
import { charactersForPrioritySlot, oppositeCharacterForSlot, prioritySlotForCharacter } from "../characters/prioritySlots";
import { selectActivePrompt } from "./promptSelectors";

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
  focusTileIndices: number[];
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
  promptRequestType: string;
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
  externalAiPolicyMode: string;
  externalAiWorkerAdapter: string;
  externalAiPolicyClass: string;
  externalAiDecisionStyle: string;
  actorCash: number | null;
  actorShards: number | null;
  actorHandCoins: number | null;
  actorPlacedCoins: number | null;
  actorTotalScore: number | null;
  actorOwnedTileCount: number | null;
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
  handCoins: number;
  placedCoins: number;
  totalScore: number;
  hiddenTrickCount: number;
  ownedTileCount: number;
  publicTricks: string[];
  trickCount: number;
};

export type DerivedPlayerViewModel = PlayerViewModel & {
  prioritySlot: number | null;
  currentCharacterFace: string;
  isMarkerOwner: boolean;
  isCurrentActor: boolean;
  isLocalPlayer: boolean;
};

export type ActiveCharacterSlotViewModel = {
  slot: number;
  playerId: number | null;
  label: string | null;
  character: string | null;
  inactiveCharacter: string | null;
  isCurrentActor: boolean;
  isLocalPlayer: boolean;
};

export type MarkTargetSlotViewModel = {
  slot: number;
  playerId: number | null;
  label: string | null;
  character: string;
};

export type CurrentTurnRevealItem = {
  seq: number;
  eventCode: string;
  label: string;
  detail: string;
  tone: "move" | "effect" | "economy";
  focusTileIndex: number | null;
  isInterrupt: boolean;
};

export type TileViewModel = {
  tileIndex: number;
  tileKind: string;
  zoneColor: string;
  purchaseCost: number | null;
  rentCost: number | null;
  scoreCoinCount: number;
  ownerPlayerId: number | null;
  pawnPlayerIds: number[];
};

export type SnapshotViewModel = {
  round: number;
  turn: number;
  markerOwnerPlayerId: number | null;
  markerDraftDirection: "clockwise" | "counterclockwise" | null;
  fValue: number;
  currentRoundOrder: number[];
  activeByCard: Record<number, string>;
  players: PlayerViewModel[];
  tiles: TileViewModel[];
};

type BackendDerivedPlayerItem = {
  player_id: number;
  display_name: string;
  cash: number;
  shards: number;
  owned_tile_count: number;
  trick_count: number;
  hand_coins: number;
  placed_coins: number;
  total_score: number;
  priority_slot: number | null;
  current_character_face: string;
  is_marker_owner: boolean;
  is_current_actor: boolean;
};

type BackendActiveSlotItem = {
  slot: number;
  player_id: number | null;
  label: string | null;
  character: string | null;
  inactive_character: string | null;
  is_current_actor: boolean;
};

type BackendMarkTargetCandidate = {
  slot: number;
  player_id: number | null;
  label: string | null;
  character: string;
};

type BackendSceneSituationProjection = {
  actorPlayerId: number | null;
  roundIndex: number | null;
  turnIndex: number | null;
  headlineSeq: number | null;
  headlineMessageType: string;
  headlineEventCode: string;
  weatherName: string;
  weatherEffect: string;
};

type BackendSceneTheaterItemProjection = {
  seq: number;
  messageType: string;
  eventCode: string;
  tone: TheaterItem["tone"];
  lane: TheaterItem["lane"];
  actorPlayerId: number | null;
  roundIndex: number | null;
  turnIndex: number | null;
};

type BackendSceneCoreActionItemProjection = {
  seq: number;
  eventCode: string;
  actorPlayerId: number | null;
  roundIndex: number | null;
  turnIndex: number | null;
};

type BackendSceneTimelineItemProjection = {
  seq: number;
  messageType: string;
  eventCode: string;
};

type BackendSceneCriticalAlertProjection = {
  seq: number;
  messageType: string;
  eventCode: string;
  severity: AlertItem["severity"];
};

type BackendSceneProjection = {
  situation: BackendSceneSituationProjection | null;
  theaterFeed: BackendSceneTheaterItemProjection[];
  coreActionFeed: BackendSceneCoreActionItemProjection[];
  timeline: BackendSceneTimelineItemProjection[];
  criticalAlerts: BackendSceneCriticalAlertProjection[];
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

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function integerArray(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is number => typeof item === "number" && Number.isFinite(item));
}

function scoreCoinCountFromRecord(raw: Record<string, unknown>): number {
  if (typeof raw["score_coin_count"] === "number") {
    return raw["score_coin_count"];
  }
  if (typeof raw["score_coins"] === "number") {
    return raw["score_coins"];
  }
  if (typeof raw["tile_score_coins"] === "number") {
    return raw["tile_score_coins"];
  }
  return 0;
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

function playerLabel(playerId: number, text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT): string {
  return text.stream.playerLabel(playerId);
}

function actorFromPayload(
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  const actor = payload["actor"];
  if (typeof actor === "string" && actor.trim()) {
    return actor;
  }
  const acting = payload["acting_player_id"] ?? payload["player_id"];
  return typeof acting === "number" ? playerLabel(acting, text) : "-";
}

function actorFromMessage(
  message: InboundMessage,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  if (message.type === "event") {
    return actorFromPayload(message.payload, text);
  }
  const pid = message.payload["player_id"];
  if (typeof pid === "number") {
    return playerLabel(pid, text);
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
  const totalDisplay = typeof total === "number" || typeof total === "string" ? total : "?";
  const cardText = cards.length > 0 ? streamText.diceCard(cards.join("+")) : "";
  const diceText = dice.length > 0 ? streamText.diceRoll(dice.join("+")) : "";
  return streamText.diceTotalSummary(cardText, diceText, totalDisplay);
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
    const actor = typeof pid === "number" ? playerLabel(pid, text) : "-";
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
      actorFromPayload(payload, text),
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
    const effectsSummary = text.stream.effectsList(effects);
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
    const actor = typeof pid === "number" ? playerLabel(pid, text) : "-";
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
      numberOrNull(publicContext?.["external_ai_attempt_limit"]),
      asString(publicContext?.["external_ai_policy_mode"]),
      asString(publicContext?.["external_ai_worker_adapter"]),
      asString(publicContext?.["external_ai_policy_class"]),
      asString(publicContext?.["external_ai_decision_style"])
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
        return text.stream.lapRewardChosen(actorFromPayload(payload, text), text.stream.lapRewardBundle(parts));
      }
    }
    const choice = asString(payload["choice"] ?? payload["reward"] ?? payload["summary"]);
    const amount = payload["amount"] ?? payload["cash_amount"] ?? payload["value"];
    if (typeof amount === "number") {
      return text.stream.lapRewardChosen(actorFromPayload(payload, text), `${choice} (${amount})`);
    }
    return text.stream.lapRewardChosen(actorFromPayload(payload, text), choice);
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
  if (eventType === "mark_queued") {
    return text.stream.markQueued(
      payload["source_player_id"] ?? payload["player_id"] ?? "?",
      payload["target_player_id"] ?? "?",
      asString(payload["target_character"]),
      asString(payload["effect_type"])
    );
  }
  if (eventType === "mark_target_none") {
    return text.stream.markTargetNone(
      payload["source_player_id"] ?? payload["player_id"] ?? "?",
      asString(payload["actor_name"])
    );
  }
  if (eventType === "mark_target_missing") {
    return text.stream.markTargetMissing(
      payload["source_player_id"] ?? payload["player_id"] ?? "?",
      asString(payload["target_character"])
    );
  }
  if (eventType === "mark_blocked") {
    return text.stream.markBlocked(
      payload["source_player_id"] ?? payload["player_id"] ?? "?",
      payload["target_player_id"] ?? "?",
      asString(payload["target_character"])
    );
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
    return text.stream.actorDetail(actorFromPayload(payload, text), text.stream.fortuneDrawn(cardName));
  }
  if (eventType === "fortune_resolved") {
    const summary = asString(payload["summary"] ?? payload["resolution"] ?? payload["card_name"]);
    return text.stream.actorDetail(actorFromPayload(payload, text), text.stream.fortuneResolved(summary));
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
  const backendScene = selectBackendScene(messages);
  if (backendScene) {
    const safeLimit = Math.max(1, limit);
    const messageBySeq = selectMessageBySeq(messages);
    return backendScene.timeline.slice(0, safeLimit).map((item) => {
      const sourceMessage = messageBySeq.get(item.seq);
      return {
        seq: item.seq,
        label: sourceMessage
          ? pickMessageLabel(sourceMessage, text)
          : item.messageType !== "event"
            ? nonEventLabelForMessageType(item.messageType as InboundMessage["type"], text.eventLabel)
            : eventLabelForCode(item.eventCode, text.eventLabel),
        detail: sourceMessage ? pickMessageDetail(sourceMessage, text) : "",
      };
    });
  }
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
  "mark_queued",
  "mark_target_none",
  "mark_target_missing",
  "mark_blocked",
  "bankruptcy",
  "game_end",
  "turn_end_snapshot",
]);

const CURRENT_TURN_REVEAL_EVENT_CODES = new Set<string>([
  "weather_reveal",
  "dice_roll",
  "player_move",
  "landing_resolved",
  "tile_purchased",
  "rent_paid",
  "fortune_drawn",
  "fortune_resolved",
]);

const CURRENT_TURN_REVEAL_ORDER: Record<string, number> = {
  weather_reveal: 10,
  dice_roll: 20,
  player_move: 30,
  landing_resolved: 40,
  rent_paid: 50,
  tile_purchased: 50,
  fortune_drawn: 60,
  fortune_resolved: 70,
};

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
  const backendScene = selectBackendScene(messages);
  if (backendScene) {
    const safeLimit = Math.max(1, limit);
    const messageBySeq = selectMessageBySeq(messages);
    return backendScene.theaterFeed.slice(0, safeLimit).map((item) => {
      const sourceMessage = messageBySeq.get(item.seq);
      return {
        seq: item.seq,
        label: sourceMessage
          ? pickMessageLabel(sourceMessage, text)
          : item.messageType !== "event"
            ? nonEventLabelForMessageType(item.messageType as InboundMessage["type"], text.eventLabel)
            : eventLabelForCode(item.eventCode, text.eventLabel),
        detail: sourceMessage ? pickMessageDetail(sourceMessage, text) : "",
        tone: item.tone,
        lane: item.lane,
        actor: item.actorPlayerId !== null ? playerLabel(item.actorPlayerId, text) : "-",
        eventCode: item.eventCode,
      };
    });
  }
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
      actor: actorFromMessage(message, text),
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
        actor: actorFromMessage(message, text),
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
  const backendScene = selectBackendScene(messages);
  if (backendScene) {
    const safeLimit = Math.max(1, limit);
    const messageBySeq = selectMessageBySeq(messages);
    return backendScene.criticalAlerts.slice(0, safeLimit).map((item) => {
      const sourceMessage = messageBySeq.get(item.seq);
      return {
        seq: item.seq,
        severity: item.severity,
        title: sourceMessage
          ? pickMessageLabel(sourceMessage, text)
          : item.messageType !== "event"
            ? nonEventLabelForMessageType(item.messageType as InboundMessage["type"], text.eventLabel)
            : eventLabelForCode(item.eventCode, text.eventLabel),
        detail: sourceMessage ? pickMessageDetail(sourceMessage, text) || "-" : "-",
      };
    });
  }
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
    const effectsSummary = Array.isArray(effects)
      ? text.stream.effectsList(effects.filter((item): item is string => typeof item === "string" && item.trim().length > 0))
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
  return CORE_EVENT_CODES.has(eventCode) || eventCode === "decision_timeout_fallback";
}

export function selectCoreActionFeed(
  messages: InboundMessage[],
  focusPlayerId: number | null = null,
  limit = 10,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): CoreActionItem[] {
  const backendScene = selectBackendScene(messages);
  if (backendScene) {
    const safeLimit = Math.max(1, limit);
    const messageBySeq = selectMessageBySeq(messages);
    return backendScene.coreActionFeed.slice(0, safeLimit).map((item) => {
      const sourceMessage = messageBySeq.get(item.seq);
      return {
        seq: item.seq,
        actor: item.actorPlayerId !== null ? playerLabel(item.actorPlayerId, text) : "-",
        eventCode: item.eventCode,
        round: item.roundIndex,
        turn: item.turnIndex,
        label: sourceMessage ? pickMessageLabel(sourceMessage, text) : eventLabelForCode(item.eventCode, text.eventLabel),
        detail: sourceMessage ? pickMessageDetail(sourceMessage, text) : "",
        isLocalActor: focusPlayerId !== null && item.actorPlayerId === focusPlayerId,
      };
    });
  }
  const safeLimit = Math.max(1, limit);
  const rows: CoreActionItem[] = [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (!isCoreActionMessage(message)) {
      continue;
    }
    const actor = actorFromMessage(message, text);
    rows.push({
      seq: message.seq,
      actor,
      eventCode: messageKindFromPayload(message.payload),
      round: numberOrNull(message.payload["round_index"]),
      turn: numberOrNull(message.payload["turn_index"]),
      label: pickMessageLabel(message, text),
      detail: pickMessageDetail(message, text),
      isLocalActor: focusPlayerId !== null && actor === playerLabel(focusPlayerId, text),
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
  const backendScene = selectBackendScene(messages);
  if (backendScene?.situation) {
    const messageBySeq = selectMessageBySeq(messages);
    const sourceMessage =
      backendScene.situation.headlineSeq !== null ? messageBySeq.get(backendScene.situation.headlineSeq) ?? null : null;
    const eventType = sourceMessage
      ? pickMessageLabel(sourceMessage, text)
      : backendScene.situation.headlineMessageType !== "event"
        ? nonEventLabelForMessageType(backendScene.situation.headlineMessageType as InboundMessage["type"], text.eventLabel)
        : eventLabelForCode(backendScene.situation.headlineEventCode, text.eventLabel);
    return {
      actor: backendScene.situation.actorPlayerId !== null ? playerLabel(backendScene.situation.actorPlayerId, text) : "-",
      round: backendScene.situation.roundIndex !== null ? String(backendScene.situation.roundIndex) : "-",
      turn: backendScene.situation.turnIndex !== null ? String(backendScene.situation.turnIndex) : "-",
      eventType,
      weather: backendScene.situation.weatherName,
      weatherEffect: backendScene.situation.weatherEffect,
    };
  }
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
        ? playerLabel(actorNum, text)
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
  policyMode: string;
  workerAdapter: string;
  policyClass: string;
  decisionStyle: string;
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
    policyMode: asString(publicContext?.["external_ai_policy_mode"]),
    workerAdapter: asString(publicContext?.["external_ai_worker_adapter"]),
    policyClass: asString(publicContext?.["external_ai_policy_class"]),
    decisionStyle: asString(publicContext?.["external_ai_decision_style"]),
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
    status.readyState,
    status.policyMode,
    status.workerAdapter,
    status.policyClass,
    status.decisionStyle
  );
}

function promptFocusTileIndex(payload: Record<string, unknown>): number | null {
  const tileIndices = promptFocusTileIndices(payload);
  return tileIndices[0] ?? null;
}

function promptFocusTileIndices(payload: Record<string, unknown>): number[] {
  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
  const contextTileIndex = numberOrNull(publicContext?.["tile_index"]);
  const landingTileIndex = numberOrNull(publicContext?.["landing_tile_index"]);
  const contextCandidateTiles = Array.isArray(publicContext?.["candidate_tiles"])
    ? publicContext["candidate_tiles"].map((item) => numberOrNull(item)).filter((item): item is number => item !== null)
    : [];
  if (landingTileIndex !== null) {
    const ordered = [landingTileIndex, contextTileIndex, ...contextCandidateTiles].filter(
      (item, index, items): item is number => item !== null && items.indexOf(item) === index
    );
    if (ordered.length > 0) {
      return ordered;
    }
  }
  if (contextTileIndex !== null && contextCandidateTiles.length > 0) {
    return [contextTileIndex, ...contextCandidateTiles.filter((item) => item !== contextTileIndex)];
  }
  if (contextTileIndex !== null) {
    return [contextTileIndex];
  }

  const legalChoices = Array.isArray(payload["legal_choices"]) ? payload["legal_choices"] : [];
  const fromChoices: number[] = [];
  for (const choice of legalChoices) {
    if (!isRecord(choice)) {
      continue;
    }
    const value = isRecord(choice["value"]) ? choice["value"] : null;
    const choiceTileIndex = numberOrNull(value?.["tile_index"]);
    if (choiceTileIndex !== null) {
      fromChoices.push(choiceTileIndex);
    }
  }

  if (fromChoices.length > 0) {
    return [...new Set(fromChoices)];
  }

  return contextCandidateTiles;
}

function updateActorStatusFromContext(model: TurnStageViewModel, payload: Record<string, unknown>) {
  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : payload;
  const cash = numberOrNull(publicContext["player_cash"]);
  const shards = numberOrNull(publicContext["player_shards"]);
  const handCoins = numberOrNull(publicContext["player_hand_coins"]);
  const placedCoins = numberOrNull(publicContext["player_placed_coins"]);
  const totalScore = numberOrNull(publicContext["player_total_score"]);
  const ownedTileCount = numberOrNull(publicContext["player_owned_tile_count"]);

  if (cash !== null) {
    model.actorCash = cash;
  }
  if (shards !== null) {
    model.actorShards = shards;
  }
  if (handCoins !== null) {
    model.actorHandCoins = handCoins;
  }
  if (placedCoins !== null) {
    model.actorPlacedCoins = placedCoins;
  }
  if (totalScore !== null) {
    model.actorTotalScore = totalScore;
  }
  if (ownedTileCount !== null) {
    model.actorOwnedTileCount = ownedTileCount;
  }
}

function isPreCharacterSelectionRequestType(requestType: string): boolean {
  return requestType === "draft_card" || requestType === "final_character" || requestType === "final_character_choice";
}

function updateActorFromPrompt(
  model: TurnStageViewModel,
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources
) {
  const promptActor = numberOrNull(payload["player_id"] ?? payload["acting_player_id"]);
  if (promptActor !== null) {
    model.actorPlayerId = promptActor;
    model.actor = playerLabel(promptActor, text);
  }

  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
  const round = numberOrNull(publicContext?.["round_index"] ?? payload["round_index"]);
  const turn = numberOrNull(publicContext?.["turn_index"] ?? payload["turn_index"]);
  if (round !== null) {
    model.round = round;
  }
  if (turn !== null) {
    model.turn = turn;
  }

  const requestType = asString(payload["request_type"]);
  if (isPreCharacterSelectionRequestType(requestType)) {
    model.character = "-";
    return;
  }

  const actorName = asString(publicContext?.["actor_name"] ?? payload["actor_name"] ?? payload["character"]);
  if (actorName !== "-") {
    model.character = actorName;
  }
}

export function selectTurnStage(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): TurnStageViewModel {
  const backendTurnStage = selectBackendTurnStage(messages);
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
    focusTileIndices: [],
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
    promptRequestType: "-",
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
    externalAiPolicyMode: "-",
    externalAiWorkerAdapter: "-",
    externalAiPolicyClass: "-",
    externalAiDecisionStyle: "-",
    actorCash: null,
    actorShards: null,
    actorHandCoins: null,
    actorPlacedCoins: null,
    actorTotalScore: null,
    actorOwnedTileCount: null,
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
    actor: actorPlayerId === null ? "-" : playerLabel(actorPlayerId, text),
    round: roundTurn.round,
    turn: roundTurn.turn,
    character: asString(startMessage.payload["character"] ?? startMessage.payload["actor_name"]),
    currentBeatKind: "system",
    focusTileIndex: null,
    currentBeatLabel: eventLabelForCode("turn_start", text.eventLabel),
    currentBeatDetail: actorPlayerId === null ? "-" : text.turnStage.turnStartDetail(playerLabel(actorPlayerId, text)),
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
      model.focusTileIndices = [focusTileIndex];
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
    if (status.policyMode !== "-") {
      model.externalAiPolicyMode = status.policyMode;
    }
    if (status.workerAdapter !== "-") {
      model.externalAiWorkerAdapter = status.workerAdapter;
    }
    if (status.policyClass !== "-") {
      model.externalAiPolicyClass = status.policyClass;
    }
    if (status.decisionStyle !== "-") {
      model.externalAiDecisionStyle = status.decisionStyle;
    }
  };

  for (let i = turnStartIndex + 1; i < messages.length; i += 1) {
    const message = messages[i];
    if (message.type === "prompt") {
      const requestType = asString(message.payload["request_type"]);
      const promptActor = numberOrNull(message.payload["player_id"]);
      if (
        requestType !== "-" &&
        (model.actorPlayerId === null ||
          model.actorPlayerId === promptActor ||
          isPreCharacterSelectionRequestType(requestType))
      ) {
        updateActorFromPrompt(model, message.payload, text);
        updateActorStatusFromContext(model, message.payload);
        model.promptSummary = text.stream.promptWaiting(promptLabelForType(requestType, text.promptType));
        model.promptRequestType = requestType;
        model.currentBeatKind = "decision";
        model.currentBeatLabel = promptLabelForType(requestType, text.promptType);
        model.currentBeatDetail = model.promptSummary;
        const promptTileIndex = promptFocusTileIndex(message.payload);
        const promptTileIndices = promptFocusTileIndices(message.payload);
        if (promptTileIndex !== null) {
          model.focusTileIndex = promptTileIndex;
        }
        if (promptTileIndices.length > 0) {
          model.focusTileIndices = promptTileIndices;
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
      updateActorFromPrompt(model, message.payload, text);
      updateExternalAiStatus(message.payload);
      updateActorStatusFromContext(model, message.payload);
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.promptSummary = detail;
      model.promptRequestType = asString(message.payload["request_type"]);
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "decision",
        promptFocusTileIndex({ public_context: message.payload["public_context"], legal_choices: message.payload["legal_choices"] })
      );
      const promptTileIndices = promptFocusTileIndices({
        public_context: message.payload["public_context"],
        legal_choices: message.payload["legal_choices"],
      });
      if (promptTileIndices.length > 0) {
        model.focusTileIndices = promptTileIndices;
      }
      continue;
    }
    if (eventCode === "decision_resolved") {
      updateActorFromPrompt(model, message.payload, text);
      updateExternalAiStatus(message.payload);
      updateActorStatusFromContext(model, message.payload);
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.promptSummary = detail;
      model.promptRequestType = asString(message.payload["request_type"]);
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "decision",
        promptFocusTileIndex({ public_context: message.payload["public_context"], legal_choices: message.payload["legal_choices"] })
      );
      const promptTileIndices = promptFocusTileIndices({
        public_context: message.payload["public_context"],
        legal_choices: message.payload["legal_choices"],
      });
      if (promptTileIndices.length > 0) {
        model.focusTileIndices = promptTileIndices;
      }
      continue;
    }
    if (eventCode === "decision_timeout_fallback") {
      updateActorFromPrompt(model, message.payload, text);
      updateExternalAiStatus(message.payload);
      updateActorStatusFromContext(model, message.payload);
      const detail = detailFromEventCode(message.payload, eventCode, text);
      model.promptSummary = detail;
      model.promptRequestType = asString(message.payload["request_type"]);
      updateBeat(
        pickMessageLabel(message, text),
        detail || "-",
        "system",
        promptFocusTileIndex({ public_context: message.payload["public_context"], legal_choices: message.payload["legal_choices"] })
      );
      const promptTileIndices = promptFocusTileIndices({
        public_context: message.payload["public_context"],
        legal_choices: message.payload["legal_choices"],
      });
      if (promptTileIndices.length > 0) {
        model.focusTileIndices = promptTileIndices;
      }
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
    if (
      eventCode === "mark_resolved" ||
      eventCode === "mark_queued" ||
      eventCode === "mark_target_none" ||
      eventCode === "mark_target_missing" ||
      eventCode === "mark_blocked"
    ) {
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

  if (backendTurnStage) {
    const messageBySeq = new Map<number, InboundMessage>();
    for (const message of messages) {
      messageBySeq.set(message.seq, message);
    }
    model.turnStartSeq = backendTurnStage.turnStartSeq;
    model.actorPlayerId = backendTurnStage.actorPlayerId;
    model.actor = backendTurnStage.actorPlayerId === null ? "-" : playerLabel(backendTurnStage.actorPlayerId, text);
    model.round = backendTurnStage.round;
    model.turn = backendTurnStage.turn;
    model.character = backendTurnStage.character;
    model.weatherName = backendTurnStage.weatherName;
    model.weatherEffect = backendTurnStage.weatherEffect;
    model.currentBeatKind = backendTurnStage.currentBeatKind;
    model.focusTileIndex = backendTurnStage.focusTileIndex;
    model.focusTileIndices = backendTurnStage.focusTileIndices;
    model.promptRequestType = backendTurnStage.promptRequestType;
    model.externalAiWorkerId = backendTurnStage.externalAiWorkerId;
    model.externalAiFailureCode = backendTurnStage.externalAiFailureCode;
    model.externalAiFallbackMode = backendTurnStage.externalAiFallbackMode;
    model.externalAiResolutionStatus = backendTurnStage.externalAiResolutionStatus;
    model.externalAiAttemptCount = backendTurnStage.externalAiAttemptCount;
    model.externalAiAttemptLimit = backendTurnStage.externalAiAttemptLimit;
    model.externalAiReadyState = backendTurnStage.externalAiReadyState;
    model.externalAiPolicyMode = backendTurnStage.externalAiPolicyMode;
    model.externalAiWorkerAdapter = backendTurnStage.externalAiWorkerAdapter;
    model.externalAiPolicyClass = backendTurnStage.externalAiPolicyClass;
    model.externalAiDecisionStyle = backendTurnStage.externalAiDecisionStyle;
    model.actorCash = backendTurnStage.actorCash;
    model.actorShards = backendTurnStage.actorShards;
    model.actorHandCoins = backendTurnStage.actorHandCoins;
    model.actorPlacedCoins = backendTurnStage.actorPlacedCoins;
    model.actorTotalScore = backendTurnStage.actorTotalScore;
    model.actorOwnedTileCount = backendTurnStage.actorOwnedTileCount;
    model.currentBeatLabel = labelForTurnStageCode(
      backendTurnStage.currentBeatEventCode,
      backendTurnStage.currentBeatRequestType,
      text
    );
    const beatSource =
      backendTurnStage.currentBeatSeq === null ? null : messageBySeq.get(backendTurnStage.currentBeatSeq) ?? null;
    model.currentBeatDetail =
      backendTurnStage.currentBeatEventCode === "prompt_active"
        ? text.stream.promptWaiting(promptLabelForType(backendTurnStage.currentBeatRequestType, text.promptType))
        : beatSource
          ? pickMessageDetail(beatSource, text) || "-"
          : model.currentBeatDetail;
    model.latestActionLabel = model.currentBeatLabel;
    model.latestActionDetail = model.currentBeatDetail;
    if (backendTurnStage.progressCodes.length > 0) {
      model.progressTrail = backendTurnStage.progressCodes
        .map((code) => labelForTurnStageCode(code, backendTurnStage.promptRequestType, text))
        .filter((label) => label !== "-")
        .slice(-6);
    }
  }

  return model;
}

export function selectCurrentTurnRevealItems(
  messages: InboundMessage[],
  limit = 6,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): CurrentTurnRevealItem[] {
  const safeLimit = Math.max(1, limit);
  const backendItems = selectBackendCurrentTurnRevealItems(messages);
  if (backendItems && backendItems.length > 0) {
    return backendItems.slice(-safeLimit);
  }
  let turnStartIndex = -1;
  let targetRound: number | null = null;
  let targetTurn: number | null = null;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event" || messageKindFromPayload(message.payload) !== "turn_start") {
      continue;
    }
    turnStartIndex = i;
    targetRound = numberOrNull(message.payload["round_index"]);
    targetTurn = numberOrNull(message.payload["turn_index"]);
    break;
  }

  if (turnStartIndex < 0) {
    return [];
  }

  const items: CurrentTurnRevealItem[] = [];
  for (let i = turnStartIndex + 1; i < messages.length; i += 1) {
    const message = messages[i];
    if (message.type !== "event") {
      continue;
    }
    if (!sameRoundTurn(message.payload, targetRound, targetTurn)) {
      continue;
    }
    const eventCode = messageKindFromPayload(message.payload);
    if (!CURRENT_TURN_REVEAL_EVENT_CODES.has(eventCode)) {
      continue;
    }
    items.push({
      seq: message.seq,
      eventCode,
      label: pickMessageLabel(message, text),
      detail: pickMessageDetail(message, text) || "-",
      tone:
        eventCode === "dice_roll" || eventCode === "player_move"
          ? "move"
          : eventCode === "tile_purchased" || eventCode === "rent_paid"
            ? "economy"
            : "effect",
      focusTileIndex: focusTileIndexFromPayload(message.payload, eventCode),
      isInterrupt: eventCode === "weather_reveal" || eventCode === "fortune_drawn" || eventCode === "fortune_resolved",
    });
  }

  items.sort((left, right) => {
    const leftOrder = CURRENT_TURN_REVEAL_ORDER[left.eventCode] ?? 999;
    const rightOrder = CURRENT_TURN_REVEAL_ORDER[right.eventCode] ?? 999;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.seq - right.seq;
  });

  return items.slice(-safeLimit);
}

export function selectLastMove(messages: InboundMessage[]): LastMoveViewModel | null {
  const backendMove = selectBackendLastMove(messages);
  if (backendMove) {
    return backendMove;
  }
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
  const publicTricks = stringArray(raw["public_tricks"]);
  const hiddenTrickCount = typeof raw["hidden_trick_count"] === "number" ? raw["hidden_trick_count"] : 0;
  return {
    playerId,
    displayName: typeof raw["display_name"] === "string" ? raw["display_name"] : `Player ${playerId}`,
    character: typeof raw["character"] === "string" ? raw["character"] : "-",
    alive: typeof raw["alive"] === "boolean" ? raw["alive"] : true,
    position: typeof raw["position"] === "number" ? raw["position"] : 0,
    cash: typeof raw["cash"] === "number" ? raw["cash"] : 0,
    shards: typeof raw["shards"] === "number" ? raw["shards"] : 0,
    handCoins:
      typeof raw["hand_coins"] === "number"
        ? raw["hand_coins"]
        : typeof raw["hand_score_coins"] === "number"
          ? raw["hand_score_coins"]
          : 0,
    placedCoins:
      typeof raw["placed_score_coins"] === "number"
        ? raw["placed_score_coins"]
        : typeof raw["score_coins_placed"] === "number"
          ? raw["score_coins_placed"]
          : 0,
    totalScore:
      typeof raw["score"] === "number"
        ? raw["score"]
        : typeof raw["total_score"] === "number"
          ? raw["total_score"]
          : (typeof raw["hand_coins"] === "number" ? raw["hand_coins"] : 0) +
            (typeof raw["placed_score_coins"] === "number"
              ? raw["placed_score_coins"]
              : typeof raw["score_coins_placed"] === "number"
                ? raw["score_coins_placed"]
                : 0),
    hiddenTrickCount,
    ownedTileCount: typeof raw["owned_tile_count"] === "number" ? raw["owned_tile_count"] : 0,
    publicTricks,
    trickCount:
      typeof raw["trick_count"] === "number"
        ? raw["trick_count"]
        : publicTricks.length + hiddenTrickCount,
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
    scoreCoinCount: scoreCoinCountFromRecord(raw),
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
  const markerDraftDirection =
    markerDraftDirectionFromRecord(snapshotBoard) ?? markerDraftDirectionFromRecord(message.payload);
  const fValue = snapshotBoard?.["f_value"];
  const currentRoundOrder = Array.from(
    new Set(
      integerArray(explicitSnapshot?.["current_round_order"] ?? message.payload["order"]).map((value) =>
        value >= 1 ? Math.trunc(value) : value
      )
    )
  ).filter((value) => value >= 1);
  const activeByCardRaw = isRecord(explicitSnapshot?.["active_by_card"])
    ? explicitSnapshot["active_by_card"]
    : isRecord(message.payload["active_by_card"])
      ? message.payload["active_by_card"]
      : null;
  const activeByCard: Record<number, string> = {};
  mergeActiveByCard(activeByCard, activeByCardRaw);
  return {
    round,
    turn,
    markerOwnerPlayerId: typeof markerOwner === "number" ? markerOwner : null,
    markerDraftDirection,
    fValue: typeof fValue === "number" ? fValue : 0,
    currentRoundOrder,
    activeByCard,
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

function findLatestSnapshotEntry(messages: InboundMessage[]): { index: number; snapshot: SnapshotViewModel } | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const snapshot = snapshotFromMessage(messages[i]);
    if (snapshot) {
      return { index: i, snapshot };
    }
  }
  return null;
}

function overlayLiveActorOnPlayers(players: PlayerViewModel[], stage: TurnStageViewModel): PlayerViewModel[] {
  if (stage.actorPlayerId === null) {
    return players;
  }
  return players.map((player) => {
    if (player.playerId !== stage.actorPlayerId) {
      return player;
    }
    return {
      ...player,
      character:
        stage.character !== "-" && stage.character.trim().length > 0
          ? stage.character
          : player.character,
      cash: stage.actorCash ?? player.cash,
      shards: stage.actorShards ?? player.shards,
      handCoins: stage.actorHandCoins ?? player.handCoins,
      placedCoins: stage.actorPlacedCoins ?? player.placedCoins,
      totalScore: stage.actorTotalScore ?? player.totalScore,
      ownedTileCount: stage.actorOwnedTileCount ?? player.ownedTileCount,
    };
  });
}

function mergeActiveByCard(target: Record<number, string>, raw: unknown): void {
  if (!isRecord(raw)) {
    return;
  }
  for (const [key, value] of Object.entries(raw)) {
    const cardNo = Number.parseInt(key, 10);
    if (!Number.isFinite(cardNo) || cardNo < 1) {
      continue;
    }
    if (typeof value === "string" && value.trim()) {
      target[cardNo] = value;
    }
  }
}

function markerDraftDirectionFromRecord(raw: unknown): "clockwise" | "counterclockwise" | null {
  if (!isRecord(raw)) {
    return null;
  }
  const value = raw["marker_draft_direction"] ?? raw["draft_direction"];
  return value === "clockwise" || value === "counterclockwise" ? value : null;
}

function mergePromptContextActiveByCard(target: Record<number, string>, publicContext: unknown): void {
  if (!isRecord(publicContext)) {
    return;
  }
  mergeActiveByCard(target, publicContext["active_by_card"]);

  const actorName = publicContext["actor_name"];
  if (typeof actorName === "string" && actorName.trim()) {
    const actorSlot = prioritySlotForCharacter(actorName);
    if (actorSlot !== null) {
      target[actorSlot] = actorName;
    }
  }

  const targetPairs = publicContext["target_pairs"];
  if (!Array.isArray(targetPairs)) {
    return;
  }
  for (const item of targetPairs) {
    if (!isRecord(item)) {
      continue;
    }
    const cardNo = numberOrNull(item["target_card_no"]);
    const targetCharacter = item["target_character"];
    if (cardNo === null || typeof targetCharacter !== "string" || !targetCharacter.trim()) {
      continue;
    }
    target[cardNo] = targetCharacter;
  }
}

function mergeMarkTargetPromptActiveByCard(target: Record<number, string>, payload: Record<string, unknown>): void {
  const requestType = asString(payload["request_type"]);
  if (requestType !== "mark_target") {
    return;
  }

  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
  const actorName = asString(publicContext?.["actor_name"] ?? payload["actor_name"] ?? payload["character"]);
  if (actorName !== "-") {
    const actorSlot = prioritySlotForCharacter(actorName);
    if (actorSlot !== null) {
      target[actorSlot] = actorName;
    }
  }

  const legalChoices = Array.isArray(payload["legal_choices"]) ? payload["legal_choices"] : [];
  for (const item of legalChoices) {
    if (!isRecord(item)) {
      continue;
    }
    const choiceId = asString(item["choice_id"]);
    if (choiceId === "none" || choiceId === "no") {
      continue;
    }
    const value = isRecord(item["value"]) ? item["value"] : null;
    const targetCharacter = asString(value?.["target_character"] ?? item["target_character"] ?? item["title"] ?? item["label"]);
    if (targetCharacter === "-") {
      continue;
    }
    const targetSlot = prioritySlotForCharacter(targetCharacter);
    if (targetSlot !== null) {
      target[targetSlot] = targetCharacter;
    }
  }
}

function mergeNormalizedPromptActiveByCard(messages: InboundMessage[], target: Record<number, string>): void {
  const activePrompt = selectActivePrompt(messages);
  if (!activePrompt) {
    return;
  }
  mergePromptContextActiveByCard(target, activePrompt.publicContext);
  if (activePrompt.requestType !== "mark_target") {
    return;
  }
  for (const choice of activePrompt.choices) {
    if (choice.choiceId === "none" || choice.choiceId === "no") {
      continue;
    }
    const targetCharacter = asString(choice.value?.["target_character"] ?? choice.title);
    if (targetCharacter === "-") {
      continue;
    }
    const targetSlot =
      numberOrNull(choice.value?.["target_card_no"]) ?? prioritySlotForCharacter(targetCharacter);
    if (targetSlot !== null) {
      target[targetSlot] = targetCharacter;
    }
  }
}

function clearActiveByCard(target: Record<number, string>): void {
  for (const key of Object.keys(target)) {
    delete target[Number(key)];
  }
}

function shouldResetActiveByCard(eventCode: string): boolean {
  return (
    eventCode === "round_start" ||
    eventCode === "round_order"
  );
}

function collectActiveByCardUntil(messages: InboundMessage[], endIndex: number): Record<number, string> {
  const activeByCard: Record<number, string> = {};
  for (let i = 0; i <= endIndex && i < messages.length; i += 1) {
    const message = messages[i];
    if (message.type === "prompt") {
      const publicContext = isRecord(message.payload["public_context"]) ? message.payload["public_context"] : null;
      mergePromptContextActiveByCard(activeByCard, publicContext);
      mergeMarkTargetPromptActiveByCard(activeByCard, message.payload);
      continue;
    }
    if (message.type !== "event") {
      continue;
    }
    const eventCode = messageKindFromPayload(message.payload);
    if (shouldResetActiveByCard(eventCode)) {
      clearActiveByCard(activeByCard);
    }
    mergeActiveByCard(activeByCard, message.payload["active_by_card"]);
    const snapshot = isRecord(message.payload["snapshot"]) ? message.payload["snapshot"] : null;
    mergeActiveByCard(activeByCard, snapshot?.["active_by_card"]);
    const publicContext = isRecord(message.payload["public_context"]) ? message.payload["public_context"] : null;
    mergeActiveByCard(activeByCard, publicContext?.["active_by_card"]);
    if (eventCode !== "marker_flip") {
      continue;
    }
    const cardNo = numberOrNull(message.payload["card_no"]);
    const toCharacter = message.payload["to_character"];
    if (cardNo !== null && typeof toCharacter === "string" && toCharacter.trim()) {
      activeByCard[cardNo] = toCharacter;
    }
  }
  mergeNormalizedPromptActiveByCard(messages.slice(0, Math.min(endIndex + 1, messages.length)), activeByCard);
  return activeByCard;
}

function resolvePublicPrioritySlots(
  players: PlayerViewModel[],
  currentActorPlayerId: number | null
): Map<number, number | null> {
  const slotOwners = new Map<number, number[]>();
  for (const player of players) {
    const slot = prioritySlotForCharacter(player.character);
    if (slot === null) {
      continue;
    }
    const owners = slotOwners.get(slot) ?? [];
    owners.push(player.playerId);
    slotOwners.set(slot, owners);
  }

  const resolved = new Map<number, number | null>();
  for (const player of players) {
    const slot = prioritySlotForCharacter(player.character);
    if (slot === null) {
      resolved.set(player.playerId, null);
      continue;
    }
    const owners = slotOwners.get(slot) ?? [];
    if (owners.length <= 1) {
      resolved.set(player.playerId, slot);
      continue;
    }
    resolved.set(player.playerId, currentActorPlayerId === player.playerId ? slot : null);
  }
  return resolved;
}

function selectBackendMarkerOrderedPlayerIds(messages: InboundMessage[]): number[] | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload?.["view_state"] : null;
    const players = isRecord(viewState?.["players"]) ? viewState?.["players"] : null;
    const ordered = Array.isArray(players?.["ordered_player_ids"]) ? players?.["ordered_player_ids"] : null;
    if (!ordered) {
      continue;
    }
    const orderedIds = ordered.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    if (orderedIds.length > 0) {
      return orderedIds;
    }
  }
  return null;
}

function selectLatestBackendViewState(messages: InboundMessage[]): Record<string, unknown> | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload["view_state"] : null;
    if (viewState) {
      return viewState;
    }
  }
  return null;
}

function isStateBearingMessage(message: InboundMessage): boolean {
  return message.type === "event" || message.type === "prompt" || message.type === "decision_ack";
}

function latestStateBearingMessageIndex(messages: InboundMessage[]): number | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (isStateBearingMessage(messages[i])) {
      return i;
    }
  }
  return null;
}

function selectLatestBackendViewStateEntry(messages: InboundMessage[]): { index: number; viewState: Record<string, unknown> } | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload["view_state"] : null;
    if (viewState) {
      return { index: i, viewState };
    }
  }
  return null;
}

function isBackendProjectionCurrent(messages: InboundMessage[], index: number): boolean {
  const latestStatefulIndex = latestStateBearingMessageIndex(messages);
  return latestStatefulIndex === null || index >= latestStatefulIndex;
}

function selectBackendDerivedPlayers(
  messages: InboundMessage[],
  currentLocalPlayerId: number | null
): DerivedPlayerViewModel[] | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry || !isBackendProjectionCurrent(messages, entry.index)) {
    return null;
  }
  const players = isRecord(entry.viewState["players"]) ? entry.viewState["players"] : null;
  const items = Array.isArray(players?.["items"]) ? players["items"] : null;
  if (!items || items.length === 0) {
    return null;
  }
  const mapped = items.map((item): DerivedPlayerViewModel | null => {
      if (!isRecord(item) || typeof item["player_id"] !== "number") {
        return null;
      }
      const playerId = item["player_id"];
      return {
        playerId,
        displayName: typeof item["display_name"] === "string" ? item["display_name"] : `Player ${playerId}`,
        character:
          typeof item["current_character_face"] === "string" && item["current_character_face"].trim()
            ? item["current_character_face"]
            : "-",
        alive: true,
        position: 0,
        cash: typeof item["cash"] === "number" ? item["cash"] : 0,
        shards: typeof item["shards"] === "number" ? item["shards"] : 0,
        handCoins: typeof item["hand_coins"] === "number" ? item["hand_coins"] : 0,
        placedCoins: typeof item["placed_coins"] === "number" ? item["placed_coins"] : 0,
        totalScore: typeof item["total_score"] === "number" ? item["total_score"] : 0,
        hiddenTrickCount: 0,
        ownedTileCount: typeof item["owned_tile_count"] === "number" ? item["owned_tile_count"] : 0,
        publicTricks: [] as string[],
        trickCount: typeof item["trick_count"] === "number" ? item["trick_count"] : 0,
        prioritySlot: typeof item["priority_slot"] === "number" ? item["priority_slot"] : null,
        currentCharacterFace:
          typeof item["current_character_face"] === "string" && item["current_character_face"].trim()
            ? item["current_character_face"]
            : "-",
        isMarkerOwner: item["is_marker_owner"] === true,
        isCurrentActor: item["is_current_actor"] === true,
        isLocalPlayer: currentLocalPlayerId === playerId,
      };
    })
  return mapped.filter((item): item is DerivedPlayerViewModel => item !== null);
}

function selectBackendActiveCharacterSlots(
  messages: InboundMessage[],
  currentLocalPlayerId: number | null
): ActiveCharacterSlotViewModel[] | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry || !isBackendProjectionCurrent(messages, entry.index)) {
    return null;
  }
  const activeSlots = isRecord(entry.viewState["active_slots"]) ? entry.viewState["active_slots"] : null;
  const items = Array.isArray(activeSlots?.["items"]) ? activeSlots["items"] : null;
  if (!items || items.length === 0) {
    return null;
  }
  const mapped = items
    .map((item) => {
      if (!isRecord(item) || typeof item["slot"] !== "number") {
        return null;
      }
      const playerId = typeof item["player_id"] === "number" ? item["player_id"] : null;
      return {
        slot: item["slot"],
        playerId,
        label: typeof item["label"] === "string" ? item["label"] : null,
        character: typeof item["character"] === "string" && item["character"].trim() ? item["character"] : null,
        inactiveCharacter:
          typeof item["inactive_character"] === "string" && item["inactive_character"].trim()
            ? item["inactive_character"]
            : null,
        isCurrentActor: item["is_current_actor"] === true,
        isLocalPlayer: playerId !== null && currentLocalPlayerId === playerId,
      };
    })
    .filter((item): item is ActiveCharacterSlotViewModel => item !== null);
  return mapped.some((item) => item.character) ? mapped : null;
}

function selectBackendMarkTargetCharacterSlots(messages: InboundMessage[]): MarkTargetSlotViewModel[] | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry || !isBackendProjectionCurrent(messages, entry.index)) {
    return null;
  }
  const markTarget = isRecord(entry.viewState["mark_target"]) ? entry.viewState["mark_target"] : null;
  const candidates = Array.isArray(markTarget?.["candidates"]) ? markTarget["candidates"] : null;
  if (!candidates) {
    return null;
  }
  const mapped = candidates
    .map((item) => {
      if (!isRecord(item) || typeof item["slot"] !== "number" || typeof item["character"] !== "string") {
        return null;
      }
      return {
        slot: item["slot"],
        playerId: typeof item["player_id"] === "number" ? item["player_id"] : null,
        label: typeof item["label"] === "string" ? item["label"] : null,
        character: item["character"],
      };
    })
    .filter((item): item is MarkTargetSlotViewModel => item !== null);
  return mapped.length > 0 ? mapped : null;
}

function selectMessageBySeq(messages: InboundMessage[]): Map<number, InboundMessage> {
  const map = new Map<number, InboundMessage>();
  for (const message of messages) {
    map.set(message.seq, message);
  }
  return map;
}

function selectBackendScene(messages: InboundMessage[]): BackendSceneProjection | null {
  const viewState = selectLatestBackendViewState(messages);
  const scene = isRecord(viewState?.["scene"]) ? viewState["scene"] : null;
  if (!scene) {
    return null;
  }
  const situation = isRecord(scene["situation"]) ? scene["situation"] : null;
  const theaterFeedRaw = Array.isArray(scene["theater_feed"]) ? scene["theater_feed"] : [];
  const coreActionFeedRaw = Array.isArray(scene["core_action_feed"]) ? scene["core_action_feed"] : [];
  const timelineRaw = Array.isArray(scene["timeline"]) ? scene["timeline"] : [];
  const criticalAlertsRaw = Array.isArray(scene["critical_alerts"]) ? scene["critical_alerts"] : [];
  return {
    situation: situation
      ? {
          actorPlayerId: typeof situation["actor_player_id"] === "number" ? situation["actor_player_id"] : null,
          roundIndex: typeof situation["round_index"] === "number" ? situation["round_index"] : null,
          turnIndex: typeof situation["turn_index"] === "number" ? situation["turn_index"] : null,
          headlineSeq: typeof situation["headline_seq"] === "number" ? situation["headline_seq"] : null,
          headlineMessageType:
            typeof situation["headline_message_type"] === "string" && situation["headline_message_type"].trim()
              ? situation["headline_message_type"]
              : "event",
          headlineEventCode:
            typeof situation["headline_event_code"] === "string" && situation["headline_event_code"].trim()
              ? situation["headline_event_code"]
              : "event",
          weatherName:
            typeof situation["weather_name"] === "string" && situation["weather_name"].trim() ? situation["weather_name"] : "-",
          weatherEffect:
            typeof situation["weather_effect"] === "string" && situation["weather_effect"].trim() ? situation["weather_effect"] : "-",
        }
      : null,
    theaterFeed: theaterFeedRaw
      .map((item) => {
        if (!isRecord(item) || typeof item["seq"] !== "number" || typeof item["event_code"] !== "string") {
          return null;
        }
        const tone = item["tone"];
        const lane = item["lane"];
        return {
          seq: item["seq"],
          messageType: typeof item["message_type"] === "string" && item["message_type"].trim() ? item["message_type"] : "event",
          eventCode: item["event_code"],
          tone: tone === "move" || tone === "economy" || tone === "system" || tone === "critical" ? tone : "system",
          lane: lane === "core" || lane === "prompt" || lane === "system" ? lane : "system",
          actorPlayerId: typeof item["actor_player_id"] === "number" ? item["actor_player_id"] : null,
          roundIndex: typeof item["round_index"] === "number" ? item["round_index"] : null,
          turnIndex: typeof item["turn_index"] === "number" ? item["turn_index"] : null,
        } satisfies BackendSceneTheaterItemProjection;
      })
      .filter((item): item is BackendSceneTheaterItemProjection => item !== null),
    coreActionFeed: coreActionFeedRaw
      .map((item) => {
        if (!isRecord(item) || typeof item["seq"] !== "number" || typeof item["event_code"] !== "string") {
          return null;
        }
        return {
          seq: item["seq"],
          eventCode: item["event_code"],
          actorPlayerId: typeof item["actor_player_id"] === "number" ? item["actor_player_id"] : null,
          roundIndex: typeof item["round_index"] === "number" ? item["round_index"] : null,
          turnIndex: typeof item["turn_index"] === "number" ? item["turn_index"] : null,
        } satisfies BackendSceneCoreActionItemProjection;
      })
      .filter((item): item is BackendSceneCoreActionItemProjection => item !== null),
    timeline: timelineRaw
      .map((item) => {
        if (!isRecord(item) || typeof item["seq"] !== "number") {
          return null;
        }
        return {
          seq: item["seq"],
          messageType: typeof item["message_type"] === "string" && item["message_type"].trim() ? item["message_type"] : "event",
          eventCode: typeof item["event_code"] === "string" && item["event_code"].trim() ? item["event_code"] : "event",
        } satisfies BackendSceneTimelineItemProjection;
      })
      .filter((item): item is BackendSceneTimelineItemProjection => item !== null),
    criticalAlerts: criticalAlertsRaw
      .map((item) => {
        if (!isRecord(item) || typeof item["seq"] !== "number") {
          return null;
        }
        const severity = item["severity"];
        return {
          seq: item["seq"],
          messageType: typeof item["message_type"] === "string" && item["message_type"].trim() ? item["message_type"] : "event",
          eventCode: typeof item["event_code"] === "string" && item["event_code"].trim() ? item["event_code"] : "event",
          severity: severity === "warning" || severity === "critical" ? severity : "critical",
        } satisfies BackendSceneCriticalAlertProjection;
      })
      .filter((item): item is BackendSceneCriticalAlertProjection => item !== null),
  };
}

function selectBackendCurrentTurnRevealItems(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): CurrentTurnRevealItem[] | null {
  const viewState = selectLatestBackendViewState(messages);
  const reveals = isRecord(viewState?.["reveals"]) ? viewState["reveals"] : null;
  const items = Array.isArray(reveals?.["items"]) ? reveals["items"] : null;
  if (!items || items.length === 0) {
    return null;
  }
  const messageBySeq = selectMessageBySeq(messages);
  return items
    .map((item) => {
      if (!isRecord(item) || typeof item["seq"] !== "number" || typeof item["event_code"] !== "string") {
        return null;
      }
      const eventCode = item["event_code"];
      const sourceMessage = messageBySeq.get(item["seq"]);
      return {
        seq: item["seq"],
        eventCode,
        label: sourceMessage ? pickMessageLabel(sourceMessage, text) : eventLabelForCode(eventCode, text.eventLabel),
        detail: sourceMessage ? pickMessageDetail(sourceMessage, text) || "-" : "-",
        tone:
          item["tone"] === "move" || item["tone"] === "economy" || item["tone"] === "effect"
            ? item["tone"]
            : toneForEventCode(eventCode) === "economy"
              ? "economy"
              : toneForEventCode(eventCode) === "move"
                ? "move"
                : "effect",
        focusTileIndex: typeof item["focus_tile_index"] === "number" ? item["focus_tile_index"] : null,
        isInterrupt: item["is_interrupt"] === true,
      } satisfies CurrentTurnRevealItem;
    })
    .filter((item): item is CurrentTurnRevealItem => item !== null);
}

function selectBackendLastMove(messages: InboundMessage[]): LastMoveViewModel | null {
  const viewState = selectLatestBackendViewState(messages);
  const board = isRecord(viewState?.["board"]) ? viewState["board"] : null;
  const lastMove = isRecord(board?.["last_move"]) ? board["last_move"] : null;
  if (!lastMove) {
    return null;
  }
  return {
    playerId: typeof lastMove["player_id"] === "number" ? lastMove["player_id"] : null,
    fromTileIndex: typeof lastMove["from_tile_index"] === "number" ? lastMove["from_tile_index"] : null,
    toTileIndex: typeof lastMove["to_tile_index"] === "number" ? lastMove["to_tile_index"] : null,
    pathTileIndices: integerArray(lastMove["path_tile_indices"]),
  };
}

function selectBackendBoardTiles(messages: InboundMessage[]): Pick<TileViewModel, "tileIndex" | "scoreCoinCount" | "ownerPlayerId" | "pawnPlayerIds">[] | null {
  const viewState = selectLatestBackendViewState(messages);
  const board = isRecord(viewState?.["board"]) ? viewState["board"] : null;
  const tiles = Array.isArray(board?.["tiles"]) ? board["tiles"] : null;
  if (!tiles || tiles.length === 0) {
    return null;
  }
  const mapped = tiles
    .map((item) => {
      if (!isRecord(item) || typeof item["tile_index"] !== "number") {
        return null;
      }
      return {
        tileIndex: item["tile_index"],
        scoreCoinCount: typeof item["score_coin_count"] === "number" ? item["score_coin_count"] : 0,
        ownerPlayerId: typeof item["owner_player_id"] === "number" ? item["owner_player_id"] : null,
        pawnPlayerIds: Array.isArray(item["pawn_player_ids"])
          ? item["pawn_player_ids"].filter((value): value is number => typeof value === "number")
          : [],
      };
    })
    .filter(
      (
        item
      ): item is Pick<TileViewModel, "tileIndex" | "scoreCoinCount" | "ownerPlayerId" | "pawnPlayerIds"> => item !== null
    );
  return mapped.length > 0 ? mapped : null;
}

type BackendTurnStageProjection = {
  turnStartSeq: number | null;
  actorPlayerId: number | null;
  round: number | null;
  turn: number | null;
  character: string;
  weatherName: string;
  weatherEffect: string;
  currentBeatKind: TurnStageViewModel["currentBeatKind"];
  currentBeatEventCode: string;
  currentBeatRequestType: string;
  currentBeatSeq: number | null;
  focusTileIndex: number | null;
  focusTileIndices: number[];
  promptRequestType: string;
  externalAiWorkerId: string;
  externalAiFailureCode: string;
  externalAiFallbackMode: string;
  externalAiResolutionStatus: string;
  externalAiAttemptCount: number | null;
  externalAiAttemptLimit: number | null;
  externalAiReadyState: string;
  externalAiPolicyMode: string;
  externalAiWorkerAdapter: string;
  externalAiPolicyClass: string;
  externalAiDecisionStyle: string;
  actorCash: number | null;
  actorShards: number | null;
  actorHandCoins: number | null;
  actorPlacedCoins: number | null;
  actorTotalScore: number | null;
  actorOwnedTileCount: number | null;
  progressCodes: string[];
};

function selectBackendTurnStage(messages: InboundMessage[]): BackendTurnStageProjection | null {
  const viewState = selectLatestBackendViewState(messages);
  const turnStage = isRecord(viewState?.["turn_stage"]) ? viewState["turn_stage"] : null;
  if (!turnStage) {
    return null;
  }
  const currentBeatKind = turnStage["current_beat_kind"];
  return {
    turnStartSeq: typeof turnStage["turn_start_seq"] === "number" ? turnStage["turn_start_seq"] : null,
    actorPlayerId: typeof turnStage["actor_player_id"] === "number" ? turnStage["actor_player_id"] : null,
    round: typeof turnStage["round_index"] === "number" ? turnStage["round_index"] : null,
    turn: typeof turnStage["turn_index"] === "number" ? turnStage["turn_index"] : null,
    character: typeof turnStage["character"] === "string" && turnStage["character"].trim() ? turnStage["character"] : "-",
    weatherName:
      typeof turnStage["weather_name"] === "string" && turnStage["weather_name"].trim() ? turnStage["weather_name"] : "-",
    weatherEffect:
      typeof turnStage["weather_effect"] === "string" && turnStage["weather_effect"].trim() ? turnStage["weather_effect"] : "-",
    currentBeatKind:
      currentBeatKind === "move" ||
      currentBeatKind === "economy" ||
      currentBeatKind === "effect" ||
      currentBeatKind === "decision" ||
      currentBeatKind === "system"
        ? currentBeatKind
        : "system",
    currentBeatEventCode:
      typeof turnStage["current_beat_event_code"] === "string" && turnStage["current_beat_event_code"].trim()
        ? turnStage["current_beat_event_code"]
        : "-",
    currentBeatRequestType:
      typeof turnStage["current_beat_request_type"] === "string" && turnStage["current_beat_request_type"].trim()
        ? turnStage["current_beat_request_type"]
        : "-",
    currentBeatSeq: typeof turnStage["current_beat_seq"] === "number" ? turnStage["current_beat_seq"] : null,
    focusTileIndex: typeof turnStage["focus_tile_index"] === "number" ? turnStage["focus_tile_index"] : null,
    focusTileIndices: integerArray(turnStage["focus_tile_indices"]),
    promptRequestType:
      typeof turnStage["prompt_request_type"] === "string" && turnStage["prompt_request_type"].trim()
        ? turnStage["prompt_request_type"]
        : "-",
    externalAiWorkerId:
      typeof turnStage["external_ai_worker_id"] === "string" && turnStage["external_ai_worker_id"].trim()
        ? turnStage["external_ai_worker_id"]
        : "-",
    externalAiFailureCode:
      typeof turnStage["external_ai_failure_code"] === "string" && turnStage["external_ai_failure_code"].trim()
        ? turnStage["external_ai_failure_code"]
        : "-",
    externalAiFallbackMode:
      typeof turnStage["external_ai_fallback_mode"] === "string" && turnStage["external_ai_fallback_mode"].trim()
        ? turnStage["external_ai_fallback_mode"]
        : "-",
    externalAiResolutionStatus:
      typeof turnStage["external_ai_resolution_status"] === "string" && turnStage["external_ai_resolution_status"].trim()
        ? turnStage["external_ai_resolution_status"]
        : "-",
    externalAiAttemptCount: typeof turnStage["external_ai_attempt_count"] === "number" ? turnStage["external_ai_attempt_count"] : null,
    externalAiAttemptLimit: typeof turnStage["external_ai_attempt_limit"] === "number" ? turnStage["external_ai_attempt_limit"] : null,
    externalAiReadyState:
      typeof turnStage["external_ai_ready_state"] === "string" && turnStage["external_ai_ready_state"].trim()
        ? turnStage["external_ai_ready_state"]
        : "-",
    externalAiPolicyMode:
      typeof turnStage["external_ai_policy_mode"] === "string" && turnStage["external_ai_policy_mode"].trim()
        ? turnStage["external_ai_policy_mode"]
        : "-",
    externalAiWorkerAdapter:
      typeof turnStage["external_ai_worker_adapter"] === "string" && turnStage["external_ai_worker_adapter"].trim()
        ? turnStage["external_ai_worker_adapter"]
        : "-",
    externalAiPolicyClass:
      typeof turnStage["external_ai_policy_class"] === "string" && turnStage["external_ai_policy_class"].trim()
        ? turnStage["external_ai_policy_class"]
        : "-",
    externalAiDecisionStyle:
      typeof turnStage["external_ai_decision_style"] === "string" && turnStage["external_ai_decision_style"].trim()
        ? turnStage["external_ai_decision_style"]
        : "-",
    actorCash: typeof turnStage["actor_cash"] === "number" ? turnStage["actor_cash"] : null,
    actorShards: typeof turnStage["actor_shards"] === "number" ? turnStage["actor_shards"] : null,
    actorHandCoins: typeof turnStage["actor_hand_coins"] === "number" ? turnStage["actor_hand_coins"] : null,
    actorPlacedCoins: typeof turnStage["actor_placed_coins"] === "number" ? turnStage["actor_placed_coins"] : null,
    actorTotalScore: typeof turnStage["actor_total_score"] === "number" ? turnStage["actor_total_score"] : null,
    actorOwnedTileCount:
      typeof turnStage["actor_owned_tile_count"] === "number" ? turnStage["actor_owned_tile_count"] : null,
    progressCodes: stringArray(turnStage["progress_codes"]),
  };
}

function labelForTurnStageCode(
  code: string,
  requestType: string,
  text: StreamSelectorTextResources
): string {
  if (code === "prompt_active") {
    return promptLabelForType(requestType, text.promptType);
  }
  return eventLabelForCode(code, text.eventLabel);
}

export function selectLivePlayers(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): PlayerViewModel[] {
  const snapshot = selectLatestSnapshot(messages);
  if (!snapshot) {
    return [];
  }
  const stage = selectTurnStage(messages, text);
  return overlayLiveActorOnPlayers(snapshot.players, stage);
}

export function selectCurrentActorPlayerId(messages: InboundMessage[]): number | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = messages[i].payload;
    const acting = payload["acting_player_id"] ?? payload["player_id"];
    if (typeof acting === "number") {
      return acting;
    }
  }
  return null;
}

export function selectDerivedPlayers(
  messages: InboundMessage[],
  currentLocalPlayerId: number | null = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): DerivedPlayerViewModel[] {
  const backendPlayers = selectBackendDerivedPlayers(messages, currentLocalPlayerId);
  if (backendPlayers && backendPlayers.length > 0) {
    return backendPlayers;
  }
  const snapshot = selectLiveSnapshot(messages, text);
  if (!snapshot) {
    return [];
  }
  const currentActorPlayerId = selectCurrentActorPlayerId(messages);
  return snapshot.players.map((player) => {
    const currentCharacterFace =
      currentActorPlayerId === player.playerId && player.character && player.character.trim() ? player.character : "-";
    const prioritySlot = currentCharacterFace !== "-" ? prioritySlotForCharacter(currentCharacterFace) : null;
    return {
      ...player,
      prioritySlot,
      currentCharacterFace,
      isMarkerOwner: snapshot.markerOwnerPlayerId === player.playerId,
      isCurrentActor: currentActorPlayerId === player.playerId,
      isLocalPlayer: currentLocalPlayerId === player.playerId,
    };
  });
}

export function selectActiveCharacterSlots(
  messages: InboundMessage[],
  currentLocalPlayerId: number | null = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): ActiveCharacterSlotViewModel[] {
  const backendSlots = selectBackendActiveCharacterSlots(messages, currentLocalPlayerId);
  if (backendSlots && backendSlots.length > 0) {
    return backendSlots;
  }
  const snapshot = selectLiveSnapshot(messages, text);
  if (!snapshot) {
    return [];
  }
  const derivedPlayers = selectDerivedPlayers(messages, currentLocalPlayerId, text);
  const actor = derivedPlayers.find((player) => player.isCurrentActor) ?? null;
  return Array.from({ length: 8 }, (_, index) => {
    const slot = index + 1;
    const owner = actor && actor.prioritySlot === slot ? actor : null;
    const slotCharacter =
      typeof snapshot.activeByCard[slot] === "string" &&
      snapshot.activeByCard[slot].trim().length > 0 &&
      snapshot.activeByCard[slot] !== "-"
        ? snapshot.activeByCard[slot]
        : null;
    const ownerCharacter =
      owner?.currentCharacterFace && owner.currentCharacterFace !== "-" ? owner.currentCharacterFace : null;
    const activeCharacter = slotCharacter ?? ownerCharacter ?? null;
    return {
      slot,
      playerId: owner?.playerId ?? null,
      label: owner ? `P${owner.playerId}` : null,
      character: activeCharacter,
      inactiveCharacter: activeCharacter ? oppositeCharacterForSlot(slot, activeCharacter) : null,
      isCurrentActor: owner?.isCurrentActor ?? false,
      isLocalPlayer: owner?.isLocalPlayer ?? false,
    };
  });
}

export function selectMarkTargetCharacterSlots(
  messages: InboundMessage[],
  actorCharacterName: string | null,
  currentLocalPlayerId: number | null = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): MarkTargetSlotViewModel[] {
  const backendCandidates = selectBackendMarkTargetCharacterSlots(messages);
  if (backendCandidates) {
    return backendCandidates;
  }
  const actorSlot = prioritySlotForCharacter(actorCharacterName);
  if (actorSlot === null) {
    return [];
  }
  return selectActiveCharacterSlots(messages, currentLocalPlayerId, text)
    .filter((slot) => slot.slot > actorSlot && typeof slot.character === "string" && slot.character.trim().length > 0)
    .map((slot) => ({
      slot: slot.slot,
      playerId: slot.playerId,
      label: slot.label,
      character: slot.character as string,
    }));
}

export function selectMarkerOrderedPlayers(
  messages: InboundMessage[],
  currentLocalPlayerId: number | null = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): DerivedPlayerViewModel[] {
  const derivedPlayers = selectDerivedPlayers(messages, currentLocalPlayerId, text);
  if (derivedPlayers.length === 0) {
    return derivedPlayers;
  }
  const backendOrderedIds = selectBackendMarkerOrderedPlayerIds(messages);
  if (backendOrderedIds && backendOrderedIds.length > 0) {
    const byId = new Map(derivedPlayers.map((player) => [player.playerId, player]));
    const orderedPlayers = backendOrderedIds
      .map((playerId) => byId.get(playerId) ?? null)
      .filter((player): player is DerivedPlayerViewModel => player !== null);
    if (orderedPlayers.length > 0) {
      return orderedPlayers;
    }
  }

  const snapshot = selectLiveSnapshot(messages, text);
  if (!snapshot) {
    return derivedPlayers;
  }

  const sortedIds = derivedPlayers
    .map((player) => player.playerId)
    .slice()
    .sort((left, right) => left - right);
  const ownerId = snapshot.markerOwnerPlayerId;
  const ownerIndex = ownerId === null ? -1 : sortedIds.indexOf(ownerId);
  if (ownerIndex < 0) {
    return derivedPlayers.slice().sort((left, right) => left.playerId - right.playerId);
  }

  const direction = snapshot.markerDraftDirection ?? "clockwise";
  const orderedIds: number[] = [];
  for (let step = 0; step < sortedIds.length; step += 1) {
    const index =
      direction === "clockwise"
        ? (ownerIndex + step) % sortedIds.length
        : (ownerIndex - step + sortedIds.length) % sortedIds.length;
    orderedIds.push(sortedIds[index]);
  }

  const byId = new Map(derivedPlayers.map((player) => [player.playerId, player]));
  return orderedIds
    .map((playerId) => byId.get(playerId) ?? null)
    .filter((player): player is DerivedPlayerViewModel => player !== null);
}

export function selectLiveSnapshot(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): SnapshotViewModel | null {
  const entry = findLatestSnapshotEntry(messages);
  if (!entry) {
    return null;
  }

  const players = selectLivePlayers(messages, text);
  const playerMap = new Map<number, PlayerViewModel>(
    players.map((player) => [player.playerId, { ...player }])
  );
  const tiles = entry.snapshot.tiles.map((tile) => ({ ...tile, pawnPlayerIds: [] as number[] }));

  let markerOwnerPlayerId = entry.snapshot.markerOwnerPlayerId;
  let markerDraftDirection = entry.snapshot.markerDraftDirection;
  let currentRoundOrder = [...entry.snapshot.currentRoundOrder];
  const activeByCard = collectActiveByCardUntil(messages, entry.index);
  for (let i = entry.index + 1; i < messages.length; i += 1) {
    const message = messages[i];
    if (message.type === "prompt") {
      const publicContext = isRecord(message.payload["public_context"]) ? message.payload["public_context"] : null;
      mergePromptContextActiveByCard(activeByCard, publicContext);
      mergeMarkTargetPromptActiveByCard(activeByCard, message.payload);
      continue;
    }
    if (message.type !== "event") {
      continue;
    }
    const eventCode = messageKindFromPayload(message.payload);
    if (shouldResetActiveByCard(eventCode)) {
      clearActiveByCard(activeByCard);
    }
    const eventActorId = numberOrNull(message.payload["acting_player_id"] ?? message.payload["player_id"]);
    const eventActor = eventActorId !== null ? playerMap.get(eventActorId) : null;
    const publicContext = isRecord(message.payload["public_context"]) ? message.payload["public_context"] : null;
    const contextMarkerDirection = markerDraftDirectionFromRecord(publicContext);
    if (contextMarkerDirection) {
      markerDraftDirection = contextMarkerDirection;
    }
    const contextPosition = numberOrNull(publicContext?.["player_position"]);
    if (eventActor && contextPosition !== null) {
      eventActor.position = contextPosition;
    }
    const contextTileIndex = numberOrNull(publicContext?.["tile_index"]);
    if (publicContext && contextTileIndex !== null) {
      const tile = tiles.find((item) => item.tileIndex === contextTileIndex);
      if (tile) {
        const contextScoreCoinCount = scoreCoinCountFromRecord(publicContext);
        if (contextScoreCoinCount > 0 || "tile_score_coins" in publicContext || "score_coin_count" in publicContext || "score_coins" in publicContext) {
          tile.scoreCoinCount = contextScoreCoinCount;
        }
      }
    }
    if (eventCode === "player_move" && eventActor) {
      const toTileIndex = numberOrNull(
        message.payload["to_tile_index"] ?? message.payload["to_tile"] ?? message.payload["to_pos"]
      );
      if (toTileIndex !== null) {
        eventActor.position = toTileIndex;
      }
    }
    if (eventCode === "tile_purchased") {
      const tileIndex = numberOrNull(message.payload["tile_index"] ?? message.payload["position"] ?? message.payload["tile"]);
      const ownerPlayerId = numberOrNull(
        message.payload["owner_player_id"] ?? message.payload["acting_player_id"] ?? message.payload["player_id"]
      );
      if (tileIndex !== null && ownerPlayerId !== null) {
        const tile = tiles.find((item) => item.tileIndex === tileIndex);
        if (tile) {
          tile.ownerPlayerId = ownerPlayerId;
          const payloadScoreCoinCount = scoreCoinCountFromRecord(message.payload);
          if (
            payloadScoreCoinCount > 0 ||
            "tile_score_coins" in message.payload ||
            "score_coin_count" in message.payload ||
            "score_coins" in message.payload
          ) {
            tile.scoreCoinCount = payloadScoreCoinCount;
          }
        }
      }
      continue;
    }
    if (eventCode === "marker_transferred") {
      const nextOwner = numberOrNull(message.payload["to_player_id"] ?? message.payload["to_owner"]);
      if (nextOwner !== null) {
        markerOwnerPlayerId = nextOwner;
      }
      const nextDirection = markerDraftDirectionFromRecord(message.payload) ?? markerDraftDirectionFromRecord(publicContext);
      if (nextDirection) {
        markerDraftDirection = nextDirection;
      }
    }
    mergeActiveByCard(activeByCard, message.payload["active_by_card"]);
    mergeActiveByCard(activeByCard, publicContext?.["active_by_card"]);
    if (eventCode === "round_order") {
      const nextOrder = integerArray(message.payload["order"])
        .map((value) => Math.trunc(value))
        .filter((value) => value >= 1);
      if (nextOrder.length > 0) {
        currentRoundOrder = Array.from(new Set(nextOrder));
      }
      const nextOwner = numberOrNull(message.payload["marker_owner_player_id"] ?? message.payload["marker_owner"] ?? publicContext?.["marker_owner_player_id"]);
      if (nextOwner !== null) {
        markerOwnerPlayerId = nextOwner;
      }
      const nextDirection = markerDraftDirectionFromRecord(message.payload) ?? markerDraftDirectionFromRecord(publicContext);
      if (nextDirection) {
        markerDraftDirection = nextDirection;
      }
      continue;
    }
    if (eventCode === "round_start") {
      const nextOwner = numberOrNull(message.payload["marker_owner_player_id"] ?? publicContext?.["marker_owner_player_id"]);
      if (nextOwner !== null) {
        markerOwnerPlayerId = nextOwner;
      }
      const nextDirection = markerDraftDirectionFromRecord(message.payload) ?? markerDraftDirectionFromRecord(publicContext);
      if (nextDirection) {
        markerDraftDirection = nextDirection;
      }
    }
    if (eventCode === "marker_flip") {
      const cardNo = numberOrNull(message.payload["card_no"]);
      const toCharacter = message.payload["to_character"];
      if (cardNo !== null && typeof toCharacter === "string" && toCharacter.trim()) {
        activeByCard[cardNo] = toCharacter;
      }
    }
  }
  mergeNormalizedPromptActiveByCard(messages, activeByCard);

  const backendBoardTiles = selectBackendBoardTiles(messages);

  for (const tile of tiles) {
    tile.pawnPlayerIds = [];
  }

  for (const player of playerMap.values()) {
    if (!player.alive) {
      continue;
    }
    const targetTile = tiles.find((tile) => tile.tileIndex === player.position);
    if (targetTile) {
      targetTile.pawnPlayerIds = [...targetTile.pawnPlayerIds, player.playerId];
    }
  }

  for (const tile of tiles) {
    tile.pawnPlayerIds.sort((a, b) => a - b);
  }

  if (backendBoardTiles && backendBoardTiles.length > 0) {
    const backendTileByIndex = new Map(backendBoardTiles.map((tile) => [tile.tileIndex, tile]));
    for (const tile of tiles) {
      const projected = backendTileByIndex.get(tile.tileIndex);
      if (!projected) {
        continue;
      }
      tile.scoreCoinCount = projected.scoreCoinCount;
      tile.ownerPlayerId = projected.ownerPlayerId;
      tile.pawnPlayerIds = [...projected.pawnPlayerIds];
    }
  }

  const normalizedPlayers = players.map((player) => ({
    ...(playerMap.get(player.playerId) ?? player),
  }));

  return {
    ...entry.snapshot,
    markerOwnerPlayerId,
    markerDraftDirection,
    currentRoundOrder,
    activeByCard,
    players: normalizedPlayers,
    tiles,
  };
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
    scoreCoinCount: 0,
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
