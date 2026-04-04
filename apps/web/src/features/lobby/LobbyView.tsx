import { FormEvent, useState } from "react";
import { type PublicSessionResult } from "../../infra/http/sessionApi";

export type LobbySeatType = "human" | "ai";

type LobbyViewProps = {
  busy: boolean;
  seedInput: string;
  seatCountInput: string;
  aiProfile: string;
  seatTypes: LobbySeatType[];
  sessionInput: string;
  hostTokenInput: string;
  joinSeatInput: string;
  joinSeatOptions: string[];
  joinTokenInput: string;
  displayNameInput: string;
  tokenInput: string;
  notice: string;
  error: string;
  lastJoinTokens: Record<string, string>;
  sessions: PublicSessionResult[];
  onSeedInput: (value: string) => void;
  onSeatCountInput: (value: string) => void;
  onAiProfile: (value: string) => void;
  onSeatTypeChange: (index: number, value: LobbySeatType) => void;
  onCreateCustomSession: () => void;
  onCreateAndStartAi: () => void;
  onQuickStartHumanVsAi: () => void;
  onSessionInput: (value: string) => void;
  onHostTokenInput: (value: string) => void;
  onStartByHostToken: () => void;
  onJoinSeatInput: (value: string) => void;
  onJoinTokenInput: (value: string) => void;
  onDisplayNameInput: (value: string) => void;
  onJoinSeat: () => void;
  onUseToken: (seat: string, token: string) => void;
  onConnect: (event: FormEvent) => void;
  onTokenInput: (value: string) => void;
  onRefreshSessions: () => void;
  onUseSession: (sessionId: string) => void;
};

export function LobbyView({
  busy,
  seedInput,
  seatCountInput,
  aiProfile,
  seatTypes,
  sessionInput,
  hostTokenInput,
  joinSeatInput,
  joinSeatOptions,
  joinTokenInput,
  displayNameInput,
  tokenInput,
  notice,
  error,
  lastJoinTokens,
  sessions,
  onSeedInput,
  onSeatCountInput,
  onAiProfile,
  onSeatTypeChange,
  onCreateCustomSession,
  onCreateAndStartAi,
  onQuickStartHumanVsAi,
  onSessionInput,
  onHostTokenInput,
  onStartByHostToken,
  onJoinSeatInput,
  onJoinTokenInput,
  onDisplayNameInput,
  onJoinSeat,
  onUseToken,
  onConnect,
  onTokenInput,
  onRefreshSessions,
  onUseSession,
}: LobbyViewProps) {
  const [collapsed, setCollapsed] = useState({
    controls: false,
    stream: true,
    sessions: false,
  });

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>로비 제어</h2>
          <button
            type="button"
            className="route-tab"
            onClick={() => setCollapsed((prev) => ({ ...prev, controls: !prev.controls }))}
          >
            {collapsed.controls ? "펼치기" : "접기"}
          </button>
        </div>
        {collapsed.controls ? null : (
          <div className="lobby-grid">
            <div>
              <h3>세션 생성</h3>
              <label>
                시드
                <input value={seedInput} onChange={(e) => onSeedInput(e.target.value)} />
              </label>
              <label>
                좌석 수 (1-4)
                <input value={seatCountInput} onChange={(e) => onSeatCountInput(e.target.value)} />
              </label>
              <label>
                AI 프로필
                <input value={aiProfile} onChange={(e) => onAiProfile(e.target.value)} />
              </label>
              <div className="seat-grid">
                {seatTypes.map((seatType, idx) => (
                  <label key={`seat-${idx + 1}`}>
                    좌석 {idx + 1}
                    <select
                      value={seatType}
                      onChange={(e) => onSeatTypeChange(idx, e.target.value === "human" ? "human" : "ai")}
                    >
                      <option value="human">human</option>
                      <option value="ai">ai</option>
                    </select>
                  </label>
                ))}
              </div>
              <div className="actions">
                <button type="button" disabled={busy} onClick={onQuickStartHumanVsAi}>
                  사람1 + AI3 바로 시작
                </button>
                <button type="button" disabled={busy} onClick={onCreateCustomSession}>
                  커스텀 세션 생성
                </button>
                <button type="button" disabled={busy} onClick={onCreateAndStartAi}>
                  AI 전용 즉시 시작
                </button>
              </div>
            </div>

            <div>
              <h3>호스트 / 참가</h3>
              <label>
                세션 ID
                <input value={sessionInput} onChange={(e) => onSessionInput(e.target.value)} placeholder="sess_xxx" />
              </label>
              <label>
                호스트 토큰
                <input value={hostTokenInput} onChange={(e) => onHostTokenInput(e.target.value)} placeholder="host_xxx" />
              </label>
              <div className="actions">
                <button type="button" disabled={busy} onClick={onStartByHostToken}>
                  세션 시작
                </button>
              </div>
              <label>
                참가 좌석
                <select value={joinSeatInput} onChange={(e) => onJoinSeatInput(e.target.value)}>
                  {joinSeatOptions.map((seat) => (
                    <option key={`seat-option-${seat}`} value={seat}>
                      Seat {seat}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                참가 토큰
                <input value={joinTokenInput} onChange={(e) => onJoinTokenInput(e.target.value)} placeholder="seat_join_token" />
              </label>
              <label>
                표시 이름
                <input value={displayNameInput} onChange={(e) => onDisplayNameInput(e.target.value)} />
              </label>
              <div className="actions">
                <button type="button" disabled={busy} onClick={onJoinSeat}>
                  참가 + 연결
                </button>
              </div>
              {Object.keys(lastJoinTokens).length > 0 ? (
                <div className="token-list">
                  <p className="mono">최근 생성 join token</p>
                  <div className="token-actions">
                    {Object.entries(lastJoinTokens).map(([seat, value]) => (
                      <button key={`token-${seat}`} type="button" onClick={() => onUseToken(seat, value)}>
                        Use Seat {seat} token
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>스트림 연결</h2>
          <button
            type="button"
            className="route-tab"
            onClick={() => setCollapsed((prev) => ({ ...prev, stream: !prev.stream }))}
          >
            {collapsed.stream ? "펼치기" : "접기"}
          </button>
        </div>
        {collapsed.stream ? null : (
          <>
            <form onSubmit={onConnect} className="form">
              <label>
                세션 ID
                <input value={sessionInput} onChange={(e) => onSessionInput(e.target.value)} placeholder="sess_xxx" />
              </label>
              <label>
                세션 토큰 (옵션)
                <input
                  value={tokenInput}
                  onChange={(e) => onTokenInput(e.target.value)}
                  placeholder="session_p1_xxx (비우면 관전자)"
                />
              </label>
              <div className="actions">
                <button type="submit" disabled={busy}>
                  연결
                </button>
                <button type="button" onClick={onRefreshSessions} disabled={busy}>
                  세션 목록 갱신
                </button>
              </div>
            </form>
            {notice ? <p className="notice ok">{notice}</p> : null}
            {error ? <p className="notice err">{error}</p> : null}
          </>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>세션 목록 ({sessions.length})</h2>
          <button
            type="button"
            className="route-tab"
            onClick={() => setCollapsed((prev) => ({ ...prev, sessions: !prev.sessions }))}
          >
            {collapsed.sessions ? "펼치기" : "접기"}
          </button>
        </div>
        {collapsed.sessions ? null : (
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
        )}
      </section>
    </>
  );
}
