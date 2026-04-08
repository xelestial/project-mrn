import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { mergeSessionManifest } from "./domain/manifest/manifestRehydrate";
import {
  characterAbilityLabelsFromManifestLabels,
  tileKindLabelsFromManifestLabels,
} from "./domain/labels/manifestLabelCatalog";
import { promptLabelForType } from "./domain/labels/promptTypeCatalog";
import { selectActivePrompt, selectLatestDecisionAck } from "./domain/selectors/promptSelectors";
import {
  selectCoreActionFeed,
  selectLastMove,
  selectLatestManifest,
  selectLiveSnapshot,
  selectLivePlayers,
  selectTimeline,
  selectTurnStage,
} from "./domain/selectors/streamSelectors";
import { BoardPanel } from "./features/board/BoardPanel";
import { LobbyView, type LobbySeatType } from "./features/lobby/LobbyView";
import { PromptOverlay } from "./features/prompt/PromptOverlay";
import { CoreActionPanel } from "./features/theater/CoreActionPanel";
import { useGameStream } from "./hooks/useGameStream";
import { useI18n } from "./i18n/useI18n";
import type { InboundMessage } from "./core/contracts/stream";
import {
  createSession,
  getRuntimeStatus,
  getSession,
  joinSession,
  listSessions,
  startSession,
  type ParameterManifest,
  type PublicSessionResult,
  type RuntimeStatusResult,
} from "./infra/http/sessionApi";

type ViewRoute = "lobby" | "match";

const LOBBY_HASH = "#/lobby";
const MATCH_HASH = "#/match";
const SESSION_TOKEN_STORAGE_PREFIX = "mrn:sessionToken:";
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

function findCurrentActorId(messages: Array<{ payload: Record<string, unknown> }>): number | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = messages[i].payload;
    const acting = payload["acting_player_id"] ?? payload["player_id"];
    if (typeof acting === "number") {
      return acting;
    }
  }
  return null;
}

function shouldHideCharacterForPrompt(requestType: string): boolean {
  return requestType === "draft_card" || requestType === "final_character";
}

function hasReadableValue(value: string | null | undefined): boolean {
  return typeof value === "string" && value.trim() !== "" && value.trim() !== "-";
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
  return isKoreanLocale(locale) ? "[나]" : "[Me]";
}

function currentTurnBadgeLabel(locale: string): string {
  return isKoreanLocale(locale) ? "현재 차례" : "Current turn";
}

type OverlayHandCard = {
  key: string;
  title: string;
  effect: string;
  serial: string;
  hidden: boolean;
  selected?: boolean;
  currentTarget?: boolean;
};

function nonEmptyText(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function handCardsFromPublicContext(publicContext: Record<string, unknown>, locale: string): OverlayHandCard[] {
  const fullHand = Array.isArray(publicContext["full_hand"]) ? publicContext["full_hand"] : [];
  if (fullHand.length > 0) {
    return fullHand.flatMap((item, index) => {
        if (!item || typeof item !== "object") {
          return [];
        }
        const row = item as Record<string, unknown>;
        const deckIndex = typeof row["deck_index"] === "number" ? row["deck_index"] : null;
        const title = nonEmptyText(row["name"]) || (locale === "ko" ? "잔꾀" : "Trick");
        const effect = nonEmptyText(row["card_description"]) || (locale === "ko" ? "효과 없음" : "No effect text");
        const hidden = row["is_hidden"] === true;
        const isCurrentTarget = row["is_current_target"] === true;
        return [{
          key: `${deckIndex ?? index}-${title}`,
          title,
          effect,
          serial: deckIndex === null ? "" : `#${deckIndex}`,
          hidden,
          currentTarget: isCurrentTarget,
        }];
      });
  }

  const burdenCards = Array.isArray(publicContext["burden_cards"]) ? publicContext["burden_cards"] : [];
  if (burdenCards.length > 0) {
    return burdenCards.flatMap((item, index) => {
        if (!item || typeof item !== "object") {
          return [];
        }
        const row = item as Record<string, unknown>;
        const deckIndex = typeof row["deck_index"] === "number" ? row["deck_index"] : null;
        const burdenCost = typeof row["burden_cost"] === "number" ? row["burden_cost"] : null;
        const title = nonEmptyText(row["name"]) || (locale === "ko" ? "짐" : "Burden");
        const effectBase = nonEmptyText(row["card_description"]) || (locale === "ko" ? "효과 없음" : "No effect text");
        const effect =
          burdenCost === null
            ? effectBase
            : locale === "ko"
              ? `${effectBase} / 제거 비용 ${burdenCost}`
              : `${effectBase} / remove cost ${burdenCost}`;
        return [{
          key: `${deckIndex ?? index}-${title}`,
          title,
          effect,
          serial: deckIndex === null ? "" : `#${deckIndex}`,
          hidden: false,
          currentTarget: row["is_current_target"] === true,
        }];
      });
  }

  return [];
}

function currentHandCardsFromMessages(
  messages: InboundMessage[],
  prompt: ReturnType<typeof selectActivePrompt>,
  locale: string,
  playerId: number | null
): OverlayHandCard[] {
  if (prompt) {
    const currentPromptCards = handCardsFromPublicContext(prompt.publicContext, locale);
    if (currentPromptCards.length > 0) {
      return currentPromptCards;
    }
  }

  const preferredPlayerId = prompt?.playerId ?? playerId;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "prompt") {
      continue;
    }
    const messagePlayerId = typeof message.payload["player_id"] === "number" ? message.payload["player_id"] : null;
    if (preferredPlayerId !== null && messagePlayerId !== preferredPlayerId) {
      continue;
    }
    const publicContext =
      message.payload["public_context"] && typeof message.payload["public_context"] === "object"
        ? (message.payload["public_context"] as Record<string, unknown>)
        : null;
    if (!publicContext) {
      continue;
    }
    const persistedCards = handCardsFromPublicContext(publicContext, locale);
    if (persistedCards.length > 0) {
      return persistedCards;
    }
  }

  return [];
}

const CHARACTER_PRIORITY: Record<string, number> = {
  어사: 1,
  탐관오리: 1,
  자객: 2,
  산적: 2,
  추노꾼: 3,
  "탈출 노비": 3,
  파발꾼: 4,
  아전: 4,
  "교리 연구관": 5,
  "교리 감독관": 5,
  박수: 6,
  만신: 6,
  객주: 7,
  중매꾼: 7,
  건설업자: 8,
  사기꾼: 8,
};

function findLatestRoundOrder(messages: Array<{ payload: Record<string, unknown> }>): number[] | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const payload = messages[i].payload;
    if (payload["event_type"] !== "round_order") {
      continue;
    }
    const rawOrder = payload["order"];
    if (!Array.isArray(rawOrder)) {
      continue;
    }
    const order = rawOrder.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    if (order.length > 0) {
      return order;
    }
  }
  return null;
}

function deriveRoundOrderFromPlayers(
  visibleSeatIds: number[],
  playersById: Map<number, { character: string }>
): number[] | null {
  const ordered = visibleSeatIds
    .map((playerId) => {
      const character = playersById.get(playerId)?.character ?? "-";
      const priority = CHARACTER_PRIORITY[character];
      return { playerId, priority: typeof priority === "number" ? priority : Number.POSITIVE_INFINITY };
    })
    .filter((entry) => Number.isFinite(entry.priority))
    .sort((a, b) => (a.priority === b.priority ? a.playerId - b.playerId : a.priority - b.priority))
    .map((entry) => entry.playerId);
  return ordered.length > 0 ? ordered : null;
}

function orderSeatIdsForDisplay(visibleSeatIds: number[], roundOrder: number[] | null): number[] {
  const ordered = roundOrder ? roundOrder.filter((playerId) => visibleSeatIds.includes(playerId)) : [...visibleSeatIds];
  const remaining = visibleSeatIds.filter((playerId) => !ordered.includes(playerId));
  return [...ordered, ...remaining];
}

export function App() {
  const { app, eventLabel, promptType, stream: streamText, turnStage: turnStageText, locale, setLocale } = useI18n();
  const [route, setRoute] = useState<ViewRoute>(() => parseHashState(window.location.hash).route);
  const [sessionInput, setSessionInput] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [token, setToken] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeStatusResult["runtime"]>({ status: "-" });
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [seatTypes, setSeatTypes] = useState<LobbySeatType[]>(["human", "ai", "ai", "ai"]);
  const [seatCountInput, setSeatCountInput] = useState("4");
  const [aiProfile, setAiProfile] = useState("balanced");
  const [seedInput, setSeedInput] = useState("");
  const [hostTokenInput, setHostTokenInput] = useState("");
  const [lastJoinTokens, setLastJoinTokens] = useState<Record<string, string>>({});
  const [joinSeatInput, setJoinSeatInput] = useState("1");
  const [joinTokenInput, setJoinTokenInput] = useState("");
  const [displayNameInput, setDisplayNameInput] = useState("Player");
  const [sessions, setSessions] = useState<PublicSessionResult[]>([]);
  const [sessionManifest, setSessionManifest] = useState<ParameterManifest | null>(null);
  const [localPlayerId, setLocalPlayerId] = useState<number | null>(null);
  const inferredPlayerId = inferPlayerIdFromSessionToken(token);
  const effectivePlayerId = localPlayerId ?? inferredPlayerId;

  const [compactDensity, setCompactDensity] = useState(false);
  const [showRawMessages, setShowRawMessages] = useState(false);
  const [promptCollapsed, setPromptCollapsed] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptRequestId, setPromptRequestId] = useState("");
  const [promptExpiresAtMs, setPromptExpiresAtMs] = useState<number | null>(null);
  const [promptFeedback, setPromptFeedback] = useState("");
  const [activeFlipQueuedChoiceIds, setActiveFlipQueuedChoiceIds] = useState<string[]>([]);
  const [activeFlipShouldFinish, setActiveFlipShouldFinish] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [turnBanner, setTurnBanner] = useState<{ seq: number; text: string; detail: string } | null>(null);
  const debugWindowRef = useRef<Window | null>(null);

  const stream = useGameStream({ sessionId, token });
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
  const latestCoreAction = coreActionFeed.find((item) => !item.isLocalActor) ?? coreActionFeed[0] ?? null;
  const turnStage = selectTurnStage(stream.messages, selectorText);
  const snapshot = selectLiveSnapshot(stream.messages, selectorText);
  const livePlayers = selectLivePlayers(stream.messages, selectorText);
  const lastMove = selectLastMove(stream.messages);
  const latestManifest = selectLatestManifest(stream.messages);

  const currentActorId = findCurrentActorId(stream.messages);
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
  const boardTurnOverlay =
    currentActorId !== null && currentActorText !== "-"
      ? {
          text: app.turnBanner(currentActorText),
          detail: boardTurnOverlayDetail,
        }
      : null;

  const activePrompt = selectActivePrompt(stream.messages);
  const canActOnPrompt = Boolean(activePrompt && token && effectivePlayerId !== null && activePrompt.playerId === effectivePlayerId);
  const actionablePrompt = canActOnPrompt ? activePrompt : null;
  const passivePrompt = activePrompt && !canActOnPrompt ? activePrompt : null;
  const waitingForMyPrompt = isMyTurn && !actionablePrompt && !promptBusy;
  const latestPromptAck = selectLatestDecisionAck(stream.messages, actionablePrompt?.requestId ?? promptRequestId);
  const promptSecondsLeft =
    promptExpiresAtMs === null ? null : Math.max(0, Math.ceil((promptExpiresAtMs - nowMs) / 1000));

  const playersById = useMemo(() => {
    const map = new Map<number, (typeof livePlayers)[number]>();
    for (const player of livePlayers) {
      map.set(player.playerId, player);
    }
    return map;
  }, [livePlayers]);

  const visibleSeatIds = useMemo(() => {
    return [1, 2, 3, 4];
  }, []);
  const latestRoundOrder = useMemo(() => findLatestRoundOrder(stream.messages), [stream.messages]);
  const derivedRoundOrder = useMemo(
    () => deriveRoundOrderFromPlayers(visibleSeatIds, playersById),
    [playersById, visibleSeatIds]
  );
  const effectiveRoundOrder = latestRoundOrder ?? derivedRoundOrder;
  const orderedSeatIds = useMemo(
    () => orderSeatIdsForDisplay(visibleSeatIds, effectiveRoundOrder),
    [effectiveRoundOrder, visibleSeatIds]
  );

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
    ownerPlayerId: null,
    pawnPlayerIds: [],
  }));
  const boardTopology = sessionManifest?.board?.topology ?? "ring";
  const tileKindLabels = tileKindLabelsFromManifestLabels(sessionManifest?.labels);
  const characterAbilityLabels = characterAbilityLabelsFromManifestLabels(sessionManifest?.labels);
  const activeCharacterAbility =
    turnStage.character && turnStage.character !== "-" ? characterAbilityLabels[turnStage.character] ?? "-" : "-";
  const tableSceneTitle = hasReadableValue(turnStage.currentBeatLabel)
    ? turnStage.currentBeatLabel
    : isMyTurn
      ? app.myTurnWaitingTitle
      : app.spectatorHeadline;
  const tableSceneDetail = hasReadableValue(turnStage.currentBeatDetail)
    ? turnStage.currentBeatDetail
    : hasReadableValue(turnStage.promptSummary)
      ? turnStage.promptSummary
      : latestCoreAction?.detail ?? "-";
  const tableSceneSupport = hasReadableValue(activeCharacterAbility) ? activeCharacterAbility : turnStageText.promptIdle;
  const currentPromptLabel = actionablePrompt ? promptLabelForType(actionablePrompt.requestType) : null;
  const overlayHandCards = useMemo(
    () => currentHandCardsFromMessages(stream.messages, actionablePrompt, locale, effectivePlayerId),
    [stream.messages, actionablePrompt, locale, effectivePlayerId]
  );
  const overlayHandTitle = locale === "ko" ? "현재 잔꾀 패" : "Current trick hand";
  const overlayHandSubtitle =
    actionablePrompt?.requestType === "burden_exchange"
      ? locale === "ko"
        ? "처리할 짐 카드를 확인하고 아래 패에서 대상을 고르세요."
        : "Check the current burden and use the tray below to pick the target card."
      : locale === "ko"
        ? "이름과 효과를 같이 보면서 현재 손패를 확인합니다."
        : "Keep the current hand visible with both name and effect text.";
  const decisionWaitingTitle = currentPromptLabel && currentPromptLabel !== "-" ? currentPromptLabel : tableSceneTitle;
  const decisionWaitingLines = Array.from(
    new Set(
      [
        tableSceneDetail,
        hasReadableValue(turnStage.diceSummary) ? turnStage.diceSummary : null,
        hasReadableValue(turnStage.moveSummary) ? turnStage.moveSummary : null,
        hasReadableValue(turnStage.landingSummary) ? turnStage.landingSummary : null,
        hasReadableValue(tableSceneSupport) ? tableSceneSupport : null,
      ].filter((value): value is string => hasReadableValue(value))
    )
  );
  const playerStageFallbackLabel =
    currentPromptLabel && currentPromptLabel !== "-"
      ? currentPromptLabel
      : hasReadableValue(turnStage.currentBeatLabel)
        ? turnStage.currentBeatLabel
        : "-";
  const activeCharacterSlots = useMemo(
    () =>
      Array.from({ length: 8 }, (_, index) => {
        const slot = index + 1;
        const owner = orderedSeatIds
          .map((playerId) => {
            const player = playersById.get(playerId);
            if (!player || !hasReadableValue(player.character) || player.character === "-") {
              return null;
            }
            return {
              playerId,
              player,
              priority: CHARACTER_PRIORITY[player.character] ?? Number.POSITIVE_INFINITY,
            };
          })
          .find((entry): entry is NonNullable<typeof entry> => entry !== null && entry.priority === slot);
        return {
          slot,
          playerId: owner?.playerId ?? null,
          label: owner ? `P${owner.playerId}` : null,
          character: owner?.player.character ?? null,
          ability: owner?.player.character ? characterAbilityLabels[owner.player.character] ?? "-" : null,
          isCurrentActor: owner?.playerId === currentActorId,
          isLocalPlayer: owner?.playerId === effectivePlayerId,
        };
      }),
    [orderedSeatIds, playersById, characterAbilityLabels, currentActorId, effectivePlayerId]
  );

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
        const runtimeState = await getRuntimeStatus(sessionId.trim());
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
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId.trim()) {
      setSessionManifest(null);
      return;
    }
    let active = true;
    void getSession({ sessionId: sessionId.trim() })
      .then((data) => {
        if (active) {
          setSessionManifest(data.parameter_manifest ?? null);
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
      setActiveFlipQueuedChoiceIds([]);
      setActiveFlipShouldFinish(false);
      return;
    }
    if (actionablePrompt.requestId !== promptRequestId) {
      setPromptBusy(false);
      setPromptCollapsed(false);
      setPromptRequestId(actionablePrompt.requestId);
      setPromptExpiresAtMs(Date.now() + actionablePrompt.timeoutMs);
      setPromptFeedback("");
    }
  }, [actionablePrompt, promptRequestId]);

  useEffect(() => {
    if (!promptBusy || !latestPromptAck) {
      return;
    }
    if (latestPromptAck.status !== "rejected" && latestPromptAck.status !== "stale") {
      return;
    }
    setPromptBusy(false);
    setActiveFlipQueuedChoiceIds([]);
    setActiveFlipShouldFinish(false);
    if (latestPromptAck.status === "rejected") {
      setPromptFeedback(app.errors.promptRejected(latestPromptAck.reason));
      return;
    }
    setPromptFeedback(app.errors.promptStale(latestPromptAck.reason));
  }, [latestPromptAck, promptBusy]);

  useEffect(() => {
    if (!actionablePrompt || promptBusy || promptSecondsLeft !== 0) {
      return;
    }
    setPromptFeedback(app.errors.promptTimedOut);
  }, [actionablePrompt, promptBusy, promptSecondsLeft]);

  useEffect(() => {
    if (!promptBusy) {
      return;
    }
    if (stream.status === "connected" || stream.status === "connecting") {
      return;
    }
    setPromptBusy(false);
    setActiveFlipQueuedChoiceIds([]);
    setActiveFlipShouldFinish(false);
    setPromptFeedback(app.errors.promptConnectionLost);
  }, [promptBusy, stream.status]);

  useEffect(() => {
    if (!actionablePrompt || promptBusy || actionablePrompt.requestType !== "active_flip") {
      return;
    }
    if (activeFlipQueuedChoiceIds.length > 0) {
      const [nextChoiceId, ...rest] = activeFlipQueuedChoiceIds;
      const sent = stream.sendDecision({
        requestId: actionablePrompt.requestId,
        playerId: actionablePrompt.playerId,
        choiceId: nextChoiceId,
        choicePayload: {},
      });
      if (!sent) {
        setPromptFeedback(app.errors.sendPrompt);
        setActiveFlipQueuedChoiceIds([]);
        setActiveFlipShouldFinish(false);
        return;
      }
      setActiveFlipQueuedChoiceIds(rest);
      setPromptBusy(true);
      return;
    }
    if (!activeFlipShouldFinish) {
      return;
    }
    const sent = stream.sendDecision({
      requestId: actionablePrompt.requestId,
      playerId: actionablePrompt.playerId,
      choiceId: "none",
      choicePayload: {},
    });
    if (!sent) {
      setPromptFeedback(app.errors.sendPrompt);
      setActiveFlipShouldFinish(false);
      return;
    }
    setActiveFlipShouldFinish(false);
    setPromptBusy(true);
  }, [actionablePrompt, activeFlipQueuedChoiceIds, activeFlipShouldFinish, promptBusy, stream, app.errors]);

  useEffect(() => {
    if (turnStage.turnStartSeq === null || turnStage.actor === "-") {
      return;
    }
    const actorText = turnStage.character && turnStage.character !== "-" ? `${turnStage.actor} (${turnStage.character})` : turnStage.actor;
    setTurnBanner({
      seq: turnStage.turnStartSeq,
      text: app.turnBanner(actorText),
      detail: turnStage.currentBeatLabel !== "-" ? turnStage.currentBeatLabel : turnStage.weatherName,
    });
    const timer = window.setTimeout(() => {
      setTurnBanner((prev) => (prev?.seq === turnStage.turnStartSeq ? null : prev));
    }, isMyTurn ? 5000 : 3200);
    return () => window.clearTimeout(timer);
  }, [app, isMyTurn, turnStage.actor, turnStage.character, turnStage.currentBeatLabel, turnStage.turnStartSeq, turnStage.weatherName]);

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
    if (!showRawMessages) {
      if (debugWindowRef.current && !debugWindowRef.current.closed) {
        debugWindowRef.current.close();
      }
      debugWindowRef.current = null;
      return;
    }
    const popup =
      debugWindowRef.current && !debugWindowRef.current.closed
        ? debugWindowRef.current
        : window.open("", "mrn-debug-log", "width=900,height=960,resizable=yes,scrollbars=yes");
    if (!popup) {
      setShowRawMessages(false);
      return;
    }
    debugWindowRef.current = popup;
    const timelineMarkup = timeline
      .map(
        (item) => `
          <article class="debug-timeline-item">
            <strong>#${item.seq} ${escapeDebugHtml(item.label)}</strong>
            <p>${escapeDebugHtml(item.detail)}</p>
          </article>
        `
      )
      .join("");
    const rawMarkup = stream.messages
      .slice()
      .reverse()
      .map((message) => `<pre>${escapeDebugHtml(JSON.stringify(message, null, 2))}</pre>`)
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
            main { display: grid; grid-template-columns: 320px 1fr; min-height: 100vh; }
            aside { border-right: 1px solid #203a63; padding: 16px; background: #0a1730; overflow: auto; }
            section { padding: 16px; overflow: auto; }
            h1, h2 { margin: 0 0 12px; font-family: "Noto Sans KR", sans-serif; }
            .meta { margin-bottom: 16px; color: #a9bbdf; font-family: "Noto Sans KR", sans-serif; }
            .debug-timeline-item { padding: 10px; border-radius: 10px; background: #0d1f3d; border: 1px solid #274679; margin-bottom: 8px; }
            .debug-timeline-item strong { display: block; color: #ffda77; margin-bottom: 6px; }
            .debug-timeline-item p { margin: 0; color: #d7e5ff; font-family: "Noto Sans KR", sans-serif; line-height: 1.5; }
            pre { margin: 0 0 10px; padding: 12px; border-radius: 10px; background: #091427; border: 1px solid #203a63; white-space: pre-wrap; word-break: break-word; }
          </style>
        </head>
        <body>
          <main>
            <aside>
              <h1>Debug Log</h1>
              <div class="meta">session=${escapeDebugHtml(sessionId || "-")} / runtime=${escapeDebugHtml(runtime.status)} / seq=${stream.lastSeq}</div>
              <h2>Timeline</h2>
              ${timelineMarkup || "<p>-</p>"}
            </aside>
            <section>
              <h2>Raw Messages (${stream.messages.length})</h2>
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
  }, [locale, runtime.status, sessionId, showRawMessages, stream.lastSeq, stream.messages, timeline]);

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
    if (!actionablePrompt || promptBusy) {
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
      const [firstChoiceId, ...restChoiceIds] = requestedIds;
      const sent = stream.sendDecision({
        requestId: actionablePrompt.requestId,
        playerId: actionablePrompt.playerId,
        choiceId: firstChoiceId,
        choicePayload: {},
      });
      if (!sent) {
        setPromptFeedback(app.errors.sendPrompt);
        return;
      }
      setActiveFlipQueuedChoiceIds(restChoiceIds);
      setActiveFlipShouldFinish(true);
      setPromptBusy(true);
      return;
    }
    setPromptFeedback("");
    setActiveFlipQueuedChoiceIds([]);
    setActiveFlipShouldFinish(false);
    const sent = stream.sendDecision({
      requestId: actionablePrompt.requestId,
      playerId: actionablePrompt.playerId,
      choiceId,
      choicePayload: {},
    });
    if (!sent) {
      setPromptFeedback(app.errors.sendPrompt);
      return;
    }
    setPromptBusy(true);
  };

  const myStatusLabel = isMyTurn ? turnStageText.myTurn : turnStageText.observing;

  return (
    <main className={`page ${compactDensity ? "page-compact" : ""} ${route === "match" ? "page-match" : ""}`}>
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
            <strong>{sessionId ? `Session ${sessionId}` : app.topSummaryEmpty}</strong>
            <small>{`${runtime.status} · ${currentActorText !== "-" ? currentActorText : app.topSummaryEmpty}`}</small>
          </div>
          <div className="match-global-right">
            <span className={`match-global-status ${isMyTurn ? "match-global-status-my-turn" : ""}`}>{myStatusLabel}</span>
            <div className="match-global-actions">
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
              <button type="button" className="route-tab" onClick={() => setShowRawMessages((prev) => !prev)}>
                {showRawMessages ? app.rawHide : app.rawShow}
              </button>
            </div>
          </div>
        </header>
      )}

      {route === "lobby" ? (
        <LobbyView
          busy={busy}
          seedInput={seedInput}
          seatCountInput={seatCountInput}
          aiProfile={aiProfile}
          seatTypes={seatTypes}
          sessionInput={sessionInput}
          hostTokenInput={hostTokenInput}
          joinSeatInput={joinSeatInput}
          joinSeatOptions={joinSeatOptions.length > 0 ? joinSeatOptions : seatTypes.map((_, index) => String(index + 1))}
          joinTokenInput={joinTokenInput}
          displayNameInput={displayNameInput}
          tokenInput={tokenInput}
          notice={notice}
          error={error}
          lastJoinTokens={lastJoinTokens}
          sessions={sessions}
          onSeedInput={setSeedInput}
          onSeatCountInput={setSeatCountInput}
          onAiProfile={setAiProfile}
          onSeatTypeChange={onSeatTypeChange}
          onCreateCustomSession={onCreateCustomSession}
          onCreateAndStartAi={onCreateAndStartAi}
          onQuickStartHumanVsAi={onQuickStartHumanVsAi}
          onSessionInput={setSessionInput}
          onHostTokenInput={setHostTokenInput}
          onStartByHostToken={onStartByHostToken}
          onJoinSeatInput={setJoinSeatInput}
          onJoinTokenInput={setJoinTokenInput}
          onDisplayNameInput={setDisplayNameInput}
          onJoinSeat={onJoinSeat}
          onUseToken={(seat, value) => {
            setJoinSeatInput(seat);
            setJoinTokenInput(value);
          }}
          onConnect={onConnect}
          onTokenInput={setTokenInput}
          onRefreshSessions={refreshSessions}
          onUseSession={onUseSession}
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
              turnBanner={boardTurnOverlay}
              showTurnOverlay={false}
              minimalHeader
              overlayContent={
                <div className="match-table-overlay">
                  {turnBanner ? (
                    <section className="match-table-turn-banner" data-testid="turn-notice-banner">
                      <strong>{turnBanner.text}</strong>
                      {turnBanner.detail && turnBanner.detail !== "-" ? <small>{turnBanner.detail}</small> : null}
                    </section>
                  ) : null}
                  <section className="match-table-topline">
                    <article className="match-table-weather-bar" data-testid="board-weather-summary">
                      <div className="match-table-card-head">
                        <strong>{turnStageText.weatherTitle}</strong>
                        <span>{turnStageText.weatherBadge}</span>
                      </div>
                      <div className="match-table-weather-content">
                        <div className="match-table-weather-main">
                          <h4>{turnStage.weatherName}</h4>
                          <p>{turnStage.weatherEffect}</p>
                        </div>
                        <div className="match-table-weather-active">
                          <div className="match-table-card-head">
                            <strong>{locale === "ko" ? "현재 활성 등장인물" : "Current active character"}</strong>
                            <span>{locale === "ko" ? "인물" : "Character"}</span>
                          </div>
                          <div className="match-table-active-character-grid">
                            {activeCharacterSlots.map((card) => (
                              <article
                                key={card.slot}
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
                                <div className="match-table-active-character-head">
                                  <strong>{locale === "ko" ? `${card.slot}번` : `#${card.slot}`}</strong>
                                  {card.label ? <span className="match-table-active-character-owner">{card.label}</span> : null}
                                  {card.isLocalPlayer ? (
                                    <span className="match-table-player-badge match-table-player-badge-local">
                                      {localPlayerBadgeLabel(locale)}
                                    </span>
                                  ) : null}
                                  {card.isCurrentActor ? (
                                    <span className="match-table-player-badge match-table-player-badge-actor">
                                      {currentTurnBadgeLabel(locale)}
                                    </span>
                                  ) : null}
                                </div>
                                <h5>
                                  {card.character ?? (locale === "ko" ? "아직 선택하지 않았습니다" : "Not selected yet")}
                                </h5>
                                <p>{card.character ? card.ability : locale === "ko" ? "미선택" : "Unselected"}</p>
                              </article>
                            ))}
                          </div>
                        </div>
                      </div>
                    </article>

                    <div className="match-table-player-strip" data-testid="match-player-strip">
                      {orderedSeatIds.map((playerId) => {
                        const player = playersById.get(playerId) ?? null;
                        const isCurrentActor = playerId === currentActorId;
                        const isLocalPlayer = playerId === effectivePlayerId;
                        const characterLabel =
                          player?.character && player.character !== "-"
                            ? player.character
                            : isCurrentActor && hasReadableValue(playerStageFallbackLabel)
                              ? stageInProgressLabel(playerStageFallbackLabel, locale)
                              : hasReadableValue(playerStageFallbackLabel)
                                ? waitingPlayerLabel(locale)
                                : "-";
                        const displayName = player?.displayName && player.displayName !== "-" ? player.displayName : `Player ${playerId}`;
                        return (
                          <article
                            key={playerId}
                            className={`match-table-player-card ${isCurrentActor ? "match-table-player-card-actor" : ""} ${
                              isLocalPlayer ? "match-table-player-card-local" : ""
                            }`}
                            style={{ "--player-accent": playerColor(playerId) } as CSSProperties}
                          >
                            <div className="match-table-player-head">
                              <div className="match-table-player-head-main">
                                <strong>{`P${playerId}`}</strong>
                                {playerId === markerOwnerPlayerId ? (
                                  <span
                                    className="match-table-player-badge match-table-player-badge-marker"
                                    title={locale === "ko" ? "현재 징표 소유자" : "Current marker owner"}
                                  >
                                    👑
                                  </span>
                                ) : null}
                                {isLocalPlayer ? (
                                  <span className="match-table-player-badge match-table-player-badge-local">
                                    {localPlayerBadgeLabel(locale)}
                                  </span>
                                ) : null}
                                {isCurrentActor ? (
                                  <span className="match-table-player-badge match-table-player-badge-actor">
                                    {currentTurnBadgeLabel(locale)}
                                  </span>
                                ) : null}
                              </div>
                              <span>{displayName}</span>
                            </div>
                            <p className="match-table-player-character">{characterLabel}</p>
                            <div className="match-table-player-stats">
                              <small>{`현금 ${player?.cash ?? "-"}`}</small>
                              <small>{`조각 ${player?.shards ?? "-"}`}</small>
                              <small>{`토지 ${player?.ownedTileCount ?? "-"}`}</small>
                              <small>{`잔꾀 ${player?.hiddenTrickCount ?? "-"}`}</small>
                              <small>{`손승점 ${player?.handCoins ?? "-"}`}</small>
                              <small>{`배치승점 ${player?.placedCoins ?? "-"}`}</small>
                              <small>{`총점 ${player?.totalScore ?? "-"}`}</small>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </section>

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

                  <div className="match-table-prompt-wrap">
                    {waitingForMyPrompt ? (
                      <section className="panel waiting-panel match-table-waiting" data-testid="my-turn-waiting-panel">
                        <div className="waiting-panel-head">
                          <div>
                            <h2>{decisionWaitingTitle}</h2>
                            {decisionWaitingLines.map((line) => (
                              <p key={line}>{line}</p>
                            ))}
                          </div>
                          <span className="spinner" aria-hidden="true" />
                        </div>
                      </section>
                    ) : null}
                    {actionablePrompt ? (
                      <div className="match-table-prompt-shell">
                        <PromptOverlay
                          prompt={actionablePrompt}
                          collapsed={promptCollapsed}
                          busy={promptBusy}
                          secondsLeft={promptSecondsLeft}
                          feedbackMessage={promptFeedback}
                          compactChoices={compactDensity}
                          onToggleCollapse={() => setPromptCollapsed((prev) => !prev)}
                          onSelectChoice={onSelectPromptChoice}
                        />
                      </div>
                    ) : null}
                    {overlayHandCards.length > 0 ? (
                      <section className="match-table-hand-tray" data-testid="board-hand-tray">
                        <div className="match-table-hand-tray-head">
                          <strong>{overlayHandTitle}</strong>
                          <small>{overlayHandSubtitle}</small>
                        </div>
                        <div className="match-table-hand-tray-grid">
                          {overlayHandCards.map((card) => (
                            <article
                              key={card.key}
                              className={`match-table-hand-card ${card.hidden ? "match-table-hand-card-hidden" : ""} ${
                                card.currentTarget ? "match-table-hand-card-current" : ""
                              }`}
                            >
                              <div className="match-table-hand-card-top">
                                <strong>{card.title}</strong>
                                <span>
                                  {[card.serial, card.hidden ? (locale === "ko" ? "히든" : "Hidden") : null]
                                    .filter(Boolean)
                                    .join(" ")}
                                </span>
                              </div>
                              <p>{card.effect}</p>
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}
                  </div>
                </div>
              }
            />

            <CoreActionPanel items={coreActionFeed} latest={latestCoreAction} />
          </section>

        </>
      )}
    </main>
  );
}
