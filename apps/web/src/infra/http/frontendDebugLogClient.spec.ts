import { describe, expect, it, vi } from "vitest";
import {
  buildFrontendDebugLogUrl,
  isFrontendDebugLogEnabled,
  logFrontendDebugEvent,
} from "./frontendDebugLogClient";

describe("frontendDebugLogClient", () => {
  it("keeps debug logging disabled by default-like values", () => {
    expect(isFrontendDebugLogEnabled("")).toBe(false);
    expect(isFrontendDebugLogEnabled("0")).toBe(false);
    expect(isFrontendDebugLogEnabled("false")).toBe(false);
  });

  it("enables debug logging for explicit on values", () => {
    expect(isFrontendDebugLogEnabled("1")).toBe(true);
    expect(isFrontendDebugLogEnabled("true")).toBe(true);
  });

  it("builds the frontend log endpoint from the configured base url", () => {
    expect(buildFrontendDebugLogUrl("127.0.0.1:9090/")).toBe("http://127.0.0.1:9090/api/v1/debug/frontend-log");
  });

  it("does not post when disabled", () => {
    const beforeFetch = globalThis.fetch;
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    try {
      logFrontendDebugEvent({ event: "stream_message", sessionId: "sess_a" });
      expect(fetchMock).not.toHaveBeenCalled();
    } finally {
      globalThis.fetch = beforeFetch;
    }
  });
});
