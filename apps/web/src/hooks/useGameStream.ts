import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type {
  ConnectionStatus,
  InboundMessage,
} from "../core/contracts/stream";
import {
  gameStreamReducer,
  initialGameStreamState,
} from "../domain/store/gameStreamReducer";
import { fetchReplayMessages } from "../infra/http/replayClient";
import { StreamClient } from "../infra/ws/StreamClient";

type UseGameStreamArgs = {
  sessionId: string;
  token?: string;
  baseUrl?: string;
};

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
  }) => boolean;
} {
  const client = useMemo(() => new StreamClient(), []);
  const [state, dispatch] = useReducer(
    gameStreamReducer,
    initialGameStreamState,
  );
  const lastSeqRef = useRef(0);
  const activeStreamKeyRef = useRef("");
  const lastResumeRequestAtRef = useRef(0);
  const recoveryTimersRef = useRef<number[]>([]);

  useEffect(() => {
    const offMessage = client.onMessage((message) => {
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
    const offStatus = client.onStatus((next) =>
      dispatch({ type: "status", status: next }),
    );
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
      client.disconnect();
      dispatch({ type: "reset" });
      lastSeqRef.current = 0;
      activeStreamKeyRef.current = "";
      lastResumeRequestAtRef.current = 0;
      return;
    }
    const streamKey = `${normalized}\n${token ?? ""}`;
    if (activeStreamKeyRef.current !== streamKey) {
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
      void fetchReplayMessages({
        sessionId: normalized,
        token,
        baseUrl,
        signal,
        projectionSeqFloor: lastSeqRef.current,
      })
        .then((messages) => {
          for (const message of messages) {
            dispatch({ type: "message", message });
          }
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            return;
          }
          dispatch({ type: "status", status: "error" });
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
    return () => {
      for (const timer of recoveryTimersRef.current) {
        window.clearTimeout(timer);
      }
      recoveryTimersRef.current = [];
    };
  }, []);

  const sendDecision = (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
  }): boolean => {
    const sent = client.send({
      type: "decision",
      request_id: args.requestId,
      player_id: args.playerId,
      choice_id: args.choiceId,
      choice_payload: args.choicePayload,
      client_seq: lastSeqRef.current,
    });
    if (sent) {
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
