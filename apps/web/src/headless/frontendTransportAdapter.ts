import type { InboundMessage, OutboundMessage } from "../core/contracts/stream";
import {
  FRONTEND_CONNECTION_REQUEST_CATALOG,
  FrontendConnectionRequestError,
  buildFrontendConnectionUrl,
  normalizeFrontendHttpBaseUrl,
  requestFrontendConnectionJson,
} from "../infra/http/connectionRequestManager";
import type {
  CreateRoomResult,
  CreateSessionResult,
  JoinRoomResult,
  JoinSessionResult,
  ListRoomsResult,
  ListSessionsResult,
  PublicRoomResult,
  PublicSessionResult,
  ResumeRoomResult,
  RuntimeStatusResult,
  SeatInput,
  StartRoomResult,
  ViewCommitResult,
} from "../infra/http/sessionApi";
import {
  FRONTEND_WEBSOCKET_CATALOG,
  buildFrontendStreamWebSocketUrl,
  serializeFrontendWebSocketMessage,
} from "../infra/ws/webSocketManager";

export { normalizeFrontendHttpBaseUrl };

type ReplayResponseBody = {
  session_id?: unknown;
  events?: unknown;
};

export type FrontendTransportRequestCatalogItem = {
  key: string;
  transport: "http" | "websocket";
  method?: "GET" | "POST";
  path: string;
};

export const FRONTEND_TRANSPORT_REQUEST_CATALOG: FrontendTransportRequestCatalogItem[] = [
  ...FRONTEND_CONNECTION_REQUEST_CATALOG,
  ...FRONTEND_WEBSOCKET_CATALOG,
];

export class FrontendTransportCatalogMismatchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FrontendTransportCatalogMismatchError";
  }
}

export class FrontendTransportApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  readonly code: string;

  constructor(status: number, body: unknown) {
    super(`Frontend transport request failed (${status}): ${JSON.stringify(body)}`);
    this.name = "FrontendTransportApiError";
    this.status = status;
    this.body = body;
    this.code = extractApiErrorCode(body);
  }
}

export type FrontendTransportAdapterArgs = {
  baseUrl?: string;
  fetchRetryCount?: number;
  fetchRetryDelayMs?: number;
};

export class FrontendTransportAdapter {
  readonly baseUrl: string;
  private readonly fetchRetryCount: number;
  private readonly fetchRetryDelayMs: number;

  constructor(args: FrontendTransportAdapterArgs = {}) {
    assertFrontendTransportManagersCovered();
    this.baseUrl = normalizeFrontendHttpBaseUrl(args.baseUrl);
    this.fetchRetryCount = Math.max(0, Math.floor(args.fetchRetryCount ?? 0));
    this.fetchRetryDelayMs = Math.max(0, Math.floor(args.fetchRetryDelayMs ?? 150));
  }

  createSession(args: { seats: SeatInput[]; config?: Record<string, unknown> }): Promise<CreateSessionResult> {
    return this.requestJson<CreateSessionResult>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({
        seats: args.seats,
        config: args.config ?? {},
      }),
    });
  }

  listSessions(): Promise<ListSessionsResult> {
    return this.requestJson<ListSessionsResult>("/api/v1/sessions");
  }

  getSession(args: { sessionId: string }): Promise<PublicSessionResult> {
    return this.requestJson<PublicSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}`);
  }

  joinSession(args: {
    sessionId: string;
    seat: number;
    joinToken: string;
    displayName?: string | null;
  }): Promise<JoinSessionResult> {
    return this.requestJson<JoinSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}/join`, {
      method: "POST",
      body: JSON.stringify({
        seat: args.seat,
        join_token: args.joinToken,
        display_name: args.displayName ?? null,
      }),
    });
  }

  startSession(args: { sessionId: string; hostToken: string }): Promise<PublicSessionResult> {
    return this.requestJson<PublicSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}/start`, {
      method: "POST",
      body: JSON.stringify({ host_token: args.hostToken }),
    });
  }

  getRuntimeStatus(args: { sessionId: string; token?: string }): Promise<RuntimeStatusResult> {
    return this.requestJson<RuntimeStatusResult>(
      sessionPathWithToken(args.sessionId, "runtime-status", args.token),
    );
  }

  getViewCommit(args: { sessionId: string; token?: string }): Promise<ViewCommitResult> {
    return this.requestJson<ViewCommitResult>(sessionPathWithToken(args.sessionId, "view-commit", args.token));
  }

  fetchReplayMessages(args: { sessionId: string; token?: string; signal?: AbortSignal }): Promise<InboundMessage[]> {
    return this.requestJson<ReplayResponseBody>(sessionPathWithToken(args.sessionId, "replay", args.token), {
      signal: args.signal,
    })
      .then((body) => {
        const events = body.events;
        return Array.isArray(events) ? events.filter(isInboundMessage) : [];
      })
      .catch(() => []);
  }

  createRoom(args: {
    roomTitle: string;
    hostSeat: number;
    nickname: string;
    seats: SeatInput[];
    config?: Record<string, unknown>;
  }): Promise<CreateRoomResult> {
    return this.requestJson<CreateRoomResult>("/api/v1/rooms", {
      method: "POST",
      body: JSON.stringify({
        room_title: args.roomTitle,
        host_seat: args.hostSeat,
        nickname: args.nickname,
        seats: args.seats,
        config: args.config ?? {},
      }),
    });
  }

  listRooms(): Promise<ListRoomsResult> {
    return this.requestJson<ListRoomsResult>("/api/v1/rooms");
  }

  getRoom(roomNo: number): Promise<PublicRoomResult> {
    return this.requestJson<PublicRoomResult>(`/api/v1/rooms/${roomNo}`);
  }

  joinRoom(args: { roomNo: number; seat: number; nickname: string }): Promise<JoinRoomResult> {
    return this.requestJson<JoinRoomResult>(`/api/v1/rooms/${args.roomNo}/join`, {
      method: "POST",
      body: JSON.stringify({
        seat: args.seat,
        nickname: args.nickname,
      }),
    });
  }

  setRoomReady(args: { roomNo: number; roomMemberToken: string; ready: boolean }): Promise<PublicRoomResult> {
    return this.requestJson<PublicRoomResult>(`/api/v1/rooms/${args.roomNo}/ready`, {
      method: "POST",
      body: JSON.stringify({
        room_member_token: args.roomMemberToken,
        ready: args.ready,
      }),
    });
  }

  leaveRoom(args: { roomNo: number; roomMemberToken: string }): Promise<PublicRoomResult> {
    return this.requestJson<PublicRoomResult>(`/api/v1/rooms/${args.roomNo}/leave`, {
      method: "POST",
      body: JSON.stringify({
        room_member_token: args.roomMemberToken,
      }),
    });
  }

  resumeRoom(args: { roomNo: number; roomMemberToken: string }): Promise<ResumeRoomResult> {
    return this.requestJson<ResumeRoomResult>(
      `/api/v1/rooms/${args.roomNo}/resume?${new URLSearchParams({ room_member_token: args.roomMemberToken })}`,
    );
  }

  startRoom(args: { roomNo: number; roomMemberToken: string }): Promise<StartRoomResult> {
    return this.requestJson<StartRoomResult>(`/api/v1/rooms/${args.roomNo}/start`, {
      method: "POST",
      body: JSON.stringify({
        room_member_token: args.roomMemberToken,
      }),
    });
  }

  logFrontendDebugEvent(args: { event: string; sessionId?: string; seq?: number; payload?: Record<string, unknown> }): void {
    void this.requestJson<unknown>("/api/v1/debug/frontend-log", {
      method: "POST",
      keepalive: true,
      body: JSON.stringify({
        event: args.event,
        session_id: args.sessionId,
        seq: args.seq,
        payload: args.payload ?? {},
      }),
    }).catch(() => {
      // Debug logging mirrors the browser client: never affect gameplay.
    });
  }

  buildStreamUrl(args: { sessionId: string; token?: string }): string {
    return buildFrontendStreamUrl({ baseUrl: this.baseUrl, sessionId: args.sessionId, token: args.token });
  }

  serializeStreamMessage(message: OutboundMessage): string {
    return serializeFrontendWebSocketMessage(message);
  }

  async requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    try {
      return await requestFrontendConnectionJson<T>({
        baseUrl: this.baseUrl,
        path,
        init,
        retryCount: this.fetchRetryCount,
        retryDelayMs: this.fetchRetryDelayMs,
      });
    } catch (error) {
      if (error instanceof FrontendConnectionRequestError) {
        throw new FrontendTransportApiError(error.status, error.body);
      }
      throw error;
    }
  }
}

export function assertFrontendTransportManagersCovered(
  adapterCatalog: FrontendTransportRequestCatalogItem[] = FRONTEND_TRANSPORT_REQUEST_CATALOG,
): void {
  const expected = [...FRONTEND_CONNECTION_REQUEST_CATALOG, ...FRONTEND_WEBSOCKET_CATALOG];
  const expectedByKey = new Map(expected.map((item) => [item.key, item]));
  const actualByKey = new Map(adapterCatalog.map((item) => [item.key, item]));
  const missing = expected.filter((item) => !actualByKey.has(item.key)).map((item) => item.key);
  const extra = adapterCatalog.filter((item) => !expectedByKey.has(item.key)).map((item) => item.key);
  const changed = expected
    .filter((item) => {
      const actual = actualByKey.get(item.key);
      return actual ? catalogSignature(actual) !== catalogSignature(item) : false;
    })
    .map((item) => item.key);
  if (missing.length || extra.length || changed.length) {
    throw new FrontendTransportCatalogMismatchError(
      [
        "Frontend transport catalog does not match manager catalogs.",
        missing.length ? `missing=${missing.join(",")}` : "",
        extra.length ? `extra=${extra.join(",")}` : "",
        changed.length ? `changed=${changed.join(",")}` : "",
      ].filter(Boolean).join(" "),
    );
  }
}

export function buildFrontendTransportUrl(
  baseUrl: string | undefined,
  path: string,
  query?: Record<string, string | number | boolean | null | undefined>,
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return buildFrontendConnectionUrl({ baseUrl, path: normalizedPath, query });
}

export function buildFrontendStreamUrl(args: { baseUrl?: string; sessionId: string; token?: string }): string {
  return buildFrontendStreamWebSocketUrl(args);
}

function sessionPathWithToken(sessionId: string, suffix: "runtime-status" | "view-commit" | "replay", token?: string): string {
  const params = new URLSearchParams();
  if (token?.trim()) {
    params.set("token", token.trim());
  }
  const query = params.toString();
  return `/api/v1/sessions/${encodeURIComponent(sessionId)}/${suffix}${query ? `?${query}` : ""}`;
}

function extractApiErrorCode(body: unknown): string {
  if (!isRecord(body)) {
    return "";
  }
  const code = body.code;
  if (typeof code === "string") {
    return code;
  }
  const error = body.error;
  if (isRecord(error) && typeof error.code === "string") {
    return error.code;
  }
  return "";
}

function isInboundMessage(value: unknown): value is InboundMessage {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value["type"] === "string" &&
    typeof value["seq"] === "number" &&
    typeof value["session_id"] === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function catalogSignature(item: FrontendTransportRequestCatalogItem): string {
  return JSON.stringify({
    key: item.key,
    transport: item.transport,
    method: item.method ?? null,
    path: item.path,
  });
}
