import type { TimelineItem } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type TimelinePanelProps = {
  items: TimelineItem[];
};

export function TimelinePanel({ items }: TimelinePanelProps) {
  const { timeline } = useI18n();
  return (
    <section className="panel">
      <h2>{timeline.title(items.length)}</h2>
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
