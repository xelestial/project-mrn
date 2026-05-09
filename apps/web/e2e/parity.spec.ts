import { expect, test, type Locator, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { nextFollowupCommitBase, withAuthoritativeViewCommits } from "./helpers/authoritativeMockRuntime";

const WEATHER_EFFECT_BY_NAME: Record<string, string> = {
  "긴급 피난": "모든 짐 제거 비용이 2배가 됩니다.",
};

function weatherEffectForDisplayName(name: string | null | undefined): string | null {
  if (typeof name !== "string") {
    return null;
  }
  return WEATHER_EFFECT_BY_NAME[name] ?? null;
}

async function expectLocatorsToShareSingleRow(elements: Locator[]) {
  const boxes = await Promise.all(
    elements.map(async (element) => {
      await element.scrollIntoViewIfNeeded();
      return element.boundingBox();
    }),
  );
  const numericBoxes = boxes.filter((box): box is NonNullable<typeof box> => box !== null);
  expect(numericBoxes.length).toBe(elements.length);
  const baselineY = numericBoxes[0]?.y ?? 0;
  for (const box of numericBoxes) {
    expect(Math.abs(box.y - baselineY)).toBeLessThanOrEqual(2);
  }
}

type FixtureRecord = {
  id: string;
  title: string;
  assertions?: string[];
};

type ManifestRecord = {
  manifest_version: number;
  manifest_hash: string;
  source_fingerprints: Record<string, string>;
  version: string;
  board?: {
    topology?: string;
    tile_count?: number;
    tiles?: Array<{
      tile_index: number;
      tile_kind: string;
      zone_color?: string;
      purchase_cost?: number;
      rent_cost?: number;
    }>;
  };
  seats?: {
    min?: number;
    max?: number;
    allowed?: number[];
    default_profile_max?: number;
  };
  dice?: {
    values?: number[];
    max_cards_per_turn?: number;
    use_one_card_plus_one_die?: boolean;
  };
  economy?: {
    starting_cash?: number;
  };
  resources?: {
    starting_shards?: number;
  };
};

type StreamMessage = {
  type: string;
  seq: number;
  session_id: string;
  server_time_ms: number;
  payload: Record<string, unknown>;
};

type TimedStreamMessage = StreamMessage & {
  delay_ms?: number;
};

function loadFixture(name: string): FixtureRecord {
  const path = resolve(process.cwd(), "e2e", "fixtures", name);
  return JSON.parse(readFileSync(path, "utf8")) as FixtureRecord;
}

function buildTiles(tileCount: number): ManifestRecord["board"]["tiles"] {
  return Array.from({ length: tileCount }, (_, index) => ({
    tile_index: index,
    tile_kind: index % 7 === 0 ? "S" : "T2",
    zone_color: index % 2 === 0 ? "blue" : "red",
    purchase_cost: 2 + (index % 3),
    rent_cost: 3 + (index % 2),
  }));
}

function buildManifest(args: {
  hash: string;
  topology: "ring" | "line";
  tileCount: number;
  seats: number[];
  diceValues?: number[];
  diceMaxCardsPerTurn?: number;
  startingCash?: number;
  startingShards?: number;
}): ManifestRecord {
  return {
    manifest_version: 1,
    manifest_hash: args.hash,
    source_fingerprints: {
      board: `board_${args.hash}`,
      seats: `seats_${args.hash}`,
      labels: `labels_${args.hash}`,
    },
    version: "v1",
    board: {
      topology: args.topology,
      tile_count: args.tileCount,
      tiles: buildTiles(args.tileCount),
    },
    seats: {
      min: 1,
      max: args.seats.length,
      allowed: args.seats,
      default_profile_max: 4,
    },
    dice: {
      values: args.diceValues ?? [1, 2, 3, 4, 5, 6],
      max_cards_per_turn: args.diceMaxCardsPerTurn ?? 2,
      use_one_card_plus_one_die: false,
    },
    economy: {
      starting_cash: args.startingCash ?? 20,
    },
    resources: {
      starting_shards: args.startingShards ?? 4,
    },
  };
}

function eventMessage(args: {
  seq: number;
  sessionId: string;
  payload: Record<string, unknown>;
}): StreamMessage {
  return {
    type: "event",
    seq: args.seq,
    session_id: args.sessionId,
    server_time_ms: 1_700_000_000_000 + args.seq,
    payload: args.payload,
  };
}

async function installMockRuntime(
  page: Page,
  args: {
    sessionManifests: Record<string, ManifestRecord>;
    sessionEvents: Record<string, StreamMessage[]>;
    decisionFollowups?: Record<string, TimedStreamMessage[]>;
    createSessionQueue?: Array<{
      session_id: string;
      status: string;
      host_token: string;
      join_tokens: Record<string, string>;
      initial_active_by_card?: Record<string, string>;
      seats?: Array<{ seat: number; seat_type: "human" | "ai"; ai_profile?: string | null; player_id?: number | null; connected?: boolean }>;
      parameter_manifest?: ManifestRecord;
    }>;
    joinResults?: Record<
      string,
      {
        session_id: string;
        seat: number;
        player_id: number;
        session_token: string;
        role: "seat";
      }
    >;
    startedSessions?: Record<
      string,
      {
        session_id: string;
        status: string;
        round_index?: number;
        turn_index?: number;
        initial_active_by_card?: Record<string, string>;
        seats?: Array<{ seat: number; seat_type: "human" | "ai"; ai_profile?: string | null; player_id?: number | null; connected?: boolean }>;
        parameter_manifest?: ManifestRecord;
      }
    >;
  },
): Promise<void> {
  const sessionEvents = withAuthoritativeViewCommits({
    sessionManifests: args.sessionManifests,
    sessionEvents: args.sessionEvents,
    createSessionQueue: args.createSessionQueue,
    startedSessions: args.startedSessions,
  }) as Record<string, StreamMessage[]>;
  const followupCommitBaseBySession = new Map<string, number>();
  const decisionFollowups = Object.fromEntries(
    Object.entries(args.decisionFollowups ?? {}).map(([requestId, followups]) => {
      const sessionId = followups[0]?.session_id;
      if (!sessionId) {
        return [requestId, followups];
      }
      const startingCommitSeq = followupCommitBaseBySession.get(sessionId) ?? nextFollowupCommitBase(sessionEvents[sessionId]);
      const normalized = withAuthoritativeViewCommits({
        sessionManifests: args.sessionManifests,
        sessionEvents: { [sessionId]: followups },
        createSessionQueue: args.createSessionQueue,
        startedSessions: args.startedSessions,
        startingCommitSeq,
      })[sessionId] as TimedStreamMessage[];
      followupCommitBaseBySession.set(sessionId, nextFollowupCommitBase(normalized, startingCommitSeq));
      return [requestId, normalized];
    }),
  ) as Record<string, TimedStreamMessage[]>;

  await page.addInitScript(
    ({ sessionManifests, sessionEvents, decisionFollowups, createSessionQueue, joinResults, startedSessions }) => {
      window.localStorage.setItem("mrn:web:locale", "ko");
      const manifests = sessionManifests as Record<string, ManifestRecord>;
      const eventsBySession = sessionEvents as Record<string, StreamMessage[]>;
      const followupsByRequest = (decisionFollowups as Record<string, TimedStreamMessage[]> | undefined) ?? {};
      const pendingCreates = [...(createSessionQueue as Array<Record<string, unknown>> | undefined ?? [])];
      const joinResultMap = (joinResults as Record<string, Record<string, unknown>> | undefined) ?? {};
      const startedSessionMap = (startedSessions as Record<string, Record<string, unknown>> | undefined) ?? {};
      const sessionSnapshots = new Map<string, Record<string, unknown>>();

      for (const created of pendingCreates) {
        const sessionId = String(created.session_id);
        const manifest = (created.parameter_manifest as ManifestRecord | undefined) ?? manifests[sessionId];
        if (manifest) {
          manifests[sessionId] = manifest;
        }
        sessionSnapshots.set(sessionId, {
          session_id: sessionId,
          status: created.status ?? "waiting",
          round_index: 0,
          turn_index: 0,
          initial_active_by_card: created.initial_active_by_card ?? null,
          seats: created.seats ?? [],
          parameter_manifest: manifest ?? null,
        });
      }

      for (const [sessionId, started] of Object.entries(startedSessionMap)) {
        sessionSnapshots.set(sessionId, {
          ...(sessionSnapshots.get(sessionId) ?? {}),
          ...started,
        });
      }

      function response(data: unknown, status = 200): Response {
        return new Response(
          JSON.stringify({
            ok: status >= 200 && status < 300,
            data,
            error: status >= 200 && status < 300 ? null : { code: "E2E_ERROR", message: "mock error", retryable: false },
          }),
          { status, headers: { "Content-Type": "application/json" } },
        );
      }

      function latestCommitForSession(sessionId: string): StreamMessage | null {
        const commits = (eventsBySession[sessionId] ?? []).filter((message) => message.type === "view_commit");
        if (commits.length === 0) {
          return null;
        }
        return commits.reduce((latest, message) => {
          const latestSeq = typeof latest.payload.commit_seq === "number" ? latest.payload.commit_seq : 0;
          const currentSeq = typeof message.payload.commit_seq === "number" ? message.payload.commit_seq : 0;
          return currentSeq > latestSeq ? message : latest;
        });
      }

      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const urlValue = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const url = new URL(urlValue, window.location.origin);
        const path = url.pathname;
        const method = (init?.method ?? "GET").toUpperCase();
        const sessionMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)$/);
        const runtimeMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/runtime-status$/);
        const viewCommitMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/view-commit$/);
        const joinMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/join$/);
        const startMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/start$/);
        if (runtimeMatch) {
          const sessionId = decodeURIComponent(runtimeMatch[1]);
          const latestCommit = latestCommitForSession(sessionId);
          return response({
            session_id: sessionId,
            runtime: {
              status: latestCommit?.payload.runtime && typeof latestCommit.payload.runtime === "object"
                ? (latestCommit.payload.runtime as Record<string, unknown>).status ?? "running"
                : "running",
              watchdog_state: "ok",
              last_activity_ms: Date.now(),
            },
          });
        }
        if (viewCommitMatch) {
          const sessionId = decodeURIComponent(viewCommitMatch[1]);
          const latestCommit = latestCommitForSession(sessionId);
          return latestCommit ? response(latestCommit.payload) : response(null, 404);
        }
        if (path === "/api/v1/sessions" && method === "POST") {
          const created = pendingCreates.shift();
          if (!created) {
            return response(null, 500);
          }
          const sessionId = String(created.session_id);
          const manifest = (created.parameter_manifest as ManifestRecord | undefined) ?? manifests[sessionId];
          if (manifest) {
            manifests[sessionId] = manifest;
          }
          sessionSnapshots.set(sessionId, {
            session_id: sessionId,
            status: created.status ?? "waiting",
            round_index: 0,
            turn_index: 0,
            initial_active_by_card: created.initial_active_by_card ?? null,
            seats: created.seats ?? [],
            parameter_manifest: manifest ?? null,
          });
          return response(created);
        }
        if (sessionMatch && method === "GET") {
          const sessionId = decodeURIComponent(sessionMatch[1]);
          const snapshot = sessionSnapshots.get(sessionId);
          const manifest = manifests[sessionId];
          if (!snapshot && !manifest) {
            return response(null, 404);
          }
          return response({
            ...(snapshot ?? {}),
            session_id: sessionId,
            status: snapshot?.status ?? "in_progress",
            round_index: snapshot?.round_index ?? 1,
            turn_index: snapshot?.turn_index ?? 1,
            initial_active_by_card: (snapshot?.initial_active_by_card as Record<string, string> | undefined) ?? null,
            seats:
              (snapshot?.seats as Array<Record<string, unknown>> | undefined) ??
              manifest?.seats?.allowed?.map((seat) => ({
                seat,
                seat_type: seat === 1 ? "human" : "ai",
                ai_profile: seat === 1 ? null : "balanced",
                player_id: seat,
                connected: true,
              })) ??
              [],
            parameter_manifest: (snapshot?.parameter_manifest as ManifestRecord | undefined) ?? manifest,
          });
        }
        if (joinMatch && method === "POST") {
          const sessionId = decodeURIComponent(joinMatch[1]);
          const requestBody = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
          const seat = Number(requestBody.seat ?? 0);
          const result = joinResultMap[`${sessionId}:${seat}`];
          if (!result) {
            return response(null, 404);
          }
          const snapshot = sessionSnapshots.get(sessionId);
          if (snapshot && Array.isArray(snapshot.seats)) {
            snapshot.seats = (snapshot.seats as Array<Record<string, unknown>>).map((seatView) =>
              Number(seatView.seat) === seat
                ? { ...seatView, player_id: result.player_id, connected: true }
                : seatView,
            );
            sessionSnapshots.set(sessionId, snapshot);
          }
          return response(result);
        }
        if (startMatch && method === "POST") {
          const sessionId = decodeURIComponent(startMatch[1]);
          const started = startedSessionMap[sessionId];
          if (!started) {
            return response(null, 404);
          }
          sessionSnapshots.set(sessionId, started);
          return response(started);
        }
        if (path === "/api/v1/sessions" && method === "GET") {
          const sessionIds = new Set([...Object.keys(manifests), ...Array.from(sessionSnapshots.keys())]);
          const sessions = Array.from(sessionIds).map((sessionId) => ({
            ...(sessionSnapshots.get(sessionId) ?? {}),
            session_id: sessionId,
            status: sessionSnapshots.get(sessionId)?.status ?? "in_progress",
            round_index: sessionSnapshots.get(sessionId)?.round_index ?? 1,
            turn_index: sessionSnapshots.get(sessionId)?.turn_index ?? 1,
            initial_active_by_card:
              (sessionSnapshots.get(sessionId)?.initial_active_by_card as Record<string, string> | undefined) ?? null,
            seats: sessionSnapshots.get(sessionId)?.seats ?? [],
            parameter_manifest: sessionSnapshots.get(sessionId)?.parameter_manifest ?? manifests[sessionId],
          }));
          return response({ sessions });
        }
        return originalFetch(input, init);
      };

      class MockWebSocket {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;
        url: string;
        readyState = MockWebSocket.CONNECTING;
        onopen: ((event: Event) => void) | null = null;
        onclose: ((event: CloseEvent) => void) | null = null;
        onmessage: ((event: MessageEvent) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;

        constructor(url: string) {
          this.url = url;
          window.setTimeout(() => {
            this.readyState = MockWebSocket.OPEN;
            this.onopen?.(new Event("open"));
            const match = this.url.match(/\/api\/v1\/sessions\/([^/]+)\/stream/);
            const sessionId = match ? decodeURIComponent(match[1]) : "";
            const latestCommit = latestCommitForSession(sessionId);
            if (latestCommit) {
              this.emitMessages([latestCommit]);
            }
          }, 0);
        }

        emitMessages(messages: TimedStreamMessage[]): void {
          messages.forEach((message, index) => {
            const delayMs = typeof message.delay_ms === "number" ? message.delay_ms : index * 5;
            window.setTimeout(() => {
              if (this.readyState !== MockWebSocket.OPEN) {
                return;
              }
              const { delay_ms: _delayMs, ...wireMessage } = message;
              this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(wireMessage) }));
            }, delayMs);
          });
        }

        send(data: string): void {
          let payload: Record<string, unknown> = {};
          try {
            payload = JSON.parse(data) as Record<string, unknown>;
          } catch {
            return;
          }
          if (payload.type === "decision") {
            const requestId = typeof payload.request_id === "string" ? payload.request_id : "";
            const followups = followupsByRequest[requestId] ?? [];
            if (followups.length === 0) {
              return;
            }
            const match = this.url.match(/\/api\/v1\/sessions\/([^/]+)\/stream/);
            const sessionId = match ? decodeURIComponent(match[1]) : "";
            eventsBySession[sessionId] = [...(eventsBySession[sessionId] ?? []), ...followups];
            this.emitMessages(followups);
            return;
          }
          if (payload.type !== "resume") {
            return;
          }
          const match = this.url.match(/\/api\/v1\/sessions\/([^/]+)\/stream/);
          const sessionId = match ? decodeURIComponent(match[1]) : "";
          const latestCommit = latestCommitForSession(sessionId);
          if (latestCommit) {
            this.emitMessages([latestCommit]);
          }
        }

        close(): void {
          if (this.readyState === MockWebSocket.CLOSED) {
            return;
          }
          this.readyState = MockWebSocket.CLOSED;
          this.onclose?.(new CloseEvent("close"));
        }
      }

      Object.defineProperty(window, "WebSocket", {
        configurable: true,
        writable: true,
        value: MockWebSocket,
      });
    },
    { ...args, sessionEvents, decisionFollowups },
  );
}

test("quick start human vs ai enters match and surfaces the first human prompt", async ({ page }) => {
  const manifest = buildManifest({
    hash: "quick_start_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const sessionId = "sess_quick_human";
  const hostToken = "host_quick_human";
  const joinTokens = {
    "1": "seat1_quick_join",
    "2": "seat2_quick_join",
    "3": "seat3_quick_join",
    "4": "seat4_quick_join",
  };
  const initialActiveByCard = {
    "1": "어사",
    "2": "자객",
    "3": "추노꾼",
    "4": "파발꾼",
    "5": "교리 연구관",
    "6": "박수",
    "7": "객주",
    "8": "건설업자",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "round_start",
            round_index: 1,
          },
        }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: {
            event_type: "weather_reveal",
            weather_name: "긴급 피난",
          },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "turn_start",
            round_index: 1,
            turn_index: 1,
            acting_player_id: 1,
            character: "교리 연구관",
          },
        }),
        {
          type: "prompt",
          seq: 5,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_005,
          payload: {
            request_id: "req_hidden_1",
            request_type: "hidden_trick_card",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              hidden_trick_count: 0,
              full_hand: [
                { deck_index: 10, name: "무거운 짐", card_description: "효과 없음", is_hidden: false, is_usable: true },
                { deck_index: 11, name: "마당발", card_description: "인접 토지를 추가 구매합니다", is_hidden: false, is_usable: true },
                { deck_index: 12, name: "건강 검진", card_description: "모든 참가자의 통행료가 절반이 됩니다", is_hidden: false, is_usable: true },
                { deck_index: 13, name: "긴장감 조성", card_description: "지정 타일 통행료를 두 배로 올립니다", is_hidden: false, is_usable: true },
                { deck_index: 14, name: "가벼운 분리불안", card_description: "같은 칸 조우 시 2냥을 얻습니다", is_hidden: false, is_usable: true },
              ],
            },
            choices: [
              { choice_id: "10", title: "무거운 짐", description: "효과 없음", value: { deck_index: 10 } },
              { choice_id: "11", title: "마당발", description: "인접 토지를 추가 구매합니다", value: { deck_index: 11 } },
              { choice_id: "12", title: "건강 검진", description: "모든 참가자의 통행료가 절반이 됩니다", value: { deck_index: 12 } },
              { choice_id: "13", title: "긴장감 조성", description: "지정 타일 통행료를 두 배로 올립니다", value: { deck_index: 13 } },
              { choice_id: "14", title: "가벼운 분리불안", description: "같은 칸 조우 시 2냥을 얻습니다", value: { deck_index: 14 } },
            ],
          },
        },
      ],
    },
    createSessionQueue: [
      {
        session_id: sessionId,
        status: "waiting",
        host_token: hostToken,
        join_tokens: joinTokens,
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: false, player_id: null },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    ],
    joinResults: {
      [`${sessionId}:1`]: {
        session_id: sessionId,
        seat: 1,
        player_id: 1,
        session_token: "session_p1_quick_token",
        role: "seat",
      },
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 1,
        turn_index: 1,
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: null, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: null, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: null, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto("/#/lobby");
  await page.getByTestId("quick-start-human-vs-ai").click();

  await expect(page).toHaveURL(/#\/match/);
  const weatherSummary = page.getByTestId("board-weather-summary");
  await expect(weatherSummary).toBeVisible();
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "hidden_trick_card");
  await expect(page.getByTestId("trick-choice-10-0")).toBeVisible();
  await expect(page.getByTestId("trick-choice-11-1")).toBeVisible();
  await expect(page.getByTestId("trick-choice-12-2")).toBeVisible();
  await expect(page.getByTestId("trick-choice-13-3")).toBeVisible();
  await expect(page.getByTestId("trick-choice-14-4")).toBeVisible();
  await expect(weatherSummary).toHaveAttribute("data-weather-name", "긴급 피난");
  await expect(weatherSummary).toHaveAttribute("data-weather-detail", weatherEffectForDisplayName("긴급 피난") ?? "");
  const activeStrip = page.getByTestId("active-character-strip");
  await expect(page.getByTestId("active-character-slot-1")).toHaveAttribute("data-character-name", "어사");
  await expect(page.getByTestId("active-character-slot-2")).toHaveAttribute("data-character-name", "자객");
  await expect(page.getByTestId("active-character-slot-5")).toHaveAttribute("data-character-name", "교리 연구관");
  await expect(page.getByTestId("active-character-slot-8")).toHaveAttribute("data-character-name", "건설업자");
  await expect(activeStrip).toHaveAttribute("data-known-count", "8");
  await expect(activeStrip).toHaveAttribute("data-slot-count", "8");
  await expectLocatorsToShareSingleRow([
    page.getByTestId("trick-choice-10-0"),
    page.getByTestId("trick-choice-11-1"),
    page.getByTestId("trick-choice-12-2"),
    page.getByTestId("trick-choice-13-3"),
    page.getByTestId("trick-choice-14-4"),
  ]);
});

test("completed engine transition shows a visible game-end state even with a stale backend turn projection", async ({ page }) => {
  const manifest = buildManifest({
    hash: "completed_engine_transition_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const sessionId = "sess_completed_engine_transition";

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "round_start",
            round_index: 6,
          },
        }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: {
            event_type: "turn_start",
            round_index: 6,
            turn_index: 21,
            acting_player_id: 1,
            character: "객주",
          },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "turn_end_snapshot",
            round_index: 6,
            turn_index: 21,
            acting_player_id: 1,
            view_state: {
              turn_stage: {
                turn_start_seq: 3,
                actor_player_id: 1,
                round_index: 6,
                turn_index: 21,
                character: "객주",
                weather_name: "맑음",
                weather_effect: "-",
                current_beat_kind: "system",
                current_beat_event_code: "turn_end_snapshot",
                current_beat_request_type: "movement",
                current_beat_seq: 4,
                focus_tile_index: 30,
                focus_tile_indices: [30],
                prompt_request_type: "movement",
                progress_codes: ["turn_start", "turn_end_snapshot"],
              },
              scene: {
                situation: {
                  actor_player_id: 1,
                  headline_seq: 4,
                  headline_message_type: "event",
                  headline_event_code: "turn_end_snapshot",
                  round_index: 6,
                  turn_index: 21,
                  weather_name: "맑음",
                  weather_effect: "-",
                },
                theater_feed: [],
                core_action_feed: [],
                timeline: [],
                critical_alerts: [],
              },
            },
          },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "engine_transition",
            status: "completed",
            reason: "end_rule",
          },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "completed",
        round_index: 6,
        turn_index: 21,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}`);

  await expect(page.getByTestId("board-weather-summary")).toBeVisible();
  await expect(page.getByTestId("turn-notice-banner-title")).toHaveText("게임 종료");
  await expect(page.getByTestId("turn-notice-banner-detail")).toContainText("end_rule");
  await expect(page.getByTestId("spectator-turn-scene-title")).toHaveText("게임 종료");
  await expect(page.getByTestId("spectator-turn-scene-detail")).toContainText("end_rule");
  await expect(page.getByTestId("spectator-turn-prompt-title")).toHaveText("-");
  await expect(page.getByTestId("turn-notice-banner")).not.toHaveAttribute("data-banner-player-id", "1");
});

test("trick use advances to tile target without resurrecting the stale trick picker", async ({ page }) => {
  const manifest = buildManifest({
    hash: "trick_prompt_lifecycle_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const sessionId = "sess_trick_target_lifecycle";
  const initialActiveByCard = {
    "1": "중매꾼",
    "2": "자객",
    "3": "추노꾼",
    "4": "파발꾼",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "turn_start",
            round_index: 1,
            turn_index: 1,
            acting_player_id: 1,
            character: "중매꾼",
          },
        }),
        {
          type: "prompt",
          seq: 3,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_003,
          payload: {
            request_id: "req_trick_use_1",
            request_type: "trick_to_use",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              total_hand_count: 1,
              hidden_trick_count: 0,
              full_hand: [
                {
                  deck_index: 13,
                  name: "긴장감 조성",
                  card_description: "지정 타일 통행료를 두 배로 올립니다",
                  is_hidden: false,
                  is_usable: true,
                },
              ],
            },
            choices: [
              { choice_id: "none", title: "쓰지 않음", description: "이번 타이밍에는 사용하지 않습니다", value: null, secondary: true },
              { choice_id: "13", title: "긴장감 조성", description: "지정 타일 통행료를 두 배로 올립니다", value: { deck_index: 13 } },
            ],
          },
        },
      ],
    },
    decisionFollowups: {
      req_trick_use_1: [
        {
          type: "decision_ack",
          seq: 4,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_004,
          delay_ms: 0,
          payload: {
            request_id: "req_trick_use_1",
            status: "accepted",
            player_id: 1,
            provider: "human",
          },
        },
        {
          ...eventMessage({
            seq: 5,
            sessionId,
            payload: {
              event_type: "trick_used",
              round_index: 1,
              turn_index: 1,
              acting_player_id: 1,
              player_id: 1,
              card_name: "긴장감 조성",
              deck_index: 13,
            },
          }),
          delay_ms: 20,
        },
        {
          type: "prompt",
          seq: 6,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_006,
          delay_ms: 600,
          payload: {
            request_id: "req_trick_target_1",
            request_type: "trick_tile_target",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              card_name: "긴장감 조성",
              target_scope: "owned_or_any",
              candidate_tiles: [3, 4],
            },
            choices: [
              { choice_id: "tile_3", title: "3번 토지", description: "통행료 두 배", value: { tile_index: 3 } },
              { choice_id: "tile_4", title: "4번 토지", description: "통행료 두 배", value: { tile_index: 4 } },
            ],
          },
        },
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 1,
        turn_index: 1,
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_trick_lifecycle_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "trick_to_use");
  await expect(page.getByTestId("trick-choice-13-0")).toHaveAttribute("data-card-name", "긴장감 조성");

  await page.getByTestId("trick-choice-13-0").click();

  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0, { timeout: 500 });
  await expect(page.getByTestId("trick-choice-13-0")).toHaveCount(0);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "trick_tile_target", { timeout: 1500 });
  await expect(page.getByTestId("trick-tile-target-choice-tile_3")).toHaveAttribute("data-choice-title", "3번 토지");
});

test("extreme separation trick closes picker while queued movement resolves", async ({ page }) => {
  const manifest = buildManifest({
    hash: "extreme_separation_lifecycle_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const sessionId = "sess_extreme_separation_lifecycle";
  const initialActiveByCard = {
    "1": "중매꾼",
    "2": "자객",
    "3": "추노꾼",
    "4": "파발꾼",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "turn_start",
            round_index: 1,
            turn_index: 1,
            acting_player_id: 1,
            character: "중매꾼",
          },
        }),
        {
          type: "prompt",
          seq: 3,
          session_id: sessionId,
          server_time_ms: 1_700_000_010_003,
          payload: {
            request_id: "req_extreme_separation_1",
            request_type: "trick_to_use",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              total_hand_count: 2,
              hidden_trick_count: 0,
              full_hand: [
                {
                  deck_index: 21,
                  name: "극심한 분리불안",
                  card_description: "가장 거리가 먼 사람의 위치에 즉시 도착합니다",
                  is_hidden: false,
                  is_usable: true,
                },
                {
                  deck_index: 22,
                  name: "건강 검진",
                  card_description: "이번 턴 통행료를 절반으로 줄입니다",
                  is_hidden: false,
                  is_usable: true,
                },
              ],
            },
            choices: [
              { choice_id: "none", title: "쓰지 않음", description: "이번 타이밍에는 사용하지 않습니다", value: null, secondary: true },
              { choice_id: "21", title: "극심한 분리불안", description: "가장 거리가 먼 사람의 위치에 즉시 도착합니다", value: { deck_index: 21 } },
              { choice_id: "22", title: "건강 검진", description: "이번 턴 통행료를 절반으로 줄입니다", value: { deck_index: 22 } },
            ],
          },
        },
      ],
    },
    decisionFollowups: {
      req_extreme_separation_1: [
        {
          type: "decision_ack",
          seq: 4,
          session_id: sessionId,
          server_time_ms: 1_700_000_010_004,
          delay_ms: 0,
          payload: {
            request_id: "req_extreme_separation_1",
            status: "accepted",
            player_id: 1,
            provider: "human",
          },
        },
        {
          ...eventMessage({
            seq: 5,
            sessionId,
            payload: {
              event_type: "trick_used",
              round_index: 1,
              turn_index: 1,
              acting_player_id: 1,
              player_id: 1,
              card_name: "극심한 분리불안",
              deck_index: 21,
            },
          }),
          delay_ms: 20,
        },
        {
          ...eventMessage({
            seq: 6,
            sessionId,
            payload: {
              event_type: "action_move",
              round_index: 1,
              turn_index: 1,
              acting_player_id: 1,
              player_id: 1,
              from_tile: 1,
              to_tile: 12,
              movement_source: "trick_extreme_separation",
            },
          }),
          delay_ms: 120,
        },
        {
          ...eventMessage({
            seq: 7,
            sessionId,
            payload: {
              event_type: "landing_resolved",
              round_index: 1,
              turn_index: 1,
              acting_player_id: 1,
              player_id: 1,
              position: 12,
              trigger: "trick_extreme_separation",
              card_name: "극심한 분리불안",
            },
          }),
          delay_ms: 260,
        },
        {
          ...eventMessage({
            seq: 8,
            sessionId,
            payload: {
              event_type: "trick_window_closed",
              round_index: 1,
              turn_index: 1,
              acting_player_id: 1,
              player_id: 1,
            },
          }),
          delay_ms: 420,
        },
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 1,
        turn_index: 1,
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_extreme_separation_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "trick_to_use");
  await expect(page.getByTestId("trick-choice-21-0")).toHaveAttribute("data-card-name", "극심한 분리불안");

  await page.getByTestId("trick-choice-21-0").click();

  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0, { timeout: 500 });
  await expect(page.getByTestId("trick-choice-21-0")).toHaveCount(0);
  await page.waitForTimeout(900);
  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0);
  await expect(page.getByTestId("trick-choice-22-0")).toHaveCount(0);
});

test("session payload initial active faces hydrate the active strip before stream events arrive", async ({ page }) => {
  const sessionId = "sess_initial_active_payload";
  const manifest = buildManifest({
    hash: "initial_active_faces_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const initialActiveByCard = {
    "1": "탐관오리",
    "2": "산적",
    "3": "탈출 노비",
    "4": "아전",
    "5": "교리 감독관",
    "6": "만신",
    "7": "중매꾼",
    "8": "사기꾼",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [],
    },
    createSessionQueue: [
      {
        session_id: sessionId,
        status: "in_progress",
        host_token: "host_initial_active_payload",
        join_tokens: { "1": "seat1", "2": "seat2", "3": "seat3", "4": "seat4" },
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    ],
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_initial_active_demo`);
  const activeStrip = page.getByTestId("active-character-strip");
  await expect(page.getByTestId("active-character-slot-1")).toHaveAttribute("data-character-name", "탐관오리");
  await expect(page.getByTestId("active-character-slot-2")).toHaveAttribute("data-character-name", "산적");
  await expect(page.getByTestId("active-character-slot-5")).toHaveAttribute("data-character-name", "교리 감독관");
  await expect(page.getByTestId("active-character-slot-8")).toHaveAttribute("data-character-name", "사기꾼");
  await expect(activeStrip).toHaveAttribute("data-known-count", "8");
  await expect(activeStrip).toHaveAttribute("data-slot-count", "8");
  await expect(page.getByTestId("match-player-card-1")).toContainText("나");
  for (const seat of [2, 3, 4]) {
    const playerCard = page.getByTestId(`match-player-card-${seat}`);
    await expect(playerCard).not.toContainText("나");
    await expect(playerCard).not.toContainText("👑");
    await expect(playerCard).not.toHaveClass(/match-table-player-card-local/);
    await expect(playerCard).not.toHaveClass(/match-table-player-card-actor/);
  }
});

test("draft prompt keeps active strip hydrated before any flip events arrive", async ({ page }) => {
  const sessionId = "sess_draft_prompt_active_faces";
  const manifest = buildManifest({
    hash: "draft_prompt_active_faces_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const initialActiveByCard = {
    "1": "어사",
    "2": "산적",
    "3": "탈출 노비",
    "4": "아전",
    "5": "교리 감독관",
    "6": "박수",
    "7": "객주",
    "8": "건설업자",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "round_start",
            round_index: 1,
          },
        }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: {
            event_type: "weather_reveal",
            weather_name: "긴급 피난",
          },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "initial_public_tricks",
            players: [
              {
                player: 1,
                public_tricks: ["월척회", "건강 검진"],
                hidden_trick_count: 1,
              },
            ],
          },
        }),
        {
          type: "prompt",
          seq: 5,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_304,
          payload: {
            request_id: "req_draft_ui_1",
            request_type: "draft_card",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              draft_phase: 1,
              offered_count: 4,
              offered_names: ["탐관오리", "중매꾼", "산적", "교리 감독관"],
            },
            choices: [
              { choice_id: "draft_tamgwanori", title: "탐관오리", description: "속성 - 관원, 상민: 속성 인물은 탐관오리에게 미리내 조각 2개마다 1냥 지급하고 이동 시 주사위 1개를 추가하여 굴림" },
              { choice_id: "draft_matchmaker", title: "중매꾼", description: "능력1: 인접 토지 추가 매입(기본 2배) / 능력2: 조각 8+이면 인접 토지 추가 매입 1배" },
              { choice_id: "draft_bandit", title: "산적", description: "지목 - 지목 인물은 산적의 미리내 조각 1개마다 1냥 지급" },
              { choice_id: "draft_doctrine_guard", title: "교리 감독관", description: "능력1: 라운드 종료 시 보라 징표 획득(드래프트 전달: 시계) / 능력2: 조각 8+이면 짐 1장 제거" },
            ],
          },
        },
      ],
    },
    createSessionQueue: [
      {
        session_id: sessionId,
        status: "in_progress",
        host_token: "host_draft_prompt_active_faces",
        join_tokens: { "1": "seat1", "2": "seat2", "3": "seat3", "4": "seat4" },
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    ],
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_draft_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "draft_card");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "긴급 피난");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute(
    "data-weather-detail",
    weatherEffectForDisplayName("긴급 피난") ?? ""
  );
  await expect(page.getByTestId("active-character-slot-1")).toHaveAttribute("data-character-name", "어사");
  await expect(page.getByTestId("active-character-slot-2")).toHaveAttribute("data-character-name", "산적");
  await expect(page.getByTestId("active-character-slot-4")).toHaveAttribute("data-character-name", "아전");
  await expect(page.getByTestId("active-character-slot-8")).toHaveAttribute("data-character-name", "건설업자");
  await expectLocatorsToShareSingleRow([
    page.getByTestId("character-choice-draft_tamgwanori"),
    page.getByTestId("character-choice-draft_matchmaker"),
    page.getByTestId("character-choice-draft_bandit"),
    page.getByTestId("character-choice-draft_doctrine_guard"),
  ]);
  await expect(page.getByTestId("character-choice-draft_matchmaker")).not.toContainText("능력1");
  await expect(page.getByTestId("character-choice-draft_matchmaker")).not.toContainText("능력2");
  await expect(page.getByTestId("character-choice-draft_matchmaker")).toContainText("조각 8+이면 인접 토지 추가 매입 1배");
  await expect(page.getByTestId("character-choice-draft_doctrine_guard")).not.toContainText("능력2");
  await expect(page.getByTestId("character-choice-draft_doctrine_guard")).toContainText("조각 8+이면 짐 1장 제거");
  await expect(page.getByTestId("board-hand-tray")).toBeVisible();
  await expect(page.getByTestId("board-hand-tray")).toContainText("월척회");
  await expect(page.getByTestId("board-hand-tray")).toContainText("비공개 잔꾀");
});

test("baksu draft choice stays available in final character prompt", async ({ page }) => {
  const sessionId = "sess_baksu_draft_final_regression";
  const manifest = buildManifest({
    hash: "baksu_draft_final_regression_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const initialActiveByCard = {
    "1": "어사",
    "2": "산적",
    "3": "탈출 노비",
    "4": "아전",
    "5": "교리 감독관",
    "6": "박수",
    "7": "객주",
    "8": "건설업자",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "round_start",
            round_index: 1,
          },
        }),
        {
          type: "prompt",
          seq: 3,
          session_id: sessionId,
          server_time_ms: 1_700_000_001_003,
          payload: {
            request_id: "req_baksu_draft_1",
            request_type: "draft_card",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              draft_phase: 1,
              offered_count: 4,
              offered_names: ["박수", "산적", "객주", "아전"],
            },
            legal_choices: [
              { choice_id: "6", title: "박수", description: "Select 박수 for your draft pool." },
              { choice_id: "2", title: "산적", description: "Select 산적 for your draft pool." },
              { choice_id: "7", title: "객주", description: "Select 객주 for your draft pool." },
              { choice_id: "4", title: "아전", description: "Select 아전 for your draft pool." },
            ],
          },
        },
      ],
    },
    decisionFollowups: {
      req_baksu_draft_1: [
        {
          type: "decision_ack",
          seq: 4,
          session_id: sessionId,
          server_time_ms: 1_700_000_001_004,
          delay_ms: 0,
          payload: {
            request_id: "req_baksu_draft_1",
            status: "accepted",
            player_id: 1,
            provider: "human",
          },
        },
        {
          ...eventMessage({
            seq: 5,
            sessionId,
            payload: {
              event_type: "draft_pick",
              round_index: 1,
              player_id: 1,
              choice_id: "6",
              character: "박수",
            },
          }),
          delay_ms: 20,
        },
        {
          type: "prompt",
          seq: 6,
          session_id: sessionId,
          server_time_ms: 1_700_000_001_006,
          delay_ms: 80,
          payload: {
            request_id: "req_baksu_final_1",
            request_type: "final_character",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              draft_phase: "final",
              offered_count: 2,
              offered_names: ["박수", "건설업자"],
            },
            legal_choices: [
              { choice_id: "6", title: "박수", description: "Finalize 박수 as your active character." },
              { choice_id: "8", title: "건설업자", description: "Finalize 건설업자 as your active character." },
            ],
          },
        },
      ],
      req_baksu_final_1: [
        {
          type: "decision_ack",
          seq: 7,
          session_id: sessionId,
          server_time_ms: 1_700_000_001_007,
          delay_ms: 0,
          payload: {
            request_id: "req_baksu_final_1",
            status: "accepted",
            player_id: 1,
            provider: "human",
          },
        },
        {
          ...eventMessage({
            seq: 8,
            sessionId,
            payload: {
              event_type: "final_character_choice",
              round_index: 1,
              player_id: 1,
              acting_player_id: 1,
              choice_id: "6",
              character: "박수",
            },
          }),
          delay_ms: 20,
        },
      ],
    },
    createSessionQueue: [
      {
        session_id: sessionId,
        status: "in_progress",
        host_token: "host_baksu_draft_final_regression",
        join_tokens: { "1": "seat1", "2": "seat2", "3": "seat3", "4": "seat4" },
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    ],
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_baksu_draft_final_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "draft_card");
  await expect(page.getByTestId("character-choice-6")).toContainText("박수");
  await expect(page.getByTestId("character-choice-2")).toContainText("산적");

  await page.getByTestId("character-choice-6").click();

  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "final_character");
  await expect(page.getByTestId("character-choice-6")).toContainText("박수");
  await expect(page.getByTestId("character-choice-8")).toContainText("건설업자");

  await page.getByTestId("character-choice-6").click();
  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0);
});

test("round start shows weather and active strip before any prompt appears", async ({ page }) => {
  const sessionId = "sess_round_start_status";
  const manifest = buildManifest({
    hash: "round_start_status_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const initialActiveByCard = {
    "1": "탐관오리",
    "2": "자객",
    "3": "추노꾼",
    "4": "아전",
    "5": "교리 감독관",
    "6": "박수",
    "7": "객주",
    "8": "건설업자",
  };

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "round_start",
            round_index: 1,
          },
        }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: {
            event_type: "weather_reveal",
            weather_name: "긴급 피난",
          },
        }),
      ],
    },
    createSessionQueue: [
      {
        session_id: sessionId,
        status: "in_progress",
        host_token: "host_round_start_status",
        join_tokens: { "1": "seat1", "2": "seat2", "3": "seat3", "4": "seat4" },
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    ],
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_round_start_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0);
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "긴급 피난");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute(
    "data-weather-detail",
    weatherEffectForDisplayName("긴급 피난") ?? ""
  );
  await expect(page.getByTestId("active-character-slot-1")).toHaveAttribute("data-character-name", "탐관오리");
  await expect(page.getByTestId("active-character-slot-2")).toHaveAttribute("data-character-name", "자객");
  await expect(page.getByTestId("active-character-slot-5")).toHaveAttribute("data-character-name", "교리 감독관");
  await expect(page.getByTestId("active-character-slot-8")).toHaveAttribute("data-character-name", "건설업자");
  await expect(page.getByTestId("active-character-strip")).toHaveAttribute("data-known-count", "8");
  await expect(page.getByTestId("active-character-strip")).toHaveAttribute("data-slot-count", "8");
});

test("movement prompt supports dice_* contract choices and card-mode selection", async ({ page }) => {
  const sessionId = "sess_prompt_movement";
  const manifest = buildManifest({
    hash: "movement_prompt_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({
          seq: 1,
          sessionId,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId,
          payload: {
            event_type: "turn_start",
            round_index: 2,
            turn_index: 7,
            acting_player_id: 1,
            character: "어사",
          },
        }),
        {
          type: "prompt",
          seq: 3,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_003,
          payload: {
            request_id: "req_move_ui_1",
            request_type: "movement",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              player_position: 9,
              weather_name: "긴급 피난",
            },
            choices: [
              { choice_id: "roll", title: "Roll dice", description: "Normal move." },
              {
                choice_id: "dice_1_4",
                title: "Use dice cards 1,4",
                description: "Fixed move 5.",
                value: { use_cards: true, card_values: [1, 4] },
              },
              {
                choice_id: "dice_2_5",
                title: "Use dice cards 2,5",
                description: "Fixed move 7.",
                value: { use_cards: true, card_values: [2, 5] },
              },
            ],
          },
        },
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_movement_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "movement");
  await page.getByTestId("movement-card-mode").click();
  await expect(page.getByTestId("movement-card-1")).toBeVisible();
  await expect(page.getByTestId("movement-card-4")).toBeVisible();
  await page.getByTestId("movement-card-1").click();
  await page.getByTestId("movement-card-4").click();
  await expect(page.getByTestId("movement-submit")).toHaveAttribute("data-movement-mode", "cards");
  await expect(page.getByTestId("movement-submit")).toHaveAttribute("data-selected-cards", "1,4");
  await expect(page.getByTestId("movement-submit")).toHaveAttribute("data-choice-id", "dice_1_4");
});

test("purchase and mark prompts render dedicated decision cards", async ({ page }) => {
  const purchaseSession = "sess_prompt_purchase";
  const markSession = "sess_prompt_mark";
  const manifest = buildManifest({
    hash: "decision_prompt_hash_001",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const initialActiveByCard = {
    "1": "어사",
    "2": "자객",
    "3": "추노꾼",
    "4": "아전",
    "5": "교리 감독관",
    "6": "만신",
    "7": "객주",
    "8": "건설업자",
  };

  await installMockRuntime(page, {
    sessionManifests: {
      [purchaseSession]: manifest,
      [markSession]: manifest,
    },
    sessionEvents: {
      [purchaseSession]: [
        eventMessage({
          seq: 1,
          sessionId: purchaseSession,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId: purchaseSession,
          payload: {
            event_type: "round_start",
            round_index: 1,
          },
        }),
        {
          type: "prompt",
          seq: 3,
          session_id: purchaseSession,
          server_time_ms: 1_700_000_000_102,
          payload: {
            request_id: "req_purchase_ui_1",
            request_type: "purchase_tile",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              tile_index: 14,
              cost: 4,
              player_cash: 9,
              zone_color: "하얀색",
            },
            choices: [
              { choice_id: "yes", title: "buy", description: "buy tile" },
              { choice_id: "no", title: "skip", description: "skip purchase" },
            ],
          },
        },
      ],
      [markSession]: [
        eventMessage({
          seq: 1,
          sessionId: markSession,
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
        eventMessage({
          seq: 2,
          sessionId: markSession,
          payload: {
            event_type: "round_start",
            round_index: 1,
            marker_owner_player_id: 2,
            marker_draft_direction: "counterclockwise",
            active_by_card: initialActiveByCard,
            players: [
              { player_id: 1, position: 8, cash: 9, burden: 0, shards: 4, character: "자객" },
              { player_id: 2, position: 3, cash: 9, burden: 0, shards: 4, character: "만신" },
              { player_id: 3, position: 12, cash: 9, burden: 0, shards: 4, character: "추노꾼" },
              { player_id: 4, position: 15, cash: 9, burden: 0, shards: 4, character: "아전" },
            ],
          },
        }),
        eventMessage({
          seq: 3,
          sessionId: markSession,
          payload: {
            event_type: "weather_reveal",
            weather_name: "긴급 피난",
          },
        }),
        eventMessage({
          seq: 4,
          sessionId: markSession,
          payload: {
            event_type: "round_order",
            order: [3, 1, 4, 2],
          },
        }),
        eventMessage({
          seq: 5,
          sessionId: markSession,
          payload: {
            event_type: "turn_start",
            round_index: 1,
            turn_index: 1,
            acting_player_id: 1,
            character: "자객",
          },
        }),
        {
          type: "prompt",
          seq: 6,
          session_id: markSession,
          server_time_ms: 1_700_000_000_202,
          payload: {
            request_id: "req_mark_ui_1",
            request_type: "mark_target",
            player_id: 1,
            timeout_ms: 30000,
            public_context: {
              actor_name: "자객",
              player_position: 8,
            },
            choices: [
              { choice_id: "none", title: "No target", description: "skip mark" },
              {
                choice_id: "mark_p2",
                title: "만신 / P2",
                description: "target P2",
                value: { target_character: "만신", target_player_id: 2 },
              },
              {
                choice_id: "mark_p4",
                title: "아전 / P4",
                description: "target P4",
                value: { target_character: "아전", target_player_id: 4 },
              },
            ],
          },
        },
      ],
    },
    startedSessions: {
      [purchaseSession]: {
        session_id: purchaseSession,
        status: "in_progress",
        round_index: 1,
        turn_index: 1,
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
      [markSession]: {
        session_id: markSession,
        status: "in_progress",
        round_index: 1,
        turn_index: 1,
        initial_active_by_card: initialActiveByCard,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1 },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced" },
          { seat: 4, seat_type: "ai", connected: true, player_id: 4, ai_profile: "balanced" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${purchaseSession}&token=session_p1_purchase_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "purchase_tile");
  await expect(page.getByTestId("purchase-choice-yes")).toHaveAttribute("data-choice-title", "땅 사기");
  await expect(page.getByTestId("purchase-choice-no")).toHaveAttribute("data-choice-title", "구매 없이 턴 종료");

  await page.goto(`/#/match?session=${markSession}&token=session_p1_mark_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "mark_target");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "긴급 피난");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute(
    "data-weather-detail",
    weatherEffectForDisplayName("긴급 피난") ?? ""
  );
  await expect(page.getByTestId("active-character-slot-1")).toHaveAttribute("data-character-name", "어사");
  await expect(page.getByTestId("active-character-slot-2")).toHaveAttribute("data-character-name", "자객");
  await expect(page.getByTestId("active-character-slot-6")).toHaveAttribute("data-character-name", "만신");
  await expect(page.getByTestId("active-character-slot-8")).toHaveAttribute("data-character-name", "건설업자");
  const orderedPlayerCards = page.locator('[data-testid^="match-player-card-"]');
  await expect(orderedPlayerCards).toHaveCount(4);
  await expect(orderedPlayerCards.nth(0)).toHaveAttribute("data-testid", "match-player-card-3");
  await expect(orderedPlayerCards.nth(1)).toHaveAttribute("data-testid", "match-player-card-1");
  await expect(orderedPlayerCards.nth(2)).toHaveAttribute("data-testid", "match-player-card-4");
  await expect(orderedPlayerCards.nth(3)).toHaveAttribute("data-testid", "match-player-card-2");
  await expect(page.getByTestId("mark-choice-mark_p2")).toHaveAttribute("data-target-character", "만신");
  await expect(page.getByTestId("mark-choice-mark_p2")).toHaveAttribute("data-target-player-id", "2");
  await expect(page.getByTestId("mark-choice-none")).toBeVisible();
  await expectLocatorsToShareSingleRow([
    page.getByTestId("mark-choice-mark_p2"),
    page.getByTestId("mark-choice-mark_p4"),
  ]);
});

test("non-default topology fixture renders line board and 3-seat lobby options", async ({ page }) => {
  const fixture = loadFixture("non_default_topology_line_3seat.json");
  expect(fixture.id).toBe("non_default_topology_line_3seat");
  const manifest = buildManifest({
    hash: "line_fixture_hash_001",
    topology: "line",
    tileCount: 6,
    seats: [1, 2, 3],
  });
  await installMockRuntime(page, {
    sessionManifests: { sess_line: manifest },
    sessionEvents: {
      sess_line: [
        eventMessage({
          seq: 1,
          sessionId: "sess_line",
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
      ],
    },
  });

  await page.goto("/#/match?session=sess_line");
  await expect(page.locator(".tile-card")).toHaveCount(6);
  await page.getByRole("button", { name: "로비" }).click();
  const joinOptions = page.getByRole("combobox", { name: "호스트 좌석" }).locator("option");
  await expect(joinOptions).toHaveCount(3);
  await expect(joinOptions.nth(0)).toHaveAttribute("value", "1");
  await expect(joinOptions.nth(1)).toHaveAttribute("value", "2");
  await expect(joinOptions.nth(2)).toHaveAttribute("value", "3");
});

test("manifest-hash reconnect fixture rehydrates projection after session switch", async ({ page }) => {
  const fixture = loadFixture("manifest_hash_reconnect.json");
  expect(fixture.id).toBe("manifest_hash_reconnect");
  const manifestA = buildManifest({
    hash: "manifest_hash_old_aaaa",
    topology: "ring",
    tileCount: 4,
    seats: [1, 2, 3, 4],
  });
  const manifestB = buildManifest({
    hash: "manifest_hash_new_bbbb",
    topology: "line",
    tileCount: 7,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: {
      sess_a: manifestA,
      sess_b: manifestB,
    },
    sessionEvents: {
      sess_a: [
        eventMessage({
          seq: 1,
          sessionId: "sess_a",
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifestA,
          },
        }),
      ],
      sess_b: [
        eventMessage({
          seq: 1,
          sessionId: "sess_b",
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifestB,
          },
        }),
      ],
    },
  });

  await page.goto("/#/match?session=sess_a");
  await expect(page.locator(".tile-card")).toHaveCount(4);

  await page.goto("/#/match?session=sess_b");
  await expect(page.locator(".tile-card")).toHaveCount(7);
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-manifest-hash", manifestB.manifest_hash);
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-board-topology", "line");
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-tile-count", "7");
  await page.getByRole("button", { name: "로비" }).click();
  await expect(page.getByRole("combobox", { name: "호스트 좌석" }).locator("option")).toHaveCount(3);
});

test("parameter matrix fixture rehydrates seat/economy/dice assumptions", async ({ page }) => {
  const fixture = loadFixture("parameter_matrix_economy_dice_2seat.json");
  expect(fixture.id).toBe("parameter_matrix_economy_dice_2seat");
  const manifest = buildManifest({
    hash: "matrix_hash_2seat_55_7_248",
    topology: "line",
    tileCount: 5,
    seats: [1, 2],
    diceValues: [2, 4, 8],
    diceMaxCardsPerTurn: 1,
    startingCash: 55,
    startingShards: 7,
  });

  await installMockRuntime(page, {
    sessionManifests: {
      sess_matrix: manifest,
    },
    sessionEvents: {
      sess_matrix: [
        eventMessage({
          seq: 1,
          sessionId: "sess_matrix",
          payload: {
            event_type: "parameter_manifest",
            parameter_manifest: manifest,
          },
        }),
      ],
    },
  });

  await page.goto("/#/match?session=sess_matrix");
  await page.getByRole("button", { name: "디버그 로그" }).click();
  await expect(page.locator(".tile-card")).toHaveCount(5);
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-manifest-hash", manifest.manifest_hash);
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-starting-cash", "55");
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-starting-shards", "7");
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-dice-values", "2,4,8");
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-seat-allowed", "1,2");
  await expect(page.getByTestId("runtime-manifest-metadata")).toHaveAttribute("data-tile-count", "5");
  await page.getByRole("button", { name: "로비" }).click();
  await expect(page.getByRole("combobox", { name: "호스트 좌석" }).locator("option")).toHaveCount(2);
});
