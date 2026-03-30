import type { TheaterItem } from "../../domain/selectors/streamSelectors";

type IncidentCardStackProps = {
  items: TheaterItem[];
};

function toneBadge(tone: TheaterItem["tone"]): string {
  if (tone === "move") {
    return "MOVE";
  }
  if (tone === "economy") {
    return "ECO";
  }
  if (tone === "critical") {
    return "ALERT";
  }
  return "SYS";
}

export function IncidentCardStack({ items }: IncidentCardStackProps) {
  const top = items.slice(0, 10);
  return (
    <section className="panel">
      <h2>Turn Theater</h2>
      <div className="incident-stack">
        {top.map((item) => (
          <article key={`incident-${item.seq}`} className={`incident-card incident-${item.tone}`}>
            <div className="incident-meta">
              <span className="incident-badge">{toneBadge(item.tone)}</span>
              <span className="incident-seq">#{item.seq}</span>
            </div>
            <strong>
              {item.actor} - {item.label}
            </strong>
            <small>{item.detail || "-"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
