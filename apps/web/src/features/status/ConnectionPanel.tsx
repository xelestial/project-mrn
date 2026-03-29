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
      <h2>Connection</h2>
      <p>Status: {status}</p>
      <p>Last Seq: {lastSeq}</p>
      <p>Runtime: {runtime.status}</p>
      <p>Watchdog: {runtime.watchdog_state ?? "-"}</p>
      <p>Last Activity: {runtime.last_activity_ms ?? "-"}</p>
    </section>
  );
}
