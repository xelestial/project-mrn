import { useEffect, useMemo, useReducer, useRef } from "react";
import type {
  ConnectionStatus,
  InboundMessage,
} from "../core/contracts/stream";
import type { PromptContinuationViewModel } from "../domain/selectors/promptSelectors";
import {
  buildDecisionMessage,
  buildGameStreamKey,
  createDecisionRequestLedger,
} from "../domain/stream/decisionProtocol";
import {
  gameStreamReducer,
  initialGameStreamState,
} from "../domain/store/gameStreamReducer";
import { logFrontendDebugEvent } from "../infra/http/frontendDebugLogClient";
import { StreamClient } from "../infra/ws/StreamClient";

type UseGameStreamArgs = {
  sessionId: string;
  token?: string;
  baseUrl?: string;
};

export { buildDecisionMessage, buildGameStreamKey, createDecisionRequestLedger };

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
  const lastCommitSeqRef = useRef(0);
  const activeStreamKeyRef = useRef("");
  const logContextRef = useRef({ sessionId: "", baseUrl: "" });
  const decisionRequestLedgerRef = useRef(createDecisionRequestLedger());

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
    lastCommitSeqRef.current = state.lastCommitSeq;
    client.updateResumeCommitSeq(state.lastCommitSeq);
  }, [client, state.lastCommitSeq]);

  useEffect(() => {
    const normalized = sessionId.trim();
    if (!normalized) {
      client.disconnect();
      dispatch({ type: "reset" });
      lastCommitSeqRef.current = 0;
      activeStreamKeyRef.current = "";
      decisionRequestLedgerRef.current.clear();
      return;
    }
    const streamKey = buildGameStreamKey(normalized, token);
    if (activeStreamKeyRef.current !== streamKey) {
      lastCommitSeqRef.current = 0;
      dispatch({ type: "reset" });
      activeStreamKeyRef.current = streamKey;
      decisionRequestLedgerRef.current.clear();
    }
    client.connect({
      sessionId: normalized,
      token,
      onOpenResumeCommitSeq: lastCommitSeqRef.current,
      baseUrl,
    });
    return () => client.disconnect();
  }, [baseUrl, client, sessionId, token]);

  const sendDecision = (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
    continuation?: PromptContinuationViewModel;
  }): boolean => {
    const continuation = args.continuation;
    const streamKey = activeStreamKeyRef.current;
    if (streamKey && !decisionRequestLedgerRef.current.shouldSend(streamKey, args.requestId)) {
      logFrontendDebugEvent({
        event: "decision_suppressed_duplicate",
        sessionId: sessionId.trim(),
        seq: lastCommitSeqRef.current,
        baseUrl,
        payload: {
          request_id: args.requestId,
          player_id: args.playerId,
          choice_id: args.choiceId,
        },
      });
      return true;
    }
    const sent = client.send(
      buildDecisionMessage({
        requestId: args.requestId,
        playerId: args.playerId,
        choiceId: args.choiceId,
        choicePayload: args.choicePayload,
        continuation,
        viewCommitSeqSeen: lastCommitSeqRef.current,
        clientSeq: lastCommitSeqRef.current,
      }),
    );
    if (sent) {
      if (streamKey) {
        decisionRequestLedgerRef.current.recordSent(streamKey, args.requestId);
      }
      logFrontendDebugEvent({
        event: "decision_sent",
        sessionId: sessionId.trim(),
        seq: lastCommitSeqRef.current,
        baseUrl,
        payload: {
          request_id: args.requestId,
          player_id: args.playerId,
          choice_id: args.choiceId,
          choice_payload: args.choicePayload,
          continuation,
          view_commit_seq_seen: lastCommitSeqRef.current,
        },
      });
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
