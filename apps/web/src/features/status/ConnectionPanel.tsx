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
    case "finished":
      return labels.finished;
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
    <section className="panel">
      <h2>{connection.title}</h2>
      <p>{connection.fields.connection}: {status}</p>
      <p>{connection.fields.lastSequence}: {lastSeq}</p>
      <p>{connection.fields.runtime}: {runtimeStatusLabel(runtime.status, connection.runtimeStatus)}</p>
      <p>{connection.fields.watchdog}: {watchdogLabel(runtime.watchdog_state, connection.watchdogStatus)}</p>
      <p>{connection.fields.lastActivityMs}: {runtime.last_activity_ms ?? "-"}</p>
    </section>
  );
}
