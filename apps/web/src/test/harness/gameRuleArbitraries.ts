import { gameplayCatalog } from "../../domain/catalogs/gameplayCatalog";
import type { BoardTopology } from "../../features/board/boardProjection";
import { fc } from "./gameRuleHarness";

type CharacterFace = {
  face_id: string;
  name: string;
  aliases: string[];
};

type CharacterSlot = {
  slot: number;
  card_no: number;
  faces: [CharacterFace, CharacterFace];
};

export const tileCountArbitrary = fc.integer({ min: 1, max: 120 });

export const topologyArbitrary = fc.constantFrom<BoardTopology>("ring", "line");

export const characterSlotArbitrary = fc.constantFrom(
  ...(gameplayCatalog.character_slots as CharacterSlot[]),
);

export const characterFaceArbitrary = characterSlotArbitrary.chain((slot) =>
  fc.constantFrom(
    ...slot.faces.map((face) => ({
      slot: slot.slot,
      face,
    })),
  ),
);
