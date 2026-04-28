import { useEffect, useRef, useState } from "react";

export type StepPathAnimationPhase = "idle" | "moving" | "arrived";

export type StepPathAnimationState<TId, TStep> = {
  animId: TId | null;
  animStep: TStep | null;
  animPreviousStep: TStep | null;
  animStepIndex: number;
  animPhase: StepPathAnimationPhase;
};

export type StepPathAnimationInput<TId, TStep> = {
  id: TId;
  fromStep: TStep;
  toStep: TStep;
  pathSteps: TStep[];
  key: string;
} | null;

export type StepPathAnimationOptions = {
  stepMs?: number;
  arrivedLingerMs?: number;
  startDelayMs?: number;
};

export function useStepPathAnimation<TId, TStep>(
  input: StepPathAnimationInput<TId, TStep>,
  options: StepPathAnimationOptions = {}
): StepPathAnimationState<TId, TStep> {
  const stepMs = options.stepMs ?? 260;
  const arrivedLingerMs = options.arrivedLingerMs ?? 1200;
  const startDelayMs = options.startDelayMs ?? 0;
  const idleState: StepPathAnimationState<TId, TStep> = {
    animId: null,
    animStep: null,
    animPreviousStep: null,
    animStepIndex: -1,
    animPhase: "idle",
  };
  const [state, setState] = useState<StepPathAnimationState<TId, TStep>>(idleState);
  const seenKeyRef = useRef<string | null>(null);
  const inputRef = useRef(input);
  inputRef.current = input;

  useEffect(() => {
    if (!input) {
      seenKeyRef.current = null;
      setState(idleState);
      return;
    }
    if (seenKeyRef.current === input.key) {
      return;
    }
    seenKeyRef.current = input.key;

    const current = inputRef.current;
    if (!current || current.pathSteps.length === 0) {
      return;
    }

    let stepIndex = 0;
    let arrivedTimer: number | null = null;
    let startTimer: number | null = null;
    let interval: number | null = null;

    const beginPath = () => {
      setState({
        animId: current.id,
        animStep: current.pathSteps[0],
        animPreviousStep: current.fromStep,
        animStepIndex: 0,
        animPhase: "moving",
      });
      interval = window.setInterval(() => {
      stepIndex += 1;
      const active = inputRef.current;
      if (!active) {
        if (interval !== null) {
          window.clearInterval(interval);
        }
        setState(idleState);
        return;
      }

      if (stepIndex >= active.pathSteps.length) {
        if (interval !== null) {
          window.clearInterval(interval);
        }
        setState({
          animId: active.id,
          animStep: active.toStep,
          animPreviousStep: active.pathSteps[active.pathSteps.length - 1] ?? active.fromStep,
          animStepIndex: stepIndex,
          animPhase: "arrived",
        });
        arrivedTimer = window.setTimeout(() => {
          setState(idleState);
        }, arrivedLingerMs);
        return;
      }

      setState({
        animId: active.id,
        animStep: active.pathSteps[stepIndex],
        animPreviousStep: active.pathSteps[stepIndex - 1] ?? active.fromStep,
        animStepIndex: stepIndex,
        animPhase: "moving",
      });
      }, stepMs);
    };

    if (startDelayMs > 0) {
      setState({
        animId: current.id,
        animStep: current.fromStep,
        animPreviousStep: null,
        animStepIndex: -1,
        animPhase: "moving",
      });
      startTimer = window.setTimeout(beginPath, startDelayMs);
    } else {
      beginPath();
    }

    return () => {
      if (startTimer !== null) {
        window.clearTimeout(startTimer);
      }
      if (interval !== null) {
        window.clearInterval(interval);
      }
      if (arrivedTimer !== null) {
        window.clearTimeout(arrivedTimer);
      }
    };
  }, [input?.key, stepMs, arrivedLingerMs, startDelayMs]);

  return state;
}
