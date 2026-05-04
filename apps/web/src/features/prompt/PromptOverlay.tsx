import { KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { PromptChoiceViewModel, PromptViewModel } from "../../domain/selectors/promptSelectors";
import { promptHelperForType } from "../../domain/labels/promptHelperCatalog";
import { promptLabelForType } from "../../domain/labels/promptTypeCatalog";
import { prioritySlotForCharacterName } from "../../domain/catalogs/gameplayCatalog";
import type { LocaleMessages } from "../../i18n/types";
import { useI18n } from "../../i18n/useI18n";
import characterPortraitSpriteUrl from "../../assets/characters/character-card-portraits-sprite.png";
import { isSpecializedPromptType } from "./promptSurfaceCatalog";

type PromptOverlayProps = {
  prompt: PromptViewModel | null;
  markTargetCandidates?: Array<{
    slot: number;
    playerId: number | null;
    label: string | null;
    character: string;
  }>;
  collapsed: boolean;
  busy: boolean;
  secondsLeft: number | null;
  feedbackMessage?: string;
  compactChoices?: boolean;
  presentationMode?: PromptPresentationMode;
  effectContext?: PromptEffectContext | null;
  onToggleCollapse: () => void;
  onSelectChoice: (choiceId: string) => void;
};

type PromptPresentationMode = "decision-focus" | "board-preserve";
type PromptEffectContext = {
  label: string;
  detail: string;
  attribution: string | null;
  tone: "move" | "effect" | "economy";
  source: string;
  intent: string;
  enhanced: boolean;
};

type PromptText = LocaleMessages["prompt"];
type PromptTypeText = LocaleMessages["promptType"];
type PromptHelperText = LocaleMessages["promptHelper"];

const CHARACTER_PORTRAIT_INDEX: Record<string, number> = {
  어사: 0,
  탐관오리: 1,
  자객: 2,
  산적: 3,
  추노꾼: 4,
  "탈출 노비": 5,
  탈출노비: 5,
  파발꾼: 6,
  아전: 7,
  "교리 연구관": 8,
  교리연구관: 8,
  "교리 감독관": 9,
  교리감독관: 9,
  박수: 10,
  만신: 11,
  객주: 12,
  중매꾼: 13,
  건설업자: 14,
  사기꾼: 15,
};

function portraitIndexForCharacter(name: string): number {
  const normalized = name.trim();
  const direct = CHARACTER_PORTRAIT_INDEX[normalized];
  if (direct !== undefined) {
    return direct;
  }
  return Math.abs(Array.from(normalized).reduce((sum, char) => sum + char.charCodeAt(0), 0)) % 16;
}

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
  serial: string;
  isHidden: boolean;
  isUsable: boolean;
  choiceId: string | null;
};

type BurdenChoiceCard = {
  key: string;
  deckIndex: number | null;
  name: string;
  description: string;
  burdenCost: number | null;
  isCurrentTarget: boolean;
};

type LapRewardSelection = {
  cashUnits: number;
  shardUnits: number;
  coinUnits: number;
};

type LapRewardOption = LapRewardSelection & {
  choiceId: string;
  spentPoints: number;
};

type CharacterPickOption = NonNullable<PromptViewModel["surface"]["characterPick"]>["options"][number];

type ChoiceGridVariant = "default" | "target" | "decision" | "reward";
type SummaryPillValue = string | null | undefined;
type PromptPillTone = "neutral" | "player" | "timer" | "resource" | "decision" | "target" | "danger" | "success" | "character";
type ChoiceBodyParts = {
  eyebrow: string | null;
  summary: string;
  detail: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function isKoreanLocale(locale: string): boolean {
  return locale.toLowerCase().startsWith("ko");
}

function cleanDisplayText(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith("[") && trimmed.endsWith("]") && trimmed.length >= 2) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function effectAttributionLabel(effectContext: PromptEffectContext, promptText: PromptText): string | null {
  const attribution = cleanDisplayText(effectContext.attribution ?? "");
  if (attribution === "Character mark") {
    return promptText.effectAttribution.characterMark;
  }
  if (attribution === "Trick effect") {
    return promptText.effectAttribution.trickEffect;
  }
  if (attribution === "Movement result") {
    return promptText.effectAttribution.movementResult;
  }
  if (attribution === "Character effect") {
    return promptText.effectAttribution.characterEffect;
  }
  if (attribution === "Supply threshold") {
    return promptText.effectAttribution.supplyThreshold;
  }
  if (attribution) {
    return attribution;
  }
  if (effectContext.source === "character" && effectContext.intent === "mark") {
    return promptText.effectAttribution.characterMark;
  }
  if (effectContext.source === "trick" && effectContext.intent === "target") {
    return promptText.effectAttribution.trickEffect;
  }
  if (effectContext.source === "move") {
    return promptText.effectAttribution.movementResult;
  }
  return null;
}

/**
 * Strip or reformat inline bracket tags from card description text.
 * Transforms: "[효과] 통행료 면제" → "효과: 통행료 면제"
 * Handles: [효과], [능력1], [능력2], [도치], and any other [TAG] patterns.
 */
function cleanCardDescription(value: string): string {
  return value
    .replace(/\[([^\]]{1,20})\]\s*/g, (_, tag: string) => `${tag.trim()}: `)
    .trim();
}

function isInternalAbilityLabel(value: string): boolean {
  return /^(능력\s*[12]|ability\s*[12])$/i.test(value.trim());
}

function stripInternalAbilityLabel(value: string): string {
  const trimmed = value.trim();
  const labeledMatch = /^([^:]{1,16}):\s*(.+)$/.exec(trimmed);
  if (!labeledMatch) {
    return trimmed;
  }

  const label = labeledMatch[1].trim();
  return isInternalAbilityLabel(label) ? labeledMatch[2].trim() : trimmed;
}

function splitChoiceBodyText(value: string): ChoiceBodyParts {
  const cleaned = cleanCardDescription(value).trim();
  if (!cleaned) {
    return { eyebrow: null, summary: "", detail: null };
  }

  const labeledMatch = /^([^:]{1,16}):\s*(.+)$/.exec(cleaned);
  if (labeledMatch) {
    const eyebrow = labeledMatch[1].trim();
    const remainder = labeledMatch[2].trim();
    const segments = remainder.split(/\s*\/\s*/).map(stripInternalAbilityLabel).filter(Boolean);
    return {
      eyebrow: isInternalAbilityLabel(eyebrow) ? null : eyebrow,
      summary: segments[0] ?? remainder,
      detail: segments.length > 1 ? segments.slice(1).join("\n") : null,
    };
  }

  const slashSegments = cleaned.split(/\s*\/\s*/).map(stripInternalAbilityLabel).filter(Boolean);
  if (slashSegments.length > 1) {
    return {
      eyebrow: null,
      summary: slashSegments[0],
      detail: slashSegments.slice(1).join("\n"),
    };
  }

  return {
    eyebrow: null,
    summary: cleaned,
    detail: null,
  };
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

function choiceDescription(choice: PromptChoiceViewModel, _promptText: PromptText): string {
  const text = choice.description.trim();
  return text ? cleanDisplayText(text) : "";
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

function numberFromNestedContext(context: Record<string, unknown>, parentKey: string, childKey: string): number | null {
  const parent = context[parentKey];
  if (!isRecord(parent)) {
    return null;
  }
  return asNumber(parent[childKey]);
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

function isMatchmakerPurchaseSource(source: string): boolean {
  return source === "matchmaker_adjacent" || source === "adjacent_extra" || /중매꾼|matchmaker/i.test(source);
}

function tileLabel(tileIndex: number | null): string {
  return tileIndex === null ? "-" : String(tileIndex + 1);
}

function formatNumber(value: number | null): string {
  return value === null ? "-" : String(value);
}

function lapRewardSelectionKey(selection: LapRewardSelection): string {
  return `${selection.cashUnits}|${selection.shardUnits}|${selection.coinUnits}`;
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

function classifyPromptPill(value: string, source: "head" | "summary", index = 0): PromptPillTone {
  const normalized = value.trim().toLowerCase();
  if (source === "head") {
    return index === 0 ? "player" : "timer";
  }
  if (
    normalized.includes("현금") ||
    normalized.includes("cash") ||
    normalized.includes("조각") ||
    normalized.includes("shard") ||
    normalized.includes("승점") ||
    normalized.includes("coin") ||
    normalized.includes("reward")
  ) {
    return "resource";
  }
  if (
    normalized.includes("남은") ||
    normalized.includes("remaining") ||
    normalized.includes("budget") ||
    normalized.includes("selected") ||
    normalized.includes("선택") ||
    normalized.includes("기본가")
  ) {
    return "decision";
  }
  if (normalized.includes("중매꾼") || normalized.includes("matchmaker") || normalized.includes("character")) {
    return "character";
  }
  if (
    normalized.includes("대상") ||
    normalized.includes("target") ||
    normalized.includes("타일") ||
    normalized.includes("tiles") ||
    normalized.includes("범위") ||
    normalized.includes("scope")
  ) {
    return "target";
  }
  if (normalized.includes("cost") || normalized.includes("위험") || normalized.includes("exceed")) {
    return "danger";
  }
  if (/^p\d+/.test(normalized)) {
    return "player";
  }
  return "neutral";
}

function SummaryPills({ values }: { values: SummaryPillValue[] }) {
  const pills = nonEmptyPills(values);
  if (pills.length === 0) {
    return null;
  }
  return (
    <div className="prompt-summary-pill-row">
      {pills.map((pill, index) => (
        <span key={pill} className="prompt-summary-pill" data-tone={classifyPromptPill(pill, "summary", index)}>
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
  if (prompt.surface.movement) {
    const rollChoice = prompt.surface.movement.rollChoiceId
      ? prompt.choices.find((choice) => choice.choiceId === prompt.surface.movement?.rollChoiceId) ?? null
      : null;
    const cardChoices = prompt.surface.movement.cardChoices
      .map((item) => {
        const choice = prompt.choices.find((entry) => entry.choiceId === item.choiceId);
        return choice ? { cards: item.cards, choice } : null;
      })
      .filter((item): item is { cards: number[]; choice: PromptChoiceViewModel } => item !== null);
    return {
      rollChoice,
      cardChoices,
      cardPool: prompt.surface.movement.cardPool,
      canUseTwoCards: prompt.surface.movement.canUseTwoCards,
    };
  }

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
  if (prompt.surface.handChoice) {
    return {
      passChoiceId: prompt.surface.handChoice.passChoiceId,
      cards: prompt.surface.handChoice.cards.map((card, index) => ({
        key: `${card.deckIndex ?? "x"}-${index}`,
        name: card.name,
        description: card.description || promptText.hiddenCardDescription(card.name),
        serial: card.deckIndex === null ? "" : `#${card.deckIndex}`,
        isHidden: card.isHidden,
        isUsable: card.isUsable,
        choiceId: card.choiceId,
      })),
    };
  }

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
          serial: deckIndex === null ? "" : `#${deckIndex}`,
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
      serial: asNumber(choice.value?.["deck_index"]) === null ? "" : `#${asNumber(choice.value?.["deck_index"])}`,
      isHidden: choice.value?.["is_hidden"] === true,
      isUsable: true,
      choiceId: choice.choiceId,
    }));

  return { cards, passChoiceId };
}

function buildBurdenChoiceCards(prompt: PromptViewModel): BurdenChoiceCard[] {
  const cards = Array.isArray(prompt.publicContext["burden_cards"]) ? prompt.publicContext["burden_cards"] : [];
  return cards
    .map((item, index) => {
      if (!isRecord(item)) {
        return null;
      }
      const deckIndex = asNumber(item["deck_index"]);
      const name = asString(item["name"], `Burden ${index + 1}`);
      const description = asString(item["card_description"], "");
      const burdenCost = asNumber(item["burden_cost"]);
      const isCurrentTarget = item["is_current_target"] === true;
      return {
        key: `${deckIndex ?? index}-${name}`,
        deckIndex,
        name,
        description,
        burdenCost,
        isCurrentTarget,
      };
    })
    .filter((item): item is BurdenChoiceCard => item !== null)
    .sort((left, right) => {
      if (left.isCurrentTarget !== right.isCurrentTarget) {
        return left.isCurrentTarget ? -1 : 1;
      }
      if (left.deckIndex === null || right.deckIndex === null) {
        return left.name.localeCompare(right.name);
      }
      return left.deckIndex - right.deckIndex;
    });
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
  const targetCharacter = asString(choice.value?.["target_character"]);
  return cleanDisplayText(targetCharacter || choice.title);
}

function markChoiceDescription(choice: PromptChoiceViewModel, promptText: PromptText): string {
  if (choice.choiceId === "none") {
    return cleanDisplayText(promptText.mark.noneDescription);
  }
  const targetPlayerId = asNumber(choice.value?.["target_player_id"]);
  if (targetPlayerId !== null) {
    return `P${targetPlayerId}의 이 등장인물에게 효과를 적용합니다.`;
  }
  return "이 등장인물에게 효과를 적용합니다.";
}

function markChoiceTarget(choice: PromptChoiceViewModel): {
  character: string;
  playerId: number | null;
  cardNo: number | null;
} {
  return {
    character: asString(choice.value?.["target_character"]),
    playerId: asNumber(choice.value?.["target_player_id"]),
    cardNo: asNumber(choice.value?.["target_card_no"]),
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
    const source = asString(prompt.publicContext["source"] ?? prompt.publicContext["purchase_source"]);
    const baseCost = asNumber(prompt.publicContext["base_cost"]) ?? asNumber(prompt.publicContext["tile_purchase_cost"]);
    const multiplier = baseCost !== null && cost !== null && baseCost > 0 ? Math.round((cost / baseCost) * 10) / 10 : null;
    const costDetail =
      baseCost !== null && cost !== null && multiplier !== null && multiplier !== 1
        ? `기본 ${formatNumber(baseCost)} x ${multiplier} = ${formatNumber(cost)}`
        : cost !== null
          ? `비용 ${formatNumber(cost)}`
          : "";
    if (choice.choiceId === "yes") {
      if (isMatchmakerPurchaseSource(source)) {
        return {
          title: "중매꾼 추가 구매",
          description: cleanDisplayText(
            `${pos !== null ? tileLabel(pos) : "인접 토지"} 구매 / ${multiplier === 2 ? "2배 가격" : "기본가 적용"}${costDetail ? ` / ${costDetail}` : ""}`
          ),
        };
      }
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
  mergeSecondaryChoices?: boolean;
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
  mergeSecondaryChoices = false,
}: EmphasisChoiceGridProps) {
  const primaryChoices = orderedChoices.filter((choice) => !isSecondaryChoice(choice));
  const secondaryChoices = orderedChoices.filter((choice) => isSecondaryChoice(choice));
  const mergedPrimaryChoices = mergeSecondaryChoices ? orderedChoices : primaryChoices;
  const groups = [mergedPrimaryChoices].filter((group) => group.length > 0);

  const renderGroup = (group: PromptChoiceViewModel[], groupIndex: number) => (
    <div
      key={`${testIdPrefix}-${groupIndex}`}
      className={`${choiceGridClass(variant, compactChoices)} ${groupIndex > 0 ? "prompt-choices-secondary" : ""}`}
    >
      {group.map((choice) => {
        const normalized = normalizeChoiceText(prompt, choice, promptText);
        const body = splitChoiceBodyText(normalized.description);
        const secondary = isSecondaryChoice(choice);
        return (
          <button
            type="button"
            key={choice.choiceId}
            className={`prompt-choice-card prompt-choice-card-emphasis ${secondary ? "prompt-choice-card-secondary" : ""}`}
            data-testid={`${testIdPrefix}-${choice.choiceId}`}
            data-choice-id={choice.choiceId}
            data-choice-title={normalized.title}
            data-choice-description={normalized.description || undefined}
            onClick={() => onSelectChoice(choice.choiceId)}
            disabled={busy}
          >
            <div className="prompt-choice-topline">
              <strong>{normalized.title}</strong>
              {secondary ? <span className="prompt-choice-badge">{promptText.secondaryChoiceBadge}</span> : null}
            </div>
            {renderExtra ? renderExtra(choice) : null}
            {normalized.description ? (
              <div className="prompt-choice-body">
                {body.eyebrow ? <span className="prompt-choice-eyebrow">{body.eyebrow}</span> : null}
                {body.summary ? <p className="prompt-choice-summary">{body.summary}</p> : null}
                {body.detail ? <small className="prompt-choice-detail">{body.detail}</small> : null}
              </div>
            ) : null}
          </button>
        );
      })}
    </div>
  );

  return (
    <>
      {groups.map(renderGroup)}
      {secondaryChoices.length > 0 && !mergeSecondaryChoices && !collapseSecondaryChoices ? renderGroup(secondaryChoices, 1) : null}
      {secondaryChoices.length > 0 && !mergeSecondaryChoices && collapseSecondaryChoices ? (
        <details className="prompt-choice-secondary-group">
          <summary>{promptText.secondaryChoiceBadge}</summary>
          {renderGroup(secondaryChoices, 1)}
        </details>
      ) : null}
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
      <SummaryPills values={summaryPills} />
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
  mergeSecondaryChoices?: boolean;
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
  mergeSecondaryChoices = false,
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
        mergeSecondaryChoices={mergeSecondaryChoices}
      />
    </ChoiceSection>
  );
}

export function PromptOverlay({
  prompt,
  markTargetCandidates = [],
  collapsed,
  busy,
  secondsLeft,
  feedbackMessage,
  compactChoices = false,
  presentationMode = "decision-focus",
  effectContext = null,
  onToggleCollapse,
  onSelectChoice,
}: PromptOverlayProps) {
  const { prompt: promptText, promptType, promptHelper, locale } = useI18n();
  const rootRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [movementMode, setMovementMode] = useState<"roll" | "cards">("roll");
  const [selectedCards, setSelectedCards] = useState<number[]>([]);
  const [selectedBurdenDeckIndexes, setSelectedBurdenDeckIndexes] = useState<number[]>([]);
  const [selectedActiveFlipChoiceIds, setSelectedActiveFlipChoiceIds] = useState<string[]>([]);
  const [lapRewardSelection, setLapRewardSelection] = useState<LapRewardSelection>({
    cashUnits: 0,
    shardUnits: 0,
    coinUnits: 0,
  });

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
  const burdenChoiceCards = useMemo(() => {
    if (!prompt || prompt.requestType !== "burden_exchange") {
      return [];
    }
    if (prompt.surface.burdenExchangeBatch) {
      return prompt.surface.burdenExchangeBatch.cards
        .map((card, index) => ({
          key: `${card.deckIndex ?? index}-${card.name}`,
          deckIndex: card.deckIndex,
          name: card.name,
          description: card.description,
          burdenCost: card.burdenCost,
          isCurrentTarget: card.isCurrentTarget,
        }))
        .sort((left, right) => {
          if (left.isCurrentTarget !== right.isCurrentTarget) {
            return left.isCurrentTarget ? -1 : 1;
          }
          if (left.deckIndex === null || right.deckIndex === null) {
            return left.name.localeCompare(right.name);
          }
          return left.deckIndex - right.deckIndex;
        });
    }
    return buildBurdenChoiceCards(prompt);
  }, [prompt]);
  const lapRewardOptions = useMemo(() => {
    if (!prompt || prompt.requestType !== "lap_reward") {
      return new Map<string, LapRewardOption>();
    }
    const options = new Map<string, LapRewardOption>();
    const rewardOptions =
      prompt.surface.lapReward?.options ??
      prompt.choices.map((choice) => ({
        choiceId: choice.choiceId,
        cashUnits: asNumber(choice.value?.["cash_units"]) ?? 0,
        shardUnits: asNumber(choice.value?.["shard_units"]) ?? 0,
        coinUnits: asNumber(choice.value?.["coin_units"]) ?? 0,
        spentPoints: asNumber(choice.value?.["spent_points"]) ?? 0,
      }));
    for (const option of rewardOptions) {
      options.set(
        lapRewardSelectionKey({
          cashUnits: option.cashUnits,
          shardUnits: option.shardUnits,
          coinUnits: option.coinUnits,
        }),
        {
          choiceId: option.choiceId,
          cashUnits: option.cashUnits,
          shardUnits: option.shardUnits,
          coinUnits: option.coinUnits,
          spentPoints: option.spentPoints,
        }
      );
    }
    return options;
  }, [prompt]);
  const orderedChoices = useMemo(() => (prompt ? sortChoicesForDisplay(prompt.choices) : []), [prompt]);
  const orderedChoiceMap = useMemo(() => new Map(orderedChoices.map((choice) => [choice.choiceId, choice] as const)), [orderedChoices]);
  const projectSurfaceOrderedChoices = (choiceIds: string[]) =>
    choiceIds
      .map((choiceId) => orderedChoiceMap.get(choiceId) ?? null)
      .filter((choice): choice is PromptChoiceViewModel => choice !== null);
  const displayedMarkChoices = useMemo(() => {
    if (!prompt || prompt.requestType !== "mark_target") {
      return orderedChoices;
    }
    const orderedSurfaceCandidates = prompt.surface.markTarget?.candidates ?? [];
    if (orderedSurfaceCandidates.length > 0) {
      const matchedChoices = orderedSurfaceCandidates
        .map((candidate) => orderedChoiceMap.get(candidate.choiceId) ?? null)
        .filter((choice): choice is PromptChoiceViewModel => choice !== null);
      const noneChoice =
        prompt.surface.markTarget?.noneChoiceId
          ? orderedChoiceMap.get(prompt.surface.markTarget.noneChoiceId) ?? null
          : null;
      return noneChoice ? [...matchedChoices, noneChoice] : matchedChoices;
    }
    const noneChoices = orderedChoices.filter((choice) => choice.choiceId === "none");
    const fallbackChoices = orderedChoices.filter((choice) => choice.choiceId !== "none");
    if (markTargetCandidates.length === 0) {
      return [...fallbackChoices, ...noneChoices];
    }
    const choiceByCharacter = new Map<string, PromptChoiceViewModel>();
    for (const choice of orderedChoices) {
      if (choice.choiceId === "none") {
        continue;
      }
      const key = asString(choice.value?.["target_character"]) || choice.choiceId || choice.title;
      if (key) {
        choiceByCharacter.set(key, choice);
      }
    }
    const matchedChoices = markTargetCandidates
      .map((candidate) => choiceByCharacter.get(candidate.character) ?? null)
      .filter((choice): choice is PromptChoiceViewModel => choice !== null);
    return matchedChoices.length > 0 ? [...matchedChoices, ...noneChoices] : noneChoices;
  }, [prompt, orderedChoices, orderedChoiceMap, markTargetCandidates]);

  useEffect(() => {
    if (!prompt) {
      if (previousFocusRef.current) {
        previousFocusRef.current.focus();
        previousFocusRef.current = null;
      }
      setSelectedCards([]);
      setMovementMode("roll");
      setSelectedBurdenDeckIndexes([]);
      setSelectedActiveFlipChoiceIds([]);
      return;
    }
    setSelectedCards([]);
    setMovementMode("roll");
    const currentBurdenDeckIndex =
      typeof prompt.publicContext["card_deck_index"] === "number"
        ? (prompt.publicContext["card_deck_index"] as number)
        : null;
    setSelectedBurdenDeckIndexes(currentBurdenDeckIndex === null ? [] : [currentBurdenDeckIndex]);
    setSelectedActiveFlipChoiceIds([]);
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
  const basePromptHelp = promptHelperForType(prompt.requestType, promptHelper);
  const usesSpecializedSurface = isSpecializedPromptType(prompt.requestType);
  const promptTimeRatio =
    secondsLeft !== null && prompt.timeoutMs > 0
      ? Math.max(0, Math.min(100, (secondsLeft * 1000 * 100) / prompt.timeoutMs))
      : null;
  const headMetaPills = promptText.requestCompactMetaPills(prompt.playerId, secondsLeft).slice(0, 2);
  const effectAttribution = effectContext ? effectAttributionLabel(effectContext, promptText) : null;

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

  const onToggleActiveFlipChoice = (choiceId: string) => {
    setSelectedActiveFlipChoiceIds((prev) =>
      prev.includes(choiceId) ? prev.filter((item) => item !== choiceId) : [...prev, choiceId]
    );
  };

  const onToggleBurdenCard = (deckIndex: number | null) => {
    if (deckIndex === null) {
      return;
    }
    setSelectedBurdenDeckIndexes((prev) =>
      prev.includes(deckIndex) ? prev.filter((item) => item !== deckIndex) : [...prev, deckIndex].sort((a, b) => a - b)
    );
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
  const activeFlipFinishChoiceId = isActiveFlip ? prompt.surface.activeFlip?.finishChoiceId ?? "none" : null;
  const activeFlipFinishChoice =
    isActiveFlip && activeFlipFinishChoiceId
      ? orderedChoices.find((choice) => choice.choiceId === activeFlipFinishChoiceId) ?? null
      : null;
  const activeFlipSelectableChoices = isActiveFlip
    ? (() => {
        if (prompt.surface.activeFlip?.options && prompt.surface.activeFlip.options.length > 0) {
          return projectSurfaceOrderedChoices(prompt.surface.activeFlip.options.map((option) => option.choiceId));
        }
        return orderedChoices.filter((choice) => choice.choiceId !== "none");
      })()
    : [];
  const characterPickChoices =
    isCharacterPick && prompt.surface.characterPick?.options && prompt.surface.characterPick.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.characterPick.options.map((option) => option.choiceId))
      : orderedChoices;
  const trickTileTargetChoices =
    isTrickTileTarget && prompt.surface.trickTileTarget?.options && prompt.surface.trickTileTarget.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.trickTileTarget.options.map((option) => option.choiceId))
      : orderedChoices;
  const coinPlacementChoices =
    isCoinPlacement && prompt.surface.coinPlacement?.options && prompt.surface.coinPlacement.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.coinPlacement.options.map((option) => option.choiceId))
      : orderedChoices;
  const doctrineReliefChoices =
    isDoctrineRelief && prompt.surface.doctrineRelief?.options && prompt.surface.doctrineRelief.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.doctrineRelief.options.map((option) => option.choiceId))
      : orderedChoices;
  const geoBonusChoices =
    isGeoBonus && prompt.surface.geoBonus?.options && prompt.surface.geoBonus.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.geoBonus.options.map((option) => option.choiceId))
      : orderedChoices;
  const specificTrickRewardChoices =
    isSpecificTrickReward && prompt.surface.specificTrickReward?.options && prompt.surface.specificTrickReward.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.specificTrickReward.options.map((option) => option.choiceId))
      : orderedChoices;
  const pabalDiceModeChoices =
    isPabalDiceMode && prompt.surface.pabalDiceMode?.options && prompt.surface.pabalDiceMode.options.length > 0
      ? projectSurfaceOrderedChoices(prompt.surface.pabalDiceMode.options.map((option) => option.choiceId))
      : orderedChoices;
  const runawayChoices =
    isRunawayChoice && prompt.surface.runawayStep
      ? projectSurfaceOrderedChoices(
          [prompt.surface.runawayStep.bonusChoiceId, prompt.surface.runawayStep.stayChoiceId].filter(
            (choiceId): choiceId is string => Boolean(choiceId)
          )
        )
      : orderedChoices;

  const currentTileIndex = numberFromContext(prompt.publicContext, "tile_index", "player_position");
  const currentCash = numberFromContext(prompt.publicContext, "player_cash");
  const currentCost = numberFromContext(prompt.publicContext, "cost", "tile_purchase_cost");
  const currentShards = numberFromContext(prompt.publicContext, "player_shards");
  const purchaseSource = stringFromContext(prompt.publicContext, "source", "purchase_source");
  const isMatchmakerPurchase = isPurchaseTile && isMatchmakerPurchaseSource(purchaseSource);
  const purchaseBaseCost = numberFromContext(prompt.publicContext, "base_cost", "tile_purchase_cost");
  const purchaseMultiplier =
    purchaseBaseCost !== null && currentCost !== null && purchaseBaseCost > 0
      ? Math.round((currentCost / purchaseBaseCost) * 10) / 10
      : currentShards !== null && currentShards >= 8
        ? 1
        : isMatchmakerPurchase
          ? 2
          : null;
  const currentCoins = numberFromContext(prompt.publicContext, "player_hand_coins");
  const currentPlacedCoins = numberFromContext(prompt.publicContext, "player_placed_coins");
  const currentTotalScore = numberFromContext(prompt.publicContext, "player_total_score");
  const currentOwnedTileCount = numberFromContext(prompt.publicContext, "player_owned_tile_count");
  const rewardBudget = prompt.surface.lapReward?.budget ?? numberFromContext(prompt.publicContext, "budget");
  const rewardSurface = prompt.surface.lapReward;
  const rewardCashPool = rewardSurface?.cashPool ?? (numberFromNestedContext(prompt.publicContext, "pools", "cash") ?? 0);
  const rewardShardPool = rewardSurface?.shardsPool ?? (numberFromNestedContext(prompt.publicContext, "pools", "shards") ?? 0);
  const rewardCoinPool = rewardSurface?.coinsPool ?? (numberFromNestedContext(prompt.publicContext, "pools", "coins") ?? 0);
  const rewardCashCost = rewardSurface?.cashPointCost ?? (numberFromContext(prompt.publicContext, "cash_point_cost") ?? 1);
  const rewardShardCost = rewardSurface?.shardsPointCost ?? (numberFromContext(prompt.publicContext, "shards_point_cost") ?? 1);
  const rewardCoinCost = rewardSurface?.coinsPointCost ?? (numberFromContext(prompt.publicContext, "coins_point_cost") ?? 1);
  const lapRewardSpentPoints =
    lapRewardSelection.cashUnits * rewardCashCost +
    lapRewardSelection.shardUnits * rewardShardCost +
    lapRewardSelection.coinUnits * rewardCoinCost;
  const selectedLapRewardChoice =
    lapRewardOptions.get(lapRewardSelectionKey(lapRewardSelection)) ?? null;
  const lapRewardRemaining =
    (rewardSurface?.budget ?? rewardBudget) === null ? null : Math.max(0, (rewardSurface?.budget ?? rewardBudget ?? 0) - lapRewardSpentPoints);

  useEffect(() => {
    if (!prompt || prompt.requestType !== "lap_reward") {
      setLapRewardSelection({ cashUnits: 0, shardUnits: 0, coinUnits: 0 });
      return;
    }
    setLapRewardSelection({ cashUnits: 0, shardUnits: 0, coinUnits: 0 });
  }, [prompt?.requestId, prompt?.requestType]);

  const adjustLapReward = (field: keyof LapRewardSelection, delta: 1 | -1) => {
    setLapRewardSelection((current) => {
      const currentValue = current[field];
      const nextValue = Math.max(0, currentValue + delta);
      if (nextValue === currentValue) {
        return current;
      }
      const candidate = { ...current, [field]: nextValue };
      const poolLimit =
        field === "cashUnits" ? rewardCashPool : field === "shardUnits" ? rewardShardPool : rewardCoinPool;
      if (nextValue > poolLimit) {
        return current;
      }
      const nextSpent =
        candidate.cashUnits * rewardCashCost +
        candidate.shardUnits * rewardShardCost +
        candidate.coinUnits * rewardCoinCost;
      if (rewardBudget !== null && nextSpent > rewardBudget) {
        return current;
      }
      if (nextSpent > 0 && !lapRewardOptions.has(lapRewardSelectionKey(candidate))) {
        return current;
      }
      return candidate;
    });
  };
  const currentZone = stringFromContext(prompt.publicContext, "tile_zone");
  const weatherName = stringFromContext(prompt.publicContext, "weather_name");
  const markActorName = stringFromContext(prompt.publicContext, "actor_name");
  const markTargetCount = numberFromContext(prompt.publicContext, "target_count");
  const burdenSurface = prompt.surface.burdenExchangeBatch;
  const currentFValue = burdenSurface?.currentFValue ?? numberFromContext(prompt.publicContext, "current_f_value");
  const supplyThreshold = burdenSurface?.supplyThreshold ?? numberFromContext(prompt.publicContext, "supply_threshold");
  const burdenTrigger = promptText.context.burdenExchangeTrigger(supplyThreshold, currentFValue);
  const markCandidateCount = prompt.choices.filter((choice) => choice.choiceId !== "none").length;
  const doctrineCandidateCount = prompt.surface.doctrineRelief?.candidateCount ?? numberFromContext(prompt.publicContext, "candidate_count") ?? markCandidateCount;
  const trickTargetCandidateCount = prompt.surface.trickTileTarget?.candidateTiles.length ?? numberFromContext(prompt.publicContext, "candidate_count");
  const trickTargetScope = stringFromContext(prompt.publicContext, "target_scope");
  const trickTargetCardName = stringFromContext(prompt.publicContext, "card_name");
  const movementPosition = numberFromContext(prompt.publicContext, "player_position");
  const runawayOneShortPos = numberFromContext(prompt.publicContext, "one_short_pos");
  const runawayBonusTargetPos = numberFromContext(prompt.publicContext, "bonus_target_pos");
  const runawayBonusTargetKind = stringFromContext(prompt.publicContext, "bonus_target_kind");
  const ownedTileIndices = Array.isArray(prompt.publicContext["owned_tile_indices"])
    ? prompt.publicContext["owned_tile_indices"].map((item) => asNumber(item)).filter((item): item is number => item !== null)
    : [];
  const ownedTileCount = prompt.surface.coinPlacement?.ownedTileCount ?? ownedTileIndices.length;
  const rewardPools = rewardSurface
    ? {
        cash: rewardSurface.cashPool,
        shards: rewardSurface.shardsPool,
        coins: rewardSurface.coinsPool,
      }
    : isRecord(prompt.publicContext["pools"])
      ? prompt.publicContext["pools"]
      : null;
  const rewardPoolSummary = rewardPools
    ? [
        typeof rewardPools["cash"] === "number" ? `${promptText.choice.cashReward(rewardPools["cash"] as number)}=2P` : null,
        typeof rewardPools["shards"] === "number" ? `${promptText.choice.shardReward(rewardPools["shards"] as number)}=3P` : null,
        typeof rewardPools["coins"] === "number" ? `${promptText.choice.coinReward(rewardPools["coins"] as number)}=3P` : null,
      ]
        .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
        .join(" / ")
    : "";
  const draftPhase = prompt.surface.characterPick?.draftPhase ?? numberFromContext(prompt.publicContext, "draft_phase");
  const offeredCount = prompt.surface.characterPick?.choiceCount ?? numberFromContext(prompt.publicContext, "offered_count");
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
  const landingTileIndex = numberFromContext(prompt.publicContext, "player_position", "landing_tile_index");
  const purchaseTargetTiles =
    isPurchaseTile
      ? [currentTileIndex, ...targetTiles].filter(
          (tile, index, items): tile is number => tile !== null && items.indexOf(tile) === index
        )
      : targetTiles;
  const yesChoice = prompt.choices.find((choice) => choice.choiceId === "yes") ?? null;
  const noChoice = prompt.choices.find((choice) => choice.choiceId === "no") ?? null;
  const selectedBurdenCards = burdenChoiceCards.filter(
    (card) => card.deckIndex !== null && selectedBurdenDeckIndexes.includes(card.deckIndex)
  );
  const selectedBurdenCount = selectedBurdenCards.length;
  const selectedBurdenTotalCost = selectedBurdenCards.reduce((sum, card) => sum + (card.burdenCost ?? 0), 0);
  const canRemoveSelectedBurden =
    yesChoice !== null &&
    selectedBurdenCount > 0 &&
    currentCash !== null &&
    selectedBurdenTotalCost <= currentCash &&
    !busy;
  const burdenTrayTitle = locale.startsWith("ko") ? "보급 잔꾀 패" : "Supply trick tray";
  const burdenTrayGuide = locale.startsWith("ko")
    ? "제거할 짐을 2장이나 3장까지 한 번에 고르면, 나머지 보급 처리도 자동으로 이어집니다."
    : "Pick two or three burdens together and the remaining supply cleanup will continue automatically.";
  const promptHelp =
    prompt.requestType === "draft_card"
      ? draftPhase === 2
        ? promptText.character.draftReversePrompt(offeredCount)
        : promptText.character.draftForwardPrompt(offeredCount)
      : basePromptHelp;
  const burdenRemoveButtonLabel = locale.startsWith("ko")
    ? "선택한 짐 없애기"
    : "Remove selected burdens";
  const burdenKeepButtonLabel = locale.startsWith("ko") ? "이번에는 유지" : "Keep it this time";
  const burdenRemoveSummary =
    selectedBurdenCount > 0
      ? locale.startsWith("ko")
        ? `${selectedBurdenCount}장 / 총 ${selectedBurdenTotalCost}냥`
        : `${selectedBurdenCount} card(s) / total ${selectedBurdenTotalCost}`
      : locale.startsWith("ko")
        ? "선택 없음"
        : "No selection";
  const burdenSelectionGuide =
    selectedBurdenCount > 0
      ? locale.startsWith("ko")
        ? `선택한 짐 ${selectedBurdenCount}장을 이번 보급 단계에서 한 번에 처리합니다.`
        : `Resolve ${selectedBurdenCount} selected burden card(s) for this supply step.`
      : locale.startsWith("ko")
        ? "제거할 짐을 1장 이상 선택하세요."
        : "Choose at least one burden card to remove.";
  const burdenSelectionBlockedGuide =
    currentCash !== null && selectedBurdenCount > 0 && selectedBurdenTotalCost > currentCash
      ? locale.startsWith("ko")
        ? `총 제거 비용 ${selectedBurdenTotalCost}냥이 현재 현금 ${currentCash}냥을 넘습니다.`
        : `Total removal cost ${selectedBurdenTotalCost} exceeds current cash ${currentCash}.`
      : "";

  if (collapsed) {
    return (
      <section
        className="panel prompt-dock-collapsed"
        data-testid="prompt-dock-collapsed"
        data-presentation-mode={presentationMode}
      >
        <div className="prompt-dock-collapsed-copy">
          <strong>{promptText.headTitle(promptLabel)}</strong>
          <small>{collapsedPromptChip(promptText, promptLabel, secondsLeft)}</small>
        </div>
        <button type="button" className="prompt-dock-collapsed-button" onClick={onToggleCollapse}>
          {promptText.expand}
        </button>
      </section>
    );
  }

  return (
    <section
      ref={rootRef}
      className={`panel prompt-overlay prompt-overlay-docked prompt-overlay-${prompt.requestType}${
        isMatchmakerPurchase ? " prompt-overlay-purchase-matchmaker" : ""
      }`}
      data-testid="prompt-overlay"
      data-prompt-type={prompt.requestType}
      data-purchase-source={purchaseSource || undefined}
      data-effect-character={isMatchmakerPurchase ? "중매꾼" : undefined}
      data-presentation-mode={presentationMode}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      role="region"
      aria-busy={busy}
    >
        <div className="prompt-topbar">
          {promptTimeRatio !== null ? (
            <div className="prompt-timebar prompt-timebar-top" aria-hidden="true">
              <span style={{ width: `${promptTimeRatio}%` }} />
            </div>
          ) : (
            <div className="prompt-timebar prompt-timebar-top prompt-timebar-top-idle" aria-hidden="true">
              <span style={{ width: "0%" }} />
            </div>
          )}
          <div className="prompt-topbar-side">
            <div className="prompt-head-meta" data-testid="prompt-head-meta">
              {headMetaPills.map((pill, index) => (
                <span key={pill} className="prompt-head-pill" data-tone={classifyPromptPill(pill, "head", index)}>
                  {pill}
                </span>
              ))}
            </div>
            <button type="button" onClick={onToggleCollapse} data-testid="prompt-overlay-collapse">
              {promptText.collapse}
            </button>
          </div>
        </div>

        <div className="prompt-head">
          <div className="prompt-head-copy">
            <h2 data-testid="prompt-overlay-title">{promptText.headTitle(promptLabel)}</h2>
            <p className="prompt-helper" data-testid="prompt-overlay-helper">
              {promptHelp}
            </p>
            {feedbackMessage ? <p className="prompt-head-status prompt-head-status-error">{cleanDisplayText(feedbackMessage)}</p> : null}
            {busy ? (
              <p className="prompt-head-status prompt-head-status-busy">
                <span className="spinner" aria-hidden="true" /> {promptText.busy}
              </p>
            ) : null}
          </div>
        </div>

        <div className="prompt-body">
          {effectContext ? (
            <section
              className={`prompt-effect-context prompt-effect-context-${effectContext.tone}`}
              data-testid="prompt-effect-context"
              data-effect-source={effectContext.source}
              data-effect-intent={effectContext.intent}
              data-effect-enhanced={effectContext.enhanced ? "true" : "false"}
            >
              <div className="prompt-effect-context-meta">
                <span>{promptText.effectContextLabel}</span>
                {effectAttribution ? <strong>{effectAttribution}</strong> : null}
              </div>
              <div className="prompt-effect-context-copy">
                <strong>{cleanDisplayText(effectContext.label)}</strong>
                {cleanDisplayText(effectContext.detail) !== cleanDisplayText(effectContext.label) ? (
                  <p>{cleanDisplayText(effectContext.detail)}</p>
                ) : null}
              </div>
            </section>
          ) : null}

        {prompt.requestType === "movement" && movement ? (
          <section className="prompt-section prompt-movement-stage">
            <div className="prompt-section-summary">
              {movementMode === "cards" ? (
                <p>{cleanDisplayText(promptText.movement.cardGuide(movement.canUseTwoCards ? 2 : 1))}</p>
              ) : null}
              <div className="prompt-summary-pill-row">
                {movementMode === "cards" ? (
                  <span className="prompt-summary-pill" data-tone="decision">
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
                data-choice-id={movementMode === "roll" ? movement.rollChoice?.choiceId ?? "roll" : movementSelectedChoice?.choiceId ?? undefined}
                data-movement-mode={movementMode}
                data-selected-cards={movementMode === "cards" && selectedCards.length > 0 ? selectedCards.join(",") : undefined}
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
          <section className="prompt-section prompt-hand-stage prompt-hand-stage-trick">
            <div className="prompt-section-summary">
              <div className="prompt-inline-summary">
                <p>{cleanDisplayText(prompt.requestType === "trick_to_use" ? promptText.trick.usePrompt : promptText.trick.hiddenPrompt)}</p>
                <div className="prompt-summary-pill-row">
                  <span className="prompt-summary-pill" data-tone="resource">
                    {promptText.trick.handSummary(
                      typeof prompt.publicContext["total_hand_count"] === "number"
                        ? (prompt.publicContext["total_hand_count"] as number)
                        : trickChoices.cards.length,
                      typeof prompt.publicContext["hidden_trick_count"] === "number"
                        ? (prompt.publicContext["hidden_trick_count"] as number)
                        : undefined
                    )}
                  </span>
                </div>
              </div>
            </div>
            <div
              className={`prompt-choices hand-grid ${
                prompt.requestType === "trick_to_use" ? "hand-grid-trick-to-use" : "hand-grid-hidden-trick"
              }`}
            >
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

              {trickChoices.cards.map((card) => {
                const canSelectCard =
                  prompt.requestType === "hidden_trick_card" ? Boolean(card.choiceId) : card.isUsable && Boolean(card.choiceId);

                return (
                  <button
                    type="button"
                    key={card.key}
                    className={`prompt-choice-card ${card.isHidden ? "hand-card-hidden" : ""}`}
                    data-testid={`trick-choice-${card.key}`}
                    data-card-name={card.name}
                    data-card-visibility={card.isHidden ? "hidden" : "public"}
                    disabled={busy || !canSelectCard}
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
                    <small>{cleanCardDescription(card.description)}</small>
                    {!card.isUsable && prompt.requestType !== "hidden_trick_card" ? (
                      <small className="prompt-choice-footnote">{promptText.hiddenState.unavailable}</small>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {isCharacterPick ? (
          <section className="prompt-section prompt-hand-stage">
            {(() => {
              const characterPickOptions: Array<CharacterPickOption> =
                prompt.surface.characterPick?.options ??
                characterPickChoices.map((choice) => ({
                  choiceId: choice.choiceId,
                  name: choice.title,
                  description: characterAbilityText(choice, promptText),
                }));

              return (
            <div className={`prompt-choices prompt-character-card-grid ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {characterPickOptions.map((choice) => (
                (() => {
                  const body = splitChoiceBodyText(choice.description);
                  const prioritySlot = prioritySlotForCharacterName(choice.name);
                  const priorityLabel = isKoreanLocale(locale) ? "우선권" : "Priority";
                  const portraitIndex = portraitIndexForCharacter(choice.name);
                  const portraitCol = portraitIndex % 4;
                  const portraitRow = Math.floor(portraitIndex / 4);

                  return (
                  <button
                    type="button"
                    key={choice.choiceId}
                    className="prompt-choice-card prompt-choice-card-emphasis prompt-character-card"
                    data-testid={`character-choice-${choice.choiceId}`}
                    onClick={() => onSelectChoice(choice.choiceId)}
                    disabled={busy}
                >
                    <div className="prompt-character-card-frame">
                      <div className="prompt-character-card-top">
                        <span className="prompt-character-card-priority">
                          {priorityLabel} {prioritySlot ?? "-"}
                        </span>
                      </div>
                      <div
                        className="prompt-character-card-art"
                        aria-hidden="true"
                        style={
                          {
                            "--character-portrait-url": `url(${characterPortraitSpriteUrl})`,
                            "--character-portrait-x": `${portraitCol * 33.333333}%`,
                            "--character-portrait-y": `${portraitRow * 33.333333}%`,
                          } as CSSProperties
                        }
                      >
                        <span>{Array.from(choice.name.trim())[0] ?? "?"}</span>
                      </div>
                      <div className="prompt-character-card-body">
                        <strong>{choice.name}</strong>
                        <div className="prompt-choice-body">
                          {body.summary ? <p className="prompt-choice-summary">{body.summary}</p> : null}
                          {body.detail ? <small className="prompt-choice-detail">{body.detail}</small> : null}
                        </div>
                      </div>
                    </div>
                  </button>
                  );
                })()
              ))}
            </div>
              );
            })()}
          </section>
        ) : null}

        {isMarkTarget ? (
          <section className="prompt-section prompt-hand-stage">
            <div className={`prompt-choices prompt-choices-mark ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {displayedMarkChoices
                .filter((choice) => choice.choiceId !== "none")
                .map((choice) => {
                const target = markChoiceTarget(choice);
                const body = splitChoiceBodyText(markChoiceDescription(choice, promptText));
                return (
                  <button
                    type="button"
                    key={choice.choiceId}
                    className="prompt-choice-card prompt-choice-card-emphasis prompt-choice-card-mark"
                    data-testid={`mark-choice-${choice.choiceId}`}
                    data-choice-id={choice.choiceId}
                    data-target-character={target.character || undefined}
                    data-target-player-id={target.playerId !== null ? String(target.playerId) : undefined}
                    data-target-card-no={target.cardNo !== null ? String(target.cardNo) : undefined}
                    onClick={() => onSelectChoice(choice.choiceId)}
                    disabled={busy}
                  >
                    <div className="prompt-choice-topline">
                      <strong>{markChoiceTitle(choice, promptText)}</strong>
                      <span className="prompt-choice-badge">{locale === "ko" ? "지목 대상" : "Target"}</span>
                    </div>
                    <div className="prompt-summary-pill-row prompt-summary-pill-row-compact">
                      {target.playerId !== null ? <span className="prompt-summary-pill" data-tone="player">P{target.playerId}</span> : null}
                      {target.cardNo !== null ? <span className="prompt-summary-pill" data-tone="target">#{target.cardNo}</span> : null}
                    </div>
                    <div className="prompt-choice-body">
                      {body.eyebrow ? <span className="prompt-choice-eyebrow">{body.eyebrow}</span> : null}
                      <p className="prompt-choice-summary">{body.summary}</p>
                      {body.detail ? <small className="prompt-choice-detail">{body.detail}</small> : null}
                    </div>
                  </button>
                );
              })}
            </div>
            {displayedMarkChoices.some((choice) => choice.choiceId === "none") ? (
              <div className="prompt-primary-row">
                {displayedMarkChoices
                  .filter((choice) => choice.choiceId === "none")
                  .map((choice) => (
                    <button
                      type="button"
                      key={choice.choiceId}
                      className="prompt-secondary-action"
                      data-testid={`mark-choice-${choice.choiceId}`}
                      data-choice-id={choice.choiceId}
                      data-choice-title={markChoiceTitle(choice, promptText)}
                      onClick={() => onSelectChoice(choice.choiceId)}
                      disabled={busy}
                    >
                      {markChoiceTitle(choice, promptText)}
                    </button>
                  ))}
              </div>
            ) : null}
          </section>
        ) : null}

        {isPurchaseTile ? (
          <>
            {isMatchmakerPurchase ? (
              <section className="prompt-section-summary prompt-purchase-special" data-testid="matchmaker-purchase-context">
                <div className="prompt-summary-pill-row">
                  <span className="prompt-summary-pill" data-tone="character">중매꾼 추가 구매</span>
                  <span className="prompt-summary-pill" data-tone={purchaseMultiplier === 2 ? "danger" : "decision"}>
                    {purchaseMultiplier === 2 ? "2배 가격" : "기본가 적용"}
                  </span>
                  {purchaseBaseCost !== null && currentCost !== null ? (
                    <span className="prompt-summary-pill" data-tone="resource">
                      {`기본 ${formatNumber(purchaseBaseCost)} -> 비용 ${formatNumber(currentCost)}`}
                    </span>
                  ) : null}
                </div>
                <p>
                  {purchaseMultiplier === 2
                    ? "중매꾼 능력으로 발생한 두 번째 구매입니다. 조각 조건이 부족하면 인접 토지는 2배 가격으로 구매합니다."
                    : "중매꾼 능력으로 발생한 두 번째 구매입니다. 조각 조건을 만족해 인접 토지를 기본가로 구매합니다."}
                </p>
              </section>
            ) : null}
            <DecisionChoiceSection
              prompt={prompt}
              orderedChoices={orderedChoices}
              promptText={promptText}
              compactChoices={compactChoices}
              busy={busy}
              onSelectChoice={onSelectChoice}
              testIdPrefix="purchase-choice"
              variant="decision"
              mergeSecondaryChoices
              summaryPills={[
                `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
                isMatchmakerPurchase ? "중매꾼 추가 구매" : null,
                isMatchmakerPurchase && purchaseMultiplier !== null
                  ? purchaseMultiplier === 2
                    ? "2배 가격"
                    : "기본가 적용"
                  : null,
              ]}
              renderExtra={() => null}
            />
          </>
        ) : null}

        {isLapReward ? (
          <section className="prompt-section prompt-hand-stage">
            <div className="prompt-section-summary">
              <div className="prompt-summary-pill-row">
                {rewardBudget !== null ? (
                  <span className="prompt-summary-pill" data-tone="decision">{`${promptText.context.rewardBudget}: ${lapRewardSpentPoints}/${rewardBudget}`}</span>
                ) : null}
                {lapRewardRemaining !== null ? (
                  <span className="prompt-summary-pill" data-tone="resource">
                    {isKoreanLocale(locale) ? `남은 포인트: ${lapRewardRemaining}` : `Remaining points: ${lapRewardRemaining}`}
                  </span>
                ) : null}
                {rewardPoolSummary ? (
                  <span className="prompt-summary-pill" data-tone="resource">{`${promptText.context.rewardPools}: ${rewardPoolSummary}`}</span>
                ) : null}
              </div>
            </div>
            <div className="prompt-lap-reward-builder">
              {[
                {
                  key: "cashUnits" as const,
                  label: isKoreanLocale(locale) ? "현금" : "Cash",
                  units: lapRewardSelection.cashUnits,
                  pool: rewardCashPool,
                  cost: rewardCashCost,
                },
                {
                  key: "shardUnits" as const,
                  label: isKoreanLocale(locale) ? "조각" : "Shards",
                  units: lapRewardSelection.shardUnits,
                  pool: rewardShardPool,
                  cost: rewardShardCost,
                },
                {
                  key: "coinUnits" as const,
                  label: isKoreanLocale(locale) ? "승점" : "Points",
                  units: lapRewardSelection.coinUnits,
                  pool: rewardCoinPool,
                  cost: rewardCoinCost,
                },
              ].map((item) => (
                <article key={item.key} className="prompt-lap-reward-card">
                  <div className="prompt-lap-reward-head">
                    <strong>{item.label}</strong>
                    <span className="prompt-choice-badge">
                      {isKoreanLocale(locale)
                        ? `1개당 ${item.cost}포인트`
                        : `${item.cost} points each`}
                    </span>
                  </div>
                  <div className="prompt-lap-reward-controls">
                    <button
                      type="button"
                      className="prompt-lap-adjust"
                      disabled={busy || item.units <= 0}
                      onClick={() => adjustLapReward(item.key, -1)}
                    >
                      -
                    </button>
                    <div className="prompt-lap-reward-value">
                      <span>{item.units}</span>
                      <small>
                        {isKoreanLocale(locale) ? `남은 풀 ${item.pool}` : `Pool ${item.pool}`}
                      </small>
                    </div>
                    <button
                      type="button"
                      className="prompt-lap-adjust"
                      disabled={busy}
                      onClick={() => adjustLapReward(item.key, 1)}
                    >
                      +
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div className="prompt-lap-reward-summary">
              <strong>
                {isKoreanLocale(locale)
                  ? `현금 +${lapRewardSelection.cashUnits} / 조각 +${lapRewardSelection.shardUnits} / 승점 +${lapRewardSelection.coinUnits}`
                  : `Cash +${lapRewardSelection.cashUnits} / Shards +${lapRewardSelection.shardUnits} / Points +${lapRewardSelection.coinUnits}`}
              </strong>
              <small>
                {selectedLapRewardChoice
                  ? isKoreanLocale(locale)
                    ? "현재 조합으로 결정할 수 있습니다."
                    : "This allocation is ready to confirm."
                  : isKoreanLocale(locale)
                    ? "가능한 조합이 되도록 포인트를 조절하세요."
                    : "Adjust to a valid allocation."}
              </small>
              <button
                type="button"
                className="prompt-primary-action"
                disabled={busy || !selectedLapRewardChoice}
                onClick={() => {
                  if (selectedLapRewardChoice) {
                    onSelectChoice(selectedLapRewardChoice.choiceId);
                  }
                }}
              >
                {isKoreanLocale(locale) ? "결정" : "Confirm"}
              </button>
            </div>
          </section>
        ) : null}

        {isTrickTileTarget ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={trickTileTargetChoices}
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
                  <span className="prompt-summary-pill" data-tone="target">{tileLabel(tileIndex)}</span>
                </div>
              ) : null;
            }}
          />
        ) : null}

        {isActiveFlip ? (
          <section className="prompt-section prompt-hand-stage">
            <div className={`prompt-choices hand-grid active-flip-grid ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {activeFlipSelectableChoices.map((choice) => (
                <button
                  type="button"
                  key={choice.choiceId}
                  className={`prompt-choice-card ${selectedActiveFlipChoiceIds.includes(choice.choiceId) ? "prompt-choice-card-selected" : ""}`}
                  data-testid={`active-flip-choice-${choice.choiceId}`}
                  disabled={busy}
                  onClick={() => onToggleActiveFlipChoice(choice.choiceId)}
                >
                  <strong>{choice.title}</strong>
                  {choiceDescription(choice, promptText) ? (
                    (() => {
                      const body = splitChoiceBodyText(choiceDescription(choice, promptText));
                      return (
                        <div className="prompt-choice-body">
                          {body.eyebrow ? <span className="prompt-choice-eyebrow">{body.eyebrow}</span> : null}
                          {body.summary ? <p className="prompt-choice-summary">{body.summary}</p> : null}
                          {body.detail ? <small className="prompt-choice-detail">{body.detail}</small> : null}
                        </div>
                      );
                    })()
                  ) : null}
                  {selectedActiveFlipChoiceIds.includes(choice.choiceId) ? (
                    <small className="prompt-choice-footnote prompt-choice-footnote-selected">
                      {locale.startsWith("ko") ? "선택됨" : "Selected"}
                    </small>
                  ) : null}
                </button>
              ))}
              {activeFlipFinishChoice ? (
                <button
                  type="button"
                  className={`prompt-choice-card prompt-choice-card-pass ${selectedActiveFlipChoiceIds.length === 0 ? "prompt-choice-card-selected" : ""}`}
                  data-testid="active-flip-finish"
                  disabled={busy}
                  onClick={() =>
                    onSelectChoice(
                      selectedActiveFlipChoiceIds.length > 0
                        ? `__active_flip_batch__:${selectedActiveFlipChoiceIds.join(",")}`
                        : activeFlipFinishChoice.choiceId
                    )
                  }
                >
                  <strong>{activeFlipFinishChoice.title}</strong>
                  {choiceDescription(activeFlipFinishChoice, promptText) ? (
                    (() => {
                      const body = splitChoiceBodyText(choiceDescription(activeFlipFinishChoice, promptText));
                      return (
                        <div className="prompt-choice-body">
                          {body.eyebrow ? <span className="prompt-choice-eyebrow">{body.eyebrow}</span> : null}
                          {body.summary ? <p className="prompt-choice-summary">{body.summary}</p> : null}
                          {body.detail ? <small className="prompt-choice-detail">{body.detail}</small> : null}
                        </div>
                      );
                    })()
                  ) : null}
                  <small
                    className={`prompt-choice-footnote ${
                      selectedActiveFlipChoiceIds.length > 0 ? "prompt-choice-footnote-selected" : ""
                    }`}
                  >
                    {selectedActiveFlipChoiceIds.length > 0
                      ? locale.startsWith("ko")
                        ? "선택한 뒤집기 확정"
                        : "Confirm selected flip"
                      : locale.startsWith("ko")
                        ? "더 뒤집지 않고 종료"
                        : "Finish without flipping more"}
                  </small>
                </button>
              ) : null}
            </div>
          </section>
        ) : null}

        {isBurdenExchange ? (
          <section className="prompt-section prompt-burden-stage prompt-burden-stage-compact">
            <div className="prompt-section-summary">
              <SummaryPills
                values={[
                  `${promptText.context.trigger}: ${burdenTrigger}`,
                  `${promptText.context.burdenCard}: ${burdenSurface?.burdenCardCount ?? prompt.publicContext["burden_card_count"] ?? burdenChoiceCards.length}`,
                  `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
                  (burdenSurface?.currentFValue ?? currentFValue) !== null
                    ? `${promptText.context.currentF}: ${burdenSurface?.currentFValue ?? currentFValue}`
                    : null,
                  `${promptText.context.selectedCards}: ${burdenRemoveSummary}`,
                ]}
              />
              <p>{burdenSelectionGuide}</p>
              {burdenSelectionBlockedGuide ? <small className="prompt-choice-footnote">{burdenSelectionBlockedGuide}</small> : null}
            </div>

            <div className="prompt-burden-actions">
              <button
                type="button"
                className="prompt-primary-action"
                data-testid="burden-remove"
                disabled={!canRemoveSelectedBurden}
                onClick={() => {
                  if (yesChoice) {
                    onSelectChoice(`__burden_exchange_batch__:${selectedBurdenDeckIndexes.join(",")}`);
                  }
                }}
              >
                {locale.startsWith("ko")
                  ? `${burdenRemoveButtonLabel} (${burdenRemoveSummary})`
                  : `${burdenRemoveButtonLabel} (${burdenRemoveSummary})`}
              </button>
              <button
                type="button"
                className="prompt-secondary-action"
                data-testid="burden-keep"
                disabled={busy || !noChoice}
                onClick={() => {
                  if (noChoice) {
                    onSelectChoice("__burden_exchange_batch__:");
                  }
                }}
              >
                {burdenKeepButtonLabel}
              </button>
            </div>

            <section className="prompt-burden-tray">
              <div className="prompt-burden-tray-head">
                <strong>{burdenTrayTitle}</strong>
                <small>{burdenTrayGuide}</small>
              </div>
              <div className="prompt-burden-tray-grid">
                {burdenChoiceCards.map((card) => (
                  <button
                    type="button"
                    key={card.key}
                    className={`prompt-choice-card prompt-burden-card ${
                      card.isCurrentTarget ? "prompt-burden-card-current" : ""
                    } ${card.deckIndex !== null && selectedBurdenDeckIndexes.includes(card.deckIndex) ? "prompt-burden-card-selected" : ""}`}
                    data-testid={`burden-card-${card.deckIndex ?? card.key}`}
                    disabled={busy}
                    onClick={() => onToggleBurdenCard(card.deckIndex)}
                  >
                    <div className="prompt-choice-topline">
                      <strong>{card.name}</strong>
                      <span className="prompt-choice-badge">
                        {card.burdenCost !== null
                          ? locale.startsWith("ko")
                            ? `비용 ${card.burdenCost}`
                            : `Cost ${card.burdenCost}`
                          : locale.startsWith("ko")
                            ? "짐"
                            : "Burden"}
                      </span>
                    </div>
                    <small>{cleanCardDescription(cleanDisplayText(card.description))}</small>
                    <small className="prompt-choice-footnote">
                      {card.deckIndex !== null && selectedBurdenDeckIndexes.includes(card.deckIndex)
                        ? locale.startsWith("ko")
                          ? "선택됨"
                          : "Selected"
                        : card.isCurrentTarget
                        ? locale.startsWith("ko")
                          ? "현재 처리 시작 카드"
                          : "Current step starts here"
                        : locale.startsWith("ko")
                          ? "선택 안 됨"
                          : "Not selected"}
                    </small>
                  </button>
                ))}
              </div>
            </section>
          </section>
        ) : null}

        {isSpecificTrickReward ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={specificTrickRewardChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            testIdPrefix="specific-reward-choice"
            summaryPills={[
              `${promptText.context.usableCards}: ${String(prompt.surface.specificTrickReward?.rewardCount ?? prompt.choices.filter((choice) => choice.choiceId !== "none").length)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
            ]}
            renderExtra={() => null}
          />
        ) : null}

        {isRunawayChoice ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={runawayChoices}
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
                    <span
                      key={`${choice.choiceId}-${pill}`}
                      className="prompt-summary-pill"
                      data-tone={classifyPromptPill(pill, "summary")}
                    >
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
            orderedChoices={coinPlacementChoices}
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
                    <span
                      key={`${choice.choiceId}-${pill}`}
                      className="prompt-summary-pill"
                      data-tone={classifyPromptPill(pill, "summary")}
                    >
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
            orderedChoices={doctrineReliefChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="target"
            testIdPrefix="doctrine-relief-choice"
            summaryPills={[
              `${promptText.context.selectableTargets}: ${String(doctrineCandidateCount)}`,
              `${promptText.context.currentCash}: ${formatNumber(currentCash)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
            ]}
            renderExtra={(choice) => {
              const targetPlayerId = asNumber(choice.value?.["target_player_id"]);
              return targetPlayerId !== null ? (
                <div className="prompt-summary-pill-row">
                  <span className="prompt-summary-pill" data-tone="player">P{targetPlayerId}</span>
                </div>
              ) : null;
            }}
          />
        ) : null}

        {isGeoBonus ? (
          <DecisionChoiceSection
            prompt={prompt}
            orderedChoices={geoBonusChoices}
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
            orderedChoices={pabalDiceModeChoices}
            promptText={promptText}
            compactChoices={compactChoices}
            busy={busy}
            onSelectChoice={onSelectChoice}
            variant="decision"
            testIdPrefix="pabal-dice-mode-choice"
            summaryPills={[
              `${promptText.context.currentPosition}: ${tileLabel(movementPosition)}`,
              `${promptText.context.currentShards}: ${currentShards ?? "-"}`,
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
    </section>
  );
}
