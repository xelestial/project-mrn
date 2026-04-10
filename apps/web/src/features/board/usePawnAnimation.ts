import { useEffect, useRef, useState } from "react";
import type { LastMoveViewModel } from "../../domain/selectors/streamSelectors";

export type PawnAnimPhase = "idle" | "moving" | "arrived";

export type PawnAnimState = {
  animPlayerId: number | null;
  animTileIndex: number | null;
  animPhase: PawnAnimPhase;
};

const IDLE: PawnAnimState = {
  animPlayerId: null,
  animTileIndex: null,
  animPhase: "idle",
};

const STEP_MS = 260;
const ARRIVED_LINGER_MS = 1200;

export function usePawnAnimation(lastMove: LastMoveViewModel | null): PawnAnimState {
  const [state, setState] = useState<PawnAnimState>(IDLE);
  const seenKeyRef = useRef<string | null>(null);
  // Keep a stable ref to the current lastMove to avoid stale closure issues
  const lastMoveRef = useRef<LastMoveViewModel | null>(null);
  lastMoveRef.current = lastMove;

  const moveKey = lastMove
    ? `${lastMove.playerId}-${lastMove.fromTileIndex}-${lastMove.toTileIndex}`
    : null;

  useEffect(() => {
    if (!moveKey || !lastMoveRef.current) {
      seenKeyRef.current = null;
      return;
    }

    // Already processed this exact move
    if (seenKeyRef.current === moveKey) return;
    seenKeyRef.current = moveKey;

    const lm = lastMoveRef.current;
    const steps = lm.pathTileIndices;

    // No path data — skip step animation (fallback arc will show)
    if (!steps || steps.length === 0) return;

    let stepIndex = 0;
    let arrivedTimer: number | null = null;

    setState({
      animPlayerId: lm.playerId,
      animTileIndex: steps[0],
      animPhase: "moving",
    });

    const interval = setInterval(() => {
      stepIndex++;

      if (stepIndex >= steps.length) {
        clearInterval(interval);
        setState({
          animPlayerId: lm.playerId,
          animTileIndex: lm.toTileIndex,
          animPhase: "arrived",
        });
        arrivedTimer = window.setTimeout(() => {
          setState(IDLE);
        }, ARRIVED_LINGER_MS);
        return;
      }

      setState((prev) => ({ ...prev, animTileIndex: steps[stepIndex] }));
    }, STEP_MS);

    return () => {
      clearInterval(interval);
      if (arrivedTimer !== null) window.clearTimeout(arrivedTimer);
    };
  }, [moveKey]); // stable key-based dep

  return state;
}
