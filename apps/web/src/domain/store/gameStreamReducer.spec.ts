import { describe, expect, it } from "vitest";
import { gameStreamReducer, initialGameStreamState } from "./gameStreamReducer";

describe("gameStreamReducer", () => {
  it("updates status", () => {
    const next = gameStreamReducer(initialGameStreamState, { type: "status", status: "connected" });
    expect(next.status).toBe("connected");
    expect(next.lastSeq).toBe(0);
  });

  it("tracks last sequence and caps message list to 50", () => {
    let state = initialGameStreamState;
    for (let i = 1; i <= 60; i += 1) {
      state = gameStreamReducer(state, {
        type: "message",
        message: { type: "event", seq: i, session_id: "s1", payload: { n: i } },
      });
    }
    expect(state.lastSeq).toBe(60);
    expect(state.messages).toHaveLength(50);
    expect(state.messages[0].seq).toBe(11);
    expect(state.messages[49].seq).toBe(60);
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
});
