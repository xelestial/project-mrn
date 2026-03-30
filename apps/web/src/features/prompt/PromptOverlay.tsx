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
    <section ref={rootRef} className="panel prompt-overlay" aria-busy={busy} onKeyDown={onKeyDown} tabIndex={-1}>
      <div className="prompt-head">
        <h2>Prompt: {promptLabelForType(prompt.requestType)}</h2>
        <button type="button" onClick={onToggleCollapse}>
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </div>
      <p className="prompt-helper">{promptHelperForType(prompt.requestType)}</p>
      <p>
        Request {prompt.requestId} / Actor P{prompt.playerId} / Timeout {Math.ceil(prompt.timeoutMs / 1000)}s / Left{" "}
        {secondsLeft ?? "-"}s
      </p>
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
          {prompt.choices.length === 0 ? <p>No selectable choices were provided.</p> : null}
        </div>
      ) : null}
      {feedbackMessage ? <p className="notice err">{feedbackMessage}</p> : null}
      {busy ? <p className="notice ok">Processing decision. Waiting for engine acknowledgment.</p> : null}
    </section>
  );
}
