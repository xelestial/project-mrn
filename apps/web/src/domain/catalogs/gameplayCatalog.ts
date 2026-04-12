import gameplayCatalog from "../../../../../packages/ui-domain/gameplay_catalog.json";

type CharacterFaceCatalog = {
  face_id: string;
  name: string;
  aliases: string[];
};

type CharacterSlotCatalog = {
  slot: number;
  card_no: number;
  faces: [CharacterFaceCatalog, CharacterFaceCatalog];
};

type WeatherCatalogItem = {
  weather_id: number;
  name: string;
  effect: string;
};

type GameplayCatalog = {
  character_slots: CharacterSlotCatalog[];
  weather_cards: WeatherCatalogItem[];
};

const catalog = gameplayCatalog as GameplayCatalog;

const slotByAlias = new Map<string, number>();
const facesBySlot = new Map<number, [string, string]>();
const weatherByName = new Map<string, WeatherCatalogItem>();

for (const slot of catalog.character_slots) {
  facesBySlot.set(slot.slot, [slot.faces[0].name, slot.faces[1].name]);
  for (const face of slot.faces) {
    slotByAlias.set(face.name.trim(), slot.slot);
    for (const alias of face.aliases) {
      slotByAlias.set(alias.trim(), slot.slot);
    }
  }
}

for (const weather of catalog.weather_cards) {
  weatherByName.set(weather.name, weather);
}

export function prioritySlotForCharacterName(character: string | null | undefined): number | null {
  if (typeof character !== "string") {
    return null;
  }
  return slotByAlias.get(character.trim()) ?? null;
}

export function charactersForSlot(slot: number): [string, string] | null {
  return facesBySlot.get(slot) ?? null;
}

export function oppositeCharacterNameForSlot(slot: number, activeCharacter: string | null | undefined): string | null {
  const pair = charactersForSlot(slot);
  if (!pair) {
    return null;
  }
  if (typeof activeCharacter !== "string" || !activeCharacter.trim()) {
    return pair[1];
  }
  const normalized = activeCharacter.trim();
  if (pair[0] === normalized) {
    return pair[1];
  }
  if (pair[1] === normalized) {
    return pair[0];
  }
  return pair[1];
}

export function weatherByDisplayName(name: string | null | undefined): WeatherCatalogItem | null {
  if (typeof name !== "string" || !name.trim()) {
    return null;
  }
  return weatherByName.get(name.trim()) ?? null;
}

export function weatherEffectForDisplayName(name: string | null | undefined): string | null {
  return weatherByDisplayName(name)?.effect ?? null;
}

export { catalog as gameplayCatalog };
