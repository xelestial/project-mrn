import { describe, expect, it } from "vitest";
import {
  buildProtocolGateGamesHelpText,
  parseProtocolGateGameRunnerArgs,
} from "./protocolGateGameRunnerOptions";

describe("protocolGateGameRunnerOptions", () => {
  it("suppresses progress output by default for single-game runs", () => {
    const options = parseProtocolGateGameRunnerArgs(["--games", "1"]);

    expect(options.quietProgress).toBe(true);
  });

  it("suppresses progress output by default for multi-game runs", () => {
    const options = parseProtocolGateGameRunnerArgs(["--games", "5", "--concurrency", "5"]);

    expect(options.quietProgress).toBe(true);
  });

  it("suppresses progress output for sequential multi-game runs too", () => {
    const options = parseProtocolGateGameRunnerArgs(["--games", "2", "--concurrency", "1"]);

    expect(options.quietProgress).toBe(true);
  });

  it("allows explicit progress verbosity for investigation runs", () => {
    const options = parseProtocolGateGameRunnerArgs([
      "--games",
      "1",
      "--quiet-progress",
      "--verbose-progress",
    ]);

    expect(options.quietProgress).toBe(false);
  });

  it("documents the file-first output policy", () => {
    expect(buildProtocolGateGamesHelpText()).toContain(
      "Progress output is suppressed by default",
    );
    expect(buildProtocolGateGamesHelpText()).toContain(
      "Failures emit PROTOCOL_GATE_FAILURE_POINTER",
    );
  });
});
