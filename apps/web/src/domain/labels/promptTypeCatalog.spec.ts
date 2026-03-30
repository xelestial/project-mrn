import { describe, expect, it } from "vitest";
import { KNOWN_PROMPT_TYPES, promptLabelForType } from "./promptTypeCatalog";

describe("promptTypeCatalog", () => {
  it("contains the canonical request types from human policy", () => {
    expect(KNOWN_PROMPT_TYPES).toEqual([
      "movement",
      "runaway_step_choice",
      "lap_reward",
      "draft_card",
      "final_character",
      "trick_to_use",
      "purchase_tile",
      "hidden_trick_card",
      "mark_target",
      "coin_placement",
      "geo_bonus",
      "doctrine_relief",
      "active_flip",
      "specific_trick_reward",
      "burden_exchange",
    ]);
  });

  it("returns readable labels for known request types", () => {
    expect(promptLabelForType("movement")).toBe("Move Decision");
    expect(promptLabelForType("trick_to_use")).toBe("Trick Usage");
    expect(promptLabelForType("final_character")).toBe("Final Character Choice");
  });

  it("supports compatibility alias and unknown fallback", () => {
    expect(promptLabelForType("final_character_choice")).toBe("Final Character Choice");
    expect(promptLabelForType("future_type")).toBe("future_type");
    expect(promptLabelForType("")).toBe("Prompt");
  });
});
