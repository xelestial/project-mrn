import type { CoreActionItem } from "../../domain/selectors/streamSelectors";

type CoreActionPanelProps = {
  items: CoreActionItem[];
  latest: CoreActionItem | null;
};

type ActionKind = "move" | "economy" | "effect" | "decision" | "system";

function normalize(value: string): string {
  return value.toLowerCase();
}

function classifyAction(item: CoreActionItem): ActionKind {
  const haystack = normalize(`${item.label} ${item.detail}`);

  if (
    haystack.includes("이동") ||
    haystack.includes("주사위") ||
    haystack.includes("dice") ||
    haystack.includes("move") ||
    haystack.includes("도착")
  ) {
    return "move";
  }

  if (
    haystack.includes("구매") ||
    haystack.includes("렌트") ||
    haystack.includes("통행료") ||
    haystack.includes("cash") ||
    haystack.includes("shard") ||
    haystack.includes("lap reward") ||
    haystack.includes("보상")
  ) {
    return "economy";
  }

  if (
    haystack.includes("운수") ||
    haystack.includes("fortune") ||
    haystack.includes("날씨") ||
    haystack.includes("weather") ||
    haystack.includes("잔꾀") ||
    haystack.includes("trick") ||
    haystack.includes("flip")
  ) {
    return "effect";
  }

  if (
    haystack.includes("선택") ||
    haystack.includes("드래프트") ||
    haystack.includes("지목") ||
    haystack.includes("결정") ||
    haystack.includes("prompt") ||
    haystack.includes("decision")
  ) {
    return "decision";
  }

  return "system";
}

function actionKindLabel(kind: ActionKind): string {
  switch (kind) {
    case "move":
      return "이동";
    case "economy":
      return "경제";
    case "effect":
      return "효과";
    case "decision":
      return "선택";
    default:
      return "진행";
  }
}

function panelLead(kind: ActionKind): string {
  switch (kind) {
    case "move":
      return "말 이동과 도착 결과를 보여줍니다.";
    case "economy":
      return "구매, 렌트, 보상처럼 자원이 바뀐 순간입니다.";
    case "effect":
      return "날씨, 운수, 잔꾀, 카드 효과가 적용된 순간입니다.";
    case "decision":
      return "누군가 선택하거나 응답한 흐름입니다.";
    default:
      return "턴 진행 중 공개된 주요 상태 변화입니다.";
  }
}

function actorToneClass(item: CoreActionItem): string {
  return item.isLocalActor ? "core-action-hero core-action-hero-local" : "core-action-hero";
}

function cardClassName(item: CoreActionItem): string {
  const kind = classifyAction(item);
  const classes = ["core-action-feed-card", `core-action-feed-card-${kind}`];
  if (item.isLocalActor) {
    classes.push("core-action-feed-card-local");
  }
  return classes.join(" ");
}

function splitDetail(detail: string): string[] {
  const compact = detail.replace(/\s+/g, " ").trim();
  if (!compact || compact === "-") {
    return ["상세 정보 없음"];
  }

  const pieces = compact
    .split(/\s*\|\s*|\s*\/\s*|(?<=\.)\s+/)
    .map((part) => part.trim())
    .filter(Boolean);

  return pieces.length > 0 ? pieces.slice(0, 3) : [compact];
}

function detailHeading(kind: ActionKind): string {
  switch (kind) {
    case "move":
      return "이동 결과";
    case "economy":
      return "자원 변화";
    case "effect":
      return "적용 효과";
    case "decision":
      return "선택 내용";
    default:
      return "상세";
  }
}

export function CoreActionPanel({ items, latest }: CoreActionPanelProps) {
  if (!latest && items.length === 0) {
    return null;
  }

  const latestKind = latest ? classifyAction(latest) : "system";
  const feedItems = items.slice(0, 8);

  return (
    <section className="panel core-action-panel">
      <div className="core-action-panel-head">
        <div>
          <strong>최근 공개 행동</strong>
          <small>다른 플레이어를 포함해 모두에게 공개된 이동, 구매, 렌트, 운수, 잔꾀 흐름을 한눈에 보여줍니다.</small>
        </div>
      </div>

      {latest ? (
        <article className={`${actorToneClass(latest)} core-action-hero-${latestKind}`}>
          <div className="core-action-hero-meta">
            <span>{latest.actor}</span>
            <span className="core-action-chip">{actionKindLabel(latestKind)}</span>
            <span>최신 공개 행동</span>
            <span>#{latest.seq}</span>
          </div>
          <strong>{latest.label}</strong>
          <p>{panelLead(latestKind)}</p>
          <div className="core-action-detail-list">
            {splitDetail(latest.detail).map((line, index) => (
              <div key={`latest-${latest.seq}-${index}`} className="core-action-detail-item">
                <span>{detailHeading(latestKind)}</span>
                <strong>{line}</strong>
              </div>
            ))}
          </div>
        </article>
      ) : null}

      {feedItems.length > 0 ? (
        <div className="core-action-feed-grid">
          {feedItems.map((item) => {
            const kind = classifyAction(item);
            return (
              <article key={`core-action-${item.seq}`} className={cardClassName(item)}>
                <div className="core-action-feed-meta">
                  <span>{item.actor}</span>
                  <span className="core-action-chip">{actionKindLabel(kind)}</span>
                  <span>#{item.seq}</span>
                </div>
                <strong>{item.label}</strong>
                <small>{panelLead(kind)}</small>
                <div className="core-action-detail-list">
                  {splitDetail(item.detail).map((line, index) => (
                    <div key={`feed-${item.seq}-${index}`} className="core-action-detail-item">
                      <span>{detailHeading(kind)}</span>
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
