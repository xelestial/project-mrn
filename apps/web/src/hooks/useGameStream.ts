import { useEffect, useMemo, useReducer, useRef } from "react";
import type {
  ConnectionStatus,
  InboundMessage,
  ProtocolPlayerId,
} from "../core/contracts/stream";
import type { PromptContinuationViewModel, PromptIdentitySource } from "../domain/selectors/promptSelectors";
import {
  buildDecisionFlightKey,
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
export { buildDecisionFlightKey };

export type StreamDecisionArgs = {
  requestId: string;
  playerId: ProtocolPlayerId;
  primaryPlayerId?: ProtocolPlayerId | null;
  primaryPlayerIdSource?: PromptIdentitySource | null;
  legacyPlayerId?: number | null;
  publicPlayerId?: string | null;
  seatId?: string | null;
  viewerId?: string | null;
  requestType?: string;
  choiceId: string;
  choicePayload?: Record<string, unknown>;
  continuation?: PromptContinuationViewModel;
};

export type StreamDecisionFlightIdentity = {
  playerId: ProtocolPlayerId;
  source: PromptIdentitySource;
  legacyPlayerId: number | null;
  publicPlayerId: string | null;
};

export function resolveDecisionFlightIdentity(args: {
  playerId: ProtocolPlayerId;
  primaryPlayerId?: ProtocolPlayerId | null;
  primaryPlayerIdSource?: PromptIdentitySource | null;
  legacyPlayerId?: number | null;
  publicPlayerId?: string | null;
}): StreamDecisionFlightIdentity | null {
  const publicPlayerId = optionalDecisionIdentityString(args.publicPlayerId);
  const legacyPlayerId =
    typeof args.legacyPlayerId === "number" && Number.isFinite(args.legacyPlayerId)
      ? Math.floor(args.legacyPlayerId)
      : null;
  const explicitPrimary = explicitDecisionFlightIdentity(args.primaryPlayerId, args.primaryPlayerIdSource);
  if (explicitPrimary !== null) {
    return {
      ...explicitPrimary,
      legacyPlayerId,
      publicPlayerId,
    };
  }
  if (publicPlayerId !== null) {
    return {
      playerId: publicPlayerId,
      source: "public",
      legacyPlayerId,
      publicPlayerId,
    };
  }
  if (typeof args.playerId === "string" && args.playerId.trim()) {
    return {
      playerId: args.playerId.trim(),
      source: "protocol",
      legacyPlayerId,
      publicPlayerId: null,
    };
  }
  if (typeof args.playerId === "number" && Number.isFinite(args.playerId)) {
    return {
      playerId: Math.floor(args.playerId),
      source: "legacy",
      legacyPlayerId: Math.floor(args.playerId),
      publicPlayerId: null,
    };
  }
  if (legacyPlayerId !== null) {
    return {
      playerId: legacyPlayerId,
      source: "legacy",
      legacyPlayerId,
      publicPlayerId: null,
    };
  }
  return null;
}

function explicitDecisionFlightIdentity(
  playerId: ProtocolPlayerId | null | undefined,
  source: PromptIdentitySource | null | undefined,
): Pick<StreamDecisionFlightIdentity, "playerId" | "source"> | null {
  if (source !== "public" && source !== "protocol" && source !== "legacy") {
    return null;
  }
  if (typeof playerId === "number" && Number.isFinite(playerId)) {
    return source === "legacy"
      ? {
          playerId: Math.floor(playerId),
          source,
        }
      : null;
  }
  if (typeof playerId === "string" && playerId.trim()) {
    return {
      playerId: playerId.trim(),
      source,
    };
  }
  return null;
}

function optionalDecisionIdentityString(value: string | null | undefined): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
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
  sendDecision: (args: StreamDecisionArgs) => boolean;
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
    if (activeStreamKeyRef.current) {
      decisionRequestLedgerRef.current.releaseFlightsForStream(activeStreamKeyRef.current);
    }
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

  const sendDecision = (args: StreamDecisionArgs): boolean => {
    const continuation = args.continuation;
    const streamKey = activeStreamKeyRef.current;
    const flightIdentity = resolveDecisionFlightIdentity({
      playerId: args.playerId,
      primaryPlayerId: args.primaryPlayerId,
      primaryPlayerIdSource: args.primaryPlayerIdSource,
      legacyPlayerId: args.legacyPlayerId,
      publicPlayerId: args.publicPlayerId,
    });
    if (flightIdentity === null) {
      logFrontendDebugEvent({
        event: "decision_suppressed_invalid_player_identity",
        sessionId: sessionId.trim(),
        seq: lastCommitSeqRef.current,
        baseUrl,
        payload: {
          request_id: args.requestId,
          player_id: args.playerId,
          choice_id: args.choiceId,
        },
      });
      return false;
    }
    const flightKey = buildDecisionFlightKey({
      requestId: args.requestId,
      playerId: flightIdentity.playerId,
      requestType: args.requestType,
      continuation,
    });
    if (streamKey) {
      const flight = decisionRequestLedgerRef.current.beginFlight(streamKey, flightKey, args.requestId);
      if (flight.status === "duplicate") {
        logFrontendDebugEvent({
          event: "decision_suppressed_duplicate",
          sessionId: sessionId.trim(),
          seq: lastCommitSeqRef.current,
          baseUrl,
          payload: {
            request_id: args.requestId,
            player_id: args.playerId,
            primary_player_id: flightIdentity.playerId,
            primary_player_id_source: flightIdentity.source,
            choice_id: args.choiceId,
            flight_key: flightKey,
          },
        });
        return true;
      }
      if (flight.status === "busy") {
        logFrontendDebugEvent({
          event: "decision_suppressed_busy",
          sessionId: sessionId.trim(),
          seq: lastCommitSeqRef.current,
          baseUrl,
          payload: {
            request_id: args.requestId,
            active_request_id: flight.requestId,
            player_id: args.playerId,
            primary_player_id: flightIdentity.playerId,
            primary_player_id_source: flightIdentity.source,
            choice_id: args.choiceId,
            flight_key: flightKey,
          },
        });
        return true;
      }
    }
    if (streamKey && !decisionRequestLedgerRef.current.shouldSend(streamKey, args.requestId)) {
      logFrontendDebugEvent({
        event: "decision_suppressed_duplicate",
        sessionId: sessionId.trim(),
        seq: lastCommitSeqRef.current,
        baseUrl,
        payload: {
          request_id: args.requestId,
          player_id: args.playerId,
          primary_player_id: flightIdentity.playerId,
          primary_player_id_source: flightIdentity.source,
          choice_id: args.choiceId,
        },
      });
      return true;
    }
    const sent = client.send(
      buildDecisionMessage({
        requestId: args.requestId,
        playerId: args.playerId,
        primaryPlayerId: args.primaryPlayerId,
        primaryPlayerIdSource: args.primaryPlayerIdSource,
        legacyPlayerId: args.legacyPlayerId,
        publicPlayerId: args.publicPlayerId,
        seatId: args.seatId,
        viewerId: args.viewerId,
        choiceId: args.choiceId,
        choicePayload: args.choicePayload,
        continuation,
        viewCommitSeqSeen: lastCommitSeqRef.current,
        clientSeq: lastCommitSeqRef.current,
      }),
    );
    if (!sent && streamKey) {
      decisionRequestLedgerRef.current.releaseFlight(streamKey, flightKey, args.requestId);
    }
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
          primary_player_id: flightIdentity.playerId,
          primary_player_id_source: flightIdentity.source,
          legacy_player_id: args.legacyPlayerId,
          public_player_id: args.publicPlayerId,
          seat_id: args.seatId,
          viewer_id: args.viewerId,
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
