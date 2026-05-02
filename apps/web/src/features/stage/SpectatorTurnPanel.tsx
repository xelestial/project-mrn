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

type SpectatorTrainTone = "move" | "economy" | "effect" | "decision" | "system";

type SpectatorTrainItem = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: SpectatorTrainTone;
  testId?: string;
  labelTestId?: string;
  valueTestId?: string;
  detailTestId?: string;
  attrs?: Record<string, string | undefined>;
};

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

function compactText(value: string, maxLength = 22): string {
  const normalized = valueOrDash(value);
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(1, maxLength - 3))}...`;
}

function joinDetail(label: string, value: string, detail: string): string {
  const detailText = valueOrDash(detail);
  const valueText = valueOrDash(value);
  if (detailText === valueText) {
    return `${label}: ${detailText}`;
  }
  return `${label}: ${valueText} - ${detailText}`;
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
  const markEventCode = model.currentBeatEventCode === "mark_queued" ? "mark_queued" : "mark_resolved";
  const markEventLabel =
    (eventLabel.events as Record<string, string>)[markEventCode] ??
    app.spectatorFields.effect;
  const flipEventLabel = eventLabel.events.marker_flip ?? app.spectatorFields.effect;
  const turnEndLabel =
    (eventLabel.events as Record<string, string>)["turn_end_snapshot"] ??
    app.spectatorFields.progress;
  const title = actorPlayerId === null ? app.spectatorHeadline : app.spectatorTitle(actorPlayerId);
  const latestActionTitle = latestAction?.label ?? "-";
  const latestActionDetail = latestAction?.detail?.trim() ? latestAction.detail : "-";
  const latestActionTone = payoffToneForEventCode(latestAction?.eventCode ?? "");
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
  const payoffBeats: SpectatorPayoffBeat[] = [];
  const hasExternalWorkerStatus = hasWorkerStatus(model);
  const hasWorkerPayoff =
    hasExternalWorkerStatus &&
    (model.externalAiAttemptCount !== null ||
      model.externalAiAttemptLimit !== null ||
      model.externalAiResolutionStatus === "resolved_by_worker");
  if (hasExternalWorkerStatus) {
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
    payoffBeats.push({ key: "lap-reward", title: lapRewardEventLabel, detail: model.lapRewardSummary, tone: "economy" });
  }
  if (hasValue(model.purchaseSummary)) {
    payoffBeats.push({ key: "purchase", title: purchaseEventLabel, detail: model.purchaseSummary, tone: "economy" });
  }
  if (hasValue(model.rentSummary)) {
    payoffBeats.push({ key: "rent", title: rentEventLabel, detail: model.rentSummary, tone: "economy" });
  }
  if (hasValue(model.fortuneDrawSummary)) {
    payoffBeats.push({ key: "fortune-draw", title: fortuneDrawEventLabel, detail: model.fortuneDrawSummary, tone: "effect" });
  }
  if (hasValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    payoffBeats.push({
      key: "fortune-effect",
      title: fortuneResolvedEventLabel,
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.markSummary)) {
    payoffBeats.push({ key: "mark", title: markEventLabel, detail: model.markSummary, tone: "effect" });
  }
  if (hasValue(model.flipSummary)) {
    payoffBeats.push({ key: "flip", title: flipEventLabel, detail: model.flipSummary, tone: "effect" });
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
  const visibleJourneyCards = orderedJourneyCards.slice(0, 8);
  const hiddenJourneyCount = Math.max(0, orderedJourneyCards.length - visibleJourneyCards.length);
  const visiblePayoffBeats = orderedPayoffBeats.slice(0, 4);
  const hiddenPayoffCount = Math.max(0, orderedPayoffBeats.length - visiblePayoffBeats.length);
  const diceEventLabel = (eventLabel.events as Record<string, string>)["dice_roll"] ?? app.spectatorFields.move;
  const moveEventLabel = (eventLabel.events as Record<string, string>)["player_move"] ?? app.spectatorFields.move;
  const trickEventLabel = (eventLabel.events as Record<string, string>)["trick_used"] ?? turnStage.fields.trick;
  const fortuneCommonEffect =
    hasValue(model.fortuneResolvedSummary) || (hasValue(model.fortuneSummary) && model.fortuneSummary !== model.fortuneDrawSummary)
      ? model.fortuneResolvedSummary || model.fortuneSummary
      : "-";
  const commonEffectDetail = valueOrDash(app.spectatorEffectSummary([model.weatherSummary || model.weatherEffect, fortuneCommonEffect]));
  const trainItems: SpectatorTrainItem[] = [];
  const addTrainItem = (item: SpectatorTrainItem) => {
    trainItems.push(item);
  };
  const payoffAttrs = (key: string, tone: "economy" | "effect") =>
    persistentPayoff?.key === key
      ? {
          testId: "spectator-turn-result",
          labelTestId: "spectator-turn-result-title",
          detailTestId: "spectator-turn-result-detail",
          attrs: {
            "data-result-key": key,
            "data-result-tone": tone,
          },
        }
      : {};

  if (hasValue(model.markSummary)) {
    addTrainItem({
      key: "mark",
      label: markEventLabel,
      value: compactText(model.markSummary, 18),
      detail: model.markSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.character)) {
    addTrainItem({
      key: "character",
      label: app.spectatorFields.character,
      value: model.character,
      detail: model.character,
      tone: "decision",
      testId: "spectator-turn-character",
      valueTestId: "spectator-turn-character-name",
      attrs: { "data-character-name": dataAttrValue(model.character) },
    });
  }
  if (hasValue(model.trickSummary)) {
    addTrainItem({
      key: "trick",
      label: trickEventLabel,
      value: compactText(model.trickSummary, 20),
      detail: model.trickSummary,
      tone: "effect",
      ...payoffAttrs("trick", "effect"),
    });
  }
  if (hasValue(model.fortuneDrawSummary)) {
    addTrainItem({
      key: "fortune-draw",
      label: fortuneDrawEventLabel,
      value: compactText(model.fortuneDrawSummary, 20),
      detail: model.fortuneDrawSummary,
      tone: "effect",
      ...payoffAttrs("fortune-draw", "effect"),
    });
  }
  if (!hasValue(fortuneCommonEffect) && hasValue(model.fortuneResolvedSummary || model.fortuneSummary)) {
    addTrainItem({
      key: "fortune-effect",
      label: fortuneResolvedEventLabel,
      value: compactText(model.fortuneResolvedSummary || model.fortuneSummary, 20),
      detail: model.fortuneResolvedSummary || model.fortuneSummary,
      tone: "effect",
      ...payoffAttrs("fortune-effect", "effect"),
    });
  }
  if (hasValue(model.promptSummary)) {
    addTrainItem({
      key: "prompt",
      label: app.spectatorFields.prompt,
      value: compactText(model.promptSummary, 18),
      detail: model.currentBeatDetail || model.promptSummary,
      tone: "decision",
      testId: "spectator-turn-prompt",
      valueTestId: "spectator-turn-prompt-title",
      detailTestId: "spectator-turn-prompt-detail",
    });
  }
  if (hasExternalWorkerStatus) {
    addTrainItem({
      key: "worker",
      label: app.spectatorFields.worker,
      value: valueOrDash(turnStage.workerStatusLabel(model.externalAiResolutionStatus)),
      detail: workerStatusDetail,
      tone: "decision",
      testId: "spectator-turn-worker",
      valueTestId: "spectator-turn-worker-title",
      detailTestId: "spectator-turn-worker-detail",
      attrs: {
        "data-worker-id": dataAttrValue(model.externalAiWorkerId),
        "data-worker-failure-code": dataAttrValue(model.externalAiFailureCode),
        "data-worker-fallback-mode": dataAttrValue(model.externalAiFallbackMode),
        "data-worker-resolution-status": dataAttrValue(model.externalAiResolutionStatus),
        "data-worker-ready-state": dataAttrValue(model.externalAiReadyState),
        "data-worker-policy-mode": dataAttrValue(model.externalAiPolicyMode),
        "data-worker-adapter": dataAttrValue(model.externalAiWorkerAdapter),
        "data-worker-policy-class": dataAttrValue(model.externalAiPolicyClass),
        "data-worker-decision-style": dataAttrValue(model.externalAiDecisionStyle),
        "data-worker-attempt-count": dataAttrValue(model.externalAiAttemptCount),
        "data-worker-attempt-limit": dataAttrValue(model.externalAiAttemptLimit),
      },
    });
  }
  if (hasValue(model.diceSummary)) {
    addTrainItem({
      key: "dice",
      label: diceEventLabel,
      value: compactText(model.diceSummary, 18),
      detail: model.diceSummary,
      tone: "move",
    });
  }
  if (hasValue(model.moveSummary)) {
    addTrainItem({
      key: "move",
      label: moveEventLabel,
      value: compactText(model.moveSummary, 18),
      detail: model.moveSummary,
      tone: "move",
      testId: "spectator-turn-move",
      valueTestId: "spectator-turn-move-title",
    });
  }
  if (hasValue(model.landingSummary)) {
    addTrainItem({
      key: "landing",
      label: landingEventLabel,
      value: compactText(model.landingSummary, 18),
      detail: model.landingSummary,
      tone: "effect",
      testId: "spectator-turn-landing",
      valueTestId: "spectator-turn-landing-title",
    });
  }
  if (hasValue(model.rentSummary)) {
    addTrainItem({
      key: "rent",
      label: rentEventLabel,
      value: compactText(model.rentSummary, 18),
      detail: model.rentSummary,
      tone: "economy",
      ...payoffAttrs("rent", "economy"),
    });
  }
  if (hasValue(model.purchaseSummary)) {
    addTrainItem({
      key: "purchase",
      label: purchaseEventLabel,
      value: compactText(model.purchaseSummary, 18),
      detail: model.purchaseSummary,
      tone: "economy",
      ...payoffAttrs("purchase", "economy"),
    });
  }
  if (hasValue(model.lapRewardSummary)) {
    addTrainItem({
      key: "lap-reward",
      label: lapRewardEventLabel,
      value: compactText(model.lapRewardSummary, 18),
      detail: model.lapRewardSummary,
      tone: "economy",
      ...payoffAttrs("lap-reward", "economy"),
    });
  }
  if (hasValue(model.flipSummary)) {
    addTrainItem({
      key: "flip",
      label: flipEventLabel,
      value: compactText(model.flipSummary, 18),
      detail: model.flipSummary,
      tone: "effect",
    });
  }
  if (hasValue(model.turnEndSummary)) {
    addTrainItem({
      key: "turn-end",
      label: turnEndLabel,
      value: compactText(model.turnEndSummary, 18),
      detail: model.turnEndSummary,
      tone: "system",
      testId: "spectator-turn-handoff",
      valueTestId: "spectator-turn-handoff-title",
    });
  }
  if (trainItems.length === 0) {
    addTrainItem({
      key: "beat",
      label: app.spectatorFields.beat,
      value: valueOrDash(model.currentBeatLabel),
      detail: valueOrDash(model.currentBeatDetail || latestActionDetail),
      tone: "system",
    });
  }
  const visibleTrainItems = trainItems.slice(0, 8);
  const hiddenTrainCount = Math.max(0, trainItems.length - visibleTrainItems.length);

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

      <div className="spectator-turn-train" data-testid="spectator-turn-train">
        {visibleTrainItems.map((item, index) => (
          <article
            key={item.key}
            className={`spectator-turn-train-step spectator-turn-train-step-${item.tone}`}
            data-testid={item.testId ?? `spectator-turn-train-step-${index + 1}`}
            data-event-key={item.key}
            data-event-tone={item.tone}
            aria-label={joinDetail(item.label, item.value, item.detail)}
            tabIndex={0}
            title={joinDetail(item.label, item.value, item.detail)}
            {...item.attrs}
          >
            <span className="spectator-turn-train-index">{turnStage.sequenceIndex(index + 1, trainItems.length)}</span>
            <span className="spectator-turn-train-copy">
              <strong data-testid={item.labelTestId}>{item.label}</strong>
              <small data-testid={item.valueTestId}>{valueOrDash(item.value)}</small>
            </span>
            <span className="spectator-turn-train-tooltip" data-testid={item.detailTestId} role="tooltip">
              {joinDetail(item.label, item.value, item.detail)}
            </span>
          </article>
        ))}
        {hiddenTrainCount > 0 ? (
          <article className="spectator-turn-train-step spectator-turn-train-step-system spectator-turn-train-more">
            <span className="spectator-turn-train-index">{`+${hiddenTrainCount}`}</span>
            <span className="spectator-turn-train-copy">
              <strong>{app.spectatorFields.progress}</strong>
              <small>{app.spectatorEffectSummary(trainItems.slice(visibleTrainItems.length).map((item) => item.detail))}</small>
            </span>
          </article>
        ) : null}
      </div>

      {hasValue(commonEffectDetail) ? (
        <aside className="spectator-turn-common-effect" data-testid="spectator-turn-common-effect">
          <strong>{app.spectatorFields.commonEffect}</strong>
          <span data-testid="spectator-turn-common-effect-detail">{commonEffectDetail}</span>
        </aside>
      ) : null}

      <div className="spectator-turn-contracts" aria-hidden="true">
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
        {!hasValue(model.character) ? (
          <article
            className="spectator-turn-card"
            data-testid="spectator-turn-character"
            data-character-name={dataAttrValue(model.character)}
          >
            <span>{app.spectatorFields.character}</span>
            <strong data-testid="spectator-turn-character-name">{valueOrDash(model.character)}</strong>
          </article>
        ) : null}
        <article className="spectator-turn-card" data-testid="spectator-turn-action">
          <span>{app.spectatorFields.action}</span>
          <strong data-testid="spectator-turn-action-title">{valueOrDash(latestActionTitle)}</strong>
          <small data-testid="spectator-turn-action-detail">{valueOrDash(latestActionDetail)}</small>
        </article>
        {!hasValue(model.promptSummary) ? (
          <article className="spectator-turn-card" data-testid="spectator-turn-prompt">
            <span>{app.spectatorFields.prompt}</span>
            <strong data-testid="spectator-turn-prompt-title">{valueOrDash(model.promptSummary)}</strong>
            <small data-testid="spectator-turn-prompt-detail">{valueOrDash(model.currentBeatDetail)}</small>
          </article>
        ) : null}
        {orderedPayoffBeats.length > 0 ? (
        <section className="core-action-payoff-sequence spectator-turn-payoff-sequence" data-testid="spectator-turn-payoff-sequence">
          <div className="core-action-journey-head">
            <strong>{payoffTitle}</strong>
            <small>{valueOrDash(latestActionTitle)}</small>
          </div>
          <div className="core-action-payoff-strip">
            {visiblePayoffBeats.map((beat, index) => (
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
            {hiddenPayoffCount > 0 ? (
              <article className="core-action-result-card core-action-result-card-effect spectator-turn-more-card">
                <div className="core-action-result-head">
                  <strong>{`+${hiddenPayoffCount}`}</strong>
                  <span>{app.spectatorFields.effect}</span>
                </div>
                <p>{app.spectatorEffectSummary(orderedPayoffBeats.slice(visiblePayoffBeats.length).map((beat) => beat.detail))}</p>
              </article>
            ) : null}
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
            {visibleJourneyCards.map((card, index) => (
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
            {hiddenJourneyCount > 0 ? (
              <article className="core-action-journey-step core-action-journey-step-effect spectator-turn-more-card">
                <span className="core-action-journey-index">{`+${hiddenJourneyCount}`}</span>
                <strong>{app.spectatorFields.progress}</strong>
                <small>
                  {app.spectatorEffectSummary(orderedJourneyCards.slice(visibleJourneyCards.length).map((card) => card.detail))}
                </small>
              </article>
            ) : null}
          </div>
        </section>
        ) : null}

        {persistentPayoff && !visibleTrainItems.some((item) => item.testId === "spectator-turn-result") ? (
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

        {hasValue(model.turnEndSummary) && !visibleTrainItems.some((item) => item.testId === "spectator-turn-handoff") ? (
        <article className="spectator-turn-card spectator-turn-card-handoff" data-testid="spectator-turn-handoff">
          <span>{turnEndLabel}</span>
          <strong data-testid="spectator-turn-handoff-title">{valueOrDash(model.turnEndSummary)}</strong>
          <small>{app.spectatorDescription}</small>
        </article>
        ) : null}
      </div>
    </section>
  );
}
