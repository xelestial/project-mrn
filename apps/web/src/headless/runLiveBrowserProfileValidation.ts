import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { chromium, type Page } from "@playwright/test";
import {
  baselineDecisionPolicy,
  conservativeDecisionPolicy,
  createResourceFocusedDecisionPolicy,
  HeadlessGameClient,
  type DecisionPolicy,
  type HeadlessMetrics,
} from "./HeadlessGameClient";
import {
  buildHeadlessHumanSessionPayload,
  createProtocolSession,
  joinProtocolSeats,
  startProtocolSession,
} from "./fullStackProtocolHarness";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:9091";
const DEFAULT_WEB_BASE_URL = "http://127.0.0.1:9000";
const DEFAULT_TIMEOUT_MS = 300_000;
const DEFAULT_IDLE_TIMEOUT_MS = 60_000;
const POLL_MS = 1_000;

type RecordValue = Record<string, unknown>;

type BrowserSnapshot = {
  textLength: number;
  boardVisible: boolean;
  promptOverlayVisible: boolean;
  spectatorPromptVisible: boolean;
  activeCharacterStripVisible: boolean;
  turnHistoryVisible: boolean;
  playerCardCount: number;
  turnHistoryEventCount: number;
  manifestHash: string | null;
  turnBanner: string | null;
};

type PolicyProfile = {
  label: string;
  policy: DecisionPolicy;
};

type ClientSummary = {
  label: string;
  playerId: number;
  status: string;
  lastCommitSeq: number;
  metrics: HeadlessMetrics;
};

function intFromEnv(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? Math.trunc(value) : fallback;
}

function boolFromEnv(name: string): boolean {
  const value = String(process.env[name] ?? "").trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

function stringFromEnv(name: string, fallback: string): string {
  const value = String(process.env[name] ?? "").trim();
  return value || fallback;
}

function buildUrl(baseUrl: string, path: string): string {
  return new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`).toString();
}

function isRecord(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function apiJson(baseUrl: string, path: string): Promise<RecordValue> {
  const response = await fetch(buildUrl(baseUrl, path), {
    headers: { "content-type": "application/json" },
  });
  const bodyText = await response.text();
  let body: unknown;
  try {
    body = bodyText ? JSON.parse(bodyText) : {};
  } catch (error) {
    throw new Error(`API returned non-JSON ${response.status} for ${path}: ${bodyText.slice(0, 300)}`, {
      cause: error,
    });
  }
  if (!response.ok || (isRecord(body) && body.ok === false)) {
    throw new Error(`API failed ${response.status} for ${path}: ${JSON.stringify(body)}`);
  }
  if (isRecord(body) && isRecord(body.data)) {
    return body.data;
  }
  return isRecord(body) ? body : {};
}

async function latestViewCommit(apiBaseUrl: string, sessionId: string): Promise<RecordValue | null> {
  try {
    return await apiJson(apiBaseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/view-commit`);
  } catch (error) {
    if (String(error instanceof Error ? error.message : error).includes("VIEW_COMMIT_NOT_FOUND")) {
      return null;
    }
    throw error;
  }
}

async function runtimeStatus(apiBaseUrl: string, sessionId: string): Promise<string | null> {
  const data = await apiJson(apiBaseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/runtime-status`);
  const runtime = isRecord(data.runtime) ? data.runtime : {};
  return typeof runtime.status === "string" ? runtime.status : null;
}

async function browserSnapshot(page: Page): Promise<BrowserSnapshot> {
  return page.evaluate(() => {
    const root = document.querySelector("#root") ?? document.body;
    const visibleText =
      root instanceof HTMLElement
        ? root.innerText.replace(/\s+/g, " ").trim()
        : (root.textContent ?? "").replace(/\s+/g, " ").trim();
    const manifest = document.querySelector("[data-testid='runtime-manifest-metadata']");
    const turnBanner = document.querySelector("[data-testid='turn-notice-banner-title']");
    const historyEvents = document.querySelectorAll("[data-testid^='turn-history-event-']");
    return {
      textLength: visibleText.length,
      boardVisible: Boolean(document.querySelector("[data-testid='board-panel'], .board-panel")),
      promptOverlayVisible: Boolean(document.querySelector("[data-testid='prompt-overlay'], .prompt-overlay")),
      spectatorPromptVisible: Boolean(document.querySelector("[data-testid='spectator-turn-prompt']")),
      activeCharacterStripVisible: Boolean(document.querySelector("[data-testid='active-character-strip']")),
      turnHistoryVisible: Boolean(document.querySelector("[data-testid='turn-history-tabs']")),
      playerCardCount: document.querySelectorAll("[data-testid^='match-player-card-']").length,
      turnHistoryEventCount: historyEvents.length,
      manifestHash: manifest instanceof HTMLElement ? manifest.dataset.manifestHash ?? null : null,
      turnBanner: turnBanner instanceof HTMLElement ? turnBanner.innerText.replace(/\s+/g, " ").trim() : null,
    };
  });
}

async function revealTurnHistory(page: Page): Promise<void> {
  const historyTab = page.getByRole("tab", { name: /^(History|히스토리)$/ });
  if ((await historyTab.count()) > 0) {
    await historyTab.first().click();
    await page.waitForTimeout(250);
  }
}

function browserSignature(snapshot: BrowserSnapshot): string {
  return JSON.stringify({
    boardVisible: snapshot.boardVisible,
    promptOverlayVisible: snapshot.promptOverlayVisible,
    spectatorPromptVisible: snapshot.spectatorPromptVisible,
    activeCharacterStripVisible: snapshot.activeCharacterStripVisible,
    turnHistoryVisible: snapshot.turnHistoryVisible,
    playerCardCount: snapshot.playerCardCount,
    turnHistoryEventCount: snapshot.turnHistoryEventCount,
    manifestHash: snapshot.manifestHash,
    turnBanner: snapshot.turnBanner,
  });
}

function policyProfiles(): PolicyProfile[] {
  return [
    { label: "baseline", policy: baselineDecisionPolicy },
    { label: "cash-focus", policy: createResourceFocusedDecisionPolicy("cash") },
    { label: "shard-focus", policy: createResourceFocusedDecisionPolicy("shard") },
    { label: "conservative", policy: conservativeDecisionPolicy },
  ];
}

function clientFailures(clients: HeadlessGameClient[]): string[] {
  const failures: string[] = [];
  for (const client of clients) {
    const label = `P${client.playerId}`;
    const metrics = client.metrics;
    if (metrics.errorMessageCount > 0) failures.push(`${label} headless client errors=${metrics.errorMessageCount}`);
    if (metrics.identityViolationCount > 0) failures.push(`${label} identity violations=${metrics.identityViolationCount}`);
    if (metrics.nonMonotonicCommitCount > 0) failures.push(`${label} non-monotonic commits=${metrics.nonMonotonicCommitCount}`);
    if (metrics.semanticCommitRegressionCount > 0) {
      failures.push(`${label} semantic commit regressions=${metrics.semanticCommitRegressionCount}`);
    }
    if (metrics.reconnectRecoveryPendingCount > 0) {
      failures.push(`${label} pending reconnect recoveries=${metrics.reconnectRecoveryPendingCount}`);
    }
    if (metrics.spectatorPromptLeakCount > 0) failures.push(`${label} spectator prompt leaks=${metrics.spectatorPromptLeakCount}`);
    if (metrics.spectatorDecisionAckLeakCount > 0) {
      failures.push(`${label} spectator decision ack leaks=${metrics.spectatorDecisionAckLeakCount}`);
    }
    if (metrics.outboundDecisionCount <= 0) failures.push(`${label} sent no policy decisions`);
  }
  return failures;
}

function summarizeClients(clients: Array<{ label: string; client: HeadlessGameClient }>): ClientSummary[] {
  return clients.map(({ label, client }) => ({
    label,
    playerId: client.playerId,
    status: client.status,
    lastCommitSeq: client.state.lastCommitSeq,
    metrics: client.metrics,
  }));
}

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function main(): Promise<void> {
  const apiBaseUrl = stringFromEnv("MRN_API_BASE_URL", DEFAULT_API_BASE_URL);
  const webBaseUrl = stringFromEnv("MRN_WEB_BASE_URL", DEFAULT_WEB_BASE_URL);
  const seed = intFromEnv("MRN_LIVE_PROFILE_SEED", Math.floor(Math.random() * 2_147_483_647));
  const timeoutMs = intFromEnv("MRN_LIVE_PROFILE_TIMEOUT_MS", DEFAULT_TIMEOUT_MS);
  const idleTimeoutMs = intFromEnv("MRN_LIVE_PROFILE_IDLE_MS", DEFAULT_IDLE_TIMEOUT_MS);
  const boundedEndRules = boolFromEnv("MRN_LIVE_PROFILE_BOUNDED");
  const outPath = resolve(
    stringFromEnv(
      "MRN_LIVE_PROFILE_OUT",
      `tmp/rl/full-stack-protocol/live-browser-profile-${Date.now()}.json`,
    ),
  );
  const screenshotPath = outPath.replace(/\.json$/i, ".png");
  const startedAtMs = Date.now();
  const profiles = policyProfiles();
  const payload = buildHeadlessHumanSessionPayload({
    seed,
    seatCount: profiles.length,
    config: boundedEndRules
      ? {
          rules: {
            end: {
              f_threshold: 1,
              monopolies_to_trigger_end: 0,
              tiles_to_trigger_end: 1,
              alive_players_at_most: 1,
            },
          },
        }
      : {},
  });

  const browser = await chromium.launch({ headless: process.env.MRN_HEADLESS !== "0" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  await page.addInitScript((serverBaseUrl) => {
    window.sessionStorage.setItem("mrn:roomServer", serverBaseUrl);
  }, apiBaseUrl);
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.stack || error.message);
  });

  const clients: Array<{ label: string; client: HeadlessGameClient }> = [];
  let sessionId = "";
  let latestSnapshot: BrowserSnapshot | null = null;
  let lastCommitSeq = 0;
  let lastProgressAtMs = Date.now();
  let lastSignature = "";
  let reconnectForced = false;

  try {
    const session = await createProtocolSession(apiBaseUrl, payload);
    sessionId = session.sessionId;
    const seats = await joinProtocolSeats(apiBaseUrl, session);
    const matchUrl = `${webBaseUrl.replace(/\/$/, "")}/#/match?session=${encodeURIComponent(session.sessionId)}`;
    await page.goto(matchUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });

    for (const [index, seat] of seats.entries()) {
      const profile = profiles[index] ?? profiles[0];
      const client = new HeadlessGameClient({
        sessionId: session.sessionId,
        token: seat.token,
        playerId: seat.playerId,
        policy: profile.policy,
        baseUrl: apiBaseUrl,
        failOnIllegal: true,
        autoReconnect: true,
      });
      clients.push({ label: `${profile.label}:P${seat.playerId}`, client });
      client.connect();
    }

    await startProtocolSession(apiBaseUrl, session.sessionId, session.hostToken);

    while (true) {
      await page.waitForTimeout(POLL_MS);
      const [commit, status, snapshot] = await Promise.all([
        latestViewCommit(apiBaseUrl, session.sessionId),
        runtimeStatus(apiBaseUrl, session.sessionId),
        browserSnapshot(page),
      ]);
      latestSnapshot = snapshot;
      const commitSeq = Number(commit?.commit_seq ?? lastCommitSeq);
      const signature = browserSignature(snapshot);
      const hasProgress =
        (Number.isFinite(commitSeq) && commitSeq > lastCommitSeq) ||
        (signature !== lastSignature && snapshot.boardVisible);
      if (hasProgress) {
        lastProgressAtMs = Date.now();
        lastCommitSeq = Math.max(lastCommitSeq, Number.isFinite(commitSeq) ? commitSeq : lastCommitSeq);
        lastSignature = signature;
      }

      if (!reconnectForced && lastCommitSeq > 0 && clients.every(({ client }) => client.metrics.outboundDecisionCount > 0)) {
        for (const { client } of clients) {
          client.forceReconnect("phase6_browser_profile_validation");
        }
        reconnectForced = true;
      }

      if (Date.now() - lastProgressAtMs > idleTimeoutMs) {
        throw new Error(
          `live_browser_profile_idle_timeout session=${session.sessionId} seed=${seed} commit_seq=${lastCommitSeq}`,
        );
      }
      if (Date.now() - startedAtMs > timeoutMs) {
        throw new Error(
          `live_browser_profile_timeout session=${session.sessionId} seed=${seed} commit_seq=${lastCommitSeq} runtime=${status ?? "unknown"}`,
        );
      }
      if (status === "failed") {
        throw new Error(`runtime_failed session=${session.sessionId} seed=${seed}`);
      }
      if (status === "completed") {
        await revealTurnHistory(page);
        latestSnapshot = await browserSnapshot(page);
        await page.screenshot({ path: screenshotPath, fullPage: true });
        break;
      }
    }

    const failures = [
      ...clientFailures(clients.map(({ client }) => client)),
      ...consoleErrors.map((item) => `browser console error: ${item}`),
      ...pageErrors.map((item) => `browser page error: ${item}`),
    ];
    if (!latestSnapshot?.boardVisible) failures.push("browser board panel was not visible");
    if (!latestSnapshot?.activeCharacterStripVisible) failures.push("browser active character strip was not visible");
    if (!latestSnapshot?.turnHistoryVisible) failures.push("browser turn history was not visible");
    if ((latestSnapshot?.playerCardCount ?? 0) < profiles.length) failures.push("browser did not render all player cards");
    if (latestSnapshot?.promptOverlayVisible) failures.push("spectator browser rendered a private prompt overlay");
    if ((latestSnapshot?.turnHistoryEventCount ?? 0) <= 0) failures.push("browser turn history had no events");

    const result = {
      ok: failures.length === 0,
      session_id: sessionId,
      seed,
      bounded_end_rules: boundedEndRules,
      duration_ms: Date.now() - startedAtMs,
      api_base_url: apiBaseUrl,
      web_base_url: webBaseUrl,
      timeout_ms: timeoutMs,
      idle_timeout_ms: idleTimeoutMs,
      commit_seq: lastCommitSeq,
      policies: clients.map((item) => item.label),
      browser: latestSnapshot,
      console_error_count: consoleErrors.length,
      page_error_count: pageErrors.length,
      reconnect_forced: reconnectForced,
      clients: summarizeClients(clients),
      failures,
      screenshot_path: screenshotPath,
    };
    await writeJson(outPath, result);
    console.log(JSON.stringify(result));
    if (failures.length > 0) {
      process.exitCode = 1;
    }
  } catch (error) {
    const failure = {
      ok: false,
      session_id: sessionId || null,
      seed,
      duration_ms: Date.now() - startedAtMs,
      commit_seq: lastCommitSeq,
      browser: latestSnapshot,
      console_error_count: consoleErrors.length,
      page_error_count: pageErrors.length,
      clients: summarizeClients(clients),
      error: error instanceof Error ? error.stack || error.message : String(error),
    };
    await writeJson(outPath, failure);
    console.error(JSON.stringify(failure));
    process.exitCode = 1;
  } finally {
    for (const { client } of clients) {
      client.disconnect();
    }
    await browser.close();
  }
}

void main();
