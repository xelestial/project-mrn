import type { CSSProperties } from "react";
import type { LastMoveViewModel, SnapshotViewModel } from "../../domain/selectors/streamSelectors";
import { boardGridForTileCount, projectTilePosition, DEFAULT_RING_TILE_COUNT } from "./boardProjection";

type BoardPanelProps = {
  snapshot: SnapshotViewModel | null;
  manifestTiles?: Array<{
    tileIndex: number;
    tileKind: string;
    zoneColor: string;
    purchaseCost: number | null;
    rentCost: number | null;
    ownerPlayerId: number | null;
    pawnPlayerIds: number[];
  }>;
  boardTopology?: string;
  tileKindLabels?: Record<string, string>;
  lastMove: LastMoveViewModel | null;
};

function tileKindLabel(kind: string, labels?: Record<string, string>): string {
  const override = labels?.[kind];
  if (override && override.trim()) {
    return override;
  }
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

export function BoardPanel({ snapshot, manifestTiles, boardTopology, tileKindLabels, lastMove }: BoardPanelProps) {
  const tiles = (snapshot?.tiles && snapshot.tiles.length > 0 ? snapshot.tiles : manifestTiles ?? []).slice();
  tiles.sort((a, b) => a.tileIndex - b.tileIndex);
  const normalizedTopology = boardTopology === "line" ? "line" : "ring";
  const effectiveTileCount = tiles.length > 0 ? tiles.length : DEFAULT_RING_TILE_COUNT;
  const grid = boardGridForTileCount(effectiveTileCount, normalizedTopology);
  const endTimeRemaining = snapshot ? Math.max(0, 15 - snapshot.fValue) : null;
  const boardStyle = {
    "--board-grid-cols": String(grid.cols),
    "--board-grid-rows": String(grid.rows),
  } as CSSProperties;
  if (tiles.length === 0) {
    return (
      <section className="panel">
        <h2>Board</h2>
        <p>No board snapshot yet. Waiting for stream snapshot or manifest bootstrap.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Board</h2>
      {snapshot ? (
        <p>
          Round {snapshot.round} / Turn {snapshot.turn} / Marker P{snapshot.markerOwnerPlayerId ?? "-"} / End Time{" "}
          {endTimeRemaining?.toFixed(2)}
        </p>
      ) : (
        <p>Board initialized from parameter manifest.</p>
      )}
      {lastMove ? (
        <p className="board-move-summary">
          Last move: P{lastMove.playerId ?? "?"} {lastMove.fromTileIndex === null ? "?" : lastMove.fromTileIndex + 1}
          {" -> "}
          {lastMove.toTileIndex === null ? "?" : lastMove.toTileIndex + 1}
        </p>
      ) : null}
      <div
        className="board-ring"
        style={boardStyle}
      >
        {tiles.map((tile) => {
          const isMoveFrom = lastMove?.fromTileIndex === tile.tileIndex;
          const isMoveTo = lastMove?.toTileIndex === tile.tileIndex;
          const position = projectTilePosition(tile.tileIndex, tiles.length, normalizedTopology);
          return (
            <article
              key={tile.tileIndex}
              className={`tile-card ${isMoveFrom ? "tile-move-from" : ""} ${isMoveTo ? "tile-move-to" : ""}`}
              style={{
                gridRow: position.row,
                gridColumn: position.col,
              }}
            >
              <div className="tile-head">
                <strong>{tile.tileIndex + 1}</strong>
                <span>{tileKindLabel(tile.tileKind, tileKindLabels)}</span>
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
