export type ProtocolGateGameRunnerOptions = {
  games: number;
  concurrency: number;
  runRoot?: string;
  label?: string;
  seedBase?: number;
  quietProgress: boolean;
  helpRequested: boolean;
  baseUrlTemplate?: string;
  redisUrlTemplate?: string;
  backendDockerComposeProjectTemplate?: string;
  gateArgs: string[];
};

export function parseProtocolGateGameRunnerArgs(args: string[]): ProtocolGateGameRunnerOptions {
  const options: Omit<ProtocolGateGameRunnerOptions, "quietProgress"> & {
    quietProgress?: boolean;
  } = {
    games: 1,
    concurrency: 1,
    helpRequested: false,
    gateArgs: [],
  };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const next = args[index + 1];
    if (arg === "--games" && next) {
      options.games = Number(next);
      index += 1;
    } else if (arg === "--concurrency" && next) {
      options.concurrency = Number(next);
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
    } else if (arg === "--quiet-progress") {
      options.quietProgress = true;
    } else if (arg === "--verbose-progress") {
      options.quietProgress = false;
    } else if (arg === "--base-url-template" && next) {
      options.baseUrlTemplate = next;
      index += 1;
    } else if (arg === "--redis-url-template" && next) {
      options.redisUrlTemplate = next;
      index += 1;
    } else if (arg === "--backend-docker-compose-project-template" && next) {
      options.backendDockerComposeProjectTemplate = next;
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      options.helpRequested = true;
    } else if (arg === "--") {
      options.gateArgs.push(...args.slice(index + 1));
      break;
    } else {
      options.gateArgs.push(arg);
    }
  }
  if (options.helpRequested) {
    return {
      ...options,
      concurrency: Math.min(options.games, options.concurrency),
      quietProgress: options.quietProgress ?? options.games > 1,
    };
  }
  if (!Number.isInteger(options.games) || options.games <= 0) {
    throw new Error(`--games must be a positive integer: ${options.games}`);
  }
  if (!Number.isInteger(options.concurrency) || options.concurrency <= 0) {
    throw new Error(`--concurrency must be a positive integer: ${options.concurrency}`);
  }
  if (options.seedBase !== undefined && !Number.isFinite(options.seedBase)) {
    throw new Error(`--seed-base must be a number: ${options.seedBase}`);
  }
  return {
    ...options,
    concurrency: Math.min(options.games, options.concurrency),
    quietProgress: options.quietProgress ?? options.games > 1,
  };
}

export function buildProtocolGateGamesHelpText(): string {
  return [
    "Usage: vite-node src/headless/runProtocolGateGames.ts --games 5 [runner options] -- [protocol gate options]",
    "",
    "Runner options:",
    "  --games 5",
    "  --concurrency 5",
    "  --run-root tmp/rl/full-stack-protocol/my-run",
    "  --label backend-timing-gate",
    "  --seed-base 2026051100",
    "  --quiet-progress",
    "  --verbose-progress",
    "  --base-url-template http://127.0.0.1:910{game}",
    "  --redis-url-template redis://127.0.0.1:638{game}/0",
    "  --backend-docker-compose-project-template project-mrn-protocol-g{game}",
    "",
    "Template variables: {game} is 1-based, {index} is 1-based, and {zeroBased} is 0-based.",
    "The runner writes raw logs under game-N/raw, compact reports under game-N/summary, and inspection pointers under game-N/pointers.",
    "Single-game runs emit compact PROTOCOL_GATE_GAME_PROGRESS lines unless --quiet-progress is set.",
    "Multi-game runs suppress progress output by default; pass --verbose-progress only for focused investigation.",
    "Progress is always persisted to raw/progress.ndjson plus summary/progress.json.",
    "Failures emit PROTOCOL_GATE_FAILURE_POINTER and persist summary/failure_reason.json plus pointers/failure_pointer.json.",
    "Do not pipe through tee for summary capture; use summary/gate_result.json first and raw/protocol_gate.log only from a pointer.",
  ].join("\n");
}
