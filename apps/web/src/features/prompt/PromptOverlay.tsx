import { KeyboardEvent, useEffect, useRef } from "react";
import { promptHelperForType } from "../../domain/labels/promptHelperCatalog";
import { promptLabelForType } from "../../domain/labels/promptTypeCatalog";
import type { PromptViewModel } from "../../domain/selectors/promptSelectors";

type PromptOverlayProps = {
  prompt: PromptViewModel | null;
  collapsed: boolean;
  busy: boolean;
  secondsLeft: number | null;
  feedbackMessage?: string;
  onToggleCollapse: () => void;
  onSelectChoice: (choiceId: string) => void;
};

export function PromptOverlay({
  prompt,
  collapsed,
  busy,
  secondsLeft,
  feedbackMessage,
  onToggleCollapse,
  onSelectChoice,
}: PromptOverlayProps) {
  const rootRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!prompt) {
      if (previousFocusRef.current) {
        previousFocusRef.current.focus();
        previousFocusRef.current = null;
      }
      return;
    }
    if (collapsed) {
      return;
    }
    if (!previousFocusRef.current && document.activeElement instanceof HTMLElement) {
      previousFocusRef.current = document.activeElement;
    }
    const firstChoice = rootRef.current?.querySelector<HTMLButtonElement>(".prompt-choice-card");
    firstChoice?.focus();
  }, [prompt, collapsed]);

  if (!prompt) {
    return null;
  }

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
      {!collapsed ? (
        <div className="prompt-choices">
          {prompt.choices.map((choice) => (
            <button
              type="button"
              key={choice.choiceId}
              className="prompt-choice-card"
              onClick={() => onSelectChoice(choice.choiceId)}
              disabled={busy}
            >
              <strong>{choice.title}</strong>
              <small>{choice.description || choice.choiceId}</small>
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
