import { describe, expect, it } from "vitest";
import { buildPromptEffectResourceDeltaChips, buildPromptEffectSourceChips } from "./promptEffectContextDisplay";

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

  it("builds localized source chips for effect-caused prompts", () => {
    expect(
      buildPromptEffectSourceChips(
        {
          label: "재보급",
          detail: "재보급으로 보유 자원이 조정되었습니다.",
          attribution: "Supply threshold",
          tone: "economy",
          source: "system",
          intent: "resupply",
          enhanced: true,
          sourcePlayerId: 2,
          sourceFamily: "weather",
          sourceName: "아주 큰 화목 난로",
        },
        "ko"
      )
    ).toEqual([
      { key: "source-player", label: "원인 P2" },
      { key: "source-family", label: "날씨" },
      { key: "source-name", label: "아주 큰 화목 난로" },
    ]);
  });
});
