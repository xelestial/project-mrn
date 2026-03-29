import type { TimelineItem } from "../../domain/selectors/streamSelectors";

type IncidentCardStackProps = {
  items: TimelineItem[];
};

function toneOf(item: TimelineItem): "move" | "economy" | "system" {
  if (item.label.includes("이동") || item.label.includes("턴")) {
    return "move";
  }
  if (item.label.includes("구매") || item.label.includes("징표") || item.label.includes("보상")) {
    return "economy";
  }
  return "system";
}

function toneBadge(tone: "move" | "economy" | "system"): string {
  if (tone === "move") {
    return "이동";
  }
  if (tone === "economy") {
    return "정산";
  }
  return "시스템";
}

export function IncidentCardStack({ items }: IncidentCardStackProps) {
  const top = items.slice(0, 5);
  return (
    <section className="panel">
      <h2>최근 사건 카드</h2>
      <div className="incident-stack">
        {top.map((item) => {
          const tone = toneOf(item);
          return (
            <article key={`incident-${item.seq}`} className={`incident-card incident-${tone}`}>
              <div className="incident-meta">
                <span className="incident-badge">{toneBadge(tone)}</span>
                <span className="incident-seq">#{item.seq}</span>
              </div>
              <strong>{item.label}</strong>
              <small>{item.detail || "-"}</small>
            </article>
          );
        })}
      </div>
    </section>
  );
}
