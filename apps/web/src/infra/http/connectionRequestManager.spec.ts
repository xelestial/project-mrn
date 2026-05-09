import { afterEach, describe, expect, it, vi } from "vitest";
import {
  FRONTEND_CONNECTION_REQUEST_CATALOG,
  buildFrontendConnectionUrl,
  requestFrontendConnectionJson,
} from "./connectionRequestManager";

describe("connectionRequestManager", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("catalogs every gameplay HTTP connection request in one place", () => {
    expect(FRONTEND_CONNECTION_REQUEST_CATALOG.map((item) => item.key)).toEqual([
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
    ]);
  });

  it("builds normalized HTTP URLs with encoded query parameters", () => {
    expect(
      buildFrontendConnectionUrl({
        baseUrl: "127.0.0.1:9090/",
        path: "/api/v1/sessions/sess%201/runtime-status",
        query: { token: "seat token" },
      }),
    ).toBe("http://127.0.0.1:9090/api/v1/sessions/sess%201/runtime-status?token=seat+token");
  });

  it("performs JSON connection requests through the manager", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, data: { session_id: "sess_a" }, error: null }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(
      requestFrontendConnectionJson<{ session_id: string }>({
        baseUrl: "http://room.test",
        path: "/api/v1/sessions",
        init: { method: "POST", body: JSON.stringify({ seats: [] }) },
        requireData: true,
      }),
    ).resolves.toEqual({ session_id: "sess_a" });
    expect(fetchMock).toHaveBeenCalledWith("http://room.test/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ seats: [] }),
      headers: { "Content-Type": "application/json" },
    });
  });
});
