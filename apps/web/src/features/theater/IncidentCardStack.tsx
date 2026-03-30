import type { TheaterItem } from "../../domain/selectors/streamSelectors";

type IncidentCardStackProps = {
  items: TheaterItem[];
};

function toneBadge(tone: TheaterItem["tone"]): string {
  if (tone === "move") {
    return "이동";
  }
  if (tone === "economy") {
    return "경제";
  }
  if (tone === "critical") {
    return "경고";
  }
  return "진행";
}

export function IncidentCardStack({ items }: IncidentCardStackProps) {
  const top = items.slice(0, 10);
  return (
    <section className="panel">
      <h2>턴 극장</h2>
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
