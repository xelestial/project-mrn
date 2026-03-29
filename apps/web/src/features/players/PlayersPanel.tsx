import type { SnapshotViewModel } from "../../domain/selectors/streamSelectors";

type PlayersPanelProps = {
  snapshot: SnapshotViewModel | null;
};

export function PlayersPanel({ snapshot }: PlayersPanelProps) {
  const players = snapshot?.players ?? [];
  return (
    <section className="panel">
      <h2>플레이어</h2>
      {players.length === 0 ? <p>아직 플레이어 공개 스냅샷이 없습니다.</p> : null}
      <div className="players-grid">
        {players.map((player) => (
          <article key={player.playerId} className={`player-card ${player.alive ? "" : "out"}`}>
            <header>
              <strong>P{player.playerId}</strong>
              <span>{player.displayName}</span>
            </header>
            <p>{player.character || "-"}</p>
            <div className="player-stats">
              <small>위치 {player.position + 1}</small>
              <small>현금 {player.cash}</small>
              <small>조각 {player.shards}</small>
              <small>토지 {player.ownedTileCount}</small>
              <small>히든 {player.hiddenTrickCount}</small>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
