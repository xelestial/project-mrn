import { describe, expect, it } from "vitest";
import { boardSizeForTileCount, projectTilePosition, ringPosition } from "./boardProjection";

function uniqueKey(row: number, col: number): string {
  return `${row}:${col}`;
}

describe("boardProjection", () => {
  it("computes reasonable board size for tile count", () => {
    expect(boardSizeForTileCount(40)).toBeGreaterThanOrEqual(11);
    expect(boardSizeForTileCount(20)).toBeGreaterThanOrEqual(6);
    expect(boardSizeForTileCount(8)).toBeGreaterThanOrEqual(5);
    expect(boardSizeForTileCount(8, "line")).toBe(8);
  });

  it("projects non-default tile count into valid ring coordinates", () => {
    const tileCount = 24;
    const boardSize = boardSizeForTileCount(tileCount);
    const coords = Array.from({ length: tileCount }, (_, i) => ringPosition(i, boardSize));
    for (const c of coords) {
      expect(c.row).toBeGreaterThanOrEqual(1);
      expect(c.col).toBeGreaterThanOrEqual(1);
      expect(c.row).toBeLessThanOrEqual(boardSize);
      expect(c.col).toBeLessThanOrEqual(boardSize);
      expect(c.row === 1 || c.row === boardSize || c.col === 1 || c.col === boardSize).toBe(true);
    }
  });

  it("keeps coordinates unique for initial tiles in small topology", () => {
    const tileCount = 12;
    const boardSize = boardSizeForTileCount(tileCount);
    const keys = new Set<string>();
    for (let i = 0; i < tileCount; i += 1) {
      const c = ringPosition(i, boardSize);
      keys.add(uniqueKey(c.row, c.col));
    }
    expect(keys.size).toBe(tileCount);
  });

  it("projects line topology positions in a single row", () => {
    const tileCount = 6;
    const projected = Array.from({ length: tileCount }, (_, i) => projectTilePosition(i, tileCount, "line"));
    for (const p of projected) {
      expect(p.row).toBe(1);
      expect(p.col).toBeGreaterThanOrEqual(1);
      expect(p.col).toBeLessThanOrEqual(tileCount);
    }
    expect(projected.map((p) => p.col)).toEqual([1, 2, 3, 4, 5, 6]);
  });
});
