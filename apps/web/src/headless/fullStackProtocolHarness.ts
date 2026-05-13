import { execFileSync } from "node:child_process";
import { cpus } from "node:os";
import type { ConnectionStatus } from "../core/contracts/stream";
import {
  baselineDecisionPolicy,
  HeadlessGameClient,
  type DecisionPolicy,
  type HeadlessMetrics,
  type HeadlessTraceEvent,
} from "./HeadlessGameClient";
import {
  FrontendTransportAdapter,
  FrontendTransportApiError,
  normalizeFrontendHttpBaseUrl,
} from "./frontendTransportAdapter";

export type ProtocolProfile = "contract" | "live";

export type ProtocolClientRole = "seat" | "spectator";

export type ProtocolClientRuntime = {
  label: string;
  role: ProtocolClientRole;
  playerId: number;
  status: ConnectionStatus;
  lastCommitSeq: number;
  metrics: HeadlessMetrics;
  traceCount: number;
};

export type ProtocolClientSummary = Record<
  string,
  {
    role: ProtocolClientRole;
    playerId: number;
    status: ConnectionStatus;
    lastCommitSeq: number;
    metrics: HeadlessMetrics;
    traceCount: number;
  }
>;

export type FullStackProtocolProgressSnapshot = {
  sessionId: string;
  profile: ProtocolProfile;
  elapsedMs: number;
  idleMs: number;
  reason: ProtocolProgressReason;
  runtimeStatus: string | null;
  pace: ProtocolPaceDiagnostic;
  clients: ProtocolClientRuntime[];
  clientSummary: ProtocolClientSummary;
  traceCount: number;
  completed: boolean;
  timedOut: boolean;
  progressTimeoutExceeded: boolean;
  idleTimedOut: boolean;
  cpu: ProtocolCpuDiagnostic;
  traces: HeadlessTraceEvent[];
};

export type ProtocolProgressReason = "progress" | "interval" | "final";

export type ProtocolPaceDiagnostic = {
  maxCommitSeq: number;
  latestRoundIndex: number | null;
  latestTurnIndex: number | null;
  latestRuntimeStatus: string | null;
  activePromptRequestId: string | null;
  activePromptPlayerId: number | null;
  activePromptRequestType: string | null;
  waitingOnActivePrompt: boolean;
  latestTraceEvent: string | null;
  latestDecisionRequestId: string | null;
  latestAckRequestId: string | null;
  latestAckStatus: string | null;
  commitSeqPerMinute: number;
  decisionsPerMinute: number;
  acceptedAcksPerMinute: number;
  slowestCommandLatencies: ProtocolCommandLatencyDiagnostic[];
  pendingDecisionAges: ProtocolPendingDecisionDiagnostic[];
};

export type ProtocolCommandLatencyDiagnostic = {
  requestId: string;
  playerId: number;
  requestType: string | null;
  promptToDecisionMs: number | null;
  decisionToAckMs: number | null;
  totalMs: number | null;
  status: string | null;
};

export type ProtocolPendingDecisionDiagnostic = {
  requestId: string;
  playerId: number;
  requestType: string | null;
  ageMs: number;
};

export type ProtocolCpuDiagnostic = {
  sampled: boolean;
  idleMs: number;
  processCpuPercent: number | null;
  hostCpuRawPercent: number | null;
  hostLogicalCpuCount: number | null;
  hostCpuPercent: number | null;
  suspiciousIdle: boolean;
  error?: string;
};

export type HeadlessHumanSessionPayload = {
  seats: Array<{ seat: number; seat_type: "human" }>;
  config: Record<string, unknown> & {
    seed: number;
    visibility: "public";
    runtime: Record<string, unknown> & { seed: number };
  };
};

export type BuildHeadlessHumanSessionPayloadArgs = {
  seed: number;
  seatCount?: number;
  config?: Record<string, unknown>;
};

export type ProtocolGateInput = {
  timedOut: boolean;
  idleTimedOut?: boolean;
  completed: boolean;
  clients: ProtocolClientRuntime[];
  runtimeStatus?: string | null;
  backendTiming?: ProtocolBackendTimingGateInput;
  traces?: HeadlessTraceEvent[];
  maxRepeatedPromptSignatureCount?: number;
  expectedSeatCount?: number;
  requireSpectator?: boolean;
  requireProtocolEvidence?: boolean;
};

export type ProtocolGateResult = {
  ok: boolean;
  failures: string[];
};

export type ProtocolGateEvidence = {
  expectedSeatCount: number | null;
  spectatorRequired: boolean;
  seatClientCount: number;
  spectatorClientCount: number;
  completedViewCommitClientCount: number;
  viewCommitCount: number;
  maxCommitSeq: number;
  promptMessageCount: number;
  activePromptViewCommitTraceCount: number;
  outboundDecisionCount: number;
  decisionSentTraceCount: number;
  acceptedAckCount: number;
  decisionAckTraceCount: number;
  acceptedDecisionAckTraceCount: number;
  staleAckCount: number;
  staleRecoveryCount: number;
  unrecoveredStaleAckCount: number;
  forcedReconnectCount: number;
  reconnectRecoveryCount: number;
  reconnectRecoveryPendingCount: number;
  rawPromptFallbackWithoutActiveCommitCount: number;
  spectatorPromptLeakCount: number;
  spectatorDecisionAckLeakCount: number;
  identityViolationCount: number;
  nonMonotonicCommitCount: number;
  semanticCommitRegressionCount: number;
  runtimeRecoveryRequiredCount: number;
  errorMessageCount: number;
  traceCount: number;
};

export type ProtocolBackendTimingEvent = {
  event: string;
  session_id?: string;
  total_ms?: number;
  command_seq?: number;
  processed_command_seq?: number;
  request_id?: string;
  request_type?: string;
  module_type?: string;
  result_status?: string;
  reason?: string;
  redis_commit_count?: number;
  view_commit_count?: number;
  internal_redis_commit_attempt_count?: number;
  internal_view_commit_attempt_count?: number;
  [key: string]: unknown;
};

export type ProtocolBackendTimingGateInput = {
  events: ProtocolBackendTimingEvent[];
  required?: boolean;
  maxCommandMs?: number;
  maxTransitionMs?: number;
  maxRedisCommitCount?: number;
  maxViewCommitCount?: number;
};

export type ProtocolBackendTimingSummary = {
  eventCount: number;
  commandTimingCount: number;
  transitionTimingCount: number;
  decisionRouteTimingCount: number;
  promptTimingCount: number;
  maxCommandMs: number;
  maxTransitionMs: number;
  maxDecisionRouteMs: number;
  maxPromptMs: number;
  maxRedisCommitCount: number;
  maxViewCommitCount: number;
  slowCommandCount: number;
  slowTransitionCount: number;
};

export type ProtocolPercentileSummary = {
  count: number;
  p50: number | null;
  p95: number | null;
  max: number | null;
};

export type ProtocolBackendPhaseSummary = {
  count: number;
  totalMs: ProtocolPercentileSummary;
  phases: Record<string, ProtocolPercentileSummary>;
};

export type ProtocolThroughputSummary = {
  decisionCount: number;
  acceptedAckCount: number;
  missingAckCount: number;
  uniqueViewCommitCount: number;
  durationMs: number;
  decisionsPerMinute: number | null;
  ackLatencyMs: ProtocolPercentileSummary;
  commitGapMs: ProtocolPercentileSummary;
  backend: {
    command: ProtocolBackendPhaseSummary;
    transition: ProtocolBackendPhaseSummary;
    decisionRoute: ProtocolBackendPhaseSummary;
    prompt: ProtocolBackendPhaseSummary;
  };
};

export type ProtocolPromptRepetitionDiagnostic = {
  signature: string;
  count: number;
  playerId: number;
  requestType: string;
  activeModuleId: string;
  activeModuleType: string | null;
  roundIndex: number | null;
  turnIndex: number | null;
  firstCommitSeq: number | null;
  lastCommitSeq: number | null;
  requestIds: string[];
};

export type ProtocolSeatJoin = {
  seat: number;
  playerId: number;
  token: string;
};

export type ProtocolSessionInfo = {
  sessionId: string;
  hostToken: string;
  joinTokens: Record<number, string>;
  seats: ProtocolSeatJoin[];
};

export type ReconnectScenario =
  | "after_start"
  | "after_first_commit"
  | "after_first_prompt"
  | "after_first_decision"
  | "round_boundary"
  | "turn_boundary";

export type RunFullStackProtocolGameOptions = {
  profile?: ProtocolProfile;
  baseUrl?: string;
  seed?: number;
  seatCount?: number;
  timeoutMs?: number;
  hardTimeoutMs?: number;
  continueWhileProgressing?: boolean;
  idleTimeoutMs?: number;
  pollIntervalMs?: number;
  config?: Record<string, unknown>;
  policy?: DecisionPolicy;
  policiesByPlayerId?: Record<number, DecisionPolicy>;
  spectator?: boolean;
  rawPromptFallbackDelayMs?: number | null;
  reconnectScenarios?: ReconnectScenario[];
  progressIntervalMs?: number;
  cpuDiagnosticIdleMs?: number;
  cpuLowLoadPercent?: number;
  onProgress?: (snapshot: FullStackProtocolProgressSnapshot) => void | Promise<void>;
};

export type FullStackProtocolRunResult = {
  ok: boolean;
  profile: ProtocolProfile;
  sessionId: string;
  durationMs: number;
  timedOut: boolean;
  progressTimeoutExceeded: boolean;
  timeoutMs: number;
  hardTimeoutMs: number;
  continueWhileProgressing: boolean;
  idleTimedOut: boolean;
  completed: boolean;
  runtimeStatus: string | null;
  failures: string[];
  clients: ProtocolClientRuntime[];
  clientSummary: ProtocolClientSummary;
  protocolEvidence: ProtocolGateEvidence;
  traces: HeadlessTraceEvent[];
};

type CreateSessionResult = {
  session_id?: string;
  host_token?: string;
  join_tokens?: Record<string, string>;
};

type JoinSessionResult = {
  seat?: number;
  player_id?: number;
  session_token?: string;
};

type RuntimeStatusResult = {
  runtime?: {
    status?: string;
  };
};

const DEFAULT_BASE_URL = "http://127.0.0.1:9091";
const COMPLETED_COMMIT_GRACE_POLLS = 20;
const DEFAULT_MAX_BACKEND_COMMAND_MS = 5_000;
const DEFAULT_MAX_BACKEND_TRANSITION_MS = 5_000;
const DEFAULT_PROTOCOL_RAW_PROMPT_FALLBACK_DELAY_MS: number | null = null;
const DEFAULT_FETCH_RETRY_COUNT = 5;
const DEFAULT_FETCH_RETRY_DELAY_MS = 150;
const DEFAULT_CPU_DIAGNOSTIC_IDLE_MS = 30_000;
const DEFAULT_CPU_LOW_LOAD_PERCENT = 10;
const DEFAULT_PROGRESS_INTERVAL_MS = 5_000;
const PROGRESS_CHANGE_MIN_INTERVAL_MS = 1_000;

export type ProtocolTimeoutPolicy = {
  timeoutMs: number;
  hardTimeoutMs: number;
  continueWhileProgressing: boolean;
};

export function resolveProtocolTimeoutPolicy(args: {
  profile: ProtocolProfile;
  timeoutMs?: number;
  hardTimeoutMs?: number;
  continueWhileProgressing?: boolean;
}): ProtocolTimeoutPolicy {
  const timeoutMs = Math.max(1_000, args.timeoutMs ?? (args.profile === "live" ? 900_000 : 120_000));
  const continueWhileProgressing = args.continueWhileProgressing ?? false;
  const hardTimeoutMs = continueWhileProgressing
    ? Math.max(timeoutMs, Math.floor(args.hardTimeoutMs ?? timeoutMs * 2))
    : timeoutMs;
  return {
    timeoutMs,
    hardTimeoutMs,
    continueWhileProgressing,
  };
}

export function buildHeadlessHumanSessionPayload({
  seed,
  seatCount = 4,
  config = {},
}: BuildHeadlessHumanSessionPayloadArgs): HeadlessHumanSessionPayload {
  const runtimeConfig = isRecord(config.runtime) ? config.runtime : {};
  return {
    seats: Array.from({ length: Math.max(1, Math.floor(seatCount)) }, (_, index) => ({
      seat: index + 1,
      seat_type: "human",
    })),
    config: {
      ...config,
      seed,
      visibility: "public",
      runtime: {
        ai_decision_delay_ms: 0,
        ...runtimeConfig,
        seed,
      },
    },
  };
}

export function summarizeProtocolClients(clients: ProtocolClientRuntime[]): ProtocolClientSummary {
  return Object.fromEntries(
    clients.map((client) => [
      client.label,
      {
        role: client.role,
        playerId: client.playerId,
        status: client.status,
        lastCommitSeq: client.lastCommitSeq,
        metrics: { ...client.metrics },
        traceCount: client.traceCount,
      },
    ]),
  );
}

export function summarizeProtocolGateEvidence(input: ProtocolGateInput): ProtocolGateEvidence {
  const traces = input.traces ?? [];
  const seatClients = input.clients.filter((client) => client.role === "seat");
  const spectatorClients = input.clients.filter((client) => client.role === "spectator");
  const metrics = input.clients.map((client) => client.metrics);
  const metricSum = (selector: (metrics: HeadlessMetrics) => number): number =>
    metrics.reduce((sum, item) => sum + selector(item), 0);
  const staleAckCount = metricSum((item) => item.staleAckCount);
  const staleRecoveryCount = metricSum((item) => item.staleDecisionRetryCount + item.unackedDecisionRetryCount);
  return {
    expectedSeatCount: input.expectedSeatCount ?? null,
    spectatorRequired: input.requireSpectator ?? false,
    seatClientCount: seatClients.length,
    spectatorClientCount: spectatorClients.length,
    completedViewCommitClientCount: input.clients.filter((client) => client.metrics.runtimeCompletedCount > 0).length,
    viewCommitCount: metricSum((item) => item.viewCommitCount),
    maxCommitSeq: Math.max(0, ...input.clients.map((client) => client.lastCommitSeq)),
    promptMessageCount: metricSum((item) => item.promptMessageCount),
    activePromptViewCommitTraceCount: traces.filter(
      (trace) =>
        trace.event === "view_commit_seen" &&
        isRecord(trace.payload) &&
        typeof trace.payload["active_prompt_request_id"] === "string",
    ).length,
    outboundDecisionCount: metricSum((item) => item.outboundDecisionCount),
    decisionSentTraceCount: traces.filter(
      (trace) =>
        trace.event === "decision_sent" ||
        trace.event === "decision_retry_sent" ||
        trace.event === "decision_unacked_retry_sent",
    ).length,
    acceptedAckCount: metricSum((item) => item.acceptedAckCount),
    decisionAckTraceCount: traces.filter((trace) => trace.event === "decision_ack").length,
    acceptedDecisionAckTraceCount: traces.filter(
      (trace) => trace.event === "decision_ack" && trace.status === "accepted",
    ).length,
    staleAckCount,
    staleRecoveryCount,
    unrecoveredStaleAckCount: Math.max(0, staleAckCount - staleRecoveryCount),
    forcedReconnectCount: metricSum((item) => item.forcedReconnectCount),
    reconnectRecoveryCount: metricSum((item) => item.reconnectRecoveryCount),
    reconnectRecoveryPendingCount: metricSum((item) => item.reconnectRecoveryPendingCount),
    rawPromptFallbackWithoutActiveCommitCount: metricSum((item) => item.rawPromptFallbackWithoutActiveCommitCount),
    spectatorPromptLeakCount: metricSum((item) => item.spectatorPromptLeakCount),
    spectatorDecisionAckLeakCount: metricSum((item) => item.spectatorDecisionAckLeakCount),
    identityViolationCount: metricSum((item) => item.identityViolationCount),
    nonMonotonicCommitCount: metricSum((item) => item.nonMonotonicCommitCount),
    semanticCommitRegressionCount: metricSum((item) => item.semanticCommitRegressionCount),
    runtimeRecoveryRequiredCount: metricSum((item) => item.runtimeRecoveryRequiredCount),
    errorMessageCount: metricSum((item) => item.errorMessageCount),
    traceCount: traces.length,
  };
}

export function evaluateProtocolGate(input: ProtocolGateInput): ProtocolGateResult {
  const failures: string[] = [];
  const evidence = summarizeProtocolGateEvidence(input);
  const runtimeCompleted = input.runtimeStatus === "completed" || input.completed;
  if (input.expectedSeatCount !== undefined && evidence.seatClientCount !== input.expectedSeatCount) {
    failures.push(`protocol gate expected ${input.expectedSeatCount} seat client(s), saw ${evidence.seatClientCount}`);
  }
  if (input.requireSpectator && evidence.spectatorClientCount === 0) {
    failures.push("protocol gate expected a spectator websocket client");
  }
  if (input.requireProtocolEvidence) {
    if (evidence.viewCommitCount === 0) {
      failures.push("protocol evidence did not include any view_commit delivery");
    }
    if (evidence.traceCount === 0) {
      failures.push("protocol evidence did not include any frontend trace");
    }
    if (evidence.acceptedAckCount > 0 && evidence.acceptedDecisionAckTraceCount === 0) {
      failures.push("protocol evidence did not include accepted decision_ack trace");
    }
    if (evidence.outboundDecisionCount > 0 && evidence.decisionSentTraceCount === 0) {
      failures.push("protocol evidence did not include decision_sent trace");
    }
    if (evidence.acceptedAckCount > 0 && evidence.activePromptViewCommitTraceCount === 0) {
      failures.push("protocol evidence did not include active prompt view_commit trace");
    }
  }
  if (input.timedOut) {
    failures.push("protocol run timed out before completion");
  }
  if (input.idleTimedOut) {
    failures.push("protocol run made no websocket/runtime progress before completion");
  }
  if (!runtimeCompleted) {
    failures.push("game did not reach completed runtime status");
  }
  if (runtimeCompleted && !input.clients.some((client) => client.metrics.runtimeCompletedCount > 0)) {
    failures.push("no websocket client received completed view_commit");
  }
  if (input.runtimeStatus === "failed") {
    failures.push("runtime status is failed");
  }
  if (input.runtimeStatus === "rejected") {
    failures.push("runtime status is rejected");
  }
  for (const client of input.clients) {
    const metrics = client.metrics;
    if (client.role === "seat" && metrics.acceptedAckCount === 0) {
      failures.push(`${client.label} did not complete any accepted decision through websocket`);
    }
    if (metrics.runtimeRecoveryRequiredCount > 0) {
      failures.push(`${client.label} entered recovery_required ${metrics.runtimeRecoveryRequiredCount} time(s)`);
    }
    if (metrics.reconnectRecoveryPendingCount > 0) {
      failures.push(`${client.label} has unresolved reconnect recovery ${metrics.reconnectRecoveryPendingCount} time(s)`);
    }
    if (metrics.reconnectRecoveryCount < metrics.forcedReconnectCount) {
      failures.push(
        `${client.label} recovered ${metrics.reconnectRecoveryCount}/${metrics.forcedReconnectCount} forced reconnect(s)`,
      );
    }
    if (metrics.nonMonotonicCommitCount > 0) {
      failures.push(`${client.label} saw non-monotonic commit seq ${metrics.nonMonotonicCommitCount} time(s)`);
    }
    if (metrics.semanticCommitRegressionCount > 0) {
      failures.push(`${client.label} saw runtime position regression ${metrics.semanticCommitRegressionCount} time(s)`);
    }
    if (metrics.illegalActionCount > 0) {
      failures.push(`${client.label} produced illegal action ${metrics.illegalActionCount} time(s)`);
    }
    if (metrics.decisionSendFailureCount > 0) {
      failures.push(`${client.label} failed to send decision ${metrics.decisionSendFailureCount} time(s)`);
    }
    if (metrics.rejectedAckCount > 0) {
      failures.push(`${client.label} received rejected decision ack ${metrics.rejectedAckCount} time(s)`);
    }
    const recoveredStaleAckCount = metrics.staleDecisionRetryCount + metrics.unackedDecisionRetryCount;
    if (metrics.staleAckCount > recoveredStaleAckCount) {
      failures.push(
        `${client.label} has unrecovered stale decision ack ${
          metrics.staleAckCount - recoveredStaleAckCount
        }/${metrics.staleAckCount} time(s)`,
      );
    }
    if (metrics.decisionTimeoutFallbackCount > 0) {
      failures.push(`${client.label} saw server decision timeout fallback ${metrics.decisionTimeoutFallbackCount} time(s)`);
    }
    if (metrics.rawPromptFallbackWithoutActiveCommitCount > 0) {
      failures.push(
        `${client.label} answered raw prompt before active view_commit ${metrics.rawPromptFallbackWithoutActiveCommitCount} time(s)`,
      );
    }
    if (metrics.spectatorPromptLeakCount > 0) {
      failures.push(`${client.label} received private prompt ${metrics.spectatorPromptLeakCount} time(s)`);
    }
    if (metrics.spectatorDecisionAckLeakCount > 0) {
      failures.push(`${client.label} received private decision ack ${metrics.spectatorDecisionAckLeakCount} time(s)`);
    }
    if (metrics.identityViolationCount > 0) {
      failures.push(`${client.label} saw malformed protocol identity ${metrics.identityViolationCount} time(s)`);
    }
    if (metrics.errorMessageCount > 0) {
      failures.push(`${client.label} saw stream/client error ${metrics.errorMessageCount} time(s)`);
    }
  }
  if (input.backendTiming) {
    failures.push(...evaluateProtocolBackendTimingGate(input.backendTiming).failures);
  }
  if (input.traces) {
    failures.push(
      ...collectProtocolPromptRepetitionFailures(
        input.traces,
        input.maxRepeatedPromptSignatureCount,
      ),
    );
  }
  return {
    ok: failures.length === 0,
    failures,
  };
}

export function parseProtocolBackendTimingEvents(
  logText: string,
  options: { sessionId?: string } = {},
): ProtocolBackendTimingEvent[] {
  const events: ProtocolBackendTimingEvent[] = [];
  for (const line of logText.split(/\r?\n/)) {
    const jsonStart = line.indexOf("{");
    if (jsonStart < 0) {
      continue;
    }
    let payload: unknown;
    try {
      payload = JSON.parse(line.slice(jsonStart));
    } catch {
      continue;
    }
    if (!isRecord(payload)) {
      continue;
    }
    const event = stringValue(payload["event"]);
    if (
      event !== "runtime_command_process_timing" &&
      event !== "runtime_transition_phase_timing" &&
      event !== "decision_route_timing" &&
      event !== "runtime_decision_gateway_prompt_timing"
    ) {
      continue;
    }
    const sessionId = stringValue(payload["session_id"]);
    if (options.sessionId && sessionId !== options.sessionId) {
      continue;
    }
    events.push({
      ...payload,
      event,
      session_id: sessionId ?? undefined,
      total_ms: numberValue(payload["total_ms"]) ?? undefined,
      command_seq: numberValue(payload["command_seq"]) ?? undefined,
      processed_command_seq: numberValue(payload["processed_command_seq"]) ?? undefined,
      request_id: stringValue(payload["request_id"]) ?? undefined,
      request_type: stringValue(payload["request_type"]) ?? undefined,
      module_type: stringValue(payload["module_type"]) ?? undefined,
      result_status: stringValue(payload["result_status"]) ?? undefined,
      reason: stringValue(payload["reason"]) ?? undefined,
      redis_commit_count: numberValue(payload["redis_commit_count"]) ?? undefined,
      view_commit_count: numberValue(payload["view_commit_count"]) ?? undefined,
      internal_redis_commit_attempt_count: numberValue(payload["internal_redis_commit_attempt_count"]) ?? undefined,
      internal_view_commit_attempt_count: numberValue(payload["internal_view_commit_attempt_count"]) ?? undefined,
    });
  }
  return events;
}

export function summarizeProtocolBackendTiming(
  events: ProtocolBackendTimingEvent[],
  options: { maxCommandMs?: number; maxTransitionMs?: number } = {},
): ProtocolBackendTimingSummary {
  const commandThreshold = Math.max(1, Math.floor(options.maxCommandMs ?? DEFAULT_MAX_BACKEND_COMMAND_MS));
  const transitionThreshold = Math.max(1, Math.floor(options.maxTransitionMs ?? DEFAULT_MAX_BACKEND_TRANSITION_MS));
  const commandEvents = events.filter((event) => event.event === "runtime_command_process_timing");
  const transitionEvents = events.filter((event) => event.event === "runtime_transition_phase_timing");
  const decisionRouteEvents = events.filter((event) => event.event === "decision_route_timing");
  const promptEvents = events.filter((event) => event.event === "runtime_decision_gateway_prompt_timing");
  return {
    eventCount: events.length,
    commandTimingCount: commandEvents.length,
    transitionTimingCount: transitionEvents.length,
    decisionRouteTimingCount: decisionRouteEvents.length,
    promptTimingCount: promptEvents.length,
    maxCommandMs: maxNumber(commandEvents.map((event) => numberValue(event.total_ms) ?? 0)),
    maxTransitionMs: maxNumber(transitionEvents.map((event) => numberValue(event.total_ms) ?? 0)),
    maxDecisionRouteMs: maxNumber(decisionRouteEvents.map((event) => numberValue(event.total_ms) ?? 0)),
    maxPromptMs: maxNumber(promptEvents.map((event) => numberValue(event.total_ms) ?? 0)),
    maxRedisCommitCount: maxNumber(commandEvents.map((event) => numberValue(event.redis_commit_count) ?? 0)),
    maxViewCommitCount: maxNumber(commandEvents.map((event) => numberValue(event.view_commit_count) ?? 0)),
    slowCommandCount: commandEvents.filter((event) => (numberValue(event.total_ms) ?? 0) > commandThreshold).length,
    slowTransitionCount: transitionEvents.filter((event) => (numberValue(event.total_ms) ?? 0) > transitionThreshold).length,
  };
}

export function summarizeProtocolThroughput(args: {
  durationMs: number;
  traces: HeadlessTraceEvent[];
  backendEvents?: ProtocolBackendTimingEvent[];
}): ProtocolThroughputSummary {
  const decisions = args.traces
    .filter((trace) => trace.event === "decision_sent" && trace.request_id && numberValue(trace.ts_ms) !== null)
    .map((trace) => ({
      requestId: trace.request_id as string,
      tsMs: numberValue(trace.ts_ms) ?? 0,
    }));
  const acceptedAcks = args.traces
    .filter((trace) => trace.event === "decision_ack" && trace.status === "accepted" && trace.request_id)
    .map((trace) => ({
      requestId: trace.request_id as string,
      tsMs: numberValue(trace.ts_ms),
    }));
  const firstDecisionByRequestId = new Map<string, number>();
  for (const decision of decisions) {
    const previous = firstDecisionByRequestId.get(decision.requestId);
    if (previous === undefined || decision.tsMs < previous) {
      firstDecisionByRequestId.set(decision.requestId, decision.tsMs);
    }
  }
  const ackLatencyMs = acceptedAcks
    .map((ack) => {
      const sentAt = firstDecisionByRequestId.get(ack.requestId);
      return sentAt !== undefined && ack.tsMs !== null ? Math.max(0, ack.tsMs - sentAt) : null;
    })
    .filter((value): value is number => value !== null);
  const firstCommitSeenAt = new Map<number, number>();
  for (const trace of args.traces) {
    if (trace.event !== "view_commit_seen") {
      continue;
    }
    const commitSeq = numberValue(trace.commit_seq ?? trace.payload?.["commit_seq"]);
    const tsMs = numberValue(trace.ts_ms);
    if (commitSeq === null || tsMs === null) {
      continue;
    }
    const previous = firstCommitSeenAt.get(commitSeq);
    if (previous === undefined || tsMs < previous) {
      firstCommitSeenAt.set(commitSeq, tsMs);
    }
  }
  const commitSeenTimes = [...firstCommitSeenAt.entries()]
    .sort((left, right) => left[0] - right[0])
    .map((entry) => entry[1]);
  const commitGaps = commitSeenTimes
    .slice(1)
    .map((tsMs, index) => Math.max(0, tsMs - commitSeenTimes[index]));
  const durationMinutes = args.durationMs > 0 ? args.durationMs / 60_000 : null;
  return {
    decisionCount: decisions.length,
    acceptedAckCount: acceptedAcks.length,
    missingAckCount: Math.max(0, firstDecisionByRequestId.size - new Set(acceptedAcks.map((ack) => ack.requestId)).size),
    uniqueViewCommitCount: firstCommitSeenAt.size,
    durationMs: Math.max(0, Math.floor(args.durationMs)),
    decisionsPerMinute: durationMinutes ? roundPercent(decisions.length / durationMinutes) : null,
    ackLatencyMs: summarizePercentiles(ackLatencyMs),
    commitGapMs: summarizePercentiles(commitGaps),
    backend: summarizeBackendThroughput(args.backendEvents ?? []),
  };
}

export function evaluateProtocolBackendTimingGate(input: ProtocolBackendTimingGateInput): ProtocolGateResult {
  const failures: string[] = [];
  const events = input.events;
  const commandEvents = events.filter((event) => event.event === "runtime_command_process_timing");
  const transitionEvents = events.filter((event) => event.event === "runtime_transition_phase_timing");
  const maxCommandMs = Math.max(1, Math.floor(input.maxCommandMs ?? DEFAULT_MAX_BACKEND_COMMAND_MS));
  const maxTransitionMs = Math.max(1, Math.floor(input.maxTransitionMs ?? DEFAULT_MAX_BACKEND_TRANSITION_MS));
  const maxRedisCommitCount = Math.max(1, Math.floor(input.maxRedisCommitCount ?? 1));
  const maxViewCommitCount = Math.max(1, Math.floor(input.maxViewCommitCount ?? 1));

  if (input.required && commandEvents.length === 0) {
    failures.push("backend timing gate did not find runtime_command_process_timing events");
  }
  if (input.required && transitionEvents.length === 0) {
    failures.push("backend timing gate did not find runtime_transition_phase_timing events");
  }
  for (const event of commandEvents) {
    const totalMs = numberValue(event.total_ms) ?? 0;
    if (totalMs > maxCommandMs) {
      failures.push(`backend command exceeded ${maxCommandMs}ms: ${describeBackendTimingEvent(event, totalMs)}`);
    }
    const redisCommitCount = numberValue(event.redis_commit_count) ?? 0;
    if (redisCommitCount > maxRedisCommitCount) {
      failures.push(
        `backend command redis_commit_count exceeded ${maxRedisCommitCount}: ${describeBackendTimingEvent(event, redisCommitCount)}`,
      );
    }
    const viewCommitCount = numberValue(event.view_commit_count) ?? 0;
    if (viewCommitCount > maxViewCommitCount) {
      failures.push(
        `backend command view_commit_count exceeded ${maxViewCommitCount}: ${describeBackendTimingEvent(event, viewCommitCount)}`,
      );
    }
  }
  for (const event of transitionEvents) {
    const totalMs = numberValue(event.total_ms) ?? 0;
    if (totalMs > maxTransitionMs) {
      failures.push(`backend transition exceeded ${maxTransitionMs}ms: ${describeBackendTimingEvent(event, totalMs)}`);
    }
  }
  return {
    ok: failures.length === 0,
    failures,
  };
}

export function collectProtocolSuspicionFailures(clients: ProtocolClientRuntime[]): string[] {
  const failures: string[] = [];
  for (const client of clients) {
    const metrics = client.metrics;
    if (metrics.runtimeRecoveryRequiredCount > 0) {
      failures.push(`${client.label} entered recovery_required ${metrics.runtimeRecoveryRequiredCount} time(s)`);
    }
    if (metrics.nonMonotonicCommitCount > 0) {
      failures.push(`${client.label} saw non-monotonic commit seq ${metrics.nonMonotonicCommitCount} time(s)`);
    }
    if (metrics.semanticCommitRegressionCount > 0) {
      failures.push(`${client.label} saw runtime position regression ${metrics.semanticCommitRegressionCount} time(s)`);
    }
    if (metrics.illegalActionCount > 0) {
      failures.push(`${client.label} produced illegal action ${metrics.illegalActionCount} time(s)`);
    }
    if (metrics.decisionSendFailureCount > 0) {
      failures.push(`${client.label} failed to send decision ${metrics.decisionSendFailureCount} time(s)`);
    }
    if (metrics.rejectedAckCount > 0) {
      failures.push(`${client.label} received rejected decision ack ${metrics.rejectedAckCount} time(s)`);
    }
    if (metrics.decisionTimeoutFallbackCount > 0) {
      failures.push(`${client.label} saw server decision timeout fallback ${metrics.decisionTimeoutFallbackCount} time(s)`);
    }
    if (metrics.spectatorPromptLeakCount > 0) {
      failures.push(`${client.label} received private prompt ${metrics.spectatorPromptLeakCount} time(s)`);
    }
    if (metrics.spectatorDecisionAckLeakCount > 0) {
      failures.push(`${client.label} received private decision ack ${metrics.spectatorDecisionAckLeakCount} time(s)`);
    }
    if (metrics.identityViolationCount > 0) {
      failures.push(`${client.label} saw malformed protocol identity ${metrics.identityViolationCount} time(s)`);
    }
    if (metrics.errorMessageCount > 0) {
      failures.push(`${client.label} saw stream/client error ${metrics.errorMessageCount} time(s)`);
    }
  }
  return failures;
}

export function collectProtocolPromptRepetitionFailures(
  traces: HeadlessTraceEvent[],
  maxRepeatedPromptSignatureCount = 8,
): string[] {
  return summarizeProtocolPromptRepetitions(traces, maxRepeatedPromptSignatureCount)
    .map((item) => (
      `repeated active prompt signature exceeded ${maxRepeatedPromptSignatureCount}: ` +
      `${item.signature} count=${item.count} first_commit_seq=${item.firstCommitSeq ?? "unknown"} ` +
      `last_commit_seq=${item.lastCommitSeq ?? "unknown"} request_ids=${item.requestIds.slice(0, 5).join(",")}`
    ));
}

export function summarizeProtocolPromptRepetitions(
  traces: HeadlessTraceEvent[],
  maxRepeatedPromptSignatureCount = 8,
): ProtocolPromptRepetitionDiagnostic[] {
  const bySignature = new Map<
    string,
    {
      playerId: number;
      requestType: string;
      activeModuleId: string;
      activeModuleType: string | null;
      roundIndex: number | null;
      turnIndex: number | null;
      requestIds: Set<string>;
      firstCommitSeq: number | null;
      lastCommitSeq: number | null;
    }
  >();
  for (const trace of traces) {
    if (trace.event !== "view_commit_seen" || !isRecord(trace.payload)) {
      continue;
    }
    const requestId = stringValue(trace.payload["active_prompt_request_id"]);
    const playerId = numberValue(trace.payload["active_prompt_player_id"]);
    const requestType = stringValue(trace.payload["active_prompt_request_type"]);
    const activeModuleId = stringValue(trace.payload["active_module_id"]);
    if (!requestId || playerId === null || !requestType || !activeModuleId) {
      continue;
    }
    const activeModuleType = stringValue(trace.payload["active_module_type"]);
    const roundIndex = numberValue(trace.payload["round_index"]);
    const turnIndex = numberValue(trace.payload["turn_index"]);
    const signature = [
      `player=${playerId}`,
      `request_type=${requestType}`,
      `module_id=${activeModuleId}`,
      `module_type=${activeModuleType ?? "unknown"}`,
      `round=${roundIndex ?? "unknown"}`,
      `turn=${turnIndex ?? "unknown"}`,
    ].join(" ");
    let item = bySignature.get(signature);
    if (!item) {
      item = {
        playerId,
        requestType,
        activeModuleId,
        activeModuleType,
        roundIndex,
        turnIndex,
        requestIds: new Set<string>(),
        firstCommitSeq: null,
        lastCommitSeq: null,
      };
      bySignature.set(signature, item);
    }
    item.requestIds.add(requestId);
    const commitSeq = numberValue(trace.commit_seq);
    if (commitSeq !== null) {
      item.firstCommitSeq = item.firstCommitSeq === null ? commitSeq : Math.min(item.firstCommitSeq, commitSeq);
      item.lastCommitSeq = item.lastCommitSeq === null ? commitSeq : Math.max(item.lastCommitSeq, commitSeq);
    }
  }
  return [...bySignature.entries()]
    .map(([signature, item]) => ({
      signature,
      count: item.requestIds.size,
      playerId: item.playerId,
      requestType: item.requestType,
      activeModuleId: item.activeModuleId,
      activeModuleType: item.activeModuleType,
      roundIndex: item.roundIndex,
      turnIndex: item.turnIndex,
      firstCommitSeq: item.firstCommitSeq,
      lastCommitSeq: item.lastCommitSeq,
      requestIds: [...item.requestIds],
    }))
    .filter((item) => item.count > Math.max(1, Math.floor(maxRepeatedPromptSignatureCount)))
    .sort((left, right) => right.count - left.count);
}

export function policyForProtocolPlayer(
  playerId: number,
  defaultPolicy: DecisionPolicy,
  policiesByPlayerId?: Record<number, DecisionPolicy>,
): DecisionPolicy {
  return policiesByPlayerId?.[playerId] ?? defaultPolicy;
}

export async function createProtocolSession(
  baseUrl: string,
  payload: HeadlessHumanSessionPayload,
  transport = new FrontendTransportAdapter({ baseUrl }),
): Promise<ProtocolSessionInfo> {
  const data = await transport.createSession(payload) as CreateSessionResult;
  const sessionId = requireString(data.session_id, "create session response did not include session_id");
  const hostToken = requireString(data.host_token, "create session response did not include host_token");
  const joinTokens = Object.fromEntries(
    Object.entries(data.join_tokens ?? {}).map(([seat, token]) => [Number(seat), String(token)]),
  );
  return {
    sessionId,
    hostToken,
    joinTokens,
    seats: [],
  };
}

export async function joinProtocolSeats(
  baseUrl: string,
  session: Pick<ProtocolSessionInfo, "sessionId" | "joinTokens">,
  transport = new FrontendTransportAdapter({ baseUrl }),
): Promise<ProtocolSeatJoin[]> {
  const joins: ProtocolSeatJoin[] = [];
  for (const seat of Object.keys(session.joinTokens).map(Number).sort((left, right) => left - right)) {
    const token = session.joinTokens[seat];
    const data = await transport.joinSession({
      sessionId: session.sessionId,
      seat,
      joinToken: token,
      displayName: `Headless ${seat}`,
    }) as JoinSessionResult;
    joins.push({
      seat,
      playerId: Number(data.player_id ?? seat),
      token: requireString(data.session_token, `join response for seat ${seat} did not include session_token`),
    });
  }
  return joins;
}

export async function startProtocolSession(
  baseUrl: string,
  sessionId: string,
  hostToken: string,
  transport = new FrontendTransportAdapter({ baseUrl }),
): Promise<void> {
  await transport.startSession({ sessionId, hostToken });
}

export async function fetchRuntimeStatus(
  baseUrl: string,
  sessionId: string,
  token?: string,
  transport = new FrontendTransportAdapter({
    baseUrl,
    fetchRetryCount: DEFAULT_FETCH_RETRY_COUNT,
    fetchRetryDelayMs: DEFAULT_FETCH_RETRY_DELAY_MS,
  }),
): Promise<string | null> {
  let data: RuntimeStatusResult;
  try {
    data = await transport.getRuntimeStatus({ sessionId, token }) as RuntimeStatusResult;
  } catch (error) {
    if (error instanceof FrontendTransportApiError && error.status === 404 && error.code === "SESSION_NOT_FOUND") {
      return "not_found";
    }
    throw error;
  }
  const status = data.runtime?.status;
  return typeof status === "string" ? status : null;
}

export async function runFullStackProtocolGame(
  options: RunFullStackProtocolGameOptions = {},
): Promise<FullStackProtocolRunResult> {
  const startedAt = Date.now();
  const profile = options.profile ?? "live";
  const baseUrl = normalizeBaseUrl(options.baseUrl ?? DEFAULT_BASE_URL);
  const transport = new FrontendTransportAdapter({
    baseUrl,
    fetchRetryCount: DEFAULT_FETCH_RETRY_COUNT,
    fetchRetryDelayMs: DEFAULT_FETCH_RETRY_DELAY_MS,
  });
  const seed = options.seed ?? Date.now();
  const timeoutPolicy = resolveProtocolTimeoutPolicy({
    profile,
    timeoutMs: options.timeoutMs,
    hardTimeoutMs: options.hardTimeoutMs,
    continueWhileProgressing: options.continueWhileProgressing,
  });
  const { timeoutMs, hardTimeoutMs, continueWhileProgressing } = timeoutPolicy;
  const pollIntervalMs = Math.max(25, options.pollIntervalMs ?? (profile === "live" ? 500 : 100));
  const idleTimeoutMs = Math.max(pollIntervalMs * 2, options.idleTimeoutMs ?? (profile === "live" ? 60_000 : 20_000));
  const policy = options.policy ?? baselineDecisionPolicy;
  const rawPromptFallbackDelayMs =
    options.rawPromptFallbackDelayMs === undefined
      ? DEFAULT_PROTOCOL_RAW_PROMPT_FALLBACK_DELAY_MS
      : options.rawPromptFallbackDelayMs;
  const payload = buildHeadlessHumanSessionPayload({
    seed,
    seatCount: options.seatCount ?? 4,
    config: options.config,
  });

  let sessionId = "";
  let runtimeStatus: string | null = null;
  let completed = false;
  let timedOut = false;
  let progressTimeoutExceeded = false;
  let idleTimedOut = false;
  let completedPollCount = 0;
  const clients: HeadlessGameClient[] = [];
  const firedReconnectScenarios = new Set<ReconnectScenario>();
  const reconnectScenarios = new Set(options.reconnectScenarios ?? []);
  let previousRound: number | null = null;
  let previousTurn: number | null = null;
  let lastProgressAt = Date.now();
  let lastProgressKey = "";
  let lastProgressCallbackAt = 0;
  let previousCpuUsage = process.cpuUsage();
  let previousCpuWallMs = Date.now();
  const cpuDiagnosticIdleMs = Math.max(1_000, Math.floor(options.cpuDiagnosticIdleMs ?? DEFAULT_CPU_DIAGNOSTIC_IDLE_MS));
  const cpuLowLoadPercent = Math.max(0, Number(options.cpuLowLoadPercent ?? DEFAULT_CPU_LOW_LOAD_PERCENT));
  const progressIntervalMs =
    options.onProgress && Number.isFinite(options.progressIntervalMs)
      ? Math.max(250, Math.floor(options.progressIntervalMs ?? 0))
      : options.onProgress
        ? DEFAULT_PROGRESS_INTERVAL_MS
        : 0;

  try {
    const session = await createProtocolSession(baseUrl, payload, transport);
    const joinedSeats = await joinProtocolSeats(baseUrl, session, transport);
    session.seats = joinedSeats;
    sessionId = session.sessionId;

    for (const join of joinedSeats) {
      clients.push(
        new HeadlessGameClient({
          sessionId: session.sessionId,
          token: join.token,
          playerId: join.playerId,
          baseUrl,
          policy: policyForProtocolPlayer(join.playerId, policy, options.policiesByPlayerId),
          autoReconnect: true,
          failOnIllegal: true,
          rawPromptFallbackDelayMs,
        }),
      );
    }
    if (options.spectator ?? true) {
      clients.push(
        new HeadlessGameClient({
          sessionId: session.sessionId,
          playerId: 0,
          baseUrl,
          policy,
          autoReconnect: true,
          failOnIllegal: true,
          rawPromptFallbackDelayMs,
        }),
      );
    }

    for (const client of clients) {
      client.connect();
    }
    await waitForClientsToConnect(clients, 2_500);
    await startProtocolSession(baseUrl, session.sessionId, session.hostToken, transport);
    if (reconnectScenarios.has("after_start")) {
      forceReconnectOnce(clients, firedReconnectScenarios, "after_start");
    }

    while (Date.now() - startedAt < hardTimeoutMs) {
      await sleep(pollIntervalMs);
      progressTimeoutExceeded = Date.now() - startedAt >= timeoutMs;
      fireReconnectTriggers({
        clients,
        reconnectScenarios,
        firedReconnectScenarios,
        previousRound,
        previousTurn,
        runtimeStatus,
      });
      const latestRuntime = latestRuntimePosition(clients);
      previousRound = latestRuntime.roundIndex ?? previousRound;
      previousTurn = latestRuntime.turnIndex ?? previousTurn;
      runtimeStatus = await fetchRuntimeStatus(baseUrl, session.sessionId, joinedSeats[0]?.token, transport);
      if (
        collectProtocolSuspicionFailures(clients.map(toProtocolClientRuntime)).length > 0 ||
        collectProtocolPromptRepetitionFailures(clients.flatMap((client) => client.trace)).length > 0
      ) {
        break;
      }
      const progressKey = buildProtocolProgressKey(clients, runtimeStatus);
      let progressKeyChanged = false;
      if (progressKey !== lastProgressKey) {
        lastProgressKey = progressKey;
        lastProgressAt = Date.now();
        progressKeyChanged = true;
      } else if (Date.now() - lastProgressAt >= idleTimeoutMs) {
        idleTimedOut = true;
        break;
      }
      completedPollCount = runtimeStatus === "completed" ? completedPollCount + 1 : 0;
      const websocketCompleted = clients.some((client) => client.metrics.runtimeCompletedCount > 0);
      if (runtimeStatus === "completed" && !websocketCompleted) {
        requestCompletionResume(clients);
        if (completedPollCount >= COMPLETED_COMMIT_GRACE_POLLS) {
          break;
        }
      }
      completed =
        completedPollCount >= 2 &&
        websocketCompleted;
      if (completed || runtimeStatus === "failed" || runtimeStatus === "rejected") {
        break;
      }
      const progressCheckAt = Date.now();
      const progressReason = progressKeyChanged ? "progress" : "interval";
      if (
        shouldEmitProtocolProgress({
          enabled: Boolean(options.onProgress),
          nowMs: progressCheckAt,
          lastCallbackAtMs: lastProgressCallbackAt,
          progressIntervalMs,
          progressKeyChanged,
        })
      ) {
        lastProgressCallbackAt = progressCheckAt;
        const onProgress = options.onProgress;
        await onProgress?.(
          buildProgressSnapshot({
            sessionId,
            profile,
            reason: progressReason,
            startedAt,
            runtimeStatus,
            clients,
            completed,
            timedOut,
            progressTimeoutExceeded,
            idleTimedOut,
            lastProgressAt,
            cpuDiagnosticIdleMs,
            cpuLowLoadPercent,
            previousCpuUsage,
            previousCpuWallMs,
          }),
        );
        previousCpuUsage = process.cpuUsage();
        previousCpuWallMs = Date.now();
      }
    }
    timedOut =
      !completed &&
      runtimeStatus !== "failed" &&
      runtimeStatus !== "rejected" &&
      Date.now() - startedAt >= hardTimeoutMs;
    progressTimeoutExceeded = progressTimeoutExceeded || Date.now() - startedAt >= timeoutMs;
  } finally {
    if (sessionId) {
      try {
        const firstSeatToken = clients.find((client) => client.playerId > 0)?.token;
        runtimeStatus = await fetchRuntimeStatus(baseUrl, sessionId, firstSeatToken, transport);
      } catch {
        // Keep the last successfully observed status in the run summary.
      }
      if (options.onProgress) {
        await options.onProgress(
          buildProgressSnapshot({
            sessionId,
            profile,
            reason: "final",
            startedAt,
            runtimeStatus,
            clients,
            completed,
            timedOut,
            progressTimeoutExceeded,
            idleTimedOut,
            lastProgressAt,
            cpuDiagnosticIdleMs,
            cpuLowLoadPercent,
            previousCpuUsage,
            previousCpuWallMs,
          }),
        );
        previousCpuUsage = process.cpuUsage();
        previousCpuWallMs = Date.now();
      }
    }
    for (const client of clients) {
      client.disconnect();
    }
  }

  const clientRuntimes = clients.map(toProtocolClientRuntime);
  const gateInput: ProtocolGateInput = {
    timedOut,
    idleTimedOut,
    completed,
    clients: clientRuntimes,
    runtimeStatus,
    traces: clients.flatMap((client) => client.trace),
    expectedSeatCount: payload.seats.length,
    requireSpectator: options.spectator ?? true,
    requireProtocolEvidence: true,
  };
  const protocolEvidence = summarizeProtocolGateEvidence(gateInput);
  const gate = evaluateProtocolGate(gateInput);
  return {
    ok: gate.ok,
    profile,
    sessionId,
    durationMs: Date.now() - startedAt,
    timedOut,
    progressTimeoutExceeded,
    timeoutMs,
    hardTimeoutMs,
    continueWhileProgressing,
    idleTimedOut,
    completed,
    runtimeStatus,
    failures: gate.failures,
    clients: clientRuntimes,
    clientSummary: summarizeProtocolClients(clientRuntimes),
    protocolEvidence,
    traces: gateInput.traces ?? [],
  };
}

function buildProgressSnapshot(args: {
  sessionId: string;
  profile: ProtocolProfile;
  reason: ProtocolProgressReason;
  startedAt: number;
  runtimeStatus: string | null;
  clients: HeadlessGameClient[];
  completed: boolean;
  timedOut: boolean;
  progressTimeoutExceeded: boolean;
  idleTimedOut: boolean;
  lastProgressAt: number;
  cpuDiagnosticIdleMs: number;
  cpuLowLoadPercent: number;
  previousCpuUsage: NodeJS.CpuUsage;
  previousCpuWallMs: number;
}): FullStackProtocolProgressSnapshot {
  const clientRuntimes = args.clients.map(toProtocolClientRuntime);
  const traces = args.clients.flatMap((client) => client.trace);
  const idleMs = Date.now() - args.lastProgressAt;
  return {
    sessionId: args.sessionId,
    profile: args.profile,
    reason: args.reason,
    elapsedMs: Date.now() - args.startedAt,
    idleMs,
    runtimeStatus: args.runtimeStatus,
    pace: buildProtocolPaceDiagnostic({
      runtimeStatus: args.runtimeStatus,
      elapsedMs: Date.now() - args.startedAt,
      clients: clientRuntimes,
      traces,
    }),
    clients: clientRuntimes,
    clientSummary: summarizeProtocolClients(clientRuntimes),
    traceCount: traces.length,
    completed: args.completed,
    timedOut: args.timedOut,
    progressTimeoutExceeded: args.progressTimeoutExceeded,
    idleTimedOut: args.idleTimedOut,
    cpu: buildCpuDiagnostic({
      idleMs,
      thresholdMs: args.cpuDiagnosticIdleMs,
      lowLoadPercent: args.cpuLowLoadPercent,
      previousCpuUsage: args.previousCpuUsage,
      previousCpuWallMs: args.previousCpuWallMs,
    }),
    traces,
  };
}

export function buildProtocolPaceDiagnostic(args: {
  runtimeStatus: string | null;
  elapsedMs: number;
  clients: ProtocolClientRuntime[];
  traces: HeadlessTraceEvent[];
}): ProtocolPaceDiagnostic {
  const elapsedMinutes = Math.max(1 / 60, args.elapsedMs / 60_000);
  const maxCommitSeq = Math.max(0, ...args.clients.map((client) => client.lastCommitSeq));
  const seatMetrics = args.clients.filter((client) => client.role === "seat").map((client) => client.metrics);
  const outboundDecisionCount = seatMetrics.reduce((sum, metrics) => sum + metrics.outboundDecisionCount, 0);
  const acceptedAckCount = seatMetrics.reduce((sum, metrics) => sum + metrics.acceptedAckCount, 0);
  const latestTrace = args.traces.at(-1) ?? null;
  const latestViewCommit = [...args.traces]
    .reverse()
    .find((trace) => trace.event === "view_commit_seen" && isRecord(trace.payload));
  const latestDecision = [...args.traces]
    .reverse()
    .find((trace) => trace.event === "decision_sent" || trace.event === "decision_retry_sent");
  const latestAck = [...args.traces].reverse().find((trace) => trace.event === "decision_ack");
  const commandLatency = buildCommandLatencyDiagnostics(args.traces);
  const payload = isRecord(latestViewCommit?.payload) ? latestViewCommit.payload : {};
  const activePromptRequestId = stringValue(payload["active_prompt_request_id"]);
  const activePromptPlayerId = numberValue(payload["active_prompt_player_id"]);
  const activePromptRequestType = stringValue(payload["active_prompt_request_type"]);
  const latestRuntimeStatus = stringValue(payload["runtime_status"]) ?? args.runtimeStatus;
  return {
    maxCommitSeq,
    latestRoundIndex: numberValue(payload["round_index"]),
    latestTurnIndex: numberValue(payload["turn_index"]),
    latestRuntimeStatus,
    activePromptRequestId,
    activePromptPlayerId,
    activePromptRequestType,
    waitingOnActivePrompt: args.runtimeStatus === "waiting_input" && activePromptRequestId !== null,
    latestTraceEvent: latestTrace?.event ?? null,
    latestDecisionRequestId: latestDecision?.request_id ?? null,
    latestAckRequestId: latestAck?.request_id ?? null,
    latestAckStatus: latestAck?.status ?? null,
    commitSeqPerMinute: roundPercent(maxCommitSeq / elapsedMinutes),
    decisionsPerMinute: roundPercent(outboundDecisionCount / elapsedMinutes),
    acceptedAcksPerMinute: roundPercent(acceptedAckCount / elapsedMinutes),
    slowestCommandLatencies: commandLatency.slowest,
    pendingDecisionAges: commandLatency.pending,
  };
}

function buildCommandLatencyDiagnostics(traces: HeadlessTraceEvent[]): {
  slowest: ProtocolCommandLatencyDiagnostic[];
  pending: ProtocolPendingDecisionDiagnostic[];
} {
  const byRequestId = new Map<
    string,
    {
      requestId: string;
      playerId: number;
      requestType: string | null;
      firstActivePromptTs: number | null;
      firstDecisionTs: number | null;
      firstAckTs: number | null;
      status: string | null;
    }
  >();
  const traceNowMs = Math.max(0, ...traces.map((trace) => numberValue(trace.ts_ms) ?? 0));
  for (const trace of traces) {
    const ts = numberValue(trace.ts_ms);
    if (ts === null) {
      continue;
    }
    if (trace.event === "view_commit_seen" && isRecord(trace.payload)) {
      const requestId = stringValue(trace.payload["active_prompt_request_id"]);
      const playerId = numberValue(trace.payload["active_prompt_player_id"]);
      if (!requestId || playerId === null) {
        continue;
      }
      const item = commandLatencyItem(byRequestId, requestId, playerId);
      item.requestType = item.requestType ?? stringValue(trace.payload["active_prompt_request_type"]);
      item.firstActivePromptTs = item.firstActivePromptTs ?? ts;
      continue;
    }
    if (trace.event === "decision_sent" || trace.event === "decision_retry_sent" || trace.event === "decision_unacked_retry_sent") {
      const requestId = trace.request_id;
      if (!requestId) {
        continue;
      }
      const item = commandLatencyItem(byRequestId, requestId, trace.player_id);
      item.requestType = item.requestType ?? stringValue(trace.payload?.["request_type"]);
      item.firstDecisionTs = item.firstDecisionTs ?? ts;
      continue;
    }
    if (trace.event === "decision_ack") {
      const requestId = trace.request_id;
      if (!requestId) {
        continue;
      }
      const item = commandLatencyItem(byRequestId, requestId, trace.player_id);
      if (item.firstAckTs === null) {
        item.firstAckTs = ts;
        item.status = trace.status ?? item.status;
      } else if (item.status !== "accepted" && trace.status === "accepted") {
        item.status = trace.status;
      }
    }
  }
  const rows = [...byRequestId.values()].map((item) => {
    const promptToDecisionMs =
      item.firstActivePromptTs !== null && item.firstDecisionTs !== null
        ? Math.max(0, item.firstDecisionTs - item.firstActivePromptTs)
        : null;
    const decisionToAckMs =
      item.firstDecisionTs !== null && item.firstAckTs !== null
        ? Math.max(0, item.firstAckTs - item.firstDecisionTs)
        : null;
    const totalMs =
      item.firstActivePromptTs !== null && item.firstAckTs !== null
        ? Math.max(0, item.firstAckTs - item.firstActivePromptTs)
        : null;
    return {
      requestId: item.requestId,
      playerId: item.playerId,
      requestType: item.requestType,
      promptToDecisionMs,
      decisionToAckMs,
      totalMs,
      status: item.status,
    };
  });
  const slowest = rows
    .filter((row) => row.promptToDecisionMs !== null || row.decisionToAckMs !== null || row.totalMs !== null)
    .sort((left, right) => commandLatencySortValue(right) - commandLatencySortValue(left))
    .slice(0, 5);
  const pending = [...byRequestId.values()]
    .filter((item) => item.firstDecisionTs !== null && item.firstAckTs === null)
    .map((item) => ({
      requestId: item.requestId,
      playerId: item.playerId,
      requestType: item.requestType,
      ageMs: Math.max(0, traceNowMs - (item.firstDecisionTs ?? traceNowMs)),
    }))
    .sort((left, right) => right.ageMs - left.ageMs)
    .slice(0, 5);
  return { slowest, pending };
}

function commandLatencyItem(
  byRequestId: Map<
    string,
    {
      requestId: string;
      playerId: number;
      requestType: string | null;
      firstActivePromptTs: number | null;
      firstDecisionTs: number | null;
      firstAckTs: number | null;
      status: string | null;
    }
  >,
  requestId: string,
  playerId: number,
) {
  let item = byRequestId.get(requestId);
  if (!item) {
    item = {
      requestId,
      playerId,
      requestType: null,
      firstActivePromptTs: null,
      firstDecisionTs: null,
      firstAckTs: null,
      status: null,
    };
    byRequestId.set(requestId, item);
  }
  return item;
}

function commandLatencySortValue(row: ProtocolCommandLatencyDiagnostic): number {
  return Math.max(row.totalMs ?? 0, row.promptToDecisionMs ?? 0, row.decisionToAckMs ?? 0);
}

export function shouldEmitProtocolProgress(args: {
  enabled: boolean;
  nowMs: number;
  lastCallbackAtMs: number;
  progressIntervalMs: number;
  progressKeyChanged: boolean;
}): boolean {
  if (!args.enabled || args.progressIntervalMs <= 0) {
    return false;
  }
  if (args.lastCallbackAtMs <= 0) {
    return true;
  }
  const elapsedMs = args.nowMs - args.lastCallbackAtMs;
  if (elapsedMs >= args.progressIntervalMs) {
    return true;
  }
  const changeMinIntervalMs = Math.min(PROGRESS_CHANGE_MIN_INTERVAL_MS, args.progressIntervalMs);
  return args.progressKeyChanged && elapsedMs >= changeMinIntervalMs;
}

function buildCpuDiagnostic(args: {
  idleMs: number;
  thresholdMs: number;
  lowLoadPercent: number;
  previousCpuUsage: NodeJS.CpuUsage;
  previousCpuWallMs: number;
}): ProtocolCpuDiagnostic {
  if (args.idleMs < args.thresholdMs) {
    return {
      sampled: false,
      idleMs: args.idleMs,
      processCpuPercent: null,
      hostCpuRawPercent: null,
      hostLogicalCpuCount: null,
      hostCpuPercent: null,
      suspiciousIdle: false,
    };
  }
  try {
    const elapsedMs = Math.max(1, Date.now() - args.previousCpuWallMs);
    const cpu = process.cpuUsage(args.previousCpuUsage);
    const processCpuPercent = roundPercent(((cpu.user + cpu.system) / 1000 / elapsedMs) * 100);
    const hostCpu = sampleHostCpuLoad();
    const hostLow = hostCpu.hostCpuPercent !== null && hostCpu.hostCpuPercent <= args.lowLoadPercent;
    const processLow = processCpuPercent <= args.lowLoadPercent;
    return {
      sampled: true,
      idleMs: args.idleMs,
      processCpuPercent,
      ...hostCpu,
      suspiciousIdle: processLow && hostLow,
    };
  } catch (error) {
    return {
      sampled: true,
      idleMs: args.idleMs,
      processCpuPercent: null,
      hostCpuRawPercent: null,
      hostLogicalCpuCount: null,
      hostCpuPercent: null,
      suspiciousIdle: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function sampleHostCpuLoad(): Pick<
  ProtocolCpuDiagnostic,
  "hostCpuRawPercent" | "hostLogicalCpuCount" | "hostCpuPercent"
> {
  try {
    const output = execFileSync("ps", ["-A", "-o", "%cpu="], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 1_000,
    });
    const total = output
      .split(/\s+/)
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value))
      .reduce((sum, value) => sum + value, 0);
    const logicalCpuCount = sampleLogicalCpuCount();
    return {
      hostCpuRawPercent: roundPercent(total),
      hostLogicalCpuCount: logicalCpuCount,
      hostCpuPercent: roundPercent(total / logicalCpuCount),
    };
  } catch {
    return {
      hostCpuRawPercent: null,
      hostLogicalCpuCount: null,
      hostCpuPercent: null,
    };
  }
}

function sampleLogicalCpuCount(): number {
  try {
    const output = execFileSync("sysctl", ["-n", "hw.logicalcpu"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 1_000,
    });
    const value = Number(output.trim());
    if (Number.isFinite(value) && value > 0) {
      return value;
    }
  } catch {
    // Fall through to Node's cross-platform CPU list.
  }
  return Math.max(1, cpus().length);
}

function roundPercent(value: number): number {
  return Math.round(value * 100) / 100;
}

export function buildProtocolProgressKey(
  clients: Array<Pick<HeadlessGameClient, "playerId" | "status" | "state" | "metrics">>,
  runtimeStatus: string | null,
): string {
  return [
    runtimeStatus ?? "",
    ...clients.map((client) => {
      const metrics = client.metrics;
      return [
        client.playerId,
        client.status,
        client.state.lastCommitSeq,
        metrics.promptMessageCount,
        metrics.outboundDecisionCount,
        metrics.acceptedAckCount,
        metrics.rejectedAckCount,
        metrics.staleAckCount,
        metrics.illegalActionCount,
        metrics.decisionSendFailureCount,
        metrics.errorMessageCount,
        metrics.runtimeCompletedCount,
        metrics.runtimeRecoveryRequiredCount,
        metrics.nonMonotonicCommitCount,
        metrics.semanticCommitRegressionCount,
        metrics.decisionTimeoutFallbackCount,
        metrics.forcedReconnectCount,
        metrics.reconnectRecoveryCount,
        metrics.reconnectRecoveryPendingCount,
      ].join(":");
    }),
  ].join("|");
}

function toProtocolClientRuntime(client: HeadlessGameClient): ProtocolClientRuntime {
  const viewer = client.state.latestCommit?.viewer;
  const role: ProtocolClientRole = viewer?.role === "spectator" || client.playerId === 0 ? "spectator" : "seat";
  return {
    label: role === "spectator" ? "spectator" : `seat:${client.playerId}`,
    role,
    playerId: client.playerId,
    status: client.status,
    lastCommitSeq: client.state.lastCommitSeq,
    metrics: { ...client.metrics },
    traceCount: client.trace.length,
  };
}

function forceReconnectOnce(
  clients: HeadlessGameClient[],
  fired: Set<ReconnectScenario>,
  scenario: ReconnectScenario,
): void {
  if (fired.has(scenario)) {
    return;
  }
  fired.add(scenario);
  for (const client of clients) {
    client.forceReconnect(scenario);
  }
}

function fireReconnectTriggers(args: {
  clients: HeadlessGameClient[];
  reconnectScenarios: Set<ReconnectScenario>;
  firedReconnectScenarios: Set<ReconnectScenario>;
  previousRound: number | null;
  previousTurn: number | null;
  runtimeStatus: string | null;
}): void {
  if (args.runtimeStatus === "completed" || args.runtimeStatus === "failed") {
    return;
  }
  if (args.reconnectScenarios.has("after_first_commit") && args.clients.some((client) => client.state.lastCommitSeq > 0)) {
    forceReconnectOnce(args.clients, args.firedReconnectScenarios, "after_first_commit");
  }
  if (args.reconnectScenarios.has("after_first_prompt") && args.clients.some((client) => client.metrics.promptMessageCount > 0)) {
    forceReconnectOnce(args.clients, args.firedReconnectScenarios, "after_first_prompt");
  }
  if (args.reconnectScenarios.has("after_first_decision") && args.clients.some((client) => client.metrics.outboundDecisionCount > 0)) {
    forceReconnectOnce(args.clients, args.firedReconnectScenarios, "after_first_decision");
  }
  const latest = latestRuntimePosition(args.clients);
  if (
    args.reconnectScenarios.has("round_boundary") &&
    args.previousRound !== null &&
    latest.roundIndex !== null &&
    latest.roundIndex > args.previousRound
  ) {
    forceReconnectOnce(args.clients, args.firedReconnectScenarios, "round_boundary");
  }
  if (
    args.reconnectScenarios.has("turn_boundary") &&
    args.previousTurn !== null &&
    latest.turnIndex !== null &&
    latest.turnIndex !== args.previousTurn
  ) {
    forceReconnectOnce(args.clients, args.firedReconnectScenarios, "turn_boundary");
  }
}

function requestCompletionResume(clients: HeadlessGameClient[]): void {
  for (const client of clients) {
    const sent = client.requestResume();
    if (!sent) {
      client.forceReconnect("completion_resume");
    }
  }
}

function latestRuntimePosition(clients: HeadlessGameClient[]): {
  roundIndex: number | null;
  turnIndex: number | null;
} {
  const latest = clients
    .map((client) => client.state.latestCommit)
    .filter((commit): commit is NonNullable<typeof commit> => commit !== null)
    .sort((left, right) => Number(right.commit_seq) - Number(left.commit_seq))[0];
  return {
    roundIndex: typeof latest?.runtime.round_index === "number" ? latest.runtime.round_index : null,
    turnIndex: typeof latest?.runtime.turn_index === "number" ? latest.runtime.turn_index : null,
  };
}

async function waitForClientsToConnect(clients: HeadlessGameClient[], timeoutMs: number): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (clients.every((client) => client.status === "connected")) {
      return;
    }
    await sleep(25);
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return normalizeFrontendHttpBaseUrl(baseUrl || DEFAULT_BASE_URL);
}

function requireString(value: unknown, message: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(message);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function maxNumber(values: number[]): number {
  return values.length > 0 ? Math.max(0, ...values) : 0;
}

function summarizePercentiles(values: number[]): ProtocolPercentileSummary {
  const sorted = values
    .filter((value) => Number.isFinite(value))
    .map((value) => Math.max(0, Math.round(value)))
    .sort((left, right) => left - right);
  return {
    count: sorted.length,
    p50: percentile(sorted, 0.5),
    p95: percentile(sorted, 0.95),
    max: sorted.length > 0 ? sorted[sorted.length - 1] : null,
  };
}

function percentile(sortedValues: number[], rank: number): number | null {
  if (sortedValues.length === 0) {
    return null;
  }
  const index = Math.min(sortedValues.length - 1, Math.max(0, Math.ceil(sortedValues.length * rank) - 1));
  return sortedValues[index];
}

function summarizeBackendThroughput(events: ProtocolBackendTimingEvent[]): ProtocolThroughputSummary["backend"] {
  return {
    command: summarizeBackendPhase(
      events.filter((event) => event.event === "runtime_command_process_timing"),
      ["command_boundary_finalization_ms", "authoritative_commit_ms", "prompt_materialize_ms", "total_ms"],
    ),
    transition: summarizeBackendPhase(
      events.filter((event) => event.event === "runtime_transition_phase_timing"),
      ["engine_transition_ms", "redis_commit_ms", "view_commit_build_ms", "total_ms"],
    ),
    decisionRoute: summarizeBackendPhase(
      events.filter((event) => event.event === "decision_route_timing"),
      ["latest_view_commit_ms", "submit_decision_ms", "ack_publish_ms", "total_ms"],
    ),
    prompt: summarizeBackendPhase(
      events.filter((event) => event.event === "runtime_decision_gateway_prompt_timing"),
      ["create_prompt_ms", "replay_wait_ms", "total_ms"],
    ),
  };
}

function summarizeBackendPhase(events: ProtocolBackendTimingEvent[], phaseKeys: string[]): ProtocolBackendPhaseSummary {
  return {
    count: events.length,
    totalMs: summarizePercentiles(events.map((event) => numberValue(event.total_ms) ?? 0)),
    phases: Object.fromEntries(
      phaseKeys.map((key) => [
        key,
        summarizePercentiles(events.map((event) => numberValue(event[key])).filter((value): value is number => value !== null)),
      ]),
    ),
  };
}

function describeBackendTimingEvent(event: ProtocolBackendTimingEvent, value: number): string {
  const commandSeq = numberValue(event.command_seq) ?? numberValue(event.processed_command_seq);
  const fields = [
    `value=${value}`,
    commandSeq !== null ? `command_seq=${commandSeq}` : null,
    stringValue(event.module_type) ? `module=${stringValue(event.module_type)}` : null,
    stringValue(event.request_type) ? `request_type=${stringValue(event.request_type)}` : null,
    stringValue(event.request_id) ? `request_id=${stringValue(event.request_id)}` : null,
    stringValue(event.reason) ? `reason=${stringValue(event.reason)}` : null,
  ].filter((field): field is string => field !== null);
  return fields.join(" ");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
