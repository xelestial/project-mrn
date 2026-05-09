import { afterEach, describe, expect, it, vi } from "vitest";
import {
  FRONTEND_WEBSOCKET_CATALOG,
  buildFrontendStreamWebSocketUrl,
  createFrontendWebSocket,
  parseFrontendWebSocketMessage,
  sendFrontendWebSocketMessage,
} from "./webSocketManager";

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.OPEN;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(payload);
  }
}

describe("webSocketManager", () => {
  afterEach(() => {
    MockWebSocket.instances = [];
    vi.unstubAllGlobals();
  });

  it("catalogs every gameplay websocket operation in one place", () => {
    expect(FRONTEND_WEBSOCKET_CATALOG.map((item) => item.key)).toEqual([
      "stream.connect",
      "stream.resume",
      "stream.decision",
    ]);
  });

  it("builds stream websocket URLs through the manager", () => {
    expect(
      buildFrontendStreamWebSocketUrl({
        baseUrl: "https://mrn.example/",
        sessionId: "sess/with/slash",
        token: "seat token",
      }),
    ).toBe("wss://mrn.example/api/v1/sessions/sess%2Fwith%2Fslash/stream?token=seat+token");
  });

  it("creates sockets and serializes outbound messages through the manager", () => {
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    const socket = createFrontendWebSocket({
      baseUrl: "http://room.test",
      sessionId: "sess_a",
    });

    expect(MockWebSocket.instances[0]?.url).toBe("ws://room.test/api/v1/sessions/sess_a/stream");
    expect(sendFrontendWebSocketMessage(socket, { type: "resume", last_commit_seq: 7 })).toBe(true);
    expect(MockWebSocket.instances[0]?.sent).toEqual([JSON.stringify({ type: "resume", last_commit_seq: 7 })]);
  });

  it("parses inbound messages through the manager", () => {
    expect(parseFrontendWebSocketMessage(JSON.stringify({ type: "heartbeat", seq: 1, session_id: "sess_a" }))).toEqual({
      type: "heartbeat",
      seq: 1,
      session_id: "sess_a",
    });
  });
});
