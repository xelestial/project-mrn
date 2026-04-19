import { useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type {
  CurrentTurnRevealItem,
  LastMoveViewModel,
  SnapshotViewModel,
  TurnStageViewModel,
} from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";
import pawnPieceUrl from "../../assets/pawn-piece.svg";
import { usePawnAnimation } from "./usePawnAnimation";
import { DEFAULT_RING_TILE_COUNT, boardGridForTileCount, projectTilePosition } from "./boardProjection";
import { computeBoardHudFrame, sameBoardHudFrame } from "./boardHudLayout";
import { computeBoardHudScale } from "./boardHudScale";

type BoardPanelProps = {
  snapshot: SnapshotViewModel | null;
  manifestTiles?: Array<{
    tileIndex: number;
    tileKind: string;
    zoneColor: string;
    purchaseCost: number | null;
    rentCost: number | null;
    scoreCoinCount: number;
    ownerPlayerId: number | null;
    pawnPlayerIds: number[];
  }>;
  boardTopology?: string;
  tileKindLabels?: Record<string, string>;
  lastMove: LastMoveViewModel | null;
  stageFocus: Pick<
    TurnStageViewModel,
    "focusTileIndex" | "focusTileIndices" | "currentBeatKind" | "currentBeatLabel" | "currentBeatDetail" | "actorPlayerId" | "promptRequestType"
  >;
  weather: Pick<TurnStageViewModel, "weatherName" | "weatherEffect">;
  revealFocus?: Pick<CurrentTurnRevealItem, "seq" | "eventCode" | "label" | "detail" | "tone" | "focusTileIndex"> | null;
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

function costLabel(cost: number | null, rent: number | null, boardText: BoardText): string {
  return boardText.costLabel(cost, rent);
}

function tileSurfaceClass(kind: string): string {
  switch (kind) {
    case "S":
      return "tile-kind-fortune";
    case "F1":
    case "F2":
      return "tile-kind-finish";
    case "T3":
      return "tile-kind-premium";
    case "T2":
    default:
      return "tile-kind-land";
  }
}

function tileLandmarkGlyph(kind: string): string {
  switch (kind) {
    case "S":
      return "✦";
    case "F1":
    case "F2":
      return "◆";
    case "T3":
      return "▲";
    case "T2":
    default:
      return "●";
  }
}

export function BoardPanel({
  snapshot,
  manifestTiles,
  boardTopology,
  tileKindLabels,
  lastMove,
  stageFocus,
  weather,
  revealFocus = null,
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
  const boardScrollRef = useRef<HTMLDivElement | null>(null);
  const overlayTopAnchorTileRef = useRef<HTMLElement | null>(null);
  const overlayBottomAnchorTileRef = useRef<HTMLElement | null>(null);
  const overlayLeftAnchorTileRef = useRef<HTMLElement | null>(null);
  const overlayRightAnchorTileRef = useRef<HTMLElement | null>(null);
  const promptTopAnchorTileRef = useRef<HTMLElement | null>(null);
  const handTrayTopAnchorTileRef = useRef<HTMLElement | null>(null);
  const handTrayBottomAnchorTileRef = useRef<HTMLElement | null>(null);
  const [hudFrame, setHudFrame] = useState<ReturnType<typeof computeBoardHudFrame> | null>(null);
  const overlayTopAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 39) ? 39 : null;
  const overlayBottomAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 31) ? 31 : null;
  const overlayLeftAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 1) ? 1 : null;
  const overlayRightAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 9) ? 9 : null;
  const promptTopAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 36) ? 36 : null;
  const handTrayTopAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 32) ? 32 : null;
  const handTrayBottomAnchorTileIndex = tiles.some((tile) => tile.tileIndex === 31) ? 31 : null;
  const hudScale = computeBoardHudScale({
    boardWidth: hudFrame?.boardWidth ?? 0,
    boardHeight: hudFrame?.boardHeight ?? 0,
    viewportWidth: hudFrame?.viewportWidth ?? 0,
    viewportHeight: hudFrame?.viewportHeight ?? 0,
  });
  const boardStyle = {
    "--board-grid-cols": String(grid.cols),
    "--board-grid-rows": String(grid.rows),
    ...(hudFrame
      ? {
          "--board-overlay-safe-top": `${hudFrame.safeTop}px`,
          "--board-overlay-safe-bottom-gap": `${hudFrame.safeBottomGap}px`,
          "--board-overlay-safe-left": `${hudFrame.safeLeft}px`,
          "--board-overlay-safe-right-gap": `${hudFrame.safeRightGap}px`,
          "--board-hud-prompt-top-inset": `${hudFrame.promptTopInset}px`,
          "--board-hud-hand-tray-top-inset": `${hudFrame.handTrayTopInset}px`,
          "--board-hud-hand-tray-bottom-gap": `${hudFrame.handTrayBottomGap}px`,
          "--board-hud-hand-tray-height": `${hudFrame.handTrayHeight}px`,
        }
      : {}),
    "--board-scene-scale": String(hudScale.sceneScale),
    "--board-hud-gap": `${hudScale.overlayGap}px`,
    "--board-hud-gap-tight": `${hudScale.overlayGapTight}px`,
    "--board-hud-panel-padding": `${hudScale.panelPadding}px`,
    "--board-hud-card-padding": `${hudScale.cardPadding}px`,
    "--board-hud-panel-radius": `${hudScale.panelRadius}px`,
    "--board-hud-card-radius": `${hudScale.cardRadius}px`,
    "--board-hud-title-size": `${hudScale.titleFontSize}px`,
    "--board-hud-emphasis-size": `${hudScale.emphasisFontSize}px`,
    "--board-hud-body-size": `${hudScale.bodyFontSize}px`,
    "--board-hud-small-size": `${hudScale.smallFontSize}px`,
    "--board-hud-chip-size": `${hudScale.chipFontSize}px`,
    "--board-hud-stat-size": `${hudScale.statFontSize}px`,
    "--board-hud-control-height": `${hudScale.controlHeight}px`,
    "--board-hud-weather-min-height": `${hudScale.weatherMinHeight}px`,
    "--board-hud-player-card-min-height": `${hudScale.playerCardMinHeight}px`,
    "--board-hud-active-card-min-height": `${hudScale.activeCharacterMinHeight}px`,
    "--board-hud-prompt-max-height": `${hudScale.promptMaxHeight}px`,
    "--board-hud-prompt-shell-max-width": `${hudScale.promptShellMaxWidth}px`,
    "--board-hud-hand-tray-max-height": `${hudScale.handTrayMaxHeight}px`,
    "--board-hud-prompt-middle-reserve-bottom": `${hudScale.promptMiddleReserveBottom}px`,
    "--board-hud-choice-min-width": `${hudScale.choiceMinWidth}px`,
    "--board-hud-choice-min-height": `${hudScale.choiceMinHeight}px`,
    "--board-hud-hand-card-min-width": `${hudScale.handCardMinWidth}px`,
    "--board-hud-hand-card-min-height": `${hudScale.handCardMinHeight}px`,
    "--board-hand-grid-cols": String(hudScale.handGridColumns),
  } as CSSProperties;

  useLayoutEffect(() => {
    const scrollNode = boardScrollRef.current;
    const topTileNode = overlayTopAnchorTileRef.current;
    const bottomTileNode = overlayBottomAnchorTileRef.current;
    const leftTileNode = overlayLeftAnchorTileRef.current;
    const rightTileNode = overlayRightAnchorTileRef.current;
    const promptTopNode = promptTopAnchorTileRef.current;
    const handTrayTopNode = handTrayTopAnchorTileRef.current;
    const handTrayBottomNode = handTrayBottomAnchorTileRef.current;
    if (!scrollNode || (!topTileNode && !bottomTileNode && !leftTileNode && !rightTileNode)) {
      setHudFrame((prev) => (prev === null ? prev : null));
      return;
    }

    const updateOverlaySafeBounds = () => {
      const leftTileRect = leftTileNode?.getBoundingClientRect() ?? null;
      const rightTileRect = rightTileNode?.getBoundingClientRect() ?? null;
      const nextHudFrame = computeBoardHudFrame({
        scrollRect: scrollNode.getBoundingClientRect(),
        topTileRect: topTileNode?.getBoundingClientRect() ?? null,
        bottomTileRect: bottomTileNode?.getBoundingClientRect() ?? null,
        leftTileRect:
          leftTileRect === null
            ? null
            : {
                ...leftTileRect.toJSON(),
                left: leftTileRect.right,
              },
        rightTileRect:
          rightTileRect === null
            ? null
            : {
                ...rightTileRect.toJSON(),
                right: rightTileRect.left,
              },
        promptTopTileRect: promptTopNode?.getBoundingClientRect() ?? null,
        handTrayTopTileRect: handTrayTopNode?.getBoundingClientRect() ?? null,
        handTrayBottomTileRect: handTrayBottomNode?.getBoundingClientRect() ?? null,
      });
      setHudFrame((prev) => (sameBoardHudFrame(prev, nextHudFrame) ? prev : nextHudFrame));
    };

    updateOverlaySafeBounds();

    const resizeObserver = new ResizeObserver(() => {
      updateOverlaySafeBounds();
    });
    resizeObserver.observe(scrollNode);
    if (topTileNode) {
      resizeObserver.observe(topTileNode);
    }
    if (bottomTileNode) {
      resizeObserver.observe(bottomTileNode);
    }
    if (leftTileNode) {
      resizeObserver.observe(leftTileNode);
    }
    if (rightTileNode) {
      resizeObserver.observe(rightTileNode);
    }
    if (promptTopNode) {
      resizeObserver.observe(promptTopNode);
    }
    if (handTrayTopNode) {
      resizeObserver.observe(handTrayTopNode);
    }
    if (handTrayBottomNode) {
      resizeObserver.observe(handTrayBottomNode);
    }
    window.addEventListener("resize", updateOverlaySafeBounds);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateOverlaySafeBounds);
    };
  }, [
    overlayBottomAnchorTileIndex,
    overlayLeftAnchorTileIndex,
    handTrayBottomAnchorTileIndex,
    handTrayTopAnchorTileIndex,
    overlayRightAnchorTileIndex,
    overlayTopAnchorTileIndex,
    promptTopAnchorTileIndex,
  ]);

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

  // Step-by-step pawn animation
  const { animPlayerId, animTileIndex, animPhase } = usePawnAnimation(lastMove);
  const ghostStepPosition =
    animTileIndex !== null
      ? projectTilePosition(animTileIndex, tiles.length, normalizedTopology)
      : null;
  const stepGhostStyle =
    ghostStepPosition !== null && animPlayerId !== null
      ? ({
          "--board-move-ghost-x": `${((ghostStepPosition.col - 0.5) / grid.cols) * 100}%`,
          "--board-move-ghost-y": `${((ghostStepPosition.row - 0.5) / grid.rows) * 100}%`,
          "--board-move-player-color": playerColor(animPlayerId),
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
  const actorRevealFallbackTileIndex =
    revealFocus &&
    revealFocus.focusTileIndex === null &&
    stageFocus.actorPlayerId !== null
      ? tiles.find((tile) => {
          const tilePawns = tile.pawnPlayerIds.length > 0 ? tile.pawnPlayerIds : pawnFallback.get(tile.tileIndex) ?? [];
          return tilePawns.includes(stageFocus.actorPlayerId ?? -1);
        })?.tileIndex ?? null
      : null;
  const showBoardRevealPanel =
    Boolean(revealFocus) && revealFocus?.focusTileIndex === null && actorRevealFallbackTileIndex === null;

  if (tiles.length === 0) {
    return (
      <section className="panel board-panel">
        <h2>{board.title}</h2>
        <p>{board.loading}</p>
      </section>
    );
  }

  return (
    <section
      className={`panel board-panel board-panel-topology-${normalizedTopology} ${minimalHeader ? "board-panel-minimal" : ""}`}
    >
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
      <div ref={boardScrollRef} className="board-scroll" style={boardStyle}>
        <div className={`board-ring ${normalizedTopology === "line" ? "board-ring-line" : "board-ring-ring"}`} style={boardStyle}>
          {stepGhostStyle ? (
            // Step-by-step animation: ghost moves through each tile
            <div
              className={`board-moving-pawn-ghost board-pawn-step${animPhase === "arrived" ? " board-pawn-arrived" : ""}`}
              data-testid="board-moving-pawn-ghost"
              style={stepGhostStyle}
              aria-hidden="true"
            >
              {animPlayerId}
            </div>
          ) : movingPawnStyle ? (
            // Fallback arc animation when no pathTileIndices available
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
            const shouldShowLiveTag =
              isStageFocus &&
              stageFocus.currentBeatLabel !== "-" &&
              (stageFocus.currentBeatKind === "move" ||
                stageFocus.currentBeatKind === "economy" ||
                stageFocus.currentBeatKind === "effect");
            const position = projectTilePosition(tile.tileIndex, tiles.length, normalizedTopology);
            const ownerPlayerId = tile.ownerPlayerId ?? null;
            const tilePawns = tile.pawnPlayerIds.length > 0 ? tile.pawnPlayerIds : pawnFallback.get(tile.tileIndex) ?? [];
            const isRevealFocus =
              revealFocus?.focusTileIndex === tile.tileIndex ||
              (Boolean(revealFocus) &&
                actorRevealFallbackTileIndex !== null &&
                actorRevealFallbackTileIndex === tile.tileIndex);
            const kindLabel = tileKindLabel(tile.tileKind, board, tileKindLabels);
            const isFortune = tile.tileKind === "S";
            const isFinish = tile.tileKind === "F1" || tile.tileKind === "F2";
            const tileKindClass = tileSurfaceClass(tile.tileKind);
            const actorOnTile =
              stageFocus.actorPlayerId !== null &&
              tilePawns.includes(stageFocus.actorPlayerId) &&
              (isStageFocus || isMoveTo || movedPlayerId === stageFocus.actorPlayerId);
            const isPurchasePromptFocus = stageFocus.promptRequestType === "purchase_tile";
            return (
              <article
                key={tile.tileIndex}
                ref={(node) => {
                  if (tile.tileIndex === overlayTopAnchorTileIndex) {
                    overlayTopAnchorTileRef.current = node;
                  }
                  if (tile.tileIndex === overlayBottomAnchorTileIndex) {
                    overlayBottomAnchorTileRef.current = node;
                  }
                  if (tile.tileIndex === overlayLeftAnchorTileIndex) {
                    overlayLeftAnchorTileRef.current = node;
                  }
                  if (tile.tileIndex === overlayRightAnchorTileIndex) {
                    overlayRightAnchorTileRef.current = node;
                  }
                  if (tile.tileIndex === promptTopAnchorTileIndex) {
                    promptTopAnchorTileRef.current = node;
                  }
                  if (tile.tileIndex === handTrayTopAnchorTileIndex) {
                    handTrayTopAnchorTileRef.current = node;
                  }
                  if (tile.tileIndex === handTrayBottomAnchorTileIndex) {
                    handTrayBottomAnchorTileRef.current = node;
                  }
                }}
                className={`tile-card ${isMoveFrom ? "tile-move-from" : ""} ${isMoveTo ? "tile-move-to" : ""} ${
                  isFortune ? "tile-fortune" : ""
                } ${isMoveTrail ? "tile-move-trail" : ""} ${
                  pathStep !== null ? "tile-move-has-path" : ""
                } ${isFinish ? "tile-finish" : ""} ${tileKindClass} ${isStageCandidate ? "tile-stage-candidate" : ""}`}
                data-focus-kind={isStageFocus ? stageFocus.currentBeatKind : undefined}
                data-tile-kind={tile.tileKind}
                style={{
                  gridRow: position.row,
                  gridColumn: position.col,
                }}
              >
                {isStageFocus ? (
                  <div
                    className={`tile-stage-focus tile-stage-focus-${stageFocus.currentBeatKind} ${
                      isPurchasePromptFocus ? "tile-stage-focus-purchase" : ""
                    }`}
                  />
                ) : null}
                {isStageCandidate ? (
                  <div
                    className={`tile-stage-candidate-ring tile-stage-candidate-ring-${stageFocus.currentBeatKind} ${
                      isPurchasePromptFocus ? "tile-stage-candidate-ring-purchase" : ""
                    }`}
                  />
                ) : null}
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
                {isRevealFocus ? (
                  <div
                    className={`tile-reveal-spotlight tile-reveal-spotlight-${revealFocus?.tone ?? "effect"}`}
                    data-testid={`board-reveal-spotlight-${revealFocus?.eventCode ?? "event"}`}
                  >
                    <strong data-testid={`board-reveal-spotlight-title-${revealFocus?.eventCode ?? "event"}`}>
                      {revealFocus?.label ?? "-"}
                    </strong>
                    {revealFocus?.detail && revealFocus.detail !== "-" ? (
                      <small data-testid={`board-reveal-spotlight-detail-${revealFocus?.eventCode ?? "event"}`}>
                        {revealFocus.detail}
                      </small>
                    ) : null}
                  </div>
                ) : null}
                {shouldShowLiveTag ? (
                  <div className={`tile-live-tag tile-live-tag-${stageFocus.currentBeatKind}`}>
                    <strong>{stageFocus.currentBeatLabel}</strong>
                    {stageFocus.currentBeatDetail !== "-" ? <small>{stageFocus.currentBeatDetail}</small> : null}
                  </div>
                ) : null}
                <div className="tile-zone-strip" style={{ backgroundColor: zoneColorToCss(tile.zoneColor ?? "", board) }} />
                <div className="tile-head">
                  <strong>{tile.tileIndex + 1}</strong>
                  <span className="tile-kind-chip">
                    <span className="tile-kind-chip-icon" aria-hidden="true">
                      {tileLandmarkGlyph(tile.tileKind)}
                    </span>
                    <span>{kindLabel}</span>
                  </span>
                </div>
                {isFortune || isFinish ? (
                  <div className="tile-special-center">
                    <span className="tile-special-icon" aria-hidden="true">
                      {tileLandmarkGlyph(tile.tileKind)}
                    </span>
                    <strong>{kindLabel}</strong>
                  </div>
                ) : (
                  <div className="tile-body">
                    <small className="tile-cost-pill">{costLabel(tile.purchaseCost, tile.rentCost, board)}</small>
                  </div>
                )}
                <div className="tile-foot">
                  <div className="tile-badge-row">
                    <small className={`tile-owner-badge ${ownerPlayerId === null ? "tile-owner-badge-empty" : ""}`}>
                      {ownerPlayerId === null ? board.ownerNone : board.owner(ownerPlayerId)}
                    </small>
                    {tile.scoreCoinCount > 0 ? <small className="tile-score-badge">{board.scoreCoins(tile.scoreCoinCount)}</small> : null}
                  </div>
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
            {stageFocus.currentBeatLabel !== "-" ? (
              <div className="board-turn-overlay-eyebrow">{stageFocus.currentBeatLabel}</div>
            ) : null}
            <strong>{turnBanner.text}</strong>
            {boardOverlayDetail ? <p>{boardOverlayDetail}</p> : null}
          </div>
        ) : null}
        {showBoardRevealPanel && revealFocus ? (
          <div
            className={`board-reveal-panel board-reveal-panel-${revealFocus.tone}`}
            data-testid={`board-reveal-spotlight-${revealFocus.eventCode}`}
          >
            <strong data-testid={`board-reveal-spotlight-title-${revealFocus.eventCode}`}>{revealFocus.label}</strong>
            {revealFocus.detail && revealFocus.detail !== "-" ? (
              <p data-testid={`board-reveal-spotlight-detail-${revealFocus.eventCode}`}>{revealFocus.detail}</p>
            ) : null}
          </div>
        ) : null}
        {overlayContent ? <div className="board-overlay-content">{overlayContent}</div> : null}
      </div>
    </section>
  );
}
