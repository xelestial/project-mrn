function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function canonicalEffectCharacterFromActorName(actorName: string | null): string | undefined {
  if (!actorName) {
    return undefined;
  }
  const normalized = actorName.trim().toLowerCase();
  if (normalized === "박수" || normalized === "baksu") return "박수";
  if (normalized === "만신" || normalized === "manshin") return "만신";
  if (normalized === "중매꾼" || normalized === "matchmaker") return "중매꾼";
  return actorName;
}

function effectCharacterFromCanonicalId(effectCharacterId: string | null): string | undefined {
  if (!effectCharacterId) {
    return undefined;
  }
  if (effectCharacterId === "character.card.6.face.1") return "박수";
  if (effectCharacterId === "character.card.6.face.2") return "만신";
  if (effectCharacterId === "character.card.7.face.2") return "중매꾼";
  return undefined;
}

export function effectCharacterFromPayload(payload: Record<string, unknown> | null): string | undefined {
  const resolution = recordOrNull(payload?.["resolution"]);
  const canonicalName =
    stringOrNull(payload?.["effect_character_name"]) ?? stringOrNull(resolution?.["effect_character_name"]);
  const byName = canonicalEffectCharacterFromActorName(canonicalName);
  if (byName) {
    return byName;
  }

  const canonicalId = stringOrNull(payload?.["effect_character_id"]) ?? stringOrNull(resolution?.["effect_character_id"]);
  const byId = effectCharacterFromCanonicalId(canonicalId);
  if (byId) {
    return byId;
  }

  return undefined;
}
