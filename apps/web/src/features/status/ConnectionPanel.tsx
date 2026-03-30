import type { ConnectionStatus } from "../../core/contracts/stream";
import type { RuntimeStatusResult } from "../../infra/http/sessionApi";

type ConnectionPanelProps = {
  status: ConnectionStatus;
  lastSeq: number;
  runtime: RuntimeStatusResult["runtime"];
};

export function ConnectionPanel({ status, lastSeq, runtime }: ConnectionPanelProps) {
  return (
    <section className="panel">
      <h2>연결 상태</h2>
      <p>연결: {status}</p>
      <p>마지막 시퀀스: {lastSeq}</p>
      <p>런타임: {runtime.status}</p>
      <p>Watchdog: {runtime.watchdog_state ?? "-"}</p>
      <p>마지막 활동(ms): {runtime.last_activity_ms ?? "-"}</p>
    </section>
  );
}
