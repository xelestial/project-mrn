import type {
  ConnectionStatus,
  InboundMessage,
  OutboundMessage,
  ProtocolPlayerId,
  ViewCommitPayload,
} from "../core/contracts/stream";
import type {
  PromptChoiceViewModel,
  PromptViewModel,
} from "../domain/selectors/promptSelectors";
import {
  promptViewModelFromActivePromptPayload,
  selectActivePrompt,
} from "../domain/selectors/promptSelectors";
import {
  buildDecisionMessage,
  buildGameStreamKey,
  createDecisionRequestLedger,
} from "../domain/stream/decisionProtocol";
import {
  gameStreamReducer,
  initialGameStreamState,
  type GameStreamState,
} from "../domain/store/gameStreamReducer";
import {
  createFrontendWebSocket,
  parseFrontendWebSocketMessage,
  sendFrontendWebSocketMessage,
} from "../infra/ws/webSocketManager";

export type HeadlessPolicyDecision = {
  choiceId: string;
  choicePayload?: Record<string, unknown>;
};

export type HeadlessDecisionContext = {
  sessionId: string;
  playerId: number;
  prompt: PromptViewModel;
  legalChoices: PromptChoiceViewModel[];
  latestCommit: ViewCommitPayload | null;
  lastCommitSeq: number;
  messages: InboundMessage[];
};

export type DecisionPolicy = (
  context: HeadlessDecisionContext,
) => HeadlessPolicyDecision | Promise<HeadlessPolicyDecision>;

export type ResourceFocus = "cash" | "shard" | "score";

export type HeadlessMetrics = {
  inboundMessageCount: number;
  promptMessageCount: number;
  viewCommitCount: number;
  snapshotPulseCount: number;
  heartbeatCount: number;
  errorMessageCount: number;
  runtimeRecoveryRequiredCount: number;
  runtimeCompletedCount: number;
  nonMonotonicCommitCount: number;
  semanticCommitRegressionCount: number;
  outboundDecisionCount: number;
  decisionSendFailureCount: number;
  duplicateDecisionSuppressionCount: number;
  illegalActionCount: number;
  acceptedAckCount: number;
  rejectedAckCount: number;
  staleAckCount: number;
  staleDecisionRetryCount: number;
  unackedDecisionRetryCount: number;
  decisionTimeoutFallbackCount: number;
  rawPromptFallbackWithoutActiveCommitCount: number;
  spectatorPromptLeakCount: number;
  spectatorDecisionAckLeakCount: number;
  identityViolationCount: number;
  reconnectCount: number;
  forcedReconnectCount: number;
  reconnectRecoveryCount: number;
  reconnectRecoveryPendingCount: number;
  resumeRequestCount: number;
};

export type HeadlessTraceEvent = {
  event: string;
  ts_ms?: number;
  session_id: string;
  player_id: number;
  seq?: number;
  commit_seq?: number;
  request_id?: string;
  choice_id?: string;
  status?: string;
  reason?: string;
  payload?: Record<string, unknown>;
};

type PendingDecision = {
  requestId: string;
  decision: OutboundMessage;
  needsRetry: boolean;
  retryConsumed: boolean;
  retryAfterReconnect: boolean;
  sentAtMs: number;
  unackedRetryCount: number;
};

type PendingReconnectRecovery = {
  id: number;
  reason: string;
  minCommitSeq: number;
};

type PromptDecisionIdentity = {
  playerId: ProtocolPlayerId;
  legacyPlayerId?: number;
  publicPlayerId?: string;
  seatId?: string;
  viewerId?: string;
};

const DEFAULT_RAW_PROMPT_FALLBACK_DELAY_MS: number | null = null;
const DEFAULT_UNACKED_DECISION_RETRY_LIMIT = 2;

function promptDecisionIdentity(prompt: PromptViewModel, fallbackPlayerId: number): PromptDecisionIdentity {
  const legacyPlayerId =
    typeof prompt.legacyPlayerId === "number" && Number.isFinite(prompt.legacyPlayerId)
      ? Math.floor(prompt.legacyPlayerId)
      : Math.floor(fallbackPlayerId);
  const publicPlayerId = optionalIdentityString(prompt.publicPlayerId);
  const seatId = optionalIdentityString(prompt.seatId);
  const viewerId = optionalIdentityString(prompt.viewerId);
  const protocolPlayerId = publicPlayerId ?? prompt.protocolPlayerId ?? legacyPlayerId;
  const needsLegacyAlias = typeof protocolPlayerId === "string";
  return {
    playerId: protocolPlayerId,
    ...(needsLegacyAlias ? { legacyPlayerId } : {}),
    ...(publicPlayerId ? { publicPlayerId } : {}),
    ...(seatId ? { seatId } : {}),
    ...(viewerId ? { viewerId } : {}),
  };
}

function optionalIdentityString(value: string | null | undefined): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

type HeadlessGameClientArgs = {
  sessionId: string;
  token?: string;
  playerId: number;
  policy: DecisionPolicy;
  baseUrl?: string;
  failOnIllegal?: boolean;
  autoReconnect?: boolean;
  rawPromptFallbackDelayMs?: number | null;
};

export class IllegalHeadlessDecisionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IllegalHeadlessDecisionError";
  }
}

export const baselineDecisionPolicy: DecisionPolicy = ({ prompt }) => {
  if (prompt.requestType === "active_flip") {
    const finishChoice = prompt.choices.find((item) => item.choiceId === "none") ?? prompt.choices[0];
    const selectedChoiceIds = prompt.choices
      .map((item) => item.choiceId)
      .filter((choiceId) => choiceId && choiceId !== "none");
    if (finishChoice && selectedChoiceIds.length > 0) {
      return {
        choiceId: finishChoice.choiceId,
        choicePayload: {
          selected_choice_ids: selectedChoiceIds,
          finish_after_selection: true,
        },
      };
    }
  }
  if (prompt.requestType === "burden_exchange") {
    const declineChoice = prompt.choices.find((item) => item.choiceId === "no") ?? prompt.choices[0];
    return {
      choiceId: declineChoice?.choiceId ?? "",
      choicePayload: declineChoice?.value ?? undefined,
    };
  }
  const choice = prompt.choices.find((item) => !item.secondary) ?? prompt.choices[0];
  return {
    choiceId: choice?.choiceId ?? "",
    choicePayload: choice?.value ?? undefined,
  };
};

export const conservativeDecisionPolicy: DecisionPolicy = ({ prompt }) => {
  const preferred = prompt.choices.find((choice) => {
    const text = choiceSearchText(choice);
    return (
      choice.secondary ||
      choice.choiceId === "none" ||
      choice.choiceId === "pass" ||
      choice.choiceId === "skip" ||
      /\b(no|none|pass|skip)\b/.test(text) ||
      text.includes("안 함") ||
      text.includes("넘김") ||
      text.includes("종료")
    );
  });
  const choice = preferred ?? prompt.choices[0];
  return {
    choiceId: choice?.choiceId ?? "",
    choicePayload: choice?.value ?? undefined,
  };
};

export function createResourceFocusedDecisionPolicy(focus: ResourceFocus): DecisionPolicy {
  return (context) => {
    if (context.prompt.requestType === "active_flip") {
      return baselineDecisionPolicy(context);
    }
    const scoredChoices = context.prompt.choices
      .map((choice) => ({
        choice,
        score: resourceChoiceScore(choice, focus),
      }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score);
    const choice = scoredChoices[0]?.choice;
    if (choice) {
      return {
        choiceId: choice.choiceId,
        choicePayload: choice.value ?? undefined,
      };
    }
    return baselineDecisionPolicy(context);
  };
}

function resourceChoiceScore(choice: PromptChoiceViewModel, focus: ResourceFocus): number {
  const text = choiceSearchText(choice);
  const value = choice.value ?? {};
  const numericValue = (key: string): number => {
    const raw = value[key];
    return typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
  };
  if (focus === "cash") {
    return keywordScore(text, ["cash", "money", "coin", "coins", "냥", "돈", "엽전", "현금"]) +
      numericValue("cash_units") +
      numericValue("coin_units") +
      numericValue("coins");
  }
  if (focus === "shard") {
    return keywordScore(text, ["shard", "shards", "조각"]) + numericValue("shard_units") + numericValue("shards");
  }
  return keywordScore(text, ["score", "point", "points", "승점", "점수"]) +
    numericValue("score") +
    numericValue("points") +
    numericValue("point_units");
}

function keywordScore(text: string, keywords: string[]): number {
  return keywords.reduce((score, keyword) => score + (text.includes(keyword) ? 10 : 0), 0);
}

function choiceSearchText(choice: PromptChoiceViewModel): string {
  return [
    choice.choiceId,
    choice.title,
    choice.description,
    choice.value ? JSON.stringify(choice.value) : "",
  ]
    .join(" ")
    .toLowerCase();
}

export function emptyHeadlessMetrics(): HeadlessMetrics {
  return {
    inboundMessageCount: 0,
    promptMessageCount: 0,
    viewCommitCount: 0,
    snapshotPulseCount: 0,
    heartbeatCount: 0,
    errorMessageCount: 0,
    runtimeRecoveryRequiredCount: 0,
    runtimeCompletedCount: 0,
    nonMonotonicCommitCount: 0,
    semanticCommitRegressionCount: 0,
    outboundDecisionCount: 0,
    decisionSendFailureCount: 0,
    duplicateDecisionSuppressionCount: 0,
    illegalActionCount: 0,
    acceptedAckCount: 0,
    rejectedAckCount: 0,
    staleAckCount: 0,
    staleDecisionRetryCount: 0,
    unackedDecisionRetryCount: 0,
    decisionTimeoutFallbackCount: 0,
    rawPromptFallbackWithoutActiveCommitCount: 0,
    spectatorPromptLeakCount: 0,
    spectatorDecisionAckLeakCount: 0,
    identityViolationCount: 0,
    reconnectCount: 0,
    forcedReconnectCount: 0,
    reconnectRecoveryCount: 0,
    reconnectRecoveryPendingCount: 0,
    resumeRequestCount: 0,
  };
}

export function serializeHeadlessTraceEvent(event: HeadlessTraceEvent): string {
  return JSON.stringify(event);
}

export class HeadlessGameClient {
  readonly sessionId: string;
  readonly token?: string;
  readonly playerId: number;
  readonly metrics = emptyHeadlessMetrics();
  readonly trace: HeadlessTraceEvent[] = [];

  private readonly policy: DecisionPolicy;
  private readonly streamKey: string;
  private readonly baseUrl: string;
  private readonly failOnIllegal: boolean;
  private readonly autoReconnect: boolean;
  private readonly rawPromptFallbackDelayMs: number | null;
  private readonly decisionLedger = createDecisionRequestLedger();
  private readonly pendingByRequestId = new Map<string, PendingDecision>();
  private readonly inFlightDecisionRequestIds = new Set<string>();
  private readonly seenDecisionTimeoutFallbacks = new Set<string>();
  private readonly deferredRawPromptRequestIds = new Set<string>();
  private readonly pendingReconnectRecoveries: PendingReconnectRecovery[] = [];
  private readonly rawPromptFallbackTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private readonly activeFlipSelectionsByPhase = new Map<string, Set<string>>();
  private stateValue: GameStreamState = initialGameStreamState;
  private socket: WebSocket | null = null;
  private statusValue: ConnectionStatus = "idle";
  private closedByUser = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private nextReconnectRecoveryId = 1;

  constructor(args: HeadlessGameClientArgs) {
    this.sessionId = args.sessionId.trim();
    this.token = args.token;
    this.playerId = args.playerId;
    this.policy = args.policy;
    this.baseUrl = args.baseUrl ?? "http://127.0.0.1:9090";
    this.failOnIllegal = args.failOnIllegal ?? true;
    this.autoReconnect = args.autoReconnect ?? true;
    const configuredRawPromptFallbackDelay =
      args.rawPromptFallbackDelayMs === undefined
        ? DEFAULT_RAW_PROMPT_FALLBACK_DELAY_MS
        : args.rawPromptFallbackDelayMs;
    this.rawPromptFallbackDelayMs =
      typeof configuredRawPromptFallbackDelay === "number" && Number.isFinite(configuredRawPromptFallbackDelay)
        ? Math.max(0, Math.floor(configuredRawPromptFallbackDelay))
        : null;
    this.streamKey = buildGameStreamKey(this.sessionId, this.token);
  }

  get state(): GameStreamState {
    return this.stateValue;
  }

  get status(): ConnectionStatus {
    return this.statusValue;
  }

  async ingestMessage(message: InboundMessage): Promise<OutboundMessage[]> {
    this.recordInbound(message);
    this.stateValue = gameStreamReducer(this.stateValue, {
      type: "message",
      message,
    });
    if (message.type === "decision_ack") {
      this.handleDecisionAck(message);
      return [];
    }
    if (message.type === "prompt") {
      return this.maybeBuildDecisionForRawPrompt(promptViewModelFromActivePromptPayload(message.payload), message.seq);
    }
    if (message.type !== "view_commit" && message.type !== "snapshot_pulse") {
      return [];
    }
    return this.maybeBuildDecisionForActivePrompt();
  }

  connect(): void {
    if (!this.sessionId) {
      throw new Error("HeadlessGameClient requires a session id before connect().");
    }
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.closedByUser = false;
    this.clearReconnectTimer();
    this.setStatus("connecting");
    const socket = createFrontendWebSocket({
      baseUrl: this.baseUrl,
      sessionId: this.sessionId,
      token: this.token,
    });
    this.socket = socket;

    socket.addEventListener("open", () => {
      if (this.socket !== socket) {
        return;
      }
      this.setStatus("connected");
      this.sendResumeIfNeeded();
    });
    socket.addEventListener("close", () => {
      if (this.socket !== socket) {
        return;
      }
      this.socket = null;
      this.clearRawPromptFallbackTimers();
      this.setStatus("disconnected");
      if (!this.closedByUser && this.autoReconnect) {
        this.scheduleReconnect();
      }
    });
    socket.addEventListener("error", () => {
      if (this.socket === socket) {
        this.setStatus("error");
      }
    });
    socket.addEventListener("message", (event) => {
      void this.handleSocketMessage(event.data);
    });
  }

  disconnect(): void {
    this.closedByUser = true;
    this.clearReconnectTimer();
    this.clearRawPromptFallbackTimers();
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.setStatus("disconnected");
  }

  forceReconnect(reason: string): void {
    const minCommitSeq = Math.max(0, Math.floor(this.stateValue.lastCommitSeq));
    const recoveryId = this.nextReconnectRecoveryId;
    this.nextReconnectRecoveryId += 1;
    this.markPendingDecisionsForReconnectRetry(reason);
    this.pendingReconnectRecoveries.push({
      id: recoveryId,
      reason,
      minCommitSeq,
    });
    this.metrics.forcedReconnectCount += 1;
    this.metrics.reconnectRecoveryPendingCount = this.pendingReconnectRecoveries.length;
    this.recordTrace({
      event: "forced_reconnect",
      session_id: this.sessionId,
      player_id: this.playerId,
      commit_seq: this.stateValue.lastCommitSeq,
      reason,
      payload: {
        reconnect_recovery_id: recoveryId,
        min_commit_seq: minCommitSeq,
      },
    });
    if (!this.socket) {
      this.connect();
      return;
    }
    this.closedByUser = false;
    this.socket.close();
  }

  requestResume(): boolean {
    const message: OutboundMessage = {
      type: "resume",
      last_commit_seq: Math.max(0, Math.floor(this.stateValue.lastCommitSeq)),
    };
    const sent = this.send(message);
    if (sent) {
      this.metrics.resumeRequestCount += 1;
      this.recordTrace({
        event: "resume_sent",
        session_id: this.sessionId,
        player_id: this.playerId,
        commit_seq: message.last_commit_seq,
      });
    }
    return sent;
  }

  send(message: OutboundMessage): boolean {
    if (!this.socket) {
      return false;
    }
    return sendFrontendWebSocketMessage(this.socket, message);
  }

  markDecisionSendFailed(message: OutboundMessage): void {
    if (message.type !== "decision") {
      return;
    }
    const requestId = typeof message.request_id === "string" ? message.request_id : "";
    if (!requestId) {
      return;
    }
    this.decisionLedger.forget(this.streamKey, requestId);
    this.pendingByRequestId.delete(requestId);
    this.inFlightDecisionRequestIds.delete(requestId);
    this.metrics.decisionSendFailureCount += 1;
    this.recordTrace({
      event: "decision_send_failed",
      session_id: this.sessionId,
      player_id: this.playerId,
      commit_seq: this.stateValue.lastCommitSeq,
      request_id: requestId,
      choice_id: typeof message.choice_id === "string" ? message.choice_id : undefined,
    });
  }

  traceJsonl(): string {
    return this.trace.map(serializeHeadlessTraceEvent).join("\n");
  }

  private recordTrace(event: HeadlessTraceEvent): void {
    this.trace.push({
      ts_ms: Date.now(),
      ...event,
    });
  }

  private async handleSocketMessage(rawData: unknown): Promise<void> {
    try {
      const message = parseFrontendWebSocketMessage(rawData);
      const outboundMessages = await this.ingestMessage(message);
      for (const outbound of outboundMessages) {
        const sent = this.send(outbound);
        if (!sent) {
          this.markDecisionSendFailed(outbound);
        }
      }
    } catch (error) {
      this.metrics.errorMessageCount += 1;
      this.recordTrace({
        event: "headless_client_error",
        session_id: this.sessionId,
        player_id: this.playerId,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async maybeBuildDecisionForActivePrompt(): Promise<OutboundMessage[]> {
    return this.maybeBuildDecisionForPrompt(selectActivePrompt(this.stateValue.messages));
  }

  private async maybeBuildDecisionForRawPrompt(prompt: PromptViewModel | null, seq?: number): Promise<OutboundMessage[]> {
    if (!prompt || prompt.playerId !== this.playerId) {
      return [];
    }
    const activePrompt = selectActivePrompt(this.stateValue.messages);
    if (activePrompt && activePrompt.requestId !== prompt.requestId) {
      this.recordTrace({
        event: "prompt_deferred_due_active_mismatch",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        payload: {
          request_type: prompt.requestType,
          active_request_id: activePrompt.requestId,
        },
      });
      return [];
    }
    if (activePrompt?.requestId === prompt.requestId) {
      this.clearRawPromptFallbackTimer(prompt.requestId);
      this.deferredRawPromptRequestIds.delete(prompt.requestId);
      return this.maybeBuildDecisionForPrompt(activePrompt);
    }
    if (!this.deferredRawPromptRequestIds.has(prompt.requestId)) {
      this.deferredRawPromptRequestIds.add(prompt.requestId);
      this.recordTrace({
        event: "prompt_deferred_until_view_commit",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        payload: {
          request_type: prompt.requestType,
          fallback_delay_ms: this.rawPromptFallbackDelayMs,
        },
      });
      this.requestResume();
      if (this.rawPromptFallbackDelayMs !== null) {
        this.scheduleRawPromptFallback(prompt, seq);
      }
      return [];
    }
    this.recordTrace({
      event: "prompt_already_deferred_until_view_commit",
      session_id: this.sessionId,
      player_id: this.playerId,
      seq,
      commit_seq: this.stateValue.lastCommitSeq,
      request_id: prompt.requestId,
      payload: {
        request_type: prompt.requestType,
      },
    });
    return [];
  }

  private async maybeBuildDecisionForPrompt(prompt: PromptViewModel | null): Promise<OutboundMessage[]> {
    if (!prompt || prompt.playerId !== this.playerId) {
      return [];
    }

    const pending = this.pendingByRequestId.get(prompt.requestId);
    const retryingStalePrompt = pending?.needsRetry === true && !pending.retryConsumed;
    if (retryingStalePrompt) {
      this.decisionLedger.forget(this.streamKey, prompt.requestId);
    } else if (this.inFlightDecisionRequestIds.has(prompt.requestId)) {
      this.metrics.duplicateDecisionSuppressionCount += 1;
      this.recordTrace({
        event: "decision_suppressed_duplicate",
        session_id: this.sessionId,
        player_id: this.playerId,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
      });
      return [];
    } else if (!this.decisionLedger.shouldSend(this.streamKey, prompt.requestId)) {
      const unackedRetry = this.buildUnackedDecisionRetry(prompt, pending);
      if (unackedRetry) {
        return [unackedRetry];
      }
      this.metrics.duplicateDecisionSuppressionCount += 1;
      this.recordTrace({
        event: "decision_suppressed_duplicate",
        session_id: this.sessionId,
        player_id: this.playerId,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
      });
      return [];
    }

    this.inFlightDecisionRequestIds.add(prompt.requestId);
    try {
      const rawPolicyDecision = await this.policy({
        sessionId: this.sessionId,
        playerId: this.playerId,
        prompt,
        legalChoices: prompt.choices,
        latestCommit: this.stateValue.latestCommit,
        lastCommitSeq: this.stateValue.lastCommitSeq,
        messages: this.stateValue.messages,
      });
      const policyDecision = this.normalizePolicyDecisionForPrompt(prompt, rawPolicyDecision);
      const selectedChoice = prompt.choices.find((choice) => choice.choiceId === policyDecision.choiceId);
      if (!selectedChoice) {
        this.metrics.illegalActionCount += 1;
        this.recordTrace({
          event: "illegal_policy_choice",
          session_id: this.sessionId,
          player_id: this.playerId,
          commit_seq: this.stateValue.lastCommitSeq,
          request_id: prompt.requestId,
          choice_id: policyDecision.choiceId,
          payload: {
            legal_choice_ids: prompt.choices.map((choice) => choice.choiceId),
          },
        });
        if (this.failOnIllegal) {
          throw new IllegalHeadlessDecisionError(
            `Illegal headless decision '${policyDecision.choiceId}' for prompt '${prompt.requestId}'.`,
          );
        }
        return [];
      }

      const outbound = buildDecisionMessage({
        requestId: prompt.requestId,
        ...promptDecisionIdentity(prompt, this.playerId),
        choiceId: selectedChoice.choiceId,
        choicePayload: policyDecision.choicePayload ?? selectedChoice.value ?? undefined,
        continuation: prompt.continuation,
        viewCommitSeqSeen: this.stateValue.lastCommitSeq,
        clientSeq: this.stateValue.lastCommitSeq,
      });
      this.clearRawPromptFallbackTimer(prompt.requestId);
      this.decisionLedger.recordSent(this.streamKey, prompt.requestId);
      this.pendingByRequestId.set(prompt.requestId, {
        requestId: prompt.requestId,
        decision: outbound,
        needsRetry: false,
        retryConsumed: pending?.retryConsumed === true || retryingStalePrompt,
        retryAfterReconnect: false,
        sentAtMs: Date.now(),
        unackedRetryCount: pending?.unackedRetryCount ?? 0,
      });
      if (retryingStalePrompt) {
        this.metrics.staleDecisionRetryCount += 1;
      }
      this.recordPromptDecisionSideEffects(
        prompt,
        selectedChoice.choiceId,
        policyDecision.choicePayload ?? selectedChoice.value ?? undefined,
      );
      this.metrics.outboundDecisionCount += 1;
      this.recordTrace({
        event: retryingStalePrompt ? "decision_retry_sent" : "decision_sent",
        session_id: this.sessionId,
        player_id: this.playerId,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        choice_id: selectedChoice.choiceId,
        payload: compactPromptDecisionTracePayload(
          prompt,
          selectedChoice,
          this.stateValue.latestCommit,
          policyDecision.choicePayload ?? selectedChoice.value ?? undefined,
        ),
      });
      return [outbound];
    } finally {
      this.inFlightDecisionRequestIds.delete(prompt.requestId);
    }
  }

  private buildUnackedDecisionRetry(prompt: PromptViewModel, pending: PendingDecision | undefined): OutboundMessage | null {
    if (!pending || pending.decision.type !== "decision" || pending.needsRetry) {
      return null;
    }
    if (pending.unackedRetryCount >= DEFAULT_UNACKED_DECISION_RETRY_LIMIT) {
      return null;
    }
    const retryAfterReconnect = pending.retryAfterReconnect === true;
    if (!retryAfterReconnect) {
      return null;
    }
    const now = Date.now();
    const retryDecision: OutboundMessage = {
      ...pending.decision,
      view_commit_seq_seen: this.stateValue.lastCommitSeq,
      client_seq: this.stateValue.lastCommitSeq,
    };
    pending.decision = retryDecision;
    pending.sentAtMs = now;
    pending.retryAfterReconnect = false;
    pending.unackedRetryCount += 1;
    this.metrics.unackedDecisionRetryCount += 1;
    this.metrics.outboundDecisionCount += 1;
    this.recordTrace({
      event: "decision_unacked_retry_sent",
      session_id: this.sessionId,
      player_id: this.playerId,
      commit_seq: this.stateValue.lastCommitSeq,
      request_id: prompt.requestId,
      choice_id: retryDecision.choice_id,
      payload: {
        request_type: prompt.requestType,
        retry_count: pending.unackedRetryCount,
        retry_after_reconnect: retryAfterReconnect,
        legal_choice_ids: prompt.choices.map((choice) => choice.choiceId),
      },
    });
    return retryDecision;
  }

  private markPendingDecisionsForReconnectRetry(reason: string): void {
    for (const pending of this.pendingByRequestId.values()) {
      if (pending.decision.type !== "decision" || pending.needsRetry) {
        continue;
      }
      pending.retryAfterReconnect = true;
      this.recordTrace({
        event: "pending_decision_reconnect_retry_armed",
        session_id: this.sessionId,
        player_id: this.playerId,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: pending.requestId,
        reason,
        payload: {
          retry_count: pending.unackedRetryCount,
        },
      });
    }
  }

  private normalizePolicyDecisionForPrompt(
    prompt: PromptViewModel,
    policyDecision: HeadlessPolicyDecision,
  ): HeadlessPolicyDecision {
    if (prompt.requestType !== "active_flip") {
      return policyDecision;
    }
    const finishChoice = prompt.choices.find((choice) => choice.choiceId === "none");
    if (!finishChoice) {
      return policyDecision;
    }

    const phaseKey = activeFlipPhaseKey(this.sessionId, this.playerId, prompt);
    const localSelections = this.activeFlipSelectionsByPhase.get(phaseKey);
    const alreadyFlippedCount = activeFlipAlreadyFlippedCount(prompt.publicContext);
    const hasPriorSelection = alreadyFlippedCount > 0 || (localSelections?.size ?? 0) > 0;
    if (hasPriorSelection && policyDecision.choiceId !== finishChoice.choiceId) {
      this.recordTrace({
        event: "active_flip_guard_applied",
        session_id: this.sessionId,
        player_id: this.playerId,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        choice_id: finishChoice.choiceId,
        reason: "finish_after_prior_selection",
        payload: {
          original_choice_id: policyDecision.choiceId,
          already_flipped_count: alreadyFlippedCount,
          local_selected_count: localSelections?.size ?? 0,
          phase_key: phaseKey,
        },
      });
      return { choiceId: finishChoice.choiceId };
    }

    if (policyDecision.choiceId === finishChoice.choiceId && policyDecision.choicePayload === undefined) {
      const selectedChoiceIds = activeFlipSelectableChoiceIds(prompt);
      if (!hasPriorSelection && selectedChoiceIds.length > 0) {
        this.recordTrace({
          event: "active_flip_guard_applied",
          session_id: this.sessionId,
          player_id: this.playerId,
          commit_seq: this.stateValue.lastCommitSeq,
          request_id: prompt.requestId,
          choice_id: finishChoice.choiceId,
          reason: "batch_finish_payload_attached",
          payload: {
            selected_choice_ids_count: selectedChoiceIds.length,
            phase_key: phaseKey,
          },
        });
        return {
          choiceId: finishChoice.choiceId,
          choicePayload: {
            selected_choice_ids: selectedChoiceIds,
            finish_after_selection: true,
          },
        };
      }
    }

    return policyDecision;
  }

  private recordPromptDecisionSideEffects(
    prompt: PromptViewModel,
    choiceId: string,
    choicePayload: Record<string, unknown> | null | undefined,
  ): void {
    if (prompt.requestType !== "active_flip") {
      return;
    }
    const phaseKey = activeFlipPhaseKey(this.sessionId, this.playerId, prompt);
    const selectedChoiceIds = selectedActiveFlipChoiceIds(choiceId, choicePayload);
    if (selectedChoiceIds.length <= 0) {
      if (choiceId === "none") {
        this.activeFlipSelectionsByPhase.delete(phaseKey);
      }
      return;
    }
    let phaseSelections = this.activeFlipSelectionsByPhase.get(phaseKey);
    if (!phaseSelections) {
      phaseSelections = new Set<string>();
      this.activeFlipSelectionsByPhase.set(phaseKey, phaseSelections);
    }
    for (const selectedChoiceId of selectedChoiceIds) {
      phaseSelections.add(selectedChoiceId);
    }
    if (this.activeFlipSelectionsByPhase.size > 32) {
      const oldestKey = this.activeFlipSelectionsByPhase.keys().next().value;
      if (typeof oldestKey === "string") {
        this.activeFlipSelectionsByPhase.delete(oldestKey);
      }
    }
  }

  private handleDecisionAck(message: Extract<InboundMessage, { type: "decision_ack" }>): void {
    const requestId = typeof message.payload["request_id"] === "string" ? message.payload["request_id"] : "";
    const status = typeof message.payload["status"] === "string" ? message.payload["status"] : "";
    const reason = typeof message.payload["reason"] === "string" ? message.payload["reason"] : "";
    if (!requestId) {
      return;
    }
    if (status === "accepted") {
      this.metrics.acceptedAckCount += 1;
      this.pendingByRequestId.delete(requestId);
      this.deferredRawPromptRequestIds.delete(requestId);
      this.clearRawPromptFallbackTimer(requestId);
    } else if (status === "rejected") {
      this.metrics.rejectedAckCount += 1;
      this.deferredRawPromptRequestIds.delete(requestId);
      this.clearRawPromptFallbackTimer(requestId);
    } else if (status === "stale") {
      this.metrics.staleAckCount += 1;
      const pending = this.pendingByRequestId.get(requestId);
      if (pending && !pending.retryConsumed && isRetryableStaleReason(reason)) {
        pending.needsRetry = true;
      }
    }
    this.recordTrace({
      event: "decision_ack",
      session_id: this.sessionId,
      player_id: this.playerId,
      seq: message.seq,
      request_id: requestId,
      status,
      reason,
    });
  }

  private scheduleRawPromptFallback(prompt: PromptViewModel, seq?: number): void {
    if (this.rawPromptFallbackDelayMs === null) {
      return;
    }
    this.clearRawPromptFallbackTimer(prompt.requestId);
    const timer = setTimeout(() => {
      this.rawPromptFallbackTimers.delete(prompt.requestId);
      this.deferredRawPromptRequestIds.delete(prompt.requestId);
      void this.sendRawPromptFallbackDecision(prompt, seq);
    }, this.rawPromptFallbackDelayMs);
    this.rawPromptFallbackTimers.set(prompt.requestId, timer);
  }

  private async sendRawPromptFallbackDecision(prompt: PromptViewModel, seq?: number): Promise<void> {
    if (this.pendingByRequestId.has(prompt.requestId)) {
      return;
    }
    const activePrompt = selectActivePrompt(this.stateValue.messages);
    if (activePrompt && activePrompt.requestId !== prompt.requestId) {
      this.recordTrace({
        event: "prompt_fallback_skipped_due_active_mismatch",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        payload: {
          request_type: prompt.requestType,
          active_request_id: activePrompt.requestId,
        },
      });
      return;
    }
    if (activePrompt?.requestId !== prompt.requestId) {
      this.recordTrace({
        event: "prompt_fallback_skipped_missing_view_commit",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        payload: {
          request_type: prompt.requestType,
        },
      });
      this.requestResume();
      return;
    }
    this.recordTrace({
      event: "prompt_fallback_resolved_by_view_commit",
      session_id: this.sessionId,
      player_id: this.playerId,
      seq,
      commit_seq: this.stateValue.lastCommitSeq,
      request_id: prompt.requestId,
      payload: {
        request_type: prompt.requestType,
      },
    });
    try {
      const outboundMessages = await this.maybeBuildDecisionForPrompt(activePrompt);
      for (const outbound of outboundMessages) {
        const sent = this.send(outbound);
        if (!sent) {
          this.markDecisionSendFailed(outbound);
        }
      }
    } catch (error) {
      this.metrics.errorMessageCount += 1;
      this.recordTrace({
        event: "raw_prompt_fallback_error",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq,
        commit_seq: this.stateValue.lastCommitSeq,
        request_id: prompt.requestId,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private clearRawPromptFallbackTimer(requestId: string): void {
    const timer = this.rawPromptFallbackTimers.get(requestId);
    if (!timer) {
      return;
    }
    clearTimeout(timer);
    this.rawPromptFallbackTimers.delete(requestId);
  }

  private clearRawPromptFallbackTimers(): void {
    for (const timer of this.rawPromptFallbackTimers.values()) {
      clearTimeout(timer);
    }
    this.rawPromptFallbackTimers.clear();
    this.deferredRawPromptRequestIds.clear();
  }

  private recordInbound(message: InboundMessage): void {
    this.metrics.inboundMessageCount += 1;
    if (message.type === "prompt") {
      this.metrics.promptMessageCount += 1;
    }
    if (this.playerId === 0 && message.type === "prompt") {
      this.metrics.spectatorPromptLeakCount += 1;
      this.recordTrace({
        event: "spectator_private_prompt_leak",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq: message.seq,
        request_id: String(message.payload?.request_id ?? ""),
      });
    }
    if (this.playerId === 0 && message.type === "decision_ack") {
      this.metrics.spectatorDecisionAckLeakCount += 1;
      this.recordTrace({
        event: "spectator_private_decision_ack_leak",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq: message.seq,
        request_id: String(message.payload?.request_id ?? ""),
      });
    }
    if (message.type === "heartbeat") {
      this.metrics.heartbeatCount += 1;
      return;
    }
    this.recordDecisionTimeoutFallbacks(message);
    if (message.type === "error") {
      this.metrics.errorMessageCount += 1;
      this.recordTrace({
        event: "stream_error",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq: message.seq,
        payload: message.payload,
      });
      return;
    }
    if (message.type !== "view_commit" && message.type !== "snapshot_pulse") {
      return;
    }

    if (message.type === "view_commit") {
      this.metrics.viewCommitCount += 1;
      this.recordViewerIdentityViolations(message);
    } else {
      this.metrics.snapshotPulseCount += 1;
    }
    const commitSeq = Number(message.payload.commit_seq);
    if (Number.isFinite(commitSeq) && commitSeq < this.stateValue.lastCommitSeq) {
      this.metrics.nonMonotonicCommitCount += 1;
      this.recordTrace({
        event: "commit_seq_non_monotonic",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq: message.seq,
        commit_seq: commitSeq,
        payload: { previous_commit_seq: this.stateValue.lastCommitSeq },
      });
    }
    const previousCommit = this.stateValue.latestCommit;
    if (
      Number.isFinite(commitSeq) &&
      commitSeq > this.stateValue.lastCommitSeq &&
      previousCommit !== null &&
      isRuntimePositionRegression(previousCommit.runtime, message.payload.runtime)
    ) {
      this.metrics.semanticCommitRegressionCount += 1;
      this.recordTrace({
        event: "runtime_position_regressed",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq: message.seq,
        commit_seq: commitSeq,
        payload: {
          previous_commit_seq: previousCommit.commit_seq,
          previous_round_index: previousCommit.runtime.round_index,
          previous_turn_index: previousCommit.runtime.turn_index,
          round_index: message.payload.runtime.round_index,
          turn_index: message.payload.runtime.turn_index,
          runtime_status: message.payload.runtime.status,
          active_module_id: message.payload.runtime.active_module_id,
          active_module_type: message.payload.runtime.active_module_type,
        },
      });
    }
    if (message.payload.runtime.status === "recovery_required") {
      this.metrics.runtimeRecoveryRequiredCount += 1;
    }
    if (message.payload.runtime.status === "completed") {
      this.metrics.runtimeCompletedCount += 1;
    }
    this.recordReconnectRecovery(message, commitSeq);
    this.recordTrace({
      event: "view_commit_seen",
      session_id: this.sessionId,
      player_id: this.playerId,
      seq: message.seq,
      commit_seq: commitSeq,
      payload: compactViewCommitTracePayload(message),
    });
  }

  private recordReconnectRecovery(
    message: Extract<InboundMessage, { type: "view_commit" | "snapshot_pulse" }>,
    commitSeq: number,
  ): void {
    if (message.type !== "view_commit" || this.pendingReconnectRecoveries.length <= 0 || !Number.isFinite(commitSeq)) {
      return;
    }
    const recovered: PendingReconnectRecovery[] = [];
    const pending: PendingReconnectRecovery[] = [];
    for (const item of this.pendingReconnectRecoveries) {
      if (commitSeq >= item.minCommitSeq) {
        recovered.push(item);
      } else {
        pending.push(item);
      }
    }
    if (recovered.length <= 0) {
      return;
    }
    this.pendingReconnectRecoveries.length = 0;
    this.pendingReconnectRecoveries.push(...pending);
    this.metrics.reconnectRecoveryCount += recovered.length;
    this.metrics.reconnectRecoveryPendingCount = this.pendingReconnectRecoveries.length;
    for (const item of recovered) {
      this.recordTrace({
        event: "forced_reconnect_recovered",
        session_id: this.sessionId,
        player_id: this.playerId,
        seq: message.seq,
        commit_seq: commitSeq,
        reason: item.reason,
        payload: {
          reconnect_recovery_id: item.id,
          min_commit_seq: item.minCommitSeq,
        },
      });
    }
  }

  private recordViewerIdentityViolations(message: Extract<InboundMessage, { type: "view_commit" }>): void {
    const viewer = message.payload.viewer;
    if (!viewer || typeof viewer !== "object") {
      return;
    }
    const checks: Array<[string, unknown, string]> = [
      ["viewer_id", viewer.viewer_id, "string"],
      ["seat_id", viewer.seat_id, "string"],
      ["public_player_id", viewer.public_player_id, "string"],
      ["seat_index", viewer.seat_index, "number"],
    ];
    for (const [field, value, expectedType] of checks) {
      if (value === undefined || value === null) {
        continue;
      }
      if (typeof value !== expectedType) {
        this.metrics.identityViolationCount += 1;
        this.recordTrace({
          event: "viewer_identity_violation",
          session_id: this.sessionId,
          player_id: this.playerId,
          seq: message.seq,
          commit_seq: Number(message.payload.commit_seq),
          reason: `${field}_type`,
          payload: { field, expected_type: expectedType, actual_type: typeof value },
        });
      }
    }
  }

  private sendResumeIfNeeded(): void {
    if (this.stateValue.lastCommitSeq <= 0) {
      return;
    }
    this.requestResume();
  }

  private setStatus(status: ConnectionStatus): void {
    this.statusValue = status;
    this.stateValue = gameStreamReducer(this.stateValue, { type: "status", status });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return;
    }
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.metrics.reconnectCount += 1;
      this.connect();
    }, 100);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private recordDecisionTimeoutFallbacks(message: InboundMessage): void {
    const keys = collectDecisionTimeoutFallbackKeys(message);
    let newCount = 0;
    for (const key of keys) {
      if (this.seenDecisionTimeoutFallbacks.has(key)) {
        continue;
      }
      this.seenDecisionTimeoutFallbacks.add(key);
      newCount += 1;
    }
    if (newCount <= 0) {
      return;
    }
    this.metrics.decisionTimeoutFallbackCount += newCount;
    this.recordTrace({
      event: "decision_timeout_fallback_seen",
      session_id: this.sessionId,
      player_id: this.playerId,
      seq: message.seq,
      commit_seq:
        message.type === "view_commit" || message.type === "snapshot_pulse"
          ? Number(message.payload.commit_seq)
          : undefined,
      payload: {
        count: newCount,
      },
    });
  }
}

function isRetryableStaleReason(reason: string): boolean {
  const normalized = reason.toLowerCase();
  return (
    !normalized.includes("unauthorized") &&
    !normalized.includes("player_mismatch") &&
    !normalized.includes("player mismatch") &&
    !normalized.includes("already_resolved") &&
    !normalized.includes("already resolved") &&
    !normalized.includes("prompt_timeout") &&
    !normalized.includes("prompt timeout") &&
    !normalized.includes("superseded") &&
    !normalized.includes("final") &&
    !normalized.includes("terminal")
  );
}

function compactPromptDecisionTracePayload(
  prompt: PromptViewModel,
  selectedChoice: PromptChoiceViewModel,
  latestCommit: ViewCommitPayload | null,
  choicePayload: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  return {
    request_type: prompt.requestType,
    legal_choice_ids: prompt.choices.map((choice) => choice.choiceId),
    has_choice_payload: selectedChoice.value !== null,
    selected_choice_ids_count: Array.isArray(choicePayload?.["selected_choice_ids"])
      ? choicePayload["selected_choice_ids"].length
      : null,
    round_index: latestCommit?.runtime.round_index ?? null,
    turn_index: latestCommit?.runtime.turn_index ?? null,
    prompt_instance_id: prompt.continuation.promptInstanceId,
    frame_id: prompt.continuation.frameId,
    module_id: prompt.continuation.moduleId,
    module_type: prompt.continuation.moduleType,
  };
}

function activeFlipPhaseKey(sessionId: string, playerId: number, prompt: PromptViewModel): string {
  return [
    sessionId,
    playerId,
    prompt.continuation.frameId ?? "",
    prompt.continuation.moduleId ?? "",
    prompt.continuation.moduleCursor ?? "",
  ].join(":");
}

function activeFlipAlreadyFlippedCount(publicContext: Record<string, unknown>): number {
  const count = numberValue(publicContext["already_flipped_count"]) ?? 0;
  const cards = Array.isArray(publicContext["already_flipped_cards"]) ? publicContext["already_flipped_cards"].length : 0;
  return Math.max(0, Math.floor(Math.max(count, cards)));
}

function activeFlipSelectableChoiceIds(prompt: PromptViewModel): string[] {
  return prompt.choices
    .map((choice) => choice.choiceId)
    .filter((choiceId) => choiceId && choiceId !== "none");
}

function selectedActiveFlipChoiceIds(
  choiceId: string,
  choicePayload: Record<string, unknown> | null | undefined,
): string[] {
  const selectedChoiceIds = Array.isArray(choicePayload?.["selected_choice_ids"])
    ? choicePayload["selected_choice_ids"]
        .map((item) => (typeof item === "string" ? item : null))
        .filter((item): item is string => item !== null && item !== "none")
    : [];
  if (choiceId && choiceId !== "none") {
    return [choiceId, ...selectedChoiceIds.filter((item) => item !== choiceId)];
  }
  return selectedChoiceIds;
}

function compactViewCommitTracePayload(
  message: Extract<InboundMessage, { type: "view_commit" | "snapshot_pulse" }>,
): Record<string, unknown> {
  const prompt = isRecord(message.payload.view_state["prompt"]) ? message.payload.view_state["prompt"] : null;
  const active = isRecord(prompt?.["active"]) ? prompt["active"] : null;
  const activeRequestId = active?.["request_id"];
  const activePlayerId = active?.["player_id"];
  const activeRequestType = active?.["request_type"];
  return {
    stream_type: message.type,
    runtime_status: message.payload.runtime.status,
    round_index: message.payload.runtime.round_index,
    turn_index: message.payload.runtime.turn_index,
    active_module_id: message.payload.runtime.active_module_id,
    active_module_type: message.payload.runtime.active_module_type,
    active_prompt_request_id: typeof activeRequestId === "string" ? activeRequestId : null,
    active_prompt_player_id: typeof activePlayerId === "number" ? activePlayerId : null,
    active_prompt_request_type: typeof activeRequestType === "string" ? activeRequestType : null,
    player_summaries: compactPlayerSummaries(message.payload.view_state),
  };
}

function compactPlayerSummaries(viewState: Record<string, unknown>): Array<Record<string, unknown>> {
  const players = isRecord(viewState["players"]) ? viewState["players"] : null;
  const items = Array.isArray(players?.["items"])
    ? players["items"]
    : Array.isArray(viewState["players"])
      ? viewState["players"]
      : [];
  return items
    .filter(isRecord)
    .map((player) => ({
      player_id: numberValue(player["player_id"]),
      seat: numberValue(player["seat"]),
      character: stringValue(player["current_character_face"]) ?? stringValue(player["character"]),
      cash: numberValue(player["cash"]),
      score: numberValue(player["score"]),
      total_score: numberValue(player["total_score"]),
      shards: numberValue(player["shards"]),
      owned_tile_count: numberValue(player["owned_tile_count"]),
      position: numberValue(player["position"]),
      alive: typeof player["alive"] === "boolean" ? player["alive"] : null,
    }))
    .filter((player) => player.player_id !== null);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRuntimePositionRegression(
  previous: ViewCommitPayload["runtime"],
  next: ViewCommitPayload["runtime"],
): boolean {
  if (next.round_index < previous.round_index) {
    return true;
  }
  return next.round_index === previous.round_index && next.turn_index < previous.turn_index;
}

function collectDecisionTimeoutFallbackKeys(message: InboundMessage): string[] {
  const root =
    message.type === "view_commit" || message.type === "snapshot_pulse"
      ? message.payload.view_state
      : message.type === "event"
        ? message.payload
        : null;
  if (!root) {
    return [];
  }
  const keys: string[] = [];
  collectFallbackKeysFromValue(root, keys, `${message.type}:${message.seq}`, new WeakSet<object>());
  return keys;
}

function collectFallbackKeysFromValue(
  value: unknown,
  keys: string[],
  path: string,
  seen: WeakSet<object>,
): void {
  if (!isRecord(value) && !Array.isArray(value)) {
    return;
  }
  if (typeof value === "object" && value !== null) {
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => collectFallbackKeysFromValue(item, keys, `${path}.${index}`, seen));
    return;
  }
  const eventCode = stringValue(value["event_code"]) ?? stringValue(value["event_type"]);
  if (eventCode === "decision_timeout_fallback") {
    const nestedPayload = isRecord(value["payload"]) ? value["payload"] : {};
    const seq =
      numberValue(value["seq"]) ??
      numberValue(value["source_seq"]) ??
      numberValue(value["source_event_seq"]) ??
      numberValue(nestedPayload["seq"]) ??
      numberValue(nestedPayload["source_event_seq"]);
    const requestId = stringValue(value["request_id"]) ?? stringValue(nestedPayload["request_id"]);
    keys.push(seq !== null ? `seq:${seq}` : requestId ? `request:${requestId}` : `path:${path}`);
  }
  for (const [key, child] of Object.entries(value)) {
    collectFallbackKeysFromValue(child, keys, `${path}.${key}`, seen);
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
