import {
  charactersForSlot,
  oppositeCharacterNameForSlot,
  prioritySlotForCharacterName,
} from "../catalogs/gameplayCatalog";

export type PrioritySlotOwner = {
  playerId: number;
  character: string | null | undefined;
};

export function prioritySlotForCharacter(character: string | null | undefined): number | null {
  return prioritySlotForCharacterName(character);
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
  return charactersForSlot(slot);
}

export function oppositeCharacterForSlot(slot: number, activeCharacter: string | null | undefined): string | null {
  return oppositeCharacterNameForSlot(slot, activeCharacter);
}
