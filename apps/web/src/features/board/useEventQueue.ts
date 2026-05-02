import { useCallback, useEffect, useRef, useState } from "react";

export type GameEventKind =
  | "weather"
  | "dice"
  | "move"
  | "purchase"
  | "rent_pay"
  | "rent_receive"
  | "rent_observe"
  | "fortune"
  | "lap_complete"
  | "bankruptcy"
  | "game_end"
  | "trick"
  | "mark_success"
  | "economy";

export type GameEventEffectIntent = "neutral" | "boost" | "gain" | "loss" | "mystic";
export type GameEventEffectSource = "weather" | "fortune" | "trick" | "character" | "economy" | "mark" | "system";
export type GameEventEffectCharacter = "박수" | "만신" | "중매꾼" | "baksu" | "manshin" | "matchmaker" | string;

export type GameEvent = {
  kind: GameEventKind;
  label: string;
  detail: string;
  seq: number;
  diceValues?: number[];
  diceTotal?: number | null;
  effectIntent?: GameEventEffectIntent;
  effectSource?: GameEventEffectSource;
  effectEnhanced?: boolean;
  effectCharacter?: GameEventEffectCharacter;
};

const DISPLAY_DURATION_MS: Record<GameEventKind, number> = {
  weather: 3000,
  dice: 2800,
  move: 3600,
  purchase: 3400,
  rent_pay: 3000,
  rent_receive: 2500,
  rent_observe: 2600,
  fortune: 3000,
  lap_complete: 3000,
  bankruptcy: 3500,
  game_end: 4500,
  trick: 3000,
  mark_success: 3400,
  economy: 2600,
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
