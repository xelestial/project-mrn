import { isAbsolute, resolve } from "node:path";

export type ProtocolGateRunLayoutOptions = {
  repoRoot: string;
  runRoot?: string;
  label?: string;
  gameIndex: number;
};

export type ProtocolGateRunArtifacts = {
  runRoot: string;
  gameDir: string;
  rawDir: string;
  summaryDir: string;
  pointersDir: string;
  traceOut: string;
  replayOut: string;
  summaryOut: string;
  backendLogOut: string;
  protocolLogOut: string;
  progressOut: string;
  runStatusOut: string;
  progressSummaryOut: string;
  slowestCommandOut: string;
  slowestTransitionOut: string;
  gateResultOut: string;
  failureReasonOut: string;
  failurePointerOut: string;
  suspectEventsOut: string;
  logOffsetsOut: string;
};

function defaultRunRoot(repoRoot: string, label?: string): string {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "");
  const suffix = label?.trim() || `protocol-gate-${stamp}`;
  return resolve(repoRoot, "tmp", "rl", "full-stack-protocol", suffix);
}

export function resolveProtocolGateRunRoot(repoRoot: string, runRoot?: string, label?: string): string {
  if (!runRoot) {
    return defaultRunRoot(repoRoot, label);
  }
  return isAbsolute(runRoot) ? runRoot : resolve(repoRoot, runRoot);
}

export function buildProtocolGateRunArtifacts(options: ProtocolGateRunLayoutOptions): ProtocolGateRunArtifacts {
  if (!Number.isInteger(options.gameIndex) || options.gameIndex <= 0) {
    throw new Error(`gameIndex must be a positive integer: ${options.gameIndex}`);
  }
  const runRoot = resolveProtocolGateRunRoot(options.repoRoot, options.runRoot, options.label);
  const gameDir = resolve(runRoot, `game-${options.gameIndex}`);
  const rawDir = resolve(gameDir, "raw");
  const summaryDir = resolve(gameDir, "summary");
  const pointersDir = resolve(gameDir, "pointers");
  return {
    runRoot,
    gameDir,
    rawDir,
    summaryDir,
    pointersDir,
    traceOut: resolve(rawDir, "protocol_trace.jsonl"),
    replayOut: resolve(rawDir, "protocol_replay.jsonl"),
    summaryOut: resolve(summaryDir, "summary.json"),
    backendLogOut: resolve(rawDir, "backend_server.log"),
    protocolLogOut: resolve(rawDir, "protocol_gate.log"),
    progressOut: resolve(rawDir, "progress.ndjson"),
    runStatusOut: resolve(summaryDir, "run_status.json"),
    progressSummaryOut: resolve(summaryDir, "progress.json"),
    slowestCommandOut: resolve(summaryDir, "slowest_command.json"),
    slowestTransitionOut: resolve(summaryDir, "slowest_transition.json"),
    gateResultOut: resolve(summaryDir, "gate_result.json"),
    failureReasonOut: resolve(summaryDir, "failure_reason.json"),
    failurePointerOut: resolve(pointersDir, "failure_pointer.json"),
    suspectEventsOut: resolve(pointersDir, "suspect_events.json"),
    logOffsetsOut: resolve(pointersDir, "log_offsets.json"),
  };
}
