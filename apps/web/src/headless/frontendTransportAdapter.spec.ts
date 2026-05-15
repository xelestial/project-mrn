import { describe, expect, it, vi } from "vitest";
import { buildDecisionMessage } from "../domain/stream/decisionProtocol";
import {
  FRONTEND_TRANSPORT_REQUEST_CATALOG,
  FrontendTransportCatalogMismatchError,
  FrontendTransportAdapter,
  assertFrontendTransportManagersCovered,
  buildFrontendStreamUrl,
  buildFrontendTransportUrl,
} from "./frontendTransportAdapter";
import { FRONTEND_CONNECTION_REQUEST_CATALOG } from "../infra/http/connectionRequestManager";
import { FRONTEND_WEBSOCKET_CATALOG } from "../infra/ws/webSocketManager";

describe("frontendTransportAdapter", () => {
  it("catalogs every frontend HTTP request and websocket stream used by gameplay", () => {
    expect(FRONTEND_TRANSPORT_REQUEST_CATALOG.map((item) => item.key)).toEqual([
      "session.create",
      "session.list",
      "session.get",
      "session.join",
      "session.start",
      "session.runtimeStatus",
      "session.viewCommit",
      "session.replay",
      "room.create",
      "room.list",
      "room.get",
      "room.join",
      "room.ready",
      "room.leave",
      "room.resume",
      "room.start",
      "debug.frontendLog",
      "stream.connect",
      "stream.resume",
      "stream.decision",
    ]);
  });

  it("compares the adapter catalog with the HTTP and websocket manager catalogs", () => {
    expect(FRONTEND_TRANSPORT_REQUEST_CATALOG.map((item) => item.key)).toEqual([
      ...FRONTEND_CONNECTION_REQUEST_CATALOG.map((item) => item.key),
      ...FRONTEND_WEBSOCKET_CATALOG.map((item) => item.key),
    ]);
    expect(() => assertFrontendTransportManagersCovered()).not.toThrow();
    expect(() =>
      assertFrontendTransportManagersCovered(
        FRONTEND_TRANSPORT_REQUEST_CATALOG.filter((item) => item.key !== "stream.decision"),
      ),
    ).toThrow(FrontendTransportCatalogMismatchError);
  });

  it("builds frontend-equivalent URLs including websocket and token query parameters", () => {
    expect(buildFrontendTransportUrl("127.0.0.1:9090/", "/api/v1/sessions")).toBe(
      "http://127.0.0.1:9090/api/v1/sessions",
    );
    expect(
      buildFrontendTransportUrl("https://mrn.example", "/api/v1/sessions/sess%201/runtime-status", {
        token: "seat token",
      }),
    ).toBe("https://mrn.example/api/v1/sessions/sess%201/runtime-status?token=seat+token");
    expect(
      buildFrontendStreamUrl({
        baseUrl: "https://mrn.example/",
        sessionId: "sess/with/slash",
        token: "seat token",
      }),
    ).toBe("wss://mrn.example/api/v1/sessions/sess%2Fwith%2Fslash/stream?token=seat+token");
  });

  it("sends the same session REST bodies as the browser frontend", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          data: { session_id: "sess_1", host_token: "host", join_tokens: { 1: "join" }, status: "created" },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const adapter = new FrontendTransportAdapter({ baseUrl: "http://127.0.0.1:9090/" });

    await adapter.createSession({
      seats: [{ seat: 1, seat_type: "human" }],
      config: { seed: 7 },
    });
    await adapter.joinSession({
      sessionId: "sess_1",
      seat: 1,
      joinToken: "join",
      displayName: "Headless 1",
    });
    await adapter.startSession({ sessionId: "sess_1", hostToken: "host" });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:9090/api/v1/sessions",
      "http://127.0.0.1:9090/api/v1/sessions/sess_1/join",
      "http://127.0.0.1:9090/api/v1/sessions/sess_1/start",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      seats: [{ seat: 1, seat_type: "human" }],
      config: { seed: 7 },
    });
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      seat: 1,
      join_token: "join",
      display_name: "Headless 1",
    });
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      host_token: "host",
    });
  });

  it("exposes websocket outbound messages through the same decision protocol as useGameStream", () => {
    const decision = buildDecisionMessage({
      requestId: "req_1",
      playerId: 2,
      choiceId: "buy",
      choicePayload: { tile_index: 3 },
      continuation: {
        promptInstanceId: 9,
        publicPromptInstanceId: "pin_transport_9",
        promptFingerprint: "fp",
        promptFingerprintVersion: "1",
        resumeToken: "resume",
        frameId: "frame",
        moduleId: "module",
        moduleType: "PromptModule",
        moduleCursor: "await_choice",
        batchId: null,
      },
      viewCommitSeqSeen: 12,
      clientSeq: 12,
    });

    expect(JSON.parse(new FrontendTransportAdapter().serializeStreamMessage(decision))).toEqual(
      {
        type: "decision",
        request_id: "req_1",
        player_id: 2,
        player_id_alias_role: "legacy_compatibility_alias",
        primary_player_id: 2,
        primary_player_id_source: "legacy",
        choice_id: "buy",
        choice_payload: { tile_index: 3 },
        prompt_instance_id: 9,
        prompt_fingerprint: "fp",
        prompt_fingerprint_version: "1",
        resume_token: "resume",
        frame_id: "frame",
        module_id: "module",
        module_type: "PromptModule",
        module_cursor: "await_choice",
        public_prompt_instance_id: "pin_transport_9",
        view_commit_seq_seen: 12,
        client_seq: 12,
      },
    );
  });
});
