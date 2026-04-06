import { describe, expect, it } from "vitest";
import { koLocale } from "../../i18n/locales/ko";
import { buildPayoffSceneItems, classifyCoreAction, splitCoreActionDetail, type ActionKind } from "./coreActionScene";
import type { CoreActionItem } from "../../domain/selectors/streamSelectors";

function item(overrides: Partial<CoreActionItem>): CoreActionItem {
  return {
    seq: 1,
    actor: "P1",
    eventCode: "turn_start",
    round: 2,
    turn: 4,
    label: "턴 시작",
    detail: "P1",
    isLocalActor: false,
    ...overrides,
  };
}

describe("coreActionScene", () => {
  it("classifies canonical payoff and effect events before string heuristics", () => {
    const cases: Array<[string, ActionKind]> = [
      ["tile_purchased", "economy"],
      ["rent_paid", "economy"],
      ["fortune_drawn", "effect"],
      ["fortune_resolved", "effect"],
      ["decision_requested", "decision"],
      ["player_move", "move"],
    ];

    for (const [eventCode, expected] of cases) {
      expect(
        classifyCoreAction(
          item({
            eventCode,
            label: "unrelated opaque label",
            detail: "opaque payload detail",
          }),
          koLocale.theater
        )
      ).toBe(expected);
    }
  });

  it("builds payoff scenes in chronological order and marks the latest beat", () => {
    const scenes = buildPayoffSceneItems(
      [
        item({ seq: 14, eventCode: "fortune_resolved", label: "운수 처리", detail: "P2 / 이동 +2" }),
        item({ seq: 13, eventCode: "fortune_drawn", label: "운수 공개", detail: "P2 / 도약의 바람" }),
        item({ seq: 12, eventCode: "tile_purchased", label: "토지 구매", detail: "P2 / 9번 칸 구매 / 비용 5" }),
        item({ seq: 11, eventCode: "player_move", label: "말 이동", detail: "4번 -> 9번 / 경로 5칸" }),
      ],
      koLocale.theater
    );

    expect(scenes.map((scene) => scene.eventCode)).toEqual(["tile_purchased", "fortune_drawn", "fortune_resolved"]);
    expect(scenes.map((scene) => scene.phaseLabel)).toEqual(["구매 결과", "운수 공개", "운수 효과"]);
    expect(scenes.map((scene) => scene.headline)).toEqual(["P2", "P2", "P2"]);
    expect(scenes.map((scene) => scene.isLatest)).toEqual([false, false, true]);
  });

  it("keeps compact detail chunks for scene cards", () => {
    expect(splitCoreActionDetail("P2 / 9번 칸 구매 / 비용 5", koLocale.theater.noDetail)).toEqual([
      "P2",
      "9번 칸 구매",
      "비용 5",
    ]);
  });
});
