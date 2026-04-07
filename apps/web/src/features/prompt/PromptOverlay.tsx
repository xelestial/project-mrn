import { KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { PromptChoiceViewModel, PromptViewModel } from "../../domain/selectors/promptSelectors";
import { promptHelperForType } from "../../domain/labels/promptHelperCatalog";
import { promptLabelForType } from "../../domain/labels/promptTypeCatalog";
import type { LocaleMessages } from "../../i18n/types";
import { useI18n } from "../../i18n/useI18n";
import { isSpecializedPromptType } from "./promptSurfaceCatalog";

type PromptOverlayProps = {
  prompt: PromptViewModel | null;
  collapsed: boolean;
  busy: boolean;
  secondsLeft: number | null;
  feedbackMessage?: string;
  compactChoices?: boolean;
  onToggleCollapse: () => void;
  onSelectChoice: (choiceId: string) => void;
};

type PromptText = LocaleMessages["prompt"];
type PromptTypeText = LocaleMessages["promptType"];
type PromptHelperText = LocaleMessages["promptHelper"];

type MovementChoiceParts = {
  rollChoice: PromptChoiceViewModel | null;
  cardChoices: Array<{ cards: number[]; choice: PromptChoiceViewModel }>;
  cardPool: number[];
  canUseTwoCards: boolean;
};

type HandChoiceCard = {
  key: string;
  name: string;
  description: string;
  isHidden: boolean;
  isUsable: boolean;
  choiceId: string | null;
};

type ChoiceGridVariant = "default" | "target" | "decision" | "reward";
type SummaryPillValue = string | null | undefined;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function cleanDisplayText(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith("[") && trimmed.endsWith("]") && trimmed.length >= 2) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function sortChoicesForDisplay(choices: PromptChoiceViewModel[]): PromptChoiceViewModel[] {
  return [...choices].sort((left, right) => {
    const leftIsPass = left.choiceId === "none";
    const rightIsPass = right.choiceId === "none";
    if (leftIsPass === rightIsPass) {
      return 0;
    }
    return leftIsPass ? 1 : -1;
  });
}

function choiceDescription(choice: PromptChoiceViewModel, promptText: PromptText): string {
  const text = choice.description.trim();
  return text ? cleanDisplayText(text) : promptText.noChoiceDescription;
}

function parseMovementChoice(choice: PromptChoiceViewModel): { cards: number[] } | null {
  const value = choice.value ?? {};
  const fromValue = Array.isArray(value["card_values"])
    ? value["card_values"].map((item) => Number(item)).filter((item) => Number.isFinite(item))
    : [];
  if (fromValue.length > 0) {
    return { cards: [...fromValue].sort((a, b) => a - b) };
  }

  const match = /^(?:card|dice)_(\d+)(?:_(\d+))?$/.exec(choice.choiceId);
  if (!match) {
    return null;
  }

  const first = Number(match[1]);
  const second = match[2] ? Number(match[2]) : null;
  if (!Number.isFinite(first)) {
    return null;
  }

  const cards = [first, ...(second !== null && Number.isFinite(second) ? [second] : [])].sort((a, b) => a - b);
  return { cards };
}

function numberFromContext(context: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const parsed = asNumber(context[key]);
    if (parsed !== null) {
      return parsed;
    }
  }
  return null;
}

function stringFromContext(context: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const parsed = asString(context[key]);
    if (parsed) {
      return parsed;
    }
  }
  return "";
}

function tileLabel(tileIndex: number | null): string {
  return tileIndex === null ? "-" : String(tileIndex + 1);
}

function formatNumber(value: number | null): string {
  return value === null ? "-" : String(value);
}

function booleanFromValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function collapsedPromptChip(promptText: PromptText, label: string, secondsLeft: number | null): string {
  return promptText.collapsedChip(label, secondsLeft);
}

function nonEmptyPills(values: Array<string | null | undefined>): string[] {
  return values
    .map((value) => (typeof value === "string" ? value.trim() : ""))
    .filter((value) => value.length > 0 && value !== "-");
}

function SummaryPills({ values }: { values: SummaryPillValue[] }) {
  const pills = nonEmptyPills(values);
  if (pills.length === 0) {
    return null;
  }
  return (
    <div className="prompt-summary-pill-row">
      {pills.map((pill) => (
        <span key={pill} className="prompt-summary-pill">
          {pill}
        </span>
      ))}
    </div>
  );
}

function choiceGridClass(variant: ChoiceGridVariant, compactChoices: boolean): string {
  const base = ["prompt-choices"];
  if (variant !== "default") {
    base.push(`prompt-choices-${variant}`);
  }
  if (compactChoices) {
    base.push("prompt-choices-compact");
  }
  return base.join(" ");
}

function isSecondaryChoice(choice: PromptChoiceViewModel): boolean {
  return choice.secondary;
}

function movementChoices(prompt: PromptViewModel): MovementChoiceParts {
  let rollChoice: PromptChoiceViewModel | null = null;
  const cardChoices: Array<{ cards: number[]; choice: PromptChoiceViewModel }> = [];
  const cardSet = new Set<number>();

  for (const choice of prompt.choices) {
    const parsed = parseMovementChoice(choice);
    if (parsed) {
      parsed.cards.forEach((card) => cardSet.add(card));
      cardChoices.push({ cards: parsed.cards, choice });
      continue;
    }

    const isRoll =
      choice.choiceId === "dice" ||
      choice.choiceId === "roll" ||
      /roll/i.test(choice.choiceId) ||
      choice.title.toLowerCase().includes("dice");

    if (isRoll) {
      rollChoice = choice;
    }
  }

  const cardPool = Array.from(cardSet).sort((a, b) => a - b);
  const canUseTwoCards = cardChoices.some((item) => item.cards.length === 2);
  return { rollChoice, cardChoices, cardPool, canUseTwoCards };
}

function findCardChoice(
  candidates: Array<{ cards: number[]; choice: PromptChoiceViewModel }>,
  selectedCards: number[]
): PromptChoiceViewModel | null {
  const sorted = [...selectedCards].sort((a, b) => a - b);
  return candidates.find((item) => item.cards.join(",") === sorted.join(","))?.choice ?? null;
}

function buildHandChoiceCards(prompt: PromptViewModel, promptText: PromptText): { cards: HandChoiceCard[]; passChoiceId: string | null } {
  const choiceByDeck = new Map<number, PromptChoiceViewModel>();
  let passChoiceId: string | null = null;

  for (const choice of prompt.choices) {
    if (choice.choiceId === "none") {
      passChoiceId = choice.choiceId;
      continue;
    }
    const deckIndex = asNumber(choice.value?.["deck_index"]);
    if (deckIndex !== null) {
      choiceByDeck.set(deckIndex, choice);
      continue;
    }
    const numericChoice = Number(choice.choiceId);
    if (Number.isFinite(numericChoice)) {
      choiceByDeck.set(numericChoice, choice);
    }
  }

  const contextHand = Array.isArray(prompt.publicContext["full_hand"]) ? prompt.publicContext["full_hand"] : [];
  if (contextHand.length > 0) {
    const cards = contextHand
      .map((item, index) => {
        if (!isRecord(item)) {
          return null;
        }
        const deckIndex = asNumber(item["deck_index"]);
        const name = asString(item["name"], promptText.hiddenCardName);
        const description = asString(item["card_description"], promptText.hiddenCardDescription(name));
        const isHidden = Boolean(item["is_hidden"]);
        const linkedChoice = deckIndex === null ? null : choiceByDeck.get(deckIndex) ?? null;
        const isUsable = linkedChoice !== null && Boolean(item["is_usable"] ?? true);
        return {
          key: `${deckIndex ?? "x"}-${index}`,
          name,
          description,
          isHidden,
          isUsable,
          choiceId: linkedChoice?.choiceId ?? null,
        };
      })
      .filter((item): item is HandChoiceCard => item !== null);
    return { cards, passChoiceId };
  }

  const cards = prompt.choices
    .filter((choice) => choice.choiceId !== "none")
    .map((choice, index) => ({
      key: `${choice.choiceId}-${index}`,
      name: choice.title,
      description: choiceDescription(choice, promptText),
      isHidden: false,
      isUsable: true,
      choiceId: choice.choiceId,
    }));

  return { cards, passChoiceId };
}

function characterAbilityText(choice: PromptChoiceViewModel, promptText: PromptText): string {
  const fromValue =
    asString(choice.value?.["character_ability"]) ||
    asString(choice.value?.["ability_text"]) ||
    asString(choice.value?.["card_description"]);

  if (fromValue) {
    return cleanDisplayText(fromValue);
  }
  if (choice.description.trim()) {
    return cleanDisplayText(choice.description.trim());
  }
  return cleanDisplayText(promptText.character.ability(choice.title));
}

function markChoiceTitle(choice: PromptChoiceViewModel, promptText: PromptText): string {
  if (choice.choiceId === "none") {
    return cleanDisplayText(promptText.mark.noneTitle);
  }
  return cleanDisplayText(promptText.mark.title(choice.title));
}

function markChoiceDescription(choice: PromptChoiceViewModel, promptText: PromptText): string {
  if (choice.choiceId === "none") {
    return cleanDisplayText(promptText.mark.noneDescription);
  }
  const targetCharacter = asString(choice.value?.["target_character"]);
  const targetPlayerId = asNumber(choice.value?.["target_player_id"]);
  if (targetCharacter && targetPlayerId !== null) {
    return cleanDisplayText(promptText.mark.description(targetCharacter, targetPlayerId));
  }
  return cleanDisplayText(promptText.mark.fallbackDescription);
}

function markChoiceTarget(choice: PromptChoiceViewModel): { character: string; playerId: number | null } {
  return {
    character: asString(choice.value?.["target_character"]),
    playerId: asNumber(choice.value?.["target_player_id"]),
  };
}

function normalizeChoiceText(
  prompt: PromptViewModel,
  choice: PromptChoiceViewModel,
  promptText: PromptText
): { title: string; description: string } {
  const fallbackTitle = choice.title.trim() ? choice.title.trim() : choice.choiceId;
  const fallbackDescription = choiceDescription(choice, promptText);
  const value = choice.value ?? {};

  if (prompt.requestType === "lap_reward") {
    const cashUnits = asNumber(value["cash_units"]) ?? 0;
    const shardUnits = asNumber(value["shard_units"]) ?? 0;
    const coinUnits = asNumber(value["coin_units"]) ?? 0;
    const spentPoints = asNumber(value["spent_points"]);
    const pointsBudget = asNumber(value["points_budget"]);
    if (cashUnits > 0 || shardUnits > 0 || coinUnits > 0) {
      return {
        title: promptText.choice.mixedReward(cashUnits, shardUnits, coinUnits, spentPoints, pointsBudget),
        description: cleanDisplayText(fallbackDescription),
      };
    }
    return { title: cleanDisplayText(fallbackTitle), description: cleanDisplayText(fallbackDescription) };
  }

  if (prompt.requestType === "purchase_tile") {
    const pos = asNumber(prompt.publicContext["tile_index"]);
    const cost = asNumber(prompt.publicContext["cost"]) ?? asNumber(prompt.publicContext["tile_purchase_cost"]);
    if (choice.choiceId === "yes") {
      return {
        title: promptText.choice.buyTileTitle,
        description: promptText.choice.buyTile(pos, cost),
      };
    }
    if (choice.choiceId === "no") {
      return { title: promptText.choice.skipPurchaseTitle, description: promptText.choice.skipPurchase };
    }
    return { title: cleanDisplayText(fallbackTitle), description: cleanDisplayText(fallbackDescription) };
  }

  if (prompt.requestType === "active_flip") {
    if (choice.choiceId === "none") {
      return { title: promptText.choice.endFlip, description: promptText.choice.endFlipDescription };
    }
    const currentName = asString(value["current_name"]);
    const flippedName = asString(value["flipped_name"]);
    if (currentName && flippedName) {
      return {
        title: promptText.choice.flipChange(currentName, flippedName),
        description: promptText.choice.flipDescription,
      };
    }
    return { title: cleanDisplayText(fallbackTitle), description: cleanDisplayText(fallbackDescription) };
  }

  if (prompt.requestType === "burden_exchange") {
    const cardName = asString(prompt.publicContext["card_name"]) || null;
    const burdenCost = asNumber(prompt.publicContext["burden_cost"]);
    const supplyThreshold = asNumber(prompt.publicContext["supply_threshold"]);
    const currentFValue = asNumber(prompt.publicContext["current_f_value"]);
    const trigger = cleanDisplayText(promptText.context.burdenExchangeTrigger(supplyThreshold, currentFValue));
    if (choice.choiceId === "yes") {
      return {
        title: promptText.choice.exchangeBurden,
        description: promptText.choice.exchangeBurdenDescription(cardName, burdenCost, trigger),
      };
    }
    if (choice.choiceId === "no") {
      return {
        title: cleanDisplayText(promptText.choice.keepBurdenTitle),
        description: cleanDisplayText(promptText.choice.keepBurdenDescription(cardName, trigger)),
      };
    }
    return { title: cleanDisplayText(fallbackTitle), description: cleanDisplayText(fallbackDescription) };
  }

  if (prompt.requestType === "trick_tile_target") {
    const tileIndex = asNumber(value["tile_index"]);
    if (tileIndex !== null) {
      return {
        title: cleanDisplayText(fallbackTitle) || tileLabel(tileIndex),
        description: cleanDisplayText(fallbackDescription),
      };
    }
  }

  return { title: cleanDisplayText(fallbackTitle), description: cleanDisplayText(fallbackDescription) };
}

type EmphasisChoiceGridProps = {
  prompt: PromptViewModel;
  orderedChoices: PromptChoiceViewModel[];
  promptText: PromptText;
  compactChoices: boolean;
  busy: boolean;
  onSelectChoice: (choiceId: string) => void;
  variant?: ChoiceGridVariant;
  testIdPrefix: string;
  renderExtra?: (choice: PromptChoiceViewModel) => ReactNode;
  collapseSecondaryChoices?: boolean;
};

function EmphasisChoiceGrid({
  prompt,
  orderedChoices,
  promptText,
  compactChoices,
  busy,
  onSelectChoice,
  variant = "default",
  testIdPrefix,
  renderExtra,
  collapseSecondaryChoices = false,
}: EmphasisChoiceGridProps) {
  const primaryChoices = orderedChoices.filter((choice) => !isSecondaryChoice(choice));
  const secondaryChoices = orderedChoices.filter((choice) => isSecondaryChoice(choice));
  const groups = [primaryChoices].filter((group) => group.length > 0);

  const renderGroup = (group: PromptChoiceViewModel[], groupIndex: number) => (
    <div
      key={`${testIdPrefix}-${groupIndex}`}
      className={`${choiceGridClass(variant, compactChoices)} ${groupIndex > 0 ? "prompt-choices-secondary" : ""}`}
    >
      {group.map((choice) => {
        const normalized = normalizeChoiceText(prompt, choice, promptText);
        const secondary = isSecondaryChoice(choice);
        return (
          <button
            type="button"
            key={choice.choiceId}
            className={`prompt-choice-card prompt-choice-card-emphasis ${secondary ? "prompt-choice-card-secondary" : ""}`}
            data-testid={`${testIdPrefix}-${choice.choiceId}`}
            onClick={() => onSelectChoice(choice.choiceId)}
            disabled={busy}
          >
            <div className="prompt-choice-topline">
              <strong>{normalized.title}</strong>
              {secondary ? <span className="prompt-choice-badge">{promptText.secondaryChoiceBadge}</span> : null}
            </div>
            {renderExtra ? renderExtra(choice) : null}
            <small>{normalized.description}</small>
          </button>
        );
      })}
    </div>
  );

  return (
    <>
      {groups.map(renderGroup)}
      {secondaryChoices.length > 0 && !collapseSecondaryChoices ? renderGroup(secondaryChoices, 1) : null}
      {secondaryChoices.length > 0 && collapseSecondaryChoices ? (
        <details className="prompt-choice-secondary-group">
          <summary>{promptText.secondaryChoiceBadge}</summary>
          {renderGroup(secondaryChoices, 1)}
        </details>
      ) : null}
      {orderedChoices.length === 0 ? <p>{promptText.choice.noChoices}</p> : null}
    </>
  );
}

type ChoiceSectionProps = {
  summaryPills?: SummaryPillValue[];
  children: ReactNode;
};

function ChoiceSection({ summaryPills = [], children }: ChoiceSectionProps) {
  return (
    <section className="prompt-section prompt-hand-stage">
      <div className="prompt-section-summary">
        <SummaryPills values={summaryPills} />
      </div>
      {children}
    </section>
  );
}

type DecisionChoiceSectionProps = {
  prompt: PromptViewModel;
  orderedChoices: PromptChoiceViewModel[];
  promptText: PromptText;
  compactChoices: boolean;
  busy: boolean;
  onSelectChoice: (choiceId: string) => void;
  testIdPrefix: string;
  summaryPills?: SummaryPillValue[];
  variant?: ChoiceGridVariant;
  renderExtra?: (choice: PromptChoiceViewModel) => ReactNode;
  collapseSecondaryChoices?: boolean;
};

function DecisionChoiceSection({
  prompt,
  orderedChoices,
  promptText,
  compactChoices,
  busy,
  onSelectChoice,
  testIdPrefix,
  summaryPills = [],
  variant = "default",
  renderExtra,
  collapseSecondaryChoices = true,
}: DecisionChoiceSectionProps) {
  return (
    <ChoiceSection summaryPills={summaryPills}>
      <EmphasisChoiceGrid
        prompt={prompt}
        orderedChoices={orderedChoices}
        promptText={promptText}
        compactChoices={compactChoices}
        busy={busy}
        onSelectChoice={onSelectChoice}
        variant={variant}
        testIdPrefix={testIdPrefix}
        renderExtra={renderExtra}
        collapseSecondaryChoices={collapseSecondaryChoices}
      />
    </ChoiceSection>
  );
}

export function PromptOverlay({
  prompt,
  collapsed,
  busy,
  secondsLeft,
  feedbackMessage,
  compactChoices = false,
  onToggleCollapse,
  onSelectChoice,
}: PromptOverlayProps) {
  const { prompt: promptText, promptType, promptHelper } = useI18n();
  const rootRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [movementMode, setMovementMode] = useState<"roll" | "cards">("roll");
  const [selectedCards, setSelectedCards] = useState<number[]>([]);

  const movement = useMemo(() => {
    if (!prompt || prompt.requestType !== "movement") {
      return null;
    }
    return movementChoices(prompt);
  }, [prompt]);

  const trickChoices = useMemo(() => {
    if (!prompt || (prompt.requestType !== "trick_to_use" && prompt.requestType !== "hidden_trick_card")) {
      return null;
    }
    return buildHandChoiceCards(prompt, promptText);
  }, [prompt, promptText]);
  const orderedChoices = useMemo(() => (prompt ? sortChoicesForDisplay(prompt.choices) : []), [prompt]);

  useEffect(() => {
    if (!prompt) {
      if (previousFocusRef.current) {
        previousFocusRef.current.focus();
        previousFocusRef.current = null;
      }
      setSelectedCards([]);
      setMovementMode("roll");
      return;
    }
    setSelectedCards([]);
    setMovementMode("roll");
  }, [prompt?.requestId]);

  useEffect(() => {
    if (!prompt || collapsed) {
      return;
    }
    if (!previousFocusRef.current && document.activeElement instanceof HTMLElement) {
      previousFocusRef.current = document.activeElement;
    }
    const firstChoice = rootRef.current?.querySelector<HTMLButtonElement>(".prompt-choice-card");
    firstChoice?.focus();
  }, [prompt, collapsed, compactChoices]);

  if (!prompt) {
    return null;
  }

  const promptLabel = promptLabelForType(prompt.requestType, promptType);
  const promptHelp = promptHelperForType(prompt.requestType, promptHelper);
  const usesSpecializedSurface = isSpecializedPromptType(prompt.requestType);
  const promptTimeRatio =
    secondsLeft !== null && prompt.timeoutMs > 0
      ? Math.max(0, Math.min(100, (secondsLeft * 1000 * 100) / prompt.timeoutMs))
      : null;
  const headMetaPills = promptText.requestCompactMetaPills(prompt.playerId, secondsLeft).slice(0, 2);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onToggleCollapse();
    }
  };

  const movementSelectedChoice =
    movement && selectedCards.length > 0 ? findCardChoice(movement.cardChoices, selectedCards) : null;

  const onToggleCardChip = (card: number) => {
    setSelectedCards((prev) => {
      if (prev.includes(card)) {
        return prev.filter((it) => it !== card);
      }
      const next = [...prev, card].sort((a, b) => a - b);
      const limit = movement?.canUseTwoCards ? 2 : 1;
      return next.slice(0, limit);
    });
  };

  const onSubmitMovement = () => {
    if (!movement) {
      return;
    }
    if (movementMode === "roll") {
      const choice = movement.rollChoice ?? prompt.choices.find((item) => item.choiceId === "dice") ?? null;
      if (choice) {
        onSelectChoice(choice.choiceId);
      }
      return;
    }
    if (!movementSelectedChoice) {
      return;
    }
    onSelectChoice(movementSelectedChoice.choiceId);
  };

  const isCharacterPick =
    prompt.requestType === "draft_card" ||
    prompt.requestType === "final_character" ||
    prompt.requestType === "final_character_choice";
  const isMarkTarget = prompt.requestType === "mark_target";
  const isPurchaseTile = prompt.requestType === "purchase_tile";
  const isLapReward = prompt.requestType === "lap_reward";
  const isTrickTileTarget = prompt.requestType === "trick_tile_target";
  const isActiveFlip = prompt.requestType === "active_flip";
  const isBurdenExchange = prompt.requestType === "burden_exchange";
  const isSpecificTrickReward = prompt.requestType === "specific_trick_reward";
  const isRunawayChoice = prompt.requestType === "runaway_step_choice";
  const isCoinPlacement = prompt.requestType === "coin_placement";
  const isDoctrineRelief = prompt.requestType === "doctrine_relief";
  const isGeoBonus = prompt.requestType === "geo_bonus";
  const isPabalDiceMode = prompt.requestType === "pabal_dice_mode";

  const currentTileIndex = numberFromContext(prompt.publicContext, "tile_index", "player_position");
  const currentCash = numberFromContext(prompt.publicContext, "player_cash");
  const currentCost = numberFromContext(prompt.publicContext, "cost", "tile_purchase_cost");
  const currentShards = numberFromContext(prompt.publicContext, "player_shards");
  const currentCoins = numberFromContext(prompt.publicContext, "player_hand_coins");
  const currentPlacedCoins = numberFromContext(prompt.publicContext, "player_placed_coins");
  const currentTotalScore = numberFromContext(prompt.publicContext, "player_total_score");
  const currentOwnedTileCount = numberFromContext(prompt.publicContext, "player_owned_tile_count");
  const currentZone = stringFromContext(prompt.publicContext, "tile_zone");
  const weatherName = stringFromContext(prompt.publicContext, "weather_name");
  const markActorName = stringFromContext(prompt.publicContext, "actor_name");
  const markTargetCount = numberFromContext(prompt.publicContext, "target_count");
  const burdenCardName = stringFromContext(prompt.publicContext, "card_name");
  const burdenCost = numberFromContext(prompt.publicContext, "burden_cost");
  const currentFValue = numberFromContext(prompt.publicContext, "current_f_value");
  const supplyThreshold = numberFromContext(prompt.publicContext, "supply_threshold");
  const burdenTrigger = promptText.context.burdenExchangeTrigger(supplyThreshold, currentFValue);
  const markCandidateCount = prompt.choices.filter((choice) => choice.choiceId !== "none").length;
  const doctrineCandidateCount = numberFromContext(prompt.publicContext, "candidate_count") ?? markCandidateCount;
  const trickTargetCandidateCount = numberFromContext(prompt.publicContext, "candidate_count");
  const trickTargetScope = stringFromContext(prompt.publicContext, "target_scope");
  const trickTargetCardName = stringFromContext(prompt.publicContext, "card_name");
  const movementPosition = numberFromContext(prompt.publicContext, "player_position");
  const runawayOneShortPos = numberFromContext(prompt.publicContext, "one_short_pos");
  const runawayBonusTargetPos = numberFromContext(prompt.publicContext, "bonus_target_pos");
  const runawayBonusTargetKind = stringFromContext(prompt.publicContext, "bonus_target_kind");
  const ownedTileIndices = Array.isArray(prompt.publicContext["owned_tile_indices"])
    ? prompt.publicContext["owned_tile_indices"].map((item) => asNumber(item)).filter((item): item is number => item !== null)
    : [];
  const ownedTileCount = ownedTileIndices.length;
  const rewardBudget = numberFromContext(prompt.publicContext, "budget");
  const rewardPools = isRecord(prompt.publicContext["pools"]) ? prompt.publicContext["pools"] : null;
  const rewardPoolSummary = rewardPools
    ? [
        typeof rewardPools["cash"] === "number" ? `${promptText.choice.cashReward(rewardPools["cash"] as number)}=2P` : null,
        typeof rewardPools["shards"] === "number" ? `${promptText.choice.shardReward(rewardPools["shards"] as number)}=3P` : null,
        typeof rewardPools["coins"] === "number" ? `${promptText.choice.coinReward(rewardPools["coins"] as number)}=3P` : null,
      ]
        .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
        .join(" / ")
    : "";
  const draftPhase = numberFromContext(prompt.publicContext, "draft_phase");
  const offeredCount = numberFromContext(prompt.publicContext, "offered_count");
  const offeredNames = Array.isArray(prompt.publicContext["offered_names"])
    ? prompt.publicContext["offered_names"].map((value) => asString(value)).filter((value) => value.length > 0)
    : [];
  const finalChoiceCount = numberFromContext(prompt.publicContext, "choice_count");
  const finalChoiceNames = Array.isArray(prompt.publicContext["choice_names"])
    ? prompt.publicContext["choice_names"].map((value) => asString(value)).filter((value) => value.length > 0)
    : [];
  const targetTiles = Array.isArray(prompt.publicContext["candidate_tiles"])
    ? prompt.publicContext["candidate_tiles"].map((item) => asNumber(item)).filter((item): item is number => item !== null)
    : [];

  if (collapsed) {
    return (
      <section className="panel prompt-dock-collapsed" data-testid="prompt-dock-collapsed">
        <div className="prompt-dock-collapsed-copy">
          <strong>{promptText.headTitle(promptLabel)}</strong>
          <small>{collapsedPromptChip(promptText, promptLabel, secondsLeft)}</small>
        </div>
        <button type="button" className="prompt-dock-collapsed-button" onClick={onToggleCollapse}>
          {promptText.collapse}
        </button>
      </section>
    );
  }

  return (
    <section
      ref={rootRef}
      className={`panel prompt-overlay prompt-overlay-docked prompt-overlay-${prompt.requestType}`}
      data-testid="prompt-overlay"
      data-prompt-type={prompt.requestType}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      role="region"
      aria-busy={busy}
    >
        <div className="prompt-head">
          <div className="prompt-head-copy">
            <h2>{promptText.headTitle(promptLabel)}</h2>
            <p className="prompt-helper">{promptHelp}</p>
            <div className="prompt-head-meta" data-testid="prompt-head-meta">
              {headMetaPills.map((pill) => (
                <span key={pill} className="prompt-head-pill">
                  {pill}
                </span>
              ))}
            </div>
          </div>
          <button type="button" onClick={onToggleCollapse}>
            {promptText.collapse}
          </button>
        </div>

        <div className="prompt-body">

        {prompt.requestType === "movement" && movement ? (
          <section className="prompt-section prompt-movement-stage">
            <div className="prompt-section-summary">
              <p>
                {movementMode === "roll"
                  ? cleanDisplayText(promptText.movement.rollButton)
                  : cleanDisplayText(promptText.movement.cardGuide(movement.canUseTwoCards ? 2 : 1))}
              </p>
              <div className="prompt-summary-pill-row">
                <span className="prompt-summary-pill">
                  {promptText.context.currentPosition}: {tileLabel(movementPosition)}
                </span>
                {weatherName ? (
                  <span className="prompt-summary-pill">
                    {promptText.context.currentWeather}: {weatherName}
                  </span>
                ) : null}
                {movementMode === "cards" ? (
                  <span className="prompt-summary-pill">
                    {promptText.context.selectedCards}:{" "}
                    {selectedCards.length > 0 ? selectedCards.join(" + ") : promptText.context.noneSelected}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="prompt-move-mode">
              <button
                type="button"
                data-testid="movement-roll-mode"
                className={movementMode === "roll" ? "route-tab route-tab-active" : "route-tab"}
                onClick={() => setMovementMode("roll")}
                disabled={busy}
              >
                {promptText.movement.rollMode}
              </button>
              <button
                type="button"
                data-testid="movement-card-mode"
                className={movementMode === "cards" ? "route-tab route-tab-active" : "route-tab"}
                onClick={() => setMovementMode("cards")}
                disabled={busy || movement.cardPool.length === 0}
              >
                {promptText.movement.cardMode}
              </button>
            </div>

            {movementMode === "cards" ? (
              <div className="dice-chip-row">
                <small className="prompt-choice-footnote">
                  {promptText.context.usableCards}: {String(movement.cardPool.length)}
                </small>
                <div className="dice-chip-list">
                  {movement.cardPool.map((card) => (
                    <button
                      type="button"
                      key={`dice-card-${card}`}
                      data-testid={`movement-card-${card}`}
                      className={selectedCards.includes(card) ? "dice-chip dice-chip-selected" : "dice-chip"}
                      disabled={busy}
                      onClick={() => onToggleCardChip(card)}
                    >
                      {card}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="prompt-primary-row">
              <button
                type="button"
                className="prompt-primary-action"
                data-testid="movement-submit"
                disabled={busy || (movementMode === "cards" && !movementSelectedChoice)}
                onClick={onSubmitMovement}
              >
                {movementMode === "roll"
                  ? promptText.movement.rollButton
                  : movementSelectedChoice
                    ? promptText.movement.rollWithCardsButton(selectedCards)
                    : promptText.movement.selectCardsFirst}
              </button>
            </div>
          </section>
        ) : null}

        {(prompt.requestType === "trick_to_use" || prompt.requestType === "hidden_trick_card") && trickChoices ? (
          <section className="prompt-section prompt-hand-stage">
            <div className="prompt-section-summary">
              <p>{cleanDisplayText(prompt.requestType === "trick_to_use" ? promptText.trick.usePrompt : promptText.trick.hiddenPrompt)}</p>
              <div className="prompt-summary-pill-row">
                <span className="prompt-summary-pill">
                  {promptText.trick.handSummary(
                    trickChoices.cards.length,
                    typeof prompt.publicContext["hidden_trick_count"] === "number"
                      ? (prompt.publicContext["hidden_trick_count"] as number)
                      : undefined
                  )}
                </span>
              </div>
            </div>
            <div className="prompt-choices hand-grid">
              {prompt.requestType === "trick_to_use" && trickChoices.passChoiceId ? (
                <button
                  type="button"
                  className="prompt-choice-card prompt-choice-card-pass"
                  data-testid="trick-pass"
                  disabled={busy}
                  onClick={() => onSelectChoice(trickChoices.passChoiceId as string)}
                >
                  <strong>{promptText.trick.skipTitle}</strong>
                  <small>{promptText.trick.skipDescription}</small>
                </button>
              ) : null}

              {trickChoices.cards.map((card) => (
                <button
                  type="button"
                  key={card.key}
                  className={`prompt-choice-card ${card.isHidden ? "hand-card-hidden" : ""}`}
                  data-testid={`trick-choice-${card.key}`}
                  disabled={busy || !card.isUsable || !card.choiceId}
                  onClick={() => {
                    if (card.choiceId) {
                      onSelectChoice(card.choiceId);
                    }
                  }}
                >
                  <div className="prompt-choice-topline">
                    <strong>{card.name}</strong>
                    <span className="prompt-choice-badge">
                      {card.isHidden ? promptText.hiddenState.hidden : promptText.hiddenState.public}
                    </span>
                  </div>
                  <small>{card.description}</small>
                  <small className="prompt-choice-footnote">
                    {card.isUsable ? promptText.hiddenState.usable : promptText.hiddenState.unavailable}
                  </small>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {isCharacterPick ? (
          <section className="prompt-section prompt-hand-stage">
            <div className="prompt-section-summary">
              <p>{cleanDisplayText(prompt.requestType === "draft_card" ? promptText.character.draftPrompt : promptText.character.finalPrompt)}</p>
              <SummaryPills
                values={[
                  prompt.requestType === "draft_card"
                    ? promptText.character.draftPhaseLabel(draftPhase)
                    : promptText.character.finalPhaseLabel,
                  prompt.requestType === "draft_card"
                    ? offeredCount !== null
                      ? `${promptText.context.selectableTargets}: ${offeredCount}`
                      : null
                    : finalChoiceCount !== null
                      ? `${promptText.context.selectableTargets}: ${finalChoiceCount}`
                      : null,
                  prompt.requestType === "draft_card"
                    ? offeredNames.length > 0
                      ? offeredNames.join(", ")
                      : null
                    : finalChoiceNames.length > 0
                      ? finalChoiceNames.join(", ")
                      : null,
                ]}
              />
            </div>
            <div className={`prompt-choices ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {prompt.choices.map((choice) => (
                  <button
                    type="button"
                    key={choice.choiceId}
                    className="prompt-choice-card prompt-choice-card-emphasis"
                    data-testid={`character-choice-${choice.choiceId}`}
                    onClick={() => onSelectChoice(choice.choiceId)}
                    disabled={busy}
                  >
                  <strong>{choice.title}</strong>
                  <small>{characterAbilityText(choice, promptText)}</small>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {isMarkTarget ? (
          <section className="prompt-section prompt-hand-stage">
            <div className="prompt-section-summary">
              <div className="prompt-summary-pill-row">
                <span className="prompt-summary-pill">
                  {promptText.context.actorCharacter}: {markActorName || "-"}
                </span>
                <span className="prompt-summary-pill">
                  {promptText.context.selectableTargets}: {String(markTargetCount ?? doctrineCandidateCount)}
                </span>
                <span className="prompt-summary-pill">
                  {promptText.context.currentPosition}: {tileLabel(currentTileIndex)}
                </span>
                <span className="prompt-summary-pill">
                  {promptText.context.targetRule}: {promptText.context.markTargetRule(markTargetCount ?? markCandidateCount)}
                </span>
              </div>
            </div>
            <div className={`prompt-choices prompt-choices-target ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {orderedChoices.map((choice) => {
                const target = markChoiceTarget(choice);
                return (
                  <button
                    type="button"
                    key={choice.choiceId}
                    className="prompt-choice-card prompt-choice-card-emphasis"
                    data-testid={`mark-choice-${choice.choiceId}`}
                    onClick={() => onSelectChoice(choice.choiceId)}
                    disabled={busy}
                  >
                    <div className="prompt-choice-topline">
                      <strong>{markChoiceTitle(choice, promptText)}</strong>
                      {choice.choiceId === "none" ? (
                        <span className="prompt-choice-badge">{cleanDisplayText(promptText.choice.skip)}</span>
                      ) : null}
                    </div>
                    {choice.choiceId === "none" ? (
                      <div className="prompt-summary-pill-row">
                        <span className="prompt-summary-pill">{cleanDisplayText(promptText.choice.skip)}</span>
                      </div>
                    ) : (
                      <div className="prompt-summary-pill-row">
                        {target.character ? <span className="prompt-summary-pill">{target.character}</span> : null}
                        {target.playerId !== null ? <span className="prompt-summary-pill">P{target.playerId}</span> : null}
                      </div>
                    )}
                    <small>{markChoiceDescription(choice, promptText)}</small>
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {isPurchaseTile ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            testIdPrefix="purchase-choice"
            variant="decision"
            summaryPills={[
              `${promptText.context.currentPosition}: ${tileLabel(currentTileIndex)}`,
              `${promptText.context.purchaseCost}: ${formatNumber(currentCost)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              currentZone ? `${promptText.context.zone}: ${currentZone}` : null,
            ]}
          />
        ) : null}

        {isLapReward ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={prompt.choices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            testIdPrefix="lap-reward-choice"
            variant="reward"
            summaryPills={[
              rewardBudget !== null ? `${promptText.context.rewardBudget}: ${rewardBudget}` : null,
              rewardPoolSummary ? `${promptText.context.rewardPools}: ${rewardPoolSummary}` : null,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
              `${promptText.context.currentCoins}: ${currentCoins ?? "-"}`,
              `${promptText.context.currentPlacedCoins}: ${currentPlacedCoins ?? "-"}`,
              `${promptText.context.currentTotalScore}: ${currentTotalScore ?? "-"}`,
              `${promptText.context.ownedTiles}: ${currentOwnedTileCount ?? "-"}`,
            ]}
          />
        ) : null}

        {isTrickTileTarget ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="target"
            testIdPrefix="trick-tile-target-choice"
            summaryPills={[
              trickTargetCardName ? `${promptText.context.trigger}: ${trickTargetCardName}` : null,
              trickTargetCandidateCount !== null ? `${promptText.context.selectableTargets}: ${trickTargetCandidateCount}` : null,
              trickTargetScope ? `${promptText.context.targetRule}: ${trickTargetScope}` : null,
              targetTiles.length > 0 ? `${promptText.context.targetTiles}: ${targetTiles.map((tile) => tileLabel(tile)).join(", ")}` : null,
            ]}
            renderExtra={(choice) => {
              const tileIndex = asNumber(choice.value?.["tile_index"]);
              return tileIndex !== null ? (
                <div className="prompt-summary-pill-row">
                  <span className="prompt-summary-pill">{tileLabel(tileIndex)}</span>
                </div>
              ) : null;
            }}
          />
        ) : null}

        {isActiveFlip ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            testIdPrefix="active-flip-choice"
            summaryPills={[
              `${promptText.context.currentPosition}: ${tileLabel(currentTileIndex)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.usableCards}: ${String(prompt.choices.filter((choice) => choice.choiceId !== "none").length)}`,
            ]}
          />
        ) : null}

        {isBurdenExchange ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            testIdPrefix="burden-exchange-choice"
            collapseSecondaryChoices={false}
            summaryPills={[
              `${promptText.context.trigger}: ${burdenTrigger}`,
              burdenCardName ? `${promptText.context.burdenCard}: ${burdenCardName}` : null,
              `${promptText.context.burdenCost}: ${formatNumber(burdenCost)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              currentFValue !== null ? `${promptText.context.currentF}: ${currentFValue}` : null,
            ]}
          />
        ) : null}

        {isSpecificTrickReward ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            testIdPrefix="specific-reward-choice"
            summaryPills={[
              `${promptText.context.usableCards}: ${String(prompt.choices.filter((choice) => choice.choiceId !== "none").length)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
            ]}
          />
        ) : null}

        {isRunawayChoice ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="target"
            testIdPrefix="runaway-choice"
            summaryPills={[
              `${promptText.context.currentPosition}: ${tileLabel(movementPosition)}`,
              `${tileLabel(runawayOneShortPos)} -> ${tileLabel(runawayBonusTargetPos)}`,
              runawayBonusTargetKind || null,
            ]}
            renderExtra={(choice) => {
              const takeBonus = booleanFromValue(choice.value?.["take_bonus"]);
              const pills = nonEmptyPills([
                takeBonus !== null ? (takeBonus ? "+1" : "Stop") : null,
                `${tileLabel(runawayOneShortPos)} -> ${tileLabel(runawayBonusTargetPos)}`,
                runawayBonusTargetKind || null,
              ]);
              return pills.length > 0 ? (
                <div className="prompt-summary-pill-row">
                  {pills.map((pill) => (
                    <span key={`${choice.choiceId}-${pill}`} className="prompt-summary-pill">
                      {pill}
                    </span>
                  ))}
                </div>
              ) : null;
            }}
          />
        ) : null}

        {isCoinPlacement ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="target"
            testIdPrefix="coin-placement-choice"
            summaryPills={[
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.selectableTargets}: ${formatNumber(ownedTileCount)}`,
            ]}
            renderExtra={(choice) => {
              const tileIndex = asNumber(choice.value?.["tile_index"]);
              const pills = nonEmptyPills([
                tileIndex !== null ? tileLabel(tileIndex) : null,
                currentZone || null,
              ]);
              return pills.length > 0 ? (
                <div className="prompt-summary-pill-row">
                  {pills.map((pill) => (
                    <span key={`${choice.choiceId}-${pill}`} className="prompt-summary-pill">
                      {pill}
                    </span>
                  ))}
                </div>
              ) : null;
            }}
          />
        ) : null}

        {isDoctrineRelief ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="target"
            testIdPrefix="doctrine-relief-choice"
            summaryPills={[
              `${promptText.context.selectableTargets}: ${String(markCandidateCount)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
            ]}
            renderExtra={(choice) => {
              const targetPlayerId = asNumber(choice.value?.["target_player_id"]);
              return targetPlayerId !== null ? (
                <div className="prompt-summary-pill-row">
                  <span className="prompt-summary-pill">P{targetPlayerId}</span>
                </div>
              ) : null;
            }}
          />
        ) : null}

        {isGeoBonus ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="reward"
            testIdPrefix="geo-bonus-choice"
            summaryPills={[
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
              `${promptText.context.currentCoins}: ${currentCoins ?? "-"}`,
            ]}
          />
        ) : null}

        {isPabalDiceMode ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={orderedChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="decision"
            testIdPrefix="pabal-dice-mode-choice"
            summaryPills={[
              `${promptText.context.currentPosition}: ${tileLabel(movementPosition)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
              weatherName ? `${promptText.context.currentWeather}: ${weatherName}` : null,
            ]}
          />
        ) : null}

        {!usesSpecializedSurface ? (
          <section className="prompt-section">
            <EmphasisChoiceGrid
              prompt={prompt}
              orderedChoices={orderedChoices}
              promptText={promptText}
              compactChoices={compactChoices}
              busy={busy}
              onSelectChoice={onSelectChoice}
              testIdPrefix="generic-choice"
              collapseSecondaryChoices
            />
          </section>
        ) : null}

        </div>

        <div className="prompt-footer">
          {feedbackMessage ? <p className="notice err">{cleanDisplayText(feedbackMessage)}</p> : null}
          {busy ? (
            <p className="notice ok">
              <span className="spinner" aria-hidden="true" /> {promptText.busy}
            </p>
          ) : null}
          {promptTimeRatio !== null ? (
            <div className="prompt-timebar" aria-hidden="true">
              <span style={{ width: `${promptTimeRatio}%` }} />
            </div>
          ) : null}
        </div>
    </section>
  );
}
