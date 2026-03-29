import type { ConnectionStatus } from "../../core/contracts/stream";

type ConnectionPanelProps = {
  status: ConnectionStatus;
  lastSeq: number;
  runtime: string;
};

export function ConnectionPanel({ status, lastSeq, runtime }: ConnectionPanelProps) {
  return (
    <section className="panel">
      <h2>Connection</h2>
      <p>Status: {status}</p>
      <p>Last Seq: {lastSeq}</p>
      <p>Runtime: {runtime}</p>
    </section>
  );
}

