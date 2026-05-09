import { chromium } from "@playwright/test";
import { createScreenProgressGuard } from "./screenProgressGuard.mjs";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:9090";
const DEFAULT_WEB_BASE_URL = "http://127.0.0.1:9000";
const DEFAULT_STALL_MS = 60_000;
const POLL_MS = 1_000;

function intFromEnv(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? Math.trunc(value) : fallback;
}

function boolFromEnv(name) {
  const value = String(process.env[name] ?? "").trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

function buildUrl(baseUrl, path) {
  return new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`).toString();
}

async function apiJson(baseUrl, path, options = {}) {
  const response = await fetch(buildUrl(baseUrl, path), {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  const bodyText = await response.text();
  let body;
  try {
    body = bodyText ? JSON.parse(bodyText) : {};
  } catch (error) {
    throw new Error(`API returned non-JSON ${response.status} for ${path}: ${bodyText.slice(0, 300)}`, {
      cause: error,
    });
  }
  if (!response.ok || body?.ok === false) {
    throw new Error(`API failed ${response.status} for ${path}: ${JSON.stringify(body)}`);
  }
  return body.data ?? body;
}

function sessionPayload(seed, boundedEndRules) {
  const config = {
    seed,
    visibility: "public",
    seat_limits: { min: 1, max: 2, allowed: [1, 2] },
  };
  if (boundedEndRules) {
    config.rules = {
      end: {
        f_threshold: 1,
        monopolies_to_trigger_end: 0,
        tiles_to_trigger_end: 1,
        alive_players_at_most: 1,
      },
    };
  }
  return {
    seats: [
      { seat: 1, seat_type: "ai", ai_profile: "balanced" },
      { seat: 2, seat_type: "ai", ai_profile: "balanced" },
    ],
    config,
  };
}

async function latestViewCommit(apiBaseUrl, sessionId) {
  try {
    return await apiJson(apiBaseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/view-commit`);
  } catch (error) {
    if (String(error?.message ?? "").includes("VIEW_COMMIT_NOT_FOUND")) {
      return null;
    }
    throw error;
  }
}

async function runtimeStatus(apiBaseUrl, sessionId) {
  const data = await apiJson(apiBaseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/runtime-status`);
  return data.runtime ?? {};
}

async function screenSignature(page) {
  return page.evaluate(() => {
    const root = document.querySelector("#root") ?? document.body;
    const visibleText =
      root instanceof HTMLElement ? root.innerText.replace(/\s+/g, " ").trim() : (root.textContent ?? "").replace(/\s+/g, " ").trim();
    const board = document.querySelector("[data-testid='board-panel'], .match-table-board, .board-panel");
    const prompt = document.querySelector("[data-testid='prompt-overlay'], .prompt-overlay");
    const active = document.querySelector("[data-testid='active-character-strip'], .active-character-strip");
    return JSON.stringify({
      text: visibleText.slice(0, 8_000),
      textLength: visibleText.length,
      boardVisible: Boolean(board),
      promptVisible: Boolean(prompt),
      activeVisible: Boolean(active),
    });
  });
}

async function main() {
  const apiBaseUrl = process.env.MRN_API_BASE_URL || DEFAULT_API_BASE_URL;
  const webBaseUrl = process.env.MRN_WEB_BASE_URL || DEFAULT_WEB_BASE_URL;
  const stallMs = intFromEnv("MRN_SCREEN_STALL_MS", DEFAULT_STALL_MS);
  const seed = intFromEnv("MRN_FULL_GAME_SEED", Math.floor(Math.random() * 2_147_483_647));
  const boundedEndRules = boolFromEnv("MRN_FULL_GAME_BOUNDED");

  const browser = await chromium.launch({ headless: process.env.MRN_HEADLESS !== "0" });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const startedAtMs = Date.now();
  const guard = createScreenProgressGuard({ stallMs, startTimeMs: startedAtMs });

  try {
    const created = await apiJson(apiBaseUrl, "/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(sessionPayload(seed, boundedEndRules)),
    });
    const sessionId = created.session_id;
    const matchUrl = `${webBaseUrl.replace(/\/$/, "")}/#/match?session=${encodeURIComponent(sessionId)}`;
    await page.goto(matchUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
    guard.observe({ nowMs: Date.now(), commitSeq: 0, screenSignature: await screenSignature(page) });

    await apiJson(apiBaseUrl, `/api/v1/sessions/${encodeURIComponent(sessionId)}/start`, {
      method: "POST",
      body: JSON.stringify({ host_token: created.host_token }),
    });

    let lastCommitSeq = 0;
    let sampleCount = 0;
    while (true) {
      await page.waitForTimeout(POLL_MS);
      sampleCount += 1;
      const [commit, runtime, signature] = await Promise.all([
        latestViewCommit(apiBaseUrl, sessionId),
        runtimeStatus(apiBaseUrl, sessionId),
        screenSignature(page),
      ]);
      const commitSeq = Number(commit?.commit_seq ?? lastCommitSeq);
      if (Number.isFinite(commitSeq)) {
        lastCommitSeq = Math.max(lastCommitSeq, commitSeq);
      }
      const progress = guard.observe({ nowMs: Date.now(), commitSeq: lastCommitSeq, screenSignature: signature });
      if (progress.status === "stalled") {
        throw new Error(
          `screen_update_stalled: session=${sessionId} seed=${seed} stalled_ms=${progress.stalledMs} last_commit_seq=${progress.lastCommitSeq}`,
        );
      }

      const runtimeState = String(runtime?.status ?? commit?.runtime?.status ?? "");
      if (runtimeState === "completed") {
        const durationMs = Date.now() - startedAtMs;
        console.log(
          JSON.stringify({
            ok: true,
            session_id: sessionId,
            seed,
            bounded_end_rules: boundedEndRules,
            duration_ms: durationMs,
            stall_ms: stallMs,
            commit_seq: lastCommitSeq,
            runtime_status: runtimeState,
            samples: sampleCount,
          }),
        );
        return;
      }
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
