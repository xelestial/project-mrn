import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export type ProtocolGateProgressArtifacts = {
  gameDir: string;
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

export type ProtocolGateChildProgress = {
  event?: string;
  reason?: string;
  session_id?: string;
  elapsed_ms?: number;
  idle_ms?: number;
  runtime_status?: string | null;
  pace?: {
    maxCommitSeq?: number;
    latestRoundIndex?: number | null;
    latestTurnIndex?: number | null;
    activePromptPlayerId?: number | null;
    activePromptRequestId?: string | null;
    activePromptRequestType?: string | null;
    latestDecisionRequestId?: string | null;
    latestAckStatus?: string | null;
    decisionsPerMinute?: number;
    acceptedAcksPerMinute?: number;
    slowestCommandLatencies?: Array<{
      requestId?: string;
      playerId?: number;
      requestType?: string | null;
      promptToDecisionMs?: number | null;
      decisionToAckMs?: number | null;
      totalMs?: number | null;
      status?: string | null;
    }>;
    pendingDecisionAges?: Array<{
      requestId?: string;
      playerId?: number;
      requestType?: string | null;
      ageMs?: number;
    }>;
  };
  completed?: boolean;
  timed_out?: boolean;
  progress_timeout_exceeded?: boolean;
  idle_timed_out?: boolean;
  trace_count?: number;
  seats?: Array<{
    player_id?: number;
    commit_seq?: number;
    accepted?: number;
    rejected?: number;
    stale?: number;
    errors?: number;
    fallbacks?: number;
    semantic_regressions?: number;
  }>;
};

export type ProtocolGateGameProgressRecord = {
  event: "protocol_gate_game_progress";
  game_id: number;
  session_id: string | null;
  elapsed_ms: number;
  elapsed_s: number;
  idle_ms: number;
  idle_s: number;
  runtime_status: string | null;
  round: number | null;
  turn: number | null;
  active_player_id: number | null;
  active_request_id: string | null;
  active_request_type: string | null;
  latest_commit_seq: number;
  command_count: number;
  accepted_count: number;
  stale_count: number;
  rejected_count: number;
  failed_count: number;
  fallback_count: number;
  max_command_ms: number | null;
  latest_decision_request_id: string | null;
  latest_ack_status: string | null;
  trace_count: number;
  artifacts: ProtocolGateProgressArtifacts;
};

export type ProtocolGateFailurePointer = {
  event: "protocol_gate_failure_pointer";
  failure_type: string;
  game_id: number;
  status: number;
  session_id: string | null;
  request_id: string | null;
  command_seq: number | null;
  commit_seq: number | null;
  elapsed_ms: number | null;
  runtime_status: string | null;
  failures: string[];
  log_hint: string;
  artifacts: ProtocolGateProgressArtifacts;
};

type ProtocolGateSummary = {
  ok?: boolean;
  session_id?: string;
  duration_ms?: number;
  runtime_status?: string | null;
  failures?: string[];
  timed_out?: boolean;
  progress_timeout_exceeded?: boolean;
  idle_timed_out?: boolean;
  backend_timing?: {
    maxCommandMs?: number;
    maxTransitionMs?: number;
    maxRedisCommitCount?: number;
    maxViewCommitCount?: number;
  } | null;
  protocol_latency?: {
    maxCommandMs?: number | null;
    offenders?: Array<{ requestId?: string }>;
  } | null;
  clients?: Record<
    string,
    {
      lastCommitSeq?: number;
      metrics?: {
        acceptedAckCount?: number;
        staleAckCount?: number;
        rejectedAckCount?: number;
        errorMessageCount?: number;
        decisionTimeoutFallbackCount?: number;
        semanticCommitRegressionCount?: number;
      };
    }
  >;
};

export function parseProtocolGateProgressLine(line: string): ProtocolGateChildProgress | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  let payload: unknown;
  try {
    payload = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (!isRecord(payload) || payload.event !== "protocol_gate_progress") {
    return null;
  }
  return payload as ProtocolGateChildProgress;
}

export function buildProtocolGateGameProgressRecord(args: {
  gameIndex: number;
  artifacts: ProtocolGateProgressArtifacts;
  progress: ProtocolGateChildProgress;
}): ProtocolGateGameProgressRecord {
  const seats = Array.isArray(args.progress.seats) ? args.progress.seats : [];
  const pace = isRecord(args.progress.pace) ? args.progress.pace : {};
  const slowestCommandLatencies = Array.isArray(pace.slowestCommandLatencies)
    ? pace.slowestCommandLatencies
    : [];
  return {
    event: "protocol_gate_game_progress",
    game_id: args.gameIndex,
    session_id: stringValue(args.progress.session_id),
    elapsed_ms: numberValue(args.progress.elapsed_ms) ?? 0,
    elapsed_s: roundSeconds(numberValue(args.progress.elapsed_ms) ?? 0),
    idle_ms: numberValue(args.progress.idle_ms) ?? 0,
    idle_s: roundSeconds(numberValue(args.progress.idle_ms) ?? 0),
    runtime_status: stringValue(args.progress.runtime_status),
    round: numberValue(pace.latestRoundIndex),
    turn: numberValue(pace.latestTurnIndex),
    active_player_id: numberValue(pace.activePromptPlayerId),
    active_request_id: stringValue(pace.activePromptRequestId),
    active_request_type: stringValue(pace.activePromptRequestType),
    latest_commit_seq: maxNumber(seats.map((seat) => numberValue(seat.commit_seq) ?? 0)),
    command_count: seats.reduce((sum, seat) => sum + (numberValue(seat.accepted) ?? 0), 0),
    accepted_count: seats.reduce((sum, seat) => sum + (numberValue(seat.accepted) ?? 0), 0),
    stale_count: seats.reduce((sum, seat) => sum + (numberValue(seat.stale) ?? 0), 0),
    rejected_count: seats.reduce((sum, seat) => sum + (numberValue(seat.rejected) ?? 0), 0),
    failed_count: seats.reduce(
      (sum, seat) => sum + (numberValue(seat.errors) ?? 0) + (numberValue(seat.semantic_regressions) ?? 0),
      0,
    ),
    fallback_count: seats.reduce((sum, seat) => sum + (numberValue(seat.fallbacks) ?? 0), 0),
    max_command_ms: maxNullable(
      slowestCommandLatencies.map((item) =>
        Math.max(
          numberValue(item.totalMs) ?? 0,
          numberValue(item.promptToDecisionMs) ?? 0,
          numberValue(item.decisionToAckMs) ?? 0,
        ),
      ),
    ),
    latest_decision_request_id: stringValue(pace.latestDecisionRequestId),
    latest_ack_status: stringValue(pace.latestAckStatus),
    trace_count: numberValue(args.progress.trace_count) ?? 0,
    artifacts: args.artifacts,
  };
}

export async function appendProtocolGateProgressRecord(
  record: ProtocolGateGameProgressRecord,
): Promise<void> {
  const line = `${JSON.stringify(record)}\n`;
  await ensureParentDir(record.artifacts.progressOut);
  await appendFile(record.artifacts.progressOut, line, "utf8");
}

export async function writeProtocolGateLatestProgressArtifacts(
  record: ProtocolGateGameProgressRecord,
): Promise<void> {
  const runStatus = {
    event: "protocol_gate_run_status",
    game_id: record.game_id,
    session_id: record.session_id,
    elapsed_ms: record.elapsed_ms,
    elapsed_s: record.elapsed_s,
    idle_ms: record.idle_ms,
    idle_s: record.idle_s,
    runtime_status: record.runtime_status,
    round: record.round,
    turn: record.turn,
    active_player_id: record.active_player_id,
    active_request_id: record.active_request_id,
    active_request_type: record.active_request_type,
    latest_commit_seq: record.latest_commit_seq,
    command_count: record.command_count,
    accepted_count: record.accepted_count,
    stale_count: record.stale_count,
    rejected_count: record.rejected_count,
    failed_count: record.failed_count,
    fallback_count: record.fallback_count,
    max_command_ms: record.max_command_ms,
    trace_count: record.trace_count,
    updated_at_ms: Date.now(),
  };
  const progressSummary = {
    event: "protocol_gate_progress_summary",
    game_id: record.game_id,
    session_id: record.session_id,
    elapsed_ms: record.elapsed_ms,
    runtime_status: record.runtime_status,
    round: record.round,
    turn: record.turn,
    active_player_id: record.active_player_id,
    active_request_id: record.active_request_id,
    active_request_type: record.active_request_type,
    latest_decision_request_id: record.latest_decision_request_id,
    latest_ack_status: record.latest_ack_status,
    latest_commit_seq: record.latest_commit_seq,
    command_count: record.command_count,
    stale_count: record.stale_count,
    rejected_count: record.rejected_count,
    failed_count: record.failed_count,
    fallback_count: record.fallback_count,
  };
  const slowestCommand = {
    event: "protocol_gate_slowest_command",
    game_id: record.game_id,
    session_id: record.session_id,
    max_command_ms: record.max_command_ms,
    active_request_id: record.active_request_id,
    active_request_type: record.active_request_type,
    latest_decision_request_id: record.latest_decision_request_id,
    latest_ack_status: record.latest_ack_status,
    elapsed_ms: record.elapsed_ms,
    round: record.round,
    turn: record.turn,
  };

  await Promise.all([
    writeJsonFile(record.artifacts.runStatusOut, runStatus),
    writeJsonFile(record.artifacts.progressSummaryOut, progressSummary),
    writeJsonFile(record.artifacts.slowestCommandOut, slowestCommand),
  ]);
}

export function formatProtocolGateProgressLine(record: ProtocolGateGameProgressRecord): string {
  return [
    "PROTOCOL_GATE_GAME_PROGRESS",
    `game=${record.game_id}`,
    `elapsed=${record.elapsed_s}s`,
    `idle=${record.idle_s}s`,
    `status=${record.runtime_status ?? "unknown"}`,
    `round=${record.round ?? "unknown"}`,
    `turn=${record.turn ?? "unknown"}`,
    `player=${record.active_player_id ?? "none"}`,
    `request=${record.active_request_type ?? "none"}`,
    `commit=${record.latest_commit_seq}`,
    `commands=${record.command_count}`,
    `stale=${record.stale_count}`,
    `rejected=${record.rejected_count}`,
    `failed=${record.failed_count}`,
    `fallback=${record.fallback_count}`,
    `max_command_ms=${record.max_command_ms ?? 0}`,
  ].join(" ");
}

export function formatProtocolGateFailurePointerLine(pointer: ProtocolGateFailurePointer): string {
  return [
    "PROTOCOL_GATE_FAILURE_POINTER",
    `game=${pointer.game_id}`,
    `type=${pointer.failure_type}`,
    `status=${pointer.status}`,
    `session=${pointer.session_id ?? "unknown"}`,
    `request_id=${pointer.request_id ?? "unknown"}`,
    `command_seq=${pointer.command_seq ?? "unknown"}`,
    `commit_seq=${pointer.commit_seq ?? "unknown"}`,
    `summary=${pointer.artifacts.summaryOut}`,
    `pointer=${pointer.artifacts.failurePointerOut}`,
  ].join(" ");
}

export async function buildProtocolGateFailurePointer(args: {
  gameIndex: number;
  status: number;
  artifacts: ProtocolGateProgressArtifacts;
  latestProgress?: ProtocolGateGameProgressRecord | null;
}): Promise<ProtocolGateFailurePointer> {
  const summary = await readProtocolGateSummary(args.artifacts.summaryOut);
  const failures = Array.isArray(summary?.failures) ? summary.failures.map(String) : [];
  const failureType = classifyFailureType({ status: args.status, summary, failures });
  const requestId = extractRequestId(failures) ?? args.latestProgress?.active_request_id ?? null;
  const commandSeq = extractNumber(failures, /command_seq=(\d+)/) ?? null;
  const commitSeq =
    extractNumber(failures, /(?:commit_seq|last_commit_seq|first_commit_seq)=(\d+)/) ??
    args.latestProgress?.latest_commit_seq ??
    maxClientCommitSeq(summary) ??
    null;
  return {
    event: "protocol_gate_failure_pointer",
    failure_type: failureType,
    game_id: args.gameIndex,
    status: args.status,
    session_id: stringValue(summary?.session_id) ?? args.latestProgress?.session_id ?? null,
    request_id: requestId,
    command_seq: commandSeq,
    commit_seq: commitSeq,
    elapsed_ms: numberValue(summary?.duration_ms) ?? args.latestProgress?.elapsed_ms ?? null,
    runtime_status: stringValue(summary?.runtime_status) ?? args.latestProgress?.runtime_status ?? null,
    failures,
    log_hint: buildLogHint(args.artifacts, requestId, commandSeq, commitSeq),
    artifacts: args.artifacts,
  };
}

export async function writeProtocolGateFailurePointer(pointer: ProtocolGateFailurePointer): Promise<void> {
  await writeJsonFile(pointer.artifacts.failurePointerOut, pointer);
}

export async function writeProtocolGateFailureSummaryArtifacts(pointer: ProtocolGateFailurePointer): Promise<void> {
  const failureReason = {
    event: "protocol_gate_failure_reason",
    failure_type: pointer.failure_type,
    game_id: pointer.game_id,
    status: pointer.status,
    session_id: pointer.session_id,
    request_id: pointer.request_id,
    command_seq: pointer.command_seq,
    commit_seq: pointer.commit_seq,
    elapsed_ms: pointer.elapsed_ms,
    runtime_status: pointer.runtime_status,
    failures: pointer.failures,
    log_hint: pointer.log_hint,
  };
  const suspectEvents = {
    event: "protocol_gate_suspect_events",
    failure_type: pointer.failure_type,
    game_id: pointer.game_id,
    session_id: pointer.session_id,
    request_id: pointer.request_id,
    command_seq: pointer.command_seq,
    commit_seq: pointer.commit_seq,
    raw_logs: {
      backend: pointer.artifacts.backendLogOut,
      protocol: pointer.artifacts.protocolLogOut,
      progress: pointer.artifacts.progressOut,
    },
    summary: pointer.artifacts.summaryOut,
    failure_reason: pointer.artifacts.failureReasonOut,
    pointer: pointer.artifacts.failurePointerOut,
  };
  const logOffsets = {
    event: "protocol_gate_log_offsets",
    game_id: pointer.game_id,
    session_id: pointer.session_id,
    request_id: pointer.request_id,
    command_seq: pointer.command_seq,
    commit_seq: pointer.commit_seq,
    strategy: "search raw logs by request_id, command_seq, then commit_seq; do not load full raw logs into chat context",
  };
  await Promise.all([
    writeJsonFile(pointer.artifacts.failureReasonOut, failureReason),
    writeJsonFile(pointer.artifacts.suspectEventsOut, suspectEvents),
    writeJsonFile(pointer.artifacts.logOffsetsOut, logOffsets),
  ]);
}

export async function writeProtocolGateGateResultArtifacts(args: {
  gameIndex: number;
  status: number;
  artifacts: ProtocolGateProgressArtifacts;
  latestProgress?: ProtocolGateGameProgressRecord | null;
}): Promise<void> {
  const summary = await readProtocolGateSummary(args.artifacts.summaryOut);
  const failures = Array.isArray(summary?.failures) ? summary.failures.map(String) : [];
  const sessionId = stringValue(summary?.session_id) ?? args.latestProgress?.session_id ?? null;
  const gateResult = {
    event: "protocol_gate_result",
    ok: args.status === 0 && (summary?.ok ?? failures.length === 0),
    status: args.status,
    game_id: args.gameIndex,
    session_id: sessionId,
    duration_ms: numberValue(summary?.duration_ms) ?? args.latestProgress?.elapsed_ms ?? null,
    runtime_status: stringValue(summary?.runtime_status) ?? args.latestProgress?.runtime_status ?? null,
    failures,
    summary: args.artifacts.summaryOut,
    raw_logs: {
      backend: args.artifacts.backendLogOut,
      protocol: args.artifacts.protocolLogOut,
      progress: args.artifacts.progressOut,
    },
    pointers: {
      failure_pointer: args.artifacts.failurePointerOut,
      suspect_events: args.artifacts.suspectEventsOut,
      log_offsets: args.artifacts.logOffsetsOut,
    },
  };
  const backendTiming = summary?.backend_timing ?? null;
  const slowestTransition = {
    event: "protocol_gate_slowest_transition",
    game_id: args.gameIndex,
    session_id: sessionId,
    max_transition_ms: numberValue(backendTiming?.maxTransitionMs),
    max_command_ms: numberValue(backendTiming?.maxCommandMs),
    max_redis_commit_count: numberValue(backendTiming?.maxRedisCommitCount),
    max_view_commit_count: numberValue(backendTiming?.maxViewCommitCount),
    backend_log: args.artifacts.backendLogOut,
    summary: args.artifacts.summaryOut,
  };
  await Promise.all([
    writeJsonFile(args.artifacts.gateResultOut, gateResult),
    writeJsonFile(args.artifacts.slowestTransitionOut, slowestTransition),
  ]);
}

function classifyFailureType(args: {
  status: number;
  summary: ProtocolGateSummary | null;
  failures: string[];
}): string {
  const text = args.failures.join("\n");
  if (args.summary?.timed_out) {
    return "timeout";
  }
  if (args.summary?.progress_timeout_exceeded || args.summary?.idle_timed_out) {
    return "idle_or_progress_timeout";
  }
  if (text.includes("repeated active prompt signature")) {
    return "prompt_repetition";
  }
  if (text.includes("backend command") || text.includes("backend transition")) {
    return "backend_timing";
  }
  if (text.includes("protocol command latency")) {
    return "protocol_latency";
  }
  if (text.includes("stale decision ack")) {
    return "stale_ack";
  }
  if (text.includes("rejected decision ack")) {
    return "rejected_ack";
  }
  if (args.status === 130) {
    return "aborted_by_fail_fast";
  }
  return "protocol_gate_failure";
}

async function readProtocolGateSummary(path: string): Promise<ProtocolGateSummary | null> {
  let text: string;
  try {
    text = await readFile(path, "utf8");
  } catch {
    return null;
  }
  try {
    const parsed = JSON.parse(text) as unknown;
    return isRecord(parsed) ? parsed as ProtocolGateSummary : null;
  } catch {
    return null;
  }
}

function buildLogHint(
  artifacts: ProtocolGateProgressArtifacts,
  requestId: string | null,
  commandSeq: number | null,
  commitSeq: number | null,
): string {
  const probes = [
    requestId ? `request_id=${requestId}` : null,
    commandSeq !== null ? `command_seq=${commandSeq}` : null,
    commitSeq !== null ? `commit_seq=${commitSeq}` : null,
  ].filter((value): value is string => value !== null);
  const probeText = probes.length > 0 ? probes.join(" OR ") : "failure text from summary.json";
  return `Inspect ${artifacts.summaryOut} first, then search ${artifacts.protocolLogOut}, ${artifacts.progressOut}, and ${artifacts.backendLogOut} for ${probeText}.`;
}

function extractRequestId(failures: string[]): string | null {
  return extractText(failures, /request_ids=([^\s,]+)/) ??
    extractText(failures, /request_id=([^\s,]+)/) ??
    null;
}

function extractNumber(failures: string[], pattern: RegExp): number | null {
  const value = extractText(failures, pattern);
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function extractText(failures: string[], pattern: RegExp): string | null {
  for (const failure of failures) {
    const match = failure.match(pattern);
    if (match?.[1]) {
      return match[1];
    }
  }
  return null;
}

function maxClientCommitSeq(summary: ProtocolGateSummary | null): number | null {
  const clients = summary?.clients;
  if (!clients) {
    return null;
  }
  return maxNullable(Object.values(clients).map((client) => numberValue(client.lastCommitSeq) ?? 0));
}

function roundSeconds(ms: number): number {
  return Math.round((ms / 1_000) * 10) / 10;
}

function maxNumber(values: number[]): number {
  return values.reduce((max, value) => Math.max(max, value), 0);
}

function maxNullable(values: number[]): number | null {
  const finite = values.filter((value) => Number.isFinite(value));
  return finite.length > 0 ? maxNumber(finite) : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function writeJsonFile(path: string, value: unknown): Promise<void> {
  await ensureParentDir(path);
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function ensureParentDir(path: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
}
