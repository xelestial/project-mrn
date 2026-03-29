import type { SnapshotViewModel } from "../../domain/selectors/streamSelectors";

type BoardPanelProps = {
  snapshot: SnapshotViewModel | null;
};

function ringPosition(tileIndex: number): { row: number; col: number } {
  if (tileIndex <= 10) {
    return { row: 1, col: tileIndex + 1 };
  }
  if (tileIndex <= 19) {
    return { row: tileIndex - 9, col: 11 };
  }
  if (tileIndex <= 30) {
    return { row: 11, col: 31 - tileIndex };
  }
  return { row: 41 - tileIndex, col: 1 };
}

function tileKindLabel(kind: string): string {
  switch (kind) {
    case "S":
      return "운수";
    case "F1":
      return "종료-1";
    case "F2":
      return "종료-2";
    case "T2":
      return "토지";
    case "T3":
      return "핵심 토지";
    default:
      return kind;
  }
}

export function BoardPanel({ snapshot }: BoardPanelProps) {
  if (!snapshot || snapshot.tiles.length === 0) {
    return (
      <section className="panel">
        <h2>Board</h2>
        <p>아직 보드 스냅샷이 없습니다. `turn_end_snapshot` 이벤트를 기다리는 중입니다.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Board</h2>
      <p>
        라운드 {snapshot.round} / 턴 {snapshot.turn} / 징표 P
        {snapshot.markerOwnerPlayerId ?? "-"} / F {snapshot.fValue.toFixed(2)}
      </p>
      <div className="board-ring">
        {snapshot.tiles.map((tile) => (
          <article
            key={tile.tileIndex}
            className="tile-card"
            style={{
              gridRow: ringPosition(tile.tileIndex).row,
              gridColumn: ringPosition(tile.tileIndex).col,
            }}
          >
            <div className="tile-head">
              <strong>{tile.tileIndex}</strong>
              <span>{tileKindLabel(tile.tileKind)}</span>
            </div>
            <div className="tile-body">
              <small>{tile.zoneColor || "-"}</small>
              <small>구매 {tile.purchaseCost ?? "-"}</small>
              <small>통행료 {tile.rentCost ?? "-"}</small>
            </div>
            <div className="tile-foot">
              <small>소유 P{tile.ownerPlayerId ?? "-"}</small>
              <small>
                말:{" "}
                {tile.pawnPlayerIds.length > 0
                  ? tile.pawnPlayerIds.map((id) => `P${id}`).join(", ")
                  : "-"}
              </small>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
