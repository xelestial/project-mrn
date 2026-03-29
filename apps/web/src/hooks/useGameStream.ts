import { useEffect, useMemo, useReducer, useRef } from "react";
import type { ConnectionStatus, InboundMessage } from "../core/contracts/stream";
import { gameStreamReducer, initialGameStreamState } from "../domain/store/gameStreamReducer";
import { StreamClient } from "../infra/ws/StreamClient";

type UseGameStreamArgs = {
  sessionId: string;
  token?: string;
};

export function useGameStream({ sessionId, token }: UseGameStreamArgs): {
  status: ConnectionStatus;
  lastSeq: number;
  messages: InboundMessage[];
  sendDecision: (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
  }) => void;
} {
  const client = useMemo(() => new StreamClient(), []);
  const [state, dispatch] = useReducer(gameStreamReducer, initialGameStreamState);
  const lastSeqRef = useRef(0);
  const activeSessionRef = useRef("");

  useEffect(() => {
    const offMessage = client.onMessage((message) => {
      if (typeof message.seq === "number") {
        lastSeqRef.current = message.seq;
      }
      dispatch({ type: "message", message });
    });
    const offStatus = client.onStatus((next) => dispatch({ type: "status", status: next }));
    return () => {
      offMessage();
      offStatus();
      client.disconnect();
    };
  }, [client]);

  useEffect(() => {
    const normalized = sessionId.trim();
    if (!normalized) {
      client.disconnect();
      dispatch({ type: "reset" });
      lastSeqRef.current = 0;
      activeSessionRef.current = "";
      return;
    }
    if (activeSessionRef.current !== normalized) {
      lastSeqRef.current = 0;
      dispatch({ type: "reset" });
      activeSessionRef.current = normalized;
    }
    client.connect({ sessionId: normalized, token, onOpenResumeSeq: lastSeqRef.current });
    return () => client.disconnect();
  }, [client, sessionId, token]);

  const sendDecision = (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
  }) => {
    client.send({
      type: "decision",
      request_id: args.requestId,
      player_id: args.playerId,
      choice_id: args.choiceId,
      choice_payload: args.choicePayload,
      client_seq: lastSeqRef.current,
    });
  };

  return { status: state.status, messages: state.messages, lastSeq: state.lastSeq, sendDecision };
}
