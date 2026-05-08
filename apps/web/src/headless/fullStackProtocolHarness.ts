import { execFileSync } from "node:child_process";
import type { ConnectionStatus } from "../core/contracts/stream";
import {
  baselineDecisionPolicy,
  HeadlessGameClient,
  type DecisionPolicy,
  type HeadlessMetrics,
  type HeadlessTraceEvent,
} from "./HeadlessGameClient";

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
  runtimeStatus: string | null;
  clients: ProtocolClientRuntime[];
  clientSummary: ProtocolClientSummary;
  traceCount: number;
  completed: boolean;
  timedOut: boolean;
  idleTimedOut: boolean;
  cpu: ProtocolCpuDiagnostic;
  traces: HeadlessTraceEvent[];
};

export type ProtocolCpuDiagnostic = {
  sampled: boolean;
  idleMs: number;
  processCpuPercent: number | null;
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
};

export type ProtocolGateResult = {
  ok: boolean;
  failures: string[];
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
  | "after_first_decision"
  | "round_boundary"
  | "turn_boundary";

export type RunFullStackProtocolGameOptions = {
  profile?: ProtocolProfile;
  baseUrl?: string;
  seed?: number;
  seatCount?: number;
  timeoutMs?: number;
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
  idleTimedOut: boolean;
  completed: boolean;
  runtimeStatus: string | null;
  failures: string[];
  clients: ProtocolClientRuntime[];
  clientSummary: ProtocolClientSummary;
  traces: HeadlessTraceEvent[];
};

type ApiEnvelope<T> = {
  ok?: boolean;
  data?: T;
  error?: unknown;
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

const DEFAULT_BASE_URL = "http://127.0.0.1:9090";
const COMPLETED_COMMIT_GRACE_POLLS = 20;
const DEFAULT_PROTOCOL_RAW_PROMPT_FALLBACK_DELAY_MS: number | null = null;
const DEFAULT_FETCH_RETRY_COUNT = 5;
const DEFAULT_FETCH_RETRY_DELAY_MS = 150;
const DEFAULT_CPU_DIAGNOSTIC_IDLE_MS = 30_000;
const DEFAULT_CPU_LOW_LOAD_PERCENT = 10;

class ProtocolApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  readonly code: string;

  constructor(status: number, body: unknown) {
    super(`Protocol API request failed (${status}): ${JSON.stringify(body)}`);
    this.name = "ProtocolApiError";
    this.status = status;
    this.body = body;
    this.code = extractApiErrorCode(body);
  }
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

export function evaluateProtocolGate(input: ProtocolGateInput): ProtocolGateResult {
  const failures: string[] = [];
  const runtimeCompleted = input.runtimeStatus === "completed" || input.completed;
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
  for (const client of input.clients) {
    const metrics = client.metrics;
    if (client.role === "seat" && metrics.acceptedAckCount === 0) {
      failures.push(`${client.label} did not complete any accepted decision through websocket`);
    }
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
    if (metrics.staleAckCount > 0) {
      failures.push(`${client.label} received stale decision ack ${metrics.staleAckCount} time(s)`);
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
  return {
    ok: failures.length === 0,
    failures,
  };
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
): Promise<ProtocolSessionInfo> {
  const data = await postJson<CreateSessionResult>(baseUrl, "/api/v1/sessions", payload);
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
): Promise<ProtocolSeatJoin[]> {
  const joins: ProtocolSeatJoin[] = [];
  for (const seat of Object.keys(session.joinTokens).map(Number).sort((left, right) => left - right)) {
    const token = session.joinTokens[seat];
    const data = await postJson<JoinSessionResult>(baseUrl, `/api/v1/sessions/${encodeURIComponent(session.sessionId)}/join`, {
      seat,
      join_token: token,
      display_name: `Headless ${seat}`,
    });
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
): Promise<void> {
  await postJson(baseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/start`, {
    host_token: hostToken,
  });
}

export async function fetchRuntimeStatus(
  baseUrl: string,
  sessionId: string,
  token?: string,
): Promise<string | null> {
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  let data: RuntimeStatusResult;
  try {
    data = await getJson<RuntimeStatusResult>(baseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/runtime-status${query}`);
  } catch (error) {
    if (error instanceof ProtocolApiError && error.status === 404 && error.code === "SESSION_NOT_FOUND") {
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
  const seed = options.seed ?? Date.now();
  const timeoutMs = Math.max(1_000, options.timeoutMs ?? (profile === "live" ? 900_000 : 120_000));
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
      : 0;

  try {
    const session = await createProtocolSession(baseUrl, payload);
    const joinedSeats = await joinProtocolSeats(baseUrl, session);
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
    await startProtocolSession(baseUrl, session.sessionId, session.hostToken);
    if (reconnectScenarios.has("after_start")) {
      forceReconnectOnce(clients, firedReconnectScenarios, "after_start");
    }

    while (Date.now() - startedAt < timeoutMs) {
      await sleep(pollIntervalMs);
      fireReconnectTriggers({
        clients,
        reconnectScenarios,
        firedReconnectScenarios,
        previousRound,
        previousTurn,
      });
      const latestRuntime = latestRuntimePosition(clients);
      previousRound = latestRuntime.roundIndex ?? previousRound;
      previousTurn = latestRuntime.turnIndex ?? previousTurn;
      runtimeStatus = await fetchRuntimeStatus(baseUrl, session.sessionId, joinedSeats[0]?.token);
      const progressKey = buildProtocolProgressKey(clients, runtimeStatus);
      if (progressKey !== lastProgressKey) {
        lastProgressKey = progressKey;
        lastProgressAt = Date.now();
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
      if (completed || runtimeStatus === "failed") {
        break;
      }
      if (
        options.onProgress &&
        progressIntervalMs > 0 &&
        Date.now() - lastProgressCallbackAt >= progressIntervalMs
      ) {
        lastProgressCallbackAt = Date.now();
        await options.onProgress(
          buildProgressSnapshot({
            sessionId,
            profile,
            startedAt,
            runtimeStatus,
            clients,
            completed,
            timedOut,
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
    timedOut = !completed && runtimeStatus !== "failed" && Date.now() - startedAt >= timeoutMs;
  } finally {
    if (sessionId) {
      try {
        const firstSeatToken = clients.find((client) => client.playerId > 0)?.token;
        runtimeStatus = await fetchRuntimeStatus(baseUrl, sessionId, firstSeatToken);
      } catch {
        // Keep the last successfully observed status in the run summary.
      }
      if (options.onProgress) {
        await options.onProgress(
          buildProgressSnapshot({
            sessionId,
            profile,
            startedAt,
            runtimeStatus,
            clients,
            completed,
            timedOut,
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
  const gate = evaluateProtocolGate({
    timedOut,
    idleTimedOut,
    completed,
    clients: clientRuntimes,
    runtimeStatus,
  });
  return {
    ok: gate.ok,
    profile,
    sessionId,
    durationMs: Date.now() - startedAt,
    timedOut,
    idleTimedOut,
    completed,
    runtimeStatus,
    failures: gate.failures,
    clients: clientRuntimes,
    clientSummary: summarizeProtocolClients(clientRuntimes),
    traces: clients.flatMap((client) => client.trace),
  };
}

function buildProgressSnapshot(args: {
  sessionId: string;
  profile: ProtocolProfile;
  startedAt: number;
  runtimeStatus: string | null;
  clients: HeadlessGameClient[];
  completed: boolean;
  timedOut: boolean;
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
    elapsedMs: Date.now() - args.startedAt,
    idleMs,
    runtimeStatus: args.runtimeStatus,
    clients: clientRuntimes,
    clientSummary: summarizeProtocolClients(clientRuntimes),
    traceCount: traces.length,
    completed: args.completed,
    timedOut: args.timedOut,
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
      hostCpuPercent: null,
      suspiciousIdle: false,
    };
  }
  try {
    const elapsedMs = Math.max(1, Date.now() - args.previousCpuWallMs);
    const cpu = process.cpuUsage(args.previousCpuUsage);
    const processCpuPercent = roundPercent(((cpu.user + cpu.system) / 1000 / elapsedMs) * 100);
    const hostCpuPercent = sampleHostCpuPercent();
    const hostLow = hostCpuPercent === null || hostCpuPercent <= args.lowLoadPercent;
    const processLow = processCpuPercent <= args.lowLoadPercent;
    return {
      sampled: true,
      idleMs: args.idleMs,
      processCpuPercent,
      hostCpuPercent,
      suspiciousIdle: processLow && hostLow,
    };
  } catch (error) {
    return {
      sampled: true,
      idleMs: args.idleMs,
      processCpuPercent: null,
      hostCpuPercent: null,
      suspiciousIdle: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function sampleHostCpuPercent(): number | null {
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
    return roundPercent(total);
  } catch {
    return null;
  }
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
}): void {
  if (args.reconnectScenarios.has("after_first_commit") && args.clients.some((client) => client.state.lastCommitSeq > 0)) {
    forceReconnectOnce(args.clients, args.firedReconnectScenarios, "after_first_commit");
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

async function postJson<T = unknown>(baseUrl: string, path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrapApiEnvelope<T>(response);
}

async function getJson<T = unknown>(baseUrl: string, path: string): Promise<T> {
  const response = await fetchWithRetry(`${normalizeBaseUrl(baseUrl)}${path}`);
  return unwrapApiEnvelope<T>(response);
}

async function fetchWithRetry(url: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= DEFAULT_FETCH_RETRY_COUNT; attempt += 1) {
    try {
      return await fetch(url, init);
    } catch (error) {
      lastError = error;
      if (attempt >= DEFAULT_FETCH_RETRY_COUNT) {
        break;
      }
      await sleep(DEFAULT_FETCH_RETRY_DELAY_MS * (attempt + 1));
    }
  }
  throw lastError;
}

async function unwrapApiEnvelope<T>(response: Response): Promise<T> {
  const body = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || body.ok === false) {
    throw new ProtocolApiError(response.status, body.error ?? body);
  }
  return (body.data ?? body) as T;
}

function extractApiErrorCode(body: unknown): string {
  if (!isRecord(body)) {
    return "";
  }
  const code = body.code;
  if (typeof code === "string") {
    return code;
  }
  const error = body.error;
  if (isRecord(error) && typeof error.code === "string") {
    return error.code;
  }
  return "";
}

function normalizeBaseUrl(baseUrl: string): string {
  const trimmed = baseUrl.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return DEFAULT_BASE_URL;
  }
  return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
