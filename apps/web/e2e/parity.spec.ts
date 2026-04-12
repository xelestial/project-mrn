import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { weatherEffectForDisplayName } from "../src/domain/catalogs/gameplayCatalog";

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
    createSessionQueue?: Array<{
      session_id: string;
      status: string;
      host_token: string;
      join_tokens: Record<string, string>;
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
        seats?: Array<{ seat: number; seat_type: "human" | "ai"; ai_profile?: string | null; player_id?: number | null; connected?: boolean }>;
        parameter_manifest?: ManifestRecord;
      }
    >;
  },
): Promise<void> {
  await page.addInitScript(
    ({ sessionManifests, sessionEvents, createSessionQueue, joinResults, startedSessions }) => {
      const manifests = sessionManifests as Record<string, ManifestRecord>;
      const eventsBySession = sessionEvents as Record<string, StreamMessage[]>;
      const pendingCreates = [...(createSessionQueue as Array<Record<string, unknown>> | undefined ?? [])];
      const joinResultMap = (joinResults as Record<string, Record<string, unknown>> | undefined) ?? {};
      const startedSessionMap = (startedSessions as Record<string, Record<string, unknown>> | undefined) ?? {};
      const sessionSnapshots = new Map<string, Record<string, unknown>>();

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

      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const urlValue = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const url = new URL(urlValue, window.location.origin);
        const path = url.pathname;
        const method = (init?.method ?? "GET").toUpperCase();
        const sessionMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)$/);
        const runtimeMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/runtime-status$/);
        const joinMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/join$/);
        const startMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/start$/);
        if (runtimeMatch) {
          return response({
            session_id: decodeURIComponent(runtimeMatch[1]),
            runtime: { status: "running", watchdog_state: "ok", last_activity_ms: Date.now() },
          });
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
          }, 0);
        }

        send(data: string): void {
          let payload: Record<string, unknown> = {};
          try {
            payload = JSON.parse(data) as Record<string, unknown>;
          } catch {
            return;
          }
          if (payload.type !== "resume") {
            return;
          }
          const match = this.url.match(/\/api\/v1\/sessions\/([^/]+)\/stream/);
          const sessionId = match ? decodeURIComponent(match[1]) : "";
          const lastSeq = typeof payload.last_seq === "number" ? payload.last_seq : 0;
          const replay = (eventsBySession[sessionId] ?? []).filter((message) => message.seq > lastSeq);
          replay.forEach((message, index) => {
            window.setTimeout(() => {
              if (this.readyState !== MockWebSocket.OPEN) {
                return;
              }
              this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(message) }));
            }, index * 5);
          });
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
    args,
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
            timeout_ms: 300000,
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

  await page.goto("/#/lobby");
  await page.getByRole("button", { name: "사람 1 + AI 3 빠른 시작" }).click();

  await expect(page).toHaveURL(/#\/match/);
  await expect(page.getByTestId("board-weather-summary")).toBeVisible();
  await expect(page.getByTestId("core-action-flow-panel")).toBeVisible();
  await expect(page.getByText("선택 요청: 히든 잔꾀 지정")).toBeVisible();
  await expect(page.getByText("손패 전체 5장 / 히든 0장")).toBeVisible();
  await expect(page.getByText("현재 라운드 날씨")).toBeVisible();
  const weatherSummary = page.getByTestId("board-weather-summary");
  await expect(weatherSummary).toContainText("긴급 피난");
  await expect(weatherSummary).toContainText(weatherEffectForDisplayName("긴급 피난") ?? "");
  await expect(page.getByText("교리 연구관", { exact: true })).toBeVisible();
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
            timeout_ms: 300000,
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
  await expect(page.getByTestId("movement-submit")).toContainText("주사위 카드 1, 4 사용");
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
        {
          type: "prompt",
          seq: 2,
          session_id: purchaseSession,
          server_time_ms: 1_700_000_000_102,
          payload: {
            request_id: "req_purchase_ui_1",
            request_type: "purchase_tile",
            player_id: 1,
            timeout_ms: 300000,
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
        {
          type: "prompt",
          seq: 2,
          session_id: markSession,
          server_time_ms: 1_700_000_000_202,
          payload: {
            request_id: "req_mark_ui_1",
            request_type: "mark_target",
            player_id: 1,
            timeout_ms: 300000,
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
  });

  await page.goto(`/#/match?session=${purchaseSession}&token=session_p1_purchase_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "purchase_tile");
  await expect(page.getByTestId("purchase-choice-yes")).toContainText("토지 구매");
  await expect(page.getByTestId("purchase-choice-no")).toContainText("구매 없이 턴 종료");

  await page.goto(`/#/match?session=${markSession}&token=session_p1_mark_demo`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "mark_target");
  await expect(page.getByTestId("mark-choice-mark_p2")).toContainText("만신 / P2");
  await expect(page.getByTestId("mark-choice-mark_p2")).toContainText("대상 인물 / 플레이어: 만신 / P2");
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
  const joinOptions = page.locator("label:has-text('참가 좌석') option");
  await expect(joinOptions).toHaveCount(3);
  await expect(joinOptions.nth(0)).toContainText("Seat 1");
  await expect(joinOptions.nth(1)).toContainText("Seat 2");
  await expect(joinOptions.nth(2)).toContainText("Seat 3");
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
  await expect(page.locator(".timeline-item small").first()).toContainText(manifestB.manifest_hash.slice(0, 8));
  await page.getByRole("button", { name: "로비" }).click();
  await expect(page.locator("label:has-text('참가 좌석') option")).toHaveCount(3);
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
  await page.getByRole("button", { name: "Raw 보기" }).click();
  await expect(page.locator(".tile-card")).toHaveCount(5);
  await expect(page.locator(".timeline-item small").first()).toContainText(manifest.manifest_hash.slice(0, 8));
  await expect(page.locator("pre").first()).toContainText('"starting_cash": 55');
  await expect(page.locator("pre").first()).toContainText('"starting_shards": 7');
  await expect(page.locator("pre").first()).toContainText('"values": [');
  await page.getByRole("button", { name: "로비" }).click();
  await expect(page.locator("label:has-text('참가 좌석') option")).toHaveCount(2);
});
