import { describe, expect, it } from "vitest";
import { buildPromptEffectResourceDeltaChips } from "./promptEffectContextDisplay";

describe("promptEffectContextDisplay", () => {
  it("builds localized resource delta chips for effect-caused prompts", () => {
    expect(
      buildPromptEffectResourceDeltaChips(
        {
          label: "재보급",
          detail: "재보급으로 보유 자원이 조정되었습니다.",
          attribution: "Supply threshold",
          tone: "economy",
          source: "system",
          intent: "resupply",
          enhanced: true,
          resourceDelta: {
            cash: -3,
            shards: 2,
            coins: 0,
            ignored: "skip",
          },
        },
        "ko"
      )
    ).toEqual([
      { key: "cash", label: "현금 -3", value: -3, polarity: "loss" },
      { key: "shards", label: "조각 +2", value: 2, polarity: "gain" },
    ]);
  });

  it("returns no chips when resource deltas are absent or zero", () => {
    expect(
      buildPromptEffectResourceDeltaChips(
        {
          label: "도착",
          detail: "도착 효과를 처리합니다.",
          attribution: "Movement result",
          tone: "move",
          source: "move",
          intent: "arrival",
          enhanced: false,
          resourceDelta: {
            cash: 0,
          },
        },
        "en"
      )
    ).toEqual([]);
  });
});
