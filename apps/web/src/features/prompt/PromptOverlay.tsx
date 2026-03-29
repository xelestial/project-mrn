import { KeyboardEvent, useEffect, useRef } from "react";
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

const PROMPT_HELPERS: Record<string, string> = {
  movement: "이동 방법을 선택하세요. 주사위 카드 사용 시 도착 칸이 즉시 바뀝니다.",
  purchase_tile: "해당 칸을 구매할지 결정하세요. 구매하지 않으면 이번 기회는 종료됩니다.",
  trick_to_use: "사용할 잔꾀를 선택하세요. 선택하지 않으면 이번 타이밍은 넘어갑니다.",
  draft_card: "이번 턴에 사용할 인물 후보를 고르세요.",
  final_character_choice: "드래프트한 인물 중 최종 인물을 확정하세요.",
  mark_target: "지목 효과의 대상을 선택하세요. 불가하면 no target을 고르세요.",
  active_flip: "카드 뒤집기를 진행하거나 종료를 선택하세요.",
  lap_reward: "랩 보상 종류를 선택하세요.",
  runaway_step_choice: "탈출 노비 +1 이동 방식(안전/보너스)을 선택하세요.",
};

function helperTextForPrompt(requestType: string): string {
  return PROMPT_HELPERS[requestType] ?? "현재 요청의 선택지 중 하나를 고르세요.";
}

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
        <h2>선택 요청: {prompt.requestType}</h2>
        <button type="button" onClick={onToggleCollapse}>
          {collapsed ? "열기" : "접기"}
        </button>
      </div>
      <p className="prompt-helper">{helperTextForPrompt(prompt.requestType)}</p>
      <p>
        요청 ID {prompt.requestId} / 대상 P{prompt.playerId} / 제한 {Math.ceil(prompt.timeoutMs / 1000)}초 / 남은 시간{" "}
        {secondsLeft ?? "-"}초
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
          {prompt.choices.length === 0 ? <p>선택지 정보가 없습니다.</p> : null}
        </div>
      ) : null}
      {feedbackMessage ? <p className="notice err">{feedbackMessage}</p> : null}
      {busy ? <p className="notice ok">처리 중입니다. 엔진 응답을 기다리는 중입니다.</p> : null}
    </section>
  );
}
