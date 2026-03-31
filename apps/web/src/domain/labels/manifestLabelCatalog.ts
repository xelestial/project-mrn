export function tileKindLabelsFromManifestLabels(labels: unknown): Record<string, string> {
  if (!labels || typeof labels !== "object" || Array.isArray(labels)) {
    return {};
  }
  const root = labels as Record<string, unknown>;
  const raw = root["tile_kind_labels"] ?? root["tileKindLabels"];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }

  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === "string" && value.trim()) {
      out[key] = value;
    }
  }
  return out;
}

export function characterAbilityLabelsFromManifestLabels(labels: unknown): Record<string, string> {
  if (!labels || typeof labels !== "object" || Array.isArray(labels)) {
    return {};
  }
  const root = labels as Record<string, unknown>;
  const raw = root["character_ability_labels"] ?? root["characterAbilityLabels"];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }

  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === "string" && value.trim()) {
      out[key] = value;
      continue;
    }
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const abilityText = (value as Record<string, unknown>)["ability_text"];
      if (typeof abilityText === "string" && abilityText.trim()) {
        out[key] = abilityText;
      }
    }
  }
  return out;
}
