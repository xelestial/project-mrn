import { useMemo, useState } from "react";
import type { TheaterItem } from "../../domain/selectors/streamSelectors";
import { useI18n } from "../../i18n/useI18n";

type IncidentCardStackProps = {
  items: TheaterItem[];
  focusPlayerId?: number | null;
};

type LaneKey = "core" | "prompt" | "system";

function toneBadge(tone: TheaterItem["tone"], theaterText: ReturnType<typeof useI18n>["theater"]): string {
  switch (tone) {
    case "move":
      return theaterText.toneBadge.move;
    case "economy":
      return theaterText.toneBadge.economy;
    case "critical":
      return theaterText.toneBadge.critical;
    default:
      return theaterText.toneBadge.system;
  }
}

export function IncidentCardStack({ items, focusPlayerId }: IncidentCardStackProps) {
  const { theater } = useI18n();
  const [collapsed, setCollapsed] = useState<Record<LaneKey, boolean>>({
    core: false,
    prompt: false,
    system: true,
  });

  const topItems = items.slice(0, 30);
  const focusActor = focusPlayerId && Number.isFinite(focusPlayerId) ? `P${focusPlayerId}` : null;

  const sections = useMemo(() => {
    const coreBase = topItems.filter((item) => item.lane === "core");
    const promptBase = topItems.filter((item) => item.lane === "prompt");
    const systemBase = topItems.filter((item) => item.lane === "system");

    const core = focusActor
      ? [...coreBase.filter((item) => item.actor !== focusActor), ...coreBase.filter((item) => item.actor === focusActor)]
      : coreBase;

    const promptPriority = (eventCode: string): number => {
      if (eventCode === "decision_resolved") return 0;
      if (eventCode === "decision_timeout_fallback") return 1;
      if (eventCode === "decision_ack") return 2;
      if (eventCode === "decision_requested") return 3;
      if (eventCode === "prompt") return 4;
      return 5;
    };

    const promptOrdered = [...promptBase].sort((a, b) => {
      const rank = promptPriority(a.eventCode) - promptPriority(b.eventCode);
      if (rank !== 0) {
        return rank;
      }
      return b.seq - a.seq;
    });

    return {
      core: core.slice(0, 14),
      prompt: promptOrdered.slice(0, 10),
      system: systemBase.slice(0, 6),
    };
  }, [focusActor, topItems]);

  const coreHero = sections.core[0] ?? null;
  const sectionList: Array<{ key: LaneKey; items: TheaterItem[] }> = [
    { key: "core", items: sections.core },
    { key: "prompt", items: sections.prompt },
    { key: "system", items: sections.system },
  ];

  return (
    <section className="panel incident-panel">
      <div className="incident-panel-head">
        <div>
          <h2>{theater.incidentTitle}</h2>
          <small>{theater.incidentDescription}</small>
        </div>
      </div>

      {coreHero ? (
        <article className={`incident-hero incident-${coreHero.tone}`}>
          <div className="incident-meta">
            <div className="incident-meta-left">
              <span className="incident-badge">{toneBadge(coreHero.tone, theater)}</span>
              <span className="incident-badge incident-lane-badge">{theater.laneBadge[coreHero.lane]}</span>
            </div>
            <span className="incident-seq">#{coreHero.seq}</span>
          </div>
          <strong>
            {coreHero.actor} - {coreHero.label}
          </strong>
          <p>{coreHero.detail || "-"}</p>
        </article>
      ) : null}

      <div className="incident-stack">
        {sectionList.map((section) => (
          <div key={section.key} className="incident-lane-group">
            <div className="incident-lane-header">
              <div>
                <h3>{theater.laneTitle[section.key]}</h3>
                <small className="incident-lane-subtitle">{theater.laneDescription[section.key]}</small>
              </div>
              <button
                type="button"
                className="incident-lane-toggle"
                onClick={() =>
                  setCollapsed((prev) => ({
                    ...prev,
                    [section.key]: !prev[section.key],
                  }))
                }
              >
                {collapsed[section.key] ? theater.expand : theater.collapse}
              </button>
            </div>

            {collapsed[section.key] ? null : section.items.length === 0 ? (
              <small className="incident-empty">{theater.laneEmpty[section.key]}</small>
            ) : (
              <div className="incident-lane-list">
                {section.items.map((item, index) => (
                  <article
                    key={`incident-${section.key}-${item.seq}`}
                    className={`incident-card incident-${item.tone} incident-lane-${item.lane} ${
                      section.key === "core" && index === 0 ? "incident-card-emphasis" : ""
                    }`}
                  >
                    <div className="incident-meta">
                      <div className="incident-meta-left">
                        <span className="incident-badge">{toneBadge(item.tone, theater)}</span>
                        <span className="incident-badge incident-lane-badge">{theater.laneBadge[item.lane]}</span>
                      </div>
                      <span className="incident-seq">#{item.seq}</span>
                    </div>
                    <strong>
                      {item.actor} - {item.label}
                    </strong>
                    <small>{item.detail || "-"}</small>
                  </article>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
