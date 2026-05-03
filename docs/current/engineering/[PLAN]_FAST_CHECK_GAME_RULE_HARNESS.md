# fast-check Game Rule Harness Plan

## Goal

Use property-based tests to protect game rules from example-only blind spots.
The harness should make rules testable as pure model transitions:

1. Generate a scenario.
2. Generate a sequence of player/system steps.
3. Apply steps through a small rule adapter.
4. Assert invariants after the initial state and every step.

## Harness Shape

The web test harness lives at `apps/web/src/test/harness/gameRuleHarness.ts`.

- `scenario`: optional `fast-check` arbitrary for board setup, catalog fixture, player count, or manifest parameters.
- `initialModel`: builds the test model from the scenario.
- `step`: arbitrary for generated rule actions.
- `applyStep`: pure transition from model and step to next model.
- `invariants`: named assertions that must hold after every transition.

This keeps rule tests focused on behavior instead of one-off fixtures. When a property fails, fast-check shrinks the scenario and step history to a small reproducible case.

## First Coverage

Initial rule coverage is intentionally low-risk and tied to current pure domain code:

- Board topology rules:
  - ring and line board grids stay within legal dimensions
  - projected positions remain on the board
  - ring coordinates remain unique for generated tile counts
  - quarterview lane ownership assigns every ring tile exactly once
- Character priority-slot rules:
  - every catalog face and alias maps back to its owning slot
  - opposite-face lookup stays inside the same character card
  - priority owner lookup remains stable when the active face changes

## Expansion Plan

1. Extract engine-core rule primitives.
   - Move movement, dice, rent, purchase, lap reward, weather, and trick-card effects into pure functions under `packages/engine-core`.
   - Keep adapters thin so UI/server tests can reuse the same rule model.

2. Add stateful command harnesses.
   - Movement: generated dice totals and board topologies preserve normalized positions and lap crossings.
   - Economy: generated purchases/rent/lap rewards never create invalid balances unless bankruptcy is explicitly emitted.
   - Prompt legality: generated prompts only accept choices present in `legal_choices`.
   - Visibility:
     - generated private/public events never leak private hand or hidden character state.
     - every user-visible state mutation must have a public announcement event. Ownership transfers, cash transfers, marker ownership changes, movement, purchases, rent, bankruptcy, and queued card/effect action results may not silently appear only as a later snapshot diff.
     - user-visible `운수`, `잔꾀`, and `날씨` effects are one checklist family: if the effect changes ownership, cash, markers, position, purchase/rent state, bankruptcy, or any other board-visible/public state, the stream must publish an event with a human-readable `summary` for the effect result.
     - decision-bearing `운수` actions such as `땅 도둑`, donation/give-tile, forced trade, subscription purchase, and pious marker tile gain must emit an action-result `fortune_resolved` event with a human-readable `summary` after the queued action mutates state.
     - `잔꾀` effects that mutate public state must surface through `trick_used` with a readable effect/result summary, not only through the later board snapshot.
     - `날씨` effects that mutate public state must surface through `weather_reveal` or a paired weather result event with a readable effect/result summary, not only through the later board snapshot.

3. Add contract-backed arbitraries.
   - Generate scenarios from runtime-contract fixture schemas.
   - Mix fixture examples with generated edge cases to keep compatibility with backend projections.

4. Run in CI with two tiers.
   - PR tier: fixed seeds and moderate `numRuns` for deterministic speed.
   - Nightly tier: more runs and rotating seeds to search wider state space.

## Conventions

- Keep seeds explicit in committed specs.
- Prefer small arbitrary ranges first, then widen once failures are understandable.
- Put reusable generators in `apps/web/src/test/harness/gameRuleArbitraries.ts`.
- Name each invariant after the game rule it protects.
- Name visibility invariants from the user-facing symptom they prevent, for example `mutating transitions are announced`.
- When a property finds a bug, keep the shrunk counterexample as a normal example test next to the property.
