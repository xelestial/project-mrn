import type { ConnectionStatus } from "../../core/contracts/stream";
import type { RuntimeStatusResult } from "../../infra/http/sessionApi";
import { useI18n } from "../../i18n/useI18n";

type ConnectionPanelProps = {
  status: ConnectionStatus;
  lastSeq: number;
  runtime: RuntimeStatusResult["runtime"];
};

function runtimeStatusLabel(status: string, labels: ReturnType<typeof useI18n>["connection"]["runtimeStatus"]): string {
  switch (status) {
    case "running":
      return labels.running;
    case "completed":
      return labels.completed;
    case "failed":
      return labels.failed;
    case "recovery_required":
      return labels.recovery_required;
    default:
      return status;
  }
}

function watchdogLabel(
  state: string | undefined,
  labels: ReturnType<typeof useI18n>["connection"]["watchdogStatus"]
): string {
  if (!state) {
    return "-";
  }
  if (state === "stalled_warning") {
    return labels.stalled_warning;
  }
  if (state === "ok") {
    return labels.ok;
  }
  return state;
}

export function ConnectionPanel({ status, lastSeq, runtime }: ConnectionPanelProps) {
  const { connection } = useI18n();
  return (
    <section className="panel connection-panel">
      <div className="panel-head">
        <h2>{connection.title}</h2>
      </div>
      <div className="connection-grid">
        <article className="connection-card">
          <span>{connection.fields.connection}</span>
          <strong>{status}</strong>
        </article>
        <article className="connection-card">
          <span>{connection.fields.runtime}</span>
          <strong>{runtimeStatusLabel(runtime.status, connection.runtimeStatus)}</strong>
        </article>
        <article className="connection-card">
          <span>{connection.fields.lastSequence}</span>
          <strong>{lastSeq}</strong>
        </article>
        <article className="connection-card">
          <span>{connection.fields.watchdog}</span>
          <strong>{watchdogLabel(runtime.watchdog_state, connection.watchdogStatus)}</strong>
        </article>
        <article className="connection-card connection-card-wide">
          <span>{connection.fields.lastActivityMs}</span>
          <strong>{runtime.last_activity_ms ?? "-"}</strong>
        </article>
      </div>
    </section>
  );
}
