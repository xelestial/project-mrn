export type RingPosition = { row: number; col: number; boardSize: number };
export type BoardTopology = "ring" | "line";
export type BoardGrid = { cols: number; rows: number; boardSize: number; topology: BoardTopology };
export type QuarterviewLane = "top" | "right" | "bottom" | "left" | "line";
export type QuarterviewBoardLane = Exclude<QuarterviewLane, "line">;
export type QuarterviewFacing = "front-right" | "front-left" | "back-right" | "back-left";
export type QuarterviewPosition = RingPosition & {
  xPercent: number;
  yPercent: number;
  zIndex: number;
  lane: QuarterviewLane;
};
export type QuarterviewLaneCell = {
  tileIndex: number;
  lane: QuarterviewBoardLane;
  laneIndex: number;
  laneCount: number;
  xPercent: number;
  yPercent: number;
  zIndex: number;
  isLaneEnd: boolean;
  isCornerCandidate: boolean;
};
export type QuarterviewLaneModel = {
  lane: QuarterviewBoardLane;
  cells: QuarterviewLaneCell[];
  centerXPercent: number;
  centerYPercent: number;
  rotationDeg: number;
  lengthPercent: number;
  thicknessPercent: number;
};
export type QuarterviewBoardGeometry = {
  xSpreadPercent: number;
  ySpreadPercent: number;
  boardAspectRatio: number;
  tileAngleDeg: number;
  tileInlinePercent: number;
  tileBlockPercent: number;
};
export type QuarterviewPoint = {
  x: number;
  y: number;
};
export type QuarterviewTilePolygon = {
  tileIndex: number;
  lane: QuarterviewLane;
  points: [QuarterviewPoint, QuarterviewPoint, QuarterviewPoint, QuarterviewPoint];
  zonePoints: [QuarterviewPoint, QuarterviewPoint, QuarterviewPoint, QuarterviewPoint];
  contentTransform: {
    a: number;
    b: number;
    c: number;
    d: number;
    e: number;
    f: number;
  };
  centerX: number;
  centerY: number;
  bboxX: number;
  bboxY: number;
  bboxWidth: number;
  bboxHeight: number;
  contentRotationDeg: number;
  zIndex: number;
};

export const DEFAULT_RING_TILE_COUNT = 40;
export const DEFAULT_RING_GRID_SIZE = 11;
export const QUARTERVIEW_RING_X_SPREAD_PERCENT = 50;
export const QUARTERVIEW_RING_Y_SPREAD_PERCENT = 32;
export const QUARTERVIEW_BOARD_ASPECT_RATIO = 1.58;
export const QUARTERVIEW_TILE_JOIN_OVERLAP = 1;
export const QUARTERVIEW_TILE_THICKNESS_OVERLAP = 1.3;
const MIN_RING_GRID_SIZE = 5;
const MIN_RING_SIDE = 3;

export function boardSizeForTileCount(tileCount: number, topology: BoardTopology = "ring"): number {
  if (topology === "line") {
    return Math.max(1, tileCount);
  }
  if (tileCount <= 0) {
    return DEFAULT_RING_GRID_SIZE;
  }
  return Math.max(MIN_RING_GRID_SIZE, Math.ceil(tileCount / 4) + 1);
}

export function boardGridForTileCount(tileCount: number, topology: BoardTopology = "ring"): BoardGrid {
  if (topology === "line") {
    const cols = Math.max(1, tileCount);
    return { cols, rows: 1, boardSize: cols, topology };
  }
  const boardSize = boardSizeForTileCount(tileCount, topology);
  return { cols: boardSize, rows: boardSize, boardSize, topology };
}

export function ringPosition(tileIndex: number, boardSize: number): RingPosition {
  const side = Math.max(MIN_RING_SIDE, boardSize);
  const topCount = side;
  const rightCount = side - 2;
  const bottomCount = side;
  const totalCapacity = topCount + rightCount + bottomCount + rightCount;
  const normalized = ((tileIndex % totalCapacity) + totalCapacity) % totalCapacity;

  if (normalized < topCount) {
    return { row: 1, col: normalized + 1, boardSize: side };
  }
  const rightOffset = normalized - topCount;
  if (rightOffset < rightCount) {
    return { row: rightOffset + 2, col: side, boardSize: side };
  }
  const bottomOffset = rightOffset - rightCount;
  if (bottomOffset < bottomCount) {
    return { row: side, col: side - bottomOffset, boardSize: side };
  }
  const leftOffset = bottomOffset - bottomCount;
  return { row: side - leftOffset - 1, col: 1, boardSize: side };
}

export function linePosition(tileIndex: number, tileCount: number): RingPosition {
  const normalizedCount = Math.max(1, tileCount);
  const normalized = ((tileIndex % normalizedCount) + normalizedCount) % normalizedCount;
  return { row: 1, col: normalized + 1, boardSize: normalizedCount };
}

export function projectTilePosition(
  tileIndex: number,
  tileCount: number,
  topology: string | undefined
): RingPosition {
  const normalizedTopology: BoardTopology = topology === "line" ? "line" : "ring";
  if (normalizedTopology === "line") {
    return linePosition(tileIndex, tileCount);
  }
  const boardSize = boardSizeForTileCount(tileCount, normalizedTopology);
  return ringPosition(tileIndex, boardSize);
}

function laneForRingPosition(position: RingPosition): QuarterviewLane {
  if (position.row === 1) {
    return "top";
  }
  if (position.row === position.boardSize) {
    return "bottom";
  }
  if (position.col === position.boardSize) {
    return "right";
  }
  return "left";
}

export function quarterviewBoardGeometry(boardSize: number): QuarterviewBoardGeometry {
  const denom = Math.max(1, boardSize - 1);
  const xStep = QUARTERVIEW_RING_X_SPREAD_PERCENT / denom;
  const yStep = QUARTERVIEW_RING_Y_SPREAD_PERCENT / denom;
  const visualXStep = xStep * QUARTERVIEW_BOARD_ASPECT_RATIO;
  const visualYStep = yStep;
  const laneStepPercent = Math.hypot(xStep, yStep / QUARTERVIEW_BOARD_ASPECT_RATIO);
  return {
    xSpreadPercent: QUARTERVIEW_RING_X_SPREAD_PERCENT,
    ySpreadPercent: QUARTERVIEW_RING_Y_SPREAD_PERCENT,
    boardAspectRatio: QUARTERVIEW_BOARD_ASPECT_RATIO,
    tileAngleDeg: Math.atan2(visualYStep, visualXStep) * (180 / Math.PI),
    tileInlinePercent: laneStepPercent * QUARTERVIEW_TILE_JOIN_OVERLAP,
    tileBlockPercent: yStep * 2 * QUARTERVIEW_TILE_THICKNESS_OVERLAP,
  };
}

export function projectTileQuarterview(
  tileIndex: number,
  tileCount: number,
  topology: string | undefined
): QuarterviewPosition {
  const normalizedTopology: BoardTopology = topology === "line" ? "line" : "ring";

  if (normalizedTopology === "line") {
    const position = projectTilePosition(tileIndex, tileCount, normalizedTopology);
    const normalizedCount = Math.max(1, tileCount);
    const xPercent = normalizedCount === 1 ? 50 : 6 + (position.col - 1) * (88 / (normalizedCount - 1));
    return {
      ...position,
      xPercent,
      yPercent: 50,
      zIndex: 1000 + position.col,
      lane: "line",
    };
  }

  const boardSize = boardSizeForTileCount(tileCount, normalizedTopology);
  const side = Math.max(MIN_RING_SIDE, boardSize);
  const position = ringPosition(tileIndex, side);
  const denom = Math.max(1, position.boardSize - 1);
  const diagonal = (position.col - position.row) / denom;
  const depth = (position.row + position.col - (position.boardSize + 1)) / denom;
  const geometry = quarterviewBoardGeometry(position.boardSize);

  return {
    ...position,
    xPercent: 50 + diagonal * geometry.xSpreadPercent,
    yPercent: 50 + depth * geometry.ySpreadPercent,
    zIndex: 1000 + position.row * 20 + position.col,
    lane: laneForRingPosition(position),
  };
}

const QUARTERVIEW_LANE_ORDER: QuarterviewBoardLane[] = ["top", "right", "bottom", "left"];

type IndexedQuarterviewPosition = QuarterviewPosition & { tileIndex: number; lane: QuarterviewBoardLane };

function compareQuarterviewLaneCells(a: IndexedQuarterviewPosition, b: IndexedQuarterviewPosition): number {
  if (a.lane === "top") {
    return a.xPercent - b.xPercent;
  }
  if (a.lane === "right") {
    return a.yPercent - b.yPercent;
  }
  if (a.lane === "bottom") {
    return b.xPercent - a.xPercent;
  }
  return b.yPercent - a.yPercent;
}

export function quarterviewLaneModels(
  tileCount: number,
  topology: string | undefined
): QuarterviewLaneModel[] {
  const normalizedTopology: BoardTopology = topology === "line" ? "line" : "ring";
  if (normalizedTopology === "line") {
    return [];
  }

  const boardSize = boardSizeForTileCount(tileCount, normalizedTopology);
  const geometry = quarterviewBoardGeometry(boardSize);
  const grouped = new Map<QuarterviewBoardLane, IndexedQuarterviewPosition[]>(
    QUARTERVIEW_LANE_ORDER.map((lane) => [lane, []])
  );

  for (let tileIndex = 0; tileIndex < tileCount; tileIndex += 1) {
    const position = projectTileQuarterview(tileIndex, tileCount, normalizedTopology);
    if (position.lane === "line") {
      continue;
    }
    grouped.get(position.lane)?.push({ ...position, tileIndex, lane: position.lane });
  }

  return QUARTERVIEW_LANE_ORDER.map((lane) => {
    const positions = [...(grouped.get(lane) ?? [])].sort(compareQuarterviewLaneCells);
    const laneCount = positions.length;
    const cells = positions.map((position, laneIndex) => ({
      tileIndex: ((position as QuarterviewPosition & { tileIndex?: number }).tileIndex ?? 0),
      lane,
      laneIndex,
      laneCount,
      xPercent: position.xPercent,
      yPercent: position.yPercent,
      zIndex: position.zIndex,
      isLaneEnd: laneIndex === 0 || laneIndex === laneCount - 1,
      isCornerCandidate: laneIndex === 0 || laneIndex === laneCount - 1,
    }));

    const angle = geometry.tileAngleDeg;
    const sideCenters: Record<QuarterviewBoardLane, { x: number; y: number; rotation: number }> = {
      top: { x: 50 + geometry.xSpreadPercent / 2, y: 50 - geometry.ySpreadPercent / 2, rotation: angle },
      right: { x: 50 + geometry.xSpreadPercent / 2, y: 50 + geometry.ySpreadPercent / 2, rotation: -angle },
      bottom: { x: 50 - geometry.xSpreadPercent / 2, y: 50 + geometry.ySpreadPercent / 2, rotation: angle },
      left: { x: 50 - geometry.xSpreadPercent / 2, y: 50 - geometry.ySpreadPercent / 2, rotation: -angle },
    };
    const center = sideCenters[lane];

    return {
      lane,
      cells,
      centerXPercent: center.x,
      centerYPercent: center.y,
      rotationDeg: center.rotation,
      lengthPercent: geometry.tileInlinePercent * Math.max(1, laneCount),
      thicknessPercent: geometry.tileBlockPercent,
    };
  }).filter((lane) => lane.cells.length > 0);
}

function projectQuarterviewGridPoint(
  x: number,
  y: number,
  boardSize: number,
  geometry: Pick<QuarterviewBoardGeometry, "xSpreadPercent" | "ySpreadPercent">
): QuarterviewPoint {
  const side = Math.max(1, boardSize);
  return {
    x: (50 + ((x - y) / side) * geometry.xSpreadPercent) * 10,
    y: (50 + (((x + y) - side) / side) * geometry.ySpreadPercent) * 10,
  };
}

function interpolatePoint(a: QuarterviewPoint, b: QuarterviewPoint, ratio: number): QuarterviewPoint {
  return {
    x: a.x + (b.x - a.x) * ratio,
    y: a.y + (b.y - a.y) * ratio,
  };
}

function polygonCenter(points: readonly QuarterviewPoint[]): QuarterviewPoint {
  return {
    x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
    y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
  };
}

function contentTransformForTile(
  points: [QuarterviewPoint, QuarterviewPoint, QuarterviewPoint, QuarterviewPoint],
  lane: QuarterviewLane
): QuarterviewTilePolygon["contentTransform"] {
  const [p0, p1, p2, p3] = points;
  const origin = lane === "left" || lane === "right" ? p3 : p0;
  const inlineEnd = lane === "left" || lane === "right" ? p0 : p1;
  const blockEnd = lane === "left" || lane === "right" ? p2 : p3;
  const inline = { x: inlineEnd.x - origin.x, y: inlineEnd.y - origin.y };
  const block = { x: blockEnd.x - origin.x, y: blockEnd.y - origin.y };
  const insetRatio = 0.035;
  const scaleRatio = 1 - insetRatio * 2;
  const adjustedOrigin = {
    x: origin.x + inline.x * insetRatio + block.x * insetRatio,
    y: origin.y + inline.y * insetRatio + block.y * insetRatio,
  };

  return {
    a: (inline.x * scaleRatio) / 100,
    b: (inline.y * scaleRatio) / 100,
    c: (block.x * scaleRatio) / 100,
    d: (block.y * scaleRatio) / 100,
    e: adjustedOrigin.x,
    f: adjustedOrigin.y,
  };
}

export function quarterviewTilePolygons(
  tileCount: number,
  topology: string | undefined
): QuarterviewTilePolygon[] {
  const normalizedTopology: BoardTopology = topology === "line" ? "line" : "ring";
  if (normalizedTopology === "line") {
    return [];
  }

  const boardSize = boardSizeForTileCount(tileCount, normalizedTopology);
  const side = Math.max(MIN_RING_SIDE, boardSize);
  const geometry = quarterviewBoardGeometry(side);
  const textAngle = geometry.tileAngleDeg;

  return Array.from({ length: tileCount }, (_, tileIndex) => {
    const position = ringPosition(tileIndex, side);
    const lane = laneForRingPosition(position);
    const left = position.col - 1;
    const right = position.col;
    const top = position.row - 1;
    const bottom = position.row;
    const points: [QuarterviewPoint, QuarterviewPoint, QuarterviewPoint, QuarterviewPoint] = [
      projectQuarterviewGridPoint(left, top, side, geometry),
      projectQuarterviewGridPoint(right, top, side, geometry),
      projectQuarterviewGridPoint(right, bottom, side, geometry),
      projectQuarterviewGridPoint(left, bottom, side, geometry),
    ];
    const zoneDepth = 0.36;
    const zonePoints: [QuarterviewPoint, QuarterviewPoint, QuarterviewPoint, QuarterviewPoint] = [
      points[0],
      points[1],
      interpolatePoint(points[1], points[2], zoneDepth),
      interpolatePoint(points[0], points[3], zoneDepth),
    ];
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const center = polygonCenter(points);
    const contentRotationDeg = lane === "top" || lane === "bottom" ? textAngle : -textAngle;

    return {
      tileIndex,
      lane,
      points,
      zonePoints,
      contentTransform: contentTransformForTile(points, lane),
      centerX: center.x,
      centerY: center.y,
      bboxX: Math.min(...xs),
      bboxY: Math.min(...ys),
      bboxWidth: Math.max(...xs) - Math.min(...xs),
      bboxHeight: Math.max(...ys) - Math.min(...ys),
      contentRotationDeg,
      zIndex: 1000 + position.row * 20 + position.col,
    };
  });
}

export function quarterviewFacingForLane(lane: QuarterviewLane): QuarterviewFacing {
  switch (lane) {
    case "right":
      return "front-right";
    case "bottom":
      return "front-left";
    case "left":
      return "back-left";
    case "top":
    case "line":
    default:
      return "back-right";
  }
}

export function quarterviewIdleFacingForPosition(
  position: Pick<QuarterviewPosition, "xPercent" | "lane">
): QuarterviewFacing {
  switch (position.lane) {
    case "top":
      return position.xPercent < 50 ? "back-left" : "back-right";
    case "bottom":
      return position.xPercent < 50 ? "front-right" : "front-left";
    default:
      return quarterviewFacingForLane(position.lane);
  }
}

export function quarterviewFacingFromPositions(
  from: Pick<QuarterviewPosition, "xPercent" | "yPercent" | "lane">,
  to: Pick<QuarterviewPosition, "xPercent" | "yPercent" | "lane">
): QuarterviewFacing {
  const dx = to.xPercent - from.xPercent;
  const dy = to.yPercent - from.yPercent;
  if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) {
    return quarterviewFacingForLane(to.lane);
  }
  if (dy >= 0) {
    return dx >= 0 ? "front-right" : "front-left";
  }
  return dx >= 0 ? "back-right" : "back-left";
}

export function quarterviewFacingForTileStep(
  fromTileIndex: number | null,
  toTileIndex: number,
  tileCount: number,
  topology: string | undefined
): QuarterviewFacing {
  const to = projectTileQuarterview(toTileIndex, tileCount, topology);
  if (fromTileIndex === null) {
    return quarterviewFacingForLane(to.lane);
  }
  const from = projectTileQuarterview(fromTileIndex, tileCount, topology);
  return quarterviewFacingFromPositions(from, to);
}

export function quarterviewIdleFacingForTile(
  tileIndex: number,
  tileCount: number,
  topology: string | undefined
): QuarterviewFacing {
  const normalizedTopology: BoardTopology = topology === "line" ? "line" : "ring";
  const current = projectTileQuarterview(tileIndex, tileCount, normalizedTopology);
  if (normalizedTopology === "line") {
    return quarterviewIdleFacingForPosition(current);
  }
  const safeTileCount = Math.max(1, Math.trunc(tileCount));
  const nextTileIndex = ((tileIndex + 1) % safeTileCount + safeTileCount) % safeTileCount;
  const next = projectTileQuarterview(nextTileIndex, safeTileCount, normalizedTopology);
  return quarterviewFacingFromPositions(current, next);
}
