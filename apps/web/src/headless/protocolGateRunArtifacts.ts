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
  traceOut: string;
  replayOut: string;
  summaryOut: string;
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
  return {
    runRoot,
    gameDir,
    traceOut: resolve(gameDir, "protocol_trace.jsonl"),
    replayOut: resolve(gameDir, "protocol_replay.jsonl"),
    summaryOut: resolve(gameDir, "summary.json"),
  };
}
