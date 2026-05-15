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

export type TurnHistoryRelevance = "mine-critical" | "mine" | "important" | "public";
export type TurnHistoryScope = "common" | "player";

export type TurnHistoryEvent = {
  seq: number;
  eventCode: string;
  label: string;
  detail: string;
  tone: "move" | "economy" | "system" | "critical";
  scope: TurnHistoryScope;
  relevance: TurnHistoryRelevance;
  participants: Record<string, number>;
  participantPlayerIds: number[];
  focusTileIndices: number[];
  resourceDelta: Record<string, number> | null;
  endTimeDelta: { before: number; delta: number; after: number } | null;
  payload: Record<string, unknown>;
};

export type TurnHistoryTurn = {
  key: string;
  label: string;
  round: number;
  turn: number;
  actorPlayerId: number | null;
  actor: string;
  eventCount: number;
  importantCount: number;
  events: TurnHistoryEvent[];
};

export type TurnHistoryViewModel = {
  currentKey: string | null;
  turns: TurnHistoryTurn[];
  latestTurn: TurnHistoryTurn | null;
};

export type AlertItem = {
  seq: number;
  severity: "warning" | "critical";
  title: string;
  detail: string;
};

export type RuntimeProjectionViewModel = {
  runnerKind: string;
  latestModulePath: string[];
  roundStage: string;
  turnStage: string;
  activeSequence: string;
  activePromptRequestId: string;
  activeFrameId: string;
  activeFrameType: string;
  activeModuleId: string;
  activeModuleType: string;
  activeModuleStatus: string;
  activeModuleCursor: string;
  activeModuleIdempotencyKey: string;
  draftActive: boolean;
  trickSequenceActive: boolean;
  cardFlipLegal: boolean;
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
  currentBeatEventCode: string;
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

export type StreamSelectorViewerIdentity = {
  legacyPlayerId?: number | null;
  protocolPlayerId?: unknown;
  publicPlayerId?: string | null;
  seatId?: string | null;
  viewerId?: string | null;
};

export type StreamSelectorViewerIdentityInput = number | StreamSelectorViewerIdentity | null | undefined;

type NormalizedStreamSelectorViewerIdentity = {
  legacyPlayerId: number | null;
  protocolPlayerId: string | null;
  publicPlayerId: string | null;
  seatId: string | null;
  viewerId: string | null;
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
  effectCharacter?: string;
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
  hidden_trick_count?: number;
  public_tricks?: string[];
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

type BackendPlayerCardItem = {
  player_id: number;
  legacy_player_id: number | null;
  public_player_id: string | null;
  seat_id: string | null;
  viewer_id: string | null;
  character: string;
  priority_slot: number | null;
  turn_order_rank: number | null;
  reveal_state: "selected_private" | "revealed";
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
  detail: string;
  payload: Record<string, unknown> | null;
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
  economy: {
    startingCash?: number;
  };
  resources: {
    startingShards?: number;
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

function nonEmptyStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
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

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function normalizeViewerIdentity(input: StreamSelectorViewerIdentityInput): NormalizedStreamSelectorViewerIdentity {
  if (typeof input === "number" && Number.isFinite(input) && input > 0) {
    return {
      legacyPlayerId: Math.floor(input),
      protocolPlayerId: null,
      publicPlayerId: null,
      seatId: null,
      viewerId: null,
    };
  }
  if (!isRecord(input)) {
    return {
      legacyPlayerId: null,
      protocolPlayerId: null,
      publicPlayerId: null,
      seatId: null,
      viewerId: null,
    };
  }
  return {
    legacyPlayerId: numberOrNull(input["legacyPlayerId"]),
    protocolPlayerId: stringOrNull(input["protocolPlayerId"]),
    publicPlayerId: stringOrNull(input["publicPlayerId"]),
    seatId: stringOrNull(input["seatId"]),
    viewerId: stringOrNull(input["viewerId"]),
  };
}

function identityStringMatches(value: string | null, ...candidates: unknown[]): boolean {
  if (!value) {
    return false;
  }
  return candidates.some((candidate) => typeof candidate === "string" && candidate.trim() === value);
}

function viewerIdentityMatchesRecord(
  record: Record<string, unknown>,
  fallbackPlayerId: number | null,
  viewer: NormalizedStreamSelectorViewerIdentity
): boolean {
  if (
    identityStringMatches(
      viewer.publicPlayerId,
      record["public_player_id"],
      record["target_public_player_id"],
      record["primary_player_id"],
      record["player_id"]
    )
  ) {
    return true;
  }
  if (
    identityStringMatches(
      viewer.protocolPlayerId,
      record["primary_player_id"],
      record["player_id"],
      record["public_player_id"],
      record["target_public_player_id"]
    )
  ) {
    return true;
  }
  if (identityStringMatches(viewer.seatId, record["seat_id"], record["target_seat_id"])) {
    return true;
  }
  if (identityStringMatches(viewer.viewerId, record["viewer_id"], record["target_viewer_id"])) {
    return true;
  }
  if (viewer.legacyPlayerId === null) {
    return false;
  }
  return (
    viewer.legacyPlayerId === numberOrNull(record["legacy_player_id"]) ||
    viewer.legacyPlayerId === numberOrNull(record["target_legacy_player_id"]) ||
    viewer.legacyPlayerId === numberOrNull(record["player_id"]) ||
    viewer.legacyPlayerId === fallbackPlayerId
  );
}

function viewerIdentityMatchesBackendPlayerCard(
  playerCard: BackendPlayerCardItem | undefined,
  viewer: NormalizedStreamSelectorViewerIdentity
): boolean {
  if (!playerCard) {
    return false;
  }
  return viewerIdentityMatchesRecord(
    {
      player_id: playerCard.player_id,
      legacy_player_id: playerCard.legacy_player_id,
      public_player_id: playerCard.public_player_id,
      seat_id: playerCard.seat_id,
      viewer_id: playerCard.viewer_id,
    },
    playerCard.player_id,
    viewer
  );
}

function messageKindFromPayload(payload: Record<string, unknown>): string {
  const eventType = payload["event_type"];
  if (eventType === "engine_transition" && payload["status"] === "completed") {
    return "game_end";
  }
  return typeof eventType === "string" && eventType.trim() ? eventType : "";
}

function isCompletedEngineTransitionPayload(payload: Record<string, unknown>): boolean {
  return payload["event_type"] === "engine_transition" && payload["status"] === "completed";
}

function findLatestTerminalGameEndMessage(messages: InboundMessage[]): InboundMessage | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "event") {
      continue;
    }
    const eventCode = messageKindFromPayload(message.payload);
    if (eventCode === "game_end") {
      return message;
    }
  }
  return null;
}

function decisionProviderFromPayload(payload: Record<string, unknown>): string {
  const provider = payload["provider"];
  return typeof provider === "string" && provider.trim() ? provider : "";
}

function playerLabel(playerId: number, text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT): string {
  return text.stream.playerLabel(playerId);
}

function firstNumberFromPayloadFields(payload: Record<string, unknown>, fields: string[]): number | null {
  for (const field of fields) {
    const value = numberOrNull(payload[field]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function firstIntegerArrayFromPayloadFields(payload: Record<string, unknown>, fields: string[]): number[] {
  for (const field of fields) {
    const values = integerArray(payload[field]);
    if (values.length > 0) {
      return values;
    }
  }
  return [];
}

function boardMarkerOwnerPlayerIdFromPayload(payload: Record<string, unknown> | null | undefined): number | null {
  return payload
    ? firstNumberFromPayloadFields(payload, [
        "marker_owner_legacy_player_id",
        "marker_owner_seat_index",
        "marker_owner_player_id",
      ])
    : null;
}

function boardTileOwnerPlayerIdFromPayload(payload: Record<string, unknown>): number | null {
  return firstNumberFromPayloadFields(payload, ["owner_legacy_player_id", "owner_seat_index", "owner_player_id"]);
}

function boardTilePawnPlayerIdsFromPayload(payload: Record<string, unknown>): number[] {
  return firstIntegerArrayFromPayloadFields(payload, ["pawn_legacy_player_ids", "pawn_seat_indices", "pawn_player_ids"]);
}

function boardLastMovePlayerIdFromPayload(payload: Record<string, unknown>): number | null {
  return firstNumberFromPayloadFields(payload, ["legacy_player_id", "seat_index", "player_id"]);
}

function playerLabelFromPayloadFields(
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources,
  labelFields: string[],
  numericFields: string[]
): string {
  for (const field of labelFields) {
    const label = nonEmptyStringOrNull(payload[field]);
    if (label !== null) {
      return label;
    }
  }
  const playerId = firstNumberFromPayloadFields(payload, numericFields);
  return playerId !== null ? playerLabel(playerId, text) : "-";
}

function playerTokenFromPayloadFields(payload: Record<string, unknown>, numericFields: string[]): number | "?" {
  const playerId = firstNumberFromPayloadFields(payload, numericFields);
  return playerId !== null ? playerId : "?";
}

function relatedPlayerTokenFromPayload(
  payload: Record<string, unknown>,
  prefix: string,
  fallbackFields: string[] = []
): number | "?" {
  return playerTokenFromPayloadFields(payload, [
    `${prefix}_legacy_player_id`,
    `${prefix}_seat_index`,
    ...fallbackFields,
  ]);
}

function relatedPlayerNumberFromPayload(
  payload: Record<string, unknown>,
  prefix: string,
  fallbackFields: string[] = []
): number | null {
  return firstNumberFromPayloadFields(payload, [
    `${prefix}_legacy_player_id`,
    `${prefix}_seat_index`,
    ...fallbackFields,
  ]);
}

function promptPlayerLabelFromPayload(
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  return playerLabelFromPayloadFields(
    payload,
    text,
    ["player_label"],
    ["legacy_player_id", "seat_index", "player_id"]
  );
}

function actorPlayerLabelFromPayload(
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  return playerLabelFromPayloadFields(
    payload,
    text,
    ["acting_player_label", "actor_player_label", "player_label"],
    [
      "acting_legacy_player_id",
      "actor_legacy_player_id",
      "legacy_player_id",
      "acting_seat_index",
      "actor_seat_index",
      "seat_index",
      "acting_player_id",
      "actor_player_id",
      "player_id",
    ]
  );
}

function actorFromPayload(
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  const actor = payload["actor"];
  if (typeof actor === "string" && actor.trim()) {
    return actor;
  }
  return actorPlayerLabelFromPayload(payload, text);
}

function actorFromMessage(
  message: InboundMessage,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): string {
  if (message.type === "event") {
    return actorFromPayload(message.payload, text);
  }
  return promptPlayerLabelFromPayload(message.payload, text);
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

function isMoveEventCode(eventCode: string): boolean {
  return eventCode === "player_move" || eventCode === "action_move" || eventCode === "fortune_move" || eventCode === "forced_move" || eventCode === "chain_move";
}

function isMarkEventCode(eventCode: string): boolean {
  return eventCode.startsWith("mark_");
}

function turnBeatKindFromEventCode(eventCode: string): TurnStageViewModel["currentBeatKind"] {
  if (eventCode === "dice_roll" || isMoveEventCode(eventCode)) {
    return "move";
  }
  if (eventCode === "tile_purchased" || eventCode === "rent_paid" || eventCode === "lap_reward_chosen" || eventCode === "start_reward_chosen") {
    return "economy";
  }
  if (
    eventCode === "weather_reveal" ||
    eventCode === "fortune_drawn" ||
    eventCode === "fortune_resolved" ||
    eventCode === "trick_used" ||
    eventCode === "marker_flip" ||
    eventCode === "marker_transferred" ||
    isMarkEventCode(eventCode) ||
    eventCode === "landing_resolved" ||
    eventCode === "f_value_change"
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
  if (isMoveEventCode(eventCode)) {
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
    const actor = promptPlayerLabelFromPayload(message.payload, text);
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
    const character = asString(payload["character"] ?? payload["actor_name"] ?? payload["current_character"]);
    return text.turnStage.turnStartDetail(actorFromPayload(payload), character !== "-" ? character : undefined);
  }
  if (isMoveEventCode(eventType)) {
    return summarizePlayerMove(payload, text.stream);
  }
  if (eventType === "dice_roll") {
    return summarizeDiceRoll(payload, text.stream);
  }
  if (eventType === "tile_purchased") {
    const tile = numberOrNull(payload["tile_index"]);
    const cost = payload["cost"] ?? payload["purchase_cost"] ?? "?";
    const source = asString(payload["purchase_source"] ?? payload["source"]);
    const multiplier = numberOrNull(payload["purchase_multiplier"]);
    const baseCost = payload["base_cost"];
    const sourceDetail =
      source === "matchmaker_adjacent" || source === "adjacent_extra"
        ? `중매꾼 추가 구매 / ${multiplier === 2 ? "2배 가격" : "기본가"}${typeof baseCost === "number" ? ` / 기본 ${baseCost}` : ""}`
        : "";
    const purchaseDetail = text.stream.tilePurchased(tile === null ? "?" : String(tile + 1), cost);
    return text.stream.actorDetail(
      actorFromPayload(payload, text),
      sourceDetail ? `${purchaseDetail} / ${sourceDetail}` : purchaseDetail
    );
  }
  if (eventType === "rent_paid") {
    const payer = relatedPlayerTokenFromPayload(payload, "payer", ["payer_player_id", "payer"]);
    const owner = relatedPlayerTokenFromPayload(payload, "owner", ["owner_player_id", "owner"]);
    const amount = payload["final_amount"] ?? payload["amount"] ?? payload["base_amount"] ?? "?";
    const tile = numberOrNull(payload["tile_index"]);
    return text.stream.rentPaid(payer, owner, amount, tile === null ? "?" : String(tile + 1));
  }
  if (eventType === "marker_transferred") {
    const from = relatedPlayerTokenFromPayload(payload, "from", ["from_player_id", "from_owner"]);
    const to = relatedPlayerTokenFromPayload(payload, "to", ["to_player_id", "to_owner"]);
    const flipped = relatedPlayerNumberFromPayload(payload, "flip", ["flip_player_id"]);
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
    const actor = promptPlayerLabelFromPayload(payload, text);
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
    const pid = playerTokenFromPayloadFields(payload, [
      "target_legacy_player_id",
      "legacy_player_id",
      "target_seat_index",
      "seat_index",
      "target_player_id",
      "player_id",
    ]);
    return text.stream.bankruptcy(pid);
  }
  if (eventType === "game_end") {
    const winner = relatedPlayerNumberFromPayload(payload, "winner", ["winner_player_id"]);
    if (winner !== null) {
      return text.stream.winner(winner);
    }
    const reason = asString(payload["summary"] ?? payload["reason"] ?? payload["end_reason"]);
    return reason === "-" ? text.stream.gameEndDefault : reason;
  }
  if (eventType === "lap_reward_chosen" || eventType === "start_reward_chosen") {
    const explicitSummary = asString(
      payload["breakdown"] ?? payload["bonus_breakdown"] ?? payload["effect_text"] ?? payload["summary"] ?? payload["resolution"]
    );
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
        const amountDetail = text.stream.lapRewardBundle(parts);
        const rewardDetail =
          explicitSummary !== "-" && explicitSummary !== amountDetail
            ? `${amountDetail} / ${explicitSummary}`
            : amountDetail;
        return text.stream.lapRewardChosen(actorFromPayload(payload, text), rewardDetail);
      }
    }
    const choice = asString(payload["choice"] ?? payload["reward"] ?? explicitSummary);
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
    const source = relatedPlayerNumberFromPayload(payload, "source", ["source_player_id", "player_id"]);
    const target = relatedPlayerNumberFromPayload(payload, "target", ["target_player_id"]);
    const resolution = isRecord(payload["resolution"]) ? payload["resolution"] : null;
    const explicitSummary = asString(payload["summary"] ?? resolution?.["summary"] ?? payload["effect_text"]);
    if (explicitSummary !== "-") {
      return explicitSummary;
    }
    const effectType = asString(payload["effect_type"] ?? resolution?.["type"]);
    const rawActorName = asString(payload["actor_name"] ?? resolution?.["actor_name"]);
    const actorName =
      rawActorName !== "-"
        ? rawActorName
        : effectType === "baksu_transfer"
          ? "박수"
          : effectType === "manshin_remove_burdens"
            ? "만신"
            : "지목";
    if (source !== null && target !== null) {
      if (effectType === "baksu_transfer") {
        const burdenCount = numberOrNull(resolution?.["burden_count"]);
        const rewardCount = numberOrNull(resolution?.["reward_count"]);
        return `${actorName} 지목 성공 / P${source} -> P${target} / 짐 ${burdenCount ?? "?"}장 전달 / 잔꾀 ${rewardCount ?? "?"}장 획득`;
      }
      if (effectType === "manshin_remove_burdens") {
        const removedCount = numberOrNull(resolution?.["removed_count"]);
        const paidAmount = resolution?.["paid_amount"] ?? resolution?.["cash_delta"] ?? resolution?.["cost"] ?? "?";
        return `${actorName} 지목 성공 / P${target} 짐 ${removedCount ?? "?"}장 제거 / P${source} +${paidAmount}냥`;
      }
      return text.stream.markResolved(source, target);
    }
    return text.stream.landing.markResolved;
  }
  if (eventType === "mark_queued") {
    return text.stream.markQueued(
      relatedPlayerTokenFromPayload(payload, "source", ["source_player_id", "player_id"]),
      relatedPlayerTokenFromPayload(payload, "target", ["target_player_id"]),
      asString(payload["target_character"]),
      asString(payload["effect_type"])
    );
  }
  if (eventType === "mark_target_none") {
    return text.stream.markTargetNone(
      relatedPlayerTokenFromPayload(payload, "source", ["source_player_id", "player_id"]),
      asString(payload["actor_name"])
    );
  }
  if (eventType === "mark_target_missing") {
    return text.stream.markTargetMissing(
      relatedPlayerTokenFromPayload(payload, "source", ["source_player_id", "player_id"]),
      asString(payload["target_character"])
    );
  }
  if (eventType === "mark_blocked") {
    return text.stream.markBlocked(
      relatedPlayerTokenFromPayload(payload, "source", ["source_player_id", "player_id"]),
      relatedPlayerTokenFromPayload(payload, "target", ["target_player_id"]),
      asString(payload["target_character"])
    );
  }
  if (eventType === "ability_suppressed") {
    const explicitSummary = asString(payload["summary"] ?? payload["effect_text"]);
    if (explicitSummary !== "-") {
      return explicitSummary;
    }
    return text.stream.abilitySuppressed(
      relatedPlayerTokenFromPayload(payload, "source", ["source_player_id", "player_id"]),
      asString(payload["actor_name"] ?? payload["character"]),
      asString(payload["reason"])
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
  if (eventType === "turn_end_snapshot") {
    const label = eventLabelForCode("turn_end_snapshot", text.eventLabel);
    const actor = actorFromPayload(payload, text);
    return actor === "-" ? label : text.stream.actorDetail(actor, label);
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
    let summary = asString(payload["summary"] ?? payload["resolution"] ?? payload["card_name"]);
    if (summary === "-") {
      summary = asString(payload["card_name"] ?? payload["card"]);
    }
    return text.stream.actorDetail(actorFromPayload(payload, text), text.stream.fortuneResolved(summary));
  }
  if (eventType === "trick_used") {
    const cardName = asString(payload["card_name"] ?? payload["card"] ?? payload["trick_name"] ?? payload["name"]);
    const effect = asString(payload["card_description"] ?? payload["description"] ?? payload["effect_text"] ?? payload["summary"]);
    const trickText = [cardName, effect].filter((part) => part !== "-").join(" / ");
    return text.stream.actorDetail(actorFromPayload(payload, text), trickText || eventLabelForCode("trick_used", text.eventLabel));
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
  if (!backendScene) {
    return [];
  }
  const safeLimit = Math.max(1, limit);
  return backendScene.timeline.slice(0, safeLimit).map((item) => ({
    seq: item.seq,
    label:
      item.messageType !== "event"
        ? nonEventLabelForMessageType(item.messageType as InboundMessage["type"], text.eventLabel)
        : eventLabelForCode(item.eventCode, text.eventLabel),
    detail: "",
  }));
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
  "action_move",
  "fortune_move",
  "forced_move",
  "chain_move",
  "landing_resolved",
  "rent_paid",
  "tile_purchased",
  "marker_transferred",
  "marker_flip",
  "lap_reward_chosen",
  "start_reward_chosen",
  "fortune_drawn",
  "fortune_resolved",
  "mark_resolved",
  "mark_queued",
  "mark_target_none",
  "mark_target_missing",
  "mark_blocked",
  "ability_suppressed",
  "f_value_change",
  "bankruptcy",
  "game_end",
  "turn_end_snapshot",
]);

const CURRENT_TURN_REVEAL_EVENT_CODES = new Set<string>([
  "weather_reveal",
  "dice_roll",
  "trick_used",
  "player_move",
  "action_move",
  "fortune_move",
  "forced_move",
  "chain_move",
  "landing_resolved",
  "tile_purchased",
  "rent_paid",
  "lap_reward_chosen",
  "start_reward_chosen",
  "fortune_drawn",
  "fortune_resolved",
  "mark_queued",
  "mark_resolved",
  "mark_target_none",
  "mark_target_missing",
  "mark_blocked",
  "ability_suppressed",
  "f_value_change",
  "marker_flip",
  "marker_transferred",
  "bankruptcy",
  "game_end",
]);

const CURRENT_TURN_REVEAL_ORDER: Record<string, number> = {
  weather_reveal: 10,
  dice_roll: 20,
  trick_used: 25,
  player_move: 30,
  action_move: 30,
  fortune_move: 32,
  forced_move: 32,
  chain_move: 32,
  landing_resolved: 40,
  rent_paid: 50,
  tile_purchased: 50,
  lap_reward_chosen: 58,
  start_reward_chosen: 58,
  fortune_drawn: 60,
  fortune_resolved: 70,
  mark_queued: 76,
  mark_resolved: 78,
  mark_target_none: 78,
  mark_target_missing: 78,
  mark_blocked: 78,
  ability_suppressed: 79,
  f_value_change: 84,
  marker_transferred: 80,
  marker_flip: 82,
  bankruptcy: 90,
  game_end: 95,
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
  if (!backendScene) {
    return [];
  }
  const safeLimit = Math.max(1, limit);
  return backendScene.theaterFeed.slice(0, safeLimit).map((item) => ({
    seq: item.seq,
    label:
      item.messageType !== "event"
        ? nonEventLabelForMessageType(item.messageType as InboundMessage["type"], text.eventLabel)
        : eventLabelForCode(item.eventCode, text.eventLabel),
    detail: "",
    tone: item.tone,
    lane: item.lane,
    actor: item.actorPlayerId !== null ? playerLabel(item.actorPlayerId, text) : "-",
    eventCode: item.eventCode,
  }));
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
  if (!backendScene) {
    return [];
  }
  const safeLimit = Math.max(1, limit);
  return backendScene.criticalAlerts
    .map((item) => ({
      seq: item.seq,
      severity: item.severity,
      title:
        item.messageType !== "event"
          ? nonEventLabelForMessageType(item.messageType as InboundMessage["type"], text.eventLabel)
          : eventLabelForCode(item.eventCode, text.eventLabel),
      detail: "-",
    }))
    .sort((a, b) => b.seq - a.seq)
    .slice(0, safeLimit);
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
  if (!backendScene) {
    return [];
  }
  const safeLimit = Math.max(1, limit);
  return backendScene.coreActionFeed.slice(0, safeLimit).map((item) => ({
    seq: item.seq,
    actor: item.actorPlayerId !== null ? playerLabel(item.actorPlayerId, text) : "-",
    eventCode: item.eventCode,
    round: item.roundIndex,
    turn: item.turnIndex,
    label: eventLabelForCode(item.eventCode, text.eventLabel),
    detail:
      isMissingRenderedDetail(item.detail) && item.payload
        ? detailFromEventCode(item.payload, item.eventCode, text) || "-"
        : item.detail,
    isLocalActor: focusPlayerId !== null && item.actorPlayerId === focusPlayerId,
  }));
}

const TURN_HISTORY_IMPORTANT_EVENT_CODES = new Set<string>([
  "dice_roll",
  "player_move",
  "action_move",
  "fortune_move",
  "forced_move",
  "chain_move",
  "landing_resolved",
  "rent_paid",
  "tile_purchased",
  "start_reward_chosen",
  "lap_reward_chosen",
  "fortune_drawn",
  "fortune_resolved",
  "mark_queued",
  "mark_resolved",
  "mark_target_none",
  "mark_target_missing",
  "mark_blocked",
  "f_value_change",
  "resource_gain",
  "cash_gain",
  "coin_gain",
  "score_gain",
  "shard_gain",
]);

function selectBackendTurnHistory(messages: InboundMessage[]): Record<string, unknown> | null {
  const viewState = selectLatestBackendViewState(messages);
  const turnHistory = isRecord(viewState?.["turn_history"]) ? viewState["turn_history"] : null;
  return turnHistory;
}

function turnHistoryTone(value: unknown, eventCode: string): TurnHistoryEvent["tone"] {
  if (value === "move" || value === "economy" || value === "system" || value === "critical") {
    return value;
  }
  return toneForEventCode(eventCode);
}

function turnHistoryRelevance(value: unknown): TurnHistoryRelevance {
  if (value === "mine-critical" || value === "mine" || value === "important" || value === "public") {
    return value;
  }
  return "public";
}

const COMMON_TURN_HISTORY_EVENT_CODES = new Set([
  "f_value_change",
  "game_completed",
  "game_end",
  "parameter_manifest",
  "round_start",
  "session_created",
  "session_start",
  "session_started",
  "weather_reveal",
]);

function turnHistoryScope(value: unknown, eventCode: string): TurnHistoryScope {
  if (value === "common" || value === "player") {
    return value;
  }
  return COMMON_TURN_HISTORY_EVENT_CODES.has(eventCode) ? "common" : "player";
}

function numericRecord(value: unknown): Record<string, number> | null {
  if (!isRecord(value)) {
    return null;
  }
  const result: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (typeof raw === "number" && Number.isFinite(raw)) {
      result[key] = raw;
    }
  }
  return Object.keys(result).length > 0 ? result : null;
}

function endTimeDeltaRecord(value: unknown): TurnHistoryEvent["endTimeDelta"] {
  if (!isRecord(value)) {
    return null;
  }
  const before = numberOrNull(value["before"]);
  const delta = numberOrNull(value["delta"]);
  const after = numberOrNull(value["after"]);
  return before !== null && delta !== null && after !== null ? { before, delta, after } : null;
}

function addParticipant(participants: Record<string, number>, key: string, value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    participants[key] = value;
  }
}

function addParticipantFromPayloadFields(
  participants: Record<string, number>,
  key: string,
  payload: Record<string, unknown>,
  fields: string[]
) {
  const value = firstNumberFromPayloadFields(payload, fields);
  if (value !== null) {
    participants[key] = value;
  }
}

function participantsFromEvent(raw: Record<string, unknown>, payload: Record<string, unknown>): Record<string, number> {
  const participants: Record<string, number> = {};
  const source = isRecord(raw["participants"]) ? raw["participants"] : null;
  if (source) {
    for (const [key, value] of Object.entries(source)) {
      addParticipant(participants, key, value);
    }
  }
  addParticipantFromPayloadFields(participants, "actor", payload, [
    "actor_legacy_player_id",
    "acting_legacy_player_id",
    "legacy_player_id",
    "actor_seat_index",
    "acting_seat_index",
    "seat_index",
    "actor_player_id",
    "acting_player_id",
    "player_id",
  ]);
  addParticipantFromPayloadFields(participants, "source", payload, [
    "source_legacy_player_id",
    "source_seat_index",
    "source_player_id",
  ]);
  addParticipantFromPayloadFields(participants, "target", payload, [
    "target_legacy_player_id",
    "target_seat_index",
    "target_player_id",
  ]);
  addParticipantFromPayloadFields(participants, "payer", payload, [
    "payer_legacy_player_id",
    "payer_seat_index",
    "payer_player_id",
    "payer",
  ]);
  addParticipantFromPayloadFields(participants, "owner", payload, [
    "owner_legacy_player_id",
    "owner_seat_index",
    "owner_player_id",
    "owner",
  ]);
  addParticipantFromPayloadFields(participants, "from", payload, [
    "from_legacy_player_id",
    "from_seat_index",
    "from_player_id",
    "from_owner",
  ]);
  addParticipantFromPayloadFields(participants, "to", payload, [
    "to_legacy_player_id",
    "to_seat_index",
    "to_player_id",
    "to_owner",
  ]);
  return participants;
}

function uniqueParticipantIds(participants: Record<string, number>): number[] {
  return [...new Set(Object.values(participants).filter((value) => Number.isFinite(value)))].sort((a, b) => a - b);
}

function focusIndicesFromEvent(raw: Record<string, unknown>, payload: Record<string, unknown>, eventCode: string): number[] {
  const explicit = integerArray(raw["focus_tile_indices"]);
  if (explicit.length > 0) {
    return [...new Set(explicit)];
  }
  const focus = focusTileIndexFromPayload(payload, eventCode);
  const path = integerArray(payload["path"]);
  return [...new Set([focus, ...path].filter((value): value is number => value !== null))];
}

function localRelevanceForTurnHistory(
  eventCode: string,
  backendRelevance: TurnHistoryRelevance,
  participants: Record<string, number>,
  resourceDelta: Record<string, number> | null,
  focusPlayerId: number | null
): TurnHistoryRelevance {
  if (focusPlayerId !== null) {
    if (
      eventCode === "rent_paid" &&
      (participants.payer === focusPlayerId || participants.owner === focusPlayerId)
    ) {
      return "mine-critical";
    }
    if (
      eventCode.startsWith("mark_") &&
      (participants.source === focusPlayerId || participants.target === focusPlayerId)
    ) {
      return "mine-critical";
    }
    if (uniqueParticipantIds(participants).includes(focusPlayerId) && resourceDelta !== null) {
      return "mine";
    }
  }
  if (backendRelevance === "mine-critical" || backendRelevance === "mine") {
    return backendRelevance;
  }
  if (TURN_HISTORY_IMPORTANT_EVENT_CODES.has(eventCode)) {
    return "important";
  }
  return backendRelevance;
}

function turnHistoryLabel(round: number, turn: number): string {
  return `R${round}-T${turn}`;
}

function turnHistoryToneFromReveal(tone: CurrentTurnRevealItem["tone"], eventCode: string): TurnHistoryEvent["tone"] {
  if (tone === "move" || tone === "economy") {
    return tone;
  }
  return turnHistoryTone(null, eventCode);
}

function turnHistoryImportantCount(events: TurnHistoryEvent[]): number {
  return events.filter((event) => event.relevance !== "public" && event.eventCode !== "turn_start").length;
}

function turnHistoryEventFromReveal(
  reveal: CurrentTurnRevealItem,
  turn: TurnHistoryTurn,
  focusPlayerId: number | null,
  text: StreamSelectorTextResources
): TurnHistoryEvent {
  const payload: Record<string, unknown> = {
    event_type: reveal.eventCode,
    round_index: turn.round,
    turn_index: turn.turn,
  };
  if (turn.actorPlayerId !== null) {
    payload["acting_player_id"] = turn.actorPlayerId;
  }
  if (reveal.focusTileIndex !== null) {
    const tileField = reveal.eventCode === "landing_resolved" ? "position" : "tile_index";
    payload[tileField] = reveal.focusTileIndex;
  }
  const participants: Record<string, number> = {};
  if (turn.actorPlayerId !== null) {
    participants["actor"] = turn.actorPlayerId;
  }
  const backendRelevance: TurnHistoryRelevance = TURN_HISTORY_IMPORTANT_EVENT_CODES.has(reveal.eventCode)
    ? "important"
    : "public";
  const fallbackDetail = detailFromEventCode(payload, reveal.eventCode, text) || "-";
  const detail = isMissingRenderedDetail(reveal.detail) ? fallbackDetail : reveal.detail;
  const focusTileIndices = reveal.focusTileIndex === null ? [] : [reveal.focusTileIndex];
  return {
    seq: reveal.seq,
    eventCode: reveal.eventCode,
    label: reveal.label || eventLabelForCode(reveal.eventCode, text.eventLabel),
    detail,
    tone: turnHistoryToneFromReveal(reveal.tone, reveal.eventCode),
    scope: "player",
    relevance: localRelevanceForTurnHistory(reveal.eventCode, backendRelevance, participants, null, focusPlayerId),
    participants,
    participantPlayerIds: uniqueParticipantIds(participants),
    focusTileIndices,
    resourceDelta: null,
    endTimeDelta: null,
    payload,
  };
}

function turnIndexForRevealSeq(turns: TurnHistoryTurn[], revealSeq: number): number {
  let candidateIndex = -1;
  let candidateStartSeq = Number.NEGATIVE_INFINITY;
  turns.forEach((turn, index) => {
    const seqs = turn.events.map((event) => event.seq);
    if (seqs.length === 0) {
      return;
    }
    const minSeq = Math.min(...seqs);
    const maxSeq = Math.max(...seqs);
    if (revealSeq >= minSeq && revealSeq <= maxSeq) {
      candidateIndex = index;
      candidateStartSeq = minSeq;
      return;
    }
    if (revealSeq >= minSeq && minSeq >= candidateStartSeq) {
      candidateIndex = index;
      candidateStartSeq = minSeq;
    }
  });
  if (candidateIndex >= 0) {
    return candidateIndex;
  }
  return -1;
}

function mergeRevealItemsIntoTurnHistory(
  turns: TurnHistoryTurn[],
  revealItems: CurrentTurnRevealItem[],
  focusPlayerId: number | null,
  text: StreamSelectorTextResources
): TurnHistoryTurn[] {
  if (turns.length === 0 || revealItems.length === 0) {
    return turns;
  }
  const existingSeqs = new Set<number>();
  turns.forEach((turn) => turn.events.forEach((event) => existingSeqs.add(event.seq)));
  const nextTurns = turns.map((turn) => ({ ...turn, events: [...turn.events] }));
  const changedTurnIndices = new Set<number>();
  revealItems.forEach((reveal) => {
    if (existingSeqs.has(reveal.seq)) {
      return;
    }
    const turnIndex = turnIndexForRevealSeq(nextTurns, reveal.seq);
    if (turnIndex < 0) {
      return;
    }
    const event = turnHistoryEventFromReveal(reveal, nextTurns[turnIndex], focusPlayerId, text);
    nextTurns[turnIndex].events.push(event);
    changedTurnIndices.add(turnIndex);
    existingSeqs.add(reveal.seq);
  });
  return nextTurns.map((turn, index) => {
    const events = [...turn.events].sort((a, b) => a.seq - b.seq);
    if (!changedTurnIndices.has(index)) {
      return { ...turn, events };
    }
    return {
      ...turn,
      eventCount: events.length,
      importantCount: turnHistoryImportantCount(events),
      events,
    };
  });
}

export function selectTurnHistory(
  messages: InboundMessage[],
  focusPlayerId: number | null = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): TurnHistoryViewModel {
  const raw = selectBackendTurnHistory(messages);
  const rawTurns = Array.isArray(raw?.["turns"]) ? raw["turns"] : [];
  const revealItems = selectBackendCurrentTurnRevealItems(messages, text) ?? [];
  const revealBySeq = new Map(revealItems.map((item) => [item.seq, item]));
  const turns = rawTurns
    .map((rawTurn): TurnHistoryTurn | null => {
      if (!isRecord(rawTurn)) {
        return null;
      }
      const key = typeof rawTurn["key"] === "string" && rawTurn["key"].trim() ? rawTurn["key"] : "";
      const round = numberOrNull(rawTurn["round_index"]);
      const turn = numberOrNull(rawTurn["turn_index"]);
      if (!key || round === null || turn === null) {
        return null;
      }
      const actorPlayerId = numberOrNull(rawTurn["actor_player_id"]);
      const eventsRaw = Array.isArray(rawTurn["events"]) ? rawTurn["events"] : [];
      const events = eventsRaw
        .map((rawEvent): TurnHistoryEvent | null => {
          if (!isRecord(rawEvent) || typeof rawEvent["seq"] !== "number" || typeof rawEvent["event_code"] !== "string") {
            return null;
          }
          const eventCode = rawEvent["event_code"];
          const payload = isRecord(rawEvent["payload"]) ? rawEvent["payload"] : {};
          const reveal = revealBySeq.get(rawEvent["seq"]);
          const participants = participantsFromEvent(rawEvent, payload);
          const resourceDelta = numericRecord(rawEvent["resource_delta"]);
          const backendRelevance = turnHistoryRelevance(rawEvent["relevance"]);
          const payloadDetail = detailFromEventCode(payload, eventCode, text) || "-";
          const detail = reveal && !isMissingRenderedDetail(reveal.detail) ? reveal.detail : payloadDetail;
          const focusTileIndices = focusIndicesFromEvent(rawEvent, payload, eventCode);
          if (reveal?.focusTileIndex !== null && reveal?.focusTileIndex !== undefined && !focusTileIndices.includes(reveal.focusTileIndex)) {
            focusTileIndices.push(reveal.focusTileIndex);
          }
          return {
            seq: rawEvent["seq"],
            eventCode,
            label: reveal?.label || eventLabelForCode(eventCode, text.eventLabel),
            detail,
            tone: reveal ? turnHistoryToneFromReveal(reveal.tone, eventCode) : turnHistoryTone(rawEvent["tone"], eventCode),
            scope: turnHistoryScope(rawEvent["scope"], eventCode),
            relevance: localRelevanceForTurnHistory(eventCode, backendRelevance, participants, resourceDelta, focusPlayerId),
            participants,
            participantPlayerIds: uniqueParticipantIds(participants),
            focusTileIndices,
            resourceDelta,
            endTimeDelta: endTimeDeltaRecord(rawEvent["end_time_delta"]),
            payload,
          };
        })
        .filter((event): event is TurnHistoryEvent => event !== null);
      return {
        key,
        label: turnHistoryLabel(round, turn),
        round,
        turn,
        actorPlayerId,
        actor: actorPlayerId !== null ? playerLabel(actorPlayerId, text) : "-",
        eventCount: typeof rawTurn["event_count"] === "number" ? rawTurn["event_count"] : events.length,
        importantCount:
          typeof rawTurn["important_count"] === "number" ? rawTurn["important_count"] : turnHistoryImportantCount(events),
        events,
      };
    })
    .filter((turn): turn is TurnHistoryTurn => turn !== null);
  const rawCurrentKey = typeof raw?.["current_key"] === "string" && raw["current_key"].trim() ? raw["current_key"] : null;
  const preliminaryLatestTurn = turns.length > 0 ? turns[turns.length - 1] : null;
  const currentKey = rawCurrentKey ?? preliminaryLatestTurn?.key ?? null;
  const mergedTurns = mergeRevealItemsIntoTurnHistory(turns, revealItems, focusPlayerId, text);
  const latestTurn = mergedTurns.length > 0 ? mergedTurns[mergedTurns.length - 1] : null;
  return { currentKey, turns: mergedTurns, latestTurn };
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
    const eventType =
      backendScene.situation.headlineMessageType !== "event"
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
  return { actor: "-", round: "-", turn: "-", eventType: "-", weather: "-", weatherEffect: "-" };
}

function roundTurnOfPayload(payload: Record<string, unknown>): { round: number | null; turn: number | null } {
  return {
    round: numberOrNull(payload["round_index"]),
    turn: numberOrNull(payload["turn_index"]),
  };
}

function promptRoundTurnOfPayload(payload: Record<string, unknown>): { round: number | null; turn: number | null } {
  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
  return {
    round: numberOrNull(payload["round_index"] ?? publicContext?.["round_index"]),
    turn: numberOrNull(payload["turn_index"] ?? publicContext?.["turn_index"]),
  };
}

function sameRoundTurn(payload: Record<string, unknown>, targetRound: number | null, targetTurn: number | null): boolean {
  if (targetRound === null || targetTurn === null) {
    return false;
  }
  const current = roundTurnOfPayload(payload);
  return current.round === targetRound && current.turn === targetTurn;
}

function isMissingRenderedDetail(detail: string): boolean {
  const trimmed = detail.trim();
  return trimmed === "" || trimmed === "-" || /\/\s*-$/.test(trimmed);
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

function isTurnScopedPrompt(payload: Record<string, unknown>, targetRound: number | null, targetTurn: number | null): boolean {
  if (targetRound === null || targetTurn === null) {
    return false;
  }
  const promptRoundTurn = promptRoundTurnOfPayload(payload);
  if (promptRoundTurn.turn !== null) {
    return true;
  }
  if (promptRoundTurn.round !== null) {
    return promptRoundTurn.round === targetRound;
  }
  return true;
}

function updateActorFromPrompt(
  model: TurnStageViewModel,
  payload: Record<string, unknown>,
  text: StreamSelectorTextResources
) {
  const promptActor = firstNumberFromPayloadFields(payload, [
    "legacy_player_id",
    "acting_legacy_player_id",
    "seat_index",
    "acting_seat_index",
    "player_id",
    "acting_player_id",
  ]);
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
  const fallback: TurnStageViewModel = {
    turnStartSeq: null,
    actorPlayerId: null,
    actor: "-",
    round: null,
    turn: null,
    character: "-",
    weatherName: "-",
    weatherEffect: "-",
    currentBeatKind: "system",
    currentBeatEventCode: "-",
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
    weatherSummary: "-",
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

  return backendTurnStage
    ? applyBackendTurnStageProjection({ ...fallback }, backendTurnStage, [], text)
    : fallback;
}

export function selectCurrentTurnRevealItems(
  messages: InboundMessage[],
  limit = 6,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): CurrentTurnRevealItem[] {
  const safeLimit = Math.max(1, limit);
  const backendItems = selectBackendCurrentTurnRevealItems(messages);
  void text;
  return backendItems ? backendItems.slice(-safeLimit) : [];
}

export function selectCurrentRoundRevealItems(
  messages: InboundMessage[],
  limit = 24,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): CurrentTurnRevealItem[] {
  const safeLimit = Math.max(1, limit);
  void text;
  const backendItems = selectBackendCurrentTurnRevealItems(messages);
  return backendItems ? backendItems.slice(-safeLimit) : [];
}

export function selectLastMove(messages: InboundMessage[]): LastMoveViewModel | null {
  const backendMove = selectBackendLastMove(messages);
  return backendMove && backendMove.fromTileIndex !== backendMove.toTileIndex ? backendMove : null;
}

function latestTurnStartSequence(messages: InboundMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type === "event" && messageKindFromPayload(message.payload) === "turn_start") {
      return message.seq;
    }
  }
  return Number.NEGATIVE_INFINITY;
}

function isMovementBearingEvent(eventCode: string): boolean {
  return (
    isMoveEventCode(eventCode) ||
    eventCode === "fortune_resolved" ||
    eventCode === "trick_used" ||
    isMarkEventCode(eventCode)
  );
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
    ownerPlayerId: boardTileOwnerPlayerIdFromPayload(raw),
    pawnPlayerIds: boardTilePawnPlayerIdsFromPayload(raw),
  };
}

function snapshotFromBackendViewStatePayload(payload: Record<string, unknown>): SnapshotViewModel | null {
  const viewState = isRecord(payload["view_state"]) ? payload["view_state"] : null;
  if (!viewState) {
    return null;
  }

  const playersState = isRecord(viewState["players"]) ? viewState["players"] : null;
  const playerItems = Array.isArray(playersState?.["items"]) ? playersState["items"] : null;
  if (!playerItems || playerItems.length === 0) {
    return null;
  }

  const board = isRecord(viewState["board"]) ? viewState["board"] : null;
  const tileItems = Array.isArray(board?.["tiles"]) ? board["tiles"] : [];
  const playerCardsByPlayerId = new Map(
    selectBackendPlayerCardItemsFromViewState(viewState).map((item) => [item.player_id, item])
  );
  const positionByPlayerId = new Map<number, number>();
  for (const rawTile of tileItems) {
    if (!isRecord(rawTile)) {
      continue;
    }
    const tileIndex = numberOrNull(rawTile["tile_index"]);
    if (tileIndex === null) {
      continue;
    }
    for (const pawnPlayerId of boardTilePawnPlayerIdsFromPayload(rawTile)) {
      positionByPlayerId.set(pawnPlayerId, tileIndex);
    }
  }

  const players = playerItems
    .map((rawPlayer): PlayerViewModel | null => {
      if (!isRecord(rawPlayer) || typeof rawPlayer["player_id"] !== "number") {
        return null;
      }
      const playerId = rawPlayer["player_id"];
      const playerCard = playerCardsByPlayerId.get(playerId);
      const backendCharacter =
        typeof rawPlayer["current_character_face"] === "string" && rawPlayer["current_character_face"].trim()
          ? rawPlayer["current_character_face"].trim()
          : "-";
      return toPlayerViewModel({
        ...rawPlayer,
        character: playerCard?.character ?? backendCharacter,
        position: numberOrNull(rawPlayer["position"]) ?? positionByPlayerId.get(playerId) ?? 0,
        alive: typeof rawPlayer["alive"] === "boolean" ? rawPlayer["alive"] : true,
        public_tricks: rawPlayer["public_tricks"],
        hand_coins: numberOrNull(rawPlayer["hand_coins"]) ?? numberOrNull(rawPlayer["hand_score_coins"]) ?? 0,
        placed_score_coins:
          numberOrNull(rawPlayer["placed_score_coins"]) ?? numberOrNull(rawPlayer["placed_coins"]) ?? 0,
        score: numberOrNull(rawPlayer["score"]) ?? numberOrNull(rawPlayer["total_score"]) ?? 0,
      });
    })
    .filter((item): item is PlayerViewModel => item !== null);
  if (players.length === 0) {
    return null;
  }

  const tiles = tileItems
    .map((tile, index) => toTileViewModel(tile, index))
    .filter((item): item is TileViewModel => item !== null);
  const markerOwnerPlayer =
    playerItems.find((item) => isRecord(item) && item["is_marker_owner"] === true && typeof item["player_id"] === "number") ??
    null;
  const markerOwnerPlayerId =
    boardMarkerOwnerPlayerIdFromPayload(board) ??
    numberOrNull(playersState?.["marker_owner_player_id"]) ??
    (isRecord(markerOwnerPlayer) ? numberOrNull(markerOwnerPlayer["player_id"]) : null);
  const turnStage = isRecord(viewState["turn_stage"]) ? viewState["turn_stage"] : null;
  const scene = isRecord(viewState["scene"]) ? viewState["scene"] : null;
  const situation = isRecord(scene?.["situation"]) ? scene["situation"] : null;
  const activeByCard: Record<number, string> = {};
  for (const playerCard of playerCardsByPlayerId.values()) {
    const slot = numberOrNull(playerCard.priority_slot);
    const character = typeof playerCard.character === "string" ? playerCard.character.trim() : "";
    if (slot !== null && character.length > 0) {
      activeByCard[slot] = character;
    }
  }
  mergeActiveByCard(activeByCard, viewState["active_by_card"]);

  return {
    round:
      numberOrNull(turnStage?.["round_index"]) ??
      numberOrNull(situation?.["round_index"]) ??
      numberOrNull(payload["round_index"]) ??
      0,
    turn:
      numberOrNull(turnStage?.["turn_index"]) ??
      numberOrNull(situation?.["turn_index"]) ??
      numberOrNull(payload["turn_index"]) ??
      0,
    markerOwnerPlayerId,
    markerDraftDirection:
      markerDraftDirectionFromRecord(board) ??
      markerDraftDirectionFromRecord(playersState) ??
      markerDraftDirectionFromRecord(payload),
    fValue: numberOrNull(board?.["f_value"]) ?? 0,
    currentRoundOrder: Array.from(new Set(integerArray(playersState?.["ordered_player_ids"]))).filter(
      (value) => value >= 1
    ),
    activeByCard,
    players,
    tiles,
  };
}

function snapshotFromMessage(message: InboundMessage): SnapshotViewModel | null {
  if (message.type !== "view_commit") {
    return null;
  }
  return snapshotFromBackendViewStatePayload(message.payload);
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

function hasActiveByCardPayload(payload: Record<string, unknown>): boolean {
  if (isRecord(payload["active_by_card"])) {
    return true;
  }
  const snapshot = isRecord(payload["snapshot"]) ? payload["snapshot"] : null;
  if (isRecord(snapshot?.["active_by_card"])) {
    return true;
  }
  const publicContext = isRecord(payload["public_context"]) ? payload["public_context"] : null;
  if (isRecord(publicContext?.["active_by_card"])) {
    return true;
  }
  return false;
}

function shouldResetActiveByCard(eventCode: string, payload: Record<string, unknown>): boolean {
  return (
    (eventCode === "round_start" || eventCode === "round_order") &&
    hasActiveByCardPayload(payload)
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
    if (shouldResetActiveByCard(eventCode, message.payload)) {
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
    if (messages[i].type !== "view_commit") {
      continue;
    }
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
    if (messages[i].type !== "view_commit") {
      continue;
    }
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload["view_state"] : null;
    if (viewState) {
      return viewState;
    }
  }
  return null;
}

export function selectRuntimeProjection(messages: InboundMessage[]): RuntimeProjectionViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type !== "view_commit") {
      continue;
    }
    const payload = isRecord(messages[i].payload) ? messages[i].payload : null;
    const viewState = isRecord(payload?.["view_state"]) ? payload["view_state"] : null;
    const runtime = isRecord(viewState?.["runtime"]) ? viewState["runtime"] : null;
    if (!runtime) {
      continue;
    }
    return {
      runnerKind: asString(runtime["runner_kind"]),
      latestModulePath: stringArray(runtime["latest_module_path"]),
      roundStage: typeof runtime["round_stage"] === "string" ? runtime["round_stage"] : "",
      turnStage: typeof runtime["turn_stage"] === "string" ? runtime["turn_stage"] : "",
      activeSequence: typeof runtime["active_sequence"] === "string" ? runtime["active_sequence"] : "",
      activePromptRequestId:
        typeof runtime["active_prompt_request_id"] === "string" ? runtime["active_prompt_request_id"] : "",
      activeFrameId: asString(runtime["active_frame_id"]),
      activeFrameType: asString(runtime["active_frame_type"]),
      activeModuleId: asString(runtime["active_module_id"]),
      activeModuleType: asString(runtime["active_module_type"]),
      activeModuleStatus: asString(runtime["active_module_status"]),
      activeModuleCursor: asString(runtime["active_module_cursor"]),
      activeModuleIdempotencyKey: asString(runtime["active_module_idempotency_key"]),
      draftActive: runtime["draft_active"] === true,
      trickSequenceActive: runtime["trick_sequence_active"] === true,
      cardFlipLegal: runtime["card_flip_legal"] === true,
    };
  }
  return null;
}

function isStateBearingMessage(message: InboundMessage): boolean {
  return message.type === "view_commit";
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
    if (messages[i].type !== "view_commit") {
      continue;
    }
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

function selectBackendPlayerCardItemsFromViewState(viewState: Record<string, unknown>): BackendPlayerCardItem[] {
  const playerCards = isRecord(viewState["player_cards"]) ? viewState["player_cards"] : null;
  const items = Array.isArray(playerCards?.["items"]) ? playerCards["items"] : null;
  if (!items) {
    return [];
  }
  return items
    .map((item): BackendPlayerCardItem | null => {
      if (!isRecord(item) || typeof item["player_id"] !== "number") {
        return null;
      }
      const character = typeof item["character"] === "string" ? item["character"].trim() : "";
      const revealState = item["reveal_state"];
      if (!character || (revealState !== "selected_private" && revealState !== "revealed")) {
        return null;
      }
      return {
        player_id: item["player_id"],
        legacy_player_id: numberOrNull(item["legacy_player_id"]),
        public_player_id: stringOrNull(item["public_player_id"]),
        seat_id: stringOrNull(item["seat_id"]),
        viewer_id: stringOrNull(item["viewer_id"]),
        character,
        priority_slot: typeof item["priority_slot"] === "number" ? item["priority_slot"] : null,
        turn_order_rank: typeof item["turn_order_rank"] === "number" ? item["turn_order_rank"] : null,
        reveal_state: revealState,
        is_current_actor: item["is_current_actor"] === true,
      };
    })
    .filter((item): item is BackendPlayerCardItem => item !== null);
}

function selectBackendDerivedPlayers(
  messages: InboundMessage[],
  currentLocalViewer: StreamSelectorViewerIdentityInput
): DerivedPlayerViewModel[] | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }
  const viewerIdentity = normalizeViewerIdentity(currentLocalViewer);
  const backendTurnStage = selectBackendTurnStage(messages);
  const gameEnded = backendTurnStage?.currentBeatEventCode === "game_end";
  const players = isRecord(entry.viewState["players"]) ? entry.viewState["players"] : null;
  const items = Array.isArray(players?.["items"]) ? players["items"] : null;
  if (!items || items.length === 0) {
    return null;
  }
  const playerCardsByPlayerId = new Map(
    selectBackendPlayerCardItemsFromViewState(entry.viewState).map((item) => [item.player_id, item])
  );
  const mapped = items.map((item): DerivedPlayerViewModel | null => {
    if (!isRecord(item) || typeof item["player_id"] !== "number") {
      return null;
    }
    const playerId = item["player_id"];
    const playerCard = playerCardsByPlayerId.get(playerId);
    const backendCharacter =
      typeof item["current_character_face"] === "string" && item["current_character_face"].trim()
        ? item["current_character_face"].trim()
        : "-";
    const currentCharacterFace = playerCard?.character ?? backendCharacter;
    return {
      playerId,
      displayName: typeof item["display_name"] === "string" ? item["display_name"] : `Player ${playerId}`,
      character: currentCharacterFace,
      alive: true,
      position: 0,
      cash: typeof item["cash"] === "number" ? item["cash"] : 0,
      shards: typeof item["shards"] === "number" ? item["shards"] : 0,
      handCoins: typeof item["hand_coins"] === "number" ? item["hand_coins"] : 0,
      placedCoins: typeof item["placed_coins"] === "number" ? item["placed_coins"] : 0,
      totalScore: typeof item["total_score"] === "number" ? item["total_score"] : 0,
      hiddenTrickCount: typeof item["hidden_trick_count"] === "number" ? item["hidden_trick_count"] : 0,
      ownedTileCount: typeof item["owned_tile_count"] === "number" ? item["owned_tile_count"] : 0,
      publicTricks: stringArray(item["public_tricks"]),
      trickCount: typeof item["trick_count"] === "number" ? item["trick_count"] : 0,
      prioritySlot: playerCard?.priority_slot ?? (typeof item["priority_slot"] === "number" ? item["priority_slot"] : null),
      currentCharacterFace,
      isMarkerOwner: item["is_marker_owner"] === true,
      isCurrentActor: !gameEnded && (item["is_current_actor"] === true || playerCard?.is_current_actor === true),
      isLocalPlayer:
        viewerIdentityMatchesRecord(item, playerId, viewerIdentity) ||
        viewerIdentityMatchesBackendPlayerCard(playerCard, viewerIdentity),
    };
  });
  return mapped.filter((item): item is DerivedPlayerViewModel => item !== null);
}

function selectBackendActiveCharacterSlots(
  messages: InboundMessage[],
  currentLocalViewer: StreamSelectorViewerIdentityInput
): ActiveCharacterSlotViewModel[] | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }
  const viewerIdentity = normalizeViewerIdentity(currentLocalViewer);
  const backendTurnStage = selectBackendTurnStage(messages);
  const gameEnded = backendTurnStage?.currentBeatEventCode === "game_end";
  const activeSlots = isRecord(entry.viewState["active_slots"]) ? entry.viewState["active_slots"] : null;
  const items = Array.isArray(activeSlots?.["items"]) ? activeSlots["items"] : null;
  if (!items || items.length === 0) {
    return null;
  }
  const playerCardsBySlot = new Map(
    selectBackendPlayerCardItemsFromViewState(entry.viewState)
      .filter((item) => item.priority_slot !== null)
      .map((item) => [item.priority_slot as number, item])
  );
  const seenSlots = new Set<number>();
  const mapped = items
    .map((item) => {
      if (!isRecord(item)) {
        return null;
      }
      const slot = numberOrNull(item["slot"] ?? item["priority_slot"]);
      if (slot === null) {
        return null;
      }
      seenSlots.add(slot);
      const playerCard = playerCardsBySlot.get(slot);
      const playerId = typeof item["player_id"] === "number" ? item["player_id"] : playerCard?.player_id ?? null;
      const character =
        typeof item["character"] === "string" && item["character"].trim()
          ? item["character"].trim()
          : playerCard?.character ?? null;
      return {
        slot,
        playerId,
        label: typeof item["label"] === "string" ? item["label"] : playerId !== null ? `P${playerId}` : null,
        character,
        inactiveCharacter:
          typeof item["inactive_character"] === "string" && item["inactive_character"].trim()
            ? item["inactive_character"]
            : null,
        isCurrentActor: !gameEnded && (item["is_current_actor"] === true || playerCard?.is_current_actor === true),
        isLocalPlayer:
          (playerId !== null && viewerIdentityMatchesRecord(item, playerId, viewerIdentity)) ||
          viewerIdentityMatchesBackendPlayerCard(playerCard, viewerIdentity),
      };
    })
    .filter((item): item is ActiveCharacterSlotViewModel => item !== null);
  for (const [slot, playerCard] of playerCardsBySlot) {
    if (seenSlots.has(slot)) {
      continue;
    }
    mapped.push({
      slot,
      playerId: playerCard.player_id,
      label: `P${playerCard.player_id}`,
      character: playerCard.character,
      inactiveCharacter: null,
      isCurrentActor: !gameEnded && playerCard.is_current_actor,
      isLocalPlayer: viewerIdentityMatchesBackendPlayerCard(playerCard, viewerIdentity),
    });
  }
  mapped.sort((left, right) => left.slot - right.slot);
  return mapped.some((item) => item.character) ? mapped : null;
}

function selectRawActiveCharacterSlotsWithoutSnapshot(messages: InboundMessage[]): ActiveCharacterSlotViewModel[] {
  const activeByCard = collectActiveByCardUntil(messages, Math.max(0, messages.length - 1));
  return Array.from({ length: 8 }, (_, index) => {
    const slot = index + 1;
    const character =
      typeof activeByCard[slot] === "string" && activeByCard[slot].trim().length > 0 ? activeByCard[slot] : null;
    return {
      slot,
      playerId: null,
      label: null,
      character,
      inactiveCharacter: character ? oppositeCharacterForSlot(slot, character) : null,
      isCurrentActor: false,
      isLocalPlayer: false,
    };
  });
}

function selectFallbackActiveCharacterSlotsFromMap(
  rawActiveByCard: Record<string, string> | Record<number, string> | null | undefined
): ActiveCharacterSlotViewModel[] {
  const activeByCard: Record<number, string> = {};
  mergeActiveByCard(activeByCard, rawActiveByCard);
  return Array.from({ length: 8 }, (_, index) => {
    const slot = index + 1;
    const character =
      typeof activeByCard[slot] === "string" && activeByCard[slot].trim().length > 0 ? activeByCard[slot] : null;
    return {
      slot,
      playerId: null,
      label: null,
      character,
      inactiveCharacter: character ? oppositeCharacterForSlot(slot, character) : null,
      isCurrentActor: false,
      isLocalPlayer: false,
    };
  });
}

function selectBackendMarkTargetCharacterSlots(messages: InboundMessage[]): MarkTargetSlotViewModel[] | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }
  const markTarget = isRecord(entry.viewState["mark_target"]) ? entry.viewState["mark_target"] : null;
  const candidates = Array.isArray(markTarget?.["candidates"]) ? markTarget["candidates"] : null;
  if (!candidates) {
    return null;
  }
  const mapped = candidates
    .map((item) => {
      if (!isRecord(item) || typeof item["character"] !== "string") {
        return null;
      }
      const slot = numberOrNull(item["slot"] ?? item["priority_slot"]);
      if (slot === null) {
        return null;
      }
      return {
        slot,
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
          detail: typeof item["detail"] === "string" && item["detail"].trim() ? item["detail"].trim() : "-",
          payload: isRecord(item["payload"]) ? item["payload"] : null,
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
  return items
    .map((item): CurrentTurnRevealItem | null => {
      if (!isRecord(item) || typeof item["seq"] !== "number" || typeof item["event_code"] !== "string") {
        return null;
      }
      const eventCode = item["event_code"];
      const label =
        typeof item["label"] === "string" && item["label"].trim()
          ? item["label"].trim()
          : eventLabelForCode(eventCode, text.eventLabel);
      const detail = typeof item["detail"] === "string" && item["detail"].trim() ? item["detail"].trim() : "-";
      const effectCharacter =
        typeof item["effect_character"] === "string" && item["effect_character"].trim()
          ? item["effect_character"].trim()
          : typeof item["effect_character_name"] === "string" && item["effect_character_name"].trim()
            ? item["effect_character_name"].trim()
            : undefined;
      return {
        seq: item["seq"],
        eventCode,
        label,
        detail,
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
        effectCharacter,
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
    playerId: boardLastMovePlayerIdFromPayload(lastMove),
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
        ownerPlayerId: boardTileOwnerPlayerIdFromPayload(item),
        pawnPlayerIds: boardTilePawnPlayerIdsFromPayload(item),
      };
    })
    .filter(
      (
        item
      ): item is Pick<TileViewModel, "tileIndex" | "scoreCoinCount" | "ownerPlayerId" | "pawnPlayerIds"> => item !== null
    );
  return mapped.length > 0 ? mapped : null;
}

function selectBackendSnapshotProjection(
  messages: InboundMessage[]
): Pick<SnapshotViewModel, "round" | "turn" | "markerOwnerPlayerId" | "fValue"> | null {
  const entry = selectLatestBackendViewStateEntry(messages);
  if (!entry) {
    return null;
  }

  const viewState = entry.viewState;
  const board = isRecord(viewState["board"]) ? viewState["board"] : null;
  const scene = isRecord(viewState["scene"]) ? viewState["scene"] : null;
  const situation = isRecord(scene?.["situation"]) ? scene["situation"] : null;
  const turnStage = isRecord(viewState["turn_stage"]) ? viewState["turn_stage"] : null;
  const players = isRecord(viewState["players"]) ? viewState["players"] : null;
  const playerItems = Array.isArray(players?.["items"]) ? players["items"] : [];

  const markerOwnerPlayerId =
    boardMarkerOwnerPlayerIdFromPayload(board) ??
    playerItems.find((item): item is Record<string, unknown> => isRecord(item) && item["is_marker_owner"] === true)?.["player_id"];

  return {
    round:
      numberOrNull(turnStage?.["round_index"]) ??
      numberOrNull(situation?.["round_index"]) ??
      0,
    turn:
      numberOrNull(turnStage?.["turn_index"]) ??
      numberOrNull(situation?.["turn_index"]) ??
      0,
    markerOwnerPlayerId:
      typeof markerOwnerPlayerId === "number" ? markerOwnerPlayerId : null,
    fValue: numberOrNull(board?.["f_value"]) ?? 0,
  };
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
  currentBeatLabel: string;
  currentBeatDetail: string;
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
    currentBeatLabel:
      typeof turnStage["current_beat_label"] === "string" && turnStage["current_beat_label"].trim()
        ? turnStage["current_beat_label"]
        : "-",
    currentBeatDetail:
      typeof turnStage["current_beat_detail"] === "string" && turnStage["current_beat_detail"].trim()
        ? turnStage["current_beat_detail"]
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
    diceSummary: asString(turnStage["dice_summary"]),
    moveSummary: asString(turnStage["move_summary"]),
    trickSummary: asString(turnStage["trick_summary"]),
    landingSummary: asString(turnStage["landing_summary"]),
    purchaseSummary: asString(turnStage["purchase_summary"]),
    rentSummary: asString(turnStage["rent_summary"]),
    turnEndSummary: asString(turnStage["turn_end_summary"]),
    fortuneDrawSummary: asString(turnStage["fortune_draw_summary"]),
    fortuneResolvedSummary: asString(turnStage["fortune_resolved_summary"]),
    fortuneSummary: asString(turnStage["fortune_summary"]),
    lapRewardSummary: asString(turnStage["lap_reward_summary"]),
    markSummary: asString(turnStage["mark_summary"]),
    flipSummary: asString(turnStage["flip_summary"]),
    weatherSummary: asString(turnStage["weather_summary"]),
    effectSummary: asString(turnStage["effect_summary"]),
    promptSummary: asString(turnStage["prompt_summary"]),
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

function applyBackendTurnStageProjection(
  model: TurnStageViewModel,
  backendTurnStage: BackendTurnStageProjection,
  messages: InboundMessage[],
  text: StreamSelectorTextResources
): TurnStageViewModel {
  const messageBySeq = new Map<number, InboundMessage>();
  for (const message of messages) {
    messageBySeq.set(message.seq, message);
  }
  model.turnStartSeq = backendTurnStage.turnStartSeq;
  model.actorPlayerId = backendTurnStage.currentBeatEventCode === "game_end" ? null : backendTurnStage.actorPlayerId;
  model.actor =
    model.actorPlayerId === null ? "-" : playerLabel(model.actorPlayerId, text);
  model.round = backendTurnStage.round;
  model.turn = backendTurnStage.turn;
  model.character = backendTurnStage.character;
  model.weatherName = backendTurnStage.weatherName;
  model.weatherEffect = backendTurnStage.weatherEffect;
  model.currentBeatKind = backendTurnStage.currentBeatKind;
  model.currentBeatEventCode = backendTurnStage.currentBeatEventCode;
  model.focusTileIndex = backendTurnStage.focusTileIndex;
  model.focusTileIndices = backendTurnStage.focusTileIndices;
  model.promptRequestType = backendTurnStage.currentBeatEventCode === "game_end" ? "-" : backendTurnStage.promptRequestType;
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
  model.diceSummary = backendTurnStage.diceSummary;
  model.moveSummary = backendTurnStage.moveSummary;
  model.trickSummary = backendTurnStage.trickSummary;
  model.landingSummary = backendTurnStage.landingSummary;
  model.purchaseSummary = backendTurnStage.purchaseSummary;
  model.rentSummary = backendTurnStage.rentSummary;
  model.turnEndSummary = backendTurnStage.turnEndSummary;
  model.fortuneDrawSummary = backendTurnStage.fortuneDrawSummary;
  model.fortuneResolvedSummary = backendTurnStage.fortuneResolvedSummary;
  model.fortuneSummary = backendTurnStage.fortuneSummary;
  model.lapRewardSummary = backendTurnStage.lapRewardSummary;
  model.markSummary = backendTurnStage.markSummary;
  model.flipSummary = backendTurnStage.flipSummary;
  model.weatherSummary = backendTurnStage.weatherSummary;
  model.effectSummary = backendTurnStage.effectSummary;
  model.promptSummary = backendTurnStage.promptSummary;
  const defaultBeatLabel = labelForTurnStageCode(
    backendTurnStage.currentBeatEventCode,
    backendTurnStage.currentBeatRequestType,
    text
  );
  model.currentBeatLabel =
    backendTurnStage.currentBeatEventCode !== "prompt_active" && backendTurnStage.currentBeatLabel !== "-"
      ? backendTurnStage.currentBeatLabel
      : defaultBeatLabel;
  const beatSource =
    backendTurnStage.currentBeatSeq === null ? null : messageBySeq.get(backendTurnStage.currentBeatSeq) ?? null;
  const explicitBeatDetail =
    backendTurnStage.currentBeatEventCode !== "prompt_active" && backendTurnStage.currentBeatDetail !== "-"
      ? backendTurnStage.currentBeatDetail
      : "";
  model.currentBeatDetail = explicitBeatDetail
    ? explicitBeatDetail
    : backendTurnStage.currentBeatEventCode === "prompt_active"
      ? text.stream.promptWaiting(promptLabelForType(backendTurnStage.currentBeatRequestType, text.promptType))
      : beatSource
        ? pickMessageDetail(beatSource, text) || "-"
        : backendTurnStage.currentBeatEventCode === "game_end"
          ? text.stream.gameEndDefault
          : model.currentBeatDetail;
  if (backendTurnStage.currentBeatEventCode === "prompt_active" && backendTurnStage.promptRequestType !== "-") {
    model.promptSummary = text.stream.promptWaiting(
      promptLabelForType(backendTurnStage.promptRequestType, text.promptType)
    );
    model.currentBeatDetail = model.promptSummary;
  }
  if (backendTurnStage.currentBeatEventCode === "game_end") {
    model.promptSummary = "-";
  }
  model.latestActionLabel = model.currentBeatLabel;
  model.latestActionDetail = model.currentBeatDetail;
  if (backendTurnStage.progressCodes.length > 0) {
    model.progressTrail = backendTurnStage.progressCodes
      .map((code) => labelForTurnStageCode(code, backendTurnStage.promptRequestType, text))
      .filter((label) => label !== "-")
      .slice(-6);
  }
  return model;
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
  const backendTurnStage = selectBackendTurnStage(messages);
  if (!backendTurnStage || backendTurnStage.currentBeatEventCode === "game_end") {
    return null;
  }
  return backendTurnStage.actorPlayerId;
}

export function selectDerivedPlayers(
  messages: InboundMessage[],
  currentLocalPlayerId: StreamSelectorViewerIdentityInput = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): DerivedPlayerViewModel[] {
  void text;
  const backendPlayers = selectBackendDerivedPlayers(messages, currentLocalPlayerId);
  return backendPlayers ?? [];
}

export function selectActiveCharacterSlots(
  messages: InboundMessage[],
  currentLocalPlayerId: StreamSelectorViewerIdentityInput = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT,
  initialActiveByCard: Record<string, string> | Record<number, string> | null = null
): ActiveCharacterSlotViewModel[] {
  void text;
  void initialActiveByCard;
  const backendSlots = selectBackendActiveCharacterSlots(messages, currentLocalPlayerId);
  return backendSlots ?? [];
}

export function selectMarkTargetCharacterSlots(
  messages: InboundMessage[],
  actorCharacterName: string | null,
  currentLocalPlayerId: StreamSelectorViewerIdentityInput = null,
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): MarkTargetSlotViewModel[] {
  void actorCharacterName;
  void currentLocalPlayerId;
  void text;
  const backendCandidates = selectBackendMarkTargetCharacterSlots(messages);
  return backendCandidates ?? [];
}

export function selectMarkerOrderedPlayers(
  messages: InboundMessage[],
  currentLocalPlayerId: StreamSelectorViewerIdentityInput = null,
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

  return derivedPlayers;
}

export function selectLiveSnapshot(
  messages: InboundMessage[],
  text: StreamSelectorTextResources = DEFAULT_STREAM_SELECTOR_TEXT
): SnapshotViewModel | null {
  void text;
  const entry = findLatestSnapshotEntry(messages);
  if (!entry) {
    return null;
  }
  return {
    ...entry.snapshot,
    currentRoundOrder: [...entry.snapshot.currentRoundOrder],
    activeByCard: { ...entry.snapshot.activeByCard },
    players: entry.snapshot.players.map((player) => ({
      ...player,
      publicTricks: [...player.publicTricks],
    })),
    tiles: entry.snapshot.tiles.map((tile) => ({
      ...tile,
      pawnPlayerIds: [...tile.pawnPlayerIds],
    })),
  };
}

function manifestRecordFromPayload(payload: Record<string, unknown>): Record<string, unknown> | null {
  if (isRecord(payload["parameter_manifest"])) {
    return payload["parameter_manifest"];
  }
  const viewState = isRecord(payload["view_state"]) ? payload["view_state"] : null;
  if (isRecord(viewState?.["parameter_manifest"])) {
    return viewState["parameter_manifest"];
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

function normalizeEconomy(manifestRaw: Record<string, unknown>): ParameterManifestViewModel["economy"] {
  const raw = isRecord(manifestRaw["economy"]) ? manifestRaw["economy"] : null;
  if (!raw) {
    return {};
  }
  return {
    startingCash: typeof raw["starting_cash"] === "number" ? raw["starting_cash"] : undefined,
  };
}

function normalizeResources(manifestRaw: Record<string, unknown>): ParameterManifestViewModel["resources"] {
  const raw = isRecord(manifestRaw["resources"]) ? manifestRaw["resources"] : null;
  if (!raw) {
    return {};
  }
  return {
    startingShards: typeof raw["starting_shards"] === "number" ? raw["starting_shards"] : undefined,
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
    economy: normalizeEconomy(manifestRaw),
    resources: normalizeResources(manifestRaw),
  };
}

export function selectLatestManifest(messages: InboundMessage[]): ParameterManifestViewModel | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "view_commit") {
      continue;
    }
    const manifest = manifestFromPayload(message.payload);
    if (manifest) {
      return manifest;
    }
  }
  return null;
}
