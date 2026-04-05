import { describe, expect, it } from "vitest";
import { DEFAULT_PROMPT_HELPER_TEXT, promptHelperForType } from "./promptHelperCatalog";

describe("promptHelperCatalog", () => {
  it("returns known helper text", () => {
    expect(promptHelperForType("movement")).toContain("주사위");
    expect(promptHelperForType("hidden_trick_card")).toContain("히든");
  });

  it("supports compatibility alias for final_character_choice", () => {
    expect(promptHelperForType("final_character_choice")).toContain("최종");
  });

  it("falls back to default text", () => {
    expect(promptHelperForType("unknown_prompt")).toBe(DEFAULT_PROMPT_HELPER_TEXT);
  });
});
