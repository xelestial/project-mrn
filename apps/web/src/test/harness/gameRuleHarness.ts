import * as fc from "fast-check";

export { fc };

export type RuleInvariant<Model> = {
  name: string;
  assert: (model: Model, history: readonly unknown[]) => void;
};

export type RuleHarness<Model, Step, Scenario = undefined> = {
  name: string;
  scenario?: fc.Arbitrary<Scenario>;
  initialModel: (scenario: Scenario) => Model;
  step: fc.Arbitrary<Step>;
  applyStep: (model: Model, step: Step) => Model;
  invariants: readonly RuleInvariant<Model>[];
};

export type RuleHarnessOptions = {
  maxSteps?: number;
  numRuns?: number;
  seed?: number;
};

export function runRuleHarness<Model, Step, Scenario = undefined>(
  harness: RuleHarness<Model, Step, Scenario>,
  options: RuleHarnessOptions = {},
): void {
  const maxSteps = options.maxSteps ?? 64;
  const scenarioArbitrary = harness.scenario ?? fc.constant(undefined as Scenario);
  const historyArbitrary = fc.array(harness.step, { maxLength: maxSteps });

  fc.assert(
    fc.property(scenarioArbitrary, historyArbitrary, (scenario, steps) => {
      let model = harness.initialModel(scenario);
      harness.invariants.forEach((invariant) => invariant.assert(model, []));

      steps.forEach((step, index) => {
        model = harness.applyStep(model, step);
        const history = steps.slice(0, index + 1);
        harness.invariants.forEach((invariant) => invariant.assert(model, history));
      });
    }),
    {
      numRuns: options.numRuns,
      seed: options.seed,
      verbose: true,
    },
  );
}
