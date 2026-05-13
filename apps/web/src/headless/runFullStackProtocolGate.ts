import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import {
  baselineDecisionPolicy,
  conservativeDecisionPolicy,
  createResourceFocusedDecisionPolicy,
  serializeHeadlessTraceEvent,
  type DecisionPolicy,
} from "./HeadlessGameClient";
import {
  evaluateProtocolBackendTimingGate,
  parseProtocolBackendTimingEvents,
  runFullStackProtocolGame,
  summarizeProtocolBackendTiming,
  summarizeProtocolThroughput,
  type FullStackProtocolRunResult,
  type ProtocolBackendTimingEvent,
  type ProtocolBackendTimingSummary,
  type FullStackProtocolProgressSnapshot,
  type ProtocolProfile,
  type ReconnectScenario,
} from "./fullStackProtocolHarness";
import { createHttpDecisionPolicy } from "./httpDecisionPolicy";
import {
  evaluateProtocolLatencyGate,
  type ProtocolLatencyGateSummary,
} from "./protocolLatencyGate";
import { protocolTraceEventsToReplayRows, serializeProtocolReplayRows } from "./protocolReplay";

type PolicyKind = "baseline" | "conservative" | "cash" | "shard" | "score" | "http";

type BackendTimingGateSummary = {
  ok: boolean;
  failures: string[];
  summary: ProtocolBackendTimingSummary;
  events: ProtocolBackendTimingEvent[];
  logPath?: string;
};

type CliOptions = {
  baseUrl?: string;
  profile?: ProtocolProfile;
  seed?: number;
  timeoutMs?: number;
  hardTimeoutMs?: number;
  continueWhileProgressing?: boolean;
  idleTimeoutMs?: number;
  out?: string;
  replayOut?: string;
  summaryOut?: string;
  progressIntervalMs?: number;
  cpuDiagnosticIdleMs?: number;
  cpuLowLoadPercent?: number;
  rawPromptFallbackDelayMs?: number | null;
  reconnectScenarios?: ReconnectScenario[];
  config?: Record<string, unknown>;
  policy?: PolicyKind;
  seatProfiles?: Record<number, PolicyKind>;
  policyHttpUrl?: string;
  policyHttpTimeoutMs?: number;
  backendLog?: string;
  backendLogOut?: string;
  requireBackendTiming?: boolean;
  maxBackendCommandMs?: number;
  maxBackendTransitionMs?: number;
  maxBackendRedisCommitCount?: number;
  maxBackendViewCommitCount?: number;
  maxProtocolCommandLatencyMs?: number;
  backendDockerComposeProject?: string;
  backendDockerComposeFile?: string;
  backendDockerComposeService?: string;
  quietProgress?: boolean;
};

const RECONNECT_SCENARIOS = new Set<ReconnectScenario>([
  "after_start",
  "after_first_commit",
  "after_first_prompt",
  "after_first_decision",
  "round_boundary",
  "turn_boundary",
]);

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const progressIntervalMs = Math.max(1_000, Math.floor(options.progressIntervalMs ?? 5_000));
  const policyMode = options.policy ?? "baseline";
  const policy = buildPolicy(options);
  const policiesByPlayerId = buildSeatPolicies(options);
  const startedAtMs = Date.now();
  let latestSnapshot: FullStackProtocolProgressSnapshot | null = null;
  let liveBackendTimingFailed = false;
  let liveProtocolLatencyFailed = false;
  let result: FullStackProtocolRunResult;
  try {
    result = await runFullStackProtocolGame({
      baseUrl: options.baseUrl,
      profile: options.profile,
      seed: options.seed,
      timeoutMs: options.timeoutMs,
      hardTimeoutMs: options.hardTimeoutMs,
      continueWhileProgressing: options.continueWhileProgressing,
      idleTimeoutMs: options.idleTimeoutMs,
      config: options.config,
      policy,
      policiesByPlayerId,
      reconnectScenarios: options.reconnectScenarios,
      rawPromptFallbackDelayMs: options.rawPromptFallbackDelayMs,
      progressIntervalMs,
      cpuDiagnosticIdleMs: options.cpuDiagnosticIdleMs,
      cpuLowLoadPercent: options.cpuLowLoadPercent,
      onProgress: async (snapshot) => {
        latestSnapshot = snapshot;
        await writeProgressArtifacts(snapshot, options);
        if (!options.quietProgress) {
          writeProgressLine(snapshot);
        }
        if (snapshot.reason !== "final" && !liveBackendTimingFailed) {
          const backendTiming = await loadBackendTimingSummary(snapshot.sessionId, options, {
            required: false,
            writeLog: false,
          });
          if (backendTiming && !backendTiming.ok) {
            liveBackendTimingFailed = true;
            throw new BackendTimingGateViolation(backendTiming);
          }
        }
        if (snapshot.reason !== "final" && options.maxProtocolCommandLatencyMs && !liveProtocolLatencyFailed) {
          const protocolLatency = evaluateProtocolLatencyGate({
            commands: snapshot.pace.slowestCommandLatencies,
            maxCommandLatencyMs: options.maxProtocolCommandLatencyMs,
          });
          if (!protocolLatency.ok) {
            liveProtocolLatencyFailed = true;
            throw new ProtocolLatencyGateViolation(protocolLatency);
          }
        }
      },
    });
  } catch (error) {
    if (error instanceof BackendTimingGateViolation) {
      const snapshot = latestSnapshot as FullStackProtocolProgressSnapshot | null;
      const backendTiming = snapshot?.sessionId
        ? await loadBackendTimingSummary(snapshot.sessionId, options, { required: false, writeLog: true })
        : null;
      await writeBackendTimingFailureSummary({
        options,
        policyMode,
        latestSnapshot: snapshot,
        backendTiming: backendTiming ?? error.backendTiming,
        durationMs: Date.now() - startedAtMs,
      });
      process.exitCode = 1;
      return;
    }
    if (error instanceof ProtocolLatencyGateViolation) {
      const snapshot = latestSnapshot as FullStackProtocolProgressSnapshot | null;
      const backendTiming = snapshot?.sessionId
        ? await loadBackendTimingSummary(snapshot.sessionId, options, { required: false, writeLog: true })
        : null;
      await writeProtocolLatencyFailureSummary({
        options,
        policyMode,
        latestSnapshot: snapshot,
        protocolLatency: error.protocolLatency,
        backendTiming,
        durationMs: Date.now() - startedAtMs,
      });
      process.exitCode = 1;
      return;
    }
    throw error;
  }

  if (options.out) {
    await writeTextFile(
      options.out,
      result.traces.map(serializeHeadlessTraceEvent).join("\n") + (result.traces.length > 0 ? "\n" : ""),
    );
  }
  if (options.replayOut) {
    const rows = protocolTraceEventsToReplayRows(result.traces, {
      seed: options.seed ?? null,
      policyMode,
      runtimeStatus: result.runtimeStatus,
    });
    await writeTextFile(options.replayOut, serializeProtocolReplayRows(rows) + (rows.length > 0 ? "\n" : ""));
  }

  const finalSnapshot = latestSnapshot as FullStackProtocolProgressSnapshot | null;
  const backendTiming = await loadBackendTimingSummary(result.sessionId, options, { writeLog: true });
  const protocolLatency = options.maxProtocolCommandLatencyMs
    ? evaluateProtocolLatencyGate({
        commands: finalSnapshot?.pace.slowestCommandLatencies ?? [],
        maxCommandLatencyMs: options.maxProtocolCommandLatencyMs,
      })
    : null;
  const failures = [...result.failures, ...(backendTiming?.failures ?? []), ...(protocolLatency?.failures ?? [])];
  const ok = result.ok && (backendTiming?.ok ?? true) && (protocolLatency?.ok ?? true);
  const throughput = summarizeProtocolThroughput({
    durationMs: result.durationMs,
    traces: result.traces,
    backendEvents: backendTiming?.events ?? [],
  });
  const summary = {
    ok,
    profile: result.profile,
    policy_mode: policyMode,
    seat_profiles: options.seatProfiles ?? {},
    session_id: result.sessionId,
    duration_ms: result.durationMs,
    timeout_ms: result.timeoutMs,
    hard_timeout_ms: result.hardTimeoutMs,
    continue_while_progressing: result.continueWhileProgressing,
    timed_out: result.timedOut,
    progress_timeout_exceeded: result.progressTimeoutExceeded,
    idle_timed_out: result.idleTimedOut,
    runtime_status: result.runtimeStatus,
    failures,
    backend_timing: backendTiming?.summary ?? null,
    backend_log: backendTiming?.logPath ?? null,
    protocol_latency: protocolLatency,
    throughput,
    clients: result.clientSummary,
    protocol_evidence: result.protocolEvidence,
    trace_count: result.traces.length,
  };
  const summaryText = `${JSON.stringify(summary, null, 2)}\n`;
  if (options.summaryOut) {
    await writeTextFile(options.summaryOut, summaryText);
  }
  process.stdout.write(summaryText);
  if (!ok) {
    process.exitCode = 1;
  }
}

class BackendTimingGateViolation extends Error {
  constructor(readonly backendTiming: BackendTimingGateSummary) {
    super(`backend_timing_gate_violation: ${backendTiming.failures.join("; ")}`);
  }
}

class ProtocolLatencyGateViolation extends Error {
  constructor(readonly protocolLatency: ProtocolLatencyGateSummary) {
    super(`protocol_latency_gate_violation: ${protocolLatency.failures.join("; ")}`);
  }
}

function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const next = args[index + 1];
    if (arg === "--base-url" && next) {
      options.baseUrl = next;
      index += 1;
    } else if (arg === "--profile" && next) {
      if (next !== "contract" && next !== "live") {
        throw new Error(`Unsupported profile: ${next}`);
      }
      options.profile = next;
      index += 1;
    } else if (arg === "--seed" && next) {
      options.seed = Number(next);
      index += 1;
    } else if (arg === "--timeout-ms" && next) {
      options.timeoutMs = Number(next);
      index += 1;
    } else if (arg === "--hard-timeout-ms" && next) {
      options.hardTimeoutMs = Number(next);
      index += 1;
    } else if (arg === "--continue-while-progressing") {
      options.continueWhileProgressing = true;
    } else if (arg === "--idle-timeout-ms" && next) {
      options.idleTimeoutMs = Number(next);
      index += 1;
    } else if (arg === "--out" && next) {
      options.out = next;
      index += 1;
    } else if (arg === "--replay-out" && next) {
      options.replayOut = next;
      index += 1;
    } else if (arg === "--summary-out" && next) {
      options.summaryOut = next;
      index += 1;
    } else if (arg === "--progress-interval-ms" && next) {
      options.progressIntervalMs = Number(next);
      index += 1;
    } else if (arg === "--cpu-diagnostic-idle-ms" && next) {
      options.cpuDiagnosticIdleMs = Number(next);
      index += 1;
    } else if (arg === "--cpu-low-load-percent" && next) {
      options.cpuLowLoadPercent = Number(next);
      index += 1;
    } else if (arg === "--raw-prompt-fallback-delay-ms" && next) {
      options.rawPromptFallbackDelayMs = next === "off" ? null : Number(next);
      index += 1;
    } else if (arg === "--reconnect" && next) {
      options.reconnectScenarios = next
        .split(",")
        .map((value) => value.trim())
        .filter((value): value is ReconnectScenario => RECONNECT_SCENARIOS.has(value as ReconnectScenario));
      index += 1;
    } else if (arg === "--config-json" && next) {
      options.config = parseJsonObject(next, "--config-json");
      index += 1;
    } else if (arg === "--policy" && next) {
      if (!isPolicyKind(next)) {
        throw new Error(`Unsupported policy: ${next}`);
      }
      options.policy = next;
      index += 1;
    } else if (arg === "--seat-profiles" && next) {
      options.seatProfiles = parseSeatProfiles(next);
      index += 1;
    } else if (arg === "--policy-http-url" && next) {
      options.policyHttpUrl = next;
      index += 1;
    } else if (arg === "--policy-http-timeout-ms" && next) {
      options.policyHttpTimeoutMs = Number(next);
      index += 1;
    } else if (arg === "--backend-log" && next) {
      options.backendLog = next;
      index += 1;
    } else if (arg === "--backend-log-out" && next) {
      options.backendLogOut = next;
      index += 1;
    } else if (arg === "--require-backend-timing") {
      options.requireBackendTiming = true;
    } else if (arg === "--max-backend-command-ms" && next) {
      options.maxBackendCommandMs = Number(next);
      index += 1;
    } else if (arg === "--max-backend-transition-ms" && next) {
      options.maxBackendTransitionMs = Number(next);
      index += 1;
    } else if (arg === "--max-backend-redis-commit-count" && next) {
      options.maxBackendRedisCommitCount = Number(next);
      index += 1;
    } else if (arg === "--max-backend-view-commit-count" && next) {
      options.maxBackendViewCommitCount = Number(next);
      index += 1;
    } else if (arg === "--max-protocol-command-latency-ms" && next) {
      options.maxProtocolCommandLatencyMs = Number(next);
      index += 1;
    } else if (arg === "--backend-docker-compose-project" && next) {
      options.backendDockerComposeProject = next;
      index += 1;
    } else if (arg === "--backend-docker-compose-file" && next) {
      options.backendDockerComposeFile = next;
      index += 1;
    } else if (arg === "--backend-docker-compose-service" && next) {
      options.backendDockerComposeService = next;
      index += 1;
    } else if (arg === "--quiet-progress") {
      options.quietProgress = true;
    } else if (arg === "--verbose-progress") {
      options.quietProgress = false;
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write(
        [
          "Usage: vite-node src/headless/runFullStackProtocolGate.ts [options]",
          "",
          "Options:",
          "  --base-url http://127.0.0.1:9091",
          "  --profile live|contract",
          "  --seed 20260508",
          "  --timeout-ms 120000",
          "  --hard-timeout-ms 240000",
          "  --continue-while-progressing",
          "  --idle-timeout-ms 60000",
          "  --out ./protocol_trace.jsonl",
          "  --replay-out ./rl_replay.jsonl",
          "  --summary-out ./summary.json",
          "  --progress-interval-ms 5000",
          "  --cpu-diagnostic-idle-ms 30000",
          "  --cpu-low-load-percent 10",
          "  --raw-prompt-fallback-delay-ms 25|off",
          "  --reconnect after_start,after_first_prompt,after_first_decision,round_boundary",
          "  --config-json '{\"rules\":{\"end\":{\"f_threshold\":4,\"monopolies_to_trigger_end\":1,\"tiles_to_trigger_end\":4,\"alive_players_at_most\":1}}}'",
          "  --policy baseline|conservative|cash|shard|score|http",
          "  --seat-profiles '1=baseline,2=cash,3=shard,4=score'",
          "  --policy-http-url http://127.0.0.1:7777/decide",
          "  --policy-http-timeout-ms 2000",
          "  --backend-log ./server.docker.log",
          "  --backend-log-out ./backend_server.log",
          "  --require-backend-timing",
          "  --max-backend-command-ms 5000",
          "  --max-backend-transition-ms 5000",
          "  --max-backend-redis-commit-count 1",
          "  --max-backend-view-commit-count 1",
          "  --max-protocol-command-latency-ms 5000",
          "  --backend-docker-compose-project project-mrn-protocol",
          "  --backend-docker-compose-file ../../docker-compose.protocol.yml",
          "  --backend-docker-compose-service server",
          "  --quiet-progress",
          "  --verbose-progress",
          "",
          "Progress JSON is quiet by default for direct single-game runs. Pass --verbose-progress for live investigation.",
        ].join("\n") + "\n",
      );
      process.exit(0);
    }
  }
  return {
    ...options,
    quietProgress: options.quietProgress ?? true,
  };
}

async function loadBackendTimingSummary(
  sessionId: string,
  options: CliOptions,
  gateOptions?: { required?: boolean; writeLog?: boolean },
): Promise<BackendTimingGateSummary | null> {
  const hasBackendLogSource = Boolean(
    options.backendLog ||
      options.backendDockerComposeProject ||
      options.backendDockerComposeFile ||
      options.backendDockerComposeService,
  );
  if (!hasBackendLogSource && !options.requireBackendTiming) {
    return null;
  }
  const logText = await loadBackendLogText(options);
  let logPath: string | undefined;
  if (gateOptions?.writeLog && options.backendLogOut) {
    await writeTextFile(options.backendLogOut, logText);
    logPath = options.backendLogOut;
  }
  const events = parseProtocolBackendTimingEvents(logText, { sessionId });
  const gate = evaluateProtocolBackendTimingGate({
    events,
    required: gateOptions?.required ?? options.requireBackendTiming,
    maxCommandMs: options.maxBackendCommandMs,
    maxTransitionMs: options.maxBackendTransitionMs,
    maxRedisCommitCount: options.maxBackendRedisCommitCount,
    maxViewCommitCount: options.maxBackendViewCommitCount,
  });
  return {
    ok: gate.ok,
    failures: gate.failures,
    events,
    logPath,
    summary: summarizeProtocolBackendTiming(events, {
      maxCommandMs: options.maxBackendCommandMs,
      maxTransitionMs: options.maxBackendTransitionMs,
    }),
  };
}

async function writeBackendTimingFailureSummary(args: {
  options: CliOptions;
  policyMode: PolicyKind;
  latestSnapshot: FullStackProtocolProgressSnapshot | null;
  backendTiming: BackendTimingGateSummary;
  durationMs: number;
}): Promise<void> {
  const summary = {
    ok: false,
    profile: args.latestSnapshot?.profile ?? args.options.profile ?? null,
    policy_mode: args.policyMode,
    seat_profiles: args.options.seatProfiles ?? {},
    session_id: args.latestSnapshot?.sessionId ?? "",
    duration_ms: args.durationMs,
    timeout_ms: args.options.timeoutMs ?? null,
    hard_timeout_ms: args.options.hardTimeoutMs ?? null,
    continue_while_progressing: args.options.continueWhileProgressing ?? false,
    timed_out: false,
    progress_timeout_exceeded: false,
    idle_timed_out: false,
    runtime_status: args.latestSnapshot?.runtimeStatus ?? null,
    aborted: true,
    abort_reason: "backend_timing_gate",
    failures: args.backendTiming.failures,
    backend_timing: args.backendTiming.summary,
    backend_log: args.backendTiming.logPath ?? null,
    throughput: summarizeProtocolThroughput({
      durationMs: args.durationMs,
      traces: args.latestSnapshot?.traces ?? [],
      backendEvents: args.backendTiming.events,
    }),
    clients: args.latestSnapshot?.clientSummary ?? [],
    trace_count: args.latestSnapshot?.traceCount ?? 0,
  };
  const summaryText = `${JSON.stringify(summary, null, 2)}\n`;
  if (args.options.summaryOut) {
    await writeTextFile(args.options.summaryOut, summaryText);
  }
  process.stdout.write(summaryText);
}

async function writeProtocolLatencyFailureSummary(args: {
  options: CliOptions;
  policyMode: PolicyKind;
  latestSnapshot: FullStackProtocolProgressSnapshot | null;
  protocolLatency: ProtocolLatencyGateSummary;
  backendTiming: BackendTimingGateSummary | null;
  durationMs: number;
}): Promise<void> {
  const summary = {
    ok: false,
    profile: args.latestSnapshot?.profile ?? args.options.profile ?? null,
    policy_mode: args.policyMode,
    seat_profiles: args.options.seatProfiles ?? {},
    session_id: args.latestSnapshot?.sessionId ?? "",
    duration_ms: args.durationMs,
    timeout_ms: args.options.timeoutMs ?? null,
    hard_timeout_ms: args.options.hardTimeoutMs ?? null,
    continue_while_progressing: args.options.continueWhileProgressing ?? false,
    timed_out: false,
    progress_timeout_exceeded: false,
    idle_timed_out: false,
    runtime_status: args.latestSnapshot?.runtimeStatus ?? null,
    aborted: true,
    abort_reason: "protocol_latency_gate",
    failures: args.protocolLatency.failures,
    backend_timing: args.backendTiming?.summary ?? null,
    backend_log: args.backendTiming?.logPath ?? null,
    protocol_latency: args.protocolLatency,
    throughput: summarizeProtocolThroughput({
      durationMs: args.durationMs,
      traces: args.latestSnapshot?.traces ?? [],
      backendEvents: args.backendTiming?.events ?? [],
    }),
    clients: args.latestSnapshot?.clientSummary ?? [],
    trace_count: args.latestSnapshot?.traceCount ?? 0,
  };
  const summaryText = `${JSON.stringify(summary, null, 2)}\n`;
  if (args.options.summaryOut) {
    await writeTextFile(args.options.summaryOut, summaryText);
  }
  process.stdout.write(summaryText);
}

async function loadBackendLogText(options: CliOptions): Promise<string> {
  const chunks: string[] = [];
  if (options.backendLog) {
    chunks.push(await readFile(options.backendLog, "utf8"));
  }
  if (options.backendDockerComposeProject || options.backendDockerComposeFile || options.backendDockerComposeService) {
    const args = ["compose"];
    if (options.backendDockerComposeProject) {
      args.push("-p", options.backendDockerComposeProject);
    }
    if (options.backendDockerComposeFile) {
      args.push("-f", options.backendDockerComposeFile);
    }
    args.push("logs", "--no-color", options.backendDockerComposeService ?? "server");
    chunks.push(execFileSync("docker", args, { encoding: "utf8", maxBuffer: 128 * 1024 * 1024 }));
  }
  return chunks.join("\n");
}

async function writeProgressArtifacts(
  snapshot: FullStackProtocolProgressSnapshot,
  options: CliOptions,
): Promise<void> {
  if (options.out) {
    await writeTextFile(
      options.out,
      snapshot.traces.map(serializeHeadlessTraceEvent).join("\n") + (snapshot.traces.length > 0 ? "\n" : ""),
    );
  }
  if (options.replayOut) {
    const rows = protocolTraceEventsToReplayRows(snapshot.traces, {
      seed: options.seed ?? null,
      policyMode: options.policy ?? "baseline",
      runtimeStatus: snapshot.runtimeStatus,
    });
    await writeTextFile(options.replayOut, serializeProtocolReplayRows(rows) + (rows.length > 0 ? "\n" : ""));
  }
}

function writeProgressLine(snapshot: FullStackProtocolProgressSnapshot): void {
  const seatMetrics = snapshot.clients
    .filter((client) => client.role === "seat")
    .map((client) => ({
      player_id: client.playerId,
      commit_seq: client.lastCommitSeq,
      accepted: client.metrics.acceptedAckCount,
      rejected: client.metrics.rejectedAckCount,
      stale: client.metrics.staleAckCount,
      prompts: client.metrics.promptMessageCount,
      reconnects: client.metrics.reconnectCount,
      forced_reconnects: client.metrics.forcedReconnectCount,
      reconnect_recovered: client.metrics.reconnectRecoveryCount,
      reconnect_pending: client.metrics.reconnectRecoveryPendingCount,
      errors: client.metrics.errorMessageCount,
      fallbacks: client.metrics.decisionTimeoutFallbackCount,
      semantic_regressions: client.metrics.semanticCommitRegressionCount,
    }));
  process.stderr.write(
    `${JSON.stringify({
      event: "protocol_gate_progress",
      reason: snapshot.reason,
      session_id: snapshot.sessionId,
      elapsed_ms: snapshot.elapsedMs,
      idle_ms: snapshot.idleMs,
      runtime_status: snapshot.runtimeStatus,
      pace: snapshot.pace,
      completed: snapshot.completed,
      timed_out: snapshot.timedOut,
      progress_timeout_exceeded: snapshot.progressTimeoutExceeded,
      idle_timed_out: snapshot.idleTimedOut,
      trace_count: snapshot.traceCount,
      cpu: snapshot.cpu,
      seats: seatMetrics,
    })}\n`,
  );
}

function buildPolicy(options: CliOptions): DecisionPolicy {
  return buildPolicyKind(options.policy ?? "baseline", options);
}

function buildSeatPolicies(options: CliOptions): Record<number, DecisionPolicy> | undefined {
  const entries = Object.entries(options.seatProfiles ?? {});
  if (entries.length === 0) {
    return undefined;
  }
  return Object.fromEntries(entries.map(([playerId, kind]) => [Number(playerId), buildPolicyKind(kind, options)]));
}

function buildPolicyKind(kind: PolicyKind, options: Pick<CliOptions, "policyHttpUrl" | "policyHttpTimeoutMs">): DecisionPolicy {
  if (kind === "baseline") {
    return baselineDecisionPolicy;
  }
  if (kind === "conservative") {
    return conservativeDecisionPolicy;
  }
  if (kind === "cash" || kind === "shard" || kind === "score") {
    return createResourceFocusedDecisionPolicy(kind);
  }
  if (!options.policyHttpUrl) {
    throw new Error("--policy http requires --policy-http-url.");
  }
  return createHttpDecisionPolicy({
    endpoint: options.policyHttpUrl,
    timeoutMs: options.policyHttpTimeoutMs,
  });
}

function parseSeatProfiles(raw: string): Record<number, PolicyKind> {
  const profiles: Record<number, PolicyKind> = {};
  for (const pair of raw.split(",")) {
    const trimmed = pair.trim();
    if (!trimmed) {
      continue;
    }
    const [seatRaw, kindRaw] = trimmed.split("=").map((value) => value.trim());
    const seat = Number(seatRaw);
    if (!Number.isInteger(seat) || seat <= 0) {
      throw new Error(`Invalid seat profile seat: ${seatRaw}`);
    }
    if (!isPolicyKind(kindRaw)) {
      throw new Error(`Unsupported seat profile policy: ${kindRaw}`);
    }
    profiles[seat] = kindRaw;
  }
  return profiles;
}

function isPolicyKind(value: string): value is PolicyKind {
  return value === "baseline" ||
    value === "conservative" ||
    value === "cash" ||
    value === "shard" ||
    value === "score" ||
    value === "http";
}

function parseJsonObject(raw: string, flag: string): Record<string, unknown> {
  const parsed = JSON.parse(raw) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${flag} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

async function writeTextFile(path: string, content: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content, "utf8");
}

void main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exitCode = 1;
});
