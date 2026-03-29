import { FormEvent, useEffect, useState } from "react";
import { useGameStream } from "./hooks/useGameStream";
import {
  createSession,
  getRuntimeStatus,
  joinSession,
  listSessions,
  type PublicSessionResult,
  type RuntimeStatusResult,
  startSession,
} from "./infra/http/sessionApi";
import {
  selectLastMove,
  selectLatestSnapshot,
  selectSituation,
  selectTimeline,
} from "./domain/selectors/streamSelectors";
import { selectActivePrompt, selectLatestDecisionAck } from "./domain/selectors/promptSelectors";
import { ConnectionPanel } from "./features/status/ConnectionPanel";
import { SituationPanel } from "./features/status/SituationPanel";
import { TimelinePanel } from "./features/timeline/TimelinePanel";
import { BoardPanel } from "./features/board/BoardPanel";
import { PlayersPanel } from "./features/players/PlayersPanel";
import { IncidentCardStack } from "./features/theater/IncidentCardStack";
import { PromptOverlay } from "./features/prompt/PromptOverlay";
import { LobbyView, type LobbySeatType } from "./features/lobby/LobbyView";

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
  const [aiProfile, setAiProfile] = useState("balanced");
  const [seedInput, setSeedInput] = useState("42");
  const [hostTokenInput, setHostTokenInput] = useState("");
  const [lastJoinTokens, setLastJoinTokens] = useState<Record<string, string>>({});
  const [joinSeatInput, setJoinSeatInput] = useState("1");
  const [joinTokenInput, setJoinTokenInput] = useState("");
  const [displayNameInput, setDisplayNameInput] = useState("Player");
  const [sessions, setSessions] = useState<PublicSessionResult[]>([]);

  const [promptCollapsed, setPromptCollapsed] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptRequestId, setPromptRequestId] = useState("");
  const [promptExpiresAtMs, setPromptExpiresAtMs] = useState<number | null>(null);
  const [promptFeedback, setPromptFeedback] = useState("");
  const [nowMs, setNowMs] = useState(() => Date.now());

  const stream = useGameStream({ sessionId, token });
  const timeline = selectTimeline(stream.messages);
  const situation = selectSituation(stream.messages);
  const snapshot = selectLatestSnapshot(stream.messages);
  const lastMove = selectLastMove(stream.messages);
  const activePrompt = selectActivePrompt(stream.messages);
  const latestPromptAck = selectLatestDecisionAck(stream.messages, activePrompt?.requestId ?? promptRequestId);

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
    return () => {
      window.removeEventListener("hashchange", onHashChange);
    };
  }, []);

  const navigateRoute = (next: ViewRoute) => {
    if (next === "match") {
      window.location.hash = buildMatchHash(sessionInput || sessionId, tokenInput || token);
    } else {
      window.location.hash = LOBBY_HASH;
    }
    setRoute(next);
  };

  useEffect(() => {
    const seat = Number(joinSeatInput) || 1;
    const tokenBySeat = lastJoinTokens[String(seat)] ?? "";
    if (tokenBySeat) {
      setJoinTokenInput(tokenBySeat);
    }
  }, [joinSeatInput, lastJoinTokens]);

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
        // Keep current runtime view on polling error.
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
    if (!activePrompt) {
      setPromptBusy(false);
      setPromptRequestId("");
      setPromptExpiresAtMs(null);
      setPromptFeedback("");
      return;
    }
    if (activePrompt.requestId !== promptRequestId) {
      setPromptBusy(false);
      setPromptCollapsed(false);
      setPromptRequestId(activePrompt.requestId);
      setPromptExpiresAtMs(Date.now() + activePrompt.timeoutMs);
      setPromptFeedback("");
    }
  }, [activePrompt, promptRequestId]);

  useEffect(() => {
    if (!promptBusy || !latestPromptAck) {
      return;
    }
    if (latestPromptAck.status === "rejected") {
      setPromptBusy(false);
      setPromptFeedback(
        latestPromptAck.reason
          ? `선택이 거절되었습니다: ${latestPromptAck.reason}`
          : "선택이 거절되었습니다. 다른 선택지를 시도해주세요."
      );
    }
    if (latestPromptAck.status === "stale") {
      setPromptBusy(false);
      setPromptFeedback(
        latestPromptAck.reason
          ? `선택이 만료되었습니다: ${latestPromptAck.reason}`
          : "선택 요청이 만료되었습니다. 현재 요청을 다시 확인해주세요."
      );
    }
  }, [latestPromptAck, promptBusy]);

  const promptSecondsLeft =
    promptExpiresAtMs === null ? null : Math.max(0, Math.ceil((promptExpiresAtMs - nowMs) / 1000));

  useEffect(() => {
    if (!activePrompt || promptBusy) {
      return;
    }
    if (promptSecondsLeft === 0) {
      setPromptFeedback("시간이 만료되었습니다. 엔진의 자동 처리 결과를 기다리는 중입니다.");
    }
  }, [activePrompt, promptBusy, promptSecondsLeft]);

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
        config: { seed: Number(seedInput) || 42 },
      });
      setSessionInput(created.session_id);
      setHostTokenInput(created.host_token);
      setLastJoinTokens(created.join_tokens);
      const seat = Number(joinSeatInput) || 1;
      const autoToken = created.join_tokens[String(seat)] ?? "";
      if (autoToken) {
        setJoinTokenInput(autoToken);
      }
      setNotice(
        `Session created: ${created.session_id} host_token=${created.host_token} join_tokens=${JSON.stringify(created.join_tokens)}`
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
        seats: [
          { seat: 1, seat_type: "ai", ai_profile: "gpt" },
          { seat: 2, seat_type: "ai", ai_profile: "claude" },
          { seat: 3, seat_type: "ai", ai_profile: "gpt" },
          { seat: 4, seat_type: "ai", ai_profile: "claude" },
        ],
        config: { seed: Number(seedInput) || 42 },
      });
      await startSession({ sessionId: created.session_id, hostToken: created.host_token });
      const runtimeState = await getRuntimeStatus(created.session_id);
      setRuntime(runtimeState.runtime);
      setSessionInput(created.session_id);
      setSessionId(created.session_id);
      setTokenInput("");
      setToken(undefined);
      setHostTokenInput(created.host_token);
      setLastJoinTokens(created.join_tokens);
      setNotice(
        `AI session started: ${created.session_id} host_token=${created.host_token} join_tokens=${JSON.stringify(created.join_tokens)}`
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
    try {
      await startSession({ sessionId: current, hostToken: hostTokenInput.trim() });
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
    try {
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
    setSessionInput(id);
    setSessionId(id);
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
    if (!activePrompt || promptBusy) {
      return;
    }
    if (!activePrompt.playerId) {
      setError("Prompt player_id is invalid.");
      return;
    }
    setPromptBusy(true);
    setPromptFeedback("");
    stream.sendDecision({
      requestId: activePrompt.requestId,
      playerId: activePrompt.playerId,
      choiceId,
      choicePayload: {},
    });
  };

  return (
    <main className="page">
      <header className="header">
        <h1>MRN Online Viewer (React/FastAPI)</h1>
        <p>Custom lobby controls are enabled: create, join, start, connect, and live stream observe.</p>
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
      </header>

      {route === "lobby" ? (
        <LobbyView
          busy={busy}
          seedInput={seedInput}
          aiProfile={aiProfile}
          seatTypes={seatTypes}
          sessionInput={sessionInput}
          hostTokenInput={hostTokenInput}
          joinSeatInput={joinSeatInput}
          joinTokenInput={joinTokenInput}
          displayNameInput={displayNameInput}
          tokenInput={tokenInput}
          notice={notice}
          error={error}
          lastJoinTokens={lastJoinTokens}
          sessions={sessions}
          onSeedInput={setSeedInput}
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
          <SituationPanel model={situation} />
          <BoardPanel snapshot={snapshot} lastMove={lastMove} />
          <IncidentCardStack items={timeline} />
          <PlayersPanel snapshot={snapshot} />
          <TimelinePanel items={timeline} />

          <PromptOverlay
            prompt={activePrompt}
            collapsed={promptCollapsed}
            busy={promptBusy}
            secondsLeft={promptSecondsLeft}
            feedbackMessage={promptFeedback}
            onToggleCollapse={() => setPromptCollapsed((prev) => !prev)}
            onSelectChoice={onSelectPromptChoice}
          />

          <section className="panel">
            <h2>Recent Messages ({stream.messages.length})</h2>
            <div className="messages">
              {stream.messages
                .slice()
                .reverse()
                .map((message, idx) => (
                  <pre key={`${message.seq}-${idx}`}>{JSON.stringify(message, null, 2)}</pre>
                ))}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
