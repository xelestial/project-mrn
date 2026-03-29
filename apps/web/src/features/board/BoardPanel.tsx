import type { LastMoveViewModel, SnapshotViewModel } from "../../domain/selectors/streamSelectors";

type BoardPanelProps = {
  snapshot: SnapshotViewModel | null;
  lastMove: LastMoveViewModel | null;
};

function ringPosition(tileIndex: number): { row: number; col: number } {
  if (tileIndex <= 10) {
    return { row: 1, col: tileIndex + 1 };
  }
  if (tileIndex <= 19) {
    return { row: tileIndex - 9, col: 11 };
  }
  if (tileIndex <= 30) {
    return { row: 11, col: 31 - tileIndex };
  }
  return { row: 41 - tileIndex, col: 1 };
}

function tileKindLabel(kind: string): string {
  switch (kind) {
    case "S":
      return "Fortune";
    case "F1":
      return "End - 1";
    case "F2":
      return "End - 2";
    case "T2":
      return "Land";
    case "T3":
      return "Land+";
    default:
      return kind;
  }
}

export function BoardPanel({ snapshot, lastMove }: BoardPanelProps) {
  if (!snapshot || snapshot.tiles.length === 0) {
    return (
      <section className="panel">
        <h2>Board</h2>
        <p>No board snapshot yet. Waiting for `turn_end_snapshot` event.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Board</h2>
      <p>
        Round {snapshot.round} / Turn {snapshot.turn} / Marker P{snapshot.markerOwnerPlayerId ?? "-"} / End Meter{" "}
        {snapshot.fValue.toFixed(2)}
      </p>
      {lastMove ? (
        <p className="board-move-summary">
          Last move: P{lastMove.playerId ?? "?"} {lastMove.fromTileIndex === null ? "?" : lastMove.fromTileIndex + 1}
          {" -> "}
          {lastMove.toTileIndex === null ? "?" : lastMove.toTileIndex + 1}
        </p>
      ) : null}
      <div className="board-ring">
        {snapshot.tiles.map((tile) => {
          const isMoveFrom = lastMove?.fromTileIndex === tile.tileIndex;
          const isMoveTo = lastMove?.toTileIndex === tile.tileIndex;
          return (
            <article
              key={tile.tileIndex}
              className={`tile-card ${isMoveFrom ? "tile-move-from" : ""} ${isMoveTo ? "tile-move-to" : ""}`}
              style={{
                gridRow: ringPosition(tile.tileIndex).row,
                gridColumn: ringPosition(tile.tileIndex).col,
              }}
            >
              <div className="tile-head">
                <strong>{tile.tileIndex + 1}</strong>
                <span>{tileKindLabel(tile.tileKind)}</span>
              </div>
              <div className="tile-body">
                <small>{tile.zoneColor || "-"}</small>
                <small>Buy {tile.purchaseCost ?? "-"}</small>
                <small>Rent {tile.rentCost ?? "-"}</small>
              </div>
              <div className="tile-foot">
                <small>Owner P{tile.ownerPlayerId ?? "-"}</small>
                <div className="pawn-chips">
                  {tile.pawnPlayerIds.length > 0 ? (
                    tile.pawnPlayerIds.map((id) => (
                      <span key={`${tile.tileIndex}-p${id}`} className={`pawn-chip ${isMoveTo ? "pawn-arrived" : ""}`}>
                        P{id}
                      </span>
                    ))
                  ) : (
                    <small>-</small>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
