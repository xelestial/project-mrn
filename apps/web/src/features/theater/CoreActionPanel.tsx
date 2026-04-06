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
  const payoffScenes = buildPayoffSceneItems(sameTurnItemsNewestFirst, theater);
  const turnFlowItems = sameTurnItemsNewestFirst.slice().reverse();
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
        <article className={`${actorToneClass(latest)} core-action-hero-${latestKind}`}>
          <div className="core-action-hero-meta">
            <span>{latest.actor}</span>
            <span className="core-action-chip">{theater.actionKind[latestKind]}</span>
            <span>{theater.roundTurnBadge(latest.round, latest.turn)}</span>
            <span>{theater.latestPublicAction}</span>
            <span>#{latest.seq}</span>
          </div>
          <strong>{latest.label}</strong>
          <p>{theater.panelLead[latestKind]}</p>
          <div className="core-action-detail-list">
            {splitCoreActionDetail(latest.detail, theater.noDetail).map((line, index) => (
              <div key={`latest-${latest.seq}-${index}`} className="core-action-detail-item">
                <span>{theater.detailHeading[latestKind]}</span>
                <strong>{line}</strong>
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
            {payoffScenes.map((scene) => (
              <article
                key={`payoff-${scene.seq}`}
                className={`core-action-result-card core-action-result-card-${scene.kind} ${
                  scene.isLatest ? "core-action-result-card-latest" : ""
                }`}
                data-testid={scene.isLatest ? "core-action-result-card" : undefined}
              >
                <div className="core-action-result-head">
                  <strong>{scene.phaseLabel}</strong>
                  <span>{scene.actor}</span>
                </div>
                <p>{scene.label}</p>
                <small className="core-action-result-caption">{resultHeadline(scene.kind, theater)}</small>
                <div className="core-action-detail-list">
                  {splitCoreActionDetail(scene.detail, theater.noDetail).map((line, index) => (
                    <div key={`result-${scene.seq}-${index}`} className="core-action-detail-item">
                      <span>{theater.detailHeading[scene.kind]}</span>
                      <strong>{line}</strong>
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
                <div key={`journey-${item.seq}`} className={`core-action-journey-step core-action-journey-step-${kind}`}>
                  <span className="core-action-journey-index">0{index + 1}</span>
                  <span className="core-action-chip">{theater.actionKind[kind]}</span>
                  <strong>{item.label}</strong>
                  <small>{headlineCoreActionDetail(item, theater)}</small>
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
