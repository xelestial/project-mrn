import { FormEvent, useEffect, useState } from "react";
import { useGameStream } from "./hooks/useGameStream";
import { createSession, getRuntimeStatus, startSession } from "./infra/http/sessionApi";
import { selectLatestSnapshot, selectSituation, selectTimeline } from "./domain/selectors/streamSelectors";
import { ConnectionPanel } from "./features/status/ConnectionPanel";
import { SituationPanel } from "./features/status/SituationPanel";
import { TimelinePanel } from "./features/timeline/TimelinePanel";
import { BoardPanel } from "./features/board/BoardPanel";
import { PlayersPanel } from "./features/players/PlayersPanel";
import { IncidentCardStack } from "./features/theater/IncidentCardStack";

export function App() {
  const [sessionInput, setSessionInput] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [token, setToken] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [runtime, setRuntime] = useState("-");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const stream = useGameStream({ sessionId, token });
  const timeline = selectTimeline(stream.messages);
  const situation = selectSituation(stream.messages);
  const snapshot = selectLatestSnapshot(stream.messages);

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
        // Keep UI stable; manual refresh still available.
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

  const onConnect = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    setSessionId(sessionInput.trim());
    setToken(tokenInput.trim() || undefined);
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
        config: { seed: 42 },
      });
      await startSession({ sessionId: created.session_id, hostToken: created.host_token });
      const runtimeState = await getRuntimeStatus(created.session_id);
      setRuntime(runtimeState.runtime.status);
      setSessionInput(created.session_id);
      setTokenInput("");
      setToken(undefined);
      setSessionId(created.session_id);
      setNotice(`AI 세션 시작 완료: ${created.session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "세션 생성/시작 중 오류가 발생했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const onRefreshRuntime = async () => {
    if (!sessionId.trim()) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const runtimeState = await getRuntimeStatus(sessionId.trim());
      setRuntime(runtimeState.runtime.status);
      setNotice(`Runtime 상태 갱신: ${runtimeState.runtime.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Runtime 상태 조회 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page">
      <header className="header">
        <h1>MRN Online Viewer (F1 Baseline)</h1>
        <p>세션 ID/토큰으로 연결하거나, AI 4인 세션을 즉시 시작할 수 있습니다.</p>
      </header>
      <section className="panel">
        <form onSubmit={onConnect} className="form">
          <label>
            Session ID
            <input value={sessionInput} onChange={(e) => setSessionInput(e.target.value)} placeholder="sess_xxx" />
          </label>
          <label>
            Session Token (optional)
            <input value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} placeholder="session_p1_xxx" />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Connect
            </button>
            <button type="button" onClick={onCreateAndStartAi} disabled={busy}>
              AI 4인 세션 생성/시작
            </button>
            <button type="button" onClick={onRefreshRuntime} disabled={busy || !sessionId.trim()}>
              Runtime 갱신
            </button>
          </div>
        </form>
        {notice ? <p className="notice ok">{notice}</p> : null}
        {error ? <p className="notice err">{error}</p> : null}
      </section>
      <ConnectionPanel status={stream.status} lastSeq={stream.lastSeq} runtime={runtime} />
      <SituationPanel model={situation} />
      <BoardPanel snapshot={snapshot} />
      <IncidentCardStack items={timeline} />
      <PlayersPanel snapshot={snapshot} />
      <TimelinePanel items={timeline} />
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
    </main>
  );
}
