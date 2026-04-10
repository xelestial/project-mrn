import { describe, expect, it } from "vitest";
import { computeBoardHudScale } from "./boardHudScale";

describe("boardHudScale", () => {
  it("keeps comfortable scale on roomy board scenes", () => {
    const scale = computeBoardHudScale({
      boardWidth: 1600,
      boardHeight: 900,
      viewportWidth: 1220,
      viewportHeight: 620,
    });

    expect(scale.sceneScale).toBeGreaterThanOrEqual(1);
    expect(scale.density).not.toBe("compact");
    expect(scale.handGridColumns).toBe(5);
    expect(scale.promptMaxHeight).toBeGreaterThanOrEqual(200);
    expect(scale.promptShellMaxWidth).toBeGreaterThanOrEqual(1000);
    expect(scale.handTrayMaxHeight).toBeGreaterThanOrEqual(136);
    expect(scale.playerCardMinHeight).toBeGreaterThanOrEqual(140);
  });

  it("shrinks typography and spacing for constrained overlay scenes", () => {
    const scale = computeBoardHudScale({
      boardWidth: 980,
      boardHeight: 640,
      viewportWidth: 720,
      viewportHeight: 360,
    });

    expect(scale.density).toBe("compact");
    expect(scale.bodyFontSize).toBeLessThanOrEqual(12);
    expect(scale.overlayGap).toBeLessThanOrEqual(12);
    expect(scale.choiceMinWidth).toBeGreaterThanOrEqual(150);
    expect(scale.handCardMinWidth).toBeGreaterThanOrEqual(138);
    expect(scale.choiceMinHeight).toBeLessThanOrEqual(140);
    expect(scale.promptShellMaxWidth).toBeLessThanOrEqual(1000);
    expect(scale.handTrayMaxHeight).toBeLessThanOrEqual(220);
  });
});
