import { describe, expect, it } from "vitest";
import {
  localViewerIdentityFromJoinResult,
  localViewerIdentityFromSessionToken,
  localViewerIdentityFromViewCommitViewer,
  resolveLocalViewerLegacyPlayerId,
} from "./localViewerIdentity";

describe("localViewerIdentity", () => {
  it("treats token-derived player numbers as a legacy bridge, not protocol identity", () => {
    expect(localViewerIdentityFromSessionToken("session_p2_abc")).toEqual({
      legacyPlayerId: 2,
      protocolPlayerId: null,
      publicPlayerId: null,
      seatId: null,
      viewerId: null,
      source: "session-token",
    });
  });

  it("keeps public protocol identity from the viewer payload and separates its numeric bridge", () => {
    const identity = localViewerIdentityFromViewCommitViewer({
      role: "seat",
      player_id: "player_public_2",
      legacy_player_id: 2,
      public_player_id: "player_public_2",
      seat_id: "seat_public_2",
      viewer_id: "viewer_public_2",
      seat: 2,
    });

    expect(identity).toEqual({
      legacyPlayerId: 2,
      protocolPlayerId: "player_public_2",
      publicPlayerId: "player_public_2",
      seatId: "seat_public_2",
      viewerId: "viewer_public_2",
      source: "view-commit-viewer",
    });
    expect(resolveLocalViewerLegacyPlayerId(identity, localViewerIdentityFromSessionToken("session_p1_fallback"))).toBe(2);
  });

  it("uses join responses as explicit legacy ownership input while no public identity is available", () => {
    expect(
      localViewerIdentityFromJoinResult({
        session_id: "s1",
        seat: 3,
        player_id: 3,
        session_token: "session_p3_join",
        role: "seat",
      })
    ).toEqual({
      legacyPlayerId: 3,
      protocolPlayerId: null,
      publicPlayerId: null,
      seatId: null,
      viewerId: null,
      source: "join-result",
    });
  });
});
