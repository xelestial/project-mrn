import type { CoreActionItem, TurnStageViewModel } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type SpectatorTurnPanelProps = {
  actorPlayerId: number | null;
  model: TurnStageViewModel;
  latestAction: CoreActionItem | null;
};

function valueOrDash(value: string): string {
  const trimmed = value.trim();
  return trimmed ? trimmed : "-";
}

function joinVisible(parts: string[]): string {
  const visible = parts.map((part) => part.trim()).filter((part) => part && part !== "-");
  return visible.length > 0 ? visible.join(" / ") : "-";
}

function hasValue(value: string): boolean {
  return value.trim() !== "" && value.trim() !== "-";
}

type SpotlightCard = {
  key: string;
  title: string;
  detail: string;
  tone: "economy" | "effect";
};

type JourneyCard = {
  key: string;
  label: string;
  detail: string;
  tone: "move" | "economy" | "effect" | "decision";
};

type PayoffTone = "economy" | "effect" | "neutral";

function payoffToneForEventCode(eventCode: string): PayoffTone {
  if (eventCode === "tile_purchased" || eventCode === "rent_paid" || eventCode === "lap_reward_chosen") {
    return "economy";
  }
  if (eventCode === "fortune_drawn" || eventCode === "fortune_resolved" || eventCode === "trick_used") {
    return "effect";
  }
  return "neutral";
}

export function SpectatorTurnPanel({ actorPlayerId, model, latestAction }: SpectatorTurnPanelProps) {
  const { app, turnStage } = useI18n();
  const title = actorPlayerId === null ? app.spectatorHeadline : app.spectatorTitle(actorPlayerId);
  const progress = model.progressTrail.filter((item) => item.trim());
  const latestActionTitle = latestAction?.label ?? "-";
  const latestActionDetail = latestAction?.detail?.trim() ? latestAction.detail : "-";
  const latestActionTone = payoffToneForEventCode(latestAction?.eventCode ?? "");
  const economyText = joinVisible([model.purchaseSummary, model.rentSummary]);
  const effectText = joinVisible([model.trickSummary, model.fortuneSummary]);
  const spotlightSummary = joinVisible([model.currentBeatDetail, model.fortuneSummary, model.rentSummary, model.purchaseSummary]);
  const payoffTitle =
    latestActionTone === "economy"
      ? app.spectatorFields.economy
      : latestActionTone === "effect"
        ? app.spectatorFields.effect
        : app.spectatorFields.beat;
  const payoffSummary =
    latestActionTone === "economy"
      ? economyText
      : latestActionTone === "effect"
        ? effectText
        : joinVisible([model.currentBeatDetail, latestActionDetail]);
  const spotlightCards: SpotlightCard[] = [];
  if (hasValue(model.weatherName) || hasValue(model.weatherEffect)) {
    spotlightCards.push({
      key: "weather",
      title: app.spectatorFields.weather,
      detail: joinVisible([model.weatherName, model.weatherEffect]),
      tone: "effect",
    });
  }
  if (hasValue(model.purchaseSummary)) {
    spotlightCards.push({ key: "purchase", title: turnStage.fields.purchase, detail: model.purchaseSummary, tone: "economy" });
  }
  if (hasValue(model.rentSummary)) {
    spotlightCards.push({ key: "rent", title: turnStage.fields.rent, detail: model.rentSummary, tone: "economy" });
  }
  if (hasValue(model.fortuneSummary)) {
    spotlightCards.push({ key: "fortune", title: turnStage.fields.fortune, detail: model.fortuneSummary, tone: "effect" });
  }
  if (hasValue(model.trickSummary)) {
    spotlightCards.push({ key: "trick", title: turnStage.fields.trick, detail: model.trickSummary, tone: "effect" });
  }
  const journeyCards: JourneyCard[] = [];
  if (hasValue(model.character)) {
    journeyCards.push({
      key: "character",
      label: app.spectatorFields.character,
      detail: model.character,
      tone: "decision",
    });
  }
  if (hasValue(model.promptSummary)) {
    journeyCards.push({
      key: "prompt",
      label: app.spectatorFields.prompt,
      detail: model.promptSummary,
      tone: "decision",
    });
  }
  if (hasValue(model.moveSummary)) {
    journeyCards.push({
      key: "move",
      label: app.spectatorFields.move,
      detail: model.moveSummary,
      tone: "move",
    });
  }
  if (hasValue(model.landingSummary)) {
    journeyCards.push({
      key: "landing",
      label: app.spectatorFields.landing,
      detail: model.landingSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.purchaseSummary)) {
    journeyCards.push({
      key: "purchase",
      label: turnStage.fields.purchase,
      detail: model.purchaseSummary,
      tone: "economy",
    });
  }
  if (hasValue(model.rentSummary)) {
    journeyCards.push({
      key: "rent",
      label: turnStage.fields.rent,
      detail: model.rentSummary,
      tone: "economy",
    });
  }
  if (hasValue(model.fortuneSummary)) {
    journeyCards.push({
      key: "fortune",
      label: turnStage.fields.fortune,
      detail: model.fortuneSummary,
      tone: "effect",
    });
  }
  if (!hasValue(model.fortuneSummary) && hasValue(model.trickSummary)) {
    journeyCards.push({
      key: "effect",
      label: app.spectatorFields.effect,
      detail: model.trickSummary,
      tone: "effect",
    });
  }

  return (
    <section className="panel spectator-turn-panel" data-testid="spectator-turn-panel">
      <div className="spectator-turn-head">
        <div>
          <h2>{app.spectatorHeadline}</h2>
          <strong>{title}</strong>
        </div>
        <p>
          <span className="spinner" aria-hidden="true" /> {app.spectatorDescription}
        </p>
      </div>

      <div className="spectator-turn-grid">
        <article className="spectator-turn-card spectator-turn-card-hero" data-testid="spectator-turn-scene">
          <span>{app.spectatorFields.beat}</span>
          <strong>{valueOrDash(model.currentBeatLabel)}</strong>
          <small>{valueOrDash(latestActionTitle === "-" ? spotlightSummary : `${latestActionTitle} / ${spotlightSummary}`)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-weather">
          <span>{app.spectatorFields.weather}</span>
          <strong>{valueOrDash(model.weatherName)}</strong>
          <small>{valueOrDash(model.weatherEffect)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-character">
          <span>{app.spectatorFields.character}</span>
          <strong>{valueOrDash(model.character)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-beat">
          <span>{app.spectatorFields.beat}</span>
          <strong>{valueOrDash(model.currentBeatLabel)}</strong>
          <small>{valueOrDash(model.currentBeatDetail)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-action">
          <span>{app.spectatorFields.action}</span>
          <strong>{valueOrDash(latestActionTitle)}</strong>
          <small>{valueOrDash(latestActionDetail)}</small>
        </article>
        {latestActionTitle !== "-" ? (
          <article
            className={`spectator-turn-card spectator-turn-card-payoff spectator-turn-card-payoff-${latestActionTone}`}
            data-testid="spectator-turn-payoff"
          >
            <span>{payoffTitle}</span>
            <strong>{valueOrDash(payoffSummary)}</strong>
            <small>{valueOrDash(latestActionTitle)}</small>
          </article>
        ) : null}
        <article className="spectator-turn-card" data-testid="spectator-turn-prompt">
          <span>{app.spectatorFields.prompt}</span>
          <strong>{valueOrDash(model.promptSummary)}</strong>
          <small>{valueOrDash(model.currentBeatDetail)}</small>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-move">
          <span>{app.spectatorFields.move}</span>
          <strong>{valueOrDash(model.moveSummary)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-landing">
          <span>{app.spectatorFields.landing}</span>
          <strong>{valueOrDash(model.landingSummary)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-economy">
          <span>{app.spectatorFields.economy}</span>
          <strong>{valueOrDash(economyText)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-effect">
          <span>{app.spectatorFields.effect}</span>
          <strong>{valueOrDash(effectText)}</strong>
        </article>
      </div>

      {spotlightCards.length > 0 ? (
        <div className="spectator-turn-spotlight" data-testid="spectator-turn-spotlight">
          {spotlightCards.map((card) => (
            <article key={card.key} className={`spectator-turn-spotlight-card spectator-turn-spotlight-card-${card.tone}`}>
              <span>{card.title}</span>
              <strong>{valueOrDash(card.detail)}</strong>
            </article>
          ))}
        </div>
      ) : null}

      {journeyCards.length > 0 ? (
        <section className="core-action-journey spectator-turn-journey" data-testid="spectator-turn-journey">
          <div className="core-action-journey-head">
            <strong>{turnStage.progressTitle}</strong>
            <small>{valueOrDash(latestActionTitle)}</small>
          </div>
          <div className="core-action-journey-strip">
            {journeyCards.map((card, index) => (
              <article key={card.key} className={`core-action-journey-step core-action-journey-step-${card.tone}`}>
                <span className="core-action-journey-index">{`0${index + 1}`}</span>
                <strong>{card.label}</strong>
                <small>{valueOrDash(card.detail)}</small>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {latestActionTitle !== "-" && payoffSummary !== "-" ? (
        <article
          className={`spectator-turn-card spectator-turn-card-payoff spectator-turn-card-payoff-${latestActionTone}`}
          data-testid="spectator-turn-result"
        >
          <span>{app.spectatorFields.action}</span>
          <strong>{valueOrDash(latestActionTitle)}</strong>
          <small>{valueOrDash(payoffSummary)}</small>
        </article>
      ) : null}

      <div className="spectator-turn-progress" data-testid="spectator-turn-progress">
        <span>{app.spectatorFields.progress}</span>
        {progress.length > 0 ? (
          <div className="spectator-turn-progress-list">
            {progress.map((step) => (
              <small key={step}>{step}</small>
            ))}
          </div>
        ) : (
          <strong>-</strong>
        )}
      </div>
    </section>
  );
}
