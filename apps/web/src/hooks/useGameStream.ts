import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type {
  ConnectionStatus,
  InboundMessage,
} from "../core/contracts/stream";
import type { PromptContinuationViewModel } from "../domain/selectors/promptSelectors";
import {
  gameStreamReducer,
  initialGameStreamState,
} from "../domain/store/gameStreamReducer";
import { fetchReplayMessages } from "../infra/http/replayClient";
import { logFrontendDebugEvent } from "../infra/http/frontendDebugLogClient";
import { StreamClient } from "../infra/ws/StreamClient";

type UseGameStreamArgs = {
  sessionId: string;
  token?: string;
  baseUrl?: string;
};

export function buildGameStreamKey(sessionId: string, token?: string): string {
  return `${sessionId.trim()}\n${token ?? ""}`;
}

export function shouldApplyReplayResponse(
  requestedStreamKey: string,
  activeStreamKey: string,
  signal?: AbortSignal,
): boolean {
  return requestedStreamKey === activeStreamKey && !signal?.aborted;
}

export function useGameStream({
  sessionId,
  token,
  baseUrl,
}: UseGameStreamArgs): {
  status: ConnectionStatus;
  lastSeq: number;
  messages: InboundMessage[];
  debugMessages: InboundMessage[];
  sendDecision: (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
    continuation?: PromptContinuationViewModel;
  }) => boolean;
} {
  const client = useMemo(() => new StreamClient(), []);
  const [state, dispatch] = useReducer(
    gameStreamReducer,
    initialGameStreamState,
  );
  const lastSeqRef = useRef(0);
  const activeStreamKeyRef = useRef("");
  const logContextRef = useRef({ sessionId: "", baseUrl: "" });
  const lastResumeRequestAtRef = useRef(0);
  const recoveryTimersRef = useRef<number[]>([]);
  const replayAbortControllersRef = useRef<AbortController[]>([]);

  const clearRecoveryTimers = useCallback(() => {
    for (const timer of recoveryTimersRef.current) {
      window.clearTimeout(timer);
    }
    recoveryTimersRef.current = [];
  }, []);

  const abortReplayRecoveries = useCallback(() => {
    for (const controller of replayAbortControllersRef.current) {
      controller.abort();
    }
    replayAbortControllersRef.current = [];
  }, []);

  const cancelRecoveryWork = useCallback(() => {
    clearRecoveryTimers();
    abortReplayRecoveries();
  }, [abortReplayRecoveries, clearRecoveryTimers]);

  useEffect(() => {
    logContextRef.current = {
      sessionId: sessionId.trim(),
      baseUrl: baseUrl ?? "",
    };
  }, [baseUrl, sessionId]);

  useEffect(() => {
    const offMessage = client.onMessage((message) => {
      logFrontendDebugEvent({
        event: "stream_message",
        sessionId: message.session_id || logContextRef.current.sessionId,
        seq: message.seq,
        baseUrl: logContextRef.current.baseUrl,
        payload: {
          type: message.type,
          payload: message.payload,
          server_time_ms: message.server_time_ms,
        },
      });
      if (typeof message.seq === "number") {
        const expected = lastSeqRef.current + 1;
        if (message.seq > expected) {
          const now = Date.now();
          if (now - lastResumeRequestAtRef.current > 1000) {
            lastResumeRequestAtRef.current = now;
            client.requestResume(lastSeqRef.current);
          }
        }
      }
      dispatch({ type: "message", message });
    });
    const offStatus = client.onStatus((next) => {
      logFrontendDebugEvent({
        event: "stream_status",
        sessionId: logContextRef.current.sessionId,
        baseUrl: logContextRef.current.baseUrl,
        payload: { status: next },
      });
      dispatch({ type: "status", status: next });
    });
    return () => {
      offMessage();
      offStatus();
      client.disconnect();
    };
  }, [client]);

  useEffect(() => {
    lastSeqRef.current = state.lastSeq;
  }, [state.lastSeq]);

  useEffect(() => {
    const normalized = sessionId.trim();
    if (!normalized) {
      cancelRecoveryWork();
      client.disconnect();
      dispatch({ type: "reset" });
      lastSeqRef.current = 0;
      activeStreamKeyRef.current = "";
      lastResumeRequestAtRef.current = 0;
      return;
    }
    const streamKey = buildGameStreamKey(normalized, token);
    if (activeStreamKeyRef.current !== streamKey) {
      cancelRecoveryWork();
      lastSeqRef.current = 0;
      dispatch({ type: "reset" });
      activeStreamKeyRef.current = streamKey;
      lastResumeRequestAtRef.current = 0;
    }
    client.connect({
      sessionId: normalized,
      token,
      onOpenResumeSeq: lastSeqRef.current,
      baseUrl,
    });
    return () => client.disconnect();
  }, [baseUrl, client, sessionId, token]);

  const recoverFromReplay = useCallback(
    (signal?: AbortSignal) => {
      const normalized = sessionId.trim();
      if (!normalized) {
        return;
      }
      const requestedStreamKey = buildGameStreamKey(normalized, token);
      if (activeStreamKeyRef.current !== requestedStreamKey) {
        return;
      }
      const ownedController = signal ? null : new AbortController();
      const requestSignal = signal ?? ownedController?.signal;
      if (ownedController) {
        replayAbortControllersRef.current.push(ownedController);
      }
      void fetchReplayMessages({
        sessionId: normalized,
        token,
        baseUrl,
        signal: requestSignal,
        projectionSeqFloor: lastSeqRef.current,
      })
        .then((messages) => {
          if (
            !shouldApplyReplayResponse(
              requestedStreamKey,
              activeStreamKeyRef.current,
              requestSignal,
            )
          ) {
            return;
          }
          for (const message of messages) {
            dispatch({ type: "message", message });
          }
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            return;
          }
          if (
            !shouldApplyReplayResponse(
              requestedStreamKey,
              activeStreamKeyRef.current,
              requestSignal,
            )
          ) {
            return;
          }
          dispatch({ type: "status", status: "error" });
        })
        .finally(() => {
          if (!ownedController) {
            return;
          }
          replayAbortControllersRef.current = replayAbortControllersRef.current.filter(
            (controller) => controller !== ownedController,
          );
        });
    },
    [baseUrl, sessionId, token],
  );

  useEffect(() => {
    const normalized = sessionId.trim();
    if (!normalized) {
      return;
    }
    const controller = new AbortController();
    recoverFromReplay(controller.signal);
    return () => controller.abort();
  }, [recoverFromReplay, sessionId]);

  useEffect(() => {
    return cancelRecoveryWork;
  }, [cancelRecoveryWork]);

  const sendDecision = (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
    continuation?: PromptContinuationViewModel;
  }): boolean => {
    const continuation = args.continuation;
    const sent = client.send({
      type: "decision",
      request_id: args.requestId,
      player_id: args.playerId,
      choice_id: args.choiceId,
      choice_payload: args.choicePayload,
      ...(continuation?.resumeToken ? { resume_token: continuation.resumeToken } : {}),
      ...(continuation?.frameId ? { frame_id: continuation.frameId } : {}),
      ...(continuation?.moduleId ? { module_id: continuation.moduleId } : {}),
      ...(continuation?.moduleType ? { module_type: continuation.moduleType } : {}),
      ...(continuation?.batchId ? { batch_id: continuation.batchId } : {}),
      client_seq: lastSeqRef.current,
    });
    if (sent) {
      logFrontendDebugEvent({
        event: "decision_sent",
        sessionId: sessionId.trim(),
        seq: lastSeqRef.current,
        baseUrl,
        payload: {
          request_id: args.requestId,
          player_id: args.playerId,
          choice_id: args.choiceId,
          choice_payload: args.choicePayload,
          continuation,
        },
      });
      for (const delay of [750, 2000, 5000, 10000, 15000, 30000]) {
        const timer = window.setTimeout(() => {
          recoveryTimersRef.current = recoveryTimersRef.current.filter(
            (item) => item !== timer,
          );
          recoverFromReplay();
        }, delay);
        recoveryTimersRef.current.push(timer);
      }
    }
    return sent;
  };

  return {
    status: state.status,
    messages: state.messages,
    debugMessages: state.debugMessages,
    lastSeq: state.lastSeq,
    sendDecision,
  };
}
