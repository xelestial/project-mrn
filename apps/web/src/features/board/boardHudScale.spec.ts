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
    expect(scale.handGridColumns).toBe(6);
    expect(scale.promptMaxHeight).toBeGreaterThanOrEqual(196);
    expect(scale.promptShellMaxWidth).toBeGreaterThanOrEqual(1000);
    expect(scale.handTrayMaxHeight).toBeGreaterThanOrEqual(136);
    expect(scale.playerCardMinHeight).toBeGreaterThanOrEqual(118);
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
    expect(scale.handCardMinWidth).toBeGreaterThanOrEqual(120);
    expect(scale.choiceMinHeight).toBeLessThanOrEqual(140);
    expect(scale.promptShellMaxWidth).toBeLessThanOrEqual(1000);
    expect(scale.handTrayMaxHeight).toBeLessThanOrEqual(220);
  });

  it.each([
    { label: "1440x900", boardWidth: 1440, boardHeight: 900, viewportWidth: 980, viewportHeight: 560 },
    { label: "1600x1000", boardWidth: 1600, boardHeight: 1000, viewportWidth: 1120, viewportHeight: 660 },
    { label: "1920x1080", boardWidth: 1920, boardHeight: 1080, viewportWidth: 1320, viewportHeight: 720 },
  ])("keeps desktop decision prompts readable at $label", ({ boardWidth, boardHeight, viewportWidth, viewportHeight }) => {
    const scale = computeBoardHudScale({
      boardWidth,
      boardHeight,
      viewportWidth,
      viewportHeight,
    });

    expect(scale.density).not.toBe("compact");
    expect(scale.promptMaxHeight).toBeGreaterThanOrEqual(240);
    expect(scale.promptShellMaxWidth).toBeGreaterThanOrEqual(960);
    expect(scale.choiceMinWidth).toBeGreaterThanOrEqual(150);
    expect(scale.handGridColumns).toBe(6);
  });
});
