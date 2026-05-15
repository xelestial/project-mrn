import type { InboundMessage, ProtocolPlayerId, ViewCommitPayload } from "../../core/contracts/stream";

export type LocalViewerIdentitySource =
  | "view-commit-viewer"
  | "join-result"
  | "session-token"
  | "none";

export type LocalViewerIdentity = {
  legacyPlayerId: number | null;
  protocolPlayerId: ProtocolPlayerId | null;
  publicPlayerId: string | null;
  seatId: string | null;
  viewerId: string | null;
  source: LocalViewerIdentitySource;
};

type JoinResultLike = {
  player_id?: ProtocolPlayerId | null;
  legacy_player_id?: number | null;
  public_player_id?: string | null;
  seat_id?: string | null;
  viewer_id?: string | null;
  [key: string]: unknown;
};

const EMPTY_LOCAL_VIEWER_IDENTITY: LocalViewerIdentity = {
  legacyPlayerId: null,
  protocolPlayerId: null,
  publicPlayerId: null,
  seatId: null,
  viewerId: null,
  source: "none",
};

export function localViewerIdentityFromSessionToken(token: string | undefined): LocalViewerIdentity {
  if (!token) {
    return EMPTY_LOCAL_VIEWER_IDENTITY;
  }
  const match = /^session_p(\d+)_/.exec(token.trim());
  if (!match) {
    return EMPTY_LOCAL_VIEWER_IDENTITY;
  }
  const parsed = Number(match[1]);
  const legacyPlayerId = Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null;
  if (legacyPlayerId === null) {
    return EMPTY_LOCAL_VIEWER_IDENTITY;
  }
  return {
    legacyPlayerId,
    protocolPlayerId: null,
    publicPlayerId: null,
    seatId: null,
    viewerId: null,
    source: "session-token",
  };
}

export function localViewerIdentityFromJoinResult(joined: JoinResultLike | null | undefined): LocalViewerIdentity {
  const publicPlayerId = normalizeIdentityString(joined?.public_player_id);
  const seatId = normalizeIdentityString(joined?.seat_id);
  const viewerId = normalizeIdentityString(joined?.viewer_id);
  const protocolPlayerId =
    typeof joined?.player_id === "number"
      ? publicPlayerId
      : normalizeProtocolPlayerId(joined?.player_id) ?? publicPlayerId;
  const legacyPlayerId =
    normalizeLegacyPlayerId(joined?.legacy_player_id) ??
    (typeof joined?.player_id === "number" ? normalizeLegacyPlayerId(joined.player_id) : null);

  if (legacyPlayerId === null && protocolPlayerId === null && publicPlayerId === null && seatId === null && viewerId === null) {
    return EMPTY_LOCAL_VIEWER_IDENTITY;
  }
  return {
    legacyPlayerId,
    protocolPlayerId,
    publicPlayerId,
    seatId,
    viewerId,
    source: "join-result",
  };
}

export function localViewerIdentityFromViewCommitViewer(
  viewer: ViewCommitPayload["viewer"] | null | undefined
): LocalViewerIdentity {
  if (!viewer || viewer.role !== "seat") {
    return EMPTY_LOCAL_VIEWER_IDENTITY;
  }
  const publicPlayerId = normalizeIdentityString(viewer.public_player_id);
  const seatId = normalizeIdentityString(viewer.seat_id);
  const viewerId = normalizeIdentityString(viewer.viewer_id);
  const protocolPlayerId =
    typeof viewer.player_id === "number"
      ? publicPlayerId
      : normalizeProtocolPlayerId(viewer.player_id) ?? publicPlayerId;
  const legacyPlayerId =
    normalizeLegacyPlayerId(viewer.legacy_player_id) ??
    (typeof viewer.player_id === "number" ? normalizeLegacyPlayerId(viewer.player_id) : null);

  if (legacyPlayerId === null && protocolPlayerId === null && publicPlayerId === null && seatId === null && viewerId === null) {
    return EMPTY_LOCAL_VIEWER_IDENTITY;
  }
  return {
    legacyPlayerId,
    protocolPlayerId,
    publicPlayerId,
    seatId,
    viewerId,
    source: "view-commit-viewer",
  };
}

export function localViewerIdentityFromMessages(messages: InboundMessage[]): LocalViewerIdentity | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if ((message.type === "view_commit" || message.type === "snapshot_pulse") && message.payload.viewer) {
      const identity = localViewerIdentityFromViewCommitViewer(message.payload.viewer);
      if (identity.source !== "none") {
        return identity;
      }
    }
  }
  return null;
}

export function resolveLocalViewerLegacyPlayerId(
  ...identities: Array<LocalViewerIdentity | null | undefined>
): number | null {
  for (const identity of identities) {
    if (identity?.legacyPlayerId !== null && identity?.legacyPlayerId !== undefined) {
      return identity.legacyPlayerId;
    }
  }
  return null;
}

function normalizeLegacyPlayerId(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  return Math.floor(value);
}

function normalizeProtocolPlayerId(value: unknown): ProtocolPlayerId | null {
  if (typeof value === "number") {
    return normalizeLegacyPlayerId(value);
  }
  return normalizeIdentityString(value);
}

function normalizeIdentityString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
