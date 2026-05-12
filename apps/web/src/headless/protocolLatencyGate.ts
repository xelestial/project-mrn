import type { ProtocolCommandLatencyDiagnostic } from "./fullStackProtocolHarness";

export type ProtocolLatencyGateOffender = ProtocolCommandLatencyDiagnostic & {
  maxMs: number;
};

export type ProtocolLatencyGateSummary = {
  ok: boolean;
  thresholdMs: number;
  maxCommandMs: number | null;
  offenders: ProtocolLatencyGateOffender[];
  failures: string[];
};

export function evaluateProtocolLatencyGate(args: {
  commands: ProtocolCommandLatencyDiagnostic[];
  maxCommandLatencyMs?: number;
}): ProtocolLatencyGateSummary {
  const thresholdMs = Math.max(1, Math.floor(args.maxCommandLatencyMs ?? 0));
  const commands = args.commands.map((command) => ({
    ...command,
    maxMs: protocolCommandLatencyMs(command),
  }));
  const maxCommandMs = commands.length > 0
    ? Math.max(...commands.map((command) => command.maxMs))
    : null;
  if (!args.maxCommandLatencyMs) {
    return {
      ok: true,
      thresholdMs,
      maxCommandMs,
      offenders: [],
      failures: [],
    };
  }
  const offenders = commands
    .filter((command) => command.maxMs > thresholdMs)
    .sort((left, right) => right.maxMs - left.maxMs);
  return {
    ok: offenders.length === 0,
    thresholdMs,
    maxCommandMs,
    offenders,
    failures: offenders.map((command) => formatProtocolLatencyFailure(command, thresholdMs)),
  };
}

export function protocolCommandLatencyMs(command: ProtocolCommandLatencyDiagnostic): number {
  return Math.max(
    command.totalMs ?? 0,
    command.promptToDecisionMs ?? 0,
    command.decisionToAckMs ?? 0,
  );
}

function formatProtocolLatencyFailure(command: ProtocolLatencyGateOffender, thresholdMs: number): string {
  return [
    `protocol command latency exceeded ${thresholdMs}ms`,
    `request_id=${command.requestId}`,
    `request_type=${command.requestType ?? "unknown"}`,
    `player_id=${command.playerId}`,
    `max_ms=${command.maxMs}`,
    `total_ms=${command.totalMs ?? "unknown"}`,
    `prompt_to_decision_ms=${command.promptToDecisionMs ?? "unknown"}`,
    `decision_to_ack_ms=${command.decisionToAckMs ?? "unknown"}`,
    `status=${command.status ?? "unknown"}`,
  ].join(" ");
}
