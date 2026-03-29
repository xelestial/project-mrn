import type { TimelineItem } from "../../domain/selectors/streamSelectors";

type TimelinePanelProps = {
  items: TimelineItem[];
};

export function TimelinePanel({ items }: TimelinePanelProps) {
  return (
    <section className="panel">
      <h2>Timeline ({items.length})</h2>
      <div className="timeline">
        {items.map((item) => (
          <article key={item.seq} className="timeline-item">
            <strong>#{item.seq}</strong>
            <span>{item.label}</span>
            <small>{item.detail}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

