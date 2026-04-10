const PRIORITY_SLOT_BY_CHARACTER: Record<string, number> = {
  어사: 1,
  탐관오리: 1,
  자객: 2,
  산적: 2,
  추노꾼: 3,
  "탈출 노비": 3,
  탈출노비: 3,
  파발꾼: 4,
  아전: 4,
  "교리 연구관": 5,
  교리연구관: 5,
  "교리 감독관": 5,
  교리감독관: 5,
  박수: 6,
  만신: 6,
  객주: 7,
  중매꾼: 7,
  건설업자: 8,
  사기꾼: 8,
};

const SLOT_CHARACTER_PAIRS: Record<number, [string, string]> = {
  1: ["어사", "탐관오리"],
  2: ["자객", "산적"],
  3: ["추노꾼", "탈출 노비"],
  4: ["파발꾼", "아전"],
  5: ["교리 연구관", "교리 감독관"],
  6: ["박수", "만신"],
  7: ["객주", "중매꾼"],
  8: ["건설업자", "사기꾼"],
};

export type PrioritySlotOwner = {
  playerId: number;
  character: string | null | undefined;
};

export function prioritySlotForCharacter(character: string | null | undefined): number | null {
  if (typeof character !== "string") {
    return null;
  }
  return PRIORITY_SLOT_BY_CHARACTER[character.trim()] ?? null;
}

export function findPrioritySlotOwner<T extends PrioritySlotOwner>(players: Iterable<T>, slot: number): T | null {
  for (const player of players) {
    if (prioritySlotForCharacter(player.character) === slot) {
      return player;
    }
  }
  return null;
}

export function charactersForPrioritySlot(slot: number): [string, string] | null {
  return SLOT_CHARACTER_PAIRS[slot] ?? null;
}

export function oppositeCharacterForSlot(slot: number, activeCharacter: string | null | undefined): string | null {
  const pair = charactersForPrioritySlot(slot);
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
