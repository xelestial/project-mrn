import { describe, expect, it } from "vitest";
import { KNOWN_PROMPT_TYPES } from "./promptTypeCatalog";
import { DEFAULT_PROMPT_HELPER_TEXT, promptHelperForType } from "./promptHelperCatalog";

describe("promptHelperCatalog", () => {
  it("covers all known prompt request types", () => {
    for (const requestType of KNOWN_PROMPT_TYPES) {
      expect(promptHelperForType(requestType)).not.toBe(DEFAULT_PROMPT_HELPER_TEXT);
    }
  });

  it("supports compatibility alias for final_character_choice", () => {
    expect(promptHelperForType("final_character_choice")).toContain("최종 캐릭터");
  });

  it("falls back for unknown request type", () => {
    expect(promptHelperForType("future_type")).toBe(DEFAULT_PROMPT_HELPER_TEXT);
  });
});
