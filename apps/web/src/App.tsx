import { FormEvent, useEffect, useState } from "react";
import { useGameStream } from "./hooks/useGameStream";
import {
  createSession,
  getRuntimeStatus,
  joinSession,
  listSessions,
  type PublicSessionResult,
  startSession,
} from "./infra/http/sessionApi";
import { selectLatestSnapshot, selectSituation, selectTimeline } from "./domain/selectors/streamSelectors";
import { selectActivePrompt, selectLatestDecisionAck } from "./domain/selectors/promptSelectors";
import { ConnectionPanel } from "./features/status/ConnectionPanel";
import { SituationPanel } from "./features/status/SituationPanel";
import { TimelinePanel } from "./features/timeline/TimelinePanel";
import { BoardPanel } from "./features/board/BoardPanel";
import { PlayersPanel } from "./features/players/PlayersPanel";
import { IncidentCardStack } from "./features/theater/IncidentCardStack";
import { PromptOverlay } from "./features/prompt/PromptOverlay";

type SeatType = "human" | "ai";
type ViewRoute = "lobby" | "match";

const LOBBY_HASH = "#/lobby";
const MATCH_HASH = "#/match";

function parseRouteFromHash(hash: string): ViewRoute {
  if (hash === MATCH_HASH) {
    return "match";
  }
  return "lobby";
}

export function App() {
  const [route, setRoute] = useState<ViewRoute>(() => parseRouteFromHash(window.location.hash));
  const [sessionInput, setSessionInput] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [token, setToken] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [runtime, setRuntime] = useState("-");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [seatTypes, setSeatTypes] = useState<SeatType[]>(["human", "ai", "ai", "ai"]);
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
  const [nowMs, setNowMs] = useState(() => Date.now());

  const stream = useGameStream({ sessionId, token });
  const timeline = selectTimeline(stream.messages);
  const situation = selectSituation(stream.messages);
  const snapshot = selectLatestSnapshot(stream.messages);
  const activePrompt = selectActivePrompt(stream.messages);
  const latestPromptAck = selectLatestDecisionAck(stream.messages, activePrompt?.requestId ?? promptRequestId);

  useEffect(() => {
    const onHashChange = () => {
      setRoute(parseRouteFromHash(window.location.hash));
    };
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) {
      window.location.hash = LOBBY_HASH;
    }
    return () => {
      window.removeEventListener("hashchange", onHashChange);
    };
  }, []);

  const navigateRoute = (next: ViewRoute) => {
    window.location.hash = next === "match" ? MATCH_HASH : LOBBY_HASH;
    setRoute(next);
  };

  useEffect(() => {
    const seat = Number(joinSeatInput) || 1;
    const autoToken = lastJoinTokens[String(seat)] ?? "";
    if (autoToken) {
      setJoinTokenInput(autoToken);
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
          setRuntime(runtimeState.runtime.status);
        }
      } catch {
        // Keep UI stable on polling failures.
      }
    };
    void tick();
    const id = window.setInterval(() => {
      void tick();
    }, 4000);
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
      return;
    }
    if (activePrompt.requestId !== promptRequestId) {
      setPromptBusy(false);
      setPromptCollapsed(false);
      setPromptRequestId(activePrompt.requestId);
      setPromptExpiresAtMs(Date.now() + activePrompt.timeoutMs);
    }
  }, [activePrompt, promptRequestId]);

  useEffect(() => {
    if (!promptBusy || !latestPromptAck) {
      return;
    }
    if (latestPromptAck.status === "rejected") {
      setPromptBusy(false);
      setError(latestPromptAck.reason ? `Decision rejected: ${latestPromptAck.reason}` : "Decision rejected");
    }
    if (latestPromptAck.status === "stale") {
      setPromptBusy(false);
      setError(latestPromptAck.reason ? `Decision stale: ${latestPromptAck.reason}` : "Decision request is stale");
    }
  }, [latestPromptAck, promptBusy]);

  const refreshSessions = async () => {
    try {
      const result = await listSessions();
      setSessions(result.sessions);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to list sessions");
    }
  };

  const onConnect = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    const normalized = sessionInput.trim();
    setSessionId(normalized);
    setToken(tokenInput.trim() || undefined);
    if (normalized) {
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
      const selectedSeat = Number(joinSeatInput) || 1;
      const autoJoinToken = created.join_tokens[String(selectedSeat)] ?? "";
      if (autoJoinToken) {
        setJoinTokenInput(autoJoinToken);
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
      setRuntime(runtimeState.runtime.status);
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
    stream.sendDecision({
      requestId: activePrompt.requestId,
      playerId: activePrompt.playerId,
      choiceId,
      choicePayload: {},
    });
  };

  const promptSecondsLeft =
    promptExpiresAtMs === null ? null : Math.max(0, Math.ceil((promptExpiresAtMs - nowMs) / 1000));

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
        <>
          <section className="panel">
            <h2>Lobby Controls</h2>
            <div className="lobby-grid">
              <div>
                <h3>Create Session</h3>
                <label>
                  Seed
                  <input value={seedInput} onChange={(e) => setSeedInput(e.target.value)} />
                </label>
                <label>
                  AI Profile
                  <input value={aiProfile} onChange={(e) => setAiProfile(e.target.value)} />
                </label>
                <div className="seat-grid">
                  {seatTypes.map((seatType, idx) => (
                    <label key={`seat-${idx + 1}`}>
                      Seat {idx + 1}
                      <select
                        value={seatType}
                        onChange={(e) => {
                          const next = [...seatTypes];
                          next[idx] = e.target.value === "human" ? "human" : "ai";
                          setSeatTypes(next);
                        }}
                      >
                        <option value="human">human</option>
                        <option value="ai">ai</option>
                      </select>
                    </label>
                  ))}
                </div>
                <div className="actions">
                  <button type="button" disabled={busy} onClick={onCreateCustomSession}>
                    Create Custom Session
                  </button>
                  <button type="button" disabled={busy} onClick={onCreateAndStartAi}>
                    Create + Start AI Session
                  </button>
                </div>
              </div>

              <div>
                <h3>Host / Join</h3>
                <label>
                  Session ID
                  <input value={sessionInput} onChange={(e) => setSessionInput(e.target.value)} placeholder="sess_xxx" />
                </label>
                <label>
                  Host Token
                  <input
                    value={hostTokenInput}
                    onChange={(e) => setHostTokenInput(e.target.value)}
                    placeholder="host_xxx"
                  />
                </label>
                <div className="actions">
                  <button type="button" disabled={busy} onClick={onStartByHostToken}>
                    Start Session
                  </button>
                </div>
                <label>
                  Join Seat
                  <input value={joinSeatInput} onChange={(e) => setJoinSeatInput(e.target.value)} />
                </label>
                <label>
                  Join Token
                  <input
                    value={joinTokenInput}
                    onChange={(e) => setJoinTokenInput(e.target.value)}
                    placeholder="seat_join_token"
                  />
                </label>
                <label>
                  Display Name
                  <input value={displayNameInput} onChange={(e) => setDisplayNameInput(e.target.value)} />
                </label>
                <div className="actions">
                  <button type="button" disabled={busy} onClick={onJoinSeat}>
                    Join and Connect
                  </button>
                </div>
                {Object.keys(lastJoinTokens).length > 0 ? (
                  <p className="mono">
                    Last create tokens:{" "}
                    {Object.entries(lastJoinTokens)
                      .map(([k, v]) => `S${k}:${v}`)
                      .join(" | ")}
                  </p>
                ) : null}
              </div>
            </div>
          </section>

          <section className="panel">
            <h2>Stream Connection</h2>
            <form onSubmit={onConnect} className="form">
              <label>
                Session ID
                <input value={sessionInput} onChange={(e) => setSessionInput(e.target.value)} placeholder="sess_xxx" />
              </label>
              <label>
                Session Token (optional)
                <input
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="session_p1_xxx (or empty for spectator)"
                />
              </label>
              <div className="actions">
                <button type="submit" disabled={busy}>
                  Connect
                </button>
                <button type="button" onClick={refreshSessions} disabled={busy}>
                  Refresh Sessions
                </button>
              </div>
            </form>
            {notice ? <p className="notice ok">{notice}</p> : null}
            {error ? <p className="notice err">{error}</p> : null}
          </section>

          <section className="panel">
            <h2>Session List ({sessions.length})</h2>
            <div className="timeline">
              {sessions.map((s) => (
                <article key={s.session_id} className="timeline-item">
                  <strong>{s.session_id}</strong>
                  <span>{s.status}</span>
                  <small>
                    R{s.round_index ?? 0} / T{s.turn_index ?? 0}
                  </small>
                  <button type="button" onClick={() => onUseSession(s.session_id)}>
                    Use session
                  </button>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : (
        <>
          <ConnectionPanel status={stream.status} lastSeq={stream.lastSeq} runtime={runtime} />
          <SituationPanel model={situation} />
          <BoardPanel snapshot={snapshot} />
          <IncidentCardStack items={timeline} />
          <PlayersPanel snapshot={snapshot} />
          <TimelinePanel items={timeline} />

          <PromptOverlay
            prompt={activePrompt}
            collapsed={promptCollapsed}
            busy={promptBusy}
            secondsLeft={promptSecondsLeft}
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
