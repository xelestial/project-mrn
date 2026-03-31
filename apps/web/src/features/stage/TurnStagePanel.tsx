import type { TurnStageViewModel } from "../../domain/selectors/streamSelectors";

type TurnStagePanelProps = {
  model: TurnStageViewModel;
  characterAbilityText: string;
  isMyTurn: boolean;
};

function valueOrDash(value: string): string {
  return value.trim() ? value : "-";
}

export function TurnStagePanel({ model, characterAbilityText, isMyTurn }: TurnStagePanelProps) {
  return (
    <section className="panel turn-stage-panel">
      <header className="turn-stage-head">
        <h2>\uD134 \uADF9\uC7A5</h2>
        <span className={isMyTurn ? "turn-stage-badge turn-stage-badge-me" : "turn-stage-badge"}>
          {isMyTurn ? "\uB0B4 \uD134" : "\uAD00\uC804 \uC911"}
        </span>
      </header>
      <div className="turn-stage-grid">
        <article className="turn-stage-card turn-stage-card-highlight">
          <strong>{model.actor !== "-" ? `${model.actor}\uC758 \uD134` : "\uD134 \uB300\uAE30 \uC911"}</strong>
          <small>
            R{model.round ?? "-"} / T{model.turn ?? "-"}
          </small>
          <small>{valueOrDash(model.promptSummary)}</small>
        </article>

        <article className="turn-stage-card">
          <strong>\uB0A0\uC528</strong>
          <small>{valueOrDash(model.weatherName)}</small>
          <small>{valueOrDash(model.weatherEffect)}</small>
        </article>

        <article className="turn-stage-card">
          <strong>\uC120\uD0DD \uC778\uBB3C</strong>
          <small>{valueOrDash(model.character)}</small>
          <small>{valueOrDash(characterAbilityText)}</small>
        </article>

        <article className="turn-stage-card">
          <strong>\uC774\uB3D9 \uCC98\uB9AC</strong>
          <small>\uC8FC\uC0AC\uC704: {valueOrDash(model.diceSummary)}</small>
          <small>\uB9D0 \uC774\uB3D9: {valueOrDash(model.moveSummary)}</small>
        </article>

        <article className="turn-stage-card">
          <strong>\uCE78 \uCC98\uB9AC</strong>
          <small>\uB3C4\uCC29: {valueOrDash(model.landingSummary)}</small>
          <small>\uAD6C\uB9E4: {valueOrDash(model.purchaseSummary)}</small>
          <small>\uB80C\uD2B8: {valueOrDash(model.rentSummary)}</small>
        </article>

        <article className="turn-stage-card">
          <strong>\uCE74\uB4DC / \uD6A8\uACFC</strong>
          <small>\uC794\uAFE0: {valueOrDash(model.trickSummary)}</small>
          <small>\uC6B4\uC218: {valueOrDash(model.fortuneSummary)}</small>
        </article>
      </div>
    </section>
  );
}
