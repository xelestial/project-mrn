import type { CSSProperties } from "react";
import type { TurnHistoryEvent, TurnHistoryTurn, TurnHistoryViewModel } from "../../domain/selectors/streamSelectors";

type TurnHistoryTabsProps = {
  history: TurnHistoryViewModel;
  activeKey: string | null;
  pinned: boolean;
  selectedEventSeq: number | null;
  locale: string;
  onSelectTurn: (key: string) => void;
  onSelectEvent: (seq: number) => void;
  onReturnLive: () => void;
};

function hasUsefulDetail(event: TurnHistoryEvent): boolean {
  const detail = event.detail.trim();
  return detail.length > 0 && detail !== "-";
}

function playerColor(playerId: number): string {
  const palette = ["#f97316", "#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#facc15"];
  return palette[(Math.max(1, playerId) - 1) % palette.length];
}

const COMMON_EVENT_COLOR = "#64748b";

function uniquePlayerIds(playerIds: number[]): number[] {
  return Array.from(new Set(playerIds.filter((playerId) => Number.isFinite(playerId) && playerId > 0)));
}

function participantPlayerId(event: TurnHistoryEvent, keys: string[]): number | null {
  for (const key of keys) {
    const playerId = event.participants[key];
    if (Number.isFinite(playerId) && playerId > 0) {
      return playerId;
    }
  }
  return null;
}

function primaryEventPlayerId(event: TurnHistoryEvent, turn: TurnHistoryTurn): number | null {
  const explicitActor = participantPlayerId(event, ["actor", "actor_player_id", "acting_player_id", "player_id"]);
  if (explicitActor !== null) {
    return explicitActor;
  }
  if (event.eventCode === "rent_paid") {
    return participantPlayerId(event, ["payer", "payer_player_id", "owner", "owner_player_id"]) ?? turn.actorPlayerId;
  }
  if (event.eventCode.startsWith("mark_")) {
    return participantPlayerId(event, ["source", "source_player_id", "target", "target_player_id"]) ?? turn.actorPlayerId;
  }
  return participantPlayerId(event, ["source", "payer", "target", "owner", "from", "to"]) ?? turn.actorPlayerId;
}

function PlayerColorDot({ playerId, locale }: { playerId: number; locale: string }) {
  const label = locale === "ko" ? `플레이어 ${playerId}` : `Player ${playerId}`;
  return (
    <span
      className="turn-history-player-dot"
      style={{ "--turn-player-color": playerColor(playerId) } as CSSProperties}
      title={label}
      aria-label={label}
    >
      {playerId}
    </span>
  );
}

type RoundHistoryGroup = {
  round: number;
  latestTurn: TurnHistoryTurn;
  eventCount: number;
  importantCount: number;
  turns: TurnHistoryTurn[];
};

function groupTurnsByRound(turns: TurnHistoryTurn[]): RoundHistoryGroup[] {
  return turns.reduce<RoundHistoryGroup[]>((groups, turn) => {
    const usefulEvents = turn.events.filter(hasUsefulDetail);
    const current = groups.find((group) => group.round === turn.round);
    if (current) {
      current.latestTurn = turn;
      current.eventCount += usefulEvents.length;
      current.importantCount += usefulEvents.filter((event) => event.relevance !== "public" && event.eventCode !== "turn_start").length;
      current.turns.push(turn);
      return groups;
    }
    groups.push({
      round: turn.round,
      latestTurn: turn,
      eventCount: usefulEvents.length,
      importantCount: usefulEvents.filter((event) => event.relevance !== "public" && event.eventCode !== "turn_start").length,
      turns: [turn],
    });
    return groups;
  }, []);
}

export function TurnHistoryTabs({
  history,
  activeKey,
  pinned,
  selectedEventSeq,
  locale,
  onSelectTurn,
  onSelectEvent,
  onReturnLive,
}: TurnHistoryTabsProps) {
  if (history.turns.length === 0) {
    return null;
  }

  const activeTurn = history.turns.find((turn) => turn.key === activeKey) ?? history.latestTurn;
  const roundGroups = groupTurnsByRound(history.turns);
  const activeRound = activeTurn?.round ?? history.latestTurn?.round ?? roundGroups[roundGroups.length - 1]?.round ?? null;
  const activeRoundGroup = roundGroups.find((group) => group.round === activeRound) ?? roundGroups[roundGroups.length - 1] ?? null;
  const visibleItems =
    activeRoundGroup?.turns.flatMap((turn) =>
      turn.events.filter(hasUsefulDetail).map((event) => ({
        turn,
        event,
      })),
    ) ?? [];
  const emptyText = locale === "ko" ? "기록된 공개 이벤트 없음" : "No public events recorded";

  return (
    <section className="turn-history-tabs" data-testid="turn-history-tabs" aria-label={locale === "ko" ? "턴 히스토리" : "Turn history"}>
      <div className="turn-history-tabs-head">
        <div className="turn-history-tab-list" role="tablist" aria-label={locale === "ko" ? "라운드 선택" : "Round selector"}>
          {roundGroups.map((group) => {
            const isActive = activeRound === group.round;
            return (
              <button
                key={group.round}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`turn-history-round-tab ${isActive ? "turn-history-round-tab-active" : ""}`}
                data-testid={`turn-history-round-tab-${group.round}`}
                aria-label={locale === "ko" ? `${group.round}라운드` : `Round ${group.round}`}
                title={locale === "ko" ? `${group.round}라운드 / 이벤트 ${group.eventCount}개` : `Round ${group.round} / ${group.eventCount} events`}
                onClick={() => onSelectTurn(group.latestTurn.key)}
              >
                <span>{group.round}</span>
                {group.importantCount > 0 ? <strong className="turn-history-tab-badge">{group.importantCount}</strong> : null}
              </button>
            );
          })}
        </div>
        {pinned ? (
          <button
            type="button"
            className="turn-history-current-button"
            data-testid="turn-history-current"
            onClick={onReturnLive}
          >
            {locale === "ko" ? "현재 턴" : "Live"}
          </button>
        ) : null}
      </div>

      <div className="turn-history-event-list" role="list">
        {visibleItems.length > 0 ? (
          visibleItems.map(({ turn, event }, index) => {
            const isActive = selectedEventSeq === event.seq;
            const isCommonEvent = event.scope === "common";
            const actorPlayerId = isCommonEvent ? null : (primaryEventPlayerId(event, turn) ?? event.participantPlayerIds[0] ?? null);
            const actorColor = isCommonEvent ? COMMON_EVENT_COLOR : actorPlayerId === null ? "rgba(148, 163, 184, 0.78)" : playerColor(actorPlayerId);
            const eventMarker = isCommonEvent ? (locale === "ko" ? "공" : "C") : (actorPlayerId ?? "-");
            const playerSummary = isCommonEvent ? [] : uniquePlayerIds(event.participantPlayerIds);
            const tileSummary = event.focusTileIndices.map((tileIndex) => `#${tileIndex + 1}`).join(" ");
            return (
              <button
                key={event.seq}
                type="button"
                className={`turn-history-event turn-history-event-${isCommonEvent ? "common" : "player"} turn-history-event-${event.relevance} turn-history-event-${event.tone} ${
                  isActive ? "turn-history-event-active" : ""
                }`}
                style={{ "--turn-actor-color": actorColor } as CSSProperties}
                data-testid={`turn-history-event-${event.seq}`}
                data-history-scope={isCommonEvent ? "common" : "player"}
                data-relevance={event.relevance}
                data-actor-player-id={actorPlayerId ?? undefined}
                title={`${event.label} / ${event.detail}`}
                onClick={() => onSelectEvent(event.seq)}
              >
                <span
                  className="turn-history-event-order"
                  aria-label={
                    isCommonEvent
                      ? locale === "ko"
                        ? `공용 정보, ${index + 1}번째 기록`
                        : `Common information, history item ${index + 1}`
                      : actorPlayerId === null
                      ? locale === "ko"
                        ? `${index + 1}번째 기록`
                        : `History item ${index + 1}`
                      : locale === "ko"
                        ? `플레이어 ${actorPlayerId} 턴, ${index + 1}번째 기록`
                        : `Player ${actorPlayerId} turn, history item ${index + 1}`
                  }
                >
                  {eventMarker}
                </span>
                <span className="turn-history-event-meta">
                  <strong>{event.label}</strong>
                  {playerSummary.length > 0 || tileSummary ? (
                    <span className="turn-history-event-badges">
                      {playerSummary.length > 0 ? (
                        <span className="turn-history-player-dots" aria-label={locale === "ko" ? "관련 플레이어" : "Related players"}>
                          {playerSummary.map((playerId) => (
                            <PlayerColorDot key={playerId} playerId={playerId} locale={locale} />
                          ))}
                        </span>
                      ) : null}
                      {tileSummary ? <span className="turn-history-tile-badge">{tileSummary}</span> : null}
                    </span>
                  ) : null}
                </span>
                <span className="turn-history-event-detail">{event.detail}</span>
              </button>
            );
          })
        ) : (
          <p className="turn-history-empty">{emptyText}</p>
        )}
      </div>
    </section>
  );
}
