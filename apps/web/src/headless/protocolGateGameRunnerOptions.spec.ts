import { describe, expect, it } from "vitest";
import {
  buildProtocolGateGamesHelpText,
  parseProtocolGateGameRunnerArgs,
} from "./protocolGateGameRunnerOptions";

describe("protocolGateGameRunnerOptions", () => {
  it("keeps single-game progress visible by default", () => {
    const options = parseProtocolGateGameRunnerArgs(["--games", "1"]);

    expect(options.quietProgress).toBe(false);
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
      "5",
      "--quiet-progress",
      "--verbose-progress",
    ]);

    expect(options.quietProgress).toBe(false);
  });

  it("documents the file-first output policy", () => {
    expect(buildProtocolGateGamesHelpText()).toContain(
      "Multi-game runs suppress progress output by default",
    );
    expect(buildProtocolGateGamesHelpText()).toContain(
      "Failures emit PROTOCOL_GATE_FAILURE_POINTER",
    );
  });
});
