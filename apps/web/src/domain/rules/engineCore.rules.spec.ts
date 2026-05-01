import { describe, expect, it } from "vitest";

import {
  applyForwardMove,
  normalizeTileIndex,
  resolveLegalChoice,
  resolvePurchase,
  resolveRentPayment,
} from "../../../../../packages/engine-core/src";
import { fc, runRuleHarness } from "../../test/harness/gameRuleHarness";
import { tileCountArbitrary } from "../../test/harness/gameRuleArbitraries";

type MovementScenario = {
  tileCount: number;
  fromTileIndex: number;
};

type MovementModel = {
  tileCount: number;
  initialTileIndex: number;
  currentTileIndex: number;
  totalSteps: number;
  crossedLaps: number;
  traversedTileIndices: number[];
};

type PublicMutationKind =
  | "none"
  | "ownership_transfer"
  | "cash_transfer"
  | "marker_transfer"
  | "queued_effect_action";

type PublicEffectSource = "fortune" | "trick" | "weather";

type PublicMutationStep = {
  mutationKind: PublicMutationKind;
  effectSource: PublicEffectSource;
  actorPlayerId: number;
  tileIndex: number;
  amount: number;
};

type PublicEvent = {
  event_type: string;
  summary?: string;
  action_result?: boolean;
  resolution?: {
    type?: string;
  };
};

type PublicMutationModel = {
  ownerByTile: (number | null)[];
  cashByPlayer: number[];
  markerOwnerId: number;
  events: PublicEvent[];
  changedSinceLastAnnouncement: boolean;
};

const eventByEffectSource: Record<PublicEffectSource, string> = {
  fortune: "fortune_resolved",
  trick: "trick_used",
  weather: "weather_reveal",
};

const movementScenarioArbitrary = tileCountArbitrary.chain((tileCount) =>
  fc.record({
    tileCount: fc.constant(tileCount),
    fromTileIndex: fc.integer({ min: 0, max: tileCount - 1 }),
  }),
);

const playerIdArbitrary = fc.integer({ min: 1, max: 4 });
const resourceAmountArbitrary = fc.integer({ min: 0, max: 500 });

const choiceIdArbitrary = fc
  .integer({ min: 0, max: 10_000 })
  .map((value) => `choice_${value}`);

const publicMutationStepArbitrary: fc.Arbitrary<PublicMutationStep> = fc.record(
  {
    mutationKind: fc.constantFrom<PublicMutationKind>(
      "none",
      "ownership_transfer",
      "cash_transfer",
      "marker_transfer",
      "queued_effect_action",
    ),
    effectSource: fc.constantFrom<PublicEffectSource>(
      "fortune",
      "trick",
      "weather",
    ),
    actorPlayerId: playerIdArbitrary,
    tileIndex: fc.integer({ min: 0, max: 15 }),
    amount: resourceAmountArbitrary,
  },
);

const announcedMutationEvents = new Set([
  "tile_purchased",
  "rent_paid",
  "marker_transferred",
  "player_move",
  "action_move",
  "bankruptcy",
  "fortune_resolved",
  "trick_used",
  "weather_reveal",
]);

function isAnnouncingEvent(event: PublicEvent | undefined): boolean {
  if (!event || !announcedMutationEvents.has(event.event_type)) {
    return false;
  }
  if (event.event_type === "fortune_resolved" && event.action_result !== true) {
    return false;
  }
  return typeof event.summary === "string" && event.summary.trim().length > 0;
}

function applyPublicMutationStep(
  model: PublicMutationModel,
  step: PublicMutationStep,
): PublicMutationModel {
  if (step.mutationKind === "none") {
    return {
      ...model,
      events: [...model.events, { event_type: "turn_end_snapshot" }],
      changedSinceLastAnnouncement: false,
    };
  }

  if (step.mutationKind === "ownership_transfer") {
    const ownerByTile = [...model.ownerByTile];
    ownerByTile[step.tileIndex] = step.actorPlayerId;
    return {
      ...model,
      ownerByTile,
      events: [
        ...model.events,
        {
          event_type: "tile_purchased",
          summary: `P${step.actorPlayerId} bought tile ${step.tileIndex + 1}`,
        },
      ],
      changedSinceLastAnnouncement: false,
    };
  }

  if (step.mutationKind === "cash_transfer") {
    const cashByPlayer = [...model.cashByPlayer];
    const payerIndex = (step.actorPlayerId - 1) % cashByPlayer.length;
    const ownerIndex = step.actorPlayerId % cashByPlayer.length;
    const paidAmount = Math.min(cashByPlayer[payerIndex], step.amount);
    cashByPlayer[payerIndex] -= paidAmount;
    cashByPlayer[ownerIndex] += paidAmount;
    return {
      ...model,
      cashByPlayer,
      events: [
        ...model.events,
        {
          event_type: "rent_paid",
          summary: `P${step.actorPlayerId} paid ${paidAmount}`,
        },
      ],
      changedSinceLastAnnouncement: false,
    };
  }

  if (step.mutationKind === "marker_transfer") {
    return {
      ...model,
      markerOwnerId: step.actorPlayerId,
      events: [
        ...model.events,
        {
          event_type: "marker_transferred",
          summary: `Marker moved to P${step.actorPlayerId}`,
        },
      ],
      changedSinceLastAnnouncement: false,
    };
  }

  const ownerByTile = [...model.ownerByTile];
  ownerByTile[step.tileIndex] = step.actorPlayerId;
  const eventType = eventByEffectSource[step.effectSource];
  return {
    ...model,
    ownerByTile,
    events: [
      ...model.events,
      {
        event_type: eventType,
        action_result: step.effectSource === "fortune" ? true : undefined,
        resolution: { type: "VISIBLE_EFFECT_MUTATION" },
        summary: `${step.effectSource} changed ownership of tile ${step.tileIndex + 1}`,
      },
    ],
    changedSinceLastAnnouncement: false,
  };
}

describe("engine-core rule primitives", () => {
  it("moves forward around generated boards without losing normalization or lap counts", () => {
    runRuleHarness<MovementModel, number, MovementScenario>(
      {
        name: "forward movement",
        scenario: movementScenarioArbitrary,
        step: fc.integer({ min: 0, max: 48 }),
        initialModel: (scenario) => ({
          tileCount: scenario.tileCount,
          initialTileIndex: scenario.fromTileIndex,
          currentTileIndex: scenario.fromTileIndex,
          totalSteps: 0,
          crossedLaps: 0,
          traversedTileIndices: [],
        }),
        applyStep: (model, steps) => {
          const result = applyForwardMove({
            fromTileIndex: model.currentTileIndex,
            steps,
            tileCount: model.tileCount,
          });

          return {
            ...model,
            currentTileIndex: result.toTileIndex,
            totalSteps: model.totalSteps + result.steps,
            crossedLaps: model.crossedLaps + result.lapCount,
            traversedTileIndices: [
              ...model.traversedTileIndices,
              ...result.pathTileIndices,
            ],
          };
        },
        invariants: [
          {
            name: "position stays on board",
            assert: (model) => {
              expect(model.currentTileIndex).toBeGreaterThanOrEqual(0);
              expect(model.currentTileIndex).toBeLessThan(model.tileCount);
            },
          },
          {
            name: "path length matches total steps",
            assert: (model) => {
              expect(model.traversedTileIndices).toHaveLength(model.totalSteps);
            },
          },
          {
            name: "every traversed tile is normalized",
            assert: (model) => {
              model.traversedTileIndices.forEach((tileIndex) => {
                expect(tileIndex).toBeGreaterThanOrEqual(0);
                expect(tileIndex).toBeLessThan(model.tileCount);
              });
            },
          },
          {
            name: "cumulative lap count matches arithmetic distance",
            assert: (model) => {
              expect(model.crossedLaps).toBe(
                Math.floor(
                  (model.initialTileIndex + model.totalSteps) / model.tileCount,
                ),
              );
            },
          },
        ],
      },
      { seed: 6_103, numRuns: 80, maxSteps: 24 },
    );
  });

  it("normalizes tile indices with modulo semantics", () => {
    fc.assert(
      fc.property(
        tileCountArbitrary,
        fc.integer({ min: -1_000, max: 1_000 }),
        (tileCount, tileIndex) => {
          const normalized = normalizeTileIndex(tileIndex, tileCount);

          expect(normalized).toBeGreaterThanOrEqual(0);
          expect(normalized).toBeLessThan(tileCount);
          expect(normalizeTileIndex(normalized, tileCount)).toBe(normalized);
        },
      ),
      { seed: 6_104, numRuns: 120 },
    );
  });

  it("resolves purchases without creating invalid balances or consuming failed discounts", () => {
    fc.assert(
      fc.property(
        fc.record({
          buyerId: playerIdArbitrary,
          buyerCash: resourceAmountArbitrary,
          purchaseCost: resourceAmountArbitrary,
          tileOwnerId: fc.option(playerIdArbitrary, { nil: null }),
          freePurchase: fc.boolean(),
        }),
        (input) => {
          const result = resolvePurchase({
            ...input,
            freePurchaseConsumption: "trick_free_purchase_this_turn",
          });

          expect(result.nextBuyerCash).toBeGreaterThanOrEqual(0);
          expect(result.finalCost).toBe(
            input.freePurchase ? 0 : input.purchaseCost,
          );

          if (result.status === "purchased") {
            expect(result.nextOwnerId).toBe(input.buyerId);
            expect(result.nextBuyerCash).toBe(
              input.buyerCash - result.finalCost,
            );
            expect(result.consumptions).toEqual(
              input.freePurchase ? ["trick_free_purchase_this_turn"] : [],
            );
          } else {
            expect(result.nextBuyerCash).toBe(input.buyerCash);
            expect(result.nextOwnerId).toBe(input.tileOwnerId);
            expect(result.consumptions).toEqual([]);
          }
        },
      ),
      { seed: 6_105, numRuns: 160 },
    );
  });

  it("resolves rent payments as bounded transfers and emits bankruptcy explicitly", () => {
    fc.assert(
      fc.property(
        fc.record({
          payerCash: resourceAmountArbitrary,
          ownerCash: resourceAmountArbitrary,
          rent: resourceAmountArbitrary,
        }),
        (input) => {
          const result = resolveRentPayment(input);
          const expectedPaidAmount = Math.min(input.payerCash, input.rent);

          expect(result.paidAmount).toBe(expectedPaidAmount);
          expect(result.nextPayerCash).toBe(
            input.payerCash - expectedPaidAmount,
          );
          expect(result.nextOwnerCash).toBe(
            input.ownerCash + expectedPaidAmount,
          );
          expect(result.nextPayerCash).toBeGreaterThanOrEqual(0);
          expect(result.status).toBe(
            input.payerCash < input.rent ? "bankrupt" : "paid",
          );
        },
      ),
      { seed: 6_106, numRuns: 160 },
    );
  });

  it("accepts only generated prompt choices present in legal_choices", () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(choiceIdArbitrary, { minLength: 1, maxLength: 8 }),
        choiceIdArbitrary,
        (choiceIds, candidateChoiceId) => {
          const legalChoices = choiceIds.map((choiceId) => ({
            choice_id: choiceId,
            label: `Choice ${choiceId}`,
          }));
          const legalChoiceId = choiceIds[0];

          expect(resolveLegalChoice(legalChoices, legalChoiceId)).toMatchObject(
            {
              status: "accepted",
              choice: { choice_id: legalChoiceId },
            },
          );

          const illegalChoiceId = choiceIds.includes(candidateChoiceId)
            ? `${candidateChoiceId}_missing`
            : candidateChoiceId;

          expect(resolveLegalChoice(legalChoices, illegalChoiceId)).toEqual({
            status: "rejected",
            reason: "illegal_choice",
          });
        },
      ),
      { seed: 6_107, numRuns: 160 },
    );
  });

  it("announces every user-visible mutation instead of relying on silent snapshot diffs", () => {
    runRuleHarness<PublicMutationModel, PublicMutationStep>(
      {
        name: "public mutation visibility",
        step: publicMutationStepArbitrary,
        initialModel: () => ({
          ownerByTile: Array.from({ length: 16 }, () => null),
          cashByPlayer: Array.from({ length: 4 }, () => 500),
          markerOwnerId: 1,
          events: [],
          changedSinceLastAnnouncement: false,
        }),
        applyStep: applyPublicMutationStep,
        invariants: [
          {
            name: "mutating transitions are announced",
            assert: (model) => {
              expect(model.changedSinceLastAnnouncement).toBe(false);
              const lastEvent = model.events.at(-1);
              if (!lastEvent) {
                return;
              }
              if (lastEvent?.event_type === "turn_end_snapshot") {
                return;
              }
              expect(isAnnouncingEvent(lastEvent)).toBe(true);
            },
          },
        ],
      },
      { seed: 6_108, numRuns: 120, maxSteps: 24 },
    );
  });
});
