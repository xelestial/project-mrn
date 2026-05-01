import type { GameEvent, GameEventKind } from "./useEventQueue";

type GameEventOverlayProps = {
  currentEvent: GameEvent | null;
};

function eventIcon(kind: GameEventKind): string {
  switch (kind) {
    case "weather":
      return "☁";
    case "dice":
      return "";
    case "move":
      return "이동";
    case "purchase":
      return "땅";
    case "rent_pay":
      return "💸";
    case "rent_receive":
      return "💰";
    case "rent_observe":
      return "👀";
    case "fortune":
      return "✦";
    case "lap_complete":
      return "🎉";
    case "bankruptcy":
      return "💀";
    case "game_end":
      return "끝";
    case "trick":
      return "꾀";
    case "mark_success":
      return "지목";
    case "economy":
      return "💼";
  }
}

function eventThemeLabel(kind: GameEventKind): string {
  switch (kind) {
    case "weather":
      return "날씨 카드";
    case "dice":
      return "주사위";
    case "move":
      return "이동";
    case "fortune":
      return "운수 카드";
    case "trick":
      return "잔꾀 카드";
    case "purchase":
      return "땅 사기";
    case "rent_pay":
    case "rent_receive":
    case "rent_observe":
      return "렌트";
    case "lap_complete":
      return "랩 보상";
    case "bankruptcy":
      return "파산";
    case "game_end":
      return "게임 종료";
    case "mark_success":
      return "지목";
    case "economy":
      return "경제";
  }
}

function eventCssClass(kind: GameEventKind): string {
  switch (kind) {
    case "weather":
      return "event-weather";
    case "dice":
      return "event-dice";
    case "move":
      return "event-move";
    case "purchase":
      return "event-purchase";
    case "rent_pay":
      return "event-rent-pay";
    case "rent_receive":
      return "event-rent-receive";
    case "rent_observe":
      return "event-rent-observe";
    case "fortune":
      return "event-fortune";
    case "lap_complete":
      return "event-lap-complete";
    case "bankruptcy":
      return "event-bankruptcy";
    case "game_end":
      return "event-game-end";
    case "trick":
      return "event-trick";
    case "mark_success":
      return "event-mark-success";
    case "economy":
      return "event-economy";
  }
}

function diePips(value: number): Array<[number, number]> {
  switch (value) {
    case 1:
      return [[50, 50]];
    case 2:
      return [[32, 32], [68, 68]];
    case 3:
      return [[30, 30], [50, 50], [70, 70]];
    case 4:
      return [[31, 31], [69, 31], [31, 69], [69, 69]];
    case 5:
      return [[30, 30], [70, 30], [50, 50], [30, 70], [70, 70]];
    case 6:
      return [[30, 28], [70, 28], [30, 50], [70, 50], [30, 72], [70, 72]];
    default:
      return [];
  }
}

function DiceFace({ value }: { value: number }) {
  const pips = diePips(value);
  return (
    <svg className="game-event-die" viewBox="0 0 100 100" role="img" aria-label={`dice ${value}`}>
      <rect x="8" y="8" width="84" height="84" rx="18" />
      {pips.length > 0 ? (
        pips.map(([cx, cy], index) => <circle key={`${cx}-${cy}-${index}`} cx={cx} cy={cy} r="7.8" />)
      ) : (
        <text x="50" y="58" textAnchor="middle">
          {value}
        </text>
      )}
    </svg>
  );
}

export function GameEventOverlay({ currentEvent }: GameEventOverlayProps) {
  if (!currentEvent) return null;
  const diceValues = currentEvent.diceValues?.length
    ? currentEvent.diceValues
    : typeof currentEvent.diceTotal === "number"
      ? [currentEvent.diceTotal]
      : [];
  const detailParts = currentEvent.detail
    .split("/")
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && part !== "-")
    .filter((part, index) => index !== 0 || part.toLowerCase() !== currentEvent.label.trim().toLowerCase());
  const shouldPromoteDetailLead =
    currentEvent.kind === "rent_pay" ||
    currentEvent.kind === "rent_receive" ||
    currentEvent.kind === "rent_observe" ||
    currentEvent.kind === "trick" ||
    currentEvent.kind === "fortune";
  const promotedDetail = shouldPromoteDetailLead && detailParts.length > 1;
  const primaryDetail = promotedDetail ? detailParts.slice(0, -1).join(" / ") : detailParts[0] ?? "";
  const secondaryDetail = promotedDetail ? detailParts[detailParts.length - 1] : detailParts.slice(1).join(" / ");

  return (
    // key forces remount (and CSS animation restart) for each new event
    <div
      key={currentEvent.seq}
      className={`game-event-overlay ${eventCssClass(currentEvent.kind)}`}
      data-event-kind={currentEvent.kind}
      role="status"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div className="game-event-overlay-sprite" aria-hidden="true" />
      <div className="game-event-overlay-card">
        <div className="game-event-overlay-ribbon">{eventThemeLabel(currentEvent.kind)}</div>
        {currentEvent.kind === "dice" && diceValues.length > 0 ? (
          <div className="game-event-dice-row">
            {diceValues.map((value, index) => (
              <DiceFace key={`${value}-${index}`} value={value} />
            ))}
          </div>
        ) : (
          <div className="game-event-overlay-icon">{eventIcon(currentEvent.kind)}</div>
        )}
        <div className="game-event-overlay-headline">{currentEvent.label}</div>
      </div>
      {primaryDetail ? (
        <div className="game-event-overlay-detail-card">
          <strong>{primaryDetail}</strong>
          {secondaryDetail ? <small>{secondaryDetail}</small> : null}
        </div>
      ) : null}
    </div>
  );
}
