import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildProtocolGateRunArtifacts, resolveProtocolGateRunRoot } from "./protocolGateRunArtifacts";

type RunnerOptions = {
  games: number;
  runRoot?: string;
  label?: string;
  seedBase?: number;
  gateArgs: string[];
};

const moduleDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(moduleDir, "../..");
const repoRoot = resolve(webRoot, "../..");

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  validateSeedArgs(options);
  const runRoot = resolveProtocolGateRunRoot(repoRoot, options.runRoot, options.label);

  for (let gameIndex = 1; gameIndex <= options.games; gameIndex += 1) {
    const artifacts = buildProtocolGateRunArtifacts({
      repoRoot,
      runRoot,
      gameIndex,
    });
    await mkdir(artifacts.gameDir, { recursive: true });
    const seedArgs = options.seedBase === undefined ? [] : ["--seed", String(options.seedBase + gameIndex)];
    const gateArgs = [
      ...options.gateArgs,
      ...seedArgs,
      "--out",
      artifacts.traceOut,
      "--replay-out",
      artifacts.replayOut,
      "--summary-out",
      artifacts.summaryOut,
    ];

    process.stderr.write(
      `PROTOCOL_GATE_GAME_START index=${gameIndex} dir=${artifacts.gameDir} summary=${artifacts.summaryOut}\n`,
    );
    const status = await runGate(gateArgs);
    process.stderr.write(`PROTOCOL_GATE_GAME_END index=${gameIndex} status=${status} dir=${artifacts.gameDir}\n`);
    if (status !== 0) {
      process.stderr.write(`PROTOCOL_GATE_FAIL_FAST index=${gameIndex} dir=${artifacts.gameDir}\n`);
      process.exitCode = status;
      return;
    }
  }

  process.stderr.write(`PROTOCOL_GATE_GAMES_PASSED games=${options.games} dir=${runRoot}\n`);
}

function parseArgs(args: string[]): RunnerOptions {
  const options: RunnerOptions = {
    games: 1,
    gateArgs: [],
  };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const next = args[index + 1];
    if (arg === "--games" && next) {
      options.games = Number(next);
      index += 1;
    } else if (arg === "--run-root" && next) {
      options.runRoot = next;
      index += 1;
    } else if (arg === "--label" && next) {
      options.label = next;
      index += 1;
    } else if (arg === "--seed-base" && next) {
      options.seedBase = Number(next);
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write(
        [
          "Usage: vite-node src/headless/runProtocolGateGames.ts --games 5 [runner options] -- [protocol gate options]",
          "",
          "Runner options:",
          "  --games 5",
          "  --run-root tmp/rl/full-stack-protocol/my-run",
          "  --label backend-timing-gate",
          "  --seed-base 2026051100",
          "",
          "The runner writes trace, replay, and summary artifacts with absolute paths.",
          "Do not pipe through tee for summary capture; use the generated summary.json files.",
        ].join("\n") + "\n",
      );
      process.exit(0);
    } else if (arg === "--") {
      options.gateArgs.push(...args.slice(index + 1));
      break;
    } else {
      options.gateArgs.push(arg);
    }
  }
  if (!Number.isInteger(options.games) || options.games <= 0) {
    throw new Error(`--games must be a positive integer: ${options.games}`);
  }
  if (options.seedBase !== undefined && !Number.isFinite(options.seedBase)) {
    throw new Error(`--seed-base must be a number: ${options.seedBase}`);
  }
  return options;
}

function validateSeedArgs(options: RunnerOptions): void {
  if (options.seedBase === undefined) {
    return;
  }
  if (options.gateArgs.includes("--seed")) {
    throw new Error("--seed-base cannot be combined with protocol gate --seed.");
  }
}

function runGate(args: string[]): Promise<number> {
  return new Promise((resolveStatus, reject) => {
    const child = spawn("npm", ["run", "rl:protocol-gate", "--", ...args], {
      cwd: webRoot,
      stdio: ["ignore", "inherit", "inherit"],
    });
    child.on("error", reject);
    child.on("close", (code, signal) => {
      if (signal) {
        reject(new Error(`protocol gate terminated by signal ${signal}`));
        return;
      }
      resolveStatus(code ?? 1);
    });
  });
}

void main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exitCode = 1;
});
