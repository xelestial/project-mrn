import { describe, expect, it } from "vitest";
import { fc, runRuleHarness, type RuleHarness } from "./gameRuleHarness";

type CounterModel = {
  value: number;
};

describe("gameRuleHarness", () => {
  it("runs generated rule steps and reports invariant violations", () => {
    const harness: RuleHarness<CounterModel, number> = {
      name: "counter never leaves the generated range",
      initialModel: () => ({ value: 0 }),
      step: fc.integer({ min: -3, max: 3 }),
      applyStep: (model, step) => ({ value: model.value + step }),
      invariants: [
        {
          name: "counter stays finite",
          assert: (model) => {
            expect(Number.isFinite(model.value)).toBe(true);
          },
        },
      ],
    };

    runRuleHarness(harness, { maxSteps: 16, numRuns: 20, seed: 20260430 });
  });
});
