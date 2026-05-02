import { describe, expect, it } from "vitest";
import {
  boardGridForTileCount,
  boardSizeForTileCount,
  projectTilePosition,
  projectTileQuarterview,
  quarterviewBoardGeometry,
  quarterviewFacingForLane,
  quarterviewFacingForTileStep,
  quarterviewIdleFacingForTile,
  quarterviewIdleFacingForPosition,
  quarterviewLaneModels,
  quarterviewTilePolygons,
  ringPosition,
} from "./boardProjection";

function uniqueKey(row: number, col: number): string {
  return `${row}:${col}`;
}

describe("boardProjection", () => {
  it("computes reasonable board size for tile count", () => {
    expect(boardSizeForTileCount(40)).toBeGreaterThanOrEqual(11);
    expect(boardSizeForTileCount(20)).toBeGreaterThanOrEqual(6);
    expect(boardSizeForTileCount(8)).toBeGreaterThanOrEqual(5);
    expect(boardSizeForTileCount(0)).toBe(11);
    expect(boardSizeForTileCount(8, "line")).toBe(8);
  });

  it("returns separate rows/cols for line topology grid", () => {
    const line = boardGridForTileCount(6, "line");
    expect(line.cols).toBe(6);
    expect(line.rows).toBe(1);

    const ring = boardGridForTileCount(24, "ring");
    expect(ring.cols).toBe(ring.rows);
    expect(ring.cols).toBeGreaterThanOrEqual(7);
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

  it("projects ring tiles into a bounded quarterview diamond", () => {
    const tileCount = 40;
    const projected = Array.from({ length: tileCount }, (_, i) => projectTileQuarterview(i, tileCount, "ring"));
    for (const point of projected) {
      expect(point.xPercent).toBeGreaterThanOrEqual(0);
      expect(point.xPercent).toBeLessThanOrEqual(100);
      expect(point.yPercent).toBeGreaterThanOrEqual(0);
      expect(point.yPercent).toBeLessThanOrEqual(100);
      expect(point.zIndex).toBeGreaterThan(1000);
    }
    expect(projected[0].lane).toBe("top");
    expect(projected[10].lane).toBe("top");
    expect(projected[11].lane).toBe("right");
    expect(projected[20].lane).toBe("bottom");
    expect(projected[31].lane).toBe("left");
    expect(projected[0].yPercent).toBeLessThan(projected[20].yPercent);
  });

  it("derives a flattened quarterview geometry from split x/y spreads", () => {
    const geometry = quarterviewBoardGeometry(boardSizeForTileCount(40));
    expect(geometry.xSpreadPercent).toBeGreaterThan(geometry.ySpreadPercent);
    expect(geometry.boardAspectRatio).toBeGreaterThan(1);
    expect(geometry.tileAngleDeg).toBeGreaterThan(18);
    expect(geometry.tileAngleDeg).toBeLessThan(30);
    expect(geometry.tileInlinePercent * geometry.boardAspectRatio).toBeGreaterThan(geometry.tileBlockPercent);
    expect(geometry.tileBlockPercent).toBeGreaterThan(0);
  });

  it("groups quarterview ring tiles into lane-owned visual strips", () => {
    const lanes = quarterviewLaneModels(40, "ring");
    expect(lanes.map((lane) => lane.lane)).toEqual(["top", "right", "bottom", "left"]);
    expect(lanes.flatMap((lane) => lane.cells).map((cell) => cell.tileIndex).sort((a, b) => a - b)).toEqual(
      Array.from({ length: 40 }, (_, i) => i)
    );
    expect(lanes.every((lane) => lane.lengthPercent > 0 && lane.thicknessPercent > 0)).toBe(true);
    expect(lanes.every((lane) => Math.abs(lane.rotationDeg) < 45)).toBe(true);
    expect(lanes.find((lane) => lane.lane === "top")?.cells.length).toBe(11);
    expect(lanes.find((lane) => lane.lane === "right")?.cells.length).toBe(9);
  });

  it("keeps quarterview tile numbers sequential around the visible board", () => {
    const lanes = quarterviewLaneModels(40, "ring");
    expect(lanes.find((lane) => lane.lane === "top")?.cells.map((cell) => cell.tileIndex + 1)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
    ]);
    expect(lanes.find((lane) => lane.lane === "right")?.cells.map((cell) => cell.tileIndex + 1)).toEqual([
      12, 13, 14, 15, 16, 17, 18, 19, 20,
    ]);
    expect(lanes.find((lane) => lane.lane === "bottom")?.cells.map((cell) => cell.tileIndex + 1)).toEqual([
      21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
    ]);
    expect(lanes.find((lane) => lane.lane === "left")?.cells.map((cell) => cell.tileIndex + 1)).toEqual([
      32, 33, 34, 35, 36, 37, 38, 39, 40,
    ]);
  });

  it("keeps lane-owned visual strip centers on the four diamond sides", () => {
    const lanes = quarterviewLaneModels(40, "ring");
    const top = lanes.find((lane) => lane.lane === "top");
    const right = lanes.find((lane) => lane.lane === "right");
    const bottom = lanes.find((lane) => lane.lane === "bottom");
    const left = lanes.find((lane) => lane.lane === "left");

    expect(top?.centerXPercent).toBeGreaterThan(50);
    expect(top?.centerYPercent).toBeLessThan(50);
    expect(right?.centerXPercent).toBeGreaterThan(50);
    expect(right?.centerYPercent).toBeGreaterThan(50);
    expect(bottom?.centerXPercent).toBeLessThan(50);
    expect(bottom?.centerYPercent).toBeGreaterThan(50);
    expect(left?.centerXPercent).toBeLessThan(50);
    expect(left?.centerYPercent).toBeLessThan(50);
  });

  it("builds one projected polygon per ring tile without lane guide ownership", () => {
    const polygons = quarterviewTilePolygons(40, "ring");
    expect(polygons).toHaveLength(40);
    expect(polygons.every((polygon) => polygon.points.length === 4)).toBe(true);
    expect(polygons.every((polygon) => polygon.bboxWidth > 0 && polygon.bboxHeight > 0)).toBe(true);
    expect(
      polygons.every((polygon) =>
        Object.values(polygon.contentTransform).every((value) => Number.isFinite(value))
      )
    ).toBe(true);
    expect(polygons.map((polygon) => polygon.tileIndex).sort((a, b) => a - b)).toEqual(
      Array.from({ length: 40 }, (_, i) => i)
    );
    expect(Math.min(...polygons.flatMap((polygon) => polygon.points.map((point) => point.x)))).toBeGreaterThanOrEqual(0);
    expect(Math.max(...polygons.flatMap((polygon) => polygon.points.map((point) => point.x)))).toBeLessThanOrEqual(1000);
    expect(Math.min(...polygons.flatMap((polygon) => polygon.points.map((point) => point.y)))).toBeGreaterThanOrEqual(0);
    expect(Math.max(...polygons.flatMap((polygon) => polygon.points.map((point) => point.y)))).toBeLessThanOrEqual(1000);
  });

  it("projects line tiles into quarterview points without changing order", () => {
    const projected = Array.from({ length: 4 }, (_, i) => projectTileQuarterview(i, 4, "line"));
    expect(projected.map((p) => p.lane)).toEqual(["line", "line", "line", "line"]);
    expect(projected.map((p) => p.xPercent)).toEqual([...projected.map((p) => p.xPercent)].sort((a, b) => a - b));
    expect(projected.every((p) => p.yPercent === 50)).toBe(true);
  });

  it("maps quarterview lanes to stable idle facings", () => {
    expect(quarterviewFacingForLane("top")).toBe("back-right");
    expect(quarterviewFacingForLane("right")).toBe("front-right");
    expect(quarterviewFacingForLane("bottom")).toBe("front-left");
    expect(quarterviewFacingForLane("left")).toBe("back-left");
  });

  it("splits top and bottom idle facings by diamond side", () => {
    expect(quarterviewIdleFacingForPosition({ lane: "top", xPercent: 35 })).toBe("back-left");
    expect(quarterviewIdleFacingForPosition({ lane: "top", xPercent: 65 })).toBe("back-right");
    expect(quarterviewIdleFacingForPosition({ lane: "bottom", xPercent: 35 })).toBe("front-right");
    expect(quarterviewIdleFacingForPosition({ lane: "bottom", xPercent: 65 })).toBe("front-left");
  });

  it("maps tile steps to the matching quarterview movement facing", () => {
    expect(quarterviewFacingForTileStep(0, 1, 40, "ring")).toBe("front-right");
    expect(quarterviewFacingForTileStep(10, 11, 40, "ring")).toBe("front-left");
    expect(quarterviewFacingForTileStep(20, 21, 40, "ring")).toBe("back-left");
    expect(quarterviewFacingForTileStep(30, 31, 40, "ring")).toBe("back-right");
  });

  it("keeps idle standees facing the clockwise next tile direction", () => {
    expect(quarterviewIdleFacingForTile(8, 40, "ring")).toBe("front-right");
    expect(quarterviewIdleFacingForTile(10, 40, "ring")).toBe("front-left");
    expect(quarterviewIdleFacingForTile(20, 40, "ring")).toBe("back-left");
    expect(quarterviewIdleFacingForTile(30, 40, "ring")).toBe("back-right");
  });
});
