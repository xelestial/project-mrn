import type { SnapshotViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type PlayersPanelProps = {
  snapshot: SnapshotViewModel | null;
};

export function PlayersPanel({ snapshot }: PlayersPanelProps) {
  const { players: playersText } = useI18n();
  const players = snapshot?.players ?? [];
  return (
    <section className="panel">
      <h2>{playersText.title}</h2>
      {players.length === 0 ? <p>{playersText.waiting}</p> : null}
      <div className="players-grid">
        {players.map((player) => (
          <article key={player.playerId} className={`player-card ${player.alive ? "" : "out"}`}>
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
          </article>
        ))}
      </div>
    </section>
  );
}
