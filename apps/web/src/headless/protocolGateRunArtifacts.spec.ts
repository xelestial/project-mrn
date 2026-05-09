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
      traceOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/protocol_trace.jsonl",
      replayOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/protocol_replay.jsonl",
      summaryOut: "/repo/project-mrn/tmp/rl/protocol/test-run/game-3/summary.json",
    });
  });

  it("keeps absolute run roots absolute", () => {
    const artifacts = buildProtocolGateRunArtifacts({
      repoRoot: "/repo/project-mrn",
      runRoot: "/var/tmp/mrn-run",
      gameIndex: 1,
    });

    expect(artifacts.summaryOut).toBe("/var/tmp/mrn-run/game-1/summary.json");
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
