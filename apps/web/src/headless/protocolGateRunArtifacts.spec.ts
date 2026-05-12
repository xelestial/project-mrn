import { describe, expect, it } from "vitest";
import { buildProtocolGateRunArtifacts } from "./protocolGateRunArtifacts";

describe("protocolGateRunArtifacts", () => {
  it("resolves relative run roots from the repository root, not the npm package cwd", () => {
    const artifacts = buildProtocolGateRunArtifacts({
      repoRoot: "/repo/project-mrn",
      runRoot: "tmp/rl/protocol/test-run",
      gameIndex: 3,
    });

    expect(artifacts).toEqual({
      runRoot: "/repo/project-mrn/tmp/rl/protocol/test-run",
      gameDir: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3",
      rawDir: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/raw",
      summaryDir: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary",
      pointersDir: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/pointers",
      traceOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/raw/protocol_trace.jsonl",
      replayOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/raw/protocol_replay.jsonl",
      summaryOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/summary.json",
      backendLogOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/raw/backend_server.log",
      protocolLogOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/raw/protocol_gate.log",
      progressOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/raw/progress.ndjson",
      runStatusOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/run_status.json",
      progressSummaryOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/progress.json",
      slowestCommandOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/slowest_command.json",
      slowestTransitionOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/slowest_transition.json",
      gateResultOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/gate_result.json",
      failureReasonOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary/failure_reason.json",
      failurePointerOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/pointers/failure_pointer.json",
      suspectEventsOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/pointers/suspect_events.json",
      logOffsetsOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/pointers/log_offsets.json",
    });
  });

  it("keeps absolute run roots absolute", () => {
    const artifacts = buildProtocolGateRunArtifacts({
      repoRoot: "/repo/project-mrn",
      runRoot: "/var/tmp/mrn-run",
      gameIndex: 1,
    });

    expect(artifacts.summaryOut).toBe("/var/tmp/mrn-run/game-1/summary/summary.json");
    expect(artifacts.backendLogOut).toBe("/var/tmp/mrn-run/game-1/raw/backend_server.log");
    expect(artifacts.failurePointerOut).toBe("/var/tmp/mrn-run/game-1/pointers/failure_pointer.json");
  });

  it("rejects invalid game indexes before a run starts", () => {
    expect(() =>
      buildProtocolGateRunArtifacts({
        repoRoot: "/repo/project-mrn",
        runRoot: "tmp/run",
        gameIndex: 0,
      }),
    ).toThrow("gameIndex must be a positive integer");
  });
});
