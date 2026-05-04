export type PromptEffectContextForDisplay = {
  [key: string]: unknown;
  resourceDelta?: Record<string, unknown> | null;
};

export type PromptEffectResourceDeltaChip = {
  key: string;
  label: string;
  value: number;
  polarity: "gain" | "loss" | "neutral";
};

const RESOURCE_ORDER = ["cash", "coins", "shards", "burden", "cards"];

const RESOURCE_LABELS: Record<string, { ko: string; en: string }> = {
  cash: { ko: "현금", en: "Cash" },
  coins: { ko: "승점", en: "Score" },
  shards: { ko: "조각", en: "Shards" },
  burden: { ko: "짐", en: "Burden" },
  cards: { ko: "카드", en: "Cards" },
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
