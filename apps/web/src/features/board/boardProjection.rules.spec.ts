import { describe, expect, it } from "vitest";
import { fc, runRuleHarness, type RuleHarness } from "../../test/harness/gameRuleHarness";
import { tileCountArbitrary, topologyArbitrary } from "../../test/harness/gameRuleArbitraries";
import {
  boardGridForTileCount,
  boardSizeForTileCount,
  projectTilePosition,
  projectTileQuarterview,
  quarterviewLaneModels,
  ringPosition,
  type BoardTopology,
} from "./boardProjection";

type BoardScenario = {
  tileCount: number;
  topology: BoardTopology;
};

type BoardModel = BoardScenario & {
  projectedTileIndices: number[];
};

describe("boardProjection rule harness", () => {
  it("keeps generated board positions inside legal topology bounds", () => {
    const harness: RuleHarness<BoardModel, number, BoardScenario> = {
      name: "board topology projection",
      scenario: fc.record({
        tileCount: tileCountArbitrary,
        topology: topologyArbitrary,
      }),
      initialModel: (scenario) => ({ ...scenario, projectedTileIndices: [] }),
      step: fc.integer({ min: -160, max: 160 }),
      applyStep: (model, tileIndex) => ({
        ...model,
        projectedTileIndices: [...model.projectedTileIndices, tileIndex],
      }),
      invariants: [
        {
          name: "grid dimensions match topology",
          assert: (model) => {
            const grid = boardGridForTileCount(model.tileCount, model.topology);
            if (model.topology === "line") {
              expect(grid.rows).toBe(1);
              expect(grid.cols).toBe(Math.max(1, model.tileCount));
            } else {
              expect(grid.rows).toBe(grid.cols);
              expect(grid.boardSize).toBeGreaterThanOrEqual(5);
            }
          },
        },
        {
          name: "projected positions stay on the board",
          assert: (model) => {
            for (const tileIndex of model.projectedTileIndices) {
              const position = projectTilePosition(tileIndex, model.tileCount, model.topology);
              expect(position.row).toBeGreaterThanOrEqual(1);
              expect(position.col).toBeGreaterThanOrEqual(1);
              expect(position.row).toBeLessThanOrEqual(position.boardSize);
              expect(position.col).toBeLessThanOrEqual(position.boardSize);
              if (model.topology === "line") {
                expect(position.row).toBe(1);
              } else {
                expect(position.row === 1 || position.row === position.boardSize || position.col === 1 || position.col === position.boardSize).toBe(true);
              }
            }
          },
        },
        {
          name: "quarterview projection stays inside the percent canvas",
          assert: (model) => {
            for (const tileIndex of model.projectedTileIndices) {
              const point = projectTileQuarterview(tileIndex, model.tileCount, model.topology);
              expect(point.xPercent).toBeGreaterThanOrEqual(0);
              expect(point.xPercent).toBeLessThanOrEqual(100);
              expect(point.yPercent).toBeGreaterThanOrEqual(0);
              expect(point.yPercent).toBeLessThanOrEqual(100);
              expect(Number.isFinite(point.zIndex)).toBe(true);
            }
          },
        },
      ],
    };

    runRuleHarness(harness, { maxSteps: 48, numRuns: 100, seed: 20260430 });
  });

  it("keeps ring tile coordinates unique for every generated board size", () => {
    fc.assert(
      fc.property(tileCountArbitrary, (tileCount) => {
        const boardSize = boardSizeForTileCount(tileCount, "ring");
        const coordinates = new Set<string>();
        for (let tileIndex = 0; tileIndex < tileCount; tileIndex += 1) {
          const position = ringPosition(tileIndex, boardSize);
          coordinates.add(`${position.row}:${position.col}`);
        }
        expect(coordinates.size).toBe(tileCount);
      }),
      { numRuns: 100, seed: 20260430 },
    );
  });

  it("assigns each generated ring tile to exactly one quarterview lane cell", () => {
    fc.assert(
      fc.property(tileCountArbitrary, (tileCount) => {
        const tileIndices = quarterviewLaneModels(tileCount, "ring")
          .flatMap((lane) => lane.cells.map((cell) => cell.tileIndex))
          .sort((left, right) => left - right);

        expect(tileIndices).toEqual(Array.from({ length: tileCount }, (_, index) => index));
      }),
      { numRuns: 100, seed: 20260430 },
    );
  });
});
