import type { ConnectionStatus } from "../../core/contracts/stream";
import type { RuntimeStatusResult } from "../../infra/http/sessionApi";

type ConnectionPanelProps = {
  status: ConnectionStatus;
  lastSeq: number;
  runtime: RuntimeStatusResult["runtime"];
};

function runtimeStatusLabel(status: string): string {
  switch (status) {
    case "running":
      return "진행 중";
    case "finished":
      return "종료됨";
    case "failed":
      return "실패";
    case "recovery_required":
      return "복구 필요";
    default:
      return status;
  }
}

function watchdogLabel(state: string | undefined): string {
  if (!state) {
    return "-";
  }
  if (state === "stalled_warning") {
    return "지연 경고";
  }
  if (state === "ok") {
    return "정상";
  }
  return state;
}

export function ConnectionPanel({ status, lastSeq, runtime }: ConnectionPanelProps) {
  return (
    <section className="panel">
      <h2>연결 상태</h2>
      <p>연결: {status}</p>
      <p>마지막 시퀀스: {lastSeq}</p>
      <p>런타임: {runtimeStatusLabel(runtime.status)}</p>
      <p>Watchdog: {watchdogLabel(runtime.watchdog_state)}</p>
      <p>마지막 활동(ms): {runtime.last_activity_ms ?? "-"}</p>
    </section>
  );
}
