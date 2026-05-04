import { describe, expect, it } from "vitest";
import { effectCharacterFromPayload } from "./effectCharacter";

describe("effectCharacterFromPayload", () => {
  it("prefers backend canonical effect owner fields over inferred fields", () => {
    expect(
      effectCharacterFromPayload({
        effect_character_name: "중매꾼",
        effect_card_no: 7,
        effect_character_id: "character.card.7.face.2",
        effect_type: "manshin_remove_burdens",
        actor_name: "만신",
      })
    ).toBe("중매꾼");
  });

  it("falls back to canonical ids when the event omits the name", () => {
    expect(effectCharacterFromPayload({ effect_character_id: "character.card.6.face.1" })).toBe("박수");
    expect(effectCharacterFromPayload({ effect_character_id: "character.card.6.face.2" })).toBe("만신");
    expect(effectCharacterFromPayload({ effect_character_id: "character.card.7.face.2" })).toBe("중매꾼");
  });

  it("does not infer effect ownership from noncanonical display fields", () => {
    expect(effectCharacterFromPayload({ effect_type: "manshin_remove_burdens", actor_name: "만신" })).toBeUndefined();
    expect(effectCharacterFromPayload({ purchase_source: "matchmaker_adjacent" })).toBeUndefined();
  });
});
