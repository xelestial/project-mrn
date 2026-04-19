import { describe, expect, it } from "vitest";
import { gameStreamReducer, initialGameStreamState, MAX_STREAM_MESSAGES } from "./gameStreamReducer";

describe("gameStreamReducer", () => {
  it("updates status", () => {
    const next = gameStreamReducer(initialGameStreamState, { type: "status", status: "connected" });
    expect(next.status).toBe("connected");
    expect(next.lastSeq).toBe(0);
    expect(next.manifestHash).toBeNull();
  });

  it("tracks last sequence and caps message list to the configured max", () => {
    let state = initialGameStreamState;
    for (let i = 1; i <= MAX_STREAM_MESSAGES + 10; i += 1) {
      state = gameStreamReducer(state, {
        type: "message",
        message: { type: "event", seq: i, session_id: "s1", payload: { n: i } },
      });
    }
    expect(state.lastSeq).toBe(MAX_STREAM_MESSAGES + 10);
    expect(state.messages).toHaveLength(MAX_STREAM_MESSAGES);
    expect(state.messages[0].seq).toBe(11);
    expect(state.messages[MAX_STREAM_MESSAGES - 1]?.seq).toBe(MAX_STREAM_MESSAGES + 10);
  });

  it("buffers out-of-order messages and flushes contiguous sequence", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 2, session_id: "s1", payload: { n: 2 } },
    });
    expect(state.lastSeq).toBe(0);
    expect(state.messages).toHaveLength(0);
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 1, session_id: "s1", payload: { n: 1 } },
    });
    expect(state.lastSeq).toBe(2);
    expect(state.messages.map((m) => m.seq)).toEqual([1, 2]);
  });

  it("ignores duplicate/old sequence messages", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 1, session_id: "s1", payload: { n: 1 } },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 1, session_id: "s1", payload: { n: 999 } },
    });
    expect(state.lastSeq).toBe(1);
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].payload).toEqual({ n: 1 });
  });

  it("resets to initial state", () => {
    const dirty = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: { type: "event", seq: 1, session_id: "s1", payload: {} },
    });
    const reset = gameStreamReducer(dirty, { type: "reset" });
    expect(reset).toEqual(initialGameStreamState);
  });

  it("rehydrates stream cache when manifest hash changes", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          parameter_manifest: { manifest_hash: "hash_a" },
        },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 2, session_id: "s1", payload: { event_type: "round_start" } },
    });
    expect(state.messages).toHaveLength(2);
    expect(state.manifestHash).toBe("hash_a");

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          parameter_manifest: { manifest_hash: "hash_b" },
        },
      },
    });
    expect(state.lastSeq).toBe(3);
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].seq).toBe(3);
    expect(state.manifestHash).toBe("hash_b");
  });

  it("tracks manifest hash from flat parameter-manifest event shape", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          manifest_hash: "hash_flat",
          seats: { max: 3 },
        },
      },
    });
    expect(state.manifestHash).toBe("hash_flat");
    expect(state.messages).toHaveLength(1);
  });

  it("keeps only new-manifest timeline during reconnect replay sequence", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          parameter_manifest: { manifest_hash: "hash_old" },
        },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 2, session_id: "s1", payload: { event_type: "round_start", round_index: 1 } },
    });

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: { event_type: "parameter_manifest", parameter_manifest: { manifest_hash: "hash_new" } },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "event", seq: 4, session_id: "s1", payload: { event_type: "round_start", round_index: 9 } },
    });

    expect(state.manifestHash).toBe("hash_new");
    expect(state.lastSeq).toBe(4);
    expect(state.messages.map((m) => m.seq)).toEqual([3, 4]);
  });
});
