import type { CSSProperties, ReactNode } from "react";
import type { LastMoveViewModel, SnapshotViewModel, TurnStageViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";
import pawnPieceUrl from "../../assets/pawn-piece.svg";
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
  stageFocus: Pick<TurnStageViewModel, "focusTileIndex" | "focusTileIndices" | "currentBeatKind" | "currentBeatLabel" | "currentBeatDetail" | "actorPlayerId">;
  weather: Pick<TurnStageViewModel, "weatherName" | "weatherEffect">;
  turnBanner: {
    text: string;
    detail: string;
  } | null;
  showTurnOverlay: boolean;
  minimalHeader?: boolean;
  overlayContent?: ReactNode;
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

export function BoardPanel({
  snapshot,
  manifestTiles,
  boardTopology,
  tileKindLabels,
  lastMove,
  stageFocus,
  weather,
  turnBanner,
  showTurnOverlay,
  minimalHeader = false,
  overlayContent = null,
}: BoardPanelProps) {
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

  const recentPathSteps = new Map<number, number>();
  for (const [index, tileIndex] of (lastMove?.pathTileIndices ?? []).entries()) {
    recentPathSteps.set(tileIndex, index + 1);
  }
  const fromPosition =
    lastMove?.fromTileIndex !== null && lastMove?.fromTileIndex !== undefined
      ? projectTilePosition(lastMove.fromTileIndex, tiles.length, normalizedTopology)
      : null;
  const toPosition =
    lastMove?.toTileIndex !== null && lastMove?.toTileIndex !== undefined
      ? projectTilePosition(lastMove.toTileIndex, tiles.length, normalizedTopology)
      : null;
  const movingPawnStyle =
    movedPlayerId !== null && fromPosition && toPosition
      ? ({
          "--board-move-from-x": `${((fromPosition.col - 0.5) / grid.cols) * 100}%`,
          "--board-move-from-y": `${((fromPosition.row - 0.5) / grid.rows) * 100}%`,
          "--board-move-to-x": `${((toPosition.col - 0.5) / grid.cols) * 100}%`,
          "--board-move-to-y": `${((toPosition.row - 0.5) / grid.rows) * 100}%`,
          "--board-move-player-color": playerColor(movedPlayerId),
        } as CSSProperties)
      : null;
  const boardOverlayMoveText =
    lastMove && showTurnOverlay ? board.lastMove(lastMove.playerId, lastMove.fromTileIndex, lastMove.toTileIndex) : "";
  const boardOverlayDetail =
    boardOverlayMoveText && boardOverlayMoveText !== "-"
      ? boardOverlayMoveText
      : turnBanner?.detail && turnBanner.detail !== "-"
        ? turnBanner.detail
        : stageFocus.currentBeatDetail !== "-"
          ? stageFocus.currentBeatDetail
          : "";

  if (tiles.length === 0) {
    return (
      <section className="panel board-panel">
        <h2>{board.title}</h2>
        <p>{board.loading}</p>
      </section>
    );
  }

  return (
    <section className={`panel board-panel ${minimalHeader ? "board-panel-minimal" : ""}`}>
      {minimalHeader ? (
        <div className="board-meta-bar">
          <strong>{snapshot ? board.roundTurnMarker(snapshot.round, snapshot.turn, snapshot.markerOwnerPlayerId, endTimeRemaining) : board.manifestBoard}</strong>
          {lastMove ? <small>{board.lastMove(lastMove.playerId, lastMove.fromTileIndex, lastMove.toTileIndex)}</small> : null}
        </div>
      ) : (
        <>
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
        </>
      )}
      <div className="board-scroll">
        <div className={`board-ring ${normalizedTopology === "line" ? "board-ring-line" : "board-ring-ring"}`} style={boardStyle}>
          {movingPawnStyle ? (
            <div
              className="board-moving-pawn-ghost"
              data-testid="board-moving-pawn-ghost"
              style={movingPawnStyle}
              aria-hidden="true"
            >
              {movedPlayerId}
            </div>
          ) : null}
          {tiles.map((tile) => {
            const isMoveFrom = lastMove?.fromTileIndex === tile.tileIndex;
            const isMoveTo = lastMove?.toTileIndex === tile.tileIndex;
            const pathStep = recentPathSteps.get(tile.tileIndex) ?? null;
            const isMoveTrail = pathStep !== null && !isMoveFrom && !isMoveTo;
            const isStageFocus = stageFocus.focusTileIndex === tile.tileIndex;
            const isStageCandidate = stageFocus.focusTileIndices.includes(tile.tileIndex) && !isStageFocus;
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
                } ${isMoveTrail ? "tile-move-trail" : ""} ${
                  pathStep !== null ? "tile-move-has-path" : ""
                } ${isFinish ? "tile-finish" : ""} ${isStageCandidate ? "tile-stage-candidate" : ""}`}
                data-focus-kind={isStageFocus ? stageFocus.currentBeatKind : undefined}
                style={{
                  gridRow: position.row,
                  gridColumn: position.col,
                }}
              >
                {isStageFocus ? <div className={`tile-stage-focus tile-stage-focus-${stageFocus.currentBeatKind}`} /> : null}
                {isStageCandidate ? <div className={`tile-stage-candidate-ring tile-stage-candidate-ring-${stageFocus.currentBeatKind}`} /> : null}
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
                {isMoveTrail ? (
                  <div
                    className="tile-path-step-badge"
                    data-testid={`board-path-step-${tile.tileIndex}`}
                    style={{ "--path-step-order": String(pathStep) } as CSSProperties}
                  >
                    {pathStep}
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
                          style={
                            {
                              "--pawn-player-color": playerColor(id),
                              "--pawn-piece-url": `url(${pawnPieceUrl})`,
                            } as CSSProperties
                          }
                          title={`P${id}`}
                        >
                          <span className="pawn-token-piece" aria-hidden="true" />
                          <span className="pawn-token-label">{id}</span>
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
        {showTurnOverlay && turnBanner ? (
          <div className="board-turn-overlay" data-testid="board-turn-overlay" aria-live="polite">
            <div className="board-turn-overlay-eyebrow">
              {stageFocus.currentBeatLabel !== "-" ? stageFocus.currentBeatLabel : board.title}
            </div>
            <strong>{turnBanner.text}</strong>
            {boardOverlayDetail ? <p>{boardOverlayDetail}</p> : null}
          </div>
        ) : null}
        {overlayContent ? <div className="board-overlay-content">{overlayContent}</div> : null}
      </div>
    </section>
  );
}
