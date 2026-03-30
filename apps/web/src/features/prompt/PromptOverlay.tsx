import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { promptHelperForType } from "../../domain/labels/promptHelperCatalog";
import { promptLabelForType } from "../../domain/labels/promptTypeCatalog";
import type { PromptViewModel } from "../../domain/selectors/promptSelectors";

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

const LARGE_CHOICE_THRESHOLD = 8;

function needsCompactByDefault(prompt: PromptViewModel, compactChoices: boolean): boolean {
  return compactChoices || prompt.choices.length >= LARGE_CHOICE_THRESHOLD;
}

function detailForChoice(choice: PromptViewModel["choices"][number]): string {
  if (choice.description && choice.description.trim()) {
    return choice.description;
  }
  return choice.choiceId;
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
  const [compactMode, setCompactMode] = useState(false);

  useEffect(() => {
    if (!prompt) {
      if (previousFocusRef.current) {
        previousFocusRef.current.focus();
        previousFocusRef.current = null;
      }
      return;
    }
    setCompactMode(needsCompactByDefault(prompt, compactChoices));
  }, [prompt, compactChoices]);

  useEffect(() => {
    if (!prompt || collapsed) {
      return;
    }
    if (!previousFocusRef.current && document.activeElement instanceof HTMLElement) {
      previousFocusRef.current = document.activeElement;
    }
    const firstChoice = rootRef.current?.querySelector<HTMLButtonElement>(".prompt-choice-card");
    firstChoice?.focus();
  }, [prompt, collapsed, compactMode]);

  if (!prompt) {
    return null;
  }

  const showCompactToggle = prompt.choices.length >= 6;

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onToggleCollapse();
    }
  };

  return (
    <section
      ref={rootRef}
      className={`panel prompt-overlay ${collapsed ? "prompt-collapsed" : ""}`}
      aria-busy={busy}
      onKeyDown={onKeyDown}
      tabIndex={-1}
    >
      <div className="prompt-head">
        <h2>선택 요청: {promptLabelForType(prompt.requestType)}</h2>
        <button type="button" onClick={onToggleCollapse}>
          {collapsed ? "열기" : "접기"}
        </button>
      </div>
      {!collapsed ? <p className="prompt-helper">{promptHelperForType(prompt.requestType)}</p> : null}
      {!collapsed ? (
        <p>
          요청 ID {prompt.requestId} / 행동자 P{prompt.playerId} / 제한 시간 {Math.ceil(prompt.timeoutMs / 1000)}초 / 남은 시간{" "}
          {secondsLeft ?? "-"}초
        </p>
      ) : (
        <p className="prompt-collapsed-note">선택창이 접혀 있습니다. 열기 버튼으로 다시 확인하세요.</p>
      )}
      {!collapsed && showCompactToggle ? (
        <div className="prompt-choice-toolbar">
          <button type="button" className="route-tab" onClick={() => setCompactMode((prev) => !prev)}>
            {compactMode ? "상세 보기" : "간단 보기"}
          </button>
          <small>{prompt.choices.length}개 선택지</small>
        </div>
      ) : null}
      {!collapsed ? (
        <div className={`prompt-choices ${compactMode ? "prompt-choices-compact" : ""}`}>
          {prompt.choices.map((choice) => (
            <button
              type="button"
              key={choice.choiceId}
              className={`prompt-choice-card ${compactMode ? "prompt-choice-card-compact" : ""}`}
              onClick={() => onSelectChoice(choice.choiceId)}
              disabled={busy}
            >
              <strong>{choice.title}</strong>
              <small>{detailForChoice(choice)}</small>
            </button>
          ))}
          {prompt.choices.length === 0 ? <p>선택 가능한 항목이 없습니다.</p> : null}
        </div>
      ) : null}
      {feedbackMessage ? <p className="notice err">{feedbackMessage}</p> : null}
      {busy ? <p className="notice ok">처리 중입니다. 서버 응답을 기다리는 중입니다.</p> : null}
    </section>
  );
}
