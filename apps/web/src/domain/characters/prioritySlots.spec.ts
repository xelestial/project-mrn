import { describe, expect, it } from "vitest";
import { findPrioritySlotOwner, prioritySlotForCharacter } from "./prioritySlots";

describe("prioritySlots", () => {
  it("maps both faces of a character card to the same priority slot", () => {
    expect(prioritySlotForCharacter("객주")).toBe(7);
    expect(prioritySlotForCharacter("중매꾼")).toBe(7);
    expect(prioritySlotForCharacter("교리 연구관")).toBe(5);
    expect(prioritySlotForCharacter("교리감독관")).toBe(5);
  });

  it("keeps the slot owner tied to the original character card even when the active face changes", () => {
    const owner = findPrioritySlotOwner(
      [
        { playerId: 2, character: "객주" },
        { playerId: 3, character: "건설업자" },
      ],
      7,
    );

    expect(prioritySlotForCharacter("중매꾼")).toBe(7);
    expect(owner?.playerId).toBe(2);
  });
});
