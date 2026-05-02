import type { LastMoveViewModel } from "../../domain/selectors/streamSelectors";
import { useStepPathAnimation } from "./useStepPathAnimation";

export type PawnAnimPhase = "idle" | "moving" | "arrived";

export type PawnAnimState = {
  animPlayerId: number | null;
  animTileIndex: number | null;
  animPreviousTileIndex: number | null;
  animStepIndex: number;
  animPhase: PawnAnimPhase;
};

const IDLE: PawnAnimState = {
  animPlayerId: null,
  animTileIndex: null,
  animPreviousTileIndex: null,
  animStepIndex: -1,
  animPhase: "idle",
};

const STEP_MS = 420;
const ARRIVED_LINGER_MS = 1800;

function buildFallbackPath(fromTileIndex: number | null, toTileIndex: number | null, tileCount: number): number[] {
  if (fromTileIndex === null || toTileIndex === null || fromTileIndex === toTileIndex || tileCount <= 0) {
    return [];
  }
  const normalizedCount = Math.max(1, tileCount);
  const normalizedTo = ((toTileIndex % normalizedCount) + normalizedCount) % normalizedCount;
  const steps: number[] = [];
  let cursor = ((fromTileIndex % normalizedCount) + normalizedCount) % normalizedCount;
  for (let guard = 0; guard < normalizedCount; guard += 1) {
    cursor = (cursor + 1) % normalizedCount;
    steps.push(cursor);
    if (cursor === normalizedTo) {
      return steps;
    }
  }
  return [normalizedTo];
}

export function usePawnAnimation(lastMove: LastMoveViewModel | null, tileCount = 0, startDelayMs = 0): PawnAnimState {
  const pathSteps =
    lastMove?.pathTileIndices && lastMove.pathTileIndices.length > 0
      ? lastMove.pathTileIndices
      : buildFallbackPath(lastMove?.fromTileIndex ?? null, lastMove?.toTileIndex ?? null, tileCount);
  const animation = useStepPathAnimation(
    lastMove && pathSteps.length > 0
      ? {
          id: lastMove.playerId,
          fromStep: lastMove.fromTileIndex,
          toStep: lastMove.toTileIndex,
          pathSteps,
          key: `${lastMove.playerId}-${lastMove.fromTileIndex}-${lastMove.toTileIndex}-${pathSteps.join(",")}`,
        }
      : null,
    { stepMs: STEP_MS, arrivedLingerMs: ARRIVED_LINGER_MS, startDelayMs }
  );

  if (animation.animId === null || animation.animStep === null) {
    return IDLE;
  }
  return {
    animPlayerId: animation.animId,
    animTileIndex: animation.animStep,
    animPreviousTileIndex: animation.animPreviousStep,
    animStepIndex: animation.animStepIndex,
    animPhase: animation.animPhase,
  };
}
