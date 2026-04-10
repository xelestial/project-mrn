import type { GameEvent, GameEventKind } from "./useEventQueue";

type GameEventOverlayProps = {
  currentEvent: GameEvent | null;
};

function eventIcon(kind: GameEventKind): string {
  switch (kind) {
    case "rent_pay":
      return "💸";
    case "rent_receive":
      return "💰";
    case "rent_observe":
      return "👀";
    case "lap_complete":
      return "🎉";
    case "bankruptcy":
      return "💀";
    case "economy":
      return "💼";
  }
}

function eventCssClass(kind: GameEventKind): string {
  switch (kind) {
    case "rent_pay":
      return "event-rent-pay";
    case "rent_receive":
      return "event-rent-receive";
    case "rent_observe":
      return "event-rent-observe";
    case "lap_complete":
      return "event-lap-complete";
    case "bankruptcy":
      return "event-bankruptcy";
    case "economy":
      return "event-economy";
  }
}

export function GameEventOverlay({ currentEvent }: GameEventOverlayProps) {
  if (!currentEvent) return null;

  return (
    // key forces remount (and CSS animation restart) for each new event
    <div
      key={currentEvent.seq}
      className={`game-event-overlay ${eventCssClass(currentEvent.kind)}`}
      role="status"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div className="game-event-overlay-icon">{eventIcon(currentEvent.kind)}</div>
      <div className="game-event-overlay-headline">{currentEvent.label}</div>
      {currentEvent.detail && currentEvent.detail !== "-" ? (
        <div className="game-event-overlay-detail">{currentEvent.detail}</div>
      ) : null}
    </div>
  );
}
