export type RingPosition = { row: number; col: number; boardSize: number };
export type BoardTopology = "ring" | "line";
export type BoardGrid = { cols: number; rows: number; boardSize: number; topology: BoardTopology };

export const DEFAULT_RING_TILE_COUNT = 40;
export const DEFAULT_RING_GRID_SIZE = 11;
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
