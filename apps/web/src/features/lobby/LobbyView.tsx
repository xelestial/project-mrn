import { FormEvent } from "react";
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
  return (
    <>
      <section className="panel">
        <h2>Lobby Controls</h2>
        <div className="lobby-grid">
          <div>
            <h3>Create Session</h3>
            <label>
              Seed
              <input value={seedInput} onChange={(e) => onSeedInput(e.target.value)} />
            </label>
            <label>
              Seat Count (1-4)
              <input value={seatCountInput} onChange={(e) => onSeatCountInput(e.target.value)} />
            </label>
            <label>
              AI Profile
              <input value={aiProfile} onChange={(e) => onAiProfile(e.target.value)} />
            </label>
            <div className="seat-grid">
              {seatTypes.map((seatType, idx) => (
                <label key={`seat-${idx + 1}`}>
                  Seat {idx + 1}
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
              <input value={sessionInput} onChange={(e) => onSessionInput(e.target.value)} placeholder="sess_xxx" />
            </label>
            <label>
              Host Token
              <input value={hostTokenInput} onChange={(e) => onHostTokenInput(e.target.value)} placeholder="host_xxx" />
            </label>
            <div className="actions">
              <button type="button" disabled={busy} onClick={onStartByHostToken}>
                Start Session
              </button>
            </div>
            <label>
              Join Seat
              <select value={joinSeatInput} onChange={(e) => onJoinSeatInput(e.target.value)}>
                {joinSeatOptions.map((seat) => (
                  <option key={`seat-option-${seat}`} value={seat}>
                    Seat {seat}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Join Token
              <input value={joinTokenInput} onChange={(e) => onJoinTokenInput(e.target.value)} placeholder="seat_join_token" />
            </label>
            <label>
              Display Name
              <input value={displayNameInput} onChange={(e) => onDisplayNameInput(e.target.value)} />
            </label>
            <div className="actions">
              <button type="button" disabled={busy} onClick={onJoinSeat}>
                Join and Connect
              </button>
            </div>
            {Object.keys(lastJoinTokens).length > 0 ? (
              <div className="token-list">
                <p className="mono">Last create join tokens</p>
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
      </section>

      <section className="panel">
        <h2>Stream Connection</h2>
        <form onSubmit={onConnect} className="form">
          <label>
            Session ID
            <input value={sessionInput} onChange={(e) => onSessionInput(e.target.value)} placeholder="sess_xxx" />
          </label>
          <label>
            Session Token (optional)
            <input
              value={tokenInput}
              onChange={(e) => onTokenInput(e.target.value)}
              placeholder="session_p1_xxx (or empty for spectator)"
            />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Connect
            </button>
            <button type="button" onClick={onRefreshSessions} disabled={busy}>
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
  );
}
