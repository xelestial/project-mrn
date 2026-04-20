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

  it("fast-forwards across seat-private sequence gaps when a newer projected prompt arrives", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "heartbeat", seq: 19, session_id: "s1", payload: {} },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: { event_type: "session_created", view_state: {} },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 12,
        session_id: "s1",
        payload: { event_type: "weather_reveal", view_state: {} },
      },
    });
    expect(state.lastSeq).toBe(12);
    expect(state.messages.map((message) => message.seq)).toEqual([1, 12]);

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 17,
        session_id: "s1",
        payload: { event_type: "draft_pick", view_state: { prompt: { active: null } } },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "prompt",
        seq: 18,
        session_id: "s1",
        payload: {
          request_id: "req_2",
          request_type: "draft_card",
          player_id: 2,
          view_state: {
            prompt: {
              active: {
                request_id: "req_2",
                request_type: "draft_card",
                player_id: 2,
                choices: [],
              },
            },
          },
        },
      },
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 19,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          request_id: "req_2",
          request_type: "draft_card",
          player_id: 2,
          view_state: {
            prompt: {
              active: {
                request_id: "req_2",
                request_type: "draft_card",
                player_id: 2,
                choices: [],
              },
            },
          },
        },
      },
    });

    expect(state.lastSeq).toBe(19);
    expect(state.messages.map((message) => message.seq)).toEqual([1, 12, 17, 18, 19]);
  });

  it("skips heartbeat-only pending gaps before a projected prompt arrives", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 27,
        session_id: "s1",
        payload: { event_type: "decision_resolved", view_state: { prompt: { last_feedback: { status: "accepted" } } } },
      },
    });

    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "heartbeat", seq: 31, session_id: "s1", payload: {} },
    });

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "prompt",
        seq: 38,
        session_id: "s1",
        payload: {
          request_id: "req_hidden",
          request_type: "hidden_trick_card",
          player_id: 1,
          view_state: {
            prompt: {
              active: {
                request_id: "req_hidden",
                request_type: "hidden_trick_card",
                player_id: 1,
                choices: [],
              },
            },
          },
        },
      },
    });

    expect(state.lastSeq).toBe(38);
    expect(state.messages.map((message) => message.seq)).toEqual([27, 38]);
  });

  it("fast-forwards to a single projected end-state message across a missing private gap", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 312,
        session_id: "s1",
        payload: {
          event_type: "fortune_resolved",
          view_state: { turn_stage: { current_beat_event_code: "fortune_resolved" } },
        },
      },
    });

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 314,
        session_id: "s1",
        payload: {
          event_type: "game_end",
          view_state: {
            turn_stage: { current_beat_event_code: "game_end" },
            scene: { situation: { headline_event_code: "game_end" } },
          },
        },
      },
    });

    expect(state.lastSeq).toBe(314);
    expect(state.messages.map((message) => message.seq)).toEqual([312, 314]);
  });

  it("ignores heartbeat messages so a same-seq projected event can still land", () => {
    let state = initialGameStreamState;

    state = gameStreamReducer(state, {
      type: "message",
      message: { type: "heartbeat", seq: 314, session_id: "s1", payload: {} },
    });

    expect(state).toEqual(initialGameStreamState);

    state = gameStreamReducer(state, {
      type: "message",
      message: {
        type: "event",
        seq: 314,
        session_id: "s1",
        payload: {
          event_type: "game_end",
          view_state: {
            turn_stage: { current_beat_event_code: "game_end" },
            scene: { situation: { headline_event_code: "game_end" } },
          },
        },
      },
    });

    expect(state.lastSeq).toBe(314);
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.payload).toMatchObject({ event_type: "game_end" });
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
