export type LegalChoice = {
  choice_id: string;
  [key: string]: unknown;
};

export type LegalChoiceResolution =
  | {
      status: "accepted";
      choice: LegalChoice;
    }
  | {
      status: "rejected";
      reason: "missing_choice_id" | "illegal_choice";
    };

export function resolveLegalChoice(
  legalChoices: readonly LegalChoice[],
  choiceId: string | null | undefined,
): LegalChoiceResolution {
  if (!choiceId) {
    return {
      status: "rejected",
      reason: "missing_choice_id",
    };
  }

  const choice = legalChoices.find(
    (legalChoice) => legalChoice.choice_id === choiceId,
  );

  if (!choice) {
    return {
      status: "rejected",
      reason: "illegal_choice",
    };
  }

  return {
    status: "accepted",
    choice,
  };
}
