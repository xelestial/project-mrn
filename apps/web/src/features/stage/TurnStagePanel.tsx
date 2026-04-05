import type { TurnStageViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

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
  const { turnStage } = useI18n();
  const actorHeadline =
    model.actor !== "-" ? turnStage.actorHeadline(model.actor) : turnStage.actorWaiting;
  const roundTurn = `R${model.round ?? "-"} / T${model.turn ?? "-"}`;

  return (
    <section className="panel turn-stage-panel">
      <header className="turn-stage-head">
        <div>
          <h2>{turnStage.title}</h2>
          <small>{turnStage.description}</small>
        </div>
        <span className={isMyTurn ? "turn-stage-badge turn-stage-badge-me" : "turn-stage-badge"}>
          {isMyTurn ? turnStage.myTurn : turnStage.observing}
        </span>
      </header>

      <div className="turn-stage-grid">
        <article className={`turn-stage-card turn-stage-card-hero turn-stage-card-hero-${model.currentBeatKind}`}>
          <div className="turn-stage-card-top">
            <strong>{actorHeadline}</strong>
            <span>{roundTurn}</span>
          </div>
          <p>{valueOrDash(model.currentBeatLabel)}</p>
          <small>{valueOrDash(model.currentBeatDetail)}</small>
        </article>

        <article className="turn-stage-card turn-stage-card-weather">
          <div className="turn-stage-card-top">
            <strong>{turnStage.weatherTitle}</strong>
            <span>{turnStage.weatherBadge}</span>
          </div>
          <p>{valueOrDash(model.weatherName)}</p>
          <small>{valueOrDash(model.weatherEffect)}</small>
        </article>

        <article className={`turn-stage-card turn-stage-card-current turn-stage-card-current-${model.currentBeatKind}`}>
          <div className="turn-stage-card-top">
            <strong>{turnStage.characterTitle}</strong>
            <span>{turnStage.characterBadge}</span>
          </div>
          <p>{valueOrDash(model.character)}</p>
          <small>{valueOrDash(characterAbilityText)}</small>
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>{turnStage.currentBeatTitle}</strong>
            <span>{turnStage.currentBeatBadge}</span>
          </div>
          {stageLine(turnStage.fields.beat, model.currentBeatLabel)}
          {stageLine(turnStage.fields.trick, model.promptSummary === "-" ? turnStage.promptIdle : model.promptSummary)}
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>{turnStage.movementTitle}</strong>
            <span>{turnStage.movementBadge}</span>
          </div>
          {stageLine(turnStage.fields.dice, model.diceSummary)}
          {stageLine(turnStage.fields.move, model.moveSummary)}
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>{turnStage.landingTitle}</strong>
            <span>{turnStage.landingBadge}</span>
          </div>
          {stageLine(turnStage.fields.landing, model.landingSummary)}
          {stageLine(turnStage.fields.purchase, model.purchaseSummary)}
          {stageLine(turnStage.fields.rent, model.rentSummary)}
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>{turnStage.cardEffectTitle}</strong>
            <span>{turnStage.cardEffectBadge}</span>
          </div>
          {stageLine(turnStage.fields.trick, model.trickSummary)}
          {stageLine(turnStage.fields.fortune, model.fortuneSummary)}
        </article>

        <article className="turn-stage-card turn-stage-card-wide">
          <div className="turn-stage-card-top">
            <strong>{turnStage.progressTitle}</strong>
            <span>{turnStage.progressBadge}</span>
          </div>
          {model.progressTrail.length > 0 ? (
            <div className="turn-stage-trail">
              {model.progressTrail.map((step, index) => (
                <span key={`trail-${index}`} className="turn-stage-trail-chip">
                  {step}
                </span>
              ))}
            </div>
          ) : (
            <small>{turnStage.progressEmpty}</small>
          )}
        </article>
      </div>
    </section>
  );
}
