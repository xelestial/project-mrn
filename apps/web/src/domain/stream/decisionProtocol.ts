import type { OutboundMessage, ProtocolPlayerId } from "../../core/contracts/stream";
import type { PromptContinuationViewModel, PromptIdentitySource } from "../selectors/promptSelectors";

export function buildGameStreamKey(sessionId: string, token?: string): string {
  return `${sessionId.trim()}\n${token ?? ""}`;
}

const sentDecisionRequestIdsByStreamKey = new Map<string, Set<string>>();
const activeDecisionFlightsByStreamKey = new Map<string, Map<string, string>>();

function sentDecisionRequestIdsFor(streamKey: string): Set<string> {
  let sentRequestIds = sentDecisionRequestIdsByStreamKey.get(streamKey);
  if (!sentRequestIds) {
    sentRequestIds = new Set<string>();
    sentDecisionRequestIdsByStreamKey.set(streamKey, sentRequestIds);
  }
  return sentRequestIds;
}

function activeDecisionFlightsFor(streamKey: string): Map<string, string> {
  let activeFlights = activeDecisionFlightsByStreamKey.get(streamKey);
  if (!activeFlights) {
    activeFlights = new Map<string, string>();
    activeDecisionFlightsByStreamKey.set(streamKey, activeFlights);
  }
  return activeFlights;
}

export type DecisionFlightResult =
  | { status: "started"; requestId: string }
  | { status: "duplicate"; requestId: string }
  | { status: "busy"; requestId: string };

export function buildDecisionFlightKey(args: {
  requestId: string;
  playerId: ProtocolPlayerId;
  requestType?: string | null;
  continuation?: PromptContinuationViewModel;
}): string {
  const continuation = args.continuation;
  const promptKey = firstNonEmpty([
    continuation?.promptFingerprint,
    typeof continuation?.publicPromptInstanceId === "string" && continuation.publicPromptInstanceId.trim()
      ? `public_prompt_instance:${continuation.publicPromptInstanceId.trim()}`
      : "",
    typeof continuation?.promptInstanceId === "number" && Number.isFinite(continuation.promptInstanceId)
      ? `prompt_instance:${Math.floor(continuation.promptInstanceId)}`
      : "",
    continuation?.resumeToken,
    continuation?.moduleId && continuation?.moduleCursor
      ? `${continuation.moduleId}:${continuation.moduleCursor}`
      : "",
    args.requestId,
  ]);
  const actionKey = firstNonEmpty([args.requestType, continuation?.moduleType, "decision"]);
  return `player:${decisionFlightPlayerKey(args.playerId)}\nprompt:${promptKey}\naction:${actionKey}`;
}

export function createDecisionRequestLedger(): {
  shouldSend: (streamKey: string, requestId: string) => boolean;
  recordSent: (streamKey: string, requestId: string) => void;
  forget: (streamKey: string, requestId: string) => void;
  beginFlight: (streamKey: string, flightKey: string, requestId: string) => DecisionFlightResult;
  releaseFlight: (streamKey: string, flightKey: string, requestId?: string) => boolean;
  releaseFlightsForStream: (streamKey: string) => void;
  clear: () => void;
} {
  let activeStreamKey = "";

  const resetIfStreamChanged = (streamKey: string) => {
    if (activeStreamKey === streamKey) {
      return;
    }
    activeStreamKey = streamKey;
  };

  return {
    shouldSend: (streamKey, requestId) => {
      resetIfStreamChanged(streamKey);
      return !sentDecisionRequestIdsFor(streamKey).has(requestId);
    },
    recordSent: (streamKey, requestId) => {
      resetIfStreamChanged(streamKey);
      sentDecisionRequestIdsFor(streamKey).add(requestId);
    },
    forget: (streamKey, requestId) => {
      resetIfStreamChanged(streamKey);
      sentDecisionRequestIdsFor(streamKey).delete(requestId);
      const activeFlights = activeDecisionFlightsFor(streamKey);
      for (const [flightKey, activeRequestId] of activeFlights) {
        if (activeRequestId === requestId) {
          activeFlights.delete(flightKey);
        }
      }
    },
    beginFlight: (streamKey, flightKey, requestId) => {
      resetIfStreamChanged(streamKey);
      if (sentDecisionRequestIdsFor(streamKey).has(requestId)) {
        return { status: "duplicate", requestId };
      }
      const activeFlights = activeDecisionFlightsFor(streamKey);
      const activeRequestId = activeFlights.get(flightKey);
      if (!activeRequestId) {
        activeFlights.set(flightKey, requestId);
        return { status: "started", requestId };
      }
      return {
        status: activeRequestId === requestId ? "duplicate" : "busy",
        requestId: activeRequestId,
      };
    },
    releaseFlight: (streamKey, flightKey, requestId) => {
      resetIfStreamChanged(streamKey);
      const activeFlights = activeDecisionFlightsFor(streamKey);
      const activeRequestId = activeFlights.get(flightKey);
      if (!activeRequestId || (requestId && activeRequestId !== requestId)) {
        return false;
      }
      activeFlights.delete(flightKey);
      return true;
    },
    releaseFlightsForStream: (streamKey) => {
      resetIfStreamChanged(streamKey);
      activeDecisionFlightsFor(streamKey).clear();
    },
    clear: () => {
      activeStreamKey = "";
    },
  };
}

function firstNonEmpty(values: Array<string | null | undefined>): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "unknown";
}

function decisionFlightPlayerKey(playerId: ProtocolPlayerId): string {
  if (typeof playerId === "number" && Number.isFinite(playerId)) {
    return String(Math.floor(playerId));
  }
  if (typeof playerId === "string" && playerId.trim()) {
    return playerId.trim();
  }
  return "unknown";
}

type PrimaryPlayerIdentity = {
  playerId: ProtocolPlayerId;
  source: PromptIdentitySource;
};

function primaryPlayerIdentity(args: {
  playerId: ProtocolPlayerId;
  primaryPlayerId?: ProtocolPlayerId | null;
  primaryPlayerIdSource?: PromptIdentitySource | null;
  legacyPlayerId: number | null;
  publicPlayerId: string | null;
}): PrimaryPlayerIdentity {
  const explicitPrimary = explicitPrimaryPlayerIdentity(args.primaryPlayerId, args.primaryPlayerIdSource);
  if (explicitPrimary !== null) {
    return explicitPrimary;
  }
  if (args.publicPlayerId) {
    return { playerId: args.publicPlayerId, source: "public" };
  }
  if (typeof args.playerId === "string" && args.playerId.trim()) {
    return { playerId: args.playerId.trim(), source: "protocol" };
  }
  return {
    playerId: args.legacyPlayerId ?? numericProtocolPlayerId(args.playerId) ?? args.playerId,
    source: "legacy",
  };
}

function explicitPrimaryPlayerIdentity(
  playerId: ProtocolPlayerId | null | undefined,
  source: PromptIdentitySource | null | undefined,
): PrimaryPlayerIdentity | null {
  if (source !== "public" && source !== "protocol" && source !== "legacy") {
    return null;
  }
  if (typeof playerId === "number" && Number.isFinite(playerId)) {
    return source === "legacy" ? { playerId: Math.floor(playerId), source } : null;
  }
  if (typeof playerId === "string" && playerId.trim()) {
    return { playerId: playerId.trim(), source };
  }
  return null;
}

function numericProtocolPlayerId(playerId: ProtocolPlayerId): number | null {
  if (typeof playerId === "number" && Number.isFinite(playerId)) {
    return Math.floor(playerId);
  }
  return null;
}

function decisionProtocolPlayerId(
  fallbackPlayerId: ProtocolPlayerId,
  primaryPlayer: { playerId: ProtocolPlayerId; source: PromptIdentitySource },
): ProtocolPlayerId {
  if (
    (primaryPlayer.source === "public" || primaryPlayer.source === "protocol") &&
    typeof primaryPlayer.playerId === "string"
  ) {
    return primaryPlayer.playerId;
  }
  return fallbackPlayerId;
}

export function buildDecisionMessage(args: {
  requestId: string;
  playerId: ProtocolPlayerId;
  primaryPlayerId?: ProtocolPlayerId | null;
  primaryPlayerIdSource?: PromptIdentitySource | null;
  legacyPlayerId?: number | null;
  publicPlayerId?: string | null;
  seatId?: string | null;
  viewerId?: string | null;
  choiceId: string;
  choicePayload?: Record<string, unknown>;
  continuation?: PromptContinuationViewModel;
  viewCommitSeqSeen: number;
  clientSeq: number;
}): OutboundMessage {
  const continuation = args.continuation;
  const legacyPlayerId =
    typeof args.legacyPlayerId === "number" && Number.isFinite(args.legacyPlayerId)
      ? Math.floor(args.legacyPlayerId)
      : null;
  const publicPlayerId = optionalString(args.publicPlayerId);
  const primaryPlayer = primaryPlayerIdentity({
    playerId: args.playerId,
    primaryPlayerId: args.primaryPlayerId,
    primaryPlayerIdSource: args.primaryPlayerIdSource,
    legacyPlayerId,
    publicPlayerId,
  });
  const playerId = decisionProtocolPlayerId(args.playerId, primaryPlayer);
  const topLevelPlayerIdIsLegacyAlias = numericProtocolPlayerId(playerId) !== null;
  const seatId = optionalString(args.seatId);
  const viewerId = optionalString(args.viewerId);
  const publicPromptInstanceId = optionalString(continuation?.publicPromptInstanceId);
  return {
    type: "decision",
    request_id: args.requestId,
    player_id: playerId,
    ...(topLevelPlayerIdIsLegacyAlias ? { player_id_alias_role: "legacy_compatibility_alias" as const } : {}),
    primary_player_id: primaryPlayer.playerId,
    primary_player_id_source: primaryPlayer.source,
    ...(legacyPlayerId !== null ? { legacy_player_id: legacyPlayerId } : {}),
    ...(publicPlayerId ? { public_player_id: publicPlayerId } : {}),
    ...(seatId ? { seat_id: seatId } : {}),
    ...(viewerId ? { viewer_id: viewerId } : {}),
    choice_id: args.choiceId,
    choice_payload: args.choicePayload,
    ...(continuation?.resumeToken ? { resume_token: continuation.resumeToken } : {}),
    ...(continuation?.frameId ? { frame_id: continuation.frameId } : {}),
    ...(continuation?.moduleId ? { module_id: continuation.moduleId } : {}),
    ...(continuation?.moduleType ? { module_type: continuation.moduleType } : {}),
    ...(continuation?.moduleCursor ? { module_cursor: continuation.moduleCursor } : {}),
    ...(continuation?.batchId ? { batch_id: continuation.batchId } : {}),
    ...(continuation?.missingPlayerIds ? { missing_player_ids: continuation.missingPlayerIds } : {}),
    ...(continuation?.resumeTokensByPlayerId
      ? { resume_tokens_by_player_id: continuation.resumeTokensByPlayerId }
      : {}),
    ...(continuation?.missingPublicPlayerIds
      ? { missing_public_player_ids: continuation.missingPublicPlayerIds }
      : {}),
    ...(continuation?.resumeTokensByPublicPlayerId
      ? { resume_tokens_by_public_player_id: continuation.resumeTokensByPublicPlayerId }
      : {}),
    ...(continuation?.missingSeatIds ? { missing_seat_ids: continuation.missingSeatIds } : {}),
    ...(continuation?.resumeTokensBySeatId ? { resume_tokens_by_seat_id: continuation.resumeTokensBySeatId } : {}),
    ...(continuation?.missingViewerIds ? { missing_viewer_ids: continuation.missingViewerIds } : {}),
    ...(continuation?.resumeTokensByViewerId
      ? { resume_tokens_by_viewer_id: continuation.resumeTokensByViewerId }
      : {}),
    ...(typeof continuation?.promptInstanceId === "number" &&
    Number.isFinite(continuation.promptInstanceId) &&
    continuation.promptInstanceId >= 0
      ? { prompt_instance_id: continuation.promptInstanceId }
      : {}),
    ...(publicPromptInstanceId ? { public_prompt_instance_id: publicPromptInstanceId } : {}),
    ...(continuation?.promptFingerprint ? { prompt_fingerprint: continuation.promptFingerprint } : {}),
    ...(continuation?.promptFingerprintVersion
      ? { prompt_fingerprint_version: continuation.promptFingerprintVersion }
      : {}),
    view_commit_seq_seen: Math.max(0, Math.floor(args.viewCommitSeqSeen)),
    client_seq: args.clientSeq,
  };
}

function optionalString(value: string | null | undefined): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
