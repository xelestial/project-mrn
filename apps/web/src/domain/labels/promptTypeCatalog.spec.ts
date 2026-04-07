import { describe, expect, it } from "vitest";
import { KNOWN_PROMPT_TYPES, promptLabelForType } from "./promptTypeCatalog";

describe("promptTypeCatalog", () => {
  it("keeps the expected prompt types", () => {
    expect(KNOWN_PROMPT_TYPES).toContain("movement");
    expect(KNOWN_PROMPT_TYPES).toContain("trick_to_use");
    expect(KNOWN_PROMPT_TYPES).toContain("final_character_choice");
    expect(KNOWN_PROMPT_TYPES).toContain("trick_tile_target");
  });

  it("maps known prompt types to Korean labels", () => {
    expect(promptLabelForType("movement")).toBe("이동값 결정");
    expect(promptLabelForType("trick_to_use")).toBe("잔꾀 사용");
    expect(promptLabelForType("final_character")).toBe("최종 캐릭터 선택");
  });

  it("supports compatibility alias for final_character_choice", () => {
    expect(promptLabelForType("final_character_choice")).toBe("최종 캐릭터 선택");
  });

  it("falls back to generic prompt label for blank values", () => {
    expect(promptLabelForType("")).toBe("선택 요청");
  });
});
