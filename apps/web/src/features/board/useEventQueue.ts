import { useCallback, useEffect, useRef, useState } from "react";

export type GameEventKind =
  | "rent_pay"
  | "rent_receive"
  | "rent_observe"
  | "lap_complete"
  | "bankruptcy"
  | "economy";

export type GameEvent = {
  kind: GameEventKind;
  label: string;
  detail: string;
  seq: number;
};

const DISPLAY_DURATION_MS: Record<GameEventKind, number> = {
  rent_pay: 3000,
  rent_receive: 2500,
  rent_observe: 2000,
  lap_complete: 2500,
  bankruptcy: 3500,
  economy: 2000,
};

export type EventQueueApi = {
  currentEvent: GameEvent | null;
  enqueue: (event: Omit<GameEvent, "seq">) => void;
};

export function useEventQueue(): EventQueueApi {
  const [currentEvent, setCurrentEvent] = useState<GameEvent | null>(null);
  const queueRef = useRef<GameEvent[]>([]);
  const timerRef = useRef<number | null>(null);
  const busyRef = useRef(false);
  const seqRef = useRef(0);

  const advance = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const next = queueRef.current.shift() ?? null;
    busyRef.current = next !== null;
    setCurrentEvent(next);
    if (next) {
      timerRef.current = window.setTimeout(advance, DISPLAY_DURATION_MS[next.kind]);
    }
  }, []);

  const enqueue = useCallback(
    (event: Omit<GameEvent, "seq">) => {
      seqRef.current += 1;
      const entry: GameEvent = { ...event, seq: seqRef.current };
      if (!busyRef.current) {
        busyRef.current = true;
        setCurrentEvent(entry);
        if (timerRef.current !== null) window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(advance, DISPLAY_DURATION_MS[entry.kind]);
      } else {
        queueRef.current.push(entry);
      }
    },
    [advance]
  );

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  return { currentEvent, enqueue };
}
