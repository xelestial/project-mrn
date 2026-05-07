import { describe, expect, it } from "vitest";

import type { InboundMessage } from "../../core/contracts/stream";
import { gameStreamReducer, initialGameStreamState } from "./gameStreamReducer";

function viewCommit(
  commitSeq: number,
  viewState: Record<string, unknown>,
  options: { seq?: number; serverTimeMs?: number } = {},
): InboundMessage {
  const seq = options.seq ?? commitSeq;
  return {
    type: "view_commit",
    seq,
    session_id: "sess_view_commit_1",
    server_time_ms: options.serverTimeMs ?? 1000 + seq,
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

function snapshotPulse(
  commitSeq: number,
  viewState: Record<string, unknown>,
  options: { seq?: number; serverTimeMs?: number } = {},
): InboundMessage {
  const seq = options.seq ?? commitSeq;
  return {
    ...viewCommit(commitSeq, viewState, options),
    type: "snapshot_pulse",
    seq,
    server_time_ms: options.serverTimeMs ?? 1000 + seq,
    payload: {
      ...viewCommit(commitSeq, viewState, options).payload,
      snapshot_pulse: {
        reason: "turn_start_guardrail",
        scope: "player",
        target_player_id: 1,
      },
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

  it("accepts same-commit repair when the server sends a later stream message", () => {
    const committed = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: viewCommit(12, { prompt: { active: { request_id: "old" } } }, { seq: 40 }),
    });

    const repaired = gameStreamReducer(committed, {
      type: "message",
      message: viewCommit(12, { prompt: { active: null }, board: { tile_count: 40 } }, { seq: 42 }),
    });

    expect(repaired.messages.map((message) => message.seq)).toEqual([42]);
    expect((repaired as any).lastCommitSeq).toBe(12);
    expect((repaired as any).latestCommit?.view_state).toEqual({
      prompt: { active: null },
      board: { tile_count: 40 },
    });
  });

  it("accepts snapshot_pulse as same-commit live repair", () => {
    const committed = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: viewCommit(12, { prompt: { active: { request_id: "old" } } }, { seq: 40 }),
    });

    const repaired = gameStreamReducer(committed, {
      type: "message",
      message: snapshotPulse(12, { prompt: { active: null }, board: { tile_count: 40 } }, { seq: 42 }),
    });

    expect(repaired.messages.map((message) => message.seq)).toEqual([42]);
    expect(repaired.messages[0].type).toBe("view_commit");
    expect(repaired.debugMessages.at(-1)?.type).toBe("snapshot_pulse");
    expect((repaired as any).lastCommitSeq).toBe(12);
    expect((repaired as any).latestCommit?.view_state).toEqual({
      prompt: { active: null },
      board: { tile_count: 40 },
    });
  });

  it("ignores same-commit repair when it has a lower stream seq even with a newer timestamp", () => {
    const committed = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: viewCommit(12, { prompt: { active: { request_id: "old" } } }, { seq: 40, serverTimeMs: 5000 }),
    });

    const stale = gameStreamReducer(committed, {
      type: "message",
      message: viewCommit(12, { prompt: { active: null } }, { seq: 12, serverTimeMs: 6000 }),
    });

    expect(stale.messages.map((message) => message.seq)).toEqual([40]);
    expect((stale as any).latestCommit?.view_state).toEqual({ prompt: { active: { request_id: "old" } } });
  });

  it("ignores older same-commit payloads", () => {
    const committed = gameStreamReducer(initialGameStreamState, {
      type: "message",
      message: viewCommit(12, { prompt: { active: null } }, { seq: 40, serverTimeMs: 5000 }),
    });

    const stale = gameStreamReducer(committed, {
      type: "message",
      message: viewCommit(
        12,
        { prompt: { active: { request_id: "stale" } } },
        { seq: 12, serverTimeMs: 4000 },
      ),
    });

    expect(stale.messages.map((message) => message.seq)).toEqual([40]);
    expect((stale as any).latestCommit?.view_state).toEqual({ prompt: { active: null } });
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
