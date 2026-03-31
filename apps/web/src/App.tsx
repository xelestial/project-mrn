import { FormEvent, useEffect, useState } from "react";
import { mergeSessionManifest } from "./domain/manifest/manifestRehydrate";
import { tileKindLabelsFromManifestLabels } from "./domain/labels/manifestLabelCatalog";
import { promptLabelForType } from "./domain/labels/promptTypeCatalog";
import { selectActivePrompt, selectLatestDecisionAck } from "./domain/selectors/promptSelectors";
import {
  selectCriticalAlerts,
  selectLastMove,
  selectLatestManifest,
  selectLatestSnapshot,
  selectSituation,
  selectTheaterFeed,
  selectTimeline,
} from "./domain/selectors/streamSelectors";
import { BoardPanel } from "./features/board/BoardPanel";
import { LobbyView, type LobbySeatType } from "./features/lobby/LobbyView";
import { PlayersPanel } from "./features/players/PlayersPanel";
import { PromptOverlay } from "./features/prompt/PromptOverlay";
import { ConnectionPanel } from "./features/status/ConnectionPanel";
import { SituationPanel } from "./features/status/SituationPanel";
import { IncidentCardStack } from "./features/theater/IncidentCardStack";
import { TimelinePanel } from "./features/timeline/TimelinePanel";
import { useGameStream } from "./hooks/useGameStream";
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

export function App() {
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
  const [seedInput, setSeedInput] = useState("42");
  const [hostTokenInput, setHostTokenInput] = useState("");
  const [lastJoinTokens, setLastJoinTokens] = useState<Record<string, string>>({});
  const [joinSeatInput, setJoinSeatInput] = useState("1");
  const [joinTokenInput, setJoinTokenInput] = useState("");
  const [displayNameInput, setDisplayNameInput] = useState("Player");
  const [sessions, setSessions] = useState<PublicSessionResult[]>([]);
  const [sessionManifest, setSessionManifest] = useState<ParameterManifest | null>(null);
  const [localPlayerId, setLocalPlayerId] = useState<number | null>(null);

  const [compactDensity, setCompactDensity] = useState(
    () => window.innerHeight <= 1080 || window.innerWidth <= 1400
  );
  const [showRawMessages, setShowRawMessages] = useState(true);

  const [promptCollapsed, setPromptCollapsed] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptRequestId, setPromptRequestId] = useState("");
  const [promptExpiresAtMs, setPromptExpiresAtMs] = useState<number | null>(null);
  const [promptFeedback, setPromptFeedback] = useState("");
  const [nowMs, setNowMs] = useState(() => Date.now());

  const stream = useGameStream({ sessionId, token });
  const timeline = selectTimeline(stream.messages, compactDensity ? 24 : 40);
  const theaterFeed = selectTheaterFeed(stream.messages, compactDensity ? 12 : 20);
  const alerts = selectCriticalAlerts(stream.messages, 6);
  const situation = selectSituation(stream.messages);
  const snapshot = selectLatestSnapshot(stream.messages);
  const lastMove = selectLastMove(stream.messages);
  const latestManifest = selectLatestManifest(stream.messages);

  const activePrompt = selectActivePrompt(stream.messages);
  const canActOnPrompt = Boolean(
    activePrompt && token && (localPlayerId === null || activePrompt.playerId === localPlayerId)
  );
  const actionablePrompt = canActOnPrompt ? activePrompt : null;
  const passivePrompt = activePrompt && !canActOnPrompt ? activePrompt : null;
  const latestPromptAck = selectLatestDecisionAck(
    stream.messages,
    actionablePrompt?.requestId ?? promptRequestId
  );
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

  useEffect(() => {
    const onHashChange = () => {
      const parsed = parseHashState(window.location.hash);
      setRoute(parsed.route);
      if (parsed.sessionId) {
        setSessionInput(parsed.sessionId);
        setSessionId(parsed.sessionId);
      }
      if (parsed.token !== undefined) {
        setTokenInput(parsed.token);
        setToken(parsed.token || undefined);
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
        // keep current runtime state when polling fails
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
      setPromptFeedback(
        latestPromptAck.reason
          ? `선택이 거절되었습니다: ${latestPromptAck.reason}`
          : "선택이 거절되었습니다. 다른 선택지를 시도해 주세요."
      );
      return;
    }
    setPromptFeedback(
      latestPromptAck.reason
        ? `선택이 만료되었습니다: ${latestPromptAck.reason}`
        : "선택 요청이 만료되었습니다. 현재 요청을 다시 확인해 주세요."
    );
  }, [latestPromptAck, promptBusy]);

  useEffect(() => {
    if (!actionablePrompt || promptBusy || promptSecondsLeft !== 0) {
      return;
    }
    setPromptFeedback("시간이 만료되었습니다. 엔진의 자동 진행 결과를 기다리는 중입니다.");
  }, [actionablePrompt, promptBusy, promptSecondsLeft]);

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
      setError(e instanceof Error ? e.message : "Failed to list sessions");
    }
  };

  const onConnect = (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");
    setLocalPlayerId(null);
    const normalized = sessionInput.trim();
    setSessionId(normalized);
    setToken(tokenInput.trim() || undefined);
    if (normalized) {
      window.location.hash = buildMatchHash(normalized, tokenInput.trim() || undefined);
      navigateRoute("match");
    }
  };

  const onCreateCustomSession = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const seats = seatTypes.map((seatType, index) => ({
        seat: index + 1,
        seat_type: seatType,
        ai_profile: seatType === "ai" ? aiProfile : undefined,
      }));
      const created = await createSession({
        seats,
        config: {
          seed: Number(seedInput) || 42,
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
      if (autoToken) {
        setJoinTokenInput(autoToken);
      } else {
        setJoinTokenInput("");
      }
      setNotice(
        `Session created: ${created.session_id} host_token=${created.host_token} join_tokens=${JSON.stringify(
          created.join_tokens
        )}`
      );
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create session");
    } finally {
      setBusy(false);
    }
  };

  const onCreateAndStartAi = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await createSession({
        seats: Array.from({ length: seatTypes.length }, (_, idx) => ({
          seat: idx + 1,
          seat_type: "ai" as const,
          ai_profile: idx % 2 === 0 ? "gpt" : "claude",
        })),
        config: {
          seed: Number(seedInput) || 42,
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
      setNotice(
        `AI session started: ${created.session_id} host_token=${created.host_token} join_tokens=${JSON.stringify(
          created.join_tokens
        )}`
      );
      navigateRoute("match");
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create/start AI session");
    } finally {
      setBusy(false);
    }
  };

  const onStartByHostToken = async () => {
    const current = sessionInput.trim() || sessionId.trim();
    if (!current || !hostTokenInput.trim()) {
      setError("Session ID and host token are required.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const started = await startSession({ sessionId: current, hostToken: hostTokenInput.trim() });
      setSessionManifest(started.parameter_manifest ?? null);
      setSessionId(current);
      setNotice(`Session started by host: ${current}`);
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start session");
    } finally {
      setBusy(false);
    }
  };

  const onJoinSeat = async () => {
    const current = sessionInput.trim() || sessionId.trim();
    const seat = Number(joinSeatInput);
    if (!current || !seat || !joinTokenInput.trim()) {
      setError("Session ID, seat, and join token are required.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const snapshot = await getSession({ sessionId: current });
      if (snapshot.status !== "waiting") {
        throw new Error("Session is already started. Join is only allowed while waiting.");
      }
      const seatView = (snapshot.seats ?? []).find((s) => s.seat === seat);
      if (!seatView) {
        throw new Error(`Seat ${seat} does not exist in this session.`);
      }
      if (seatView.seat_type !== "human") {
        throw new Error(`Seat ${seat} is not a human seat.`);
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
      setNotice(`Joined seat P${joined.player_id}. Connected with session token.`);
      navigateRoute("match");
      await refreshSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join seat");
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
    setNotice(`Session selected: ${id}`);
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
      setError("Prompt player_id is invalid.");
      return;
    }
    setPromptBusy(true);
    setPromptFeedback("");
    stream.sendDecision({
      requestId: actionablePrompt.requestId,
      playerId: actionablePrompt.playerId,
      choiceId,
      choicePayload: {},
    });
  };

  return (
    <main className={`page ${compactDensity ? "page-compact" : ""}`}>
      <header className="header">
        <h1>MRN Online Viewer (React/FastAPI)</h1>
        <p>세션 생성, 참가, 시작, 실시간 스트림 관찰을 한 화면에서 진행할 수 있습니다.</p>
        <div className="route-tabs">
          <button
            type="button"
            className={route === "lobby" ? "route-tab route-tab-active" : "route-tab"}
            onClick={() => navigateRoute("lobby")}
          >
            Lobby
          </button>
          <button
            type="button"
            className={route === "match" ? "route-tab route-tab-active" : "route-tab"}
            onClick={() => navigateRoute("match")}
          >
            Match
          </button>
        </div>
        {route === "match" ? (
          <div className="view-controls">
            <button type="button" className="route-tab" onClick={() => setCompactDensity((prev) => !prev)}>
              {compactDensity ? "표준 밀도" : "컴팩트 밀도"}
            </button>
            <button type="button" className="route-tab" onClick={() => setShowRawMessages((prev) => !prev)}>
              {showRawMessages ? "Raw 숨기기" : "Raw 보기"}
            </button>
          </div>
        ) : null}
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
          <ConnectionPanel status={stream.status} lastSeq={stream.lastSeq} runtime={runtime} />
          <div className="match-layout">
            <div className="match-board-column">
              <BoardPanel
                snapshot={snapshot}
                manifestTiles={manifestTiles}
                boardTopology={boardTopology}
                tileKindLabels={tileKindLabels}
                lastMove={lastMove}
              />
              <IncidentCardStack items={theaterFeed} />
              {passivePrompt ? (
                <section className="panel passive-prompt-card">
                  <h2>다른 플레이어 선택 진행 중</h2>
                  <p>
                    P{passivePrompt.playerId} / {promptLabelForType(passivePrompt.requestType)} / 남은 시간{" "}
                    {promptSecondsLeft ?? "-"}초
                  </p>
                  <p className="prompt-collapsed-note">
                    관전 중에는 입력창 대신 진행 상황만 표시됩니다. 선택이 끝나면 다음 공개 이벤트가 이어집니다.
                  </p>
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
          <section className="panel debug-panel">
            <div className="debug-head">
              <h2>Recent Messages ({stream.messages.length})</h2>
              <button type="button" className="route-tab" onClick={() => setShowRawMessages((prev) => !prev)}>
                {showRawMessages ? "숨기기" : "보기"}
              </button>
            </div>
            {showRawMessages ? (
              <div className="messages">
                {stream.messages
                  .slice()
                  .reverse()
                  .map((message, idx) => (
                    <pre key={`${message.seq}-${idx}`}>{JSON.stringify(message, null, 2)}</pre>
                  ))}
              </div>
            ) : (
              <p className="prompt-collapsed-note">장시간 플레이에서는 기본적으로 Raw 로그를 숨깁니다.</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}
