import { describe, expect, it } from "vitest";

import type { InboundMessage } from "../../core/contracts/stream";
import { gameStreamReducer, initialGameStreamState } from "./gameStreamReducer";

function viewCommit(commitSeq: number, viewState: Record<string, unknown>): InboundMessage {
  return {
    type: "view_commit",
    seq: commitSeq,
    session_id: "sess_view_commit_1",
    server_time_ms: 1000 + commitSeq,
    payload: {
      schema_version: 1,
      commit_seq: commitSeq,
      source_event_seq: commitSeq - 1,
      viewer: { role: "spectator" },
      runtime: {
        status: "running",
        round_index: 1,
        turn_index: 0,
        active_frame_id: "frame-1",
        active_module_id: "module-1",
        active_module_type: "TestModule",
        module_path: ["frame-1", "module-1"],
      },
      view_state: viewState,
    },
  } as InboundMessage;
}

function event(seq: number, payload: Record<string, unknown>): InboundMessage {
  return {
    type: "event",
    seq,
    session_id: "sess_view_commit_1",
    server_time_ms: 1000 + seq,
    payload,
  };
}

describe("gameStreamReducer authoritative view commits", () => {
  it("keeps live state on the latest view_commit when a later event arrives", () => {
    const committed = gameStreamReducer(
      initialGameStreamState,
      { type: "message", message: viewCommit(10, { turn_stage: { round_index: 1 } }) }
    );

    const next = gameStreamReducer(committed, {
      type: "message",
      message: event(11, { event_type: "round_start", round_index: 2 }),
    });

    expect(next.messages).toHaveLength(1);
    expect(next.messages[0].type).toBe("view_commit");
    expect((next as any).lastCommitSeq).toBe(10);
    expect((next as any).latestCommit?.view_state).toEqual({ turn_stage: { round_index: 1 } });
    expect(next.debugMessages.map((message) => message.type)).toEqual(["view_commit", "event"]);
  });

  it("ignores stale view_commit payloads for live state", () => {
    const newest = gameStreamReducer(
      initialGameStreamState,
      { type: "message", message: viewCommit(20, { turn_stage: { round_index: 2 } }) }
    );

    const stale = gameStreamReducer(newest, {
      type: "message",
      message: viewCommit(19, { turn_stage: { round_index: 1 } }),
    });

    expect(stale.messages[0].seq).toBe(20);
    expect((stale as any).lastCommitSeq).toBe(20);
    expect((stale as any).latestCommit?.view_state).toEqual({ turn_stage: { round_index: 2 } });
  });

  it("accepts the same latest view_commit when live state is missing", () => {
    const damaged = {
      ...initialGameStreamState,
      lastCommitSeq: 12,
      messages: [],
      latestCommit: null,
    };

    const repaired = gameStreamReducer(damaged, {
      type: "message",
      message: viewCommit(12, { turn_stage: { round_index: 3 }, board: { tile_count: 40 } }),
    });

    expect(repaired.messages).toHaveLength(1);
    expect(repaired.messages[0].type).toBe("view_commit");
    expect((repaired as any).lastCommitSeq).toBe(12);
    expect((repaired as any).latestCommit?.view_state).toEqual({
      turn_stage: { round_index: 3 },
      board: { tile_count: 40 },
    });
  });

  it("does not let older repair commits overwrite a newer known commit sequence", () => {
    const damaged = {
      ...initialGameStreamState,
      lastCommitSeq: 12,
      messages: [],
      latestCommit: null,
    };

    const staleRepair = gameStreamReducer(damaged, {
      type: "message",
      message: viewCommit(11, { turn_stage: { round_index: 2 } }),
    });

    expect(staleRepair.messages).toHaveLength(0);
    expect((staleRepair as any).lastCommitSeq).toBe(12);
    expect((staleRepair as any).latestCommit).toBeNull();
  });
});
