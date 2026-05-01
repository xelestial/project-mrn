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

async function openPublicEvents(page: Page): Promise<void> {
  await expect(page.getByTestId("board-event-reveal-stack")).toHaveCount(0);
  const toggle = page.locator(".match-table-event-toggle");
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("board-event-reveal-stack")).toBeVisible();
}

async function expectPublicEventsNotDuplicated(page: Page): Promise<void> {
  const duplicateIssues = await page.getByTestId("board-event-reveal-stack").evaluate((panel) => {
    const spotlightSeq = panel.querySelector(".match-table-event-spotlight")?.getAttribute("data-event-seq");
    const repeatedSeqs = spotlightSeq
      ? Array.from(panel.querySelectorAll(".match-table-event-card"))
          .map((card) => card.getAttribute("data-event-seq"))
          .filter((seq) => seq === spotlightSeq)
      : [];
    const repeatedCopy = Array.from(panel.querySelectorAll(".match-table-event-spotlight, .match-table-event-card")).flatMap((card) => {
      const title = card.querySelector("strong")?.textContent?.trim().toLowerCase();
      const detail = card.querySelector("p")?.textContent?.trim().toLowerCase();
      return title && detail && (title === detail || detail.startsWith(`${title} /`)) ? [`${title}:${detail}`] : [];
    });
    return [...repeatedSeqs, ...repeatedCopy];
  });

  expect(duplicateIssues).toEqual([]);
}

async function expectPublicEventsClearRightPlayerCards(page: Page): Promise<void> {
  const overlap = await page.locator(".match-table-overlay").evaluate((overlay) => {
    const eventPanel = overlay.querySelector(".match-table-event-overlay");
    const eventToggle = overlay.querySelector(".match-table-event-toggle");
    const playerCards = Array.from(overlay.querySelectorAll(".match-table-player-card"));
    const rightPlayerCards = [playerCards[1], playerCards[3]].filter(Boolean);
    if (!eventPanel || !eventToggle || rightPlayerCards.length === 0) {
      return null;
    }

    const floatingRects = [eventPanel.getBoundingClientRect(), eventToggle.getBoundingClientRect()];
    return rightPlayerCards.flatMap((card) => {
      const rect = card.getBoundingClientRect();
      return floatingRects.map(
        (eventRect) =>
          Math.max(0, Math.min(eventRect.right, rect.right) - Math.max(eventRect.left, rect.left)) *
          Math.max(0, Math.min(eventRect.bottom, rect.bottom) - Math.max(eventRect.top, rect.top))
      );
    });
  });

  expect(overlap).not.toBeNull();
  expect(overlap).toEqual([0, 0, 0, 0]);
}

async function expectDesktopHudDensity(page: Page): Promise<void> {
  const metrics = await page.locator(".match-table-overlay").evaluate((overlay) => {
    const prompt = overlay.querySelector(".prompt-overlay");
    const playerCards = Array.from(overlay.querySelectorAll(".match-table-player-card"));
    const promptRect = prompt?.getBoundingClientRect();
    const cardMetrics = playerCards.map((card) => {
      const persona = card.querySelector(".match-table-player-persona");
      const statValue = card.querySelector(".match-table-player-stat-value");
      const cardElement = card as HTMLElement;
      return {
        personaFont: persona ? Number.parseFloat(getComputedStyle(persona).fontSize) : 0,
        statValueFont: statValue ? Number.parseFloat(getComputedStyle(statValue).fontSize) : 0,
        verticalOverflow: cardElement.scrollHeight > cardElement.clientHeight + 1,
      };
    });
    return {
      promptWidth: promptRect?.width ?? null,
      viewportWidth: window.innerWidth,
      maxPersonaFont: Math.max(...cardMetrics.map((card) => card.personaFont), 0),
      maxStatValueFont: Math.max(...cardMetrics.map((card) => card.statValueFont), 0),
      verticalOverflow: cardMetrics.some((card) => card.verticalOverflow),
    };
  });

  expect(metrics.promptWidth).not.toBeNull();
  expect(metrics.promptWidth ?? 0).toBeLessThanOrEqual(metrics.viewportWidth * 0.75 + 4);
  expect(metrics.maxPersonaFont).toBeLessThanOrEqual(13.5);
  expect(metrics.maxStatValueFont).toBeLessThanOrEqual(12.5);
  expect(metrics.verticalOverflow).toBe(false);
}

async function expectTrickPromptUsesSixSlots(page: Page): Promise<void> {
  const metrics = await page.getByTestId("prompt-overlay").evaluate((prompt) => {
    const grid = prompt.querySelector<HTMLElement>(".hand-grid-hidden-trick, .hand-grid-trick-to-use");
    if (!grid) {
      return null;
    }
    const gridRect = grid.getBoundingClientRect();
    const cardRects = Array.from(grid.children).map((child) => child.getBoundingClientRect());
    const columns = getComputedStyle(grid)
      .gridTemplateColumns.split(" ")
      .filter((column) => column.trim().length > 0);
    const firstWidth = cardRects[0]?.width ?? 0;
    return {
      columnCount: columns.length,
      gridWidth: gridRect.width,
      firstWidth,
      maxRightOverflow: Math.max(...cardRects.map((rect) => rect.right - gridRect.right), 0),
      widthSpread: Math.max(...cardRects.map((rect) => Math.abs(rect.width - firstWidth)), 0),
    };
  });

  expect(metrics).not.toBeNull();
  expect(metrics?.columnCount).toBe(6);
  expect(metrics?.maxRightOverflow ?? 0).toBeLessThanOrEqual(1);
  expect(metrics?.widthSpread ?? 0).toBeLessThanOrEqual(1);
  expect(metrics?.firstWidth ?? 0).toBeGreaterThan(0);
  expect(metrics?.firstWidth ?? 0).toBeLessThan((metrics?.gridWidth ?? 0) / 5);
}

async function expectTrickPromptHoverKeepsTopBorder(page: Page): Promise<void> {
  const card = page.getByTestId("trick-choice-10-0");
  await card.hover();

  const metrics = await card.evaluate((node) => {
    const grid = node.closest<HTMLElement>(".hand-grid-hidden-trick, .hand-grid-trick-to-use");
    const body = node.closest<HTMLElement>(".prompt-body");
    const cardRect = node.getBoundingClientRect();
    const gridRect = grid?.getBoundingClientRect();
    const bodyRect = body?.getBoundingClientRect();
    const gridStyle = grid ? getComputedStyle(grid) : null;
    return {
      cardTop: cardRect.top,
      gridTop: gridRect?.top ?? null,
      bodyTop: bodyRect?.top ?? null,
      gridOverflowY: gridStyle?.overflowY ?? null,
    };
  });

  expect(metrics.gridTop).not.toBeNull();
  expect(metrics.bodyTop).not.toBeNull();
  expect(metrics.gridOverflowY).toBe("visible");
  expect(metrics.cardTop).toBeGreaterThanOrEqual((metrics.gridTop ?? 0) - 0.5);
  expect(metrics.cardTop).toBeGreaterThanOrEqual((metrics.bodyTop ?? 0) - 0.5);
}

async function expectTurnNoticeAboveWeather(page: Page): Promise<void> {
  const metrics = await page.evaluate(() => {
    const turnNotice = document.querySelector<HTMLElement>(".turn-notice-banner");
    const weather = document.querySelector<HTMLElement>(".match-table-weather-bar");
    const boardOverlay = document.querySelector<HTMLElement>(".board-overlay-content");
    const numericZIndex = (element: HTMLElement | null): number | null => {
      if (!element) {
        return null;
      }
      const value = Number.parseInt(getComputedStyle(element).zIndex, 10);
      return Number.isNaN(value) ? null : value;
    };

    return {
      turnNoticeZIndex: numericZIndex(turnNotice),
      weatherZIndex: numericZIndex(weather),
      boardOverlayZIndex: numericZIndex(boardOverlay),
    };
  });

  expect(metrics.turnNoticeZIndex).not.toBeNull();
  expect(metrics.weatherZIndex).not.toBeNull();
  expect(metrics.boardOverlayZIndex).not.toBeNull();
  expect(metrics.turnNoticeZIndex ?? 0).toBeGreaterThan(metrics.weatherZIndex ?? 0);
  expect(metrics.turnNoticeZIndex ?? 0).toBeGreaterThan(metrics.boardOverlayZIndex ?? 0);
}

async function expectCharacterPromptSingleRow(page: Page, viewportWidth: number): Promise<void> {
  const metrics = await page.getByTestId("prompt-overlay").evaluate((prompt) => {
    const grid = prompt.querySelector<HTMLElement>(".prompt-character-card-grid");
    const body = prompt.querySelector<HTMLElement>(".prompt-body");
    const cards = Array.from(prompt.querySelectorAll<HTMLElement>(".prompt-character-card"));
    const cardRows = new Set(cards.map((card) => Math.round(card.getBoundingClientRect().top)));
    const gridStyle = grid ? getComputedStyle(grid) : null;
    const gridColumns = gridStyle?.gridTemplateColumns
      .split(" ")
      .map((track) => track.trim())
      .filter(Boolean).length ?? 0;

    return {
      promptWidth: prompt.getBoundingClientRect().width,
      cardCount: cards.length,
      rowCount: cardRows.size,
      gridColumns,
      bodyOverflowsY: body ? body.scrollHeight > body.clientHeight + 1 : null,
      gridOverflowsY: grid ? grid.scrollHeight > grid.clientHeight + 1 : null,
      gridOverflowsX: grid ? grid.scrollWidth > grid.clientWidth + 1 : null,
    };
  });

  expect(metrics.promptWidth).toBeLessThanOrEqual(Math.min(viewportWidth * 0.8, 1280) + 2);
  expect(metrics.promptWidth).toBeGreaterThanOrEqual(Math.min(viewportWidth * 0.8, 1280) - 8);
  expect(metrics.cardCount).toBe(4);
  expect(metrics.rowCount).toBe(1);
  expect(metrics.gridColumns).toBe(4);
  expect(metrics.bodyOverflowsY).toBe(false);
  expect(metrics.gridOverflowsY).toBe(false);
  expect(metrics.gridOverflowsX).toBe(false);
}

async function expectProjectedBoardMessagesReadable(page: Page): Promise<void> {
  const metrics = await page.locator(".board-projected-tile-layer").evaluate(() => {
    const tileContents = Array.from(document.querySelectorAll<HTMLElement>(".board-projected-content"));
    const zoneLabel = document.querySelector<HTMLElement>(".board-projected-zone strong");
    const mainPanel = document.querySelector<HTMLElement>(".board-projected-main");
    const economyPill = document.querySelector<HTMLElement>(
      ".board-projected-cost, .board-projected-owner, .board-projected-score"
    );
    const specialLabel = document.querySelector<HTMLElement>(".board-projected-special strong");
    const fontWeightValue = (element: HTMLElement | null): number => {
      if (!element) return 0;
      const weight = getComputedStyle(element).fontWeight;
      if (weight === "bold") return 700;
      const parsed = Number.parseInt(weight, 10);
      return Number.isNaN(parsed) ? 0 : parsed;
    };
    const hasVisibleBackground = (element: HTMLElement | null): boolean => {
      if (!element) return false;
      const style = getComputedStyle(element);
      return style.backgroundImage !== "none" || style.backgroundColor !== "rgba(0, 0, 0, 0)";
    };

    return {
      tileContentCount: tileContents.length,
      zoneFontSize: zoneLabel ? Number.parseFloat(getComputedStyle(zoneLabel).fontSize) : 0,
      zoneFontWeight: fontWeightValue(zoneLabel),
      zoneTextShadow: zoneLabel ? getComputedStyle(zoneLabel).textShadow : "none",
      mainHasVisibleBackground: hasVisibleBackground(mainPanel),
      economyFontWeight: fontWeightValue(economyPill),
      economyTextShadow: economyPill ? getComputedStyle(economyPill).textShadow : "none",
      specialFontWeight: fontWeightValue(specialLabel),
    };
  });

  expect(metrics.tileContentCount).toBeGreaterThan(0);
  expect(metrics.zoneFontSize).toBeGreaterThanOrEqual(13);
  expect(metrics.zoneFontWeight).toBeGreaterThanOrEqual(900);
  expect(metrics.zoneTextShadow).not.toBe("none");
  expect(metrics.mainHasVisibleBackground).toBe(true);
  expect(metrics.economyFontWeight).toBeGreaterThanOrEqual(850);
  expect(metrics.economyTextShadow).not.toBe("none");
  expect(metrics.specialFontWeight).toBeGreaterThanOrEqual(900);
}

async function expectMyTurnCelebrationClearPlayerTwo(page: Page): Promise<void> {
  const overlap = await page.locator(".match-table-overlay").evaluate((overlay) => {
    const celebration = document.querySelector<HTMLElement>('[data-testid="my-turn-celebration"]');
    const playerTwo = overlay.querySelector<HTMLElement>('[data-testid="match-player-card-2"]');
    if (!celebration || !playerTwo) {
      return null;
    }

    const waitingRect = celebration.getBoundingClientRect();
    const playerRect = playerTwo.getBoundingClientRect();
    return (
      Math.max(0, Math.min(waitingRect.right, playerRect.right) - Math.max(waitingRect.left, playerRect.left)) *
      Math.max(0, Math.min(waitingRect.bottom, playerRect.bottom) - Math.max(waitingRect.top, playerRect.top))
    );
  });

  expect(overlap).not.toBeNull();
  expect(overlap).toBe(0);
}

async function expectMyTurnCelebrationSpinningBorder(page: Page): Promise<void> {
  const animationName = await page
    .getByTestId("my-turn-celebration")
    .evaluate((element) => getComputedStyle(element, "::before").animationName);

  expect(animationName).toContain("myTurnBorderSpin");
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
  await page.setViewportSize({ width: 1440, height: 900 });

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
  await expect(page.locator(".board-panel")).toBeVisible();
  await expect(page.getByTestId("prompt-overlay")).toBeVisible();
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-presentation-mode", "decision-focus");
  await expect(page.getByTestId("prompt-overlay-title")).toBeVisible();
  await expect(page.getByTestId("prompt-overlay-helper")).toBeVisible();
  await expect(page.getByTestId("prompt-head-meta")).toBeVisible();
  await expect(page.getByRole("button", { name: "Debug log" })).toHaveCount(1);
  await expect(page.getByTestId("trick-choice-10-0")).toHaveAttribute("data-card-name", "Scout Route");
  await expect(page.getByTestId("trick-choice-14-4")).toBeVisible();
  await expectTrickPromptUsesSixSlots(page);
  await expectTrickPromptHoverKeepsTopBorder(page);
  await expectDesktopHudDensity(page);
});

test("character selection prompt uses one four-card row without scrollbars on desktop viewports", async ({ page }) => {
  const sessionId = "sess_character_prompt_layout";
  const manifest = buildManifest({
    hash: "character_prompt_layout_hash",
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
          payload: { event_type: "turn_start", round_index: 1, turn_index: 1, acting_player_id: 1, character: "Hidden" },
        }),
        {
          type: "prompt",
          seq: 5,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_005,
          payload: {
            request_id: "req_final_character_layout",
            request_type: "final_character_choice",
            player_id: 1,
            timeout_ms: 300000,
            public_context: {},
            choices: [
              { choice_id: "tamgwanori", title: "탐관오리", description: "세금과 통행료 흐름을 빠르게 굴립니다.", value: { character: "탐관오리" } },
              { choice_id: "matchmaker", title: "뚜쟁이", description: "인접 토지와 협상 선택지를 강화합니다.", value: { character: "뚜쟁이" } },
              { choice_id: "bandit", title: "도적", description: "상대의 자원 흐름을 끊고 기회를 만듭니다.", value: { character: "도적" } },
              { choice_id: "doctrine_guard", title: "교리 감독관", description: "짐을 줄이고 안정적인 점수를 준비합니다.", value: { character: "교리 감독관" } },
            ],
          },
        },
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_character_layout`);
  await expect(page.getByTestId("prompt-overlay")).toHaveAttribute("data-prompt-type", "final_character_choice");

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1600, height: 1000 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await expectCharacterPromptSingleRow(page, viewport.width);
  }
});

test("my-turn celebration replaces the waiting panel and stays clear of the second player card", async ({ page }) => {
  const sessionId = "sess_waiting_panel_layout";
  const manifest = buildManifest({
    hash: "waiting_panel_layout_hash",
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
          payload: { event_type: "turn_start", round_index: 1, turn_index: 1, acting_player_id: 1, character: "Archivist" },
        }),
      ],
    },
  });

  await page.goto(`/#/match?session=${sessionId}&token=session_p1_waiting_layout`);
  await expect(page.getByTestId("my-turn-waiting-panel")).toHaveCount(0);
  await expect(page.getByTestId("my-turn-celebration")).toBeVisible();
  await expect(page.getByTestId("my-turn-celebration")).toHaveAttribute("data-turn-owner", "local");
  await expect(page.getByTestId("my-turn-celebration")).toContainText(/당신의 턴!|Your turn!/);
  await expectMyTurnCelebrationSpinningBorder(page);

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1600, height: 1000 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await expectMyTurnCelebrationClearPlayerTwo(page);
  }
});

test("remote turn keeps spectator continuity visible and does not open a local prompt", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

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
  await expect(page.getByTestId("turn-notice-banner")).toHaveAttribute("data-banner-variant", "turn");
  await expect(page.getByTestId("turn-notice-banner")).toHaveAttribute("data-banner-player-id", "2");
  await expectTurnNoticeAboveWeather(page);
  await openPublicEvents(page);
  await expectPublicEventsNotDuplicated(page);
  await expect(page.getByTestId("board-event-reveal-dice_roll-1")).toHaveAttribute("data-event-code", "dice_roll");
  await expect(page.getByTestId("board-event-reveal-player_move-2")).toHaveAttribute("data-event-code", "player_move");
  await expect(page.getByTestId("board-event-reveal-landing_resolved-3")).toHaveAttribute("data-event-code", "landing_resolved");
  await expect(page.getByTestId("board-event-reveal-tile_purchased-4")).toHaveCount(0);
  await expect(page.getByTestId("board-event-spotlight-tile_purchased")).toBeVisible();
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "Cold Front");
  await expect(page.getByTestId("board-move-start-badge")).toHaveCount(1);
  await expect(page.getByTestId("board-move-end-badge")).toHaveCount(1);
  await expect(page.getByTestId("board-path-step-3")).toHaveCount(1);
  await expect(page.getByTestId("board-actor-banner")).toHaveCount(1);
  await expect(page.getByTestId("turn-stage-actor-status")).toHaveCount(0);
  await expect(page.getByTestId("prompt-overlay")).toHaveCount(0);
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1600, height: 1000 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await expectPublicEventsClearRightPlayerCards(page);
  }
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

  await expect(page.getByTestId("spectator-turn-weather")).toHaveAttribute("data-weather-name", "Cold Front");
  await expect(page.getByTestId("spectator-turn-character")).toHaveAttribute("data-character-name", "Courier");
  await expect(page.getByTestId("spectator-turn-journey-step-1")).toHaveAttribute("data-step-key", "flip");
  await expect(page.getByTestId("spectator-turn-payoff-step-1")).toHaveAttribute("data-beat-key", "flip");
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
  await expect(page.getByTestId("spectator-turn-character")).toHaveAttribute("data-character-name", "Surveyor");
  await expect(page.getByTestId("spectator-turn-weather")).toHaveAttribute("data-weather-name", "Dry Season");
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

  const workerCard = page.getByTestId("spectator-turn-worker");
  const journeyStep1 = page.getByTestId("spectator-turn-journey-step-1");
  await expect(page.getByTestId("spectator-turn-panel")).toBeVisible();
  await expect(journeyStep1).toHaveAttribute("data-step-key", "worker");
  await expect(journeyStep1).toHaveAttribute("data-step-tone", "decision");
  await expect(workerCard).toHaveAttribute("data-worker-id", "prod-bot-1");
  await expect(workerCard).toHaveAttribute("data-worker-fallback-mode", "local_ai");
  await expect(workerCard).toHaveAttribute("data-worker-resolution-status", "resolved_by_local_fallback");
  await expect(page.getByTestId("spectator-turn-prompt-title")).toBeVisible();
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

  const workerCard = page.getByTestId("spectator-turn-worker");
  const journeyStep1 = page.getByTestId("spectator-turn-journey-step-1");
  await expect(page.getByTestId("spectator-turn-panel")).toBeVisible();
  await expect(journeyStep1).toHaveAttribute("data-step-key", "worker");
  await expect(journeyStep1).toHaveAttribute("data-step-tone", "decision");
  await expect(workerCard).toHaveAttribute("data-worker-id", "prod-bot-1");
  await expect(workerCard).toHaveAttribute("data-worker-failure-code", "external_ai_timeout");
  await expect(workerCard).toHaveAttribute("data-worker-fallback-mode", "local_ai");
  await expect(page.getByTestId("spectator-turn-result")).toHaveAttribute("data-result-key", "purchase");
  await expect(page.getByTestId("spectator-turn-result")).toHaveAttribute("data-result-tone", "economy");
  await expect(page.getByTestId("spectator-turn-handoff")).toBeVisible();
  await expect(page.getByTestId("spectator-turn-payoff-step-1")).toHaveAttribute("data-beat-key", "purchase");
  await expect(page.getByTestId("spectator-turn-payoff-step-1")).toHaveAttribute("data-beat-tone", "economy");
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
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_worker_adapter: "priority_score_v1",
              external_ai_policy_class: "PriorityScoredPolicy",
              external_ai_decision_style: "priority_scored_contract",
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
              external_ai_ready_state: "ready",
              external_ai_attempt_count: 1,
              external_ai_attempt_limit: 1,
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_worker_adapter: "priority_score_v1",
              external_ai_policy_class: "PriorityScoredPolicy",
              external_ai_decision_style: "priority_scored_contract",
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
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_worker_adapter: "priority_score_v1",
              external_ai_policy_class: "PriorityScoredPolicy",
              external_ai_decision_style: "priority_scored_contract",
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

  const workerCard = page.getByTestId("spectator-turn-worker");
  await expect(workerCard).toHaveAttribute("data-worker-id", "prod-bot-1");
  await expect(workerCard).toHaveAttribute("data-worker-attempt-count", "3");
  await expect(workerCard).toHaveAttribute("data-worker-failure-code", "external_ai_timeout");
  await expect(workerCard).toHaveAttribute("data-worker-policy-class", "PriorityScoredPolicy");
  await expect(workerCard).toHaveAttribute("data-worker-adapter", "priority_score_v1");
  await expect(page.getByTestId("spectator-turn-payoff-step-1")).toHaveAttribute("data-beat-key", "worker");
  await expect(page.getByTestId("spectator-turn-payoff-step-1")).toHaveAttribute("data-beat-tone", "effect");
  await expect(page.getByTestId("spectator-turn-journey-step-1")).toHaveAttribute("data-step-key", "worker");
  await expect(page.getByTestId("spectator-turn-journey-step-1")).toHaveAttribute("data-step-tone", "decision");
  await expect(page.getByTestId("spectator-turn-payoff-step-2")).toHaveAttribute("data-beat-key", "purchase");
  await expect(page.getByTestId("spectator-turn-payoff-step-2")).toHaveAttribute("data-beat-tone", "economy");
});

test("mixed participant runtime keeps timeout fallback and weather continuity visible", async ({ page }) => {
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

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mixed_worker_not_ready_runtime`);

  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "Dry Season");
  await expect(page.getByTestId("board-reveal-spotlight-rent_paid")).toHaveCount(1);
  const boostedRentOverlay = page.locator(".game-event-overlay[data-event-kind='rent_receive']");
  await expect(boostedRentOverlay).toBeVisible();
  await expect(boostedRentOverlay).toHaveAttribute("data-effect-source", "weather");
  await expect(boostedRentOverlay).toHaveAttribute("data-effect-intent", "boost");
  await expect(boostedRentOverlay).toHaveAttribute("data-effect-enhanced", "true");
  await expect(boostedRentOverlay).toHaveAttribute("data-effect-badge", "날씨 강화");
  await expect(boostedRentOverlay.getByTestId("game-event-effect-badge")).toHaveText("날씨 강화");
  await expect(boostedRentOverlay.locator(".game-event-effect-bolt")).toHaveCount(2);
  await expectProjectedBoardMessagesReadable(page);
  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-spotlight-rent_paid")).toHaveAttribute("data-effect-source", "weather");
  await expect(page.getByTestId("board-event-attribution-rent_paid")).toHaveText("Weather boost");
  await expectPublicEventsNotDuplicated(page);
});

test("runtime keeps fortune cash loss cause readable in overlay and event feed", async ({ page }) => {
  const sessionId = "sess_fortune_loss_attribution_runtime";
  const manifest = buildManifest({
    hash: "fortune_loss_attr_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 7 } }),
        eventMessage({ seq: 3, sessionId, payload: { event_type: "turn_start", round_index: 7, turn_index: 1, acting_player_id: 2, character: "Oracle" } }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: { event_type: "fortune_drawn", round_index: 7, turn_index: 1, player_id: 2, card_name: "Unlucky Tax" },
        }),
        eventMessage({
          seq: 5,
          sessionId,
          payload: {
            event_type: "fortune_resolved",
            round_index: 7,
            turn_index: 1,
            player_id: 2,
            card_name: "Unlucky Tax",
            summary: "Unlucky Tax: Lose 2 cash.",
          },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 7,
        turn_index: 1,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "local_ai" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/match?session=${sessionId}&token=session_p1_fortune_loss_attribution_runtime`);

  const fortuneOverlay = page.locator(".game-event-overlay[data-event-kind='fortune']");
  await expect(fortuneOverlay).toBeVisible();
  await expect(fortuneOverlay).toHaveAttribute("data-effect-source", "fortune");
  await expect(fortuneOverlay).toHaveAttribute("data-effect-intent", "loss");
  await expect(fortuneOverlay).toHaveAttribute("data-effect-badge", "운수 손실");
  await expect(fortuneOverlay.locator(".game-event-effect-shock")).toHaveCount(1);
  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-spotlight-fortune_resolved")).toHaveAttribute("data-effect-source", "fortune");
  await expect(page.getByTestId("board-event-attribution-fortune_resolved")).toHaveText("Fortune loss");
  await expect(page.getByTestId("board-event-spotlight-detail-fortune_resolved")).toContainText("Lose 2 cash");
  await expectPublicEventsNotDuplicated(page);
});

test("runtime keeps innkeeper lap bonus breakdown readable", async ({ page }) => {
  const sessionId = "sess_innkeeper_bonus_attribution_runtime";
  const manifest = buildManifest({
    hash: "innkeeper_bonus_attr_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 8 } }),
        eventMessage({ seq: 3, sessionId, payload: { event_type: "turn_start", round_index: 8, turn_index: 1, acting_player_id: 1, character: "객주" } }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "lap_reward_chosen",
            round_index: 8,
            turn_index: 1,
            player_id: 1,
            amount: { cash: 4 },
            summary: "기본 보상 2 + 객주 보너스 2",
          },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 8,
        turn_index: 1,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "local_ai" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/match?session=${sessionId}&token=session_p1_innkeeper_bonus_attribution_runtime`);

  const lapOverlay = page.locator(".game-event-overlay[data-event-kind='lap_complete']");
  await expect(lapOverlay).toBeVisible();
  await expect(lapOverlay).toHaveAttribute("data-effect-source", "character");
  await expect(lapOverlay).toHaveAttribute("data-effect-intent", "gain");
  await expect(lapOverlay).toHaveAttribute("data-effect-badge", "캐릭터 보너스");
  await expect(lapOverlay).toContainText("객주 보너스 2");
  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-spotlight-lap_reward_chosen")).toHaveAttribute("data-effect-source", "character");
  await expect(page.getByTestId("board-event-attribution-lap_reward_chosen")).toHaveText("Innkeeper bonus");
  await expect(page.getByTestId("board-event-spotlight-detail-lap_reward_chosen")).toContainText("객주 보너스 2");
  await expectPublicEventsNotDuplicated(page);
});

test("runtime gives Manshin successful mark a distinct readable effect", async ({ page }) => {
  const sessionId = "sess_mark_character_effects_runtime";
  const manifest = buildManifest({
    hash: "mark_character_effects_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2, 3],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 9 } }),
        eventMessage({ seq: 3, sessionId, payload: { event_type: "turn_start", round_index: 9, turn_index: 1, acting_player_id: 2, character: "박수" } }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "mark_resolved",
            round_index: 9,
            turn_index: 1,
            player_id: 2,
            source_player_id: 2,
            target_player_id: 1,
            actor_name: "박수",
            effect_type: "baksu_transfer",
            resolution: {
              type: "baksu_transfer",
              actor_name: "박수",
              burden_count: 2,
              reward_count: 2,
              summary: "박수 지목 성공 / P2 -> P1 / 짐 2장 전달 / 잔꾀 2장 획득",
            },
            summary: "박수 지목 성공 / P2 -> P1 / 짐 2장 전달 / 잔꾀 2장 획득",
          },
        }),
        eventMessage({ seq: 5, sessionId, payload: { event_type: "turn_start", round_index: 9, turn_index: 2, acting_player_id: 3, character: "만신" } }),
        eventMessage({
          seq: 6,
          sessionId,
          payload: {
            event_type: "mark_resolved",
            round_index: 9,
            turn_index: 2,
            player_id: 3,
            source_player_id: 3,
            target_player_id: 1,
            actor_name: "만신",
            effect_type: "manshin_remove_burdens",
            resolution: {
              type: "manshin_remove_burdens",
              actor_name: "만신",
              removed_count: 3,
              paid_amount: 6,
              cash_delta: 6,
              summary: "만신 지목 성공 / P1 짐 3장 제거 / P3 +6냥",
            },
            summary: "만신 지목 성공 / P1 짐 3장 제거 / P3 +6냥",
          },
        }),
      ],
    },
    startedSessions: {
      [sessionId]: {
        session_id: sessionId,
        status: "in_progress",
        round_index: 9,
        turn_index: 2,
        seats: [
          { seat: 1, seat_type: "human", connected: true, player_id: 1, participant_client: "human_http" },
          { seat: 2, seat_type: "ai", connected: true, player_id: 2, ai_profile: "balanced", participant_client: "local_ai" },
          { seat: 3, seat_type: "ai", connected: true, player_id: 3, ai_profile: "balanced", participant_client: "local_ai" },
        ],
        parameter_manifest: manifest,
      },
    },
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/match?session=${sessionId}&token=session_p1_mark_character_effects_runtime`);

  const manshinOverlay = page.locator(".game-event-overlay[data-event-kind='mark_success']");
  await expect(manshinOverlay).toBeVisible();
  await expect(manshinOverlay).toHaveAttribute("data-effect-source", "mark");
  await expect(manshinOverlay).toHaveAttribute("data-effect-character", "만신");
  await expect(manshinOverlay).toHaveAttribute("data-effect-badge", "만신 지목 성공");
  await expect(manshinOverlay.locator(".game-event-effect-cleansing-ring")).toHaveCount(1);
  await expect(manshinOverlay).toContainText("+6냥");

  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-attribution-mark_resolved").first()).toHaveText("Manshin mark");
  await expect(page.getByTestId("board-event-spotlight-detail-mark_resolved")).toContainText("만신 지목 성공");
  await expectPublicEventsNotDuplicated(page);
});

test("runtime gives Baksu successful mark a distinct burden-transfer effect", async ({ page }) => {
  const sessionId = "sess_baksu_mark_effect_runtime";
  const manifest = buildManifest({
    hash: "baksu_mark_effect_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2],
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 9 } }),
        eventMessage({ seq: 3, sessionId, payload: { event_type: "turn_start", round_index: 9, turn_index: 1, acting_player_id: 2, character: "박수" } }),
        eventMessage({
          seq: 4,
          sessionId,
          payload: {
            event_type: "mark_resolved",
            round_index: 9,
            turn_index: 1,
            player_id: 2,
            source_player_id: 2,
            target_player_id: 1,
            actor_name: "박수",
            effect_type: "baksu_transfer",
            resolution: {
              type: "baksu_transfer",
              actor_name: "박수",
              burden_count: 2,
              reward_count: 2,
              summary: "박수 지목 성공 / P2 -> P1 / 짐 2장 전달 / 잔꾀 2장 획득",
            },
            summary: "박수 지목 성공 / P2 -> P1 / 짐 2장 전달 / 잔꾀 2장 획득",
          },
        }),
      ],
    },
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/match?session=${sessionId}&token=session_p1_baksu_mark_effect_runtime`);

  const baksuOverlay = page.locator(".game-event-overlay[data-event-kind='mark_success']");
  await expect(baksuOverlay).toBeVisible();
  await expect(baksuOverlay).toHaveAttribute("data-effect-source", "mark");
  await expect(baksuOverlay).toHaveAttribute("data-effect-character", "박수");
  await expect(baksuOverlay).toHaveAttribute("data-effect-badge", "박수 지목 성공");
  await expect(baksuOverlay.locator(".game-event-effect-burden-card")).toHaveCount(2);
  await expect(baksuOverlay).toContainText("잔꾀 2장 획득");

  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-attribution-mark_resolved")).toHaveText("Baksu mark");
  await expect(page.getByTestId("board-event-spotlight-detail-mark_resolved")).toContainText("박수 지목 성공");
  await expectPublicEventsNotDuplicated(page);
});

test("matchmaker adjacent purchase prompt labels the ability and double-price context", async ({ page }) => {
  const sessionId = "sess_matchmaker_purchase_prompt_runtime";
  const manifest = buildManifest({
    hash: "matchmaker_purchase_prompt_hash",
    topology: "ring",
    tileCount: 36,
    seats: [1, 2],
    startingShards: 3,
  });

  await installMockRuntime(page, {
    sessionManifests: { [sessionId]: manifest },
    sessionEvents: {
      [sessionId]: [
        eventMessage({ seq: 1, sessionId, payload: { event_type: "parameter_manifest", parameter_manifest: manifest } }),
        eventMessage({ seq: 2, sessionId, payload: { event_type: "round_start", round_index: 10 } }),
        eventMessage({ seq: 3, sessionId, payload: { event_type: "turn_start", round_index: 10, turn_index: 1, acting_player_id: 1, character: "중매꾼" } }),
        {
          type: "prompt",
          seq: 4,
          session_id: sessionId,
          server_time_ms: 1_700_000_000_004,
          payload: {
            request_id: "req_matchmaker_purchase_1",
            request_type: "purchase_tile",
            player_id: 1,
            timeout_ms: 300000,
            public_context: {
              source: "matchmaker_adjacent",
              tile_index: 6,
              landing_tile_index: 5,
              cost: 8,
              tile_purchase_cost: 4,
              base_cost: 4,
              player_cash: 20,
              player_shards: 3,
              candidate_tiles: [6],
            },
            choices: [
              { choice_id: "yes", title: "Buy adjacent tile", description: "Buy tile 7 for 8 cash.", value: { buy: true } },
              { choice_id: "no", title: "Skip purchase", description: "Do not buy.", value: { buy: false } },
            ],
          },
        },
      ],
    },
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/match?session=${sessionId}&token=session_p1_matchmaker_purchase_prompt_runtime`);

  const prompt = page.getByTestId("prompt-overlay");
  await expect(prompt).toBeVisible();
  await expect(prompt).toHaveAttribute("data-prompt-type", "purchase_tile");
  await expect(prompt).toHaveAttribute("data-purchase-source", "matchmaker_adjacent");
  await expect(prompt).toHaveAttribute("data-effect-character", "중매꾼");
  await expect(page.getByTestId("matchmaker-purchase-context")).toContainText("중매꾼 추가 구매");
  await expect(page.getByTestId("matchmaker-purchase-context")).toContainText("2배 가격");
  await expect(page.getByTestId("matchmaker-purchase-context")).toContainText("기본 4 -> 비용 8");
  await expect(page.getByTestId("purchase-choice-yes")).toHaveAttribute("data-choice-title", "중매꾼 추가 구매");
  await expect(page.getByTestId("purchase-choice-yes")).toHaveAttribute("data-choice-description", /2배 가격/);
  await expect(page.getByTestId("purchase-choice-yes")).toHaveAttribute("data-choice-description", /기본 4 x 2 = 8/);
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
              external_ai_worker_adapter: "reference_heuristic_v1",
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
              external_ai_worker_adapter: "reference_heuristic_v1",
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
              external_ai_worker_adapter: "reference_heuristic_v1",
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

  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-reveal-rent_paid-1")).toHaveAttribute("data-event-code", "rent_paid");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "Cold Front");
  await expect(page.getByTestId("core-action-latest")).toHaveAttribute("data-latest-event-code", "turn_end_snapshot");
  await expect(page.getByTestId("core-action-result-card")).toHaveAttribute("data-result-event-code", "fortune_resolved");
  await expect(page.getByTestId("core-action-result-card")).toHaveAttribute("data-result-kind", "effect");
  await expect(page.getByTestId("core-action-result-card-1")).toHaveAttribute("data-result-event-code", "fortune_drawn");
  await expect(page.getByTestId("core-action-result-card-1")).toHaveAttribute("data-result-kind", "effect");
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
              external_ai_worker_adapter: "reference_heuristic_v1",
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
              external_ai_worker_adapter: "reference_heuristic_v1",
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

  await expect(page.getByTestId("turn-notice-banner")).toBeVisible();
  await expect(page.getByTestId("turn-notice-banner")).toHaveAttribute("data-banner-variant", "interrupt");
  await expect(page.getByTestId("turn-notice-banner")).toHaveAttribute("data-banner-has-detail", "true");
  await expect(page.getByTestId("board-weather-summary")).toHaveAttribute("data-weather-name", "Monsoon");
  await openPublicEvents(page);
  await expect(page.getByTestId("board-event-reveal-fortune_resolved-1")).toHaveAttribute("data-event-code", "fortune_resolved");
  await expect(page.getByTestId("board-reveal-spotlight-fortune_resolved")).toBeVisible();
  await expect(page.getByTestId("core-action-result-card")).toHaveAttribute("data-result-event-code", "fortune_resolved");
  await expect(page.getByTestId("core-action-result-card")).toHaveAttribute("data-result-kind", "effect");
  await expect(page.getByTestId("core-action-journey-step-1")).toHaveAttribute("data-journey-event-code", "decision_timeout_fallback");
  await expect(page.getByTestId("core-action-journey-step-1")).toHaveAttribute("data-journey-kind", "decision");
  await expect(page.getByTestId("core-action-latest")).toHaveAttribute("data-latest-event-code", "turn_end_snapshot");
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
