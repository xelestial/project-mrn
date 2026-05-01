export type PlayerId = number;

export type PurchaseInput = {
  buyerId: PlayerId;
  buyerCash: number;
  purchaseCost: number;
  tileOwnerId: PlayerId | null;
  freePurchase?: boolean;
  freePurchaseConsumption?: string;
};

export type PurchaseResult = {
  status: "purchased" | "blocked";
  blockedReason: "already_owned" | "insufficient_cash" | null;
  baseCost: number;
  finalCost: number;
  nextBuyerCash: number;
  nextOwnerId: PlayerId | null;
  consumptions: string[];
};

export type RentPaymentInput = {
  payerCash: number;
  ownerCash: number;
  rent: number;
};

export type RentPaymentResult = {
  status: "paid" | "bankrupt";
  rentDue: number;
  paidAmount: number;
  nextPayerCash: number;
  nextOwnerCash: number;
};

function toNonNegativeInteger(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.max(0, Math.trunc(value));
}

export function resolvePurchase(input: PurchaseInput): PurchaseResult {
  const buyerCash = toNonNegativeInteger(input.buyerCash);
  const baseCost = toNonNegativeInteger(input.purchaseCost);
  const finalCost = input.freePurchase ? 0 : baseCost;

  if (input.tileOwnerId !== null) {
    return {
      status: "blocked",
      blockedReason: "already_owned",
      baseCost,
      finalCost,
      nextBuyerCash: buyerCash,
      nextOwnerId: input.tileOwnerId,
      consumptions: [],
    };
  }

  if (buyerCash < finalCost) {
    return {
      status: "blocked",
      blockedReason: "insufficient_cash",
      baseCost,
      finalCost,
      nextBuyerCash: buyerCash,
      nextOwnerId: null,
      consumptions: [],
    };
  }

  return {
    status: "purchased",
    blockedReason: null,
    baseCost,
    finalCost,
    nextBuyerCash: buyerCash - finalCost,
    nextOwnerId: input.buyerId,
    consumptions:
      input.freePurchase && input.freePurchaseConsumption
        ? [input.freePurchaseConsumption]
        : [],
  };
}

export function resolveRentPayment(input: RentPaymentInput): RentPaymentResult {
  const payerCash = toNonNegativeInteger(input.payerCash);
  const ownerCash = toNonNegativeInteger(input.ownerCash);
  const rentDue = toNonNegativeInteger(input.rent);
  const paidAmount = Math.min(payerCash, rentDue);

  return {
    status: paidAmount < rentDue ? "bankrupt" : "paid",
    rentDue,
    paidAmount,
    nextPayerCash: payerCash - paidAmount,
    nextOwnerCash: ownerCash + paidAmount,
  };
}
