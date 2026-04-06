import { expect, test, type Page } from "@playwright/test";

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

function buildTiles(tileCount: number): NonNullable<ManifestRecord["board"]>["tiles"] {
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
      values: [1, 2, 3, 4, 5, 6],
      max_cards_per_turn: 2,
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
      seats?: Array<{
        seat: number;
        seat_type: "human" | "ai";
        ai_profile?: string | null;
        player_id?: number | null;
        connected?: boolean;
        participant_client?: "human_http" | "local_ai" | "external_ai";
        participant_config?: Record<string, unknown>;
      }>;
      parameter_manifest?: ManifestRecord;
    }>;
    joinResults?: Record<string, { session_id: string; seat: number; player_id: number; session_token: string; role: "seat" }>;
    startedSessions?: Record<
      string,
      {
        session_id: string;
        status: string;
        round_index?: number;
        turn_index?: number;
        seats?: Array<{
          seat: number;
          seat_type: "human" | "ai";
          ai_profile?: string | null;
          player_id?: number | null;
          connected?: boolean;
          participant_client?: "human_http" | "local_ai" | "external_ai";
          participant_config?: Record<string, unknown>;
        }>;
        parameter_manifest?: ManifestRecord;
      }
    >;
  }
): Promise<void> {
  await page.addInitScript(
    ({ sessionManifests, sessionEvents, createSessionQueue, joinResults, startedSessions }) => {
      const manifests = sessionManifests as Record<string, ManifestRecord>;
      const eventsBySession = sessionEvents as Record<string, StreamMessage[]>;
      const pendingCreates = [...((createSessionQueue as Array<Record<string, unknown>> | undefined) ?? [])];
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
          { status, headers: { "Content-Type": "application/json" } }
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
          const requestBody = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
          const seat = Number(requestBody.seat ?? 0);
          const result = joinResultMap[`${sessionId}:${seat}`];
          if (!result) {
            return response(null, 404);
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
    args
  );
}

test("human quick start surfaces turn banner and first prompt through stable ids", async ({ page }) => {
  const manifest = buildManifest({
    hash: "human_quick_start_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });
  const sessionId = "sess_human_quick_start";

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 1 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", weather_name: "Cold Front", effect_text: "No lap cash. Pay 2 cash to bank." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 1, turn_index: 1, acting_player_id: 1, character: "Archivist" },
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
                { deck_index: 10, name: "Scout Route", card_description: "Move safely through blue tiles.", is_hidden: false, is_usable: true },
                { deck_index: 11, name: "Tax Break", card_description: "Cut rent in half this turn.", is_hidden: false, is_usable: true },
                { deck_index: 12, name: "Sharp Pivot", card_description: "Gain a shard after a risky landing.", is_hidden: false, is_usable: true },
                { deck_index: 13, name: "Emergency Exit", card_description: "Jump to a safer stop if needed.", is_hidden: false, is_usable: true },
                { deck_index: 14, name: "Companion Step", card_description: "Earn 2 cash when sharing a tile.", is_hidden: false, is_usable: true },
              ],
            },
            choices: [
              { choice_id: "10", title: "Scout Route", description: "Move safely through blue tiles.", value: { deck_index: 10 } },
              { choice_id: "11", title: "Tax Break", description: "Cut rent in half this turn.", value: { deck_index: 11 } },
              { choice_id: "12", title: "Sharp Pivot", description: "Gain a shard after a risky landing.", value: { deck_index: 12 } },
              { choice_id: "13", title: "Emergency Exit", description: "Jump to a safer stop if needed.", value: { deck_index: 13 } },
              { choice_id: "14", title: "Companion Step", description: "Earn 2 cash when sharing a tile.", value: { deck_index: 14 } },
            ],
          },
        },
      ],
    },
    createSessionQueue: [
      {
        session_id: sessionId,
        status: "waiting",
        host_token: "host_human_quick_start",
        join_tokens: { "1": "join_human_1", "2": "join_ai_2", "3": "join_ai_3", "4": "join_ai_4" },
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
        session_token: "session_p1_quick_token_runtime",
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
  await page.getByTestId("quick-start-human-vs-ai").click();

  await expect(page).toHaveURL(/#\/match/);
  await expect(page.getByTestId("board-weather-summary")).toBeVisible();
  await expect(page.getByTestId("core-action-panel")).toBeVisible();
  await expect(page.getByTestId("turn-notice-banner")).toBeVisible();
  await expect(page.getByTestId("prompt-overlay")).toBeVisible();
  await expect(page.getByText("Show raw")).toHaveCount(0);
  await expect(page.getByTestId("trick-choice-10-0")).toBeVisible();
  await expect(page.getByTestId("trick-choice-14-4")).toBeVisible();
  await expect(page.getByTestId("prompt-overlay")).toContainText("Scout Route");
  await expect(page.getByTestId("prompt-overlay")).not.toContainText("Request ID");
});

test("remote turn keeps spectator continuity visible and does not open a local prompt", async ({ page }) => {
  const sessionId = "sess_remote_turn_runtime";
  const manifest = buildManifest({
    hash: "remote_turn_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 1 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", weather_name: "Cold Front", effect_text: "No lap cash. Pay 2 cash to bank." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 1, turn_index: 1, acting_player_id: 2, character: "Bandit" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: { event_type: "dice_roll", round_index: 1, turn_index: 1, player_id: 2, dice_total: 6 },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: {
            event_type: "player_move",
            round_index: 1,
            turn_index: 1,
            player_id: 2,
            from_tile_index: 0,
            to_tile_index: 6,
            path: [1, 2, 3, 4, 5, 6],
          },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "landing_resolved", round_index: 1, turn_index: 1, player_id: 2, summary: "PURCHASE", tile_index: 6 },
        }),
        eventMessage({
          seq: 8,
          sessionId,
          payload: { event_type: "tile_purchased", round_index: 1, turn_index: 1, player_id: 2, tile_index: 6, cost: 2 },
        }),
        eventMessage({
          seq: 9,
          sessionId,
          payload: {
            event_type: "turn_end_snapshot",
            round_index: 1,
            turn_index: 1,
            player_id: 2,
            summary: "P2 turn closed",
          },
        }),
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_remote_runtime`);

  await expect(page.getByTestId("turn-notice-banner")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-panel")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-scene")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-weather")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-weather")).toContainText("Cold Front");
  await expect(page.getByTestId("spectator-turn-character")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-action")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-payoff")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-prompt")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-move")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-spotlight")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-journey")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-progress")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-result")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-handoff")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-spotlight")).toContainText("Bought tile 7 for 2");
  await expect(page.getByTestId("board-move-start-badge")).toBeVisible();
  await expect(page.getByTestId("board-move-end-badge")).toBeVisible();
  await expect(page.getByTestId("board-moving-pawn-ghost")).toBeVisible();
  await expect(page.getByTestId("board-path-step-3")).toBeVisible();
  await expect(page.getByTestId("board-actor-banner")).toBeVisible();
  await expect(page.getByTestId("core-action-journey")).toBeVisible();
  await expect(page.getByTestId("core-action-result-card")).toBeVisible();
  await expect(page.getByTestId("turn-stage-spotlight-strip")).toBeVisible();
  await expect(page.getByTestId("turn-stage-scene-strip")).toBeVisible();
  await expect(page.getByTestId("turn-stage-outcome-strip")).toBeVisible();
  await expect(page.getByTestId("turn-stage-handoff-card")).toBeVisible();
  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0);
  await expect(page.getByTestId("core-action-journey")).toContainText("P2");
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("Bandit");
  await expect(page.getByTestId("spectator-turn-result")).toContainText("Tile purchased");
  await expect(page.getByTestId("spectator-turn-handoff")).toContainText("P2 turn closed");
  await expect(page.getByTestId("turn-stage-handoff-card")).toContainText("P2 turn closed");
});

test("remote turn keeps lap reward, mark, and flip effects visible through spectator and stage panels", async ({ page }) => {
  const sessionId = "sess_remote_turn_effect_runtime";
  const manifest = buildManifest({
    hash: "remote_turn_effect_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3, 4],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 2 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", round_index: 2, turn_index: 4, weather_name: "Cold Front", effect_text: "No lap cash. Pay 2 cash to bank." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 2, turn_index: 4, acting_player_id: 3, character: "Courier" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: { event_type: "lap_reward_chosen", round_index: 2, turn_index: 4, acting_player_id: 3, amount: { cash: 6 } },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: { event_type: "mark_resolved", round_index: 2, turn_index: 4, source_player_id: 3, target_player_id: 1 },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "marker_flip", round_index: 2, turn_index: 4, from_character: "Courier", to_character: "Bandit" },
        }),
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_remote_effect_runtime`);

  await expect(page.getByTestId("spectator-turn-spotlight")).toContainText("Cold Front");
  await expect(page.getByTestId("spectator-turn-spotlight")).toContainText("P3");
  await expect(page.getByTestId("spectator-turn-spotlight")).toContainText("Courier");
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("Card flip");
  await expect(page.getByTestId("turn-stage-spotlight-strip")).toContainText("Card flip");
  await expect(page.getByTestId("turn-stage-outcome-strip")).toContainText("P3");
});

test("mixed participant seats with external ai descriptors still load match runtime cleanly", async ({ page }) => {
  const sessionId = "sess_mixed_participants_runtime";
  const manifest = buildManifest({
    hash: "mixed_participants_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 1 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", weather_name: "Dry Season", effect_text: "Rent increases by 1 on red tiles." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 1, turn_index: 2, acting_player_id: 3, character: "Surveyor" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: { event_type: "decision_requested", round_index: 1, turn_index: 2, player_id: 3, request_type: "movement", provider: "ai" },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: { event_type: "decision_resolved", round_index: 1, turn_index: 2, player_id: 3, request_type: "movement", resolution: "auto", choice_id: "dice", provider: "ai" },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "dice_roll", round_index: 1, turn_index: 2, player_id: 3, dice_total: 5 },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 1,
        turn_index: 2,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "local_ai" },
          {
            seat: 3,
            seat_type: "ai",
            connected: true,
            player_id: 3,
            ai_profile: "balanced",
            participant_client: "external_ai",
            participant_config: {
              transport: "http",
              endpoint: "http://worker.local/decide",
              expected_worker_id: "bot-worker-1",
            },
          },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_runtime`);

  await expect(page.getByTestId("spectator-turn-panel")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-character")).toContainText("Surveyor");
  await expect(page.getByTestId("spectator-turn-weather")).toContainText("Dry Season");
  await expect(page.getByTestId("turn-stage-spotlight-strip")).toContainText("Dry Season");
  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0);
});

test("remote timeout fallback stays visible in spectator and stage flow", async ({ page }) => {
  const sessionId = "sess_remote_timeout_runtime";
  const manifest = buildManifest({
    hash: "remote_timeout_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 1 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "turn_start", round_index: 1, turn_index: 4, acting_player_id: 2, character: "Bandit" },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "decision_requested",
            round_index: 1,
            turn_index: 4,
            player_id: 2,
            request_type: "purchase_tile",
            public_context: { tile_index: 11 },
          },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 1,
            turn_index: 4,
            player_id: 2,
            summary: "defaulted to local AI",
            public_context: {
              tile_index: 11,
              external_ai_worker_id: "prod-bot-1",
              external_ai_failure_code: "external_ai_timeout",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
            },
          },
        }),
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_remote_timeout_runtime`);

  await expect(page.getByTestId("spectator-turn-panel")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("Timeout fallback");
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("prod-bot-1");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("local fallback");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("local_ai");
  await expect(page.getByTestId("turn-stage-scene-strip")).toContainText("Timeout fallback / defaulted to local AI");
});

test("mixed participant runtime keeps timeout and payoff continuity through handoff", async ({ page }) => {
  const sessionId = "sess_mixed_continuity_runtime";
  const manifest = buildManifest({
    hash: "mixed_continuity_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 2 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", weather_name: "Cold Front", effect_text: "No lap cash. Pay 2 cash to bank." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 2, turn_index: 5, acting_player_id: 3, character: "Bandit" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "decision_requested",
            round_index: 2,
            turn_index: 5,
            player_id: 3,
            request_type: "purchase_tile",
            provider: "ai",
            public_context: { tile_index: 8 },
          },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 2,
            turn_index: 5,
            player_id: 3,
            provider: "ai",
            summary: "defaulted to local AI",
            public_context: {
              tile_index: 8,
              external_ai_worker_id: "prod-bot-1",
              external_ai_failure_code: "external_ai_timeout",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
            },
          },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "tile_purchased", round_index: 2, turn_index: 5, player_id: 3, tile_index: 8, cost: 4 },
        }),
        eventMessage({
          seq: 8,
          sessionId,
          payload: { event_type: "turn_end_snapshot", round_index: 2, turn_index: 5, player_id: 3, summary: "P3 turn closed" },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 2,
        turn_index: 5,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "local_ai" },
          {
            seat: 3,
            seat_type: "ai",
            connected: true,
            player_id: 3,
            ai_profile: "balanced",
            participant_client: "external_ai",
            participant_config: {
              transport: "http",
              endpoint: "http://worker.local/decide",
              expected_worker_id: "prod-bot-1",
            },
          },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_continuity_runtime`);

  await expect(page.getByTestId("spectator-turn-panel")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("Timeout fallback");
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("prod-bot-1");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("prod-bot-1");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("local fallback");
  await expect(page.getByTestId("spectator-turn-result")).toContainText("Bought tile 9 for 4");
  await expect(page.getByTestId("spectator-turn-handoff")).toContainText("P3 turn closed");
  await expect(page.getByTestId("turn-stage-outcome-strip")).toContainText("Bought tile 9 for 4");
});

test("mixed participant runtime keeps worker success then fallback visible across consecutive turns", async ({ page }) => {
  const sessionId = "sess_mixed_worker_handoff_runtime";
  const manifest = buildManifest({
    hash: "mixed_worker_handoff_hash",
    topology: "ring",
    tileCount: 32,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 3 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "turn_start", round_index: 3, turn_index: 6, acting_player_id: 2, character: "Scholar" },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "decision_requested",
            round_index: 3,
            turn_index: 6,
            player_id: 2,
            request_type: "lap_reward",
            provider: "ai",
            public_context: {
              external_ai_worker_id: "prod-bot-1",
              external_ai_resolution_status: "resolved_by_worker",
            },
          },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "decision_resolved",
            round_index: 3,
            turn_index: 6,
            player_id: 2,
            provider: "ai",
            resolution: "accepted",
            choice_id: "coins",
            public_context: {
              external_ai_worker_id: "prod-bot-1",
              external_ai_resolution_status: "resolved_by_worker",
            },
          },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: { event_type: "lap_reward_chosen", round_index: 3, turn_index: 6, player_id: 2, choice: "coins", amount: 2 },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "turn_end_snapshot", round_index: 3, turn_index: 6, player_id: 2, summary: "P2 handoff" },
        }),
        eventMessage({
          seq: 8,
          sessionId,
          payload: { event_type: "turn_start", round_index: 3, turn_index: 7, acting_player_id: 3, character: "Bandit" },
        }),
        eventMessage({
          seq: 9,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 3,
            turn_index: 7,
            player_id: 3,
            provider: "ai",
            summary: "defaulted to local AI",
            public_context: {
              tile_index: 10,
              external_ai_worker_id: "prod-bot-1",
              external_ai_failure_code: "external_ai_timeout",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
              external_ai_attempt_count: 3,
            },
          },
        }),
        eventMessage({
          seq: 10,
          sessionId,
          payload: { event_type: "tile_purchased", round_index: 3, turn_index: 7, player_id: 3, tile_index: 10, cost: 3 },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 3,
        turn_index: 7,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "external_ai" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced", participant_client: "external_ai" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_worker_handoff_runtime`);

  await expect(page.getByTestId("spectator-turn-worker")).toContainText("prod-bot-1");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("local fallback");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("attempt 3");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("Participant status");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("prod-bot-1");
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("Participant status");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("external_ai_timeout");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("attempt 3");
  await expect(page.getByTestId("turn-stage-scene-strip")).toContainText("Participant Status");
  await expect(page.getByTestId("turn-stage-outcome-strip")).toContainText("Bought tile 11 for 3");
});

test("mixed participant runtime keeps worker-not-ready fallback and weather continuity visible", async ({ page }) => {
  const sessionId = "sess_mixed_worker_not_ready_runtime";
  const manifest = buildManifest({
    hash: "mixed_worker_not_ready_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 4 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", round_index: 4, turn_index: 3, weather_name: "Dry Season", effect_text: "Rent increases by 1 on red tiles." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 4, turn_index: 3, acting_player_id: 3, character: "Surveyor" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "decision_requested",
            round_index: 4,
            turn_index: 3,
            player_id: 3,
            request_type: "purchase_tile",
            provider: "ai",
            public_context: {
              tile_index: 12,
              external_ai_worker_id: "prod-bot-2",
              external_ai_resolution_status: "pending",
              external_ai_ready_state: "not_ready",
            },
            legal_choices: [
              { choice_id: "yes", label: "Buy tile" },
              { choice_id: "no", label: "Skip purchase", priority: "secondary" },
            ],
          },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 4,
            turn_index: 3,
            player_id: 3,
            provider: "ai",
            summary: "worker reported not ready",
            public_context: {
              tile_index: 12,
              external_ai_worker_id: "prod-bot-2",
              external_ai_failure_code: "external_ai_worker_not_ready",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
              external_ai_attempt_count: 1,
              external_ai_attempt_limit: 3,
              external_ai_ready_state: "not_ready",
            },
          },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "rent_paid", round_index: 4, turn_index: 3, player_id: 3, payer_player_id: 3, owner_player_id: 1, tile_index: 12, final_amount: 5 },
        }),
        eventMessage({
          seq: 8,
          sessionId,
          payload: { event_type: "turn_end_snapshot", round_index: 4, turn_index: 3, player_id: 3, summary: "P3 weather turn closed" },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 4,
        turn_index: 3,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "local_ai" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced", participant_client: "external_ai" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_worker_not_ready_runtime`);

  await expect(page.getByTestId("spectator-turn-weather")).toContainText("Dry Season");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("external_ai_worker_not_ready");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("state not_ready");
  await expect(page.getByTestId("spectator-turn-worker")).toContainText("attempt 1/3");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("Participant status");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("P3 paid P1 5 on tile 13");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("external_ai_worker_not_ready");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("state not_ready");
  await expect(page.getByTestId("turn-stage-scene-strip")).toContainText("Dry Season");
  await expect(page.getByTestId("turn-stage-outcome-strip")).toContainText("P3 paid P1 5 on tile 13");
});

test("mixed participant runtime keeps a long worker-success to fallback chain readable", async ({ page }) => {
  const sessionId = "sess_mixed_long_chain_runtime";
  const manifest = buildManifest({
    hash: "mixed_long_chain_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 5 } }),
        eventMessage({
          seq: 3,
          sessionId,
          payload: { event_type: "weather_reveal", round_index: 5, turn_index: 2, weather_name: "Cold Front", effect_text: "No lap cash. Pay 2 cash to bank." },
        }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "turn_start", round_index: 5, turn_index: 2, acting_player_id: 2, character: "Bandit" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "decision_requested",
            round_index: 5,
            turn_index: 2,
            player_id: 2,
            request_type: "movement",
            provider: "ai",
            public_context: {
              external_ai_worker_id: "prod-bot-3",
              external_ai_resolution_status: "pending",
              external_ai_ready_state: "ready",
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_policy_class: "HeuristicPolicy",
              external_ai_decision_style: "contract_heuristic",
            },
            legal_choices: [{ choice_id: "dice", label: "Roll dice" }],
          },
        }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: {
            event_type: "decision_resolved",
            round_index: 5,
            turn_index: 2,
            player_id: 2,
            resolution: "auto",
            choice_id: "dice",
            provider: "ai",
            public_context: {
              external_ai_worker_id: "prod-bot-3",
              external_ai_resolution_status: "resolved_by_worker",
              external_ai_ready_state: "ready",
              external_ai_attempt_count: 1,
              external_ai_attempt_limit: 2,
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_policy_class: "HeuristicPolicy",
              external_ai_decision_style: "contract_heuristic",
            },
          },
        }),
        eventMessage({
          seq: 7,
          sessionId,
          payload: { event_type: "fortune_drawn", round_index: 5, turn_index: 2, player_id: 2, card_name: "Lucky Wind" },
        }),
        eventMessage({
          seq: 8,
          sessionId,
          payload: { event_type: "fortune_resolved", round_index: 5, turn_index: 2, player_id: 2, summary: "Gain 2 cash." },
        }),
        eventMessage({
          seq: 9,
          sessionId,
          payload: { event_type: "turn_end_snapshot", round_index: 5, turn_index: 2, player_id: 2, summary: "P2 fortune turn closed" },
        }),
        eventMessage({
          seq: 10,
          sessionId,
          payload: { event_type: "turn_start", round_index: 5, turn_index: 3, acting_player_id: 3, character: "Surveyor" },
        }),
        eventMessage({
          seq: 11,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 5,
            turn_index: 3,
            player_id: 3,
            summary: "defaulted to local AI",
            provider: "ai",
            public_context: {
              tile_index: 14,
              external_ai_worker_id: "prod-bot-4",
              external_ai_failure_code: "external_ai_timeout",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
              external_ai_ready_state: "ready",
              external_ai_attempt_count: 2,
              external_ai_attempt_limit: 2,
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_policy_class: "HeuristicPolicy",
              external_ai_decision_style: "contract_heuristic",
            },
          },
        }),
        eventMessage({
          seq: 12,
          sessionId,
          payload: { event_type: "rent_paid", round_index: 5, turn_index: 3, player_id: 3, payer_player_id: 3, owner_player_id: 1, tile_index: 14, final_amount: 6 },
        }),
        eventMessage({
          seq: 13,
          sessionId,
          payload: { event_type: "turn_end_snapshot", round_index: 5, turn_index: 3, player_id: 3, summary: "P3 fallback turn closed" },
        }),
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_long_chain_runtime`);

  await expect(page.getByTestId("spectator-turn-weather")).toContainText("Cold Front");
  await expect(page.getByTestId("spectator-turn-scene")).toContainText("P3 fallback turn closed");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("P3 paid P1 6 on tile 15");
  await expect(page.getByTestId("spectator-turn-journey")).toContainText("Participant status");
  await expect(page.getByTestId("spectator-turn-progress")).toContainText("Decision timeout fallback");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("attempt 2/2");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("mode heuristic_v3_gpt");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("class HeuristicPolicy");
  await expect(page.getByTestId("turn-stage-scene-strip")).toContainText("Round Weather");
  await expect(page.getByTestId("turn-stage-outcome-strip")).toContainText("P3 paid P1 6 on tile 15");
});

test("mixed participant runtime keeps repeated fallback continuity readable across longer chains", async ({ page }) => {
  const sessionId = "sess_mixed_repeated_fallback_chain";
  const manifest = buildManifest({
    hash: "mixed_repeated_fallback_hash",
    topology: "ring",
    tileCount: 40,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 6 } }),
        eventMessage({ seq: 3, sessionId, payload: { event_type: "weather_reveal", round_index: 6, turn_index: 1, weather_name: "Monsoon", effect_text: "Rent +1 on flooded tiles." } }),
        eventMessage({ seq: 4, sessionId, payload: { event_type: "turn_start", round_index: 6, turn_index: 1, acting_player_id: 2, character: "Broker" } }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 6,
            turn_index: 1,
            player_id: 2,
            summary: "defaulted to local AI",
            public_context: {
              tile_index: 10,
              external_ai_worker_id: "prod-bot-8",
              external_ai_failure_code: "external_ai_timeout",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
              external_ai_ready_state: "ready",
              external_ai_attempt_count: 2,
              external_ai_attempt_limit: 2,
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_policy_class: "HeuristicPolicy",
              external_ai_decision_style: "contract_heuristic",
            },
          },
        }),
        eventMessage({ seq: 6, sessionId, payload: { event_type: "tile_purchased", round_index: 6, turn_index: 1, player_id: 2, tile_index: 10, cost: 4 } }),
        eventMessage({ seq: 7, sessionId, payload: { event_type: "turn_end_snapshot", round_index: 6, turn_index: 1, player_id: 2, summary: "P2 fallback purchase closed" } }),
        eventMessage({ seq: 8, sessionId, payload: { event_type: "turn_start", round_index: 6, turn_index: 2, acting_player_id: 3, character: "Oracle" } }),
        eventMessage({
          seq: 9,
          sessionId,
          payload: {
            event_type: "decision_timeout_fallback",
            round_index: 6,
            turn_index: 2,
            player_id: 3,
            summary: "defaulted to local AI",
            public_context: {
              tile_index: 18,
              external_ai_worker_id: "prod-bot-9",
              external_ai_failure_code: "external_ai_worker_not_ready",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "resolved_by_local_fallback",
              external_ai_ready_state: "not_ready",
              external_ai_attempt_count: 1,
              external_ai_attempt_limit: 2,
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_policy_class: "HeuristicPolicy",
              external_ai_decision_style: "contract_heuristic",
            },
          },
        }),
        eventMessage({ seq: 10, sessionId, payload: { event_type: "fortune_resolved", round_index: 6, turn_index: 2, player_id: 3, summary: "Gain 1 shard." } }),
        eventMessage({ seq: 11, sessionId, payload: { event_type: "turn_end_snapshot", round_index: 6, turn_index: 2, player_id: 3, summary: "P3 fallback fortune closed" } }),
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_repeated_fallback_chain`);

  await expect(page.getByTestId("spectator-turn-weather")).toContainText("Monsoon");
  await expect(page.getByTestId("spectator-turn-scene")).toContainText("P3 fallback fortune closed");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("Participant status");
  await expect(page.getByTestId("spectator-turn-payoff-sequence")).toContainText("Fortune effect");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("class HeuristicPolicy");
  await expect(page.getByTestId("turn-stage-worker-status")).toContainText("not_ready");
  await expect(page.getByTestId("turn-stage-outcome-strip")).toContainText("Gain 1 shard.");
});

test("locale toggle persists across reload", async ({ page }) => {
  await page.goto("/#/lobby");

  await expect(page.getByTestId("locale-switch-en")).toHaveClass(/route-tab-active/);
  await page.getByTestId("locale-switch-ko").click();
  await expect(page.getByTestId("locale-switch-ko")).toHaveClass(/route-tab-active/);

  await page.reload();

  await expect(page.getByTestId("locale-switch-ko")).toHaveClass(/route-tab-active/);
  await expect(page.getByTestId("locale-switch-en")).not.toHaveClass(/route-tab-active/);
});
