import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { mergeSessionManifest } from "./domain/manifest/manifestRehydrate";
import {
  characterAbilityLabelsFromManifestLabels,
  tileKindLabelsFromManifestLabels,
} from "./domain/labels/manifestLabelCatalog";
import { promptLabelForType } from "./domain/labels/promptTypeCatalog";
import {
  selectActivePrompt,
  selectCurrentHandTrayCards,
  selectPromptInteractionState,
} from "./domain/selectors/promptSelectors";
import {
  type CurrentTurnRevealItem,
  selectActiveCharacterSlots,
  selectCoreActionFeed,
  selectCurrentActorPlayerId,
  selectCurrentRoundRevealItems,
  selectCurrentTurnRevealItems,
  selectDerivedPlayers,
  selectLastMove,
  selectLatestManifest,
  selectLiveSnapshot,
  selectMarkTargetCharacterSlots,
  selectMarkerOrderedPlayers,
  selectSituation,
  selectTimeline,
  selectTurnStage,
} from "./domain/selectors/streamSelectors";
import { BoardPanel } from "./features/board/BoardPanel";
import { GameEventOverlay } from "./features/board/GameEventOverlay";
import privateCharacterSealUrl from "./assets/private-character-seal.svg";
import {
  type GameEventEffectIntent,
  type GameEventEffectSource,
  useEventQueue,
} from "./features/board/useEventQueue";
import { LobbyView, type LobbySeatType } from "./features/lobby/LobbyView";
import { PlayerTrickPeek } from "./features/players/PlayerTrickPeek";
import { PromptOverlay } from "./features/prompt/PromptOverlay";
import { SpectatorTurnPanel } from "./features/stage/SpectatorTurnPanel";
import { CoreActionPanel } from "./features/theater/CoreActionPanel";
import { useGameStream } from "./hooks/useGameStream";
import { useI18n } from "./i18n/useI18n";
import type { InboundMessage } from "./core/contracts/stream";
import {
  createSession,
  createRoom,
  getRuntimeStatus,
  getRoom,
  getSession,
  getApiBaseUrl,
  joinSession,
  joinRoom,
  leaveRoom,
  listSessions,
  listRooms,
  normalizeServerBaseUrl,
  type SeatPublic,
  type PublicRoomResult,
  startSession,
  startRoom,
  setApiBaseUrl,
  setRoomReady,
  resumeRoom,
  type ParameterManifest,
  type PublicSessionResult,
  type RuntimeStatusResult,
} from "./infra/http/sessionApi";

type ViewRoute = "lobby" | "match";

const LOBBY_HASH = "#/lobby";
const MATCH_HASH = "#/match";
const SESSION_TOKEN_STORAGE_PREFIX = "mrn:sessionToken:";
const ROOM_SERVER_STORAGE_KEY = "mrn:roomServer";
const ROOM_NUMBER_STORAGE_KEY = "mrn:roomNumber";
const ROOM_TOKEN_STORAGE_KEY = "mrn:roomToken";
const MAX_SESSION_SEED = 2_147_483_647;
function parseRouteFromHash(hash: string): ViewRoute {
  if (hash.startsWith(MATCH_HASH)) {
    return "match";
  }
  return "lobby";
}

function parseHashState(hash: string): { route: ViewRoute; sessionId?: string; token?: string } {
  const route = parseRouteFromHash(hash);
  if (!hash.includes("?")) {
    return { route };
  }
  const query = hash.split("?")[1] ?? "";
  const params = new URLSearchParams(query);
  const sessionId = params.get("session") ?? undefined;
  const token = params.get("token") ?? undefined;
  return { route, sessionId, token };
}

function buildMatchHash(sessionId: string, token?: string): string {
  const params = new URLSearchParams();
  if (sessionId.trim()) {
    params.set("session", sessionId.trim());
  }
  if (token && token.trim()) {
    params.set("token", token.trim());
  }
  const query = params.toString();
  return query ? `${MATCH_HASH}?${query}` : MATCH_HASH;
}

function inferPlayerIdFromSessionToken(token: string | undefined): number | null {
  if (!token) {
    return null;
  }
  const match = /^session_p(\d+)_/.exec(token.trim());
  if (!match) {
    return null;
  }
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function tokenStorageKey(sessionId: string): string {
  return `${SESSION_TOKEN_STORAGE_PREFIX}${sessionId.trim()}`;
}

function generateSessionSeed(): number {
  if (typeof window !== "undefined" && window.crypto?.getRandomValues) {
    const values = new Uint32Array(1);
    window.crypto.getRandomValues(values);
    return (values[0] % MAX_SESSION_SEED) + 1;
  }
  return Math.floor(Math.random() * MAX_SESSION_SEED) + 1;
}

function resolveSessionSeed(seedInput: string): number {
  const normalized = seedInput.trim();
  if (normalized) {
    const parsed = Number(normalized);
    if (Number.isFinite(parsed)) {
      const truncated = Math.trunc(parsed);
      if (truncated > 0) {
        return truncated;
      }
    }
  }
  return generateSessionSeed();
}

function loadStoredSessionToken(sessionId: string): string | undefined {
  const normalized = sessionId.trim();
  if (!normalized) {
    return undefined;
  }
  const stored = window.sessionStorage.getItem(tokenStorageKey(normalized));
  return stored && stored.trim() ? stored : undefined;
}

function escapeDebugHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;");
}

type DebugTurnGroup = {
  key: string;
  label: string;
  messages: InboundMessage[];
};

function debugPayloadRecord(message: InboundMessage): Record<string, unknown> | null {
  return typeof message.payload === "object" && message.payload !== null
    ? (message.payload as Record<string, unknown>)
    : null;
}

function debugTurnLabel(message: InboundMessage): string | null {
  const payload = debugPayloadRecord(message);
  const roundIndex = payload?.["round_index"];
  const turnIndex = payload?.["turn_index"];
  if (typeof roundIndex === "number" && typeof turnIndex === "number") {
    return `Round ${roundIndex} / Turn ${turnIndex}`;
  }
  if (typeof turnIndex === "number") {
    return `Turn ${turnIndex}`;
  }
  return null;
}

function groupDebugMessagesByTurn(messages: InboundMessage[], locale: string): DebugTurnGroup[] {
  const fallbackLabel = locale === "ko" ? "턴 정보 없음" : "No turn metadata";
  const groups: DebugTurnGroup[] = [];
  let current: DebugTurnGroup | null = null;
  const sortedMessages = [...messages].sort((left, right) => {
    const seqDiff = left.seq - right.seq;
    if (seqDiff !== 0) {
      return seqDiff;
    }
    return (left.server_time_ms ?? 0) - (right.server_time_ms ?? 0);
  });

  for (const message of sortedMessages) {
    const label = debugTurnLabel(message);
    const payload = debugPayloadRecord(message);
    const eventType = typeof payload?.["event_type"] === "string" ? payload["event_type"] : "";
    const startsTurn = eventType === "turn_start" || eventType === "turn_context_started";
    if (!current || (label && (startsTurn || current.label !== label))) {
      const groupLabel: string = label ?? fallbackLabel;
      current = {
        key: `${groups.length}:${groupLabel}:${message.seq}`,
        label: groupLabel,
        messages: [],
      };
      groups.push(current);
    }
    current.messages.push(message);
  }

  return groups;
}

function saveStoredSessionToken(sessionId: string, token: string | undefined): void {
  const normalized = sessionId.trim();
  if (!normalized) {
    return;
  }
  if (token && token.trim()) {
    window.sessionStorage.setItem(tokenStorageKey(normalized), token.trim());
    return;
  }
  window.sessionStorage.removeItem(tokenStorageKey(normalized));
}

function loadStoredRoomServer(): string {
  const stored = window.sessionStorage.getItem(ROOM_SERVER_STORAGE_KEY);
  return normalizeServerBaseUrl(stored || "http://127.0.0.1:9090");
}

function saveStoredRoomServer(serverBaseUrl: string): void {
  window.sessionStorage.setItem(ROOM_SERVER_STORAGE_KEY, normalizeServerBaseUrl(serverBaseUrl));
}

function loadStoredRoomNumber(): number | null {
  const raw = window.sessionStorage.getItem(ROOM_NUMBER_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function loadStoredRoomToken(): string | null {
  const raw = window.sessionStorage.getItem(ROOM_TOKEN_STORAGE_KEY);
  return raw && raw.trim() ? raw.trim() : null;
}

function saveStoredRoomMembership(roomNo: number | null, token: string | null, serverBaseUrl: string): void {
  saveStoredRoomServer(serverBaseUrl);
  if (roomNo && token) {
    window.sessionStorage.setItem(ROOM_NUMBER_STORAGE_KEY, String(roomNo));
    window.sessionStorage.setItem(ROOM_TOKEN_STORAGE_KEY, token);
    return;
  }
  window.sessionStorage.removeItem(ROOM_NUMBER_STORAGE_KEY);
  window.sessionStorage.removeItem(ROOM_TOKEN_STORAGE_KEY);
}

function shouldHideCharacterForPrompt(requestType: string): boolean {
  return requestType === "draft_card" || requestType === "final_character" || requestType === "final_character_choice";
}

function hasReadableValue(value: string | null | undefined): boolean {
  return typeof value === "string" && value.trim() !== "" && value.trim() !== "-";
}

function compactEventDetail(label: string, detail: string | null | undefined): string {
  if (!hasReadableValue(detail)) {
    return "";
  }
  const rawDetail = detail ?? "";
  const normalizedLabel = label.trim().toLowerCase();
  const normalizedDetail = rawDetail.trim();
  if (normalizedDetail.toLowerCase() === normalizedLabel) {
    return "";
  }
  for (const separator of ["/", ":", "-", "–", "—"]) {
    const prefix = `${label.trim()} ${separator}`;
    if (normalizedDetail.toLowerCase().startsWith(prefix.toLowerCase())) {
      return normalizedDetail.slice(prefix.length).trim();
    }
  }
  return normalizedDetail;
}

function playerColor(playerId: number): string {
  const palette = ["#f97316", "#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#facc15"];
  return palette[(Math.max(1, playerId) - 1) % palette.length];
}

function isKoreanLocale(locale: string): boolean {
  return locale.toLowerCase().startsWith("ko");
}

function stageInProgressLabel(label: string, locale: string): string {
  if (!hasReadableValue(label)) {
    return "-";
  }
  return isKoreanLocale(locale) ? `${label} 중...` : `${label} in progress`;
}

function waitingPlayerLabel(locale: string): string {
  return isKoreanLocale(locale) ? "대기 중" : "Waiting";
}

function localPlayerBadgeLabel(locale: string): string {
  return isKoreanLocale(locale) ? "나" : "Me";
}

function currentTurnBadgeLabel(locale: string): string {
  return isKoreanLocale(locale) ? "현재 차례" : "Current turn";
}

function eventToneIcon(tone: CurrentTurnRevealItem["tone"]): string {
  switch (tone) {
    case "move":
      return "→";
    case "economy":
      return "¤";
    case "effect":
      return "✦";
  }
}

function eventToneLabel(tone: CurrentTurnRevealItem["tone"], locale: string): string {
  const ko = isKoreanLocale(locale);
  switch (tone) {
    case "move":
      return ko ? "이동" : "Move";
    case "economy":
      return ko ? "경제" : "Economy";
    case "effect":
      return ko ? "효과" : "Effect";
  }
}

function eventToneForEventCode(eventCode: string): CurrentTurnRevealItem["tone"] {
  if (eventCode === "tile_purchased" || eventCode === "rent_paid" || eventCode === "lap_reward_chosen") {
    return "economy";
  }
  if (eventCode === "dice_roll" || eventCode === "player_move") {
    return "move";
  }
  return "effect";
}

function rentOverlayKindForPlayer(
  detail: string,
  playerId: number | null
): "rent_pay" | "rent_receive" | "rent_observe" {
  if (playerId === null) {
    return "rent_observe";
  }
  const playerToken = `P${playerId}`;
  const escapedToken = playerToken.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const payerPattern = new RegExp(`\\b${escapedToken}\\b\\s*(?:->|paid\\b)`);
  const receiverPattern = new RegExp(`(?:->|paid\\s+P\\d+\\s+to\\s+)\\s*\\b${escapedToken}\\b|\\bpaid\\s+\\b${escapedToken}\\b`);
  if (payerPattern.test(detail)) {
    return "rent_pay";
  }
  if (receiverPattern.test(detail)) {
    return "rent_receive";
  }
  return "rent_observe";
}

type EventOverlayEffectKind =
  | "rent_pay"
  | "rent_receive"
  | "rent_observe"
  | "purchase"
  | "lap_complete"
  | "fortune"
  | "trick"
  | "weather"
  | "mark_success"
  | "bankruptcy"
  | "game_end"
  | "dice"
  | "move"
  | "economy";

function gameEventTextMatches(text: string, pattern: RegExp): boolean {
  return pattern.test(text.toLowerCase());
}

function economyEffectIntentForText(
  text: string,
  fallback: GameEventEffectIntent = "neutral"
): GameEventEffectIntent {
  if (
    gameEventTextMatches(
      text,
      /벌금|지불|냈|차감|손실|잃|파산|pay|paid|penalty|fine|lose|lost|bankrupt|no lap cash/
    )
  ) {
    return "loss";
  }
  if (
    gameEventTextMatches(
      text,
      /보상|획득|얻|받|수입|현금 \+|조각 \+|승점 \+|reward|gain|receive|received|cash \+|shard \+|coin \+/
    )
  ) {
    return "gain";
  }
  if (gameEventTextMatches(text, /강화|증가|상승|통행료|렌트|배|boost|increase|double|rent/)) {
    return "boost";
  }
  return fallback;
}

function isWeatherEnhancedRent(weatherName: string, weatherEffect: string): boolean {
  if (!hasReadableValue(weatherName) && !hasReadableValue(weatherEffect)) {
    return false;
  }
  const weatherText = `${weatherName} ${weatherEffect}`;
  return gameEventTextMatches(weatherText, /날씨|통행료|렌트|강화|증가|상승|배|weather|rent|toll|boost|increase|double/);
}

function weatherEffectIntent(weatherName: string, weatherEffect: string): GameEventEffectIntent {
  const weatherText = `${weatherName} ${weatherEffect}`;
  return economyEffectIntentForText(weatherText, gameEventTextMatches(weatherText, /weather|날씨/) ? "boost" : "neutral");
}

function isCharacterPassiveEffectText(text: string): boolean {
  return gameEventTextMatches(
    text,
    /객주|중매꾼|캐릭터|인물|능력|패시브|추가 보상|추가 구매|보너스|innkeeper|matchmaker|character|passive|ability|bonus/
  );
}

function isMatchmakerPurchaseText(text: string): boolean {
  return gameEventTextMatches(text, /중매꾼|matchmaker|matchmaker_adjacent|adjacent extra|추가 구매|인접 토지/);
}

function eventEffectForReveal(args: {
  eventCode: string;
  kind: EventOverlayEffectKind;
  label: string;
  detail: string;
  weatherName: string;
  weatherEffect: string;
}): {
  effectIntent: GameEventEffectIntent;
  effectSource: GameEventEffectSource;
  effectEnhanced: boolean;
} {
  const text = `${args.label} ${args.detail}`;
  if (args.eventCode === "weather_reveal") {
    return {
      effectIntent: weatherEffectIntent(args.weatherName || args.label, args.weatherEffect || args.detail),
      effectSource: "weather",
      effectEnhanced: true,
    };
  }
  if (args.eventCode === "rent_paid") {
    const enhancedByWeather = isWeatherEnhancedRent(args.weatherName, args.weatherEffect);
    return {
      effectIntent: enhancedByWeather
        ? "boost"
        : args.kind === "rent_receive"
          ? "gain"
          : args.kind === "rent_pay"
            ? "loss"
            : economyEffectIntentForText(text, "neutral"),
      effectSource: enhancedByWeather ? "weather" : "economy",
      effectEnhanced: enhancedByWeather,
    };
  }
  if (args.eventCode === "fortune_drawn" || args.eventCode === "fortune_resolved") {
    return {
      effectIntent: economyEffectIntentForText(text, "mystic"),
      effectSource: "fortune",
      effectEnhanced: args.eventCode === "fortune_resolved",
    };
  }
  if (args.eventCode === "trick_used") {
    return {
      effectIntent: economyEffectIntentForText(text, "mystic"),
      effectSource: "trick",
      effectEnhanced: true,
    };
  }
  if (args.eventCode === "lap_reward_chosen") {
    return {
      effectIntent: "gain",
      effectSource: isCharacterPassiveEffectText(text) ? "character" : "economy",
      effectEnhanced: true,
    };
  }
  if (args.eventCode === "tile_purchased") {
    if (isMatchmakerPurchaseText(text)) {
      return { effectIntent: "boost", effectSource: "character", effectEnhanced: true };
    }
    return { effectIntent: "loss", effectSource: "economy", effectEnhanced: false };
  }
  if (args.eventCode === "mark_resolved" || args.eventCode === "mark_queued") {
    return { effectIntent: "mystic", effectSource: "mark", effectEnhanced: true };
  }
  if (args.eventCode === "bankruptcy") {
    return { effectIntent: "loss", effectSource: "economy", effectEnhanced: true };
  }
  return { effectIntent: "neutral", effectSource: "system", effectEnhanced: false };
}

function eventOverlayKindForFeedItem(eventCode: string): EventOverlayEffectKind {
  switch (eventCode) {
    case "weather_reveal":
      return "weather";
    case "dice_roll":
      return "dice";
    case "player_move":
      return "move";
    case "tile_purchased":
      return "purchase";
    case "rent_paid":
      return "rent_observe";
    case "lap_reward_chosen":
      return "lap_complete";
    case "fortune_drawn":
    case "fortune_resolved":
      return "fortune";
    case "trick_used":
      return "trick";
    case "mark_resolved":
    case "mark_queued":
      return "mark_success";
    case "bankruptcy":
      return "bankruptcy";
    case "game_end":
      return "game_end";
    default:
      return "economy";
  }
}

function eventEffectAttributionLabel(
  effect: ReturnType<typeof eventEffectForReveal>,
  text: string,
  locale: string
): string | null {
  const ko = isKoreanLocale(locale);
  switch (effect.effectSource) {
    case "weather":
      if (effect.effectIntent === "loss") return ko ? "날씨 페널티" : "Weather penalty";
      if (effect.effectIntent === "gain") return ko ? "날씨 보상" : "Weather reward";
      return ko ? "날씨 강화" : "Weather boost";
    case "fortune":
      if (effect.effectIntent === "loss") return ko ? "운수 손실" : "Fortune loss";
      if (effect.effectIntent === "gain") return ko ? "운수 보상" : "Fortune reward";
      if (effect.effectIntent === "boost") return ko ? "운수 강화" : "Fortune boost";
      return ko ? "운수 효과" : "Fortune effect";
    case "trick":
      if (effect.effectIntent === "loss") return ko ? "잔꾀 손실" : "Trick loss";
      if (effect.effectIntent === "gain") return ko ? "잔꾀 보상" : "Trick reward";
      return ko ? "잔꾀 효과" : "Trick effect";
    case "character":
      if (/중매꾼|matchmaker|추가 구매|인접 토지/i.test(text)) {
        return ko ? "중매꾼 추가 구매" : "Matchmaker purchase";
      }
      if (/객주|innkeeper/i.test(text)) {
        return ko ? "객주 보너스" : "Innkeeper bonus";
      }
      return ko ? "캐릭터 보너스" : "Character bonus";
    case "mark":
      if (/박수|baksu/i.test(text)) {
        return ko ? "박수 지목 성공" : "Baksu mark";
      }
      if (/만신|manshin/i.test(text)) {
        return ko ? "만신 지목 성공" : "Manshin mark";
      }
      return ko ? "지목 효과" : "Mark effect";
    default:
      return null;
  }
}

function eventEffectForFeedItem(
  item: CurrentTurnRevealItem,
  weatherName: string,
  weatherEffect: string
): ReturnType<typeof eventEffectForReveal> {
  return eventEffectForReveal({
    eventCode: item.eventCode,
    kind: eventOverlayKindForFeedItem(item.eventCode),
    label: item.label,
    detail: item.detail,
    weatherName,
    weatherEffect,
  });
}

const PROMPT_EFFECT_CONTEXT_EVENT_CODES = new Set([
  "weather_reveal",
  "fortune_drawn",
  "fortune_resolved",
  "trick_used",
  "rent_paid",
  "tile_purchased",
  "lap_reward_chosen",
  "mark_resolved",
  "mark_queued",
  "mark_target_none",
  "mark_target_missing",
  "mark_blocked",
  "marker_flip",
  "bankruptcy",
]);

function isPromptEffectContextEvent(item: CurrentTurnRevealItem): boolean {
  return PROMPT_EFFECT_CONTEXT_EVENT_CODES.has(item.eventCode);
}

function appNumberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function appStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function appRecordOrNull(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function effectCharacterFromPayload(payload: Record<string, unknown> | null, detail: string): string | undefined {
  const resolution = appRecordOrNull(payload?.["resolution"]);
  const actorName =
    appStringOrNull(payload?.["actor_name"]) ??
    appStringOrNull(resolution?.["actor_name"]) ??
    appStringOrNull(payload?.["character"]) ??
    appStringOrNull(payload?.["card_name"]);
  const effectType = appStringOrNull(payload?.["effect_type"]) ?? appStringOrNull(resolution?.["type"]);
  const purchaseSource = appStringOrNull(payload?.["purchase_source"]) ?? appStringOrNull(payload?.["source"]);
  const text = `${actorName ?? ""} ${effectType ?? ""} ${purchaseSource ?? ""} ${detail}`;
  if (/baksu|박수/i.test(text)) return "박수";
  if (/manshin|만신/i.test(text)) return "만신";
  if (/matchmaker|matchmaker_adjacent|중매꾼|인접 토지|추가 구매/i.test(text)) return "중매꾼";
  return actorName ?? undefined;
}

function diceOverlayValues(payload: Record<string, unknown>): { values: number[]; total: number | null } {
  const rawValues = Array.isArray(payload["dice_values"])
    ? payload["dice_values"]
    : Array.isArray(payload["dice"])
      ? payload["dice"]
      : [];
  const values = rawValues.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const total =
    appNumberOrNull(payload["dice_total"]) ??
    appNumberOrNull(payload["total_move"]) ??
    appNumberOrNull(payload["total"]) ??
    (values.length > 0 ? values.reduce((sum, value) => sum + value, 0) : null);
  return { values: values.length > 0 ? values : total !== null ? [total] : [], total };
}

function movementOverlayDetail(payload: Record<string, unknown>, locale: string): string | null {
  const playerId = appNumberOrNull(payload["acting_player_id"] ?? payload["player_id"]);
  const from =
    appNumberOrNull(payload["from_tile_index"]) ??
    appNumberOrNull(payload["from_tile"]) ??
    appNumberOrNull(payload["from_pos"]) ??
    appNumberOrNull(payload["start_pos"]);
  const to =
    appNumberOrNull(payload["to_tile_index"]) ??
    appNumberOrNull(payload["to_tile"]) ??
    appNumberOrNull(payload["to_pos"]) ??
    appNumberOrNull(payload["end_pos"]) ??
    appNumberOrNull(payload["target_pos"]) ??
    appNumberOrNull(payload["position"]);
  if (from === null || to === null || from === to) {
    return null;
  }
  const actor = playerId === null ? (locale === "ko" ? "말" : "Pawn") : `P${playerId}`;
  return locale === "ko"
    ? `${actor} ${from + 1}번 타일에서 ${to + 1}번 타일로 이동`
    : `${actor} moved from tile ${from + 1} to tile ${to + 1}`;
}

function seatTypeBadgeLabel(seatType: SeatPublic["seat_type"] | null | undefined, locale: string): string | null {
  if (seatType === "human") {
    return isKoreanLocale(locale) ? "사람" : "Human";
  }
  if (seatType === "ai") {
    return "AI";
  }
  return null;
}

function sessionInfoToggleLabel(locale: string, expanded: boolean): string {
  if (isKoreanLocale(locale)) {
    return expanded ? "정보 감추기" : "정보 펼치기";
  }
  return expanded ? "Hide info" : "Show info";
}

function promptProgressText(requestType: string, promptLabel: string | null, locale: string): string {
  const ko = isKoreanLocale(locale);
  switch (requestType) {
    case "draft_card":
      return ko ? "인물 뽑기 중..." : "Drafting characters...";
    case "final_character":
    case "final_character_choice":
      return ko ? "최종 인물 고르는 중..." : "Choosing final character...";
    case "active_flip":
      return ko ? "카드 뒤집는 중..." : "Flipping cards...";
    case "hidden_trick_card":
      return ko ? "히든 잔꾀 고르는 중..." : "Choosing hidden trick...";
    case "movement":
      return ko ? "이동값 고르는 중..." : "Choosing movement...";
    case "purchase_tile":
      return ko ? "땅 사기 결정 중..." : "Deciding tile purchase...";
    case "trick_to_use":
      return ko ? "잔꾀 고르는 중..." : "Choosing trick...";
    case "mark_target":
      return ko ? "지목 대상 고르는 중..." : "Choosing mark target...";
    case "burden_exchange":
      return ko ? "짐 카드 정리 중..." : "Resolving burden cards...";
    case "coin_placement":
      return ko ? "승점 놓는 중..." : "Placing score coins...";
    default:
      return promptLabel && promptLabel !== "-"
        ? stageInProgressLabel(promptLabel, locale)
        : ko
          ? "선택 진행 중..."
          : "Decision in progress...";
  }
}

export function App() {
  const { app, board: boardText, eventLabel, promptType, stream: streamText, turnStage: turnStageText, locale, setLocale } = useI18n();
  const [route, setRoute] = useState<ViewRoute>(() => parseHashState(window.location.hash).route);
  const [sessionInput, setSessionInput] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [token, setToken] = useState<string | undefined>(undefined);
  const [serverBaseInput, setServerBaseInput] = useState(() => loadStoredRoomServer());
  const [serverBaseUrl, setServerBaseUrl] = useState(() => loadStoredRoomServer());
  const [serverConnected, setServerConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeStatusResult["runtime"]>({ status: "-" });
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [seatTypes, setSeatTypes] = useState<LobbySeatType[]>(["human", "ai", "ai", "ai"]);
  const [seatCountInput, setSeatCountInput] = useState("4");
  const [aiProfile, setAiProfile] = useState("balanced");
  const [seedInput, setSeedInput] = useState("");
  const [roomTitleInput, setRoomTitleInput] = useState("MRN Room");
  const [hostSeatInput, setHostSeatInput] = useState("1");
  const [hostTokenInput, setHostTokenInput] = useState("");
  const [lastJoinTokens, setLastJoinTokens] = useState<Record<string, string>>({});
  const [joinSeatInput, setJoinSeatInput] = useState("1");
  const [joinTokenInput, setJoinTokenInput] = useState("");
  const [displayNameInput, setDisplayNameInput] = useState("Player");
  const [sessions, setSessions] = useState<PublicSessionResult[]>([]);
  const [rooms, setRooms] = useState<PublicRoomResult[]>([]);
  const [activeRoomNo, setActiveRoomNo] = useState<number | null>(() => loadStoredRoomNumber());
  const [roomMemberToken, setRoomMemberToken] = useState<string | null>(() => loadStoredRoomToken());
  const [activeRoom, setActiveRoom] = useState<PublicRoomResult | null>(null);
  const [activeRoomSeat, setActiveRoomSeat] = useState<number | null>(null);
  const [sessionManifest, setSessionManifest] = useState<ParameterManifest | null>(null);
  const [sessionInitialActiveByCard, setSessionInitialActiveByCard] = useState<Record<string, string> | null>(null);
  const [sessionSeats, setSessionSeats] = useState<SeatPublic[] | null>(null);
  const [localPlayerId, setLocalPlayerId] = useState<number | null>(null);
  const inferredPlayerId = inferPlayerIdFromSessionToken(token);
  const effectivePlayerId = localPlayerId ?? inferredPlayerId;

  const [compactDensity, setCompactDensity] = useState(false);
  const [sessionInfoExpanded, setSessionInfoExpanded] = useState(false);
  const [weatherExpanded, setWeatherExpanded] = useState(false);
  const [showRawMessages, setShowRawMessages] = useState(false);
  const [publicEventFeedOpen, setPublicEventFeedOpen] = useState(false);
  const [promptCollapsed, setPromptCollapsed] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptRequestId, setPromptRequestId] = useState("");
  const [promptExpiresAtMs, setPromptExpiresAtMs] = useState<number | null>(null);
  const [promptFeedback, setPromptFeedback] = useState("");
  const [burdenExchangeQueuedDeckIndexes, setBurdenExchangeQueuedDeckIndexes] = useState<number[]>([]);
  const [burdenExchangeQueuedPlayerId, setBurdenExchangeQueuedPlayerId] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [turnBanner, setTurnBanner] = useState<{
    seq: number;
    text: string;
    detail: string;
    variant: "turn" | "interrupt";
  } | null>(null);
  const debugWindowRef = useRef<Window | null>(null);
  const lastTurnBannerSeqRef = useRef<number>(0);
  const lastRevealBannerSeqRef = useRef<number>(0);
  const promptSubmitRequestIdRef = useRef<string | null>(null);

  const stream = useGameStream({ sessionId, token, baseUrl: serverBaseUrl });
  const debugMessages = stream.debugMessages;
  const eventQueue = useEventQueue();
  const selectorText = useMemo(
    () => ({
      eventLabel,
      promptType,
      stream: streamText,
      turnStage: turnStageText,
    }),
    [eventLabel, promptType, streamText, turnStageText]
  );

  const timeline = selectTimeline(stream.messages, compactDensity ? 24 : 40, selectorText);
  const coreActionFeed = selectCoreActionFeed(stream.messages, effectivePlayerId, compactDensity ? 10 : 14, selectorText);
  const latestCoreAction = coreActionFeed[0] ?? null;
  const situation = selectSituation(stream.messages, selectorText);
  const turnStage = selectTurnStage(stream.messages, selectorText);
  const snapshot = selectLiveSnapshot(stream.messages, selectorText);
  const derivedPlayers = selectDerivedPlayers(stream.messages, effectivePlayerId, selectorText);
  const markerOrderedPlayers = selectMarkerOrderedPlayers(stream.messages, effectivePlayerId, selectorText);
  const lastMove = selectLastMove(stream.messages);
  const latestManifest = selectLatestManifest(stream.messages);
  const currentTurnRevealItems = useMemo(
    () => selectCurrentTurnRevealItems(stream.messages, 6, selectorText),
    [stream.messages, selectorText]
  );
  const currentRoundRevealItems = useMemo(
    () => selectCurrentRoundRevealItems(stream.messages, 24, selectorText),
    [stream.messages, selectorText]
  );
  const latestCurrentTurnReveal = currentTurnRevealItems[currentTurnRevealItems.length - 1] ?? null;
  const latestCurrentRoundReveal = currentRoundRevealItems[currentRoundRevealItems.length - 1] ?? null;
  const fallbackRevealSpotlight = useMemo(() => {
    if (currentTurnRevealItems.length > 0) {
      return null;
    }
    const candidate = coreActionFeed.find((item) =>
      [
        "tile_purchased",
        "rent_paid",
        "lap_reward_chosen",
        "fortune_drawn",
        "fortune_resolved",
        "landing_resolved",
        "trick_used",
        "mark_resolved",
        "marker_flip",
        "marker_transferred",
      ].includes(item.eventCode)
    );
    if (!candidate) {
      return null;
    }
    const detail = hasReadableValue(candidate.detail) ? candidate.detail : candidate.label;
    if (!hasReadableValue(detail)) {
      return null;
    }
    return {
      seq: candidate.seq,
      eventCode: candidate.eventCode,
      label: candidate.label,
      detail,
      tone: eventToneForEventCode(candidate.eventCode),
      focusTileIndex: null,
      isInterrupt: false,
    } satisfies CurrentTurnRevealItem;
  }, [coreActionFeed, currentTurnRevealItems]);
  const eventFeedSpotlightItem = latestCurrentRoundReveal ?? latestCurrentTurnReveal ?? fallbackRevealSpotlight;
  const eventFeedHistoryItems = currentRoundRevealItems.slice(0, -1);

  const currentActorId =
    turnStage.currentBeatEventCode === "game_end" ? null : selectCurrentActorPlayerId(stream.messages);
  const markerOwnerPlayerId = snapshot?.markerOwnerPlayerId ?? null;
  const isMyTurn = currentActorId !== null && effectivePlayerId !== null && currentActorId === effectivePlayerId;
  const actorLabel = currentActorId !== null ? `P${currentActorId}` : turnStage.actor;
  const actorCharacterText =
    shouldHideCharacterForPrompt(turnStage.promptRequestType) || turnStage.actorPlayerId !== currentActorId
      ? "-"
      : turnStage.character;
  const currentActorText =
    actorLabel !== "-"
      ? actorCharacterText && actorCharacterText !== "-"
        ? `${actorLabel} (${actorCharacterText})`
        : actorLabel
      : "-";
  const boardTurnOverlayDetail = hasReadableValue(turnStage.diceSummary)
    ? turnStage.diceSummary
    : hasReadableValue(turnStage.moveSummary)
      ? turnStage.moveSummary
      : hasReadableValue(turnStage.currentBeatDetail)
        ? turnStage.currentBeatDetail
        : hasReadableValue(turnStage.currentBeatLabel)
          ? turnStage.currentBeatLabel
          : "";
  const weatherHeadline =
    hasReadableValue(situation.weather)
      ? situation.weather
      : hasReadableValue(turnStage.weatherName)
        ? turnStage.weatherName
      : locale === "ko"
        ? "날씨 대기 중"
        : "Weather pending";
  const weatherDetail =
    hasReadableValue(situation.weatherEffect) && situation.weatherEffect !== weatherHeadline
      ? situation.weatherEffect
      : hasReadableValue(turnStage.weatherEffect) && turnStage.weatherEffect !== weatherHeadline
        ? turnStage.weatherEffect
        : "";
  const weatherHudPills: string[] = [];
  const manifestHash = typeof sessionManifest?.manifest_hash === "string" ? sessionManifest.manifest_hash : "";
  const manifestStartingCash =
    typeof sessionManifest?.economy?.starting_cash === "number" ? String(sessionManifest.economy.starting_cash) : "";
  const manifestStartingShards =
    typeof sessionManifest?.resources?.starting_shards === "number" ? String(sessionManifest.resources.starting_shards) : "";
  const manifestDiceValues =
    Array.isArray(sessionManifest?.dice?.values) && sessionManifest.dice.values.length > 0
      ? sessionManifest.dice.values.join(",")
      : "";
  const manifestSeatAllowed =
    Array.isArray(sessionManifest?.seats?.allowed) && sessionManifest.seats.allowed.length > 0
      ? sessionManifest.seats.allowed.join(",")
      : "";
  const manifestTileCount =
    typeof sessionManifest?.board?.tile_count === "number"
      ? String(sessionManifest.board.tile_count)
      : Array.isArray(sessionManifest?.board?.tiles)
        ? String(sessionManifest.board.tiles.length)
        : "";
  const manifestTopology =
    typeof sessionManifest?.board?.topology === "string" && sessionManifest.board.topology.trim()
      ? sessionManifest.board.topology
      : "";

  const activePrompt = selectActivePrompt(stream.messages);
  const activePromptLabel = activePrompt ? promptLabelForType(activePrompt.requestType) : null;
  const canActOnPrompt = Boolean(activePrompt && token && effectivePlayerId !== null && activePrompt.playerId === effectivePlayerId);
  const actionablePrompt = canActOnPrompt ? activePrompt : null;
  const actionablePromptBehavior = actionablePrompt?.behavior ?? null;
  const suppressQueuedBurdenPrompt = Boolean(
    actionablePrompt &&
      actionablePromptBehavior?.normalizedRequestType === "burden_exchange_batch" &&
      actionablePromptBehavior.singleSurface &&
      burdenExchangeQueuedPlayerId !== null &&
      actionablePrompt.playerId === burdenExchangeQueuedPlayerId
  );
  const visibleActionablePrompt = suppressQueuedBurdenPrompt ? null : actionablePrompt;
  const passivePrompt = activePrompt && !canActOnPrompt ? activePrompt : null;
  const promptInteraction = useMemo(
    () =>
      selectPromptInteractionState({
        messages: stream.messages,
        activePrompt: actionablePrompt,
        trackedRequestId: promptRequestId,
        submitting: promptBusy,
        expiresAtMs: promptExpiresAtMs,
        nowMs,
        streamStatus: stream.status,
        manualFeedbackMessage: promptFeedback,
      }),
    [actionablePrompt, nowMs, promptBusy, promptExpiresAtMs, promptFeedback, promptRequestId, stream.messages, stream.status]
  );
  const promptSecondsLeft = promptInteraction.secondsLeft;
  const promptUiBusy = promptInteraction.busy;
  const promptFeedbackMessage = useMemo(() => {
    switch (promptInteraction.feedback.kind) {
      case "manual":
        return promptInteraction.feedback.message;
      case "rejected":
        return app.errors.promptRejected(promptInteraction.feedback.reason);
      case "stale":
        return app.errors.promptStale(promptInteraction.feedback.reason);
      case "timed_out":
        return app.errors.promptTimedOut;
      case "connection_lost":
        return app.errors.promptConnectionLost;
      default:
        return "";
    }
  }, [app.errors, promptInteraction.feedback]);
  const waitingForMyPrompt = isMyTurn && !actionablePrompt && !promptUiBusy;

  const playersById = useMemo(() => {
    const map = new Map<number, (typeof derivedPlayers)[number]>();
    for (const player of derivedPlayers) {
      map.set(player.playerId, player);
    }
    return map;
  }, [derivedPlayers]);

  const orderedSeatEntries = useMemo(() => {
    const derivedPlayerIds = new Set(derivedPlayers.map((player) => player.playerId));
    const orderedPlayerIds = markerOrderedPlayers.map((player) => player.playerId);
    const orderRank = new Map(orderedPlayerIds.map((playerId, index) => [playerId, index] as const));
    const sessionSeatEntries = (sessionSeats ?? [])
      .slice()
      .sort((left, right) => left.seat - right.seat)
      .map((seat) => ({
        seat: seat.seat,
        playerId: seat.player_id ?? (derivedPlayerIds.has(seat.seat) ? seat.seat : null),
        seatType: seat.seat_type,
        connected: seat.connected ?? null,
      }));

    if (sessionSeatEntries.length > 0) {
      return sessionSeatEntries.slice().sort((left, right) => {
        const leftRank = left.playerId !== null ? orderRank.get(left.playerId) : undefined;
        const rightRank = right.playerId !== null ? orderRank.get(right.playerId) : undefined;
        if (leftRank !== undefined || rightRank !== undefined) {
          return (leftRank ?? Number.MAX_SAFE_INTEGER) - (rightRank ?? Number.MAX_SAFE_INTEGER);
        }
        return left.seat - right.seat;
      });
    }

    const fallbackPlayers = markerOrderedPlayers.length > 0
      ? markerOrderedPlayers
      : derivedPlayers.slice().sort((left, right) => left.playerId - right.playerId);
    return fallbackPlayers
      .map((player) => ({
        seat: player.playerId,
        playerId: player.playerId,
        seatType: null,
        connected: true,
      }));
  }, [derivedPlayers, markerOrderedPlayers, sessionSeats]);

  const joinSeatOptions = (sessionManifest?.seats?.allowed ?? [])
    .slice()
    .sort((a, b) => a - b)
    .map((seat) => String(seat));
  const manifestTiles = (sessionManifest?.board?.tiles ?? []).map((tile) => ({
    tileIndex: tile.tile_index,
    tileKind: tile.tile_kind,
    zoneColor: tile.zone_color ?? "",
    purchaseCost: tile.purchase_cost ?? null,
    rentCost: tile.rent_cost ?? null,
    scoreCoinCount: 0,
    ownerPlayerId: null,
    pawnPlayerIds: [],
  }));
  const boardTopology = sessionManifest?.board?.topology ?? "ring";
  const tileKindLabels = tileKindLabelsFromManifestLabels(sessionManifest?.labels);
  const characterAbilityLabels = characterAbilityLabelsFromManifestLabels(sessionManifest?.labels);
  const currentPromptLabel = actionablePrompt ? promptLabelForType(actionablePrompt.requestType) : null;
  const visiblePrompt = activePrompt ?? null;
  const visiblePromptLabel = activePromptLabel;
  const boardTurnOverlay =
    turnStage.currentBeatEventCode === "game_end"
      ? {
          text: turnStage.currentBeatLabel,
          detail: hasReadableValue(turnStage.currentBeatDetail) ? turnStage.currentBeatDetail : turnStage.currentBeatLabel,
        }
      : visiblePrompt && visiblePrompt.requestType
      ? {
          text: promptProgressText(visiblePrompt.requestType, visiblePromptLabel, locale),
          detail: visiblePromptLabel && visiblePromptLabel !== "-" ? visiblePromptLabel : boardTurnOverlayDetail,
        }
      : currentActorId !== null && currentActorText !== "-"
        ? {
            text: app.turnBanner(currentActorText),
            detail: boardTurnOverlayDetail,
          }
        : null;
  const gameEndSpotlight =
    turnStage.currentBeatEventCode === "game_end"
      ? {
          seq: Number.MAX_SAFE_INTEGER,
          eventCode: "game_end",
          label: turnStage.currentBeatLabel,
          detail: hasReadableValue(turnStage.currentBeatDetail) ? turnStage.currentBeatDetail : turnStage.currentBeatLabel,
          tone: eventToneForEventCode("game_end"),
          focusTileIndex: null,
          isInterrupt: true,
        }
      : null;
  const effectiveEventFeedSpotlightItem = gameEndSpotlight ?? eventFeedSpotlightItem;
  const effectiveTurnBanner =
    turnBanner?.variant === "turn" && (visiblePrompt || passivePrompt || waitingForMyPrompt || isMyTurn)
      ? null
      : turnBanner && turnBanner.variant === "turn" && boardTurnOverlay
        ? {
            ...turnBanner,
            text: boardTurnOverlay.text,
            detail:
              boardTurnOverlay.detail && boardTurnOverlay.detail !== "-" ? boardTurnOverlay.detail : turnBanner.detail,
          }
        : turnBanner;
  const myTurnCelebration = turnBanner?.variant === "turn" && isMyTurn ? turnBanner : null;
  const myTurnCelebrationTitle = locale === "ko" ? "당신의 턴!" : "Your turn!";
  const myTurnCelebrationDetail =
    myTurnCelebration?.detail && myTurnCelebration.detail !== "-"
      ? myTurnCelebration.detail
      : locale === "ko"
        ? "선택지를 준비하세요"
        : "Get ready to choose";
  const overlayHandCards = useMemo(
    () => selectCurrentHandTrayCards(stream.messages, locale, effectivePlayerId),
    [stream.messages, locale, effectivePlayerId]
  );
  const overlayHandTitle = locale === "ko" ? "잔꾀 패" : "Trick hand";
  const overlayHandSubtitle =
    actionablePromptBehavior?.normalizedRequestType === "burden_exchange_batch"
      ? locale === "ko"
        ? "처리할 짐을 아래에서 고르세요."
        : "Pick the burden target below."
      : null;
  const hasBoardBottomDock =
    Boolean(passivePrompt) || Boolean(actionablePrompt) || overlayHandCards.length > 0;
  const hasPublicEventFeed =
    route !== "lobby" &&
    Boolean(eventFeedSpotlightItem) &&
    !visibleActionablePrompt;
  const showPublicEventFeed = hasPublicEventFeed && publicEventFeedOpen;
  const promptEffectContextItem = useMemo(() => {
    if (!visibleActionablePrompt) {
      return null;
    }
    const candidates = [
      ...currentTurnRevealItems.filter(isPromptEffectContextEvent),
      ...currentRoundRevealItems.filter((item) => item.eventCode === "weather_reveal"),
    ];
    candidates.sort((a, b) => b.seq - a.seq);
    return candidates[0] ?? null;
  }, [currentRoundRevealItems, currentTurnRevealItems, visibleActionablePrompt]);
  const promptEffectContext = useMemo(() => {
    if (!promptEffectContextItem) {
      return null;
    }
    const detail = compactEventDetail(promptEffectContextItem.label, promptEffectContextItem.detail);
    const effect = eventEffectForFeedItem(promptEffectContextItem, turnStage.weatherName, turnStage.weatherEffect);
    return {
      label: promptEffectContextItem.label,
      detail: hasReadableValue(detail) ? detail : promptEffectContextItem.label,
      attribution: eventEffectAttributionLabel(
        effect,
        `${promptEffectContextItem.label} ${promptEffectContextItem.detail}`,
        locale
      ),
      tone: promptEffectContextItem.tone,
      source: effect.effectSource,
      intent: effect.effectIntent,
      enhanced: effect.effectEnhanced,
    };
  }, [locale, promptEffectContextItem, turnStage.weatherEffect, turnStage.weatherName]);
  const playerStageFallbackLabel =
    currentPromptLabel && currentPromptLabel !== "-"
      ? currentPromptLabel
      : hasReadableValue(turnStage.currentBeatLabel)
        ? turnStage.currentBeatLabel
        : "-";
  const activeCharacterSlots = useMemo(
    () =>
      selectActiveCharacterSlots(stream.messages, effectivePlayerId, selectorText, sessionInitialActiveByCard).map((slot) => ({
        ...slot,
        ability: slot.character ? characterAbilityLabels[slot.character] ?? "-" : null,
      })),
    [stream.messages, effectivePlayerId, selectorText, sessionInitialActiveByCard, characterAbilityLabels]
  );
  const knownActiveCharacterCount = activeCharacterSlots.filter((slot) => Boolean(slot.character)).length;
  const markTargetActorName =
    visibleActionablePrompt?.requestType === "mark_target"
      ? typeof visibleActionablePrompt.publicContext["actor_name"] === "string" &&
        visibleActionablePrompt.publicContext["actor_name"].trim().length > 0
        ? (visibleActionablePrompt.publicContext["actor_name"] as string)
        : turnStage.character !== "-"
          ? turnStage.character
          : null
      : null;
  const markTargetDisplaySlots = useMemo(
    () =>
      visibleActionablePrompt?.requestType === "mark_target"
        ? selectMarkTargetCharacterSlots(stream.messages, markTargetActorName, effectivePlayerId, selectorText)
        : [],
    [visibleActionablePrompt?.requestType, stream.messages, markTargetActorName, effectivePlayerId, selectorText]
  );

  useEffect(() => {
    setApiBaseUrl(serverBaseUrl);
    saveStoredRoomServer(serverBaseUrl);
  }, [serverBaseUrl]);

  useEffect(() => {
    const onHashChange = () => {
      const parsed = parseHashState(window.location.hash);
      setRoute(parsed.route);
      if (parsed.sessionId) {
        setSessionInput(parsed.sessionId);
        setSessionId(parsed.sessionId);
      }
      if (parsed.token !== undefined) {
        const restoredToken = parsed.token || loadStoredSessionToken(parsed.sessionId ?? "");
        setTokenInput(restoredToken ?? "");
        setToken(restoredToken);
        setLocalPlayerId(inferPlayerIdFromSessionToken(restoredToken));
      } else if (parsed.sessionId) {
        const restoredToken = loadStoredSessionToken(parsed.sessionId);
        if (restoredToken) {
          setTokenInput(restoredToken);
          setToken(restoredToken);
          setLocalPlayerId(inferPlayerIdFromSessionToken(restoredToken));
        }
      }
    };

    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) {
      window.location.hash = LOBBY_HASH;
    } else {
      onHashChange();
    }
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (!activeRoomNo || !roomMemberToken) {
      setActiveRoom(null);
      setActiveRoomSeat(null);
      return;
    }
    let active = true;
    void resumeRoom({ roomNo: activeRoomNo, roomMemberToken })
      .then((room) => {
        if (!active) {
          return;
        }
        setActiveRoom(room);
        setActiveRoomSeat(room.member_seat);
        setServerConnected(true);
        if (room.session_id && room.session_token) {
          setSessionInput(room.session_id);
          setSessionId(room.session_id);
          setTokenInput(room.session_token);
          setToken(room.session_token);
          setLocalPlayerId(inferPlayerIdFromSessionToken(room.session_token));
          navigateRoute("match");
        }
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setActiveRoom(null);
        setActiveRoomNo(null);
        setRoomMemberToken(null);
        setActiveRoomSeat(null);
        saveStoredRoomMembership(null, null, serverBaseUrl);
      });
    return () => {
      active = false;
    };
  }, [activeRoomNo, roomMemberToken, serverBaseUrl]);

  useEffect(() => {
    if (!activeRoomNo || !roomMemberToken || route !== "lobby") {
      return;
    }
    let active = true;
    const tick = async () => {
      try {
        const room = await resumeRoom({ roomNo: activeRoomNo, roomMemberToken });
        if (!active) {
          return;
        }
        setActiveRoom(room);
        setActiveRoomSeat(room.member_seat);
        if (room.session_id && room.session_token) {
          setSessionInput(room.session_id);
          setSessionId(room.session_id);
          setTokenInput(room.session_token);
          setToken(room.session_token);
          setLocalPlayerId(inferPlayerIdFromSessionToken(room.session_token));
          navigateRoute("match");
        }
      } catch {
        // ignore transient room refresh failures
      }
    };
    const id = window.setInterval(() => void tick(), 3000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [activeRoomNo, roomMemberToken, route]);

  useEffect(() => {
    const seat = Number(joinSeatInput) || 1;
    const tokenBySeat = lastJoinTokens[String(seat)] ?? "";
    if (tokenBySeat) {
      setJoinTokenInput(tokenBySeat);
    }
  }, [joinSeatInput, lastJoinTokens]);

  useEffect(() => {
    if (joinSeatOptions.length === 0) {
      return;
    }
    if (!joinSeatOptions.includes(joinSeatInput)) {
      setJoinSeatInput(joinSeatOptions[0]);
    }
  }, [joinSeatInput, joinSeatOptions]);

  useEffect(() => {
    const parsed = Number(seatCountInput);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const seatCount = Math.max(1, Math.min(4, Math.trunc(parsed)));
    setSeatTypes((prev) => {
      if (prev.length === seatCount) {
        return prev;
      }
      if (prev.length > seatCount) {
        return prev.slice(0, seatCount);
      }
      return [...prev, ...Array.from({ length: seatCount - prev.length }, () => "ai" as const)];
    });
  }, [seatCountInput]);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!sessionId.trim()) {
      return;
    }
    let active = true;
    const tick = async () => {
      try {
        const runtimeState = await getRuntimeStatus(sessionId.trim(), token);
        if (active) {
          setRuntime(runtimeState.runtime);
        }
      } catch {
        // ignore transient polling errors
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 4000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [sessionId, token]);

  useEffect(() => {
    if (!sessionId.trim()) {
      setSessionManifest(null);
      setSessionInitialActiveByCard(null);
      setSessionSeats(null);
      return;
    }
    let active = true;
    void getSession({ sessionId: sessionId.trim() })
      .then((data) => {
        if (active) {
          setSessionManifest(data.parameter_manifest ?? null);
          setSessionInitialActiveByCard(data.initial_active_by_card ?? null);
          setSessionSeats(data.seats ?? null);
        }
      })
      .catch(() => {
        // keep last known manifest
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!latestManifest) {
      return;
    }
    setSessionManifest((prev) => mergeSessionManifest(prev, latestManifest));
  }, [latestManifest]);

  useEffect(() => {
    if (!actionablePrompt) {
      setPromptBusy(false);
      setPromptRequestId("");
      setPromptExpiresAtMs(null);
      setPromptFeedback("");
      setBurdenExchangeQueuedDeckIndexes([]);
      setBurdenExchangeQueuedPlayerId(null);
      promptSubmitRequestIdRef.current = null;
      return;
    }
    if (actionablePrompt.requestId !== promptRequestId) {
      setPromptBusy(false);
      setPromptCollapsed(false);
      setPromptRequestId(actionablePrompt.requestId);
      setPromptExpiresAtMs(Date.now() + actionablePrompt.timeoutMs);
      setPromptFeedback("");
      promptSubmitRequestIdRef.current = null;
    }
  }, [actionablePrompt, promptRequestId]);

  useEffect(() => {
    if (!promptBusy || !promptInteraction.shouldReleaseSubmission) {
      return;
    }
    const keepBurdenExchangeQueue =
      burdenExchangeQueuedPlayerId !== null &&
      actionablePromptBehavior?.normalizedRequestType === "burden_exchange_batch" &&
      actionablePromptBehavior.autoContinue === true &&
      actionablePrompt?.playerId === burdenExchangeQueuedPlayerId;
    setPromptBusy(false);
    if (!keepBurdenExchangeQueue) {
      setBurdenExchangeQueuedDeckIndexes([]);
      setBurdenExchangeQueuedPlayerId(null);
    }
    promptSubmitRequestIdRef.current = null;
  }, [
    actionablePrompt,
    actionablePromptBehavior,
    burdenExchangeQueuedPlayerId,
    promptBusy,
    promptInteraction.shouldReleaseSubmission,
  ]);

  useEffect(() => {
    if (burdenExchangeQueuedPlayerId === null) {
      return;
    }
    if (promptUiBusy) {
      return;
    }
    if (!actionablePrompt) {
      setBurdenExchangeQueuedDeckIndexes([]);
      setBurdenExchangeQueuedPlayerId(null);
      return;
    }
    if (
      actionablePromptBehavior?.normalizedRequestType !== "burden_exchange_batch" ||
      actionablePrompt.playerId !== burdenExchangeQueuedPlayerId
    ) {
      setBurdenExchangeQueuedDeckIndexes([]);
      setBurdenExchangeQueuedPlayerId(null);
    }
  }, [actionablePrompt, actionablePromptBehavior, burdenExchangeQueuedPlayerId, promptUiBusy]);

  useEffect(() => {
    if (
      !actionablePrompt ||
      promptUiBusy ||
      actionablePromptBehavior?.normalizedRequestType !== "burden_exchange_batch" ||
      actionablePromptBehavior.autoContinue !== true ||
      burdenExchangeQueuedPlayerId === null ||
      actionablePrompt.playerId !== burdenExchangeQueuedPlayerId
    ) {
      return;
    }

    const currentDeckIndex =
      typeof actionablePrompt.publicContext["card_deck_index"] === "number"
        ? (actionablePrompt.publicContext["card_deck_index"] as number)
        : null;
    const shouldRemove = currentDeckIndex !== null && burdenExchangeQueuedDeckIndexes.includes(currentDeckIndex);
    const sent = stream.sendDecision({
      requestId: actionablePrompt.requestId,
      playerId: actionablePrompt.playerId,
      choiceId: shouldRemove ? "yes" : "no",
      choicePayload: {},
    });
    if (!sent) {
      setPromptFeedback(app.errors.sendPrompt);
      setBurdenExchangeQueuedDeckIndexes([]);
      setBurdenExchangeQueuedPlayerId(null);
      return;
    }
    setBurdenExchangeQueuedDeckIndexes((prev) =>
      currentDeckIndex === null ? prev : prev.filter((item) => item !== currentDeckIndex)
    );
    setPromptBusy(true);
  }, [
    actionablePrompt,
    actionablePromptBehavior,
    burdenExchangeQueuedDeckIndexes,
    burdenExchangeQueuedPlayerId,
    promptUiBusy,
    stream,
    app.errors,
  ]);

  useEffect(() => {
    if (
      turnStage.turnStartSeq === null ||
      !boardTurnOverlay ||
      turnStage.turnStartSeq <= lastTurnBannerSeqRef.current
    ) {
      return;
    }
    lastTurnBannerSeqRef.current = turnStage.turnStartSeq;
    setTurnBanner({
      seq: turnStage.turnStartSeq,
      text: boardTurnOverlay.text,
      detail: boardTurnOverlay.detail && boardTurnOverlay.detail !== "-" ? boardTurnOverlay.detail : turnStage.weatherName,
      variant: "turn",
    });
    const timer = window.setTimeout(() => {
      setTurnBanner((prev) => (prev?.seq === turnStage.turnStartSeq ? null : prev));
    }, isMyTurn ? 5000 : 3200);
    return () => window.clearTimeout(timer);
  }, [boardTurnOverlay, isMyTurn, turnStage.turnStartSeq, turnStage.weatherName]);

  useEffect(() => {
    if (!latestCurrentTurnReveal || latestCurrentTurnReveal.seq <= lastRevealBannerSeqRef.current) {
      return;
    }
    if (!latestCurrentTurnReveal.isInterrupt) {
      return;
    }

    lastRevealBannerSeqRef.current = latestCurrentTurnReveal.seq;
    setTurnBanner({
      seq: latestCurrentTurnReveal.seq,
      text: latestCurrentTurnReveal.label,
      detail: latestCurrentTurnReveal.detail && latestCurrentTurnReveal.detail !== "-" ? latestCurrentTurnReveal.detail : turnStage.weatherName,
      variant: "interrupt",
    });
    const timer = window.setTimeout(() => {
      setTurnBanner((prev) => (prev?.seq === latestCurrentTurnReveal.seq ? null : prev));
    }, 2800);
    return () => window.clearTimeout(timer);
  }, [latestCurrentTurnReveal, turnStage.weatherName]);

  // Enqueue game event overlays for notable economy events
  const lastEnqueuedRevealSeqRef = useRef<number>(0);
  useEffect(() => {
    if (!latestCurrentTurnReveal) return;
    if (latestCurrentTurnReveal.seq <= lastEnqueuedRevealSeqRef.current) return;

    const { eventCode, label, detail, seq } = latestCurrentTurnReveal;
    const sourcePayload = appRecordOrNull(stream.messages.find((message) => message.seq === seq)?.payload);
    const effect = (kind: EventOverlayEffectKind) =>
      eventEffectForReveal({
        eventCode,
        kind,
        label,
        detail,
        weatherName: turnStage.weatherName,
        weatherEffect: turnStage.weatherEffect,
      });

    if (eventCode === "weather_reveal") {
      lastEnqueuedRevealSeqRef.current = seq;
      eventQueue.enqueue({ kind: "weather", label, detail, ...effect("weather") });
    } else if (eventCode === "dice_roll") {
      lastEnqueuedRevealSeqRef.current = seq;
      const dice = sourcePayload ? diceOverlayValues(sourcePayload) : { values: [], total: null };
      eventQueue.enqueue({
        kind: "dice",
        label,
        detail,
        diceValues: dice.values,
        diceTotal: dice.total,
        ...effect("dice"),
      });
    } else if (eventCode === "tile_purchased") {
      lastEnqueuedRevealSeqRef.current = seq;
      eventQueue.enqueue({
        kind: "purchase",
        label,
        detail,
        ...effect("purchase"),
        effectCharacter: effectCharacterFromPayload(sourcePayload, detail),
      });
    } else if (eventCode === "rent_paid") {
      lastEnqueuedRevealSeqRef.current = seq;
      const kind = rentOverlayKindForPlayer(detail, effectivePlayerId);
      eventQueue.enqueue({ kind, label, detail, ...effect(kind) });
    } else if (eventCode === "lap_reward_chosen") {
      lastEnqueuedRevealSeqRef.current = seq;
      eventQueue.enqueue({ kind: "lap_complete", label, detail, ...effect("lap_complete") });
    } else if (eventCode === "fortune_drawn" || eventCode === "fortune_resolved") {
      lastEnqueuedRevealSeqRef.current = seq;
      const moveDetail = sourcePayload ? movementOverlayDetail(sourcePayload, locale) : null;
      if (moveDetail) {
        eventQueue.enqueue({ kind: "move", label: locale === "ko" ? "운수 이동" : "Fortune move", detail: moveDetail });
      }
      eventQueue.enqueue({ kind: "fortune", label, detail, ...effect("fortune") });
    } else if (eventCode === "trick_used") {
      lastEnqueuedRevealSeqRef.current = seq;
      const moveDetail = sourcePayload ? movementOverlayDetail(sourcePayload, locale) : null;
      if (moveDetail) {
        eventQueue.enqueue({ kind: "move", label: locale === "ko" ? "잔꾀 이동" : "Trick move", detail: moveDetail });
      }
      eventQueue.enqueue({ kind: "trick", label, detail, ...effect("trick") });
    } else if (eventCode === "mark_resolved" || eventCode === "mark_queued") {
      lastEnqueuedRevealSeqRef.current = seq;
      const moveDetail = sourcePayload ? movementOverlayDetail(sourcePayload, locale) : null;
      if (moveDetail) {
        eventQueue.enqueue({ kind: "move", label: locale === "ko" ? "지목 이동" : "Mark move", detail: moveDetail });
      }
      eventQueue.enqueue({
        kind: "mark_success",
        label,
        detail,
        ...effect("mark_success"),
        effectCharacter: effectCharacterFromPayload(sourcePayload, detail),
      });
    } else if (eventCode === "bankruptcy") {
      lastEnqueuedRevealSeqRef.current = seq;
      eventQueue.enqueue({ kind: "bankruptcy", label, detail, ...effect("bankruptcy") });
    } else if (eventCode === "game_end") {
      lastEnqueuedRevealSeqRef.current = seq;
      eventQueue.enqueue({ kind: "game_end", label, detail, ...effect("game_end") });
    }
  }, [latestCurrentTurnReveal, effectivePlayerId, eventQueue, locale, stream.messages, turnStage.weatherEffect, turnStage.weatherName]);

  useEffect(() => {
    if (route !== "match" || stream.status !== "connected") {
      return;
    }
    const parsed = parseHashState(window.location.hash);
    if (!parsed.token || !sessionId.trim()) {
      return;
    }
    const safeHash = buildMatchHash(sessionId.trim());
    window.history.replaceState(null, "", safeHash);
  }, [route, sessionId, stream.status]);

  useEffect(() => {
    if (!hasPublicEventFeed && publicEventFeedOpen) {
      setPublicEventFeedOpen(false);
    }
  }, [hasPublicEventFeed, publicEventFeedOpen]);

  const openDebugWindow = () => {
    if (debugWindowRef.current && !debugWindowRef.current.closed) {
      return debugWindowRef.current;
    }
    const popup = window.open("", "mrn-debug-log", "width=900,height=960,resizable=yes,scrollbars=yes");
    if (popup) {
      debugWindowRef.current = popup;
    }
    return popup;
  };

  const toggleRawMessages = () => {
    if (showRawMessages) {
      setShowRawMessages(false);
      return;
    }
    if (openDebugWindow()) {
      setShowRawMessages(true);
    }
  };

  useEffect(() => {
    if (!showRawMessages) {
      if (debugWindowRef.current && !debugWindowRef.current.closed) {
        debugWindowRef.current.close();
      }
      debugWindowRef.current = null;
      return;
    }
    const popup = debugWindowRef.current && !debugWindowRef.current.closed ? debugWindowRef.current : null;
    if (!popup) {
      debugWindowRef.current = null;
      setShowRawMessages(false);
      return;
    }
    const debugTimeline = selectTimeline(debugMessages, Math.max(debugMessages.length, compactDensity ? 24 : 40), selectorText);
    const debugCoreActionFeed = selectCoreActionFeed(
      debugMessages,
      effectivePlayerId,
      Math.max(debugMessages.length, compactDensity ? 10 : 14),
      selectorText
    );
    const timelineMarkup = debugTimeline
      .slice()
      .sort((left, right) => right.seq - left.seq)
      .map(
        (item) => `
          <article class="debug-timeline-item">
            <strong>#${item.seq} ${escapeDebugHtml(item.label)}</strong>
            <p>${escapeDebugHtml(item.detail)}</p>
          </article>
        `
      )
      .join("");
    const coreActionMarkup = debugCoreActionFeed
      .slice()
      .sort((left, right) => right.seq - left.seq)
      .map(
        (item) => `
          <article class="debug-core-item ${item.isLocalActor ? "debug-core-item-local" : ""}">
            <strong>#${item.seq} ${escapeDebugHtml(item.label)}</strong>
            <p>${escapeDebugHtml(item.actor)} · ${escapeDebugHtml(item.detail)}</p>
          </article>
        `
      )
      .join("");
    const debugTurnGroups = groupDebugMessagesByTurn(debugMessages, locale);
    const rawMarkup = debugTurnGroups
      .slice()
      .reverse()
      .map(
        (group) => `
          <article class="debug-turn-group">
            <h3>${escapeDebugHtml(group.label)} <span>${group.messages.length}</span></h3>
            ${group.messages
              .slice()
              .reverse()
              .map((message) => `<pre>${escapeDebugHtml(JSON.stringify(message, null, 2))}</pre>`)
              .join("")}
          </article>
        `
      )
      .join("");
    popup.document.open();
    popup.document.write(`
      <!doctype html>
      <html lang="${locale}">
        <head>
          <meta charset="utf-8" />
          <title>MRN Debug Log</title>
          <style>
            body { margin: 0; font-family: "SF Mono", ui-monospace, monospace; background: #071225; color: #e6efff; }
            main { display: grid; grid-template-columns: 300px 360px minmax(0, 1fr); min-height: 100vh; }
            aside { border-right: 1px solid #203a63; padding: 16px; background: #0a1730; overflow: auto; }
            .core { border-right: 1px solid #203a63; padding: 16px; background: #09182f; overflow: auto; }
            section { padding: 16px; overflow: auto; }
            h1, h2 { margin: 0 0 12px; font-family: "Noto Sans KR", sans-serif; }
            .meta { margin-bottom: 16px; color: #a9bbdf; font-family: "Noto Sans KR", sans-serif; }
            .debug-timeline-item { padding: 10px; border-radius: 10px; background: #0d1f3d; border: 1px solid #274679; margin-bottom: 8px; }
            .debug-timeline-item strong { display: block; color: #ffda77; margin-bottom: 6px; }
            .debug-timeline-item p { margin: 0; color: #d7e5ff; font-family: "Noto Sans KR", sans-serif; line-height: 1.5; }
            .debug-core-item { padding: 10px; border-radius: 10px; background: #10233f; border: 1px solid #29567a; margin-bottom: 8px; }
            .debug-core-item-local { border-color: #d4ad54; }
            .debug-core-item strong { display: block; color: #f2f6ff; margin-bottom: 6px; font-family: "Noto Sans KR", sans-serif; }
            .debug-core-item p { margin: 0; color: #cddcff; font-family: "Noto Sans KR", sans-serif; line-height: 1.5; }
            .debug-turn-group { margin-bottom: 18px; }
            .debug-turn-group h3 { position: sticky; top: 0; z-index: 1; display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 0 0 10px; padding: 10px 12px; border-radius: 10px; border: 1px solid #3a5f95; background: #0f2749; color: #ffda77; font-family: "Noto Sans KR", sans-serif; font-size: 14px; }
            .debug-turn-group h3 span { color: #b9c7e6; font-family: "SF Mono", ui-monospace, monospace; font-size: 12px; }
            pre { margin: 0 0 10px; padding: 12px; border-radius: 10px; background: #091427; border: 1px solid #203a63; white-space: pre-wrap; word-break: break-word; }
          </style>
        </head>
        <body>
          <main>
            <aside>
              <h1>Debug Log</h1>
              <div class="meta">session=${escapeDebugHtml(sessionId || "-")} / runtime=${escapeDebugHtml(runtime.status)} / seq=${stream.lastSeq} / accumulated=${debugMessages.length}</div>
              <h2>Timeline</h2>
              ${timelineMarkup || "<p>-</p>"}
            </aside>
            <div class="core">
              <h2>Public Action (${debugCoreActionFeed.length})</h2>
              ${coreActionMarkup || "<p>-</p>"}
            </div>
            <section>
              <h2>Raw Messages by Turn (${debugTurnGroups.length} / ${debugMessages.length})</h2>
              ${rawMarkup || "<p>-</p>"}
            </section>
          </main>
        </body>
      </html>
    `);
    popup.document.close();
    const syncClosed = window.setInterval(() => {
      if (debugWindowRef.current?.closed) {
        debugWindowRef.current = null;
        setShowRawMessages(false);
      }
    }, 1000);
    return () => window.clearInterval(syncClosed);
  }, [
    compactDensity,
    debugMessages,
    effectivePlayerId,
    locale,
    runtime.status,
    selectorText,
    sessionId,
    showRawMessages,
    stream.lastSeq,
  ]);

  useEffect(() => {
    saveStoredSessionToken(sessionId, token);
  }, [sessionId, token]);

  const navigateRoute = (next: ViewRoute) => {
    if (next === "match") {
      window.location.hash = buildMatchHash(sessionInput || sessionId, tokenInput || token);
    } else {
      window.location.hash = LOBBY_HASH;
    }
    setRoute(next);
  };

  const refreshSessions = async () => {
    try {
      const result = await listSessions();
      setSessions(result.sessions);
    } catch (e) {
      setError(e instanceof Error ? e.message : app.errors.refreshSessions);
    }
  };

  const refreshRooms = async () => {
    try {
      const result = await listRooms();
      setRooms(result.rooms);
      setServerConnected(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh rooms.");
      setServerConnected(false);
    }
  };

  const connectServer = async () => {
    const normalized = normalizeServerBaseUrl(serverBaseInput);
    setBusy(true);
    setError("");
    setNotice("");
    setServerBaseUrl(normalized);
    setApiBaseUrl(normalized);
    try {
      const result = await listRooms();
      setRooms(result.rooms);
      setServerConnected(true);
      setNotice(locale === "ko" ? `서버에 연결했습니다: ${normalized}` : `Connected to ${normalized}`);
    } catch (e) {
      setServerConnected(false);
      setError(e instanceof Error ? e.message : "Failed to connect to server.");
    } finally {
      setBusy(false);
    }
  };

  const onCreateRoom = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const seed = resolveSessionSeed(seedInput);
      const seats = seatTypes.map((seatType, index) => ({
        seat: index + 1,
        seat_type: seatType,
        ai_profile: seatType === "ai" ? aiProfile : undefined,
      }));
      const created = await createRoom({
        roomTitle: roomTitleInput.trim() || "MRN Room",
        hostSeat: Number(hostSeatInput) || 1,
        nickname: displayNameInput.trim() || "Player",
        seats,
        config: {
          seed,
          seat_limits: {
            min: 1,
            max: seats.length,
            allowed: Array.from({ length: seats.length }, (_, idx) => idx + 1),
          },
        },
      });
      setActiveRoom(created.room);
      setActiveRoomNo(created.room.room_no);
      setRoomMemberToken(created.room_member_token);
      setActiveRoomSeat(created.seat);
      saveStoredRoomMembership(created.room.room_no, created.room_member_token, serverBaseUrl);
      setNotice(locale === "ko" ? `방 #${created.room.room_no} 생성 완료` : `Created room #${created.room.room_no}`);
      await refreshRooms();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create room.");
    } finally {
      setBusy(false);
    }
  };

  const onJoinRoom = async (roomNo: number, seat: number) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const joined = await joinRoom({
        roomNo,
        seat,
        nickname: displayNameInput.trim() || "Player",
      });
      setActiveRoom(joined.room);
      setActiveRoomNo(joined.room.room_no);
      setRoomMemberToken(joined.room_member_token);
      setActiveRoomSeat(joined.seat);
      saveStoredRoomMembership(joined.room.room_no, joined.room_member_token, serverBaseUrl);
      setNotice(locale === "ko" ? `방 #${roomNo}에 참가했습니다.` : `Joined room #${roomNo}.`);
      await refreshRooms();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join room.");
    } finally {
      setBusy(false);
    }
  };

  const onToggleRoomReady = async (ready: boolean) => {
    if (!activeRoomNo || !roomMemberToken) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const room = await setRoomReady({
        roomNo: activeRoomNo,
        roomMemberToken,
        ready,
      });
      setActiveRoom(room);
      await refreshRooms();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to change ready state.");
    } finally {
      setBusy(false);
    }
  };

  const onLeaveRoom = async () => {
    if (!activeRoomNo || !roomMemberToken) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await leaveRoom({ roomNo: activeRoomNo, roomMemberToken });
      setActiveRoom(null);
      setActiveRoomNo(null);
      setRoomMemberToken(null);
      setActiveRoomSeat(null);
      saveStoredRoomMembership(null, null, serverBaseUrl);
      setNotice(locale === "ko" ? "방에서 나왔습니다." : "Left the room.");
      await refreshRooms();
    } catch (e) {
      setActiveRoom(null);
      setActiveRoomNo(null);
      setRoomMemberToken(null);
      setActiveRoomSeat(null);
      saveStoredRoomMembership(null, null, serverBaseUrl);
      setError(e instanceof Error ? e.message : "Failed to leave room.");
      await refreshRooms();
    } finally {
      setBusy(false);
    }
  };

  const onStartRoom = async () => {
    if (!activeRoomNo || !roomMemberToken || !activeRoomSeat) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const started = await startRoom({
        roomNo: activeRoomNo,
        roomMemberToken,
      });
      const roomSessionToken = started.session_tokens[String(activeRoomSeat)];
      setActiveRoom(started.room);
      if (roomSessionToken) {
        setSessionInput(started.session_id);
        setSessionId(started.session_id);
        setTokenInput(roomSessionToken);
        setToken(roomSessionToken);
        setLocalPlayerId(inferPlayerIdFromSessionToken(roomSessionToken));
        navigateRoute("match");
      }
      setNotice(locale === "ko" ? `방 #${activeRoomNo} 게임 시작` : `Started room #${activeRoomNo}`);
      await refreshRooms();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start room.");
    } finally {
      setBusy(false);
    }
  };

  const onConnect = (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");
    setLocalPlayerId(null);
    const normalized = sessionInput.trim();
    setSessionId(normalized);
    const nextToken = tokenInput.trim() || undefined;
    setToken(nextToken);
    setLocalPlayerId(inferPlayerIdFromSessionToken(nextToken));
    if (normalized) {
      window.location.hash = buildMatchHash(normalized, nextToken);
      navigateRoute("match");
    }
  };

  const onCreateCustomSession = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const seed = resolveSessionSeed(seedInput);
      const seats = seatTypes.map((seatType, index) => ({
        seat: index + 1,
        seat_type: seatType,
        ai_profile: seatType === "ai" ? aiProfile : undefined,
      }));
      const created = await createSession({
        seats,
        config: {
          seed,
          seat_limits: {
            min: 1,
            max: seats.length,
            allowed: Array.from({ length: seats.length }, (_, idx) => idx + 1),
          },
        },
      });
      setSessionManifest(created.parameter_manifest ?? null);
      setSessionInitialActiveByCard(created.initial_active_by_card ?? null);
      setSessionSeats(created.seats ?? null);
      setSessionInput(created.session_id);
      setSessionId(created.session_id);
      setTokenInput("");
      setToken(undefined);
      setLocalPlayerId(null);
      setHostTokenInput(created.host_token);
      setLastJoinTokens(created.join_tokens);
      const seat = Number(joinSeatInput) || 1;
      const autoToken = created.join_tokens[String(seat)] ?? "";
      setJoinTokenInput(autoToken);
      setNotice(app.notices.createSession(created.session_id, created.host_token, created.join_tokens));
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : app.errors.createSession);
    } finally {
      setBusy(false);
    }
  };

  const onCreateAndStartAi = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const seed = resolveSessionSeed(seedInput);
      const created = await createSession({
        seats: Array.from({ length: seatTypes.length }, (_, idx) => ({
          seat: idx + 1,
          seat_type: "ai" as const,
          ai_profile: idx % 2 === 0 ? "gpt" : "claude",
        })),
        config: {
          seed,
          seat_limits: {
            min: 1,
            max: seatTypes.length,
            allowed: Array.from({ length: seatTypes.length }, (_, idx) => idx + 1),
          },
        },
      });
      setSessionManifest(created.parameter_manifest ?? null);
      setSessionInitialActiveByCard(created.initial_active_by_card ?? null);
      setSessionSeats(created.seats ?? null);
      await startSession({ sessionId: created.session_id, hostToken: created.host_token });
      const runtimeState = await getRuntimeStatus(created.session_id);
      setRuntime(runtimeState.runtime);
      setSessionInput(created.session_id);
      setSessionId(created.session_id);
      setTokenInput("");
      setToken(undefined);
      setLocalPlayerId(null);
      setHostTokenInput(created.host_token);
      setLastJoinTokens(created.join_tokens);
      setJoinSeatInput("1");
      setJoinTokenInput("");
      setNotice(app.notices.startAiSession(created.session_id));
      navigateRoute("match");
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : app.errors.startAiSession);
    } finally {
      setBusy(false);
    }
  };

  const onQuickStartHumanVsAi = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const seed = resolveSessionSeed(seedInput);
      const seatCount = Math.max(2, Math.min(4, Number(seatCountInput) || 4));
      const seats = Array.from({ length: seatCount }, (_, idx) => ({
        seat: idx + 1,
        seat_type: idx === 0 ? ("human" as const) : ("ai" as const),
        ai_profile: idx === 0 ? undefined : aiProfile,
      }));
      const created = await createSession({
        seats,
        config: {
          seed,
          seat_limits: {
            min: 1,
            max: seats.length,
            allowed: Array.from({ length: seats.length }, (_, idx) => idx + 1),
          },
        },
      });
      const seat1Token = created.join_tokens["1"];
      if (!seat1Token) {
        throw new Error("Seat 1 join token was not issued.");
      }
      const joined = await joinSession({
        sessionId: created.session_id,
        seat: 1,
        joinToken: seat1Token,
        displayName: displayNameInput.trim() || "Player",
      });
      await startSession({ sessionId: created.session_id, hostToken: created.host_token });

      setSessionManifest(created.parameter_manifest ?? null);
      setSessionInitialActiveByCard(created.initial_active_by_card ?? null);
      setSessionSeats(created.seats ?? null);
      setSessionInput(created.session_id);
      setSessionId(created.session_id);
      setTokenInput(joined.session_token);
      setToken(joined.session_token);
      setLocalPlayerId(joined.player_id);
      setHostTokenInput(created.host_token);
      setLastJoinTokens(created.join_tokens);
      setJoinSeatInput("1");
      setJoinTokenInput(seat1Token);
      setNotice(app.notices.quickStart(created.session_id, joined.player_id));
      navigateRoute("match");
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : app.errors.quickStart);
    } finally {
      setBusy(false);
    }
  };

  const onStartByHostToken = async () => {
    const current = sessionInput.trim() || sessionId.trim();
    if (!current || !hostTokenInput.trim()) {
      setError(app.errors.startByHostTokenMissing);
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const started = await startSession({ sessionId: current, hostToken: hostTokenInput.trim() });
      setSessionManifest(started.parameter_manifest ?? null);
      setSessionInitialActiveByCard(started.initial_active_by_card ?? null);
      setSessionSeats(started.seats ?? null);
      setSessionId(current);
      setNotice(app.notices.startSession(current));
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : app.errors.startSession);
    } finally {
      setBusy(false);
    }
  };

  const onJoinSeat = async () => {
    const current = sessionInput.trim() || sessionId.trim();
    const seat = Number(joinSeatInput);
    if (!current || !seat || !joinTokenInput.trim()) {
      setError(app.errors.joinSeatMissing);
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const snapshotLocal = await getSession({ sessionId: current });
      if (snapshotLocal.status !== "waiting") {
        throw new Error(app.errors.joinSeatNotWaiting);
      }
      const seatView = (snapshotLocal.seats ?? []).find((s) => s.seat === seat);
      if (!seatView) {
        throw new Error(app.errors.joinSeatNotFound(seat));
      }
      if (seatView.seat_type !== "human") {
        throw new Error(app.errors.joinSeatNotHuman(seat));
      }
      const joined = await joinSession({
        sessionId: current,
        seat,
        joinToken: joinTokenInput.trim(),
        displayName: displayNameInput.trim() || undefined,
      });
      setSessionInput(current);
      setSessionId(current);
      setSessionSeats(snapshotLocal.seats ?? null);
      setTokenInput(joined.session_token);
      setToken(joined.session_token);
      setLocalPlayerId(joined.player_id);
      setNotice(app.notices.joinSeat(joined.player_id));
      navigateRoute("match");
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : app.errors.joinSeatFailed);
    } finally {
      setBusy(false);
    }
  };

  const onUseSession = (id: string) => {
    setError("");
    setSessionInput(id);
    setSessionId(id);
    setHostTokenInput("");
    setJoinSeatInput("1");
    setJoinTokenInput("");
    setLastJoinTokens({});
    setTokenInput("");
    setToken(undefined);
    setLocalPlayerId(null);
    const selected = sessions.find((session) => session.session_id === id);
    setSessionManifest(selected?.parameter_manifest ?? null);
    setSessionInitialActiveByCard(selected?.initial_active_by_card ?? null);
    setSessionSeats(selected?.seats ?? null);
    setNotice(app.notices.useSession(id));
    if (route === "match") {
      window.location.hash = buildMatchHash(id);
    }
  };

  const onSeatTypeChange = (index: number, value: LobbySeatType) => {
    const next = [...seatTypes];
    next[index] = value;
    setSeatTypes(next);
  };

  const onSelectPromptChoice = (choiceId: string) => {
    if (!actionablePrompt || promptUiBusy) {
      return;
    }
    if (promptSubmitRequestIdRef.current === actionablePrompt.requestId) {
      return;
    }
    if (!actionablePrompt.playerId) {
      setError(app.errors.invalidPromptPlayer);
      return;
    }
    if (actionablePrompt.requestType === "active_flip" && choiceId.startsWith("__active_flip_batch__:")) {
      const requestedIds = choiceId
        .replace("__active_flip_batch__:", "")
        .split(",")
        .map((value) => value.trim())
        .filter((value) => value.length > 0 && value !== "none");
      if (requestedIds.length === 0) {
        setPromptFeedback(locale === "ko" ? "뒤집을 카드를 한 장 이상 선택하세요." : "Choose at least one card to flip.");
        return;
      }
      promptSubmitRequestIdRef.current = actionablePrompt.requestId;
      const sent = stream.sendDecision({
        requestId: actionablePrompt.requestId,
        playerId: actionablePrompt.playerId,
        choiceId: "none",
        choicePayload: {
          selected_choice_ids: requestedIds,
          finish_after_selection: true,
        },
      });
      if (!sent) {
        promptSubmitRequestIdRef.current = null;
        setPromptFeedback(app.errors.sendPrompt);
        return;
      }
      setPromptBusy(true);
      return;
    }
    if (
      actionablePromptBehavior?.normalizedRequestType === "burden_exchange_batch" &&
      choiceId.startsWith("__burden_exchange_batch__:")
    ) {
      const requestedDeckIndexes = choiceId
        .replace("__burden_exchange_batch__:", "")
        .split(",")
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isFinite(value));
      const currentDeckIndex =
        typeof actionablePrompt.publicContext["card_deck_index"] === "number"
          ? (actionablePrompt.publicContext["card_deck_index"] as number)
          : null;
      const shouldRemoveCurrent = currentDeckIndex !== null && requestedDeckIndexes.includes(currentDeckIndex);
      const sent = stream.sendDecision({
        requestId: actionablePrompt.requestId,
        playerId: actionablePrompt.playerId,
        choiceId: shouldRemoveCurrent ? "yes" : "no",
        choicePayload: {},
      });
      if (!sent) {
        setPromptFeedback(app.errors.sendPrompt);
        return;
      }
      setBurdenExchangeQueuedPlayerId(actionablePrompt.playerId);
      setBurdenExchangeQueuedDeckIndexes(
        currentDeckIndex === null ? requestedDeckIndexes : requestedDeckIndexes.filter((item) => item !== currentDeckIndex)
      );
      setPromptBusy(true);
      return;
    }
    setPromptFeedback("");
    setBurdenExchangeQueuedDeckIndexes([]);
    setBurdenExchangeQueuedPlayerId(null);
    promptSubmitRequestIdRef.current = actionablePrompt.requestId;
    const sent = stream.sendDecision({
      requestId: actionablePrompt.requestId,
      playerId: actionablePrompt.playerId,
      choiceId,
      choicePayload: {},
    });
    if (!sent) {
      promptSubmitRequestIdRef.current = null;
      setPromptFeedback(app.errors.sendPrompt);
      return;
    }
    setPromptBusy(true);
  };

  return (
    <main className={`page ${compactDensity ? "page-compact" : ""} ${route === "match" ? "page-match" : "page-lobby"}`}>
      {route === "lobby" ? (
        <header className="header">
          <h1>{app.title}</h1>
          <p>{app.subtitle}</p>
          <div className="route-tabs">
            <button
              type="button"
              className={route === "lobby" ? "route-tab route-tab-active" : "route-tab"}
              onClick={() => navigateRoute("lobby")}
            >
              {app.routeLobby}
            </button>
            <button
              type="button"
              className="route-tab"
              onClick={() => navigateRoute("match")}
            >
              {app.routeMatch}
            </button>
            <button
              type="button"
              className={locale === "ko" ? "route-tab route-tab-active" : "route-tab"}
              data-testid="locale-switch-ko"
              onClick={() => setLocale("ko")}
            >
              {app.localeKo}
            </button>
            <button
              type="button"
              className={locale === "en" ? "route-tab route-tab-active" : "route-tab"}
              data-testid="locale-switch-en"
              onClick={() => setLocale("en")}
            >
              {app.localeEn}
            </button>
          </div>
        </header>
      ) : (
        <header className="match-global-bar">
          <div className="match-global-left">
            <div className="match-global-summary-line">
              <strong>{sessionId ? `Session ${sessionId}` : app.topSummaryEmpty}</strong>
              {snapshot ? (
                <span className="match-global-round">
                  {boardText.roundTurnMarker(snapshot.round, snapshot.turn, snapshot.markerOwnerPlayerId, Math.max(0, 15 - snapshot.fValue))}
                </span>
              ) : null}
              {sessionInfoExpanded ? (
                <small>{`${runtime.status} · ${currentActorText !== "-" ? currentActorText : app.topSummaryEmpty}`}</small>
              ) : null}
            </div>
          </div>
          <div className="match-global-right">
            <div className="match-global-actions">
              <button type="button" className="route-tab" onClick={() => setSessionInfoExpanded((prev) => !prev)}>
                {sessionInfoToggleLabel(locale, sessionInfoExpanded)}
              </button>
              <button type="button" className="route-tab" onClick={() => navigateRoute("lobby")}>
                {app.routeLobby}
              </button>
              <button
                type="button"
                className={locale === "ko" ? "route-tab route-tab-active" : "route-tab"}
                data-testid="locale-switch-ko"
                onClick={() => setLocale("ko")}
              >
                {app.localeKo}
              </button>
              <button
                type="button"
                className={locale === "en" ? "route-tab route-tab-active" : "route-tab"}
                data-testid="locale-switch-en"
                onClick={() => setLocale("en")}
              >
                {app.localeEn}
              </button>
              <button type="button" className="route-tab" onClick={() => setCompactDensity((prev) => !prev)}>
                {compactDensity ? app.densityStandard : app.densityCompact}
              </button>
              <button type="button" className="route-tab" onClick={toggleRawMessages}>
                {showRawMessages ? app.rawHide : app.rawShow}
              </button>
            </div>
          </div>
        </header>
      )}

      {route !== "lobby" && effectiveTurnBanner ? (
        <section
          className={`turn-notice-banner ${
            effectiveTurnBanner.variant === "interrupt" ? "turn-notice-banner-interrupt" : "turn-notice-banner-turn"
          } ${effectiveTurnBanner.variant === "turn" && isMyTurn ? "turn-notice-banner-local" : ""}`}
          data-testid="turn-notice-banner"
          data-banner-variant={effectiveTurnBanner.variant}
          data-banner-local={effectiveTurnBanner.variant === "turn" && isMyTurn ? "true" : "false"}
          data-banner-has-detail={effectiveTurnBanner.detail && effectiveTurnBanner.detail !== "-" ? "true" : "false"}
          data-banner-player-id={currentActorId ? String(currentActorId) : undefined}
        >
          <strong data-testid="turn-notice-banner-title">{effectiveTurnBanner.text}</strong>
          {effectiveTurnBanner.detail && effectiveTurnBanner.detail !== "-" ? (
            <small data-testid="turn-notice-banner-detail">{effectiveTurnBanner.detail}</small>
          ) : null}
        </section>
      ) : null}

      {route !== "lobby" && myTurnCelebration ? (
        <section
          className="my-turn-celebration"
          data-testid="my-turn-celebration"
          data-turn-owner="local"
          aria-live="polite"
        >
          <div className="my-turn-celebration-particles" aria-hidden="true">
            {Array.from({ length: 14 }).map((_, index) => (
              <span
                key={index}
                className="my-turn-celebration-particle"
                style={
                  {
                    "--particle-angle": `${index * 25.7}deg`,
                    "--particle-distance": `${82 + (index % 4) * 18}px`,
                    "--particle-size": `${5 + (index % 3) * 2}px`,
                    "--particle-delay": `${index * 24}ms`,
                  } as CSSProperties
                }
              />
            ))}
          </div>
          <span className="my-turn-celebration-kicker">{locale === "ko" ? "READY" : "READY"}</span>
          <strong>{myTurnCelebrationTitle}</strong>
          <small>{myTurnCelebrationDetail}</small>
        </section>
      ) : null}

      {route !== "lobby" ? (
        <section
          data-testid="runtime-manifest-metadata"
          aria-hidden="true"
          hidden
          data-manifest-hash={manifestHash || undefined}
          data-starting-cash={manifestStartingCash || undefined}
          data-starting-shards={manifestStartingShards || undefined}
          data-dice-values={manifestDiceValues || undefined}
          data-seat-allowed={manifestSeatAllowed || undefined}
          data-board-topology={manifestTopology || undefined}
          data-tile-count={manifestTileCount || undefined}
        />
      ) : null}

      {route === "lobby" ? (
        <LobbyView
          busy={busy}
          locale={locale}
          serverBaseInput={serverBaseInput}
          serverConnected={serverConnected}
          roomTitleInput={roomTitleInput}
          nicknameInput={displayNameInput}
          hostSeatInput={hostSeatInput}
          seatTypes={seatTypes}
          activeRoom={activeRoom}
          activeRoomSeat={activeRoomSeat}
          rooms={rooms}
          notice={notice}
          error={error}
          onServerBaseInput={setServerBaseInput}
          onConnectServer={connectServer}
          onRoomTitleInput={setRoomTitleInput}
          onNicknameInput={setDisplayNameInput}
          onHostSeatInput={setHostSeatInput}
          onSeatTypeChange={onSeatTypeChange}
          onCreateRoom={onCreateRoom}
          onQuickStartHumanVsAi={onQuickStartHumanVsAi}
          onRefreshRooms={refreshRooms}
          onJoinRoom={onJoinRoom}
          onToggleReady={onToggleRoomReady}
          onStartRoom={onStartRoom}
          onLeaveRoom={onLeaveRoom}
        />
      ) : (
        <>
          <section className="match-table-layout">
            <BoardPanel
              snapshot={snapshot}
              manifestTiles={manifestTiles}
              boardTopology={boardTopology}
              tileKindLabels={tileKindLabels}
              lastMove={lastMove}
              stageFocus={turnStage}
              weather={turnStage}
              revealFocus={latestCurrentTurnReveal}
              turnBanner={boardTurnOverlay}
              showTurnOverlay={false}
              minimalHeader
              overlayContent={
                <div className="match-table-overlay">
                  <div className="match-table-overlay-top">
                    <section className="match-table-stage-header">
                      <section className="match-table-topline">
                        <article
                          className={`match-table-weather-bar${weatherExpanded ? " match-table-weather-bar-expanded" : ""}`}
                          data-testid="board-weather-summary"
                          data-weather-name={hasReadableValue(weatherHeadline) ? weatherHeadline : undefined}
                          data-weather-detail={hasReadableValue(weatherDetail) ? weatherDetail : undefined}
                          tabIndex={0}
                          onPointerEnter={() => setWeatherExpanded(true)}
                          onPointerLeave={() => setWeatherExpanded(false)}
                          onFocus={() => setWeatherExpanded(true)}
                          onBlur={() => setWeatherExpanded(false)}
                        >
                          <div className="match-table-card-head">
                            <strong>{turnStageText.weatherTitle}</strong>
                            <span>{turnStageText.weatherBadge}</span>
                          </div>
                          <div className="match-table-weather-content">
                            {weatherHudPills.length > 0 ? (
                              <div className="match-table-weather-pills">
                                {weatherHudPills.map((pill) => (
                                  <span key={pill} className="match-table-weather-pill">
                                    {pill}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                            <div
                              className="match-table-weather-main"
                              data-weather-name={hasReadableValue(weatherHeadline) ? weatherHeadline : undefined}
                              data-weather-detail={hasReadableValue(weatherDetail) ? weatherDetail : undefined}
                            >
                              <h4 data-testid="board-weather-headline">{weatherHeadline}</h4>
                              {weatherDetail ? <p data-testid="board-weather-detail">{weatherDetail}</p> : null}
                            </div>
                          </div>
                        </article>

                        <div className="match-table-player-strip" data-testid="match-player-strip">
                          {orderedSeatEntries.map((seatEntry) => {
                            const player = seatEntry.playerId !== null ? playersById.get(seatEntry.playerId) ?? null : null;
                            const playerId = seatEntry.playerId;
                            const seatType = seatEntry.seatType;
                            const seatTypeLabel = seatTypeBadgeLabel(seatType, locale);
                            const isCurrentActor =
                              playerId !== null && currentActorId !== null && playerId === currentActorId;
                            const isLocalPlayer =
                              playerId !== null && effectivePlayerId !== null && playerId === effectivePlayerId;
                            const isPromptActive = isCurrentActor && hasReadableValue(playerStageFallbackLabel);
                            const hideCharacterEmblem = shouldHideCharacterForPrompt(turnStage.promptRequestType);
                            const knownCharacterName =
                              !hideCharacterEmblem &&
                              player?.isCurrentActor &&
                              player?.currentCharacterFace &&
                              player.currentCharacterFace !== "-"
                                ? player.currentCharacterFace
                                : null;
                            const rawDisplayName =
                              player?.displayName && player.displayName !== "-" ? player.displayName : "";
                            const rawDisplayNameLooksLikeCharacter =
                              hasReadableValue(rawDisplayName) && Object.prototype.hasOwnProperty.call(characterAbilityLabels, rawDisplayName);
                            const displayName =
                              hasReadableValue(rawDisplayName) &&
                              rawDisplayName !== knownCharacterName &&
                              !rawDisplayNameLooksLikeCharacter
                                ? rawDisplayName
                                : seatType === "ai"
                                  ? `AI ${seatEntry.seat}`
                                  : `Player ${seatEntry.seat}`;
                            const characterStatus =
                              isCurrentActor && hasReadableValue(playerStageFallbackLabel)
                                ? stageInProgressLabel(playerStageFallbackLabel, locale)
                                : seatType === "ai"
                                  ? waitingPlayerLabel(locale)
                                  : seatType === "human" && !seatEntry.connected
                                    ? waitingPlayerLabel(locale)
                                    : hasReadableValue(playerStageFallbackLabel)
                                      ? waitingPlayerLabel(locale)
                                      : "-";
                            const personaHeadline = displayName;
                            const personaSupportingLine = characterStatus;
                            const privateCharacterLabel = locale === "ko" ? "비공개" : "Hidden";
                            const publicTrickNames = player?.publicTricks ?? [];
                            const rawHiddenTrickCount = Math.max(
                              player?.hiddenTrickCount ?? 0,
                              (player?.trickCount ?? 0) - publicTrickNames.length
                            );
                            const hiddenTrickCount = Math.max(0, rawHiddenTrickCount);
                            const trickPeekCardCount = publicTrickNames.length + hiddenTrickCount;
                            const shouldShowTrickPeek = trickPeekCardCount > 0;
                            const playerStats = [
                              { key: "cash", tone: "cash", label: locale === "ko" ? "현금" : "Cash", value: player?.cash ?? "-" },
                              { key: "shards", tone: "shards", label: locale === "ko" ? "조각" : "Shard", value: player?.shards ?? "-" },
                              { key: "land", tone: "land", label: locale === "ko" ? "토지" : "Land", value: player?.ownedTileCount ?? "-" },
                              { key: "trick", tone: "trick", label: locale === "ko" ? "잔꾀" : "Trick", value: player?.trickCount ?? "-" },
                              { key: "hand", tone: "coins", label: locale === "ko" ? "손승" : "Hand", value: player?.handCoins ?? "-" },
                              { key: "board", tone: "coins", label: locale === "ko" ? "배승" : "Board", value: player?.placedCoins ?? "-" },
                              { key: "score", tone: "score", label: locale === "ko" ? "총점" : "Score", value: player?.totalScore ?? "-" },
                            ] as const;
                            return (
                              <article
                                key={`${seatEntry.seat}-${playerId ?? "pending"}`}
                                data-testid={`match-player-card-${seatEntry.seat}`}
                                className={`match-table-player-card ${isCurrentActor ? "match-table-player-card-actor" : ""} ${
                                  isPromptActive ? "match-table-player-card-active-prompt" : ""
                                } ${isLocalPlayer ? "match-table-player-card-local" : ""}`}
                                tabIndex={shouldShowTrickPeek ? 0 : undefined}
                                style={{ "--player-accent": playerColor(playerId ?? seatEntry.seat) } as CSSProperties}
                              >
                                <div className="match-table-player-identity">
                                  <div
                                    className={`match-table-player-emblem ${
                                      knownCharacterName ? "match-table-player-emblem-revealed" : "match-table-player-emblem-hidden"
                                    }`}
                                    aria-label={
                                      knownCharacterName
                                        ? `${locale === "ko" ? "선택 인물" : "Selected character"} ${knownCharacterName}`
                                        : privateCharacterLabel
                                    }
                                  >
                                    {knownCharacterName ? (
                                      <span className="match-table-player-emblem-glyph">
                                        {Array.from(knownCharacterName.trim())[0] ?? "?"}
                                      </span>
                                    ) : (
                                      <img src={privateCharacterSealUrl} alt="" className="match-table-player-emblem-secret" />
                                    )}
                                  </div>
                                  <div className="match-table-player-identity-body">
                                    <div className="match-table-player-head">
                                      <div className="match-table-player-head-main">
                                        {player?.isMarkerOwner ??
                                        (playerId !== null && markerOwnerPlayerId !== null && playerId === markerOwnerPlayerId) ? (
                                          <span
                                            className="match-table-player-badge match-table-player-badge-marker"
                                            title={locale === "ko" ? "현재 징표 소유자" : "Current marker owner"}
                                          >
                                            👑
                                          </span>
                                        ) : null}
                                        {seatTypeLabel ? (
                                          <span className="match-table-player-badge match-table-player-badge-seat-type">
                                            {seatTypeLabel}
                                          </span>
                                        ) : null}
                                        {isLocalPlayer ? (
                                          <span className="match-table-player-badge match-table-player-badge-local">
                                            {localPlayerBadgeLabel(locale)}
                                          </span>
                                        ) : null}
                                      </div>
                                      <div className="match-table-player-head-side">
                                        <span>{`PLAYER ${seatEntry.seat}`}</span>
                                      </div>
                                    </div>
                                    <strong className="match-table-player-persona">{personaHeadline}</strong>
                                    <p className="match-table-player-character">{personaSupportingLine}</p>
                                  </div>
                                </div>
                                <div className="match-table-player-stats">
                                  {playerStats.map((stat) => (
                                    <small
                                      key={stat.key}
                                      className={`match-table-player-stat match-table-player-stat-${stat.tone}`}
                                      data-stat-tone={stat.tone}
                                    >
                                      <span className="match-table-player-stat-label">{stat.label}</span>
                                      <strong className="match-table-player-stat-value">{stat.value}</strong>
                                    </small>
                                  ))}
                                </div>
                                {shouldShowTrickPeek ? (
                                  <PlayerTrickPeek
                                    locale={locale}
                                    playerLabel={`P${seatEntry.seat}`}
                                    publicTricks={publicTrickNames}
                                    hiddenTrickCount={hiddenTrickCount}
                                    testId={`player-${playerId ?? seatEntry.seat}-trick-peek`}
                                  />
                                ) : null}
                              </article>
                            );
                          })}
                        </div>
                      </section>

                      <section
                        className="match-table-active-strip"
                        data-testid="active-character-strip"
                        data-known-count={String(knownActiveCharacterCount)}
                        data-slot-count={String(activeCharacterSlots.length)}
                      >
                        <div className="match-table-card-head">
                          <strong>{locale === "ko" ? "현재 활성 등장인물" : "Current active character"}</strong>
                          <span>
                            {locale === "ko"
                              ? `${knownActiveCharacterCount}/${activeCharacterSlots.length} 공개`
                              : `${knownActiveCharacterCount}/${activeCharacterSlots.length} revealed`}
                          </span>
                        </div>
                        <div className="match-table-active-character-grid">
                          {activeCharacterSlots.map((card) => (
                            <article
                              key={card.slot}
                              data-testid={`active-character-slot-${card.slot}`}
                              data-character-name={card.character ?? undefined}
                              data-inactive-character={card.inactiveCharacter ?? undefined}
                              data-slot-label={card.label ?? undefined}
                              data-player-id={card.playerId !== null ? String(card.playerId) : undefined}
                              data-is-current-actor={card.isCurrentActor ? "true" : undefined}
                              className={`match-table-active-character-card ${
                                card.isCurrentActor ? "match-table-active-character-card-actor" : ""
                              } ${card.isLocalPlayer ? "match-table-active-character-card-local" : ""} ${
                                card.character ? "" : "match-table-active-character-card-empty"
                              }`}
                              style={
                                {
                                  "--player-accent": playerColor(card.playerId ?? card.slot),
                                } as CSSProperties
                              }
                            >
                              <div className="match-table-active-character-body">
                                <div className="match-table-active-character-heading">
                                  <span className="match-table-active-character-slot">{`#${card.slot}`}</span>
                                  <strong className="match-table-active-character-name">
                                    {card.character ?? "-"}
                                  </strong>
                                </div>
                                <span
                                  className={`match-table-active-character-meta ${
                                    card.character ? "match-table-active-character-meta-active" : ""
                                  }`}
                                >
                                  {[card.inactiveCharacter, card.label, card.isCurrentActor ? currentTurnBadgeLabel(locale) : null]
                                    .filter(Boolean)
                                    .join(" · ") || "-"}
                                </span>
                              </div>
                            </article>
                          ))}
                        </div>
                      </section>
                    </section>
                  </div>
                  {hasBoardBottomDock ? (
                    <div
                      className={`match-table-overlay-middle ${
                        overlayHandCards.length > 0 ? "match-table-overlay-middle-with-hand-tray" : ""
                      }`}
                    >
                      <div className="match-table-overlay-middle-stack">
                        {hasBoardBottomDock ? (
                          <div className="match-table-prompt-wrap match-table-prompt-floating">
                            {passivePrompt ? (
                              <section className="panel passive-prompt-card match-table-passive" data-testid="passive-prompt-card">
                                <div className="passive-prompt-head">
                                  <div>
                                    <h2>{app.passivePromptTitle}</h2>
                                    <p>
                                      {app.passivePromptSummary(
                                        passivePrompt.playerId,
                                        promptLabelForType(passivePrompt.requestType),
                                        promptSecondsLeft
                                      )}
                                    </p>
                                  </div>
                                  <div className="passive-prompt-badge">
                                    <span className="spinner" aria-hidden="true" />
                                  </div>
                                </div>
                              </section>
                            ) : null}
                            {visibleActionablePrompt ? (
                              <div className="match-table-prompt-shell">
                                <PromptOverlay
                                  prompt={visibleActionablePrompt}
                                  markTargetCandidates={markTargetDisplaySlots}
                                  collapsed={promptCollapsed}
                                  busy={promptUiBusy}
                                  secondsLeft={promptSecondsLeft}
                                  feedbackMessage={promptFeedbackMessage}
                                  compactChoices={compactDensity}
                                  presentationMode="decision-focus"
                                  effectContext={promptEffectContext}
                                  onToggleCollapse={() => setPromptCollapsed((prev) => !prev)}
                                  onSelectChoice={onSelectPromptChoice}
                                />
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  {!visibleActionablePrompt && !passivePrompt ? (
                    <div className="match-table-spectator-context">
                      <SpectatorTurnPanel
                        actorPlayerId={currentActorId}
                        model={turnStage}
                        latestAction={latestCoreAction}
                      />
                      <div className="match-table-core-action-contract">
                        <CoreActionPanel items={coreActionFeed} latest={latestCoreAction} />
                      </div>
                    </div>
                  ) : null}
                  {hasPublicEventFeed ? (
                    <button
                      type="button"
                      className={`match-table-event-toggle ${publicEventFeedOpen ? "match-table-event-toggle-open" : ""}`}
                      aria-expanded={publicEventFeedOpen}
                      aria-controls="match-table-public-event-panel"
                      onClick={() => setPublicEventFeedOpen((isOpen) => !isOpen)}
                    >
                      <span className="match-table-event-toggle-track" aria-hidden="true">
                        <span className="match-table-event-toggle-thumb" />
                      </span>
                      <span className="match-table-event-toggle-label">
                        {locale === "ko" ? "공개 이벤트" : "Public events"}
                      </span>
                    </button>
                  ) : null}
                  {showPublicEventFeed ? (
                    <section className="match-table-event-overlay">
                      <section
                        id="match-table-public-event-panel"
                        className="match-table-event-stack"
                        data-testid="board-event-reveal-stack"
                      >
                        <div className="match-table-card-head">
                          <strong>{locale === "ko" ? "공개 이벤트" : "Public events"}</strong>
                          <span>{locale === "ko" ? "이번 턴 흐름" : "This turn flow"}</span>
                        </div>
	                        {effectiveEventFeedSpotlightItem
	                          ? (() => {
	                              const spotlightDetail = compactEventDetail(
	                                effectiveEventFeedSpotlightItem.label,
	                                effectiveEventFeedSpotlightItem.detail
	                              );
	                              const spotlightEffect = eventEffectForFeedItem(
	                                effectiveEventFeedSpotlightItem,
	                                turnStage.weatherName,
	                                turnStage.weatherEffect
	                              );
	                              const spotlightAttribution = eventEffectAttributionLabel(
	                                spotlightEffect,
	                                `${effectiveEventFeedSpotlightItem.label} ${effectiveEventFeedSpotlightItem.detail}`,
	                                locale
	                              );
	                              return (
	                                <article
	                                  className={`match-table-event-spotlight match-table-event-spotlight-${effectiveEventFeedSpotlightItem.tone}`}
	                                  data-testid={`board-event-spotlight-${effectiveEventFeedSpotlightItem.eventCode}`}
	                                  data-event-tone={effectiveEventFeedSpotlightItem.tone}
	                                  data-event-seq={effectiveEventFeedSpotlightItem.seq}
	                                  data-effect-source={spotlightEffect.effectSource}
	                                  data-effect-intent={spotlightEffect.effectIntent}
	                                  data-effect-enhanced={spotlightEffect.effectEnhanced ? "true" : "false"}
	                                >
                                      <span
                                        hidden
                                        aria-hidden="true"
                                        data-testid={`board-event-reveal-${effectiveEventFeedSpotlightItem.eventCode}-1`}
                                        data-event-code={effectiveEventFeedSpotlightItem.eventCode}
                                      />
	                                  <div className="match-table-event-meta">
	                                    <span className={`match-table-event-tone match-table-event-tone-${effectiveEventFeedSpotlightItem.tone}`}>
	                                      <span className="match-table-event-icon" aria-hidden="true">
	                                        {eventToneIcon(effectiveEventFeedSpotlightItem.tone)}
	                                      </span>
	                                      <span>{eventToneLabel(effectiveEventFeedSpotlightItem.tone, locale)}</span>
	                                    </span>
	                                    {spotlightAttribution ? (
	                                      <span
	                                        className="match-table-event-attribution"
	                                        data-testid={`board-event-attribution-${effectiveEventFeedSpotlightItem.eventCode}`}
	                                      >
	                                        {spotlightAttribution}
	                                      </span>
	                                    ) : null}
	                                    <span className="match-table-event-live-badge">
	                                      {latestCurrentTurnReveal
	                                        ? locale === "ko"
                                          ? "방금 결과"
                                          : "Latest result"
                                        : locale === "ko"
                                          ? "최근 결과"
                                          : "Recent result"}
                                    </span>
                                  </div>
                                  <strong
                                    className="match-table-event-spotlight-title"
                                    data-testid={`board-event-spotlight-title-${effectiveEventFeedSpotlightItem.eventCode}`}
                                  >
                                    {effectiveEventFeedSpotlightItem.label}
                                  </strong>
                                  {spotlightDetail ? (
                                    <p
                                      className="match-table-event-spotlight-detail"
                                      data-testid={`board-event-spotlight-detail-${effectiveEventFeedSpotlightItem.eventCode}`}
                                    >
                                      {spotlightDetail}
                                    </p>
                                  ) : null}
                                </article>
                              );
                            })()
                          : null}
	                        {eventFeedHistoryItems.length > 0 ? (
	                          <div className="match-table-event-list match-table-event-history">
	                            {eventFeedHistoryItems.map((item, index) => {
	                              const itemDetail = compactEventDetail(item.label, item.detail);
	                              const itemEffect = eventEffectForFeedItem(item, turnStage.weatherName, turnStage.weatherEffect);
	                              const itemAttribution = eventEffectAttributionLabel(
	                                itemEffect,
	                                `${item.label} ${item.detail}`,
	                                locale
	                              );
	                              return (
	                                <article
	                                  key={`${item.seq}-${item.eventCode}`}
	                                  data-testid={`board-event-reveal-${item.eventCode}-${index + 1}`}
	                                  data-event-code={item.eventCode}
	                                  data-event-tone={item.tone}
	                                  data-event-seq={item.seq}
	                                  data-effect-source={itemEffect.effectSource}
	                                  data-effect-intent={itemEffect.effectIntent}
	                                  data-effect-enhanced={itemEffect.effectEnhanced ? "true" : "false"}
	                                  className={`match-table-event-card match-table-event-card-${item.tone}`}
	                                  style={{ "--event-order": String(index + 1) } as CSSProperties}
	                                >
                                  <div className="match-table-event-meta">
                                    <span className={`match-table-event-tone match-table-event-tone-${item.tone}`}>
                                      <span className="match-table-event-icon" aria-hidden="true">
                                        {eventToneIcon(item.tone)}
                                      </span>
                                      <span>{eventToneLabel(item.tone, locale)}</span>
                                    </span>
	                                    <span className="match-table-event-index">
	                                      {locale === "ko" ? `${index + 1}단계` : `Step ${index + 1}`}
	                                    </span>
	                                  </div>
	                                  {itemAttribution ? (
	                                    <span
	                                      className="match-table-event-attribution match-table-event-attribution-inline"
	                                      data-testid={`board-event-reveal-attribution-${item.eventCode}-${index + 1}`}
	                                    >
	                                      {itemAttribution}
	                                    </span>
	                                  ) : null}
	                                  <div className="match-table-event-headline-row">
	                                    <strong data-testid={`board-event-reveal-title-${item.eventCode}-${index + 1}`}>{item.label}</strong>
	                                  </div>
                                  {itemDetail ? <p data-testid={`board-event-reveal-detail-${item.eventCode}-${index + 1}`}>{itemDetail}</p> : null}
                                </article>
                              );
                            })}
                          </div>
                        ) : null}
                      </section>
                    </section>
                  ) : null}
                  {overlayHandCards.length > 0 ? (
                    <div className="match-table-overlay-bottom">
                      <div className="match-table-hand-shell">
                        <section
                          className={`match-table-hand-tray match-table-hand-tray-docked ${
                            overlayHandSubtitle ? "" : "match-table-hand-tray-minimal"
                          }`}
                          data-testid="board-hand-tray"
                        >
                          <div className="match-table-hand-tray-head">
                            <strong>{overlayHandTitle}</strong>
                            {overlayHandSubtitle ? <small>{overlayHandSubtitle}</small> : null}
                          </div>
                          <div
                            className="match-table-hand-tray-grid"
                            style={
                              {
                                "--hand-card-columns": 6,
                              } as CSSProperties
                            }
                          >
                            {overlayHandCards.map((card) => (
                              <article
                                key={card.key}
                                className={`match-table-hand-card ${card.hidden ? "match-table-hand-card-hidden" : ""} ${
                                  card.currentTarget ? "match-table-hand-card-current" : ""
                                }`}
                              >
                                <div className="match-table-hand-card-top">
                                  <strong>{card.title}</strong>
                                  <span className="match-table-hand-card-badge">
                                    {card.hidden ? (locale === "ko" ? "히든" : "Hidden") : ""}
                                  </span>
                                </div>
                                <p className="match-table-hand-card-effect">{card.effect}</p>
                              </article>
                            ))}
                          </div>
                        </section>
                      </div>
                    </div>
                  ) : null}
                </div>
              }
            />
          </section>

          <GameEventOverlay currentEvent={eventQueue.currentEvent} />
        </>
      )}
    </main>
  );
}
