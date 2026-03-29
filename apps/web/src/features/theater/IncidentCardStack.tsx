import type { TimelineItem } from "../../domain/selectors/streamSelectors";

type IncidentCardStackProps = {
  items: TimelineItem[];
};

export function IncidentCardStack({ items }: IncidentCardStackProps) {
  const top = items.slice(0, 3);
  return (
    <section className="panel">
      <h2>최근 사건</h2>
      <div className="incident-stack">
        {top.map((item) => (
          <article key={`incident-${item.seq}`} className="incident-card">
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
            <span>#{item.seq}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

