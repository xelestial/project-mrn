import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

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
  },
): Promise<void> {
  await page.addInitScript(
    ({ sessionManifests, sessionEvents }) => {
      const manifests = sessionManifests as Record<string, ManifestRecord>;
      const eventsBySession = sessionEvents as Record<string, StreamMessage[]>;

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
        const sessionMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)$/);
        const runtimeMatch = path.match(/^\/api\/v1\/sessions\/([^/]+)\/runtime-status$/);
        if (runtimeMatch) {
          return response({
            session_id: decodeURIComponent(runtimeMatch[1]),
            runtime: { status: "running", watchdog_state: "ok", last_activity_ms: Date.now() },
          });
        }
        if (sessionMatch && (init?.method ?? "GET").toUpperCase() === "GET") {
          const sessionId = decodeURIComponent(sessionMatch[1]);
          const manifest = manifests[sessionId];
          if (!manifest) {
            return response(null, 404);
          }
          return response({
            session_id: sessionId,
            status: "in_progress",
            round_index: 1,
            turn_index: 1,
            seats:
              manifest.seats?.allowed?.map((seat) => ({
                seat,
                seat_type: seat === 1 ? "human" : "ai",
                ai_profile: seat === 1 ? null : "balanced",
                player_id: seat,
                connected: true,
              })) ?? [],
            parameter_manifest: manifest,
          });
        }
        if (path === "/api/v1/sessions" && (init?.method ?? "GET").toUpperCase() === "GET") {
          const sessions = Object.keys(manifests).map((sessionId) => ({
            session_id: sessionId,
            status: "in_progress",
            round_index: 1,
            turn_index: 1,
            seats: [],
            parameter_manifest: manifests[sessionId],
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
  await page.getByRole("button", { name: "Lobby" }).click();
  const joinOptions = page.locator("label:has-text('Join Seat') option");
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
  await page.getByRole("button", { name: "Lobby" }).click();
  await expect(page.locator("label:has-text('Join Seat') option")).toHaveCount(3);
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
  await expect(page.locator(".tile-card")).toHaveCount(5);
  await expect(page.locator(".timeline-item small").first()).toContainText(manifest.manifest_hash.slice(0, 8));
  await expect(page.locator("pre").first()).toContainText('"starting_cash": 55');
  await expect(page.locator("pre").first()).toContainText('"starting_shards": 7');
  await expect(page.locator("pre").first()).toContainText('"values": [');
  await page.getByRole("button", { name: "Lobby" }).click();
  await expect(page.locator("label:has-text('Join Seat') option")).toHaveCount(2);
});
