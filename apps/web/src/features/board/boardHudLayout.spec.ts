import { describe, expect, it } from "vitest";
import { computeBoardHudFrame, sameBoardHudFrame, type BoardHudFrame } from "./boardHudLayout";

describe("boardHudLayout", () => {
  it("computes board-safe overlay bounds from tile anchor rects", () => {
    const frame = computeBoardHudFrame({
      scrollRect: { left: 100, top: 50, right: 1100, bottom: 850, width: 1000, height: 800 },
      topTileRect: { left: 0, top: 210, right: 0, bottom: 0, width: 0, height: 0 },
      bottomTileRect: { left: 0, top: 0, right: 0, bottom: 730, width: 0, height: 0 },
      leftTileRect: { left: 180, top: 0, right: 0, bottom: 0, width: 0, height: 0 },
      rightTileRect: { left: 0, top: 0, right: 920, bottom: 0, width: 0, height: 0 },
      promptTopTileRect: { left: 0, top: 310, right: 0, bottom: 0, width: 0, height: 0 },
      handTrayTopTileRect: { left: 0, top: 610, right: 0, bottom: 0, width: 0, height: 0 },
      handTrayBottomTileRect: { left: 0, top: 0, right: 0, bottom: 690, width: 0, height: 0 },
    });

    expect(frame).toEqual({
      boardWidth: 1000,
      boardHeight: 800,
      safeTop: 160,
      safeBottomGap: 120,
      safeLeft: 80,
      safeRightGap: 180,
      viewportLeft: 180,
      viewportTop: 210,
      viewportWidth: 740,
      viewportHeight: 520,
      promptTopInset: 100,
      handTrayTopInset: 400,
      handTrayBottomGap: 160,
      handTrayHeight: 80,
    });
  });

  it("returns null without both horizontal anchor tiles", () => {
    expect(
      computeBoardHudFrame({
        scrollRect: { left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100 },
        leftTileRect: { left: 20, top: 20, right: 20, bottom: 20, width: 0, height: 0 },
      })
    ).toBeNull();
  });

  it("compares frames structurally", () => {
    const left: BoardHudFrame = {
      boardWidth: 100,
      boardHeight: 100,
      safeTop: 10,
      safeBottomGap: 10,
      safeLeft: 10,
      safeRightGap: 10,
      viewportLeft: 20,
      viewportTop: 20,
      viewportWidth: 80,
      viewportHeight: 80,
      promptTopInset: 0,
      handTrayTopInset: 20,
      handTrayBottomGap: 10,
      handTrayHeight: 20,
    };
    expect(sameBoardHudFrame(left, { ...left })).toBe(true);
    expect(sameBoardHudFrame(left, { ...left, viewportWidth: 81 })).toBe(false);
    expect(sameBoardHudFrame(left, null)).toBe(false);
  });
});
