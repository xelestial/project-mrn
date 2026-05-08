import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import {
  baselineDecisionPolicy,
  conservativeDecisionPolicy,
  createResourceFocusedDecisionPolicy,
  serializeHeadlessTraceEvent,
  type DecisionPolicy,
} from "./HeadlessGameClient";
import {
  runFullStackProtocolGame,
  type FullStackProtocolProgressSnapshot,
  type ProtocolProfile,
  type ReconnectScenario,
} from "./fullStackProtocolHarness";
import { createHttpDecisionPolicy } from "./httpDecisionPolicy";
import { protocolTraceEventsToReplayRows, serializeProtocolReplayRows } from "./protocolReplay";

type PolicyKind = "baseline" | "conservative" | "cash" | "shard" | "score" | "http";

type CliOptions = {
  baseUrl?: string;
  profile?: ProtocolProfile;
  seed?: number;
  timeoutMs?: number;
  idleTimeoutMs?: number;
  out?: string;
  replayOut?: string;
  progressIntervalMs?: number;
  rawPromptFallbackDelayMs?: number | null;
  reconnectScenarios?: ReconnectScenario[];
  config?: Record<string, unknown>;
  policy?: PolicyKind;
  seatProfiles?: Record<number, PolicyKind>;
  policyHttpUrl?: string;
  policyHttpTimeoutMs?: number;
};

const RECONNECT_SCENARIOS = new Set<ReconnectScenario>([
  "after_start",
  "after_first_commit",
  "after_first_decision",
  "round_boundary",
  "turn_boundary",
]);

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const progressIntervalMs = Math.max(1_000, Math.floor(options.progressIntervalMs ?? 30_000));
  const policyMode = options.policy ?? "baseline";
  const policy = buildPolicy(options);
  const policiesByPlayerId = buildSeatPolicies(options);
  const result = await runFullStackProtocolGame({
    baseUrl: options.baseUrl,
    profile: options.profile,
    seed: options.seed,
    timeoutMs: options.timeoutMs,
    idleTimeoutMs: options.idleTimeoutMs,
    config: options.config,
    policy,
    policiesByPlayerId,
    reconnectScenarios: options.reconnectScenarios,
    rawPromptFallbackDelayMs: options.rawPromptFallbackDelayMs,
    progressIntervalMs,
    onProgress: async (snapshot) => {
      await writeProgressArtifacts(snapshot, options);
      writeProgressLine(snapshot);
    },
  });

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

  const summary = {
    ok: result.ok,
    profile: result.profile,
    policy_mode: policyMode,
    seat_profiles: options.seatProfiles ?? {},
    session_id: result.sessionId,
    duration_ms: result.durationMs,
    timed_out: result.timedOut,
    idle_timed_out: result.idleTimedOut,
    runtime_status: result.runtimeStatus,
    failures: result.failures,
    clients: result.clientSummary,
    trace_count: result.traces.length,
  };
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  if (!result.ok) {
    process.exitCode = 1;
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
    } else if (arg === "--idle-timeout-ms" && next) {
      options.idleTimeoutMs = Number(next);
      index += 1;
    } else if (arg === "--out" && next) {
      options.out = next;
      index += 1;
    } else if (arg === "--replay-out" && next) {
      options.replayOut = next;
      index += 1;
    } else if (arg === "--progress-interval-ms" && next) {
      options.progressIntervalMs = Number(next);
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
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write(
        [
          "Usage: vite-node src/headless/runFullStackProtocolGate.ts [options]",
          "",
          "Options:",
          "  --base-url http://127.0.0.1:9090",
          "  --profile live|contract",
          "  --seed 20260508",
          "  --timeout-ms 120000",
          "  --idle-timeout-ms 60000",
          "  --out ./protocol_trace.jsonl",
          "  --replay-out ./rl_replay.jsonl",
          "  --progress-interval-ms 30000",
          "  --raw-prompt-fallback-delay-ms 25|off",
          "  --reconnect after_start,after_first_decision,round_boundary",
          "  --config-json '{\"runtime\":{\"max_turns\":4}}'",
          "  --policy baseline|conservative|cash|shard|score|http",
          "  --seat-profiles '1=baseline,2=cash,3=shard,4=score'",
          "  --policy-http-url http://127.0.0.1:7777/decide",
          "  --policy-http-timeout-ms 2000",
        ].join("\n") + "\n",
      );
      process.exit(0);
    }
  }
  return options;
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
      reconnects: client.metrics.reconnectCount,
      errors: client.metrics.errorMessageCount,
      fallbacks: client.metrics.decisionTimeoutFallbackCount,
      semantic_regressions: client.metrics.semanticCommitRegressionCount,
    }));
  process.stderr.write(
    `${JSON.stringify({
      event: "protocol_gate_progress",
      session_id: snapshot.sessionId,
      elapsed_ms: snapshot.elapsedMs,
      runtime_status: snapshot.runtimeStatus,
      trace_count: snapshot.traceCount,
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
