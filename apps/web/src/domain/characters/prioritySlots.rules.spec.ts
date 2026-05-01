import { describe, expect, it } from "vitest";
import { fc } from "../../test/harness/gameRuleHarness";
import { characterFaceArbitrary, characterSlotArbitrary } from "../../test/harness/gameRuleArbitraries";
import { gameplayCatalog } from "../catalogs/gameplayCatalog";
import {
  charactersForPrioritySlot,
  findPrioritySlotOwner,
  oppositeCharacterForSlot,
  prioritySlotForCharacter,
} from "./prioritySlots";

describe("prioritySlots rule harness", () => {
  it("maps every generated catalog face and alias back to its priority slot", () => {
    fc.assert(
      fc.property(characterFaceArbitrary, ({ slot, face }) => {
        expect(prioritySlotForCharacter(face.name)).toBe(slot);
        for (const alias of face.aliases) {
          expect(prioritySlotForCharacter(alias)).toBe(slot);
        }
      }),
      { numRuns: 100, seed: 20260430 },
    );
  });

  it("keeps opposite faces inside the same generated character card", () => {
    fc.assert(
      fc.property(characterSlotArbitrary, (slot) => {
        const [left, right] = slot.faces.map((face) => face.name);

        expect(charactersForPrioritySlot(slot.slot)).toEqual([left, right]);
        expect(oppositeCharacterForSlot(slot.slot, left)).toBe(right);
        expect(oppositeCharacterForSlot(slot.slot, right)).toBe(left);
      }),
      { numRuns: 100, seed: 20260430 },
    );
  });

  it("finds the first generated player whose active face owns the requested slot", () => {
    fc.assert(
      fc.property(characterSlotArbitrary, fc.integer({ min: 1, max: 4 }), (slot, ownerPlayerId) => {
        const otherSlot = gameplayCatalog.character_slots.find((candidate) => candidate.slot !== slot.slot);
        const players = [
          { playerId: ownerPlayerId, character: slot.faces[1].name },
          { playerId: ownerPlayerId + 10, character: otherSlot?.faces[0].name ?? null },
        ];

        expect(findPrioritySlotOwner(players, slot.slot)?.playerId).toBe(ownerPlayerId);
      }),
      { numRuns: 100, seed: 20260430 },
    );
  });
});
