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
    expect(promptLabelForType("movement")).toBe("이동값 결정");
    expect(promptLabelForType("trick_to_use")).toBe("잔꾀 사용");
    expect(promptLabelForType("final_character")).toBe("최종 캐릭터 선택");
  });

  it("supports compatibility alias and unknown fallback", () => {
    expect(promptLabelForType("final_character_choice")).toBe("최종 캐릭터 선택");
    expect(promptLabelForType("future_type")).toBe("future_type");
    expect(promptLabelForType("")).toBe("선택 요청");
  });
});
