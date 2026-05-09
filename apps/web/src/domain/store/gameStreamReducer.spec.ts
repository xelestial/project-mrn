import { describe, expect, it } from "vitest";
import type { InboundMessage, ViewCommitPayload } from "../../core/contracts/stream";
import { gameStreamReducer, initialGameStreamState, MAX_STREAM_MESSAGES } from "./gameStreamReducer";

function commitMessage(seq: number, commitSeq: number, viewState: Record<string, unknown>): InboundMessage {
  const payload: ViewCommitPayload = {
    schema_version: 1,
    commit_seq: commitSeq,
    source_event_seq: Math.max(0, seq - 1),
    round_index: 0,
    turn_index: 0,
    turn_label: "R0-T0",
    viewer: { role: "spectator" },
    runtime: {
      status: "running",
      round_index: 0,
      turn_index: 0,
      turn_label: "R0-T0",
      active_frame_id: "",
      active_module_id: "",
      active_module_type: "",
      module_path: [],
    },
    view_state: viewState,
  };
  return {
    type: "view_commit",
    seq,
    session_id: "s1",
    server_time_ms: seq,
    payload,
  };
}

describe("gameStreamReducer", () => {
  it("updates connection status without changing authoritative state", () => {
    const next = gameStreamReducer(initialGameStreamState, { type: "status", status: "connected" });
    expect(next.status).toBe("connected");
    expect(next.latestCommit).toBeNull();
    expect(next.lastCommitSeq).toBe(0);
    expect(next.messages).toEqual([]);
  });

  it("keeps source events in the debug log without changing live UI state", () => {
    const next = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: {
        type: "event",
        seq: 10,
        session_id: "s1",
        payload: { event_type: "round_start", view_state: { board: { round: 99 } } },
      },
    });

    expect(next.latestCommit).toBeNull();
    expect(next.lastCommitSeq).toBe(0);
    expect(next.messages).toEqual([]);
    expect(next.debugMessages.map((message) => message.seq)).toEqual([10]);
  });

  it("replaces live UI state with the newest view_commit only", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: commitMessage(20, 2, { board: { round: 1 }, prompt: { active: null } }),
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: commitMessage(22, 3, {
        board: { round: 2 },
        prompt: { active: { request_id: "r1", choices: [{ choice_id: "roll" }] } },
      }),
    });

    expect(state.lastCommitSeq).toBe(3);
    expect(state.lastSeq).toBe(3);
    expect(state.latestCommit?.view_state).toEqual({
      board: { round: 2 },
      prompt: { active: { request_id: "r1", choices: [{ choice_id: "roll" }] } },
    });
    expect(state.messages).toEqual([commitMessage(22, 3, state.latestCommit?.view_state as Record<string, unknown>)]);
  });

  it("ignores stale view_commit messages for live UI while preserving them for debug", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: commitMessage(30, 5, { board: { round: 2 }, prompt: { active: null } }),
    });
    state = gameStreamReducer(state, {
      type: "message",
      message: commitMessage(31, 4, {
        board: { round: 1 },
        prompt: { active: { request_id: "stale" } },
      }),
    });

    expect(state.lastCommitSeq).toBe(5);
    expect(state.latestCommit?.view_state).toEqual({ board: { round: 2 }, prompt: { active: null } });
    expect(state.messages.map((message) => message.seq)).toEqual([30]);
    expect(state.debugMessages.map((message) => message.seq)).toEqual([30, 31]);
  });

  it("caps debug messages independently from authoritative live state", () => {
    let state = initialGameStreamState;
    state = gameStreamReducer(state, {
      type: "message",
      message: commitMessage(1, 1, { board: { round: 1 } }),
    });
    for (let i = 2; i <= MAX_STREAM_MESSAGES + 20; i += 1) {
      state = gameStreamReducer(state, {
        type: "message",
        message: { type: "event", seq: i, session_id: "s1", payload: { n: i } },
      });
    }

    expect(state.lastCommitSeq).toBe(1);
    expect(state.messages.map((message) => message.seq)).toEqual([1]);
    expect(state.debugMessages).toHaveLength(MAX_STREAM_MESSAGES);
    expect(state.debugMessages[0]?.seq).toBe(21);
  });

  it("reset clears authoritative and debug state", () => {
    let state = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: commitMessage(1, 1, { board: { round: 1 } }),
    });
    state = gameStreamReducer(state, { type: "reset" });

    expect(state).toEqual(initialGameStreamState);
  });
});
