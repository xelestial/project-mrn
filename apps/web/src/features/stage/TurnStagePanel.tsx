import type { TurnStageViewModel } from "../../domain/selectors/streamSelectors";

type TurnStagePanelProps = {
  model: TurnStageViewModel;
  characterAbilityText: string;
  isMyTurn: boolean;
};

function valueOrDash(value: string): string {
  const trimmed = value.trim();
  return trimmed ? trimmed : "-";
}

function stageLine(label: string, value: string) {
  return (
    <div className="turn-stage-line">
      <span>{label}</span>
      <strong>{valueOrDash(value)}</strong>
    </div>
  );
}

export function TurnStagePanel({ model, characterAbilityText, isMyTurn }: TurnStagePanelProps) {
  const actorHeadline = model.actor !== "-" ? `${model.actor}의 턴 진행` : "턴 대기 중";
  const roundTurn = `R${model.round ?? "-"} / T${model.turn ?? "-"}`;

  return (
    <section className="panel turn-stage-panel">
      <header className="turn-stage-head">
        <div>
          <h2>턴 극장 요약</h2>
          <small>날씨, 인물, 이동, 도착 결과, 카드 효과를 이번 턴 기준으로 계속 보여줍니다.</small>
        </div>
        <span className={isMyTurn ? "turn-stage-badge turn-stage-badge-me" : "turn-stage-badge"}>
          {isMyTurn ? "내 차례" : "관전 중"}
        </span>
      </header>

      <div className="turn-stage-grid">
        <article className="turn-stage-card turn-stage-card-hero">
          <div className="turn-stage-card-top">
            <strong>{actorHeadline}</strong>
            <span>{roundTurn}</span>
          </div>
          <p>{valueOrDash(model.promptSummary)}</p>
        </article>

        <article className="turn-stage-card turn-stage-card-weather">
          <div className="turn-stage-card-top">
            <strong>현재 라운드 날씨</strong>
            <span>지속 표시</span>
          </div>
          <p>{valueOrDash(model.weatherName)}</p>
          <small>{valueOrDash(model.weatherEffect)}</small>
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>선택 인물</strong>
            <span>능력</span>
          </div>
          <p>{valueOrDash(model.character)}</p>
          <small>{valueOrDash(characterAbilityText)}</small>
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>이동 처리</strong>
            <span>주사위 / 카드</span>
          </div>
          {stageLine("주사위", model.diceSummary)}
          {stageLine("이동", model.moveSummary)}
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>도착 결과</strong>
            <span>구매 / 렌트</span>
          </div>
          {stageLine("도착", model.landingSummary)}
          {stageLine("구매", model.purchaseSummary)}
          {stageLine("렌트", model.rentSummary)}
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>카드 효과</strong>
            <span>잔꾀 / 운수</span>
          </div>
          {stageLine("잔꾀", model.trickSummary)}
          {stageLine("운수", model.fortuneSummary)}
        </article>
      </div>
    </section>
  );
}
