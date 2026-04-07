import { FormEvent, useEffect, useMemo, useState } from "react";
import { mergeSessionManifest } from "./domain/manifest/manifestRehydrate";
import {
  characterAbilityLabelsFromManifestLabels,
  tileKindLabelsFromManifestLabels,
} from "./domain/labels/manifestLabelCatalog";
import { promptLabelForType } from "./domain/labels/promptTypeCatalog";
import { selectActivePrompt, selectLatestDecisionAck } from "./domain/selectors/promptSelectors";
import {
  selectCoreActionFeed,
  selectCriticalAlerts,
  selectLastMove,
  selectLatestManifest,
  selectLatestSnapshot,
  selectSituation,
  selectTheaterFeed,
  selectTimeline,
  selectTurnStage,
} from "./domain/selectors/streamSelectors";
import { BoardPanel } from "./features/board/BoardPanel";
import { LobbyView, type LobbySeatType } from "./features/lobby/LobbyView";
import { PlayersPanel } from "./features/players/PlayersPanel";
import { PromptOverlay } from "./features/prompt/PromptOverlay";
import { SpectatorTurnPanel } from "./features/stage/SpectatorTurnPanel";
import { TurnStagePanel } from "./features/stage/TurnStagePanel";
import { ConnectionPanel } from "./features/status/ConnectionPanel";
import { SituationPanel } from "./features/status/SituationPanel";
import { CoreActionPanel } from "./features/theater/CoreActionPanel";
import { IncidentCardStack } from "./features/theater/IncidentCardStack";
import { TimelinePanel } from "./features/timeline/TimelinePanel";
import { useGameStream } from "./hooks/useGameStream";
import { useI18n } from "./i18n/useI18n";
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
  const [matchTopCollapsed, setMatchTopCollapsed] = useState(true);

  const [promptCollapsed, setPromptCollapsed] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptRequestId, setPromptRequestId] = useState("");
  const [promptExpiresAtMs, setPromptExpiresAtMs] = useState<number | null>(null);
  const [promptFeedback, setPromptFeedback] = useState("");
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [turnBanner, setTurnBanner] = useState<{ seq: number; text: string; detail: string } | null>(null);

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
  const theaterFeed = selectTheaterFeed(stream.messages, compactDensity ? 16 : 28, selectorText);
  const coreActionFeed = selectCoreActionFeed(stream.messages, effectivePlayerId, compactDensity ? 10 : 14, selectorText);
  const latestCoreAction = coreActionFeed.find((item) => !item.isLocalActor) ?? coreActionFeed[0] ?? null;
  const alerts = selectCriticalAlerts(stream.messages, 6, selectorText);
  const situation = selectSituation(stream.messages, selectorText);
  const turnStage = selectTurnStage(stream.messages, selectorText);
  const snapshot = selectLatestSnapshot(stream.messages);
  const lastMove = selectLastMove(stream.messages);
  const latestManifest = selectLatestManifest(stream.messages);

  const currentActorId = findCurrentActorId(stream.messages);
  const isMyTurn = currentActorId !== null && effectivePlayerId !== null && currentActorId === effectivePlayerId;
  const currentActorText =
    turnStage.actor !== "-"
      ? turnStage.character && turnStage.character !== "-"
        ? `${turnStage.actor} (${turnStage.character})`
        : turnStage.actor
      : "-";
  const boardTurnOverlay =
    !isMyTurn && currentActorId !== null && currentActorText !== "-"
      ? {
          text: app.turnBanner(currentActorText),
          detail: turnStage.currentBeatLabel !== "-" ? turnStage.currentBeatLabel : turnStage.currentBeatDetail,
        }
      : null;

  const activePrompt = selectActivePrompt(stream.messages);
  const canActOnPrompt = Boolean(activePrompt && token && effectivePlayerId !== null && activePrompt.playerId === effectivePlayerId);
  const actionablePrompt = canActOnPrompt ? activePrompt : null;
  const passivePrompt = activePrompt && !canActOnPrompt ? activePrompt : null;
  const latestPromptAck = selectLatestDecisionAck(stream.messages, actionablePrompt?.requestId ?? promptRequestId);
  const promptSecondsLeft =
    promptExpiresAtMs === null ? null : Math.max(0, Math.ceil((promptExpiresAtMs - nowMs) / 1000));

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
    setPromptFeedback(app.errors.promptConnectionLost);
  }, [promptBusy, stream.status]);

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
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [turnStage.actor, turnStage.character, turnStage.turnStartSeq]);

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
      window.location.hash = buildMatchHash(id, tokenInput.trim() || undefined);
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
    setPromptFeedback("");
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

  const topCommandSummary = useMemo(() => {
    if (!sessionId.trim()) {
      return app.topSummaryEmpty;
    }
    return app.topSummary(sessionId, runtime.status);
  }, [app, runtime.status, sessionId]);

  return (
    <main className={`page ${compactDensity ? "page-compact" : ""} ${route === "match" ? "page-match" : ""}`}>
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
            className={route === "match" ? "route-tab route-tab-active" : "route-tab"}
            onClick={() => navigateRoute("match")}
          >
            {app.routeMatch}
          </button>
          {route === "match" ? (
            <>
              <button type="button" className="route-tab" onClick={() => setMatchTopCollapsed((prev) => !prev)}>
                {matchTopCollapsed ? app.connectionExpand : app.connectionCollapse}
              </button>
              <button type="button" className="route-tab" onClick={() => setCompactDensity((prev) => !prev)}>
                {compactDensity ? app.densityStandard : app.densityCompact}
              </button>
            </>
          ) : null}
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
          <section className="panel match-command-strip">
            <div className="match-command-row">
              <strong>{topCommandSummary}</strong>
              {actionablePrompt && promptCollapsed ? (
                <button
                  type="button"
                  className="route-tab route-tab-active match-reopen-prompt"
                  onClick={() => setPromptCollapsed(false)}
                >
                  {app.reopenPrompt(promptLabelForType(actionablePrompt.requestType), promptSecondsLeft)}
                </button>
              ) : null}
            </div>
            {!matchTopCollapsed ? (
              <>
                <ConnectionPanel status={stream.status} lastSeq={stream.lastSeq} runtime={runtime} />
                <div className="match-command-secondary">
                  <button type="button" className="route-tab route-tab-muted" onClick={() => setShowRawMessages((prev) => !prev)}>
                    {showRawMessages ? app.rawHide : app.rawShow}
                  </button>
                </div>
              </>
            ) : null}
          </section>

          {turnBanner ? (
            <div className="turn-notice-banner" data-testid="turn-notice-banner">
              <strong>{turnBanner.text}</strong>
              <small>{turnBanner.detail}</small>
            </div>
          ) : null}

          <div className="match-layout">
            <div className="match-board-column">
              <BoardPanel
                snapshot={snapshot}
                manifestTiles={manifestTiles}
                boardTopology={boardTopology}
                tileKindLabels={tileKindLabels}
                lastMove={lastMove}
                stageFocus={turnStage}
                weather={turnStage}
                turnBanner={boardTurnOverlay}
                showTurnOverlay={!isMyTurn && currentActorId !== null}
              />

              <TurnStagePanel model={turnStage} characterAbilityText={activeCharacterAbility} isMyTurn={isMyTurn} />
              <CoreActionPanel items={coreActionFeed} latest={latestCoreAction} />

              {!isMyTurn && currentActorId !== null ? (
                <SpectatorTurnPanel actorPlayerId={currentActorId} model={turnStage} latestAction={latestCoreAction} />
              ) : null}

              <IncidentCardStack items={theaterFeed} focusPlayerId={effectivePlayerId} />

              {passivePrompt ? (
                <section className="panel passive-prompt-card" data-testid="passive-prompt-card">
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

            <div className="match-side-column">
              <SituationPanel model={situation} alerts={alerts} />
              <PlayersPanel snapshot={snapshot} />
              <TimelinePanel items={timeline} />
            </div>
          </div>

          {showRawMessages ? (
            <section className="panel debug-panel">
              <div className="debug-head">
                <h2>{app.rawMessages} ({stream.messages.length})</h2>
                <button type="button" className="route-tab" onClick={() => setShowRawMessages(false)}>
                  {app.rawHide}
                </button>
              </div>
              <div className="messages">
                {stream.messages
                  .slice()
                  .reverse()
                  .map((message, idx) => (
                    <pre key={`${message.seq}-${idx}`}>{JSON.stringify(message, null, 2)}</pre>
                  ))}
              </div>
            </section>
          ) : null}

        </>
      )}
    </main>
  );
}
