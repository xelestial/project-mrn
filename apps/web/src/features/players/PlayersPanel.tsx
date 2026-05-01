import type { SnapshotViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";
import { PlayerTrickPeek } from "./PlayerTrickPeek";

type PlayersPanelProps = {
  snapshot: SnapshotViewModel | null;
  currentActorPlayerId: number | null;
  currentLocalPlayerId?: number | null;
  variant?: "panel" | "strip";
};

export function PlayersPanel({
  snapshot,
  currentActorPlayerId,
  currentLocalPlayerId = null,
  variant = "panel",
}: PlayersPanelProps) {
  const { players: playersText, locale } = useI18n();
  const players = snapshot?.players ?? [];
  const grid = (
    <div className={variant === "strip" ? "players-strip" : "players-grid"}>
      {players.map((player) => {
        const publicTrickNames = player.publicTricks ?? [];
        const hiddenTrickCount = Math.max(player.hiddenTrickCount ?? 0, (player.trickCount ?? 0) - publicTrickNames.length);
        const trickPeekCardCount = publicTrickNames.length + hiddenTrickCount;

        return (
          <article
            key={player.playerId}
            className={`player-card ${player.alive ? "" : "out"} ${
              player.playerId === currentActorPlayerId ? "player-card-active" : ""
            } ${player.playerId === currentLocalPlayerId ? "player-card-local" : ""} ${
              variant === "strip" ? "player-card-strip" : ""
            }`}
            tabIndex={trickPeekCardCount > 0 ? 0 : undefined}
          >
            <header>
              <strong>P{player.playerId}</strong>
              <span>{player.displayName}</span>
            </header>
            <p>{player.character || "-"}</p>
            <div className="player-stats">
              <small>{playersText.stats.position(player.position + 1)}</small>
              <small>{playersText.stats.cash(player.cash)}</small>
              <small>{playersText.stats.shards(player.shards)}</small>
              <small>{playersText.stats.tiles(player.ownedTileCount)}</small>
              <small>{playersText.stats.hidden(player.hiddenTrickCount)}</small>
            </div>
            {trickPeekCardCount > 0 ? (
              <PlayerTrickPeek
                locale={locale}
                playerLabel={`P${player.playerId}`}
                publicTricks={publicTrickNames}
                hiddenTrickCount={hiddenTrickCount}
                testId={`player-panel-${player.playerId}-trick-peek`}
              />
            ) : null}
          </article>
        );
      })}
    </div>
  );

  if (variant === "strip") {
    return <section className="players-strip-panel">{grid}</section>;
  }

  return (
    <section className="panel">
      <h2>{playersText.title}</h2>
      {players.length === 0 ? <p>{playersText.waiting}</p> : null}
      {grid}
    </section>
  );
}
