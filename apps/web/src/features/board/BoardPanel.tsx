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
import scoreTokenStack1Url from "../../assets/score-token-stack-1.svg";
import scoreTokenStack2Url from "../../assets/score-token-stack-2.svg";
import scoreTokenStack3Url from "../../assets/score-token-stack-3.svg";
import yeopjeonCoinUrl from "../../assets/yeopjeon-coin.svg";
import { characterSpriteSetForPlayer } from "../../domain/characters/characterSprites";
import type { CharacterSpriteSet, CharacterWalkSprite } from "../../domain/characters/characterSprites";
import { usePawnAnimation } from "./usePawnAnimation";
import {
  DEFAULT_RING_TILE_COUNT,
  boardGridForTileCount,
  projectTilePosition,
  projectTileQuarterview,
  quarterviewBoardGeometry,
  quarterviewFacingForTileStep,
  quarterviewIdleFacingForTile,
  quarterviewTilePolygons,
} from "./boardProjection";
import type { QuarterviewFacing } from "./boardProjection";
import type { QuarterviewTilePolygon } from "./boardProjection";
import type { QuarterviewPosition } from "./boardProjection";
import { boardHudFrameToCssVars, computeBoardHudFrame, sameBoardHudFrame } from "./boardHudLayout";
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
  historyFocusPlayerIds?: number[];
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
  if (kind === "T2" || kind === "T3") {
    const landOverride = labels?.T2;
    return landOverride && landOverride.trim() ? landOverride : boardText.tileKind.T2;
  }
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
    default:
      return kind;
  }
}

const ZONE_COLOR_FALLBACK_CSS: Record<string, string> = {
  "": "#475569",
  black: "#475569",
  red: "#ef4444",
  yellow: "#eab308",
  blue: "#3b82f6",
  green: "#22c55e",
  white: "#e2e8f0",
  "검은색": "#475569",
  "빨간색": "#ef4444",
  "노란색": "#eab308",
  "파란색": "#3b82f6",
  "초록색": "#22c55e",
  "하얀색": "#e2e8f0",
};

function zoneColorToCss(zoneColor: string, boardText: BoardText): string {
  const trimmed = zoneColor.trim().toLowerCase();
  if (!trimmed) {
    return "#274679";
  }
  return boardText.zoneColorCss[trimmed as keyof typeof boardText.zoneColorCss] ?? ZONE_COLOR_FALLBACK_CSS[trimmed] ?? zoneColor;
}

const FALLBACK_TILE_FACE_COLORS = ["#2f7de1", "#06b6d4", "#a855f7", "#f97316", "#22c55e", "#ec4899", "#84cc16"];

function tileFaceColor(kind: string, tileIndex: number, zoneColor: string, boardText: BoardText): string {
  if (zoneColor.trim()) {
    return zoneColorToCss(zoneColor, boardText);
  }
  if (kind === "S" || kind === "F1" || kind === "F2") {
    return "#e7f2ff";
  }
  return FALLBACK_TILE_FACE_COLORS[Math.abs(tileIndex) % FALLBACK_TILE_FACE_COLORS.length];
}

function playerColor(playerId: number): string {
  const palette = ["#f97316", "#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#facc15"];
  return palette[(Math.max(1, playerId) - 1) % palette.length];
}

const SCORE_TOKEN_STACK_URLS = [scoreTokenStack1Url, scoreTokenStack2Url, scoreTokenStack3Url] as const;

function normalizedScoreTokenCount(scoreCoinCount: number): number {
  return Number.isFinite(scoreCoinCount) ? Math.max(1, Math.trunc(scoreCoinCount)) : 1;
}

function scoreTokenStackUrl(scoreCoinCount: number): string {
  const stackIndex = Math.min(3, normalizedScoreTokenCount(scoreCoinCount)) - 1;
  return SCORE_TOKEN_STACK_URLS[stackIndex];
}

function renderScoreToken(scoreCoinCount: number, className: string, label: string): ReactNode {
  const normalizedCount = normalizedScoreTokenCount(scoreCoinCount);
  const stackCount = Math.min(3, normalizedCount);
  return (
    <span
      className={`score-token score-token-stack-${stackCount} ${className}`}
      data-score-count={normalizedCount}
      aria-label={label}
      title={label}
    >
      <img src={scoreTokenStackUrl(normalizedCount)} alt="" draggable={false} />
      <span className="score-token-count">{normalizedCount}</span>
    </span>
  );
}

const PLAYER_SPRITE_SETS: Record<number, CharacterSpriteSet> = {
  1: characterSpriteSetForPlayer(1),
  2: characterSpriteSetForPlayer(2),
  3: characterSpriteSetForPlayer(3),
  4: characterSpriteSetForPlayer(4),
};
const BOARD_STANDEE_WALK_STEP_MS = 420;

function playerSpriteUrl(playerId: number, facing: QuarterviewFacing): string | null {
  return PLAYER_SPRITE_SETS[playerId]?.sprites[facing] ?? null;
}

function playerWalkSprite(playerId: number, facing: QuarterviewFacing): CharacterWalkSprite | null {
  return PLAYER_SPRITE_SETS[playerId]?.walkSprites?.[facing] ?? null;
}

function playerSpriteVisualScale(playerId: number): number {
  return PLAYER_SPRITE_SETS[playerId]?.visualScale ?? 1;
}

function standeeBoardInwardOffset(position: Pick<QuarterviewPosition, "xPercent" | "yPercent" | "lane">): { x: number; y: number } {
  if (position.lane === "line") {
    return { x: 0, y: 0 };
  }
  const dx = 50 - position.xPercent;
  const dy = 50 - position.yPercent;
  const distance = Math.hypot(dx, dy);
  if (distance < 0.01) {
    return { x: 0, y: 0 };
  }
  const amount = 16;
  return {
    x: (dx / distance) * amount,
    y: (dy / distance) * amount,
  };
}

function tilePriceValue(value: number | null, boardText: BoardText): string {
  return value === null ? "-" : `${value}${boardText.tilePrice.unit}`;
}

function renderTilePrice(cost: number | null, boardText: BoardText, className: string): ReactNode {
  const label = `${boardText.tilePrice.purchase} ${tilePriceValue(cost, boardText)}`;
  return (
    <span className={className} title={label} aria-label={label}>
      <span className="tile-price-label">{boardText.tilePrice.purchase}</span>
      <span className="tile-price-coin" aria-hidden="true">
        <img src={yeopjeonCoinUrl} alt="" draggable={false} />
        <strong className="tile-price-value">{cost === null ? "-" : cost}</strong>
      </span>
    </span>
  );
}

function tileSurfaceClass(kind: string): string {
  switch (kind) {
    case "S":
      return "tile-kind-fortune";
    case "F1":
    case "F2":
      return "tile-kind-finish";
    case "T2":
    case "T3":
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
    case "T2":
    case "T3":
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
  historyFocusPlayerIds = [],
  turnBanner,
  showTurnOverlay,
  minimalHeader = false,
  overlayContent = null,
}: BoardPanelProps) {
  const { board } = useI18n();
  const tiles = (snapshot?.tiles && snapshot.tiles.length > 0 ? snapshot.tiles : manifestTiles ?? []).slice();
  tiles.sort((a, b) => a.tileIndex - b.tileIndex);
  const normalizedTopology = boardTopology === "line" ? "line" : "ring";
  const useQuarterview = normalizedTopology === "ring";
  const effectiveTileCount = tiles.length > 0 ? tiles.length : DEFAULT_RING_TILE_COUNT;
  const grid = boardGridForTileCount(effectiveTileCount, normalizedTopology);
  const quarterviewGeometry = quarterviewBoardGeometry(grid.boardSize);
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
    "--board-diamond-tile-side": `${quarterviewGeometry.tileInlinePercent}%`,
    "--board-qv-aspect-ratio": String(quarterviewGeometry.boardAspectRatio),
    "--board-qv-tile-angle": `${quarterviewGeometry.tileAngleDeg}deg`,
    "--board-qv-tile-inline": `${quarterviewGeometry.tileInlinePercent}%`,
    "--board-qv-tile-block": `${quarterviewGeometry.tileBlockPercent}%`,
    ...boardHudFrameToCssVars(hudFrame),
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
  const historyFocusPlayerIdSet = new Set(historyFocusPlayerIds);
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
  const shouldDelayEffectMove =
    Boolean(lastMove) &&
    Boolean(revealFocus) &&
    (revealFocus?.eventCode === "fortune_resolved" ||
      revealFocus?.eventCode === "trick_used" ||
      revealFocus?.eventCode === "mark_resolved");
  const { animPlayerId, animTileIndex, animPreviousTileIndex, animStepIndex, animPhase } = usePawnAnimation(
    lastMove,
    tiles.length,
    shouldDelayEffectMove ? 900 : 0
  );
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
  const quarterviewGhostPosition =
    animTileIndex !== null
      ? projectTileQuarterview(animTileIndex, tiles.length, normalizedTopology)
      : movedTileIndex !== null
        ? projectTileQuarterview(movedTileIndex, tiles.length, normalizedTopology)
        : null;
  const quarterviewMovingPawnStyle =
    useQuarterview && quarterviewGhostPosition !== null && (animPlayerId ?? movedPlayerId) !== null
      ? (() => {
          const inwardOffset = standeeBoardInwardOffset(quarterviewGhostPosition);
          return {
            "--board-standee-x": `${quarterviewGhostPosition.xPercent}%`,
            "--board-standee-y": `${quarterviewGhostPosition.yPercent}%`,
            "--board-standee-color": playerColor(animPlayerId ?? movedPlayerId ?? 1),
            "--board-standee-z": String(quarterviewGhostPosition.zIndex + 14),
            "--board-standee-offset-x": `${inwardOffset.x}px`,
            "--board-standee-offset-y": `${inwardOffset.y}px`,
          } as CSSProperties;
        })()
      : null;
  const standeePlayerIds = new Set<number>();
  const rawStandeePlacements = (snapshot?.players ?? [])
    .filter((player) => player.alive)
    .map((player) => {
      const isAnimating = useQuarterview && animPlayerId === player.playerId && quarterviewGhostPosition !== null;
      const position = isAnimating ? quarterviewGhostPosition : projectTileQuarterview(player.position, tiles.length, normalizedTopology);
      const tileIndex = isAnimating && animTileIndex !== null ? animTileIndex : player.position;
      const facingTileIndex = isAnimating && animTileIndex !== null ? animTileIndex : player.position;
      const facing = isAnimating
        ? quarterviewFacingForTileStep(animPreviousTileIndex, facingTileIndex, tiles.length, normalizedTopology)
        : quarterviewIdleFacingForTile(player.position, tiles.length, normalizedTopology);
      const walkSprite = isAnimating ? playerWalkSprite(player.playerId, facing) : null;
      standeePlayerIds.add(player.playerId);
      return {
        playerId: player.playerId,
        displayName: player.displayName,
        character: player.character,
        tileIndex,
        position,
        facing,
        assetUrl: playerSpriteUrl(player.playerId, facing),
        walkSprite,
        walkFrameDelayMs: walkSprite ? -Math.max(0, animStepIndex) * BOARD_STANDEE_WALK_STEP_MS : 0,
        spriteVisualScale: playerSpriteVisualScale(player.playerId),
        isAnimating,
      };
    });
  const standeeTileCounts = rawStandeePlacements.reduce((counts, placement) => {
    counts.set(placement.tileIndex, (counts.get(placement.tileIndex) ?? 0) + 1);
    return counts;
  }, new Map<number, number>());
  const standeeTileSeen = new Map<number, number>();
  const standeePlacements = rawStandeePlacements.map((placement) => {
    const tileMateIndex = standeeTileSeen.get(placement.tileIndex) ?? 0;
    standeeTileSeen.set(placement.tileIndex, tileMateIndex + 1);
    return {
      ...placement,
      tileMateIndex,
      tileMateCount: standeeTileCounts.get(placement.tileIndex) ?? 1,
      animationKey: placement.isAnimating ? `${placement.playerId}-${placement.tileIndex}-${animStepIndex}` : `${placement.playerId}-idle`,
    };
  });
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
    Boolean(revealFocus) && (useQuarterview || (revealFocus?.focusTileIndex === null && actorRevealFallbackTileIndex === null));
  const tilesByIndex = new Map(tiles.map((tile) => [tile.tileIndex, tile]));
  const projectedTilePolygons = useQuarterview
    ? quarterviewTilePolygons(tiles.length, normalizedTopology).filter((polygon) => tilesByIndex.has(polygon.tileIndex))
    : [];
  const svgPointList = (points: QuarterviewTilePolygon["points"] | QuarterviewTilePolygon["zonePoints"]) =>
    points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
  const svgMatrix = (matrix: QuarterviewTilePolygon["contentTransform"]) =>
    `matrix(${matrix.a.toFixed(5)}, ${matrix.b.toFixed(5)}, ${matrix.c.toFixed(5)}, ${matrix.d.toFixed(5)}, ${matrix.e.toFixed(2)}, ${matrix.f.toFixed(2)})`;
  const renderProjectedTile = (tile: (typeof tiles)[number], polygon: QuarterviewTilePolygon) => {
    const ownerPlayerId = tile.ownerPlayerId ?? null;
    const hasOwner = ownerPlayerId !== null;
    const tilePawns = tile.pawnPlayerIds.length > 0 ? tile.pawnPlayerIds : pawnFallback.get(tile.tileIndex) ?? [];
    const visiblePawnIds = tilePawns.filter((id) => !standeePlayerIds.has(id));
    const kindLabel = tileKindLabel(tile.tileKind, board, tileKindLabels);
    const isFortune = tile.tileKind === "S";
    const isFinish = tile.tileKind === "F1" || tile.tileKind === "F2";
    const isSpecial = isFortune || isFinish;
    const isMoveFrom = lastMove?.fromTileIndex === tile.tileIndex;
    const isMoveTo = lastMove?.toTileIndex === tile.tileIndex;
    const pathStep = recentPathSteps.get(tile.tileIndex) ?? null;
    const isMoveTrail = pathStep !== null && !isMoveFrom && !isMoveTo;
    const isStageFocus = stageFocus.focusTileIndex === tile.tileIndex;
    const isStageCandidate = stageFocus.focusTileIndices.includes(tile.tileIndex) && !isStageFocus;
    const isRevealFocus =
      revealFocus?.focusTileIndex === tile.tileIndex ||
      (Boolean(revealFocus) &&
        actorRevealFallbackTileIndex !== null &&
        actorRevealFallbackTileIndex === tile.tileIndex);
    const isPurchaseRevealFocus = isRevealFocus && revealFocus?.eventCode === "tile_purchased";
    const zoneColor = tileFaceColor(tile.tileKind, tile.tileIndex, tile.zoneColor ?? "", board);
    const ownerColor = hasOwner ? playerColor(ownerPlayerId) : "transparent";

    return (
      <g
        key={`projected-tile-${tile.tileIndex}`}
        className={`board-projected-tile ${isSpecial ? "board-projected-tile-special" : ""} ${
          isFortune ? "board-projected-tile-fortune" : ""
        } ${isFinish ? "board-projected-tile-finish" : ""} ${isMoveFrom ? "board-projected-tile-move-from" : ""} ${
          isMoveTo ? "board-projected-tile-move-to" : ""
        } ${isMoveTrail ? "board-projected-tile-move-trail" : ""} ${
          isStageFocus ? "board-projected-tile-stage-focus" : ""
        } ${isStageCandidate ? "board-projected-tile-stage-candidate" : ""} ${
          isRevealFocus ? "board-projected-tile-reveal-focus" : ""
        } ${isPurchaseRevealFocus ? "board-projected-tile-purchase-stamped" : ""} ${
          hasOwner ? "board-projected-tile-owned" : ""
        }`}
        data-lane={polygon.lane}
        data-tile-kind={tile.tileKind}
        style={
          {
            "--tile-zone-color": zoneColor,
            "--tile-owner-color": ownerColor,
          } as CSSProperties
        }
      >
        <polygon className="board-projected-tile-base" points={svgPointList(polygon.points)} />
        <foreignObject
          className="board-projected-content-object"
          x={0}
          y={0}
          width={100}
          height={100}
          transform={svgMatrix(polygon.contentTransform)}
        >
          {isSpecial ? (
            <div className="board-projected-special">
              <span className="board-projected-special-icon" aria-hidden="true">
                {tileLandmarkGlyph(tile.tileKind)}
              </span>
              <strong>{kindLabel}</strong>
              <small>#{tile.tileIndex + 1}</small>
              {tile.scoreCoinCount > 0
                ? renderScoreToken(tile.scoreCoinCount, "board-projected-score-token", board.scoreCoins(tile.scoreCoinCount))
                : null}
            </div>
          ) : (
            <div className="board-projected-content">
              <div className="board-projected-zone">
                <span className="board-projected-index">{tile.tileIndex + 1}</span>
                <strong>{kindLabel}</strong>
              </div>
              <div className="board-projected-main">
                {renderTilePrice(tile.purchaseCost, board, "board-projected-cost")}
              </div>
              <div className={`board-projected-stamp ${hasOwner ? "" : "board-projected-stamp-empty"}`}>
                <span>{hasOwner ? `P${ownerPlayerId}` : ""}</span>
              </div>
              {tile.scoreCoinCount > 0
                ? renderScoreToken(tile.scoreCoinCount, "board-projected-score-token", board.scoreCoins(tile.scoreCoinCount))
                : null}
            </div>
          )}
        </foreignObject>
        {pathStep !== null ? (
          <text className="board-projected-path-step" x={polygon.centerX + polygon.bboxWidth * 0.23} y={polygon.centerY + polygon.bboxHeight * 0.2}>
            {pathStep}
          </text>
        ) : null}
        {visiblePawnIds.length > 0 ? (
          <text className="board-projected-pawn-count" x={polygon.centerX - polygon.bboxWidth * 0.26} y={polygon.centerY + polygon.bboxHeight * 0.2}>
            {visiblePawnIds.length}
          </text>
        ) : null}
      </g>
    );
  };

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
        <div
          className={`board-ring ${
            useQuarterview
              ? "board-ring-quarterview board-ring-ring"
              : normalizedTopology === "line"
                ? "board-ring-line"
                : "board-ring-ring"
          }`}
          style={boardStyle}
        >
          {!useQuarterview && stepGhostStyle ? (
            // Step-by-step animation: ghost moves through each tile
            <div
              className={`board-moving-pawn-ghost board-pawn-step${animPhase === "arrived" ? " board-pawn-arrived" : ""}`}
              data-testid="board-moving-pawn-ghost"
              style={stepGhostStyle}
              aria-hidden="true"
            >
              {animPlayerId}
            </div>
          ) : !useQuarterview && movingPawnStyle ? (
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
          {useQuarterview && projectedTilePolygons.length > 0 ? (
            <svg className="board-projected-tile-layer" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
              {projectedTilePolygons
                .slice()
                .sort((a, b) => a.zIndex - b.zIndex)
                .map((polygon) => {
                  const tile = tilesByIndex.get(polygon.tileIndex);
                  return tile ? renderProjectedTile(tile, polygon) : null;
                })}
            </svg>
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
            const quarterviewPosition = projectTileQuarterview(tile.tileIndex, tiles.length, normalizedTopology);
            const ownerPlayerId = tile.ownerPlayerId ?? null;
            const hasOwner = ownerPlayerId !== null;
            const tilePawns = tile.pawnPlayerIds.length > 0 ? tile.pawnPlayerIds : pawnFallback.get(tile.tileIndex) ?? [];
            const isRevealFocus =
              revealFocus?.focusTileIndex === tile.tileIndex ||
              (Boolean(revealFocus) &&
                actorRevealFallbackTileIndex !== null &&
                actorRevealFallbackTileIndex === tile.tileIndex);
            const isPurchaseRevealFocus = isRevealFocus && revealFocus?.eventCode === "tile_purchased";
            const kindLabel = tileKindLabel(tile.tileKind, board, tileKindLabels);
            const isFortune = tile.tileKind === "S";
            const isFinish = tile.tileKind === "F1" || tile.tileKind === "F2";
            const tileKindClass = tileSurfaceClass(tile.tileKind);
            const actorOnTile =
              stageFocus.actorPlayerId !== null &&
              tilePawns.includes(stageFocus.actorPlayerId) &&
              (isStageFocus || isMoveTo || movedPlayerId === stageFocus.actorPlayerId);
            const isPurchasePromptFocus = stageFocus.promptRequestType === "purchase_tile";
            const tileStyle = (useQuarterview
              ? {
                  "--board-tile-x": `${quarterviewPosition.xPercent}%`,
                  "--board-tile-y": `${quarterviewPosition.yPercent}%`,
                  "--board-tile-z": String(quarterviewPosition.zIndex),
                  "--tile-owner-color": hasOwner ? playerColor(ownerPlayerId) : "transparent",
                  "--tile-zone-color": tileFaceColor(tile.tileKind, tile.tileIndex, tile.zoneColor ?? "", board),
                }
              : {
                  gridRow: position.row,
                  gridColumn: position.col,
                  "--tile-owner-color": hasOwner ? playerColor(ownerPlayerId) : "transparent",
                  "--tile-zone-color": tileFaceColor(tile.tileKind, tile.tileIndex, tile.zoneColor ?? "", board),
                }) as unknown as CSSProperties;
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
                } ${isFinish ? "tile-finish" : ""} ${tileKindClass} ${isStageCandidate ? "tile-stage-candidate" : ""} ${
                  hasOwner ? "tile-owned" : ""
                } ${isPurchaseRevealFocus ? "tile-purchase-stamped" : ""}`}
                data-focus-kind={isStageFocus ? stageFocus.currentBeatKind : undefined}
                data-tile-kind={tile.tileKind}
                data-quarterview-lane={useQuarterview ? quarterviewPosition.lane : undefined}
                style={tileStyle}
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
                {!useQuarterview && isRevealFocus ? (
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
                {tile.scoreCoinCount > 0
                  ? renderScoreToken(tile.scoreCoinCount, "tile-score-token", board.scoreCoins(tile.scoreCoinCount))
                  : null}
                <div className="tile-content">
                  <div className="tile-zone-strip" style={{ backgroundColor: zoneColorToCss(tile.zoneColor ?? "", board) }} />
                  {hasOwner || useQuarterview ? (
                    <div
                      className={`tile-owner-stamp ${hasOwner ? "" : "tile-owner-stamp-empty"}`}
                      data-testid={hasOwner ? `tile-owner-stamp-${tile.tileIndex}` : undefined}
                      aria-label={hasOwner ? board.owner(ownerPlayerId) : undefined}
                      aria-hidden={hasOwner ? undefined : true}
                    >
                      <span>{hasOwner ? `P${ownerPlayerId}` : ""}</span>
                    </div>
                  ) : null}
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
                      {renderTilePrice(tile.purchaseCost, board, "tile-cost-pill")}
                    </div>
                  )}
                  <div className="tile-foot">
                    <div className="pawn-chips">
                      {tilePawns.filter((id) => !useQuarterview || !standeePlayerIds.has(id)).length > 0 ? (
                        tilePawns.filter((id) => !useQuarterview || !standeePlayerIds.has(id)).map((id) => (
                          <span
                            key={`${tile.tileIndex}-p${id}`}
                            className={`pawn-token ${isMoveTo ? "pawn-arrived" : ""} ${
                              isStageFocus && stageFocus.actorPlayerId === id ? "pawn-active-turn" : ""
                            } ${historyFocusPlayerIdSet.has(id) ? "pawn-history-focus" : ""}`}
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
                </div>
              </article>
            );
          })}
          {useQuarterview ? (
            <div className="board-character-layer" aria-hidden="true">
              {standeePlacements.map((placement, index) => {
                const tileMateOffsets =
                  placement.tileMateCount <= 1
                    ? { x: 0, y: 0 }
                    : [
                        { x: -18, y: 2 },
                        { x: 18, y: -2 },
                        { x: 0, y: -14 },
                        { x: 0, y: 14 },
                      ][placement.tileMateIndex % 4];
                const inwardOffset = standeeBoardInwardOffset(placement.position);
                const style = {
                  "--board-standee-x": `${placement.position.xPercent}%`,
                  "--board-standee-y": `${placement.position.yPercent}%`,
                  "--board-standee-z": String(placement.position.zIndex + 18 + index),
                  "--board-standee-color": playerColor(placement.playerId),
                  "--board-standee-offset-x": `${tileMateOffsets.x + inwardOffset.x}px`,
                  "--board-standee-offset-y": `${tileMateOffsets.y + inwardOffset.y}px`,
                  "--board-standee-walk-duration": placement.walkSprite
                    ? `${(placement.walkSprite.frameCount - 1) * placement.walkSprite.frameStepMs}ms`
                    : undefined,
                  "--board-standee-walk-delay": placement.walkSprite ? `${placement.walkFrameDelayMs}ms` : undefined,
                  "--character-sprite-scale": String(placement.spriteVisualScale),
                } as CSSProperties;
                return (
                  <div
                    key={`standee-${placement.animationKey}`}
                    className={`board-character-standee ${
                      placement.playerId === stageFocus.actorPlayerId ? "board-character-standee-active" : ""
                    } ${placement.isAnimating ? "board-character-standee-moving" : ""} ${
                      historyFocusPlayerIdSet.has(placement.playerId) ? "board-character-standee-history-focus" : ""
                    }`}
                    data-facing={placement.facing}
                    style={style}
                    title={`P${placement.playerId} ${placement.character}`}
                  >
                    {placement.walkSprite ? (
                      <span
                        className="board-character-standee-walk-viewport"
                        style={{ aspectRatio: `${placement.walkSprite.frameWidth} / ${placement.walkSprite.frameHeight}` }}
                      >
                        <img className="board-character-standee-walk-sheet" src={placement.walkSprite.url} alt="" draggable={false} />
                      </span>
                    ) : placement.assetUrl ? (
                      <img src={placement.assetUrl} alt="" draggable={false} />
                    ) : (
                      <span className="board-character-standee-fallback">P{placement.playerId}</span>
                    )}
                    <span className="board-character-standee-label">P{placement.playerId}</span>
                  </div>
                );
              })}
              {quarterviewMovingPawnStyle && animPlayerId !== null && !standeePlayerIds.has(animPlayerId) ? (
                <div className="board-character-standee board-character-standee-moving" style={quarterviewMovingPawnStyle}>
                  <span className="board-character-standee-fallback">P{animPlayerId}</span>
                </div>
              ) : null}
            </div>
          ) : null}
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
