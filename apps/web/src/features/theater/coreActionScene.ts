import type { LocaleMessages } from "../../i18n/types";
import type { CoreActionItem } from "../../domain/selectors/streamSelectors";

export type ActionKind = "move" | "economy" | "effect" | "decision" | "system";

export type PayoffSceneItem = {
  seq: number;
  actor: string;
  label: string;
  detail: string;
  headline: string;
  kind: ActionKind;
  eventCode: string;
  phaseLabel: string;
  isLatest: boolean;
};

type TheaterText = LocaleMessages["theater"];

const MOVE_EVENT_CODES = new Set(["turn_start", "dice_roll", "player_move"]);
const ECONOMY_EVENT_CODES = new Set(["tile_purchased", "rent_paid", "lap_reward_chosen"]);
const EFFECT_EVENT_CODES = new Set([
  "weather_reveal",
  "fortune_drawn",
  "fortune_resolved",
  "trick_used",
  "marker_flip",
  "marker_transferred",
  "mark_queued",
  "mark_resolved",
  "landing_resolved",
]);
const DECISION_EVENT_CODES = new Set(["decision_requested", "decision_resolved", "decision_timeout_fallback"]);
const PAYOFF_SCENE_EVENT_CODES = new Set([
  "tile_purchased",
  "rent_paid",
  "fortune_drawn",
  "fortune_resolved",
  "lap_reward_chosen",
]);
const EFFECT_PAYOFF_SCENE_EVENT_CODES = new Set(["fortune_drawn", "fortune_resolved"]);

function normalize(value: string): string {
  return value.toLowerCase();
}

export function classifyCoreAction(item: CoreActionItem, theaterText: TheaterText): ActionKind {
  if (MOVE_EVENT_CODES.has(item.eventCode)) {
    return "move";
  }
  if (ECONOMY_EVENT_CODES.has(item.eventCode)) {
    return "economy";
  }
  if (EFFECT_EVENT_CODES.has(item.eventCode)) {
    return "effect";
  }
  if (DECISION_EVENT_CODES.has(item.eventCode)) {
    return "decision";
  }

  const haystack = normalize(`${item.label} ${item.detail}`);
  const includesAny = (terms: readonly string[]) => terms.some((term) => haystack.includes(normalize(term)));

  if (haystack.includes("move") || haystack.includes("dice") || includesAny(theaterText.actionKeywords.move)) {
    return "move";
  }
  if (
    haystack.includes("rent") ||
    haystack.includes("purchase") ||
    haystack.includes("cash") ||
    haystack.includes("shard") ||
    includesAny(theaterText.actionKeywords.economy)
  ) {
    return "economy";
  }
  if (
    haystack.includes("fortune") ||
    haystack.includes("weather") ||
    haystack.includes("trick") ||
    haystack.includes("flip") ||
    includesAny(theaterText.actionKeywords.effect)
  ) {
    return "effect";
  }
  if (haystack.includes("prompt") || haystack.includes("decision") || includesAny(theaterText.actionKeywords.decision)) {
    return "decision";
  }
  return "system";
}

export function splitCoreActionDetail(detail: string, noDetailLabel: string): string[] {
  const compact = detail.replace(/\s+/g, " ").trim();
  if (!compact || compact === "-") {
    return [noDetailLabel];
  }

  const pieces = compact
    .split(/\s*\|\s*|\s*\/\s*|(?<=\.)\s+/)
    .map((part) => part.trim())
    .filter(Boolean);

  return pieces.length > 0 ? pieces.slice(0, 3) : [compact];
}

export function headlineCoreActionDetail(item: CoreActionItem, theaterText: TheaterText): string {
  return splitCoreActionDetail(item.detail, theaterText.noDetail)[0] ?? theaterText.noDetail;
}

export function payoffPhaseLabel(eventCode: string, theaterText: TheaterText): string {
  return theaterText.payoffBeat[eventCode as keyof typeof theaterText.payoffBeat] ?? theaterText.actionKind.system;
}

export function buildPayoffSceneItems(itemsNewestFirst: CoreActionItem[], theaterText: TheaterText): PayoffSceneItem[] {
  const selected = itemsNewestFirst.filter((item) => PAYOFF_SCENE_EVENT_CODES.has(item.eventCode));
  if (selected.length === 0) {
    return [];
  }

  const anchor = selected.find((item) => EFFECT_PAYOFF_SCENE_EVENT_CODES.has(item.eventCode)) ?? selected[0] ?? null;
  const isSameTurn = (item: CoreActionItem) => item.round === anchor?.round && item.turn === anchor?.turn;
  const anchorTurnItems =
    anchor === null
      ? selected
      : selected.filter((item) => isSameTurn(item) && PAYOFF_SCENE_EVENT_CODES.has(item.eventCode));
  const preferredItems = [...anchorTurnItems].sort((a, b) => a.seq - b.seq);
  const latestSeq = preferredItems.at(-1)?.seq ?? null;
  return preferredItems.map((item) => ({
    seq: item.seq,
    actor: item.actor,
    label: item.label,
    detail: item.detail,
    headline: headlineCoreActionDetail(item, theaterText),
    kind: classifyCoreAction(item, theaterText),
    eventCode: item.eventCode,
    phaseLabel: payoffPhaseLabel(item.eventCode, theaterText),
    isLatest: latestSeq !== null && item.seq === latestSeq,
  }));
}
