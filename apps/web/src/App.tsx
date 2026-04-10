import { CSSProperties, FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
  selectCurrentTurnRevealItems,
  selectDerivedPlayers,
  selectLastMove,
  selectLatestManifest,
  selectLiveSnapshot,
  selectMarkTargetCharacterSlots,
  selectMarkerOrderedPlayers,
  selectTimeline,
  selectTurnStage,
} from "./domain/selectors/streamSelectors";
import { BoardPanel } from "./features/board/BoardPanel";
import { LobbyView, type LobbySeatType } from "./features/lobby/LobbyView";
import { PromptOverlay } from "./features/prompt/PromptOverlay";
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

function shouldHideCharacterForPrompt(requestType: string): boolean {
  return requestType === "draft_card" || requestType === "final_character" || requestType === "final_character_choice";
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
      return ko ? "토지 구매 결정 중..." : "Deciding tile purchase...";
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
  const [boardOverlayFrame, setBoardOverlayFrame] = useState<{ viewportLeft: number; viewportWidth: number } | null>(null);
  const [eventOverlayLayout, setEventOverlayLayout] = useState<{ bottom: number; maxHeight: number } | null>(null);
  const [sessionInfoExpanded, setSessionInfoExpanded] = useState(false);
  const [showRawMessages, setShowRawMessages] = useState(false);
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
  const handTrayDockRef = useRef<HTMLElement | null>(null);
  const debugWindowRef = useRef<Window | null>(null);
  const lastTurnBannerSeqRef = useRef<number>(0);
  const lastRevealBannerSeqRef = useRef<number>(0);
  const promptSubmitRequestIdRef = useRef<string | null>(null);

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
  const derivedPlayers = selectDerivedPlayers(stream.messages, effectivePlayerId, selectorText);
  const markerOrderedPlayers = selectMarkerOrderedPlayers(stream.messages, effectivePlayerId, selectorText);
  const lastMove = selectLastMove(stream.messages);
  const latestManifest = selectLatestManifest(stream.messages);
  const currentTurnRevealItems = useMemo(
    () => selectCurrentTurnRevealItems(stream.messages, 6, selectorText),
    [stream.messages, selectorText]
  );
  const latestCurrentTurnReveal = currentTurnRevealItems[currentTurnRevealItems.length - 1] ?? null;

  const currentActorId = selectCurrentActorPlayerId(stream.messages);
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
    hasReadableValue(turnStage.weatherName)
      ? turnStage.weatherName
      : locale === "ko"
        ? "날씨 대기 중"
        : "Weather pending";
  const weatherDetail =
    hasReadableValue(turnStage.weatherEffect) && turnStage.weatherEffect !== weatherHeadline ? turnStage.weatherEffect : "";
  const weatherHudPills: string[] = [];

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

  const orderedSeatIds = useMemo(
    () => markerOrderedPlayers.map((player) => player.playerId),
    [markerOrderedPlayers]
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
    scoreCoinCount: 0,
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
  const visiblePrompt = activePrompt ?? null;
  const visiblePromptLabel = activePromptLabel;
  const boardTurnOverlay =
    visiblePrompt && visiblePrompt.requestType
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
  const effectiveTurnBanner =
    turnBanner && turnBanner.variant === "turn" && visiblePrompt && boardTurnOverlay
      ? {
          ...turnBanner,
          text: boardTurnOverlay.text,
          detail:
            boardTurnOverlay.detail && boardTurnOverlay.detail !== "-" ? boardTurnOverlay.detail : turnBanner.detail,
        }
      : turnBanner;
  const overlayHandCards = useMemo(
    () => selectCurrentHandTrayCards(stream.messages, locale, effectivePlayerId),
    [stream.messages, locale, effectivePlayerId]
  );
  const overlayHandTitle = locale === "ko" ? "현재 잔꾀 패" : "Current trick hand";
  const overlayHandSubtitle =
    actionablePromptBehavior?.normalizedRequestType === "burden_exchange_batch"
      ? locale === "ko"
        ? "처리할 짐 카드를 확인하고 아래 패에서 대상을 고르세요."
        : "Check the current burden and use the tray below to pick the target card."
      : locale === "ko"
        ? "이름과 효과를 같이 보면서 현재 손패를 확인합니다."
        : "Keep the current hand visible with both name and effect text.";
  const hasBoardBottomDock =
    Boolean(passivePrompt) || waitingForMyPrompt || Boolean(actionablePrompt) || overlayHandCards.length > 0;
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
      selectActiveCharacterSlots(stream.messages, effectivePlayerId, selectorText).map((slot) => ({
        ...slot,
        ability: slot.character ? characterAbilityLabels[slot.character] ?? "-" : null,
      })),
    [stream.messages, effectivePlayerId, selectorText, characterAbilityLabels]
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
    setPromptBusy(false);
    setBurdenExchangeQueuedDeckIndexes([]);
    setBurdenExchangeQueuedPlayerId(null);
    promptSubmitRequestIdRef.current = null;
  }, [promptBusy, promptInteraction.shouldReleaseSubmission]);

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
    const coreActionMarkup = coreActionFeed
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
            <div class="core">
              <h2>Recent Public Action (${coreActionFeed.length})</h2>
              ${coreActionMarkup || "<p>-</p>"}
            </div>
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
  }, [coreActionFeed, locale, runtime.status, sessionId, showRawMessages, stream.lastSeq, stream.messages, timeline]);

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

  const boardBoundedFixedStyle = boardOverlayFrame
    ? ({
        left: `${boardOverlayFrame.viewportLeft}px`,
        width: `${boardOverlayFrame.viewportWidth}px`,
      } as CSSProperties)
    : undefined;

  useLayoutEffect(() => {
    const node = handTrayDockRef.current;
    if (!node || route === "lobby" || overlayHandCards.length === 0) {
      setEventOverlayLayout(null);
      return;
    }

    const updateEventOverlayLayout = () => {
      const rect = node.getBoundingClientRect();
      const nextBottom = Math.max(24, Math.round(window.innerHeight - rect.top + 12));
      const nextMaxHeight = Math.max(140, Math.round(rect.top - 132));
      setEventOverlayLayout((prev) =>
        prev && prev.bottom === nextBottom && prev.maxHeight === nextMaxHeight
          ? prev
          : { bottom: nextBottom, maxHeight: nextMaxHeight }
      );
    };

    updateEventOverlayLayout();
    const resizeObserver = new ResizeObserver(() => {
      updateEventOverlayLayout();
    });
    resizeObserver.observe(node);
    window.addEventListener("resize", updateEventOverlayLayout);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateEventOverlayLayout);
    };
  }, [overlayHandCards.length, route]);

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
            <div className="match-global-summary-line">
              <strong>{sessionId ? `Session ${sessionId}` : app.topSummaryEmpty}</strong>
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
              <button type="button" className="route-tab" onClick={() => setShowRawMessages((prev) => !prev)}>
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
          }`}
          data-testid="turn-notice-banner"
        >
          <strong>{effectiveTurnBanner.text}</strong>
          {effectiveTurnBanner.detail && effectiveTurnBanner.detail !== "-" ? <small>{effectiveTurnBanner.detail}</small> : null}
        </section>
      ) : null}

      {route !== "lobby" &&
      currentTurnRevealItems.length > 0 &&
      !(visibleActionablePrompt && (visibleActionablePrompt.surface.blocksPublicEvents ?? true)) ? (
        <section
          className="match-table-event-overlay"
          style={
            {
              ...(boardBoundedFixedStyle ?? {}),
              ...(eventOverlayLayout
                ? {
                    bottom: `${eventOverlayLayout.bottom}px`,
                    maxHeight: `${eventOverlayLayout.maxHeight}px`,
                  }
                : {}),
              ...(boardBoundedFixedStyle ? { transform: "none" } : {}),
            }
          }
        >
          <section className="match-table-event-stack" data-testid="board-event-reveal-stack">
            <div className="match-table-card-head">
              <strong>{locale === "ko" ? "공개 이벤트" : "Public events"}</strong>
              <span>{locale === "ko" ? "이번 턴 순서" : "This turn order"}</span>
            </div>
            <div className="match-table-event-list">
              {currentTurnRevealItems.map((item, index) => (
                <article
                  key={`${item.seq}-${item.eventCode}`}
                  data-testid={`board-event-reveal-${item.eventCode}-${index + 1}`}
                  className={`match-table-event-card match-table-event-card-${item.tone} ${
                    index === currentTurnRevealItems.length - 1 ? "match-table-event-card-latest" : ""
                  }`}
                >
                  <div className="match-table-event-meta">
                    <span className="match-table-event-index">
                      {locale === "ko" ? `${index + 1}단계` : `Step ${index + 1}`}
                    </span>
                  </div>
                  <strong>{item.label}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </section>
        </section>
      ) : null}

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
              revealFocus={latestCurrentTurnReveal}
              turnBanner={boardTurnOverlay}
              showTurnOverlay={false}
              minimalHeader
              onOverlayFrameChange={setBoardOverlayFrame}
              overlayContent={
                <div className="match-table-overlay">
                  <div className="match-table-overlay-top">
                    <section className="match-table-stage-header">
                      <section className="match-table-topline">
                        <article className="match-table-weather-bar" data-testid="board-weather-summary">
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
                            <div className="match-table-weather-main">
                              <h4>{weatherHeadline}</h4>
                              {weatherDetail ? <p>{weatherDetail}</p> : null}
                            </div>
                          </div>
                        </article>

                        <div className="match-table-player-strip" data-testid="match-player-strip">
                          {orderedSeatIds.map((playerId) => {
                            const player = playersById.get(playerId) ?? null;
                            const isCurrentActor = playerId === currentActorId;
                            const isLocalPlayer = playerId === effectivePlayerId;
                            const characterLabel =
                              player?.currentCharacterFace && player.currentCharacterFace !== "-"
                                ? player.currentCharacterFace
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
                                    {player?.isMarkerOwner ?? (playerId === markerOwnerPlayerId) ? (
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
                                  </div>
                                  <div className="match-table-player-head-side">
                                    {isCurrentActor ? (
                                      <span className="match-table-player-badge match-table-player-badge-actor">
                                        {currentTurnBadgeLabel(locale)}
                                      </span>
                                    ) : null}
                                    <span>{displayName}</span>
                                  </div>
                                </div>
                                <p className="match-table-player-character">{characterLabel}</p>
                                <div className="match-table-player-stats">
                                  <small>{`현금 ${player?.cash ?? "-"}`}</small>
                                  <small>{`조각 ${player?.shards ?? "-"}`}</small>
                                  <small>{`토지 ${player?.ownedTileCount ?? "-"}`}</small>
                                  <small>{`잔꾀 ${player?.trickCount ?? "-"}`}</small>
                                  <small>{`손승점 ${player?.handCoins ?? "-"}`}</small>
                                  <small>{`배치승점 ${player?.placedCoins ?? "-"}`}</small>
                                  <small>{`총점 ${player?.totalScore ?? "-"}`}</small>
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      </section>

                      <section className="match-table-active-strip" data-testid="active-character-strip">
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
                              <span className="match-table-active-character-slot">
                                {locale === "ko" ? `${card.slot}번` : `#${card.slot}`}
                              </span>
                              <strong className="match-table-active-character-name">
                                {card.character ?? "-"}
                              </strong>
                              <span
                                className={`match-table-active-character-meta ${
                                  card.character ? "match-table-active-character-meta-active" : ""
                                }`}
                              >
                                {[card.inactiveCharacter, card.label, card.isCurrentActor ? currentTurnBadgeLabel(locale) : null]
                                  .filter(Boolean)
                                  .join(" · ") || "-"}
                              </span>
                            </article>
                          ))}
                        </div>
                      </section>
                    </section>
                  </div>
                  {hasBoardBottomDock ? (
                    <div
                      className="match-table-overlay-middle"
                      style={
                        boardBoundedFixedStyle
                          ? {
                              ...boardBoundedFixedStyle,
                              transform: "translateY(-50%)",
                            }
                          : undefined
                      }
                    >
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
                              onToggleCollapse={() => setPromptCollapsed((prev) => !prev)}
                              onSelectChoice={onSelectPromptChoice}
                            />
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  {overlayHandCards.length > 0 ? (
                    <div className="match-table-overlay-bottom">
                      <section
                        ref={handTrayDockRef}
                        className="match-table-hand-tray match-table-hand-tray-docked"
                        data-testid="board-hand-tray"
                      >
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
                                <span>{card.hidden ? (locale === "ko" ? "히든" : "Hidden") : ""}</span>
                              </div>
                              <p>{card.effect}</p>
                            </article>
                          ))}
                        </div>
                      </section>
                    </div>
                  ) : null}
                </div>
              }
            />
          </section>

        </>
      )}
    </main>
  );
}
