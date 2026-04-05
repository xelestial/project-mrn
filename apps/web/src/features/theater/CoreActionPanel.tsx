import type { CoreActionItem } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type CoreActionPanelProps = {
  items: CoreActionItem[];
  latest: CoreActionItem | null;
};

type ActionKind = "move" | "economy" | "effect" | "decision" | "system";

function normalize(value: string): string {
  return value.toLowerCase();
}

function classifyAction(item: CoreActionItem, theaterText: ReturnType<typeof useI18n>["theater"]): ActionKind {
  const haystack = normalize(`${item.label} ${item.detail}`);
  const includesAny = (terms: readonly string[]) => terms.some((term) => haystack.includes(normalize(term)));

  if (haystack.includes("move") || haystack.includes("dice") || includesAny(theaterText.actionKeywords.move)) {
    return "move";
  }

  if (
    haystack.includes("rent") ||
    haystack.includes("purchase") ||
    haystack.includes("cash") ||
    haystack.includes("shard") ||
    includesAny(theaterText.actionKeywords.economy)
  ) {
    return "economy";
  }

  if (
    haystack.includes("fortune") ||
    haystack.includes("weather") ||
    haystack.includes("trick") ||
    haystack.includes("flip") ||
    includesAny(theaterText.actionKeywords.effect)
  ) {
    return "effect";
  }

  if (haystack.includes("prompt") || haystack.includes("decision") || includesAny(theaterText.actionKeywords.decision)) {
    return "decision";
  }

  return "system";
}

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

function splitDetail(detail: string, noDetailLabel: string): string[] {
  const compact = detail.replace(/\s+/g, " ").trim();
  if (!compact || compact === "-") {
    return [noDetailLabel];
  }

  const pieces = compact
    .split(/\s*\|\s*|\s*\/\s*|(?<=\.)\s+/)
    .map((part) => part.trim())
    .filter(Boolean);

  return pieces.length > 0 ? pieces.slice(0, 3) : [compact];
}

function headlineDetail(item: CoreActionItem, theaterText: ReturnType<typeof useI18n>["theater"]): string {
  return splitDetail(item.detail, theaterText.noDetail)[0] ?? theaterText.noDetail;
}

export function CoreActionPanel({ items, latest }: CoreActionPanelProps) {
  const { theater } = useI18n();
  if (!latest && items.length === 0) {
    return null;
  }

  const latestKind = latest ? classifyAction(latest, theater) : "system";
  const feedItems = items.slice(0, 8);
  const turnFlowItems =
    latest && latest.round !== null && latest.turn !== null
      ? feedItems
          .filter((item) => item.round === latest.round && item.turn === latest.turn)
          .slice()
          .reverse()
      : [];
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
            {splitDetail(latest.detail, theater.noDetail).map((line, index) => (
              <div key={`latest-${latest.seq}-${index}`} className="core-action-detail-item">
                <span>{theater.detailHeading[latestKind]}</span>
                <strong>{line}</strong>
              </div>
            ))}
          </div>
        </article>
      ) : null}

      {turnFlowItems.length > 0 ? (
        <article className="core-action-journey" data-testid="core-action-journey">
          <div className="core-action-journey-head">
            <strong>{theater.turnFlowTitle}</strong>
            {latest ? <small>{theater.roundTurnBadge(latest.round, latest.turn)}</small> : null}
          </div>
          <div className="core-action-journey-strip">
            {turnFlowItems.map((item, index) => {
              const kind = classifyAction(item, theater);
              return (
                <div key={`journey-${item.seq}`} className={`core-action-journey-step core-action-journey-step-${kind}`}>
                  <span className="core-action-journey-index">0{index + 1}</span>
                  <span className="core-action-chip">{theater.actionKind[kind]}</span>
                  <strong>{item.label}</strong>
                  <small>{headlineDetail(item, theater)}</small>
                </div>
              );
            })}
          </div>
        </article>
      ) : null}

      {historyItems.length > 0 ? (
        <div className="core-action-feed-grid">
          {historyItems.map((item) => {
            const kind = classifyAction(item, theater);
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
                  {splitDetail(item.detail, theater.noDetail).map((line, index) => (
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
