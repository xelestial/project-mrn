export type PromptEffectContextForDisplay = {
  [key: string]: unknown;
  sourcePlayerId?: number | null;
  sourceFamily?: string | null;
  sourceName?: string | null;
  resourceDelta?: Record<string, unknown> | null;
};

export type PromptEffectResourceDeltaChip = {
  key: string;
  label: string;
  value: number;
  polarity: "gain" | "loss" | "neutral";
};

export type PromptEffectSourceChip = {
  key: string;
  label: string;
};

const RESOURCE_ORDER = ["cash", "coins", "shards", "burden", "cards"];

const RESOURCE_LABELS: Record<string, { ko: string; en: string }> = {
  cash: { ko: "현금", en: "Cash" },
  coins: { ko: "승점", en: "Score" },
  shards: { ko: "조각", en: "Shards" },
  burden: { ko: "짐", en: "Burden" },
  cards: { ko: "카드", en: "Cards" },
};

const SOURCE_FAMILY_LABELS: Record<string, { ko: string; en: string }> = {
  character: { ko: "인물", en: "Character" },
  economy: { ko: "경제", en: "Economy" },
  fortune: { ko: "운수", en: "Fortune" },
  mark: { ko: "지목", en: "Mark" },
  move: { ko: "이동", en: "Move" },
  system: { ko: "시스템", en: "System" },
  trick: { ko: "잔꾀", en: "Trick" },
  weather: { ko: "날씨", en: "Weather" },
};

export function buildPromptEffectResourceDeltaChips(
  effectContext: PromptEffectContextForDisplay | null | undefined,
  locale: string
): PromptEffectResourceDeltaChip[] {
  const delta = effectContext?.resourceDelta;
  if (!delta || typeof delta !== "object") {
    return [];
  }
  const entries = Object.entries(delta)
    .filter((entry): entry is [string, number] => {
      const value = entry[1];
      return typeof value === "number" && Number.isFinite(value) && value !== 0;
    })
    .sort(([left], [right]) => resourceSortIndex(left) - resourceSortIndex(right) || left.localeCompare(right));

  return entries.map(([key, value]) => {
    const resourceLabel = resourceLabelForKey(key, locale);
    const signedValue = value > 0 ? `+${value}` : String(value);
    return {
      key,
      label: `${resourceLabel} ${signedValue}`,
      value,
      polarity: value > 0 ? "gain" : value < 0 ? "loss" : "neutral",
    };
  });
}

export function buildPromptEffectSourceChips(
  effectContext: PromptEffectContextForDisplay | null | undefined,
  locale: string
): PromptEffectSourceChip[] {
  if (!effectContext) {
    return [];
  }
  const chips: PromptEffectSourceChip[] = [];
  if (typeof effectContext.sourcePlayerId === "number" && Number.isFinite(effectContext.sourcePlayerId)) {
    chips.push({
      key: "source-player",
      label: locale.toLowerCase().startsWith("ko")
        ? `원인 P${effectContext.sourcePlayerId}`
        : `Source P${effectContext.sourcePlayerId}`,
    });
  }
  const sourceFamily =
    stringValue(effectContext.sourceFamily) ||
    stringValue(effectContext.source);
  if (sourceFamily) {
    chips.push({
      key: "source-family",
      label: sourceFamilyLabelForKey(sourceFamily, locale),
    });
  }
  const sourceName = stringValue(effectContext.sourceName);
  if (sourceName) {
    chips.push({
      key: "source-name",
      label: sourceName,
    });
  }
  return chips;
}

function resourceSortIndex(key: string): number {
  const index = RESOURCE_ORDER.indexOf(key);
  return index === -1 ? RESOURCE_ORDER.length : index;
}

function resourceLabelForKey(key: string, locale: string): string {
  const labels = RESOURCE_LABELS[key];
  if (!labels) {
    return key;
  }
  return locale.toLowerCase().startsWith("ko") ? labels.ko : labels.en;
}

function sourceFamilyLabelForKey(key: string, locale: string): string {
  const labels = SOURCE_FAMILY_LABELS[key];
  if (!labels) {
    return key;
  }
  return locale.toLowerCase().startsWith("ko") ? labels.ko : labels.en;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
