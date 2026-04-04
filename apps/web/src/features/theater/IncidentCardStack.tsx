import { useMemo, useState } from "react";
import type { TheaterItem } from "../../domain/selectors/streamSelectors";

type IncidentCardStackProps = {
  items: TheaterItem[];
  focusPlayerId?: number | null;
};

type LaneKey = "core" | "prompt" | "system";

function toneBadge(tone: TheaterItem["tone"]): string {
  switch (tone) {
    case "move":
      return "이동";
    case "economy":
      return "경제";
    case "critical":
      return "중요";
    default:
      return "진행";
  }
}

function laneBadge(lane: TheaterItem["lane"]): string {
  switch (lane) {
    case "core":
      return "공개 행동";
    case "prompt":
      return "선택 요청";
    default:
      return "시스템";
  }
}

function laneTitle(lane: LaneKey): string {
  switch (lane) {
    case "core":
      return "턴 진행";
    case "prompt":
      return "선택 흐름";
    default:
      return "시스템 기록";
  }
}

function laneDescription(lane: LaneKey): string {
  switch (lane) {
    case "core":
      return "이동, 구매, 렌트, 운수처럼 모두에게 공개되는 흐름입니다.";
    case "prompt":
      return "선택 요청, 응답, 타임아웃 대체를 추적합니다.";
    default:
      return "연결 상태, 회복, 경고 같은 시스템 메시지입니다.";
  }
}

function emptyMessage(lane: LaneKey): string {
  switch (lane) {
    case "core":
      return "아직 공개된 턴 진행이 없습니다.";
    case "prompt":
      return "아직 선택 요청 흐름이 없습니다.";
    default:
      return "시스템 기록이 없습니다.";
  }
}

export function IncidentCardStack({ items, focusPlayerId }: IncidentCardStackProps) {
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
          <h2>턴 극장</h2>
          <small>공개 행동, 선택 흐름, 시스템 기록을 나눠서 보여줍니다. 다른 플레이어의 턴도 여기서 따라갈 수 있습니다.</small>
        </div>
      </div>

      {coreHero ? (
        <article className={`incident-hero incident-${coreHero.tone}`}>
          <div className="incident-meta">
            <div className="incident-meta-left">
              <span className="incident-badge">{toneBadge(coreHero.tone)}</span>
              <span className="incident-badge incident-lane-badge">{laneBadge(coreHero.lane)}</span>
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
                <h3>{laneTitle(section.key)}</h3>
                <small className="incident-lane-subtitle">{laneDescription(section.key)}</small>
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
                {collapsed[section.key] ? "펼치기" : "접기"}
              </button>
            </div>

            {collapsed[section.key] ? null : section.items.length === 0 ? (
              <small className="incident-empty">{emptyMessage(section.key)}</small>
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
                        <span className="incident-badge">{toneBadge(item.tone)}</span>
                        <span className="incident-badge incident-lane-badge">{laneBadge(item.lane)}</span>
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
