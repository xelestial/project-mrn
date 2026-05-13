import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildProtocolGateRunArtifacts, resolveProtocolGateRunRoot } from "./protocolGateRunArtifacts";
import {
  buildProtocolGateGamesHelpText,
  parseProtocolGateGameRunnerArgs,
  type ProtocolGateGameRunnerOptions,
} from "./protocolGateGameRunnerOptions";
import {
  buildProtocolGateFailurePointer,
  buildProtocolGateGameProgressRecord,
  formatProtocolGateFailurePointerLine,
  formatProtocolGateProgressLine,
  parseProtocolGateProgressLine,
  writeProtocolGateGateResultArtifacts,
  writeProtocolGateFailureSummaryArtifacts,
  writeProtocolGateFailurePointer,
  writeProtocolGateLatestProgressArtifacts,
  type ProtocolGateGameProgressRecord,
  type ProtocolGateProgressArtifacts,
} from "./protocolGateRunProgress";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(moduleDir, "../..");
const repoRoot = resolve(webRoot, "../..");

async function main(): Promise<void> {
  const options = parseProtocolGateGameRunnerArgs(process.argv.slice(2));
  if (options.helpRequested) {
    process.stdout.write(`${buildProtocolGateGamesHelpText()}\n`);
    process.exit(0);
  }
  validateSeedArgs(options);
  const runRoot = resolveProtocolGateRunRoot(repoRoot, options.runRoot, options.label);
  const activeRuns = new Set<AbortController>();
  let nextGameIndex = 1;
  let failedStatus = 0;

  async function runOne(gameIndex: number): Promise<void> {
    const artifacts = buildProtocolGateRunArtifacts({
      repoRoot,
      runRoot,
      gameIndex,
    });
    await Promise.all([
      mkdir(artifacts.rawDir, { recursive: true }),
      mkdir(artifacts.summaryDir, { recursive: true }),
      mkdir(artifacts.pointersDir, { recursive: true }),
    ]);
    const seedArgs = options.seedBase === undefined ? [] : ["--seed", String(options.seedBase + gameIndex)];
    const gameRuntime = buildGameRuntimeOverrides(options, gameIndex);
    const gateArgs = [
      ...options.gateArgs,
      ...seedArgs,
      ...defaultGateArgs(options.gateArgs, artifacts.backendLogOut),
      "--out",
      artifacts.traceOut,
      "--replay-out",
      artifacts.replayOut,
      "--summary-out",
      artifacts.summaryOut,
    ];
    const perGameGateArgs = applyGameGateArgOverrides(gateArgs, gameRuntime);

    process.stderr.write(
      `PROTOCOL_GATE_GAME_START index=${gameIndex} dir=${artifacts.gameDir} summary=${artifacts.summaryOut} log=${artifacts.protocolLogOut}${gameRuntime.redisUrl ? ` redis=${redactUrlCredentials(gameRuntime.redisUrl)}` : ""}\n`,
    );
    const abortController = new AbortController();
    activeRuns.add(abortController);
    let status = 1;
    let latestProgress: ProtocolGateGameProgressRecord | null = null;
    try {
      const result = await runGate(
        perGameGateArgs,
        gameRuntime.env,
        abortController,
        artifacts,
        gameIndex,
        options.quietProgress,
      );
      status = result.status;
      latestProgress = result.latestProgress;
    } finally {
      activeRuns.delete(abortController);
    }
    await writeProtocolGateGateResultArtifacts({
      gameIndex,
      status,
      artifacts,
      latestProgress,
    });
    process.stderr.write(`PROTOCOL_GATE_GAME_END index=${gameIndex} status=${status} dir=${artifacts.gameDir}\n`);
    if (status !== 0) {
      const pointer = await buildProtocolGateFailurePointer({
        gameIndex,
        status,
        artifacts,
        latestProgress,
      });
      await writeProtocolGateFailurePointer(pointer);
      await writeProtocolGateFailureSummaryArtifacts(pointer);
      process.stderr.write(`${formatProtocolGateFailurePointerLine(pointer)}\n`);
      process.stderr.write(`PROTOCOL_GATE_FAIL_FAST index=${gameIndex} dir=${artifacts.gameDir}\n`);
      failedStatus = status;
      for (const activeRun of activeRuns) {
        activeRun.abort();
      }
    }
  }

  async function worker(): Promise<void> {
    while (failedStatus === 0 && nextGameIndex <= options.games) {
      const gameIndex = nextGameIndex;
      nextGameIndex += 1;
      await runOne(gameIndex);
    }
  }

  const workers = Array.from(
    { length: Math.min(options.games, options.concurrency) },
    () => worker(),
  );
  await Promise.all(workers);

  if (failedStatus !== 0) {
    process.exitCode = failedStatus;
    return;
  }

  process.stderr.write(
    `PROTOCOL_GATE_GAMES_PASSED games=${options.games} concurrency=${options.concurrency} dir=${runRoot}\n`,
  );
}

function validateSeedArgs(options: ProtocolGateGameRunnerOptions): void {
  if (options.seedBase === undefined) {
    return;
  }
  if (options.gateArgs.includes("--seed")) {
    throw new Error("--seed-base cannot be combined with protocol gate --seed.");
  }
}

function defaultGateArgs(gateArgs: string[], backendLogOut: string): string[] {
  const args: string[] = [];
  if (!hasCliFlag(gateArgs, "--backend-log-out")) {
    args.push("--backend-log-out", backendLogOut);
  }
  return args;
}

type GameRuntimeOverrides = {
  baseUrl?: string;
  redisUrl?: string;
  backendDockerComposeProject?: string;
  env: NodeJS.ProcessEnv;
};

function buildGameRuntimeOverrides(options: ProtocolGateGameRunnerOptions, gameIndex: number): GameRuntimeOverrides {
  const redisUrl = options.redisUrlTemplate
    ? renderGameTemplate(options.redisUrlTemplate, gameIndex)
    : undefined;
  return {
    baseUrl: options.baseUrlTemplate ? renderGameTemplate(options.baseUrlTemplate, gameIndex) : undefined,
    redisUrl,
    backendDockerComposeProject: options.backendDockerComposeProjectTemplate
      ? renderGameTemplate(options.backendDockerComposeProjectTemplate, gameIndex)
      : undefined,
    env: redisUrl ? { MRN_REDIS_URL: redisUrl } : {},
  };
}

function applyGameGateArgOverrides(args: string[], overrides: GameRuntimeOverrides): string[] {
  let nextArgs = args;
  if (overrides.baseUrl) {
    nextArgs = withCliFlagValue(nextArgs, "--base-url", overrides.baseUrl);
  }
  if (overrides.backendDockerComposeProject) {
    nextArgs = withCliFlagValue(
      nextArgs,
      "--backend-docker-compose-project",
      overrides.backendDockerComposeProject,
    );
  }
  return nextArgs;
}

function renderGameTemplate(template: string, gameIndex: number): string {
  return template
    .replaceAll("{game}", String(gameIndex))
    .replaceAll("{index}", String(gameIndex))
    .replaceAll("{zeroBased}", String(gameIndex - 1));
}

function withCliFlagValue(args: string[], flag: string, value: string): string[] {
  const nextArgs: string[] = [];
  let replaced = false;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === flag) {
      nextArgs.push(flag, value);
      index += 1;
      replaced = true;
    } else if (arg.startsWith(`${flag}=`)) {
      nextArgs.push(`${flag}=${value}`);
      replaced = true;
    } else {
      nextArgs.push(arg);
    }
  }
  if (!replaced) {
    nextArgs.push(flag, value);
  }
  return nextArgs;
}

function redactUrlCredentials(value: string): string {
  try {
    const url = new URL(value);
    if (url.username) {
      url.username = "***";
    }
    if (url.password) {
      url.password = "***";
    }
    return url.toString();
  } catch {
    return value;
  }
}

function hasCliFlag(args: string[], flag: string): boolean {
  return args.includes(flag) || args.some((arg) => arg.startsWith(`${flag}=`));
}

function runGate(
  args: string[],
  env: NodeJS.ProcessEnv,
  abortController: AbortController,
  artifacts: ProtocolGateProgressArtifacts,
  gameIndex: number,
  quietProgress: boolean,
): Promise<{ status: number; latestProgress: ProtocolGateGameProgressRecord | null }> {
  return new Promise((resolveStatus, reject) => {
    const protocolLog = createWriteStream(artifacts.protocolLogOut, { flags: "w" });
    const progressLog = createWriteStream(artifacts.progressOut, { flags: "w" });
    let latestProgress: ProtocolGateGameProgressRecord | null = null;
    const observeChildOutput = createChildOutputObserver({
      gameIndex,
      artifacts,
      protocolLog,
      progressLog,
      quietProgress,
      onProgress: (record) => {
        latestProgress = record;
      },
    });
    let settled = false;
    const settle = (status: number | undefined, error?: unknown): void => {
      if (settled) {
        return;
      }
      settled = true;
      observeChildOutput.flush().then(
        () => {
          progressLog.end(() => {
            protocolLog.end(() => {
              if (error) {
                reject(error);
                return;
              }
              resolveStatus({ status: status ?? 1, latestProgress });
            });
          });
        },
        (flushError: unknown) => {
          progressLog.end(() => {
            protocolLog.end(() => reject(flushError));
          });
        });
    };

    protocolLog.on("error", (error) => {
      if (settled) {
        return;
      }
      settled = true;
      reject(error);
    });

    const child = spawn("npm", ["run", "rl:protocol-gate", "--", ...args], {
      cwd: webRoot,
      env: { ...process.env, ...env },
      stdio: ["ignore", "pipe", "pipe"],
      signal: abortController.signal,
    });
    child.stdout?.on("data", observeChildOutput.write);
    child.stderr?.on("data", observeChildOutput.write);
    child.on("error", (error) => {
      if (abortController.signal.aborted && error.name === "AbortError") {
        settle(130);
        return;
      }
      settle(undefined, error);
    });
    child.on("close", (code, signal) => {
      if (signal) {
        if (abortController.signal.aborted) {
          settle(130);
          return;
        }
        settle(undefined, new Error(`protocol gate terminated by signal ${signal}`));
        return;
      }
      settle(code ?? 1);
    });
  });
}

function createChildOutputObserver(args: {
  gameIndex: number;
  artifacts: ProtocolGateProgressArtifacts;
  protocolLog: NodeJS.WritableStream;
  progressLog: NodeJS.WritableStream;
  quietProgress: boolean;
  onProgress: (record: ProtocolGateGameProgressRecord) => void;
}): {
  write: (chunk: Buffer | string) => void;
  flush: () => Promise<void>;
} {
  let pendingLine = "";
  let writeChain = Promise.resolve();

  const consumeLine = (line: string): void => {
    const progress = parseProtocolGateProgressLine(line);
    if (!progress) {
      return;
    }
    const record = buildProtocolGateGameProgressRecord({
      gameIndex: args.gameIndex,
      artifacts: args.artifacts,
      progress,
    });
    args.progressLog.write(`${JSON.stringify(record)}\n`);
    writeChain = writeChain.then(() => writeProtocolGateLatestProgressArtifacts(record));
    if (!args.quietProgress) {
      process.stderr.write(`${formatProtocolGateProgressLine(record)}\n`);
    }
    args.onProgress(record);
  };

  return {
    write: (chunk) => {
      const text = Buffer.isBuffer(chunk) ? chunk.toString("utf8") : chunk;
      args.protocolLog.write(text);
      pendingLine += text;
      const lines = pendingLine.split(/\r?\n/);
      pendingLine = lines.pop() ?? "";
      for (const line of lines) {
        consumeLine(line);
      }
    },
    flush: async () => {
      if (!pendingLine) {
        await writeChain;
        return;
      }
      consumeLine(pendingLine);
      pendingLine = "";
      await writeChain;
    },
  };
}

void main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exitCode = 1;
});
