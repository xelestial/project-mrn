import type { GameEvent, GameEventEffectIntent, GameEventEffectSource, GameEventKind } from "./useEventQueue";

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

function eventEffectSource(event: GameEvent): GameEventEffectSource {
  if (event.effectSource) return event.effectSource;
  switch (event.kind) {
    case "weather":
      return "weather";
    case "fortune":
      return "fortune";
    case "trick":
      return "trick";
    case "mark_success":
      return "mark";
    case "purchase":
    case "rent_pay":
    case "rent_receive":
    case "rent_observe":
    case "lap_complete":
    case "bankruptcy":
    case "economy":
      return "economy";
    case "dice":
    case "move":
    case "game_end":
      return "system";
  }
}

function eventEffectIntent(event: GameEvent): GameEventEffectIntent {
  if (event.effectIntent) return event.effectIntent;
  const text = `${event.label} ${event.detail}`.toLowerCase();
  if (/벌금|지불|냈|차감|손실|파산|pay|paid|penalty|fine|lose|lost|bankrupt/.test(text)) {
    return "loss";
  }
  if (/보상|획득|얻|받|수입|현금 \+|조각 \+|승점 \+|reward|gain|receive|received|cash \+|shard \+|coin \+/.test(text)) {
    return "gain";
  }
  if (/강화|증가|상승|배|날씨|통행료|렌트|boost|increase|double|weather|rent/.test(text)) {
    return "boost";
  }
  switch (event.kind) {
    case "rent_pay":
    case "bankruptcy":
      return "loss";
    case "rent_receive":
    case "lap_complete":
      return "gain";
    case "fortune":
    case "trick":
    case "mark_success":
      return "mystic";
    default:
      return "neutral";
  }
}

function eventEffectBadgeLabel(
  source: GameEventEffectSource,
  intent: GameEventEffectIntent,
  enhanced: boolean
): string | null {
  if (source === "weather") {
    if (intent === "loss") return "날씨 페널티";
    if (intent === "gain") return "날씨 보상";
    return enhanced || intent === "boost" ? "날씨 강화" : "날씨 효과";
  }
  if (source === "fortune") {
    if (intent === "loss") return "운수 손실";
    if (intent === "gain") return "운수 보상";
    if (intent === "boost") return "운수 강화";
    return "운수 효과";
  }
  if (source === "trick") {
    if (intent === "loss") return "잔꾀 손실";
    if (intent === "gain") return "잔꾀 보상";
    return "잔꾀 효과";
  }
  if (source === "character") {
    if (intent === "loss") return "캐릭터 페널티";
    return "캐릭터 보너스";
  }
  if (source === "mark") {
    return "지목 효과";
  }
  if (source === "economy" && enhanced) {
    if (intent === "loss") return "지출";
    if (intent === "gain") return "수입";
    if (intent === "boost") return "경제 강화";
  }
  return null;
}

function EventEffectParticles({
  intent,
  source,
  enhanced,
}: {
  intent: GameEventEffectIntent;
  source: GameEventEffectSource;
  enhanced: boolean;
}) {
  const showLightning = source === "weather" && (enhanced || intent === "boost" || intent === "loss");
  const showGain = intent === "gain";
  const showLoss = intent === "loss";
  const showMystic = source === "fortune" || source === "trick" || source === "character" || intent === "mystic";

  return (
    <div className="game-event-overlay-effects" aria-hidden="true">
      {showLightning ? (
        <>
          <span className="game-event-effect-bolt game-event-effect-bolt-1" />
          <span className="game-event-effect-bolt game-event-effect-bolt-2" />
          <span className="game-event-effect-flash" />
        </>
      ) : null}
      {showGain ? (
        <>
          <span className="game-event-effect-coin game-event-effect-coin-1" />
          <span className="game-event-effect-coin game-event-effect-coin-2" />
          <span className="game-event-effect-coin game-event-effect-coin-3" />
          <span className="game-event-effect-glint game-event-effect-glint-1" />
          <span className="game-event-effect-glint game-event-effect-glint-2" />
        </>
      ) : null}
      {showLoss ? (
        <>
          <span className="game-event-effect-shock" />
          <span className="game-event-effect-debit game-event-effect-debit-1" />
          <span className="game-event-effect-debit game-event-effect-debit-2" />
          <span className="game-event-effect-debit game-event-effect-debit-3" />
        </>
      ) : null}
      {showMystic ? (
        <>
          <span className="game-event-effect-wisp game-event-effect-wisp-1" />
          <span className="game-event-effect-wisp game-event-effect-wisp-2" />
          <span className="game-event-effect-rune game-event-effect-rune-1" />
          <span className="game-event-effect-rune game-event-effect-rune-2" />
        </>
      ) : null}
    </div>
  );
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
  const effectSource = eventEffectSource(currentEvent);
  const effectIntent = eventEffectIntent(currentEvent);
  const effectEnhanced =
    currentEvent.effectEnhanced === true || effectIntent === "boost" || (effectSource === "weather" && effectIntent !== "neutral");
  const effectBadge = eventEffectBadgeLabel(effectSource, effectIntent, effectEnhanced);
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
      className={`game-event-overlay ${eventCssClass(currentEvent.kind)} game-event-overlay-intent-${effectIntent} game-event-overlay-source-${effectSource} ${
        effectEnhanced ? "game-event-overlay-effect-enhanced" : ""
      }`}
      data-event-kind={currentEvent.kind}
      data-effect-intent={effectIntent}
      data-effect-source={effectSource}
      data-effect-enhanced={effectEnhanced ? "true" : "false"}
      data-effect-badge={effectBadge ?? ""}
      role="status"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div className="game-event-overlay-sprite" aria-hidden="true" />
      <EventEffectParticles intent={effectIntent} source={effectSource} enhanced={effectEnhanced} />
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
        {effectBadge ? (
          <div className="game-event-effect-badge" data-testid="game-event-effect-badge">
            {effectBadge}
          </div>
        ) : null}
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
