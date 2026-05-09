import { afterEach, describe, expect, it, vi } from "vitest";
import { buildReplayUrl, fetchReplayMessages } from "./replayClient";

describe("replayClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds the replay endpoint from the configured room server", () => {
    expect(
      buildReplayUrl({
        sessionId: "sess A",
        token: "seat token",
        baseUrl: "127.0.0.1:9090/",
      }),
    ).toBe(
      "http://127.0.0.1:9090/api/v1/sessions/sess%20A/replay?token=seat+token",
    );
  });

  it("filters replay export data to stream messages", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          events: [
            {
              type: "event",
              seq: 4,
              session_id: "sess_a",
              payload: {
                event_type: "weather_reveal",
                view_state: { board: {} },
              },
            },
            { type: "event", seq: "bad", session_id: "sess_a", payload: {} },
          ],
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchReplayMessages({ sessionId: "sess_a", baseUrl: "http://room.test" }),
    ).resolves.toEqual([
      {
        type: "event",
        seq: 4,
        session_id: "sess_a",
        payload: { event_type: "weather_reveal", view_state: { board: {} } },
      },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://room.test/api/v1/sessions/sess_a/replay",
      { headers: { "Content-Type": "application/json" }, signal: undefined },
    );
  });

  it("does not inject restored view state from replay data", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          session_id: "sess_gap",
          events: [
            {
              type: "event",
              seq: 10,
              session_id: "sess_gap",
              payload: { event_type: "draft_pick" },
            },
            {
              type: "prompt",
              seq: 42,
              session_id: "sess_gap",
              payload: {
                request_id: "sess_gap:r1:t1:p1:hidden_trick_card:4",
                request_type: "hidden_trick_card",
                player_id: 1,
              },
            },
          ],
          view_state: {
            prompt: {
              active: {
                request_id: "sess_gap:r1:t1:p1:hidden_trick_card:4",
                request_type: "hidden_trick_card",
                player_id: 1,
              },
            },
          },
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchReplayMessages({ sessionId: "sess_gap", baseUrl: "http://room.test" }),
    ).resolves.toEqual([
      {
        type: "event",
        seq: 10,
        session_id: "sess_gap",
        payload: { event_type: "draft_pick" },
      },
      {
        type: "prompt",
        seq: 42,
        session_id: "sess_gap",
        payload: {
          request_id: "sess_gap:r1:t1:p1:hidden_trick_card:4",
          request_type: "hidden_trick_card",
          player_id: 1,
        },
      },
    ]);
  });

  it("ignores projection sequence floor because replay is debug-only", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          session_id: "sess_gap",
          events: [
            {
              type: "event",
              seq: 80,
              session_id: "sess_gap",
              payload: { event_type: "prompt_required" },
            },
          ],
          view_state: {
            prompt: {
              active: {
                request_id: "sess_gap:r1:t1:p1:hidden_trick_card:4",
                request_type: "hidden_trick_card",
                player_id: 1,
              },
            },
          },
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const messages = await fetchReplayMessages({ sessionId: "sess_gap", baseUrl: "http://room.test" });

    expect(messages).toEqual([
      {
        type: "event",
        seq: 80,
        session_id: "sess_gap",
        payload: { event_type: "prompt_required" },
      },
    ]);
  });
});
