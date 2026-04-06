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

type PersistentPayoff = {
  title: string;
  detail: string;
  tone: "economy" | "effect";
};

type SpectatorPayoffBeat = {
  key: string;
  title: string;
  detail: string;
  tone: "economy" | "effect";
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

function hasWorkerStatus(model: TurnStageViewModel): boolean {
  return (
    hasValue(model.externalAiWorkerId) ||
    hasValue(model.externalAiFailureCode) ||
    hasValue(model.externalAiFallbackMode) ||
    hasValue(model.externalAiResolutionStatus) ||
    model.externalAiReadyState !== "-" ||
    model.externalAiAttemptCount !== null ||
    model.externalAiAttemptLimit !== null
  );
}

export function SpectatorTurnPanel({ actorPlayerId, model, latestAction }: SpectatorTurnPanelProps) {
  const { app, turnStage, eventLabel, stream } = useI18n();
  const purchaseEventLabel = eventLabel.events.tile_purchased ?? turnStage.fields.purchase;
  const rentEventLabel = eventLabel.events.rent_paid ?? turnStage.fields.rent;
  const fortuneDrawEventLabel = eventLabel.events.fortune_drawn ?? turnStage.fields.fortune;
  const fortuneResolvedEventLabel = eventLabel.events.fortune_resolved ?? app.spectatorFields.effect;
  const landingEventLabel = eventLabel.events.landing_resolved ?? app.spectatorFields.landing;
  const lapRewardEventLabel = eventLabel.events.lap_reward_chosen ?? app.spectatorFields.economy;
  const markEventLabel =
    (eventLabel.events as Record<string, string>)["mark_resolved"] ??
    app.spectatorFields.effect;
  const flipEventLabel = eventLabel.events.marker_flip ?? app.spectatorFields.effect;
  const turnEndLabel =
    (eventLabel.events as Record<string, string>)["turn_end_snapshot"] ??
    app.spectatorFields.progress;
  const title = actorPlayerId === null ? app.spectatorHeadline : app.spectatorTitle(actorPlayerId);
  const progress = model.progressTrail.filter((item) => item.trim());
  const latestActionTitle = latestAction?.label ?? "-";
  const latestActionDetail = latestAction?.detail?.trim() ? latestAction.detail : "-";
  const latestActionTone = payoffToneForEventCode(latestAction?.eventCode ?? "");
  const economyText = joinVisible([model.purchaseSummary, model.rentSummary]);
  const effectText = joinVisible([
    model.trickSummary,
    model.fortuneResolvedSummary || model.fortuneSummary,
    model.fortuneDrawSummary,
    model.markSummary,
    model.flipSummary,
    model.weatherSummary,
  ]);
  const spotlightSummary = joinVisible([
    model.currentBeatDetail,
    model.turnEndSummary,
    model.fortuneDrawSummary,
    model.fortuneResolvedSummary || model.fortuneSummary,
    model.rentSummary,
    model.purchaseSummary,
    model.lapRewardSummary,
    model.markSummary,
    model.flipSummary,
  ]);
  const workerStatusSummary = turnStage.workerStatusSummary(
    model.externalAiResolutionStatus,
    model.externalAiWorkerId,
    model.externalAiFailureCode,
    model.externalAiFallbackMode,
    model.externalAiAttemptCount
  );
  const workerStatusDetail = stream.workerStatusDetail(
    turnStage.workerStatusLabel(model.externalAiResolutionStatus),
    model.externalAiWorkerId,
    model.externalAiFailureCode,
    model.externalAiFallbackMode,
    model.externalAiAttemptCount,
    model.externalAiAttemptLimit,
    model.externalAiReadyState
  );
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
  let persistentPayoff: PersistentPayoff | null = null;
  if (hasValue(model.rentSummary)) {
    persistentPayoff = { title: rentEventLabel, detail: model.rentSummary, tone: "economy" };
  } else if (hasValue(model.purchaseSummary)) {
    persistentPayoff = { title: purchaseEventLabel, detail: model.purchaseSummary, tone: "economy" };
  } else if (hasValue(model.lapRewardSummary)) {
    persistentPayoff = { title: lapRewardEventLabel, detail: model.lapRewardSummary, tone: "economy" };
  } else if (hasValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    persistentPayoff = {
      title: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    };
  } else if (hasValue(model.fortuneDrawSummary)) {
    persistentPayoff = { title: fortuneDrawEventLabel, detail: model.fortuneDrawSummary, tone: "effect" };
  } else if (hasValue(model.trickSummary)) {
    persistentPayoff = { title: turnStage.fields.trick, detail: model.trickSummary, tone: "effect" };
  }
  const spotlightCards: SpotlightCard[] = [];
  const payoffBeats: SpectatorPayoffBeat[] = [];
  if (hasValue(model.weatherName) || hasValue(model.weatherEffect)) {
    spotlightCards.push({
      key: "weather",
      title: app.spectatorFields.weather,
      detail: valueOrDash(model.weatherSummary),
      tone: "effect",
    });
  }
  if (hasWorkerStatus(model)) {
    spotlightCards.push({
      key: "worker",
      title: app.spectatorFields.worker,
      detail: valueOrDash(workerStatusDetail),
      tone: "effect",
    });
    payoffBeats.push({
      key: "worker",
      title: app.spectatorFields.worker,
      detail: valueOrDash(workerStatusDetail),
      tone: "effect",
    });
  }
  if (hasValue(model.lapRewardSummary)) {
    spotlightCards.push({ key: "lap-reward", title: lapRewardEventLabel, detail: model.lapRewardSummary, tone: "economy" });
    payoffBeats.push({ key: "lap-reward", title: lapRewardEventLabel, detail: model.lapRewardSummary, tone: "economy" });
  }
  if (hasValue(model.purchaseSummary)) {
    spotlightCards.push({ key: "purchase", title: purchaseEventLabel, detail: model.purchaseSummary, tone: "economy" });
    payoffBeats.push({ key: "purchase", title: purchaseEventLabel, detail: model.purchaseSummary, tone: "economy" });
  }
  if (hasValue(model.rentSummary)) {
    spotlightCards.push({ key: "rent", title: rentEventLabel, detail: model.rentSummary, tone: "economy" });
    payoffBeats.push({ key: "rent", title: rentEventLabel, detail: model.rentSummary, tone: "economy" });
  }
  if (hasValue(model.fortuneDrawSummary)) {
    spotlightCards.push({ key: "fortune-draw", title: fortuneDrawEventLabel, detail: model.fortuneDrawSummary, tone: "effect" });
    payoffBeats.push({ key: "fortune-draw", title: fortuneDrawEventLabel, detail: model.fortuneDrawSummary, tone: "effect" });
  }
  if (hasValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    spotlightCards.push({
      key: "fortune-effect",
      title: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    });
    payoffBeats.push({
      key: "fortune-effect",
      title: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.trickSummary)) {
    spotlightCards.push({ key: "trick", title: turnStage.fields.trick, detail: model.trickSummary, tone: "effect" });
  }
  if (hasValue(model.markSummary)) {
    spotlightCards.push({ key: "mark", title: markEventLabel, detail: model.markSummary, tone: "effect" });
    payoffBeats.push({ key: "mark", title: markEventLabel, detail: model.markSummary, tone: "effect" });
  }
  if (hasValue(model.flipSummary)) {
    spotlightCards.push({ key: "flip", title: flipEventLabel, detail: model.flipSummary, tone: "effect" });
    payoffBeats.push({ key: "flip", title: flipEventLabel, detail: model.flipSummary, tone: "effect" });
  }
  if (hasValue(model.turnEndSummary)) {
    spotlightCards.push({
      key: "turn-end",
      title: turnEndLabel,
      detail: model.turnEndSummary,
      tone: "effect",
    });
  }
  const journeyCards: JourneyCard[] = [];
  if (hasValue(model.weatherName) || hasValue(model.weatherEffect)) {
    journeyCards.push({
      key: "weather",
      label: app.spectatorFields.weather,
      detail: valueOrDash(model.weatherSummary),
      tone: "effect",
    });
  }
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
  if (hasWorkerStatus(model)) {
    journeyCards.push({
      key: "worker",
      label: app.spectatorFields.worker,
      detail: valueOrDash(workerStatusSummary),
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
      label: landingEventLabel,
      detail: model.landingSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.purchaseSummary)) {
    journeyCards.push({
      key: "purchase",
      label: purchaseEventLabel,
      detail: model.purchaseSummary,
      tone: "economy",
    });
  }
  if (hasValue(model.rentSummary)) {
    journeyCards.push({
      key: "rent",
      label: rentEventLabel,
      detail: model.rentSummary,
      tone: "economy",
    });
  }
  if (hasValue(model.lapRewardSummary)) {
    journeyCards.push({
      key: "lap-reward",
      label: lapRewardEventLabel,
      detail: model.lapRewardSummary,
      tone: "economy",
    });
  }
  if (hasValue(model.fortuneDrawSummary)) {
    journeyCards.push({
      key: "fortune-draw",
      label: fortuneDrawEventLabel,
      detail: model.fortuneDrawSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    journeyCards.push({
      key: "fortune-effect",
      label: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.turnEndSummary)) {
    journeyCards.push({
      key: "turn-end",
      label: turnEndLabel,
      detail: model.turnEndSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.markSummary)) {
    journeyCards.push({
      key: "mark",
      label: markEventLabel,
      detail: model.markSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.flipSummary)) {
    journeyCards.push({
      key: "flip",
      label: flipEventLabel,
      detail: model.flipSummary,
      tone: "effect",
    });
  }
  if (!hasValue(model.fortuneResolvedSummary || model.fortuneSummary) && hasValue(model.trickSummary)) {
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
        {hasWorkerStatus(model) ? (
          <article
            className={`spectator-turn-card spectator-turn-card-worker spectator-turn-card-worker-${model.externalAiResolutionStatus || "idle"}`}
            data-testid="spectator-turn-worker"
          >
            <span>{app.spectatorFields.worker}</span>
            <strong>{valueOrDash(turnStage.workerStatusLabel(model.externalAiResolutionStatus))}</strong>
            <small>{valueOrDash(workerStatusDetail)}</small>
          </article>
        ) : null}
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

      {payoffBeats.length > 0 ? (
        <section className="core-action-payoff-sequence spectator-turn-payoff-sequence" data-testid="spectator-turn-payoff-sequence">
          <div className="core-action-journey-head">
            <strong>{app.spectatorFields.effect}</strong>
            <small>{valueOrDash(latestActionTitle)}</small>
          </div>
          <div className="core-action-payoff-strip">
            {payoffBeats.map((beat, index) => (
              <article key={beat.key} className={`core-action-result-card core-action-result-card-${beat.tone}`}>
                <div className="core-action-result-head">
                  <strong>{turnStage.sequenceIndex(index + 1, payoffBeats.length)}</strong>
                  <span>{beat.title}</span>
                </div>
                <p>{valueOrDash(beat.detail)}</p>
              </article>
            ))}
          </div>
        </section>
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

      {persistentPayoff ? (
        <article
          className={`spectator-turn-card spectator-turn-card-payoff spectator-turn-card-payoff-${persistentPayoff.tone}`}
          data-testid="spectator-turn-result"
        >
          <span>{app.spectatorFields.action}</span>
          <strong>{valueOrDash(persistentPayoff.title)}</strong>
          <small>{valueOrDash(persistentPayoff.detail)}</small>
        </article>
      ) : null}

      {hasValue(model.turnEndSummary) ? (
        <article className="spectator-turn-card spectator-turn-card-handoff" data-testid="spectator-turn-handoff">
          <span>{turnEndLabel}</span>
          <strong>{valueOrDash(model.turnEndSummary)}</strong>
          <small>{app.spectatorDescription}</small>
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
