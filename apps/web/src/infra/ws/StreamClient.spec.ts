import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StreamClient } from "./StreamClient";

type MockHandler = ((event?: unknown) => void) | null;

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: MockHandler = null;
  onclose: MockHandler = null;
  onerror: MockHandler = null;
  onmessage: MockHandler = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  triggerOpen(): void {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  triggerClose(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

function setupWindowStub(): void {
  vi.stubGlobal("window", {
    location: { protocol: "http:", host: "localhost:5173" },
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
  });
}

describe("StreamClient", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    setupWindowStub();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("sends resume request on socket open", () => {
    const client = new StreamClient();
    client.connect({ sessionId: "sess_a", token: "seat token", onOpenResumeSeq: 7 });
    expect(MockWebSocket.instances).toHaveLength(1);

    const socket = MockWebSocket.instances[0];
    expect(socket.url).toContain("/api/v1/sessions/sess_a/stream");
    expect(socket.url).toContain("token=seat%20token");

    socket.triggerOpen();
    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0])).toEqual({ type: "resume", last_seq: 7 });
  });

  it("reconnects after close and replays latest resume seq", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0);
    (window as unknown as { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout }).setTimeout =
      globalThis.setTimeout;
    (window as unknown as { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout }).clearTimeout =
      globalThis.clearTimeout;

    const client = new StreamClient();
    client.connect({ sessionId: "sess_b", onOpenResumeSeq: 4 });
    const first = MockWebSocket.instances[0];
    first.triggerOpen();
    first.triggerClose();

    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances).toHaveLength(2);
    const second = MockWebSocket.instances[1];
    second.triggerOpen();
    expect(second.sent).toHaveLength(1);
    expect(JSON.parse(second.sent[0])).toEqual({ type: "resume", last_seq: 4 });
  });

  it("does not reconnect after explicit disconnect", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0);
    (window as unknown as { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout }).setTimeout =
      globalThis.setTimeout;
    (window as unknown as { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout }).clearTimeout =
      globalThis.clearTimeout;

    const client = new StreamClient();
    client.connect({ sessionId: "sess_c", onOpenResumeSeq: 3 });
    const first = MockWebSocket.instances[0];
    first.triggerOpen();

    client.disconnect();
    vi.advanceTimersByTime(15000);
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("returns false when sending decision without open socket", () => {
    const client = new StreamClient();
    const sent = client.send({
      type: "decision",
      request_id: "req_1",
      player_id: 1,
      choice_id: "dice",
      client_seq: 0,
    });
    expect(sent).toBe(false);
  });

  it("returns false when resume is requested without open socket", () => {
    const client = new StreamClient();
    const sent = client.requestResume(10);
    expect(sent).toBe(false);
  });
});
