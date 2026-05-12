import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import {
  appendProtocolGateProgressRecord,
  buildProtocolGateFailurePointer,
  buildProtocolGateGameProgressRecord,
  formatProtocolGateFailurePointerLine,
  formatProtocolGateProgressLine,
  parseProtocolGateProgressLine,
  writeProtocolGateGateResultArtifacts,
  writeProtocolGateFailureSummaryArtifacts,
  writeProtocolGateFailurePointer,
  writeProtocolGateLatestProgressArtifacts,
  type ProtocolGateProgressArtifacts,
} from "./protocolGateRunProgress";

function artifacts(root: string): ProtocolGateProgressArtifacts {
  return {
    gameDir: root,
    summaryOut: join(root, "summary.json"),
    protocolLogOut: join(root, "protocol_gate.log"),
    backendLogOut: join(root, "backend_server.log"),
    progressOut: join(root, "progress.ndjson"),
    runStatusOut: join(root, "summary", "run_status.json"),
    progressSummaryOut: join(root, "summary", "progress.json"),
    slowestCommandOut: join(root, "summary", "slowest_command.json"),
    slowestTransitionOut: join(root, "summary", "slowest_transition.json"),
    gateResultOut: join(root, "summary", "gate_result.json"),
    failureReasonOut: join(root, "summary", "failure_reason.json"),
    failurePointerOut: join(root, "pointers", "failure_pointer.json"),
    suspectEventsOut: join(root, "pointers", "suspect_events.json"),
    logOffsetsOut: join(root, "pointers", "log_offsets.json"),
  };
}

describe("protocolGateRunProgress", () => {
  it("turns verbose child progress JSON into compact game progress records", async () => {
    const root = await mkdtemp(join(tmpdir(), "mrn-progress-"));
    const parsed = parseProtocolGateProgressLine(JSON.stringify({
      event: "protocol_gate_progress",
      session_id: "sess_progress",
      elapsed_ms: 12_345,
      idle_ms: 2_000,
      runtime_status: "waiting_input",
      trace_count: 99,
      pace: {
        maxCommitSeq: 42,
        latestRoundIndex: 2,
        latestTurnIndex: 7,
        activePromptPlayerId: 3,
        activePromptRequestId: "req_buy",
        activePromptRequestType: "purchase_tile",
        latestDecisionRequestId: "req_roll",
        latestAckStatus: "accepted",
        slowestCommandLatencies: [
          { requestId: "req_buy", promptToDecisionMs: 120, decisionToAckMs: 240, totalMs: 360 },
        ],
      },
      seats: [
        { player_id: 1, commit_seq: 41, accepted: 4, stale: 1, rejected: 0, errors: 0, fallbacks: 0 },
        { player_id: 3, commit_seq: 42, accepted: 5, stale: 0, rejected: 1, errors: 2, fallbacks: 1 },
      ],
    }));

    expect(parsed).not.toBeNull();
    const record = buildProtocolGateGameProgressRecord({
      gameIndex: 4,
      artifacts: artifacts(root),
      progress: parsed!,
    });

    expect(record).toMatchObject({
      event: "protocol_gate_game_progress",
      game_id: 4,
      session_id: "sess_progress",
      elapsed_s: 12.3,
      idle_s: 2,
      runtime_status: "waiting_input",
      round: 2,
      turn: 7,
      active_player_id: 3,
      active_request_id: "req_buy",
      active_request_type: "purchase_tile",
      latest_commit_seq: 42,
      command_count: 9,
      stale_count: 1,
      rejected_count: 1,
      failed_count: 2,
      fallback_count: 1,
      max_command_ms: 360,
      latest_decision_request_id: "req_roll",
      latest_ack_status: "accepted",
      trace_count: 99,
    });

    await appendProtocolGateProgressRecord(record);
    const progressFile = await readFile(record.artifacts.progressOut, "utf8");
    expect(JSON.parse(progressFile)).toMatchObject({ game_id: 4, active_request_id: "req_buy" });
    await writeProtocolGateLatestProgressArtifacts(record);
    expect(JSON.parse(await readFile(record.artifacts.runStatusOut, "utf8"))).toMatchObject({
      event: "protocol_gate_run_status",
      game_id: 4,
      session_id: "sess_progress",
      elapsed_ms: 12_345,
      latest_commit_seq: 42,
      max_command_ms: 360,
    });
    expect(JSON.parse(await readFile(record.artifacts.progressSummaryOut, "utf8"))).toMatchObject({
      event: "protocol_gate_progress_summary",
      game_id: 4,
      active_request_id: "req_buy",
      command_count: 9,
    });
    expect(JSON.parse(await readFile(record.artifacts.slowestCommandOut, "utf8"))).toMatchObject({
      event: "protocol_gate_slowest_command",
      game_id: 4,
      max_command_ms: 360,
      active_request_id: "req_buy",
    });
    expect(formatProtocolGateProgressLine(record)).toBe(
      "PROTOCOL_GATE_GAME_PROGRESS game=4 elapsed=12.3s idle=2s status=waiting_input round=2 turn=7 player=3 request=purchase_tile commit=42 commands=9 stale=1 rejected=1 failed=2 fallback=1 max_command_ms=360",
    );
  });

  it("writes a failure pointer that tells the operator where to inspect next", async () => {
    const root = await mkdtemp(join(tmpdir(), "mrn-failure-pointer-"));
    const paths = artifacts(root);
    await writeFile(paths.summaryOut, JSON.stringify({
      session_id: "sess_fail",
      duration_ms: 88_000,
      runtime_status: "waiting_input",
      failures: [
        "repeated active prompt signature exceeded 8: player=2 request_type=trick_to_use last_commit_seq=69 request_ids=trick_to_use:2",
      ],
      clients: {
        "seat:2": { lastCommitSeq: 69, metrics: { acceptedAckCount: 12 } },
      },
    }));

    const pointer = await buildProtocolGateFailurePointer({
      gameIndex: 2,
      status: 1,
      artifacts: paths,
      latestProgress: null,
    });
    await writeProtocolGateFailurePointer(pointer);
    await writeProtocolGateFailureSummaryArtifacts(pointer);

    expect(pointer).toMatchObject({
      event: "protocol_gate_failure_pointer",
      failure_type: "prompt_repetition",
      game_id: 2,
      status: 1,
      session_id: "sess_fail",
      request_id: "trick_to_use:2",
      commit_seq: 69,
      elapsed_ms: 88_000,
      runtime_status: "waiting_input",
    });
    expect(pointer.log_hint).toContain(paths.summaryOut);
    expect(pointer.log_hint).toContain("request_id=trick_to_use:2");
    expect(formatProtocolGateFailurePointerLine(pointer)).toContain("type=prompt_repetition");
    expect(formatProtocolGateFailurePointerLine(pointer)).toContain(`pointer=${paths.failurePointerOut}`);
    const pointerFile = await readFile(paths.failurePointerOut, "utf8");
    expect(JSON.parse(pointerFile)).toMatchObject({ failure_type: "prompt_repetition" });
    expect(JSON.parse(await readFile(paths.failureReasonOut, "utf8"))).toMatchObject({
      event: "protocol_gate_failure_reason",
      failure_type: "prompt_repetition",
      session_id: "sess_fail",
      request_id: "trick_to_use:2",
      commit_seq: 69,
    });
    expect(JSON.parse(await readFile(paths.suspectEventsOut, "utf8"))).toMatchObject({
      event: "protocol_gate_suspect_events",
      failure_type: "prompt_repetition",
      raw_logs: {
        backend: paths.backendLogOut,
        protocol: paths.protocolLogOut,
        progress: paths.progressOut,
      },
    });
  });

  it("classifies browser-observed command latency failures", async () => {
    const root = await mkdtemp(join(tmpdir(), "mrn-protocol-latency-"));
    const paths = artifacts(root);
    await writeFile(paths.summaryOut, JSON.stringify({
      session_id: "sess_latency",
      duration_ms: 45_000,
      runtime_status: "waiting_input",
      failures: [
        "protocol command latency exceeded 5000ms request_id=req_slow request_type=burden_exchange player_id=2 max_ms=9899 total_ms=9899 prompt_to_decision_ms=9 decision_to_ack_ms=9890 status=accepted",
      ],
      clients: {
        "seat:2": { lastCommitSeq: 304, metrics: { acceptedAckCount: 21 } },
      },
    }));

    const pointer = await buildProtocolGateFailurePointer({
      gameIndex: 7,
      status: 1,
      artifacts: paths,
      latestProgress: null,
    });

    expect(pointer).toMatchObject({
      failure_type: "protocol_latency",
      session_id: "sess_latency",
      request_id: "req_slow",
      commit_seq: 304,
    });
    expect(formatProtocolGateFailurePointerLine(pointer)).toContain("type=protocol_latency");
  });

  it("writes final gate and slowest backend summaries without requiring raw log reads", async () => {
    const root = await mkdtemp(join(tmpdir(), "mrn-gate-result-"));
    const paths = artifacts(root);
    await writeFile(paths.summaryOut, JSON.stringify({
      ok: true,
      session_id: "sess_pass",
      duration_ms: 204_177,
      runtime_status: "completed",
      failures: [],
      backend_timing: {
        maxCommandMs: 977,
        maxTransitionMs: 4387,
        maxRedisCommitCount: 1,
        maxViewCommitCount: 1,
      },
      protocol_latency: {
        maxCommandMs: 4270,
      },
    }));

    await writeProtocolGateGateResultArtifacts({
      gameIndex: 1,
      status: 0,
      artifacts: paths,
      latestProgress: null,
    });

    expect(JSON.parse(await readFile(paths.gateResultOut, "utf8"))).toMatchObject({
      event: "protocol_gate_result",
      ok: true,
      status: 0,
      session_id: "sess_pass",
      duration_ms: 204_177,
      failures: [],
      summary: paths.summaryOut,
      raw_logs: {
        backend: paths.backendLogOut,
        protocol: paths.protocolLogOut,
        progress: paths.progressOut,
      },
    });
    expect(JSON.parse(await readFile(paths.slowestTransitionOut, "utf8"))).toMatchObject({
      event: "protocol_gate_slowest_transition",
      game_id: 1,
      session_id: "sess_pass",
      max_transition_ms: 4387,
      max_command_ms: 977,
      max_redis_commit_count: 1,
      max_view_commit_count: 1,
    });
  });
});
