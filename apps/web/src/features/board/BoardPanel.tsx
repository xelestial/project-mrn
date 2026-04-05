import type { CSSProperties } from "react";
import type { LastMoveViewModel, SnapshotViewModel, TurnStageViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";
import { DEFAULT_RING_TILE_COUNT, boardGridForTileCount, projectTilePosition } from "./boardProjection";

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
  stageFocus: Pick<TurnStageViewModel, "focusTileIndex" | "currentBeatKind" | "currentBeatLabel" | "currentBeatDetail" | "actorPlayerId">;
  weather: Pick<TurnStageViewModel, "weatherName" | "weatherEffect">;
};

type BoardText = ReturnType<typeof useI18n>["board"];

function tileKindLabel(kind: string, boardText: BoardText, labels?: Record<string, string>): string {
  const override = labels?.[kind];
  if (override && override.trim()) {
    return override;
  }
  switch (kind) {
    case "S":
      return boardText.tileKind.S;
    case "F1":
      return boardText.tileKind.F1;
    case "F2":
      return boardText.tileKind.F2;
    case "T2":
      return boardText.tileKind.T2;
    case "T3":
      return boardText.tileKind.T3;
    default:
      return kind;
  }
}

function zoneColorToCss(zoneColor: string, boardText: BoardText): string {
  const trimmed = zoneColor.trim().toLowerCase();
  if (!trimmed) {
    return "#274679";
  }
  return boardText.zoneColorCss[trimmed as keyof typeof boardText.zoneColorCss] ?? zoneColor;
}

function playerColor(playerId: number): string {
  const palette = ["#f97316", "#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#facc15"];
  return palette[(Math.max(1, playerId) - 1) % palette.length];
}

function zoneLabel(zoneColor: string, boardText: BoardText): string {
  return boardText.zoneLabel(zoneColor);
}

function costLabel(cost: number | null, rent: number | null, boardText: BoardText): string {
  return boardText.costLabel(cost, rent);
}

export function BoardPanel({ snapshot, manifestTiles, boardTopology, tileKindLabels, lastMove, stageFocus, weather }: BoardPanelProps) {
  const { board } = useI18n();
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

  const pawnFallback = new Map<number, number[]>();
  for (const player of snapshot?.players ?? []) {
    if (!player.alive) {
      continue;
    }
    const list = pawnFallback.get(player.position) ?? [];
    list.push(player.playerId);
    pawnFallback.set(player.position, list);
  }

  const movedPlayerId = lastMove?.playerId ?? null;
  const movedTileIndex = lastMove?.toTileIndex ?? null;
  if (movedPlayerId !== null && movedTileIndex !== null) {
    const moved = pawnFallback.get(movedTileIndex) ?? [];
    if (!moved.includes(movedPlayerId)) {
      moved.push(movedPlayerId);
      pawnFallback.set(movedTileIndex, moved);
    }
  }

  if (tiles.length === 0) {
    return (
      <section className="panel">
        <h2>{board.title}</h2>
        <p>{board.loading}</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>{board.title}</h2>
      {snapshot ? (
        <p>{board.roundTurnMarker(snapshot.round, snapshot.turn, snapshot.markerOwnerPlayerId, endTimeRemaining)}</p>
      ) : (
        <p>{board.manifestBoard}</p>
      )}
      {weather.weatherName !== "-" ? (
        <p className="board-weather-summary" data-testid="board-weather-summary">
          <strong>{weather.weatherName}</strong>
          <span>{weather.weatherEffect}</span>
        </p>
      ) : null}
      {stageFocus.currentBeatLabel !== "-" ? (
        <p className={`board-focus-summary board-focus-summary-${stageFocus.currentBeatKind}`} data-testid="board-focus-summary">
          <strong>{stageFocus.currentBeatLabel}</strong>
          <span>{stageFocus.currentBeatDetail}</span>
        </p>
      ) : null}
      {lastMove ? (
        <p className="board-move-summary">{board.lastMove(lastMove.playerId, lastMove.fromTileIndex, lastMove.toTileIndex)}</p>
      ) : null}
      <div className="board-scroll">
        <div className={`board-ring ${normalizedTopology === "line" ? "board-ring-line" : "board-ring-ring"}`} style={boardStyle}>
          {tiles.map((tile) => {
            const isMoveFrom = lastMove?.fromTileIndex === tile.tileIndex;
            const isMoveTo = lastMove?.toTileIndex === tile.tileIndex;
            const isStageFocus = stageFocus.focusTileIndex === tile.tileIndex;
            const position = projectTilePosition(tile.tileIndex, tiles.length, normalizedTopology);
            const ownerPlayerId = tile.ownerPlayerId ?? null;
            const tilePawns = tile.pawnPlayerIds.length > 0 ? tile.pawnPlayerIds : pawnFallback.get(tile.tileIndex) ?? [];
            const kindLabel = tileKindLabel(tile.tileKind, board, tileKindLabels);
            const isFortune = tile.tileKind === "S";
            const isFinish = tile.tileKind === "F1" || tile.tileKind === "F2";
            const actorOnTile =
              stageFocus.actorPlayerId !== null &&
              tilePawns.includes(stageFocus.actorPlayerId) &&
              (isStageFocus || isMoveTo || movedPlayerId === stageFocus.actorPlayerId);
            return (
              <article
                key={tile.tileIndex}
                className={`tile-card ${isMoveFrom ? "tile-move-from" : ""} ${isMoveTo ? "tile-move-to" : ""} ${
                  isFortune ? "tile-fortune" : ""
                } ${isFinish ? "tile-finish" : ""}`}
                data-focus-kind={isStageFocus ? stageFocus.currentBeatKind : undefined}
                style={{
                  gridRow: position.row,
                  gridColumn: position.col,
                }}
              >
                {isStageFocus ? <div className={`tile-stage-focus tile-stage-focus-${stageFocus.currentBeatKind}`} /> : null}
                {isMoveFrom ? (
                  <div className="tile-corner-badge tile-corner-badge-from" data-testid="board-move-start-badge">
                    {board.moveStartTag}
                  </div>
                ) : null}
                {isMoveTo ? (
                  <div className="tile-corner-badge tile-corner-badge-to" data-testid="board-move-end-badge">
                    {board.moveEndTag}
                  </div>
                ) : null}
                {actorOnTile ? (
                  <div className="tile-actor-banner" data-testid="board-actor-banner">
                    {board.activeTurnTag(stageFocus.actorPlayerId ?? 0)}
                  </div>
                ) : null}
                {isStageFocus && stageFocus.currentBeatLabel !== "-" ? (
                  <div className={`tile-live-tag tile-live-tag-${stageFocus.currentBeatKind}`}>
                    <strong>{stageFocus.currentBeatLabel}</strong>
                    {stageFocus.currentBeatDetail !== "-" ? <small>{stageFocus.currentBeatDetail}</small> : null}
                  </div>
                ) : null}
                <div className="tile-zone-strip" style={{ backgroundColor: zoneColorToCss(tile.zoneColor ?? "", board) }} />
                <div className="tile-head">
                  <strong>{tile.tileIndex + 1}</strong>
                  {!isFortune && !isFinish ? <span>{kindLabel}</span> : null}
                </div>
                {isFortune || isFinish ? (
                  <div className="tile-special-center">{kindLabel}</div>
                ) : (
                  <div className="tile-body">
                    <small>{zoneLabel(tile.zoneColor ?? "", board)}</small>
                    <small>{costLabel(tile.purchaseCost, tile.rentCost, board)}</small>
                  </div>
                )}
                <div className="tile-foot">
                  <small>{ownerPlayerId === null ? board.ownerNone : board.owner(ownerPlayerId)}</small>
                  <div className="pawn-chips">
                    {tilePawns.length > 0 ? (
                      tilePawns.map((id) => (
                        <span
                          key={`${tile.tileIndex}-p${id}`}
                          className={`pawn-token ${isMoveTo ? "pawn-arrived" : ""} ${
                            isStageFocus && stageFocus.actorPlayerId === id ? "pawn-active-turn" : ""
                          }`}
                          style={{ backgroundColor: playerColor(id) }}
                          title={`P${id}`}
                        >
                          {id}
                        </span>
                      ))
                    ) : (
                      <small className="pawn-empty">-</small>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
