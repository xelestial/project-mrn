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
  key: string;
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
    hasValue(model.externalAiPolicyMode) ||
    hasValue(model.externalAiWorkerAdapter) ||
    hasValue(model.externalAiPolicyClass) ||
    hasValue(model.externalAiDecisionStyle) ||
    model.externalAiAttemptCount !== null ||
    model.externalAiAttemptLimit !== null
  );
}

function dataAttrValue(value: string | number | null | undefined): string | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  const normalized = String(value).trim();
  return normalized ? normalized : undefined;
}

function journeyPriority(key: string): number {
  switch (key) {
    case "worker":
      return 0;
    case "flip":
      return 1;
    case "mark":
      return 2;
    case "effect":
    case "trick":
      return 3;
    case "fortune-effect":
      return 4;
    case "fortune-draw":
      return 5;
    case "rent":
      return 6;
    case "purchase":
      return 7;
    case "lap-reward":
      return 8;
    case "landing":
      return 9;
    case "move":
      return 10;
    case "prompt":
      return 11;
    case "character":
      return 12;
    case "weather":
      return 13;
    default:
      return 20;
  }
}

function payoffPriority(key: string): number {
  switch (key) {
    case "worker":
      return 0;
    case "flip":
      return 1;
    case "mark":
      return 2;
    case "trick":
      return 3;
    case "fortune-effect":
      return 4;
    case "fortune-draw":
      return 5;
    case "rent":
      return 6;
    case "purchase":
      return 7;
    case "lap-reward":
      return 8;
    default:
      return 20;
  }
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
  const latestActionTitle = latestAction?.label ?? "-";
  const latestActionDetail = latestAction?.detail?.trim() ? latestAction.detail : "-";
  const latestActionTone = payoffToneForEventCode(latestAction?.eventCode ?? "");
  const economyText = app.spectatorEconomySummary([model.purchaseSummary, model.rentSummary]);
  const effectText = app.spectatorEffectSummary([
    model.trickSummary,
    model.fortuneResolvedSummary || model.fortuneSummary,
    model.fortuneDrawSummary,
    model.markSummary,
    model.flipSummary,
    model.weatherSummary,
  ]);
  const spotlightSummary = app.spectatorSpotlightSummary([
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
    model.externalAiAttemptCount,
    model.externalAiAttemptLimit,
    model.externalAiReadyState,
    model.externalAiPolicyMode,
    model.externalAiWorkerAdapter,
    model.externalAiPolicyClass,
    model.externalAiDecisionStyle
  );
  const workerStatusDetail = stream.workerStatusDetail(
    turnStage.workerStatusLabel(model.externalAiResolutionStatus),
    model.externalAiWorkerId,
    model.externalAiFailureCode,
    model.externalAiFallbackMode,
    model.externalAiAttemptCount,
    model.externalAiAttemptLimit,
    model.externalAiReadyState,
    model.externalAiPolicyMode,
    model.externalAiWorkerAdapter,
    model.externalAiPolicyClass,
    model.externalAiDecisionStyle
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
        : app.spectatorNeutralSummary([model.currentBeatDetail, latestActionDetail]);
  let persistentPayoff: PersistentPayoff | null = null;
  if (hasValue(model.rentSummary)) {
    persistentPayoff = { key: "rent", title: rentEventLabel, detail: model.rentSummary, tone: "economy" };
  } else if (hasValue(model.purchaseSummary)) {
    persistentPayoff = { key: "purchase", title: purchaseEventLabel, detail: model.purchaseSummary, tone: "economy" };
  } else if (hasValue(model.lapRewardSummary)) {
    persistentPayoff = { key: "lap-reward", title: lapRewardEventLabel, detail: model.lapRewardSummary, tone: "economy" };
  } else if (hasValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    persistentPayoff = {
      key: "fortune-effect",
      title: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    };
  } else if (hasValue(model.fortuneDrawSummary)) {
    persistentPayoff = { key: "fortune-draw", title: fortuneDrawEventLabel, detail: model.fortuneDrawSummary, tone: "effect" };
  } else if (hasValue(model.trickSummary)) {
    persistentPayoff = { key: "trick", title: turnStage.fields.trick, detail: model.trickSummary, tone: "effect" };
  }
  const spotlightCards: SpotlightCard[] = [];
  const payoffBeats: SpectatorPayoffBeat[] = [];
  const hasExternalWorkerStatus = hasWorkerStatus(model);
  const hasWorkerPayoff =
    hasExternalWorkerStatus &&
    (model.externalAiAttemptCount !== null ||
      model.externalAiAttemptLimit !== null ||
      model.externalAiResolutionStatus === "resolved_by_worker");
  if (hasValue(model.weatherName) || hasValue(model.weatherEffect)) {
    spotlightCards.push({
      key: "weather",
      title: app.spectatorFields.weather,
      detail: valueOrDash(model.weatherSummary),
      tone: "effect",
    });
  }
  if (hasExternalWorkerStatus) {
    spotlightCards.push({
      key: "worker",
      title: app.spectatorFields.worker,
      detail: valueOrDash(workerStatusDetail),
      tone: "effect",
    });
    if (hasWorkerPayoff) {
      payoffBeats.push({
        key: "worker",
        title: app.spectatorFields.worker,
        detail: valueOrDash(workerStatusDetail),
        tone: "effect",
      });
    }
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
  const orderedPayoffBeats = payoffBeats.slice().sort((left, right) => payoffPriority(left.key) - payoffPriority(right.key));
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
  if (hasExternalWorkerStatus) {
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
  const orderedJourneyCards = journeyCards.slice().sort((left, right) => journeyPriority(left.key) - journeyPriority(right.key));

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
          <strong data-testid="spectator-turn-scene-title">{valueOrDash(model.currentBeatLabel)}</strong>
          <small data-testid="spectator-turn-scene-detail">
            {valueOrDash(latestActionTitle === "-" ? spotlightSummary : app.spectatorHeadlineSummary(latestActionTitle, spotlightSummary))}
          </small>
        </article>
        <article
          className="spectator-turn-card"
          data-testid="spectator-turn-weather"
          data-weather-name={dataAttrValue(model.weatherName)}
          data-weather-detail={dataAttrValue(model.weatherEffect)}
        >
          <span>{app.spectatorFields.weather}</span>
          <strong data-testid="spectator-turn-weather-name">{valueOrDash(model.weatherName)}</strong>
          <small data-testid="spectator-turn-weather-detail">{valueOrDash(model.weatherEffect)}</small>
        </article>
        <article
          className="spectator-turn-card"
          data-testid="spectator-turn-character"
          data-character-name={dataAttrValue(model.character)}
        >
          <span>{app.spectatorFields.character}</span>
          <strong data-testid="spectator-turn-character-name">{valueOrDash(model.character)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-action">
          <span>{app.spectatorFields.action}</span>
          <strong data-testid="spectator-turn-action-title">{valueOrDash(latestActionTitle)}</strong>
          <small data-testid="spectator-turn-action-detail">{valueOrDash(latestActionDetail)}</small>
        </article>
      {latestActionTitle !== "-" ? (
          <article
            className={`spectator-turn-card spectator-turn-card-payoff spectator-turn-card-payoff-${latestActionTone}`}
            data-testid="spectator-turn-payoff"
          >
            <span>{payoffTitle}</span>
            <strong data-testid="spectator-turn-payoff-title">{valueOrDash(payoffSummary)}</strong>
            <small data-testid="spectator-turn-payoff-detail">{valueOrDash(latestActionTitle)}</small>
          </article>
        ) : null}
        <article className="spectator-turn-card" data-testid="spectator-turn-prompt">
          <span>{app.spectatorFields.prompt}</span>
          <strong data-testid="spectator-turn-prompt-title">{valueOrDash(model.promptSummary)}</strong>
          <small data-testid="spectator-turn-prompt-detail">{valueOrDash(model.currentBeatDetail)}</small>
        </article>
        {hasWorkerStatus(model) ? (
          <article
            className={`spectator-turn-card spectator-turn-card-worker spectator-turn-card-worker-${model.externalAiResolutionStatus || "idle"}`}
            data-testid="spectator-turn-worker"
            data-worker-id={dataAttrValue(model.externalAiWorkerId)}
            data-worker-failure-code={dataAttrValue(model.externalAiFailureCode)}
            data-worker-fallback-mode={dataAttrValue(model.externalAiFallbackMode)}
            data-worker-resolution-status={dataAttrValue(model.externalAiResolutionStatus)}
            data-worker-ready-state={dataAttrValue(model.externalAiReadyState)}
            data-worker-policy-mode={dataAttrValue(model.externalAiPolicyMode)}
            data-worker-adapter={dataAttrValue(model.externalAiWorkerAdapter)}
            data-worker-policy-class={dataAttrValue(model.externalAiPolicyClass)}
            data-worker-decision-style={dataAttrValue(model.externalAiDecisionStyle)}
            data-worker-attempt-count={dataAttrValue(model.externalAiAttemptCount)}
            data-worker-attempt-limit={dataAttrValue(model.externalAiAttemptLimit)}
          >
            <span>{app.spectatorFields.worker}</span>
            <strong data-testid="spectator-turn-worker-title">{valueOrDash(turnStage.workerStatusLabel(model.externalAiResolutionStatus))}</strong>
            <small data-testid="spectator-turn-worker-detail">{valueOrDash(workerStatusDetail)}</small>
          </article>
        ) : null}
        <article className="spectator-turn-card" data-testid="spectator-turn-move">
          <span>{app.spectatorFields.move}</span>
          <strong data-testid="spectator-turn-move-title">{valueOrDash(model.moveSummary)}</strong>
        </article>
        <article className="spectator-turn-card" data-testid="spectator-turn-landing">
          <span>{app.spectatorFields.landing}</span>
          <strong data-testid="spectator-turn-landing-title">{valueOrDash(model.landingSummary)}</strong>
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

      {orderedPayoffBeats.length > 0 ? (
        <section className="core-action-payoff-sequence spectator-turn-payoff-sequence" data-testid="spectator-turn-payoff-sequence">
          <div className="core-action-journey-head">
            <strong>{payoffTitle}</strong>
            <small>{valueOrDash(latestActionTitle)}</small>
          </div>
          <div className="core-action-payoff-strip">
            {orderedPayoffBeats.map((beat, index) => (
              <article
                key={beat.key}
                className={`core-action-result-card core-action-result-card-${beat.tone}`}
                data-testid={`spectator-turn-payoff-step-${index + 1}`}
                data-beat-key={beat.key}
                data-beat-tone={beat.tone}
              >
                <div className="core-action-result-head">
                  <strong>{turnStage.sequenceIndex(index + 1, orderedPayoffBeats.length)}</strong>
                  <span data-testid={`spectator-turn-payoff-step-title-${index + 1}`}>{beat.title}</span>
                </div>
                <p data-testid={`spectator-turn-payoff-step-detail-${index + 1}`}>{valueOrDash(beat.detail)}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {orderedJourneyCards.length > 0 ? (
        <section className="core-action-journey spectator-turn-journey" data-testid="spectator-turn-journey">
          <div className="core-action-journey-head">
            <strong>{turnStage.progressTitle}</strong>
            <small>{valueOrDash(latestActionTitle)}</small>
          </div>
          <div className="core-action-journey-strip">
            {orderedJourneyCards.map((card, index) => (
              <article
                key={card.key}
                className={`core-action-journey-step core-action-journey-step-${card.tone}`}
                data-testid={`spectator-turn-journey-step-${index + 1}`}
                data-step-key={card.key}
                data-step-tone={card.tone}
              >
                <span className="core-action-journey-index">{`0${index + 1}`}</span>
                <strong data-testid={`spectator-turn-journey-step-title-${index + 1}`}>{card.label}</strong>
                <small data-testid={`spectator-turn-journey-step-detail-${index + 1}`}>{valueOrDash(card.detail)}</small>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {persistentPayoff ? (
        <article
          className={`spectator-turn-card spectator-turn-card-payoff spectator-turn-card-payoff-${persistentPayoff.tone}`}
          data-testid="spectator-turn-result"
          data-result-key={persistentPayoff.key}
          data-result-tone={persistentPayoff.tone}
        >
          <span>{app.spectatorFields.action}</span>
          <strong data-testid="spectator-turn-result-title">{valueOrDash(persistentPayoff.title)}</strong>
          <small data-testid="spectator-turn-result-detail">{valueOrDash(persistentPayoff.detail)}</small>
        </article>
      ) : null}

      {hasValue(model.turnEndSummary) ? (
        <article className="spectator-turn-card spectator-turn-card-handoff" data-testid="spectator-turn-handoff">
          <span>{turnEndLabel}</span>
          <strong data-testid="spectator-turn-handoff-title">{valueOrDash(model.turnEndSummary)}</strong>
          <small>{app.spectatorDescription}</small>
        </article>
      ) : null}

    </section>
  );
}
