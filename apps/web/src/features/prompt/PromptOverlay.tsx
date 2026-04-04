import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { promptHelperForType } from "../../domain/labels/promptHelperCatalog";
import { promptLabelForType } from "../../domain/labels/promptTypeCatalog";
import type { PromptChoiceViewModel, PromptViewModel } from "../../domain/selectors/promptSelectors";

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function choiceDescription(choice: PromptChoiceViewModel): string {
  const text = choice.description.trim();
  return text ? text : "설명이 없습니다.";
}

function parseMovementChoice(choice: PromptChoiceViewModel): { cards: number[] } | null {
  const match = /^card_(\d+)(?:_(\d+))?$/.exec(choice.choiceId);
  if (!match) {
    return null;
  }
  const first = Number(match[1]);
  const second = match[2] ? Number(match[2]) : null;
  if (!Number.isFinite(first)) {
    return null;
  }
  const cards = [first];
  if (second !== null && Number.isFinite(second)) {
    cards.push(second);
  }
  cards.sort((a, b) => a - b);
  return { cards };
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
      /주사위/.test(choice.title);
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

function buildHandChoiceCards(prompt: PromptViewModel): { cards: HandChoiceCard[]; passChoiceId: string | null } {
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
        const name = asString(item["name"], "카드");
        const description = asString(item["card_description"], `${name} 효과`);
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
      description: choiceDescription(choice),
      isHidden: false,
      isUsable: true,
      choiceId: choice.choiceId,
    }));
  return { cards, passChoiceId };
}

function characterAbilityText(choice: PromptChoiceViewModel): string {
  const fromValue =
    asString(choice.value?.["character_ability"]) ||
    asString(choice.value?.["ability_text"]) ||
    asString(choice.value?.["card_description"]);
  if (fromValue) {
    return fromValue;
  }
  if (choice.description.trim()) {
    return choice.description.trim();
  }
  return `${choice.title} 능력`;
}

function markChoiceTitle(choice: PromptChoiceViewModel): string {
  if (choice.choiceId === "none") {
    return "[지목 안 함]";
  }
  return `[${choice.title}]`;
}

function markChoiceDescription(choice: PromptChoiceViewModel): string {
  if (choice.choiceId === "none") {
    return "[이번 턴에는 지목 효과를 사용하지 않습니다.]";
  }
  const targetCharacter = asString(choice.value?.["target_character"]);
  const targetPlayerId = asNumber(choice.value?.["target_player_id"]);
  if (targetCharacter && targetPlayerId !== null) {
    return `[대상 인물 / 플레이어: ${targetCharacter} / P${targetPlayerId}]`;
  }
  return "[지목 대상 정보]";
}

function normalizeChoiceText(
  prompt: PromptViewModel,
  choice: PromptChoiceViewModel
): { title: string; description: string } {
  const fallbackTitle = choice.title.trim() ? choice.title.trim() : choice.choiceId;
  const fallbackDescription = choiceDescription(choice);
  const value = choice.value ?? {};

  if (prompt.requestType === "lap_reward") {
    const reward = asString(value["choice"]).toLowerCase();
    const cashUnits = asNumber(value["cash_units"]) ?? 0;
    const shardUnits = asNumber(value["shard_units"]) ?? 0;
    const coinUnits = asNumber(value["coin_units"]) ?? 0;
    if (reward === "cash" || cashUnits > 0) {
      return { title: "현금 선택", description: `현금 +${cashUnits}` };
    }
    if (reward === "shards" || shardUnits > 0) {
      return { title: "조각 선택", description: `조각 +${shardUnits}` };
    }
    if (reward === "coins" || coinUnits > 0) {
      return { title: "승점 선택", description: `승점 +${coinUnits}` };
    }
    return { title: fallbackTitle, description: fallbackDescription };
  }

  if (prompt.requestType === "purchase_tile") {
    const pos = asNumber(prompt.publicContext["pos"]);
    const cost = asNumber(prompt.publicContext["cost"]);
    if (choice.choiceId === "yes") {
      const detail = pos !== null && cost !== null ? `${pos}번 칸 / 비용 ${cost}` : "도착한 칸을 구매합니다.";
      return { title: "토지 구매", description: detail };
    }
    if (choice.choiceId === "no") {
      return { title: "구매 없이 턴 종료", description: "이번 턴에는 구매하지 않습니다." };
    }
    return { title: fallbackTitle, description: fallbackDescription };
  }

  if (prompt.requestType === "active_flip") {
    if (choice.choiceId === "none") {
      return { title: "뒤집기 종료", description: "이번 라운드 카드 뒤집기를 종료합니다." };
    }
    const currentName = asString(value["current_name"]);
    const flippedName = asString(value["flipped_name"]);
    if (currentName && flippedName) {
      return { title: `${currentName} -> ${flippedName}`, description: "선택한 카드를 즉시 뒤집습니다." };
    }
    return { title: fallbackTitle, description: fallbackDescription };
  }

  if (prompt.requestType === "burden_exchange") {
    if (choice.choiceId === "yes") {
      return { title: "지 카드 제거", description: "비용을 지불하고 지 카드를 제거합니다." };
    }
    if (choice.choiceId === "no") {
      return { title: "유지", description: "이번에는 지 카드를 유지합니다." };
    }
    return { title: fallbackTitle, description: fallbackDescription };
  }

  return { title: fallbackTitle, description: fallbackDescription };
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
    return buildHandChoiceCards(prompt);
  }, [prompt]);

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

  const isCharacterPick = prompt.requestType === "draft_card" || prompt.requestType === "final_character";
  const isMarkTarget = prompt.requestType === "mark_target";

  if (collapsed) {
    return (
      <button type="button" className="prompt-floating-chip" onClick={onToggleCollapse}>
        선택 요청: {promptLabelForType(prompt.requestType)} / 남은 시간 {secondsLeft ?? "-"}초
      </button>
    );
  }

  const overlay = (
    <div className="prompt-modal-layer" role="dialog" aria-modal="true" aria-busy={busy}>
      <div className="prompt-backdrop" />
      <section
        ref={rootRef}
        className={`panel prompt-overlay prompt-overlay-${prompt.requestType}`}
        onKeyDown={onKeyDown}
        tabIndex={-1}
      >
        <div className="prompt-head">
          <h2>선택 요청: {promptLabelForType(prompt.requestType)}</h2>
          <button type="button" onClick={onToggleCollapse}>
            접기
          </button>
        </div>
        <p className="prompt-helper">{promptHelperForType(prompt.requestType)}</p>
        <p>
          요청 ID {prompt.requestId} / 행동자 P{prompt.playerId} / 제한 시간 {Math.ceil(prompt.timeoutMs / 1000)}초 / 남은 시간{" "}
          {secondsLeft ?? "-"}초
        </p>

        {prompt.requestType === "movement" && movement ? (
          <section className="prompt-movement-stage">
            <div className="prompt-move-mode">
              <button
                type="button"
                className={movementMode === "roll" ? "route-tab route-tab-active" : "route-tab"}
                onClick={() => setMovementMode("roll")}
                disabled={busy}
              >
                주사위 굴리기
              </button>
              <button
                type="button"
                className={movementMode === "cards" ? "route-tab route-tab-active" : "route-tab"}
                onClick={() => setMovementMode("cards")}
                disabled={busy || movement.cardPool.length === 0}
              >
                주사위 카드 사용
              </button>
            </div>
            {movementMode === "cards" ? (
              <div className="dice-chip-row">
                <small>사용할 주사위 카드를 선택하세요. 최대 {movement.canUseTwoCards ? "2" : "1"}장까지 사용 가능합니다.</small>
                <div className="dice-chip-list">
                  {movement.cardPool.map((card) => (
                    <button
                      type="button"
                      key={`dice-card-${card}`}
                      className={selectedCards.includes(card) ? "dice-chip dice-chip-selected" : "dice-chip"}
                      disabled={busy}
                      onClick={() => onToggleCardChip(card)}
                    >
                      [{card}]
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <button
              type="button"
              className="prompt-primary-action"
              disabled={busy || (movementMode === "cards" && !movementSelectedChoice)}
              onClick={onSubmitMovement}
            >
              {movementMode === "roll"
                ? "주사위 굴리기"
                : movementSelectedChoice
                  ? `주사위 굴리기 (카드 ${selectedCards.join(", ")} 사용)`
                  : "주사위 카드를 선택하세요"}
            </button>
          </section>
        ) : null}

        {(prompt.requestType === "trick_to_use" || prompt.requestType === "hidden_trick_card") && trickChoices ? (
          <section className="prompt-hand-stage">
            <p>{prompt.requestType === "trick_to_use" ? "[사용할 잔꾀를 선택하세요]" : "[이번 라운드 히든 잔꾀를 선택하세요]"}</p>
            <p>
              손패 전체 {trickChoices.cards.length}장
              {typeof prompt.publicContext["hidden_trick_count"] === "number"
                ? ` / 히든 ${prompt.publicContext["hidden_trick_count"]}장`
                : ""}
            </p>
            <div className="prompt-choices hand-grid">
              {prompt.requestType === "trick_to_use" && trickChoices.passChoiceId ? (
                <button
                  type="button"
                  className="prompt-choice-card"
                  disabled={busy}
                  onClick={() => onSelectChoice(trickChoices.passChoiceId as string)}
                >
                  <strong>[이번에는 사용 안 함]</strong>
                  <small>[이번 턴에는 잔꾀를 사용하지 않습니다.]</small>
                </button>
              ) : null}
              {trickChoices.cards.map((card) => (
                <button
                  type="button"
                  key={card.key}
                  className={`prompt-choice-card ${card.isHidden ? "hand-card-hidden" : ""}`}
                  disabled={busy || !card.isUsable || !card.choiceId}
                  onClick={() => {
                    if (card.choiceId) {
                      onSelectChoice(card.choiceId);
                    }
                  }}
                >
                  <strong>[{card.name}]</strong>
                  <small>[{card.description}]</small>
                  <small>{card.isHidden ? "히든 잔꾀" : "공개 잔꾀"} / {card.isUsable ? "사용 가능" : "현재 사용 불가"}</small>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {isCharacterPick ? (
          <section className="prompt-hand-stage">
            <p>{prompt.requestType === "draft_card" ? "[클릭해서 이번 턴에 사용할 인물을 고르세요]" : "[최종으로 사용할 인물을 고르세요]"}</p>
            <div className={`prompt-choices ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {prompt.choices.map((choice) => (
                <button
                  type="button"
                  key={choice.choiceId}
                  className="prompt-choice-card"
                  onClick={() => onSelectChoice(choice.choiceId)}
                  disabled={busy}
                >
                  <strong>[{choice.title}]</strong>
                  <small>[{characterAbilityText(choice)}]</small>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {isMarkTarget ? (
          <section className="prompt-hand-stage">
            <p>[지목할 대상(인물/플레이어)을 선택하세요]</p>
            <div className={`prompt-choices ${compactChoices ? "prompt-choices-compact" : ""}`}>
              {prompt.choices.map((choice) => (
                <button
                  type="button"
                  key={choice.choiceId}
                  className="prompt-choice-card"
                  onClick={() => onSelectChoice(choice.choiceId)}
                  disabled={busy}
                >
                  <strong>{markChoiceTitle(choice)}</strong>
                  <small>{markChoiceDescription(choice)}</small>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {prompt.requestType !== "movement" &&
        prompt.requestType !== "trick_to_use" &&
        prompt.requestType !== "hidden_trick_card" &&
        !isCharacterPick &&
        !isMarkTarget ? (
          <div className={`prompt-choices ${compactChoices ? "prompt-choices-compact" : ""}`}>
            {prompt.choices.map((choice) => {
              const normalized = normalizeChoiceText(prompt, choice);
              return (
                <button
                  type="button"
                  key={choice.choiceId}
                  className="prompt-choice-card"
                  onClick={() => onSelectChoice(choice.choiceId)}
                  disabled={busy}
                >
                  <strong>[{normalized.title}]</strong>
                  <small>[{normalized.description}]</small>
                </button>
              );
            })}
            {prompt.choices.length === 0 ? <p>선택 가능한 항목이 없습니다.</p> : null}
          </div>
        ) : null}

        {feedbackMessage ? <p className="notice err">{feedbackMessage}</p> : null}
        {busy ? (
          <p className="notice ok">
            <span className="spinner" aria-hidden="true" /> 처리 중... 엔진 응답을 기다리는 중
          </p>
        ) : null}
      </section>
    </div>
  );

  return createPortal(overlay, document.body);
}
