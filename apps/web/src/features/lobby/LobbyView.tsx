import { FormEvent, useState } from "react";
import { type PublicSessionResult } from "../../infra/http/sessionApi";
import { useI18n } from "../../i18n/useI18n";

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
  const { lobby } = useI18n();
  const [collapsed, setCollapsed] = useState({
    controls: false,
    stream: true,
    sessions: false,
  });

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>{lobby.controlsTitle}</h2>
          <button
            type="button"
            className="route-tab"
            onClick={() => setCollapsed((prev) => ({ ...prev, controls: !prev.controls }))}
          >
            {collapsed.controls ? lobby.expand : lobby.collapse}
          </button>
        </div>
        {collapsed.controls ? null : (
          <div className="lobby-grid">
            <div>
              <h3>{lobby.createSessionTitle}</h3>
              <p>{lobby.createSessionDescription}</p>
              <label>
                {lobby.fields.seed}
                <input value={seedInput} onChange={(e) => onSeedInput(e.target.value)} />
              </label>
              <label>
                {lobby.fields.seatCount}
                <input value={seatCountInput} onChange={(e) => onSeatCountInput(e.target.value)} />
              </label>
              <label>
                {lobby.fields.aiProfile}
                <input value={aiProfile} onChange={(e) => onAiProfile(e.target.value)} />
              </label>
              <div className="seat-grid">
                {seatTypes.map((seatType, idx) => (
                  <label key={`seat-${idx + 1}`}>
                    {lobby.values.seat(String(idx + 1))}
                    <select
                      value={seatType}
                      onChange={(e) => onSeatTypeChange(idx, e.target.value === "human" ? "human" : "ai")}
                    >
                      <option value="human">{lobby.values.human}</option>
                      <option value="ai">{lobby.values.ai}</option>
                    </select>
                  </label>
                ))}
              </div>
              <div className="actions">
                <button type="button" data-testid="quick-start-human-vs-ai" disabled={busy} onClick={onQuickStartHumanVsAi}>
                  {lobby.buttons.quickStartHumanVsAi}
                </button>
                <button type="button" disabled={busy} onClick={onCreateCustomSession}>
                  {lobby.buttons.createCustomSession}
                </button>
                <button type="button" disabled={busy} onClick={onCreateAndStartAi}>
                  {lobby.buttons.createAndStartAi}
                </button>
              </div>
            </div>

            <div>
              <h3>{lobby.hostJoinTitle}</h3>
              <p>{lobby.hostJoinDescription}</p>
              <label>
                {lobby.fields.sessionId}
                <input value={sessionInput} onChange={(e) => onSessionInput(e.target.value)} placeholder={lobby.placeholders.sessionId} />
              </label>
              <label>
                {lobby.fields.hostToken}
                <input value={hostTokenInput} onChange={(e) => onHostTokenInput(e.target.value)} placeholder={lobby.placeholders.hostToken} />
              </label>
              <div className="actions">
                <button type="button" disabled={busy} onClick={onStartByHostToken}>
                  {lobby.buttons.startSession}
                </button>
              </div>
              <label>
                {lobby.fields.joinSeat}
                <select value={joinSeatInput} onChange={(e) => onJoinSeatInput(e.target.value)}>
                  {joinSeatOptions.map((seat) => (
                    <option key={`seat-option-${seat}`} value={seat}>
                      {lobby.values.seat(seat)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {lobby.fields.joinToken}
                <input value={joinTokenInput} onChange={(e) => onJoinTokenInput(e.target.value)} placeholder={lobby.placeholders.joinToken} />
              </label>
              <label>
                {lobby.fields.displayName}
                <input value={displayNameInput} onChange={(e) => onDisplayNameInput(e.target.value)} />
              </label>
              <div className="actions">
                <button type="button" disabled={busy} onClick={onJoinSeat}>
                  {lobby.buttons.joinAndConnect}
                </button>
              </div>
              {Object.keys(lastJoinTokens).length > 0 ? (
                <div className="token-list">
                  <p className="mono">{lobby.labels.latestCreateTokens}</p>
                  <div className="token-actions">
                    {Object.entries(lastJoinTokens).map(([seat, value]) => (
                      <button key={`token-${seat}`} type="button" onClick={() => onUseToken(seat, value)}>
                        {lobby.buttons.useSeatToken(seat)}
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
          <h2>{lobby.streamTitle}</h2>
          <button
            type="button"
            className="route-tab"
            onClick={() => setCollapsed((prev) => ({ ...prev, stream: !prev.stream }))}
          >
            {collapsed.stream ? lobby.expand : lobby.collapse}
          </button>
        </div>
        {collapsed.stream ? null : (
          <>
            <form onSubmit={onConnect} className="form">
              <label>
                {lobby.fields.sessionId}
                <input value={sessionInput} onChange={(e) => onSessionInput(e.target.value)} placeholder={lobby.placeholders.sessionId} />
              </label>
              <label>
                {lobby.fields.sessionToken}
                <input
                  value={tokenInput}
                  onChange={(e) => onTokenInput(e.target.value)}
                  placeholder={lobby.placeholders.sessionToken}
                />
              </label>
              <div className="actions">
                <button type="submit" disabled={busy}>
                  {lobby.buttons.connect}
                </button>
                <button type="button" onClick={onRefreshSessions} disabled={busy}>
                  {lobby.buttons.refreshSessions}
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
          <h2>{lobby.sessionListTitle(sessions.length)}</h2>
          <button
            type="button"
            className="route-tab"
            onClick={() => setCollapsed((prev) => ({ ...prev, sessions: !prev.sessions }))}
          >
            {collapsed.sessions ? lobby.expand : lobby.collapse}
          </button>
        </div>
        {collapsed.sessions ? null : (
          <div className="timeline">
            {sessions.map((session) => (
              <article key={session.session_id} className="timeline-item">
                <strong>{session.session_id}</strong>
                <span>{session.status}</span>
                <small>
                  R{session.round_index ?? 0} / T{session.turn_index ?? 0}
                </small>
                <button type="button" onClick={() => onUseSession(session.session_id)}>
                  {lobby.buttons.useSession}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
