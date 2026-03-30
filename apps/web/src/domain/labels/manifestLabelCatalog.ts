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

