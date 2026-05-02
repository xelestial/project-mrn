import type { CoreActionItem } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";
import {
  buildPayoffSceneItems,
  classifyCoreAction,
  headlineCoreActionDetail,
  splitCoreActionDetail,
  type ActionKind,
} from "./coreActionScene";

type CoreActionPanelProps = {
  items: CoreActionItem[];
  latest: CoreActionItem | null;
};

function actorToneClass(item: CoreActionItem): string {
  return item.isLocalActor ? "core-action-hero core-action-hero-local" : "core-action-hero";
}

function cardClassName(item: CoreActionItem, kind: ActionKind): string {
  const classes = ["core-action-feed-card", `core-action-feed-card-${kind}`];
  if (item.isLocalActor) {
    classes.push("core-action-feed-card-local");
  }
  return classes.join(" ");
}

function resultHeadline(kind: ActionKind, theaterText: ReturnType<typeof useI18n>["theater"]): string {
  if (kind === "economy") {
    return theaterText.panelLead.economy;
  }
  if (kind === "effect") {
    return theaterText.panelLead.effect;
  }
  return theaterText.panelLead.system;
}

function journeyPriority(item: CoreActionItem): number {
  switch (item.eventCode) {
    case "decision_timeout_fallback":
      return 0;
    case "decision_resolved":
      return 1;
    case "decision_requested":
      return 2;
    case "fortune_resolved":
    case "marker_flip":
    case "mark_queued":
    case "mark_resolved":
    case "marker_transferred":
      return 3;
    case "fortune_drawn":
    case "trick_used":
      return 4;
    case "rent_paid":
    case "tile_purchased":
    case "lap_reward_chosen":
      return 5;
    case "player_move":
    case "dice_roll":
      return 6;
    case "turn_start":
      return 7;
    case "turn_end_snapshot":
      return 8;
    default:
      return 20;
  }
}

export function CoreActionPanel({ items, latest }: CoreActionPanelProps) {
  const { theater } = useI18n();
  if (!latest && items.length === 0) {
    return null;
  }

  const latestKind = latest ? classifyCoreAction(latest, theater) : "system";
  const feedItems = items.slice(0, 8);
  const sameTurnItemsNewestFirst =
    latest && latest.round !== null && latest.turn !== null
      ? feedItems.filter((item) => item.round === latest.round && item.turn === latest.turn)
      : [];
  const payoffScenes = buildPayoffSceneItems(feedItems, theater);
  const turnFlowItems = sameTurnItemsNewestFirst
    .slice()
    .sort((left, right) => journeyPriority(left) - journeyPriority(right) || right.seq - left.seq);
  const turnFlowSeqs = new Set(turnFlowItems.map((item) => item.seq));
  const historyItems = feedItems.filter((item) => !turnFlowSeqs.has(item.seq));

  return (
    <section className="panel core-action-panel" data-testid="core-action-panel">
      <div className="core-action-panel-head">
        <div>
          <strong>{theater.coreActionTitle}</strong>
          <small>{theater.coreActionDescription}</small>
        </div>
      </div>

      {latest ? (
        <article
          className={`${actorToneClass(latest)} core-action-hero-${latestKind}`}
          data-testid="core-action-latest"
          data-latest-event-code={latest.eventCode}
          data-latest-kind={latestKind}
        >
          <div className="core-action-hero-meta">
            <span>{latest.actor}</span>
            <span className="core-action-chip">{theater.actionKind[latestKind]}</span>
            <span>{theater.roundTurnBadge(latest.round, latest.turn)}</span>
            <span>{theater.latestPublicAction}</span>
            <span>#{latest.seq}</span>
          </div>
          <strong data-testid="core-action-latest-title">{latest.label}</strong>
          <p data-testid="core-action-latest-detail">{theater.panelLead[latestKind]}</p>
          <div className="core-action-detail-list">
            {splitCoreActionDetail(latest.detail, theater.noDetail).map((line, index) => (
              <div key={`latest-${latest.seq}-${index}`} className="core-action-detail-item">
                <span>{theater.detailHeading[latestKind]}</span>
                <strong data-testid={index === 0 ? "core-action-latest-detail-line-0" : undefined}>{line}</strong>
              </div>
            ))}
          </div>
        </article>
      ) : null}

      {payoffScenes.length > 0 ? (
        <section className="core-action-payoff-sequence" data-testid="core-action-payoff-sequence">
          <div className="core-action-journey-head">
            <strong>{theater.payoffSceneTitle}</strong>
            {latest ? <small>{theater.roundTurnBadge(latest.round, latest.turn)}</small> : null}
          </div>
          <div className="core-action-payoff-strip">
            {payoffScenes.map((scene, index) => (
              <article
                key={`payoff-${scene.seq}`}
                className={`core-action-result-card core-action-result-card-${scene.kind} ${
                  scene.isLatest ? "core-action-result-card-latest" : ""
                }`}
                data-testid={scene.isLatest ? "core-action-result-card" : `core-action-result-card-${index + 1}`}
                data-result-event-code={scene.eventCode}
                data-result-kind={scene.kind}
              >
                <div className="core-action-result-head">
                  <strong>{theater.payoffBeatIndex(index + 1, payoffScenes.length, scene.phaseLabel)}</strong>
                  <span data-testid={scene.isLatest ? "core-action-result-actor" : `core-action-result-actor-${index + 1}`}>{scene.actor}</span>
                </div>
                <p data-testid={scene.isLatest ? "core-action-result-title" : `core-action-result-title-${index + 1}`}>{scene.headline}</p>
                <small className="core-action-result-caption">{resultHeadline(scene.kind, theater)}</small>
                <div className="core-action-detail-list">
                  {splitCoreActionDetail(scene.detail, theater.noDetail).map((line, index) => (
                    <div key={`result-${scene.seq}-${index}`} className="core-action-detail-item">
                      <span>{theater.detailHeading[scene.kind]}</span>
                      <strong
                        data-testid={
                          scene.isLatest && index === 0
                            ? "core-action-result-detail-line-0"
                            : index === 0
                              ? `core-action-result-detail-line-0-${scene.seq}`
                              : undefined
                        }
                      >
                        {line}
                      </strong>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {turnFlowItems.length > 0 ? (
        <article className="core-action-journey" data-testid="core-action-journey">
          <div className="core-action-journey-head">
            <strong>{theater.turnFlowTitle}</strong>
            {latest ? <small>{theater.roundTurnBadge(latest.round, latest.turn)}</small> : null}
          </div>
          <div className="core-action-journey-strip">
            {turnFlowItems.map((item, index) => {
              const kind = classifyCoreAction(item, theater);
              return (
                <div
                  key={`journey-${item.seq}`}
                  className={`core-action-journey-step core-action-journey-step-${kind}`}
                  data-testid={`core-action-journey-step-${index + 1}`}
                  data-journey-event-code={item.eventCode}
                  data-journey-kind={kind}
                >
                  <span className="core-action-journey-index">0{index + 1}</span>
                  <span className="core-action-chip">{theater.actionKind[kind]}</span>
                  <strong data-testid={`core-action-journey-step-title-${index + 1}`}>{item.label}</strong>
                  <small data-testid={`core-action-journey-step-detail-${index + 1}`}>{headlineCoreActionDetail(item, theater)}</small>
                </div>
              );
            })}
          </div>
        </article>
      ) : null}

      {historyItems.length > 0 ? (
        <div className="core-action-feed-grid">
          {historyItems.map((item) => {
            const kind = classifyCoreAction(item, theater);
            return (
              <article key={`core-action-${item.seq}`} className={cardClassName(item, kind)}>
                <div className="core-action-feed-meta">
                  <span>{item.actor}</span>
                  <span className="core-action-chip">{theater.actionKind[kind]}</span>
                  <span>#{item.seq}</span>
                </div>
                <strong>{item.label}</strong>
                <small>{theater.panelLead[kind]}</small>
                <div className="core-action-detail-list">
                  {splitCoreActionDetail(item.detail, theater.noDetail).map((line, index) => (
                    <div key={`feed-${item.seq}-${index}`} className="core-action-detail-item">
                      <span>{theater.detailHeading[kind]}</span>
                      <strong>{line}</strong>
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
