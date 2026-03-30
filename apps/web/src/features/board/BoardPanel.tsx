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
      return "운수";
    case "F1":
      return "종료 - 1";
    case "F2":
      return "종료 - 2";
    case "T2":
      return "토지";
    case "T3":
      return "고급 토지";
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
        <h2>보드</h2>
        <p>보드 스냅샷을 기다리는 중입니다.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>보드</h2>
      {snapshot ? (
        <p>
          {snapshot.round}라운드 / {snapshot.turn}턴 / 징표 소유자 P{snapshot.markerOwnerPlayerId ?? "-"} / 종료 시간{" "}
          {endTimeRemaining?.toFixed(2)}
        </p>
      ) : (
        <p>설정 정보(parameter manifest)로 초기화된 보드입니다.</p>
      )}
      {lastMove ? (
        <p className="board-move-summary">
          최근 이동: P{lastMove.playerId ?? "?"} {lastMove.fromTileIndex === null ? "?" : lastMove.fromTileIndex + 1}
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
                <small>{tile.zoneColor ? `구역 ${tile.zoneColor}` : "구역 -"}</small>
                <small>구매가 {tile.purchaseCost ?? "-"}</small>
                <small>통행료 {tile.rentCost ?? "-"}</small>
              </div>
              <div className="tile-foot">
                <small>소유자 P{tile.ownerPlayerId ?? "-"}</small>
                <div className="pawn-chips">
                  {tile.pawnPlayerIds.length > 0 ? (
                    tile.pawnPlayerIds.map((id) => (
                      <span key={`${tile.tileIndex}-p${id}`} className={`pawn-chip ${isMoveTo ? "pawn-arrived" : ""}`}>
                        P{id}
                      </span>
                    ))
                  ) : (
                    <small>말 없음</small>
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
