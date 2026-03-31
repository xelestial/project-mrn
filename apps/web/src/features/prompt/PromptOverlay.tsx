import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
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
  return text ? text : "내용 없음";
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

function prettyChoiceTitle(prompt: PromptViewModel, choice: PromptChoiceViewModel): string {
  if (prompt.requestType === "trick_to_use" && choice.choiceId === "none") {
    return "[이번에는 사용 안 함]";
  }
  if (prompt.requestType === "hidden_trick_card") {
    return `[${choice.title}]`;
  }
  if (prompt.requestType === "mark_target") {
    return `[${choice.title}]`;
  }
  if (prompt.requestType === "lap_reward") {
    return `[${choice.title}]`;
  }
  return choice.title;
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
        const name = asString(item["name"], "잔꾀");
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
    .map((choice, index) => {
      const deckIndex = asNumber(choice.value?.["deck_index"]);
      return {
        key: `${choice.choiceId}-${index}`,
        name: choice.title,
        description: choiceDescription(choice),
        isHidden: false,
        isUsable: true,
        choiceId: choice.choiceId,
        deckIndex,
      };
    })
    .map((item) => ({
      key: item.key,
      name: item.name,
      description: item.description,
      isHidden: item.isHidden,
      isUsable: item.isUsable,
      choiceId: item.choiceId,
    }));
  return { cards, passChoiceId };
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

  if (collapsed) {
    return (
      <button type="button" className="prompt-floating-chip" onClick={onToggleCollapse}>
        선택 요청: {promptLabelForType(prompt.requestType)} / 남은 시간 {secondsLeft ?? "-"}초
      </button>
    );
  }

  return (
    <div className="prompt-modal-layer" role="dialog" aria-modal="true" aria-busy={busy}>
      <div className="prompt-backdrop" />
      <section ref={rootRef} className="panel prompt-overlay" onKeyDown={onKeyDown} tabIndex={-1}>
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
                <small>사용할 주사위 카드를 선택하세요. 최대 {movement.canUseTwoCards ? "2" : "1"}장 사용 가능합니다.</small>
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
            <button type="button" className="prompt-primary-action" disabled={busy} onClick={onSubmitMovement}>
              {movementMode === "roll"
                ? "주사위 굴리기"
                : movementSelectedChoice
                  ? `주사위 굴리기 (주사위 카드 ${selectedCards.join(", ")} 사용)`
                  : "카드를 먼저 선택하세요"}
            </button>
          </section>
        ) : null}

        {(prompt.requestType === "trick_to_use" || prompt.requestType === "hidden_trick_card") && trickChoices ? (
          <section className="prompt-hand-stage">
            {prompt.requestType === "trick_to_use" ? <p>[사용할 잔꾀를 선택하세요]</p> : <p>[히든으로 지정할 잔꾀를 선택하세요]</p>}
            <div className="prompt-choices hand-grid">
              {prompt.requestType === "trick_to_use" && trickChoices.passChoiceId ? (
                <button
                  type="button"
                  className="prompt-choice-card"
                  disabled={busy}
                  onClick={() => onSelectChoice(trickChoices.passChoiceId as string)}
                >
                  <strong>[이번에는 사용 안 함]</strong>
                  <small>[이번 타이밍에는 잔꾀를 사용하지 않습니다.]</small>
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
                  <small>{card.isHidden ? "히든 잔꾀" : "공개 잔꾀"} / {card.isUsable ? "선택 가능" : "이번 타이밍 불가"}</small>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {prompt.requestType !== "movement" &&
        prompt.requestType !== "trick_to_use" &&
        prompt.requestType !== "hidden_trick_card" ? (
          <div className={`prompt-choices ${compactChoices ? "prompt-choices-compact" : ""}`}>
            {prompt.choices.map((choice) => (
              <button
                type="button"
                key={choice.choiceId}
                className="prompt-choice-card"
                onClick={() => onSelectChoice(choice.choiceId)}
                disabled={busy}
              >
                <strong>{prettyChoiceTitle(prompt, choice)}</strong>
                <small>{choiceDescription(choice)}</small>
              </button>
            ))}
            {prompt.choices.length === 0 ? <p>선택 가능한 항목이 없습니다.</p> : null}
          </div>
        ) : null}

        {feedbackMessage ? <p className="notice err">{feedbackMessage}</p> : null}
        {busy ? (
          <p className="notice ok">
            <span className="spinner" aria-hidden="true" /> 처리 중입니다. 엔진 응답을 기다리는 중
          </p>
        ) : null}
      </section>
    </div>
  );
}
