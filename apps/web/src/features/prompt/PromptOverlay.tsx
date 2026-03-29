import type { PromptViewModel } from "../../domain/selectors/promptSelectors";

type PromptOverlayProps = {
  prompt: PromptViewModel | null;
  collapsed: boolean;
  busy: boolean;
  secondsLeft: number | null;
  onToggleCollapse: () => void;
  onSelectChoice: (choiceId: string) => void;
};

export function PromptOverlay({
  prompt,
  collapsed,
  busy,
  secondsLeft,
  onToggleCollapse,
  onSelectChoice,
}: PromptOverlayProps) {
  if (!prompt) {
    return null;
  }
  return (
    <section className="panel prompt-overlay" aria-busy={busy}>
      <div className="prompt-head">
        <h2>선택 요청: {prompt.requestType}</h2>
        <button type="button" onClick={onToggleCollapse}>
          {collapsed ? "열기" : "접기"}
        </button>
      </div>
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
      {busy ? <p className="notice ok">처리 중... 엔진 응답을 기다리는 중입니다.</p> : null}
    </section>
  );
}
