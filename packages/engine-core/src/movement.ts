export type ForwardMoveInput = {
  fromTileIndex: number;
  steps: number;
  tileCount: number;
};

export type ForwardMoveResult = {
  fromTileIndex: number;
  toTileIndex: number;
  steps: number;
  tileCount: number;
  lapCount: number;
  pathTileIndices: number[];
};

function toNonNegativeInteger(value: number, fallback = 0): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }

  return Math.max(0, Math.trunc(value));
}

function toPositiveInteger(value: number, fallback = 1): number {
  const integer = toNonNegativeInteger(value, fallback);

  return integer > 0 ? integer : fallback;
}

export function normalizeTileIndex(tileIndex: number, tileCount: number): number {
  const count = toPositiveInteger(tileCount);
  const integerTileIndex = Number.isFinite(tileIndex) ? Math.trunc(tileIndex) : 0;

  return ((integerTileIndex % count) + count) % count;
}

export function applyForwardMove(input: ForwardMoveInput): ForwardMoveResult {
  const tileCount = toPositiveInteger(input.tileCount);
  const fromTileIndex = normalizeTileIndex(input.fromTileIndex, tileCount);
  const steps = toNonNegativeInteger(input.steps);
  const pathTileIndices = Array.from({ length: steps }, (_, index) =>
    normalizeTileIndex(fromTileIndex + index + 1, tileCount),
  );
  const toTileIndex =
    pathTileIndices.length > 0
      ? pathTileIndices[pathTileIndices.length - 1]
      : fromTileIndex;

  return {
    fromTileIndex,
    toTileIndex,
    steps,
    tileCount,
    lapCount: Math.floor((fromTileIndex + steps) / tileCount),
    pathTileIndices,
  };
}
