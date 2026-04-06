import type { TurnStageViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type TurnStagePanelProps = {
  model: TurnStageViewModel;
  characterAbilityText: string;
  isMyTurn: boolean;
};

type SceneCard = {
  key: string;
  label: string;
  value: string;
  detail?: string;
  tone: "move" | "economy" | "effect";
};

type SpotlightCard = {
  key: string;
  title: string;
  detail: string;
  tone: "move" | "economy" | "effect";
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

function hasMeaningfulValue(value: string): boolean {
  return value.trim() !== "" && value.trim() !== "-";
}

function isSceneCard(card: SceneCard | null): card is SceneCard {
  return card !== null;
}

function hasOutcome(summary: string): boolean {
  return hasMeaningfulValue(summary);
}

export function TurnStagePanel({ model, characterAbilityText, isMyTurn }: TurnStagePanelProps) {
  const { turnStage, eventLabel } = useI18n();
  const landingEventLabel = eventLabel.events.landing_resolved ?? turnStage.fields.landing;
  const purchaseEventLabel = eventLabel.events.tile_purchased ?? turnStage.fields.purchase;
  const rentEventLabel = eventLabel.events.rent_paid ?? turnStage.fields.rent;
  const fortuneDrawEventLabel = eventLabel.events.fortune_drawn ?? turnStage.fields.fortune;
  const fortuneResolvedEventLabel = eventLabel.events.fortune_resolved ?? turnStage.cardEffectTitle;
  const turnEndLabel =
    (eventLabel.events as Record<string, string>)["turn_end_snapshot"] ??
    turnStage.progressTitle;
  const actorHeadline =
    model.actor !== "-" ? turnStage.actorHeadline(model.actor) : turnStage.actorWaiting;
  const roundTurn = `R${model.round ?? "-"} / T${model.turn ?? "-"}`;
  const sceneCardCandidates: Array<SceneCard | null> = [
    hasMeaningfulValue(model.weatherName) || hasMeaningfulValue(model.weatherEffect)
      ? {
          key: "weather",
          label: turnStage.weatherTitle,
          value:
            model.weatherEffect !== "-" && model.weatherEffect.trim()
              ? `${valueOrDash(model.weatherName)} / ${valueOrDash(model.weatherEffect)}`
              : valueOrDash(model.weatherName),
          tone: "effect",
        }
      : null,
    hasMeaningfulValue(model.promptSummary)
      ? { key: "prompt", label: turnStage.fields.beat, value: model.promptSummary, tone: "effect" }
      : null,
    hasMeaningfulValue(model.moveSummary)
      ? { key: "move", label: turnStage.fields.move, value: model.moveSummary, tone: "move" }
      : null,
    hasMeaningfulValue(model.landingSummary)
      ? { key: "landing", label: landingEventLabel, value: model.landingSummary, tone: "effect" }
      : null,
    hasMeaningfulValue(model.purchaseSummary)
      ? { key: "purchase", label: purchaseEventLabel, value: model.purchaseSummary, detail: turnStage.sequenceBeat.purchase, tone: "economy" }
      : null,
    hasMeaningfulValue(model.rentSummary)
      ? { key: "rent", label: rentEventLabel, value: model.rentSummary, detail: turnStage.sequenceBeat.rent, tone: "economy" }
      : null,
    hasMeaningfulValue(model.turnEndSummary)
      ? { key: "turn-end", label: turnEndLabel, value: model.turnEndSummary, tone: "effect" }
      : null,
    hasMeaningfulValue(model.fortuneDrawSummary)
      ? { key: "fortune-draw", label: fortuneDrawEventLabel, value: model.fortuneDrawSummary, detail: turnStage.sequenceBeat.fortuneDraw, tone: "effect" }
      : null,
    hasMeaningfulValue(model.fortuneResolvedSummary || model.fortuneSummary)
      ? {
          key: "fortune-effect",
          label: fortuneResolvedEventLabel,
          value: model.fortuneResolvedSummary || model.fortuneSummary,
          detail: turnStage.sequenceBeat.fortuneResolved,
          tone: "effect",
        }
      : null,
  ];
  const sceneCards = sceneCardCandidates.filter(isSceneCard);
  const outcomeCards: SceneCard[] = [];
  if (hasOutcome(model.purchaseSummary)) {
    outcomeCards.push({ key: "purchase-outcome", label: purchaseEventLabel, value: model.purchaseSummary, tone: "economy" });
  }
  if (hasOutcome(model.rentSummary)) {
    outcomeCards.push({ key: "rent-outcome", label: rentEventLabel, value: model.rentSummary, tone: "economy" });
  }
  if (hasOutcome(model.fortuneResolvedSummary || model.fortuneSummary)) {
    outcomeCards.push({
      key: "fortune-outcome",
      label: fortuneResolvedEventLabel,
      value: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    });
  }
  if (!hasOutcome(model.fortuneResolvedSummary || model.fortuneSummary) && hasOutcome(model.weatherEffect)) {
    outcomeCards.push({
      key: "weather-outcome",
      label: turnStage.weatherTitle,
      value: model.weatherEffect,
      tone: "effect",
    });
  }
  if (hasOutcome(model.trickSummary)) {
    outcomeCards.push({ key: "trick-outcome", label: turnStage.fields.trick, value: model.trickSummary, tone: "effect" });
  }
  if (hasOutcome(model.turnEndSummary)) {
    outcomeCards.push({ key: "turn-end-outcome", label: turnEndLabel, value: model.turnEndSummary, tone: "effect" });
  }
  const spotlightCards: SpotlightCard[] = [];
  if (hasMeaningfulValue(model.weatherName) || hasMeaningfulValue(model.weatherEffect)) {
    spotlightCards.push({
      key: "weather",
      title: turnStage.weatherTitle,
      detail: valueOrDash(model.weatherEffect === "-" ? model.weatherName : `${model.weatherName} / ${model.weatherEffect}`),
      tone: "effect",
    });
  }
  if (hasMeaningfulValue(model.fortuneDrawSummary)) {
    spotlightCards.push({
      key: "fortune-draw",
      title: fortuneDrawEventLabel,
      detail: model.fortuneDrawSummary,
      tone: "effect",
    });
  }
  if (hasMeaningfulValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    spotlightCards.push({
      key: "fortune-effect",
      title: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    });
  }
  if (hasMeaningfulValue(model.purchaseSummary)) {
    spotlightCards.push({
      key: "purchase",
      title: purchaseEventLabel,
      detail: model.purchaseSummary,
      tone: "economy",
    });
  }
  if (hasMeaningfulValue(model.rentSummary)) {
    spotlightCards.push({
      key: "rent",
      title: rentEventLabel,
      detail: model.rentSummary,
      tone: "economy",
    });
  }

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

        {spotlightCards.length > 0 ? (
          <article className="turn-stage-card turn-stage-card-wide turn-stage-spotlight-strip" data-testid="turn-stage-spotlight-strip">
            <div className="turn-stage-card-top">
              <strong>{turnStage.currentBeatTitle}</strong>
              <span>{turnStage.currentBeatBadge}</span>
            </div>
            <div className="turn-stage-spotlight-list">
              {spotlightCards.map((card) => (
                <div key={card.key} className={`turn-stage-spotlight-card turn-stage-spotlight-card-${card.tone}`}>
                  <span>{card.title}</span>
                  <strong>{valueOrDash(card.detail)}</strong>
                </div>
              ))}
            </div>
          </article>
        ) : null}

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
          {stageLine(landingEventLabel, model.landingSummary)}
          {stageLine(purchaseEventLabel, model.purchaseSummary)}
          {stageLine(rentEventLabel, model.rentSummary)}
        </article>

        <article className="turn-stage-card">
          <div className="turn-stage-card-top">
            <strong>{turnStage.cardEffectTitle}</strong>
            <span>{turnStage.cardEffectBadge}</span>
          </div>
          {stageLine(turnStage.fields.trick, model.trickSummary)}
          {stageLine(fortuneDrawEventLabel, model.fortuneDrawSummary)}
          {stageLine(fortuneResolvedEventLabel, model.fortuneResolvedSummary || model.fortuneSummary)}
          {stageLine(turnEndLabel, model.turnEndSummary)}
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

        {sceneCards.length > 0 ? (
          <article className="turn-stage-card turn-stage-card-wide turn-stage-scene-strip" data-testid="turn-stage-scene-strip">
            <div className="turn-stage-card-top">
              <strong>{turnStage.currentBeatTitle}</strong>
              <span>{turnStage.currentBeatBadge}</span>
            </div>
            <div className="turn-stage-scene-list">
              {sceneCards.map((card, index) => (
                <div key={card.key} className={`turn-stage-scene-card turn-stage-scene-card-${card.tone}`}>
                  <span className="turn-stage-scene-index">{turnStage.sequenceIndex(index + 1, sceneCards.length)}</span>
                  <span>{card.label}</span>
                  <strong>{valueOrDash(card.value)}</strong>
                  {card.detail ? <small>{card.detail}</small> : null}
                </div>
              ))}
            </div>
          </article>
        ) : null}

        {outcomeCards.length > 0 ? (
          <article className="turn-stage-card turn-stage-card-wide turn-stage-outcome-strip" data-testid="turn-stage-outcome-strip">
            <div className="turn-stage-card-top">
              <strong>{turnStage.cardEffectTitle}</strong>
              <span>{turnStage.cardEffectBadge}</span>
            </div>
            <div className="turn-stage-outcome-list">
              {outcomeCards.map((card) => (
                <div key={card.key} className={`turn-stage-outcome-card turn-stage-outcome-card-${card.tone}`}>
                  <span>{card.label}</span>
                  <strong>{valueOrDash(card.value)}</strong>
                </div>
              ))}
            </div>
          </article>
        ) : null}

        {hasMeaningfulValue(model.turnEndSummary) ? (
          <article className="turn-stage-card turn-stage-card-wide turn-stage-card-handoff" data-testid="turn-stage-handoff-card">
            <div className="turn-stage-card-top">
              <strong>{turnEndLabel}</strong>
              <span>{turnStage.progressBadge}</span>
            </div>
            <p>{valueOrDash(model.turnEndSummary)}</p>
            <small>{turnStage.progressTitle}</small>
          </article>
        ) : null}
      </div>
    </section>
  );
}
