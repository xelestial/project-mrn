type SeatType = "human" | "ai";

let apiBaseUrl = "";

export type SeatInput = {
  seat: number;
  seat_type: SeatType;
  ai_profile?: string;
};

type ApiEnvelope<T> = {
  ok: boolean;
  data: T | null;
  error: { code: string; category?: string; message: string; retryable: boolean } | null;
};

type ErrorEnvelope = {
  ok?: boolean;
  data?: unknown;
  error?: { message?: string } | null;
  detail?: unknown;
};

export type ParameterManifest = {
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
      block_id?: number;
      zone_color?: string | null;
      purchase_cost?: number | null;
      rent_cost?: number | null;
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
  labels?: Record<string, unknown>;
};

export type SeatPublic = {
  seat: number;
  seat_type: SeatType;
  ai_profile?: string | null;
  player_id?: number | null;
  display_name?: string | null;
  connected?: boolean;
};

export type CreateSessionResult = {
  session_id: string;
  status: string;
  host_token: string;
  join_tokens: Record<string, string>;
  seats?: SeatPublic[];
  parameter_manifest?: ParameterManifest;
  initial_active_by_card?: Record<string, string>;
};

export type PublicSessionResult = {
  session_id: string;
  status: string;
  seed?: number;
  round_index?: number;
  turn_index?: number;
  created_at?: string;
  started_at?: string | null;
  seats?: SeatPublic[];
  parameter_manifest?: ParameterManifest;
  initial_active_by_card?: Record<string, string>;
};

export type JoinSessionResult = {
  session_id: string;
  seat: number;
  player_id: number;
  session_token: string;
  role: "seat";
};

export type ListSessionsResult = {
  sessions: PublicSessionResult[];
};

export type RuntimeStatusResult = {
  session_id: string;
  runtime: {
    status: string;
    reason?: string;
    error?: string;
    watchdog_state?: string;
    started_at_ms?: number;
    last_activity_ms?: number;
  };
};

export type RoomSeatPublic = {
  seat: number;
  seat_type: SeatType;
  ai_profile?: string | null;
  player_id?: number | null;
  nickname?: string | null;
  ready?: boolean;
  connected?: boolean | null;
};

export type PublicRoomResult = {
  room_no: number;
  room_title: string;
  status: string;
  host_seat: number;
  session_id?: string | null;
  created_at?: string;
  started_at?: string | null;
  human_joined_count: number;
  human_total_count: number;
  human_ready_count: number;
  seats: RoomSeatPublic[];
};

export type CreateRoomResult = {
  room: PublicRoomResult;
  room_member_token: string;
  seat: number;
  nickname: string;
};

export type JoinRoomResult = {
  room: PublicRoomResult;
  room_member_token: string;
  seat: number;
  nickname: string;
};

export type ListRoomsResult = {
  rooms: PublicRoomResult[];
};

export type StartRoomResult = {
  room: PublicRoomResult;
  session_id: string;
  session_tokens: Record<string, string>;
};

export type ResumeRoomResult = PublicRoomResult & {
  member_seat: number;
  member_nickname: string;
  session_token?: string;
};

export function normalizeServerBaseUrl(value: string | null | undefined): string {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) {
    return "http://127.0.0.1:9090";
  }
  if (/^https?:\/\//i.test(raw)) {
    return raw.replace(/\/+$/, "");
  }
  return `http://${raw}`.replace(/\/+$/, "");
}

export function setApiBaseUrl(value: string): void {
  apiBaseUrl = normalizeServerBaseUrl(value);
}

export function getApiBaseUrl(): string {
  return normalizeServerBaseUrl(apiBaseUrl);
}

function buildApiUrl(path: string): string {
  const base = getApiBaseUrl();
  return `${base}${path}`;
}

function extractErrorMessage(payload: ErrorEnvelope | null | undefined, status: number): string {
  const directMessage = payload?.error?.message;
  if (typeof directMessage === "string" && directMessage.trim()) {
    return directMessage;
  }
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object") {
    const detailRecord = detail as { error?: { message?: string } | null; message?: unknown };
    const nested = detailRecord.error?.message;
    if (typeof nested === "string" && nested.trim()) {
      return nested;
    }
    if (typeof detailRecord.message === "string" && detailRecord.message.trim()) {
      return detailRecord.message;
    }
  }
  return `Request failed: ${status}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  let payload: (ApiEnvelope<T> & ErrorEnvelope) | null = null;
  try {
    payload = (await response.json()) as ApiEnvelope<T> & ErrorEnvelope;
  } catch {
    payload = null;
  }
  if (!response.ok || !payload?.ok || payload.data == null) {
    const message = extractErrorMessage(payload, response.status);
    throw new Error(message);
  }
  return payload.data;
}

export async function createSession(args: {
  seats: SeatInput[];
  config?: Record<string, unknown>;
}): Promise<CreateSessionResult> {
  return requestJson<CreateSessionResult>("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify({
      seats: args.seats,
      config: args.config ?? {},
    }),
  });
}

export async function listSessions(): Promise<ListSessionsResult> {
  return requestJson<ListSessionsResult>("/api/v1/sessions");
}

export async function getSession(args: { sessionId: string }): Promise<PublicSessionResult> {
  return requestJson<PublicSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}`);
}

export async function joinSession(args: {
  sessionId: string;
  seat: number;
  joinToken: string;
  displayName?: string;
}): Promise<JoinSessionResult> {
  return requestJson<JoinSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}/join`, {
    method: "POST",
    body: JSON.stringify({
      seat: args.seat,
      join_token: args.joinToken,
      display_name: args.displayName ?? null,
    }),
  });
}

export async function startSession(args: { sessionId: string; hostToken: string }): Promise<PublicSessionResult> {
  return requestJson<PublicSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}/start`, {
    method: "POST",
    body: JSON.stringify({ host_token: args.hostToken }),
  });
}

export async function getRuntimeStatus(sessionId: string): Promise<RuntimeStatusResult> {
  return requestJson<RuntimeStatusResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/runtime-status`);
}

export async function createRoom(args: {
  roomTitle: string;
  hostSeat: number;
  nickname: string;
  seats: SeatInput[];
  config?: Record<string, unknown>;
}): Promise<CreateRoomResult> {
  return requestJson<CreateRoomResult>("/api/v1/rooms", {
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

export async function listRooms(): Promise<ListRoomsResult> {
  return requestJson<ListRoomsResult>("/api/v1/rooms");
}

export async function getRoom(roomNo: number): Promise<PublicRoomResult> {
  return requestJson<PublicRoomResult>(`/api/v1/rooms/${roomNo}`);
}

export async function joinRoom(args: {
  roomNo: number;
  seat: number;
  nickname: string;
}): Promise<JoinRoomResult> {
  return requestJson<JoinRoomResult>(`/api/v1/rooms/${args.roomNo}/join`, {
    method: "POST",
    body: JSON.stringify({
      seat: args.seat,
      nickname: args.nickname,
    }),
  });
}

export async function setRoomReady(args: {
  roomNo: number;
  roomMemberToken: string;
  ready: boolean;
}): Promise<PublicRoomResult> {
  return requestJson<PublicRoomResult>(`/api/v1/rooms/${args.roomNo}/ready`, {
    method: "POST",
    body: JSON.stringify({
      room_member_token: args.roomMemberToken,
      ready: args.ready,
    }),
  });
}

export async function leaveRoom(args: { roomNo: number; roomMemberToken: string }): Promise<PublicRoomResult> {
  return requestJson<PublicRoomResult>(`/api/v1/rooms/${args.roomNo}/leave`, {
    method: "POST",
    body: JSON.stringify({
      room_member_token: args.roomMemberToken,
    }),
  });
}

export async function resumeRoom(args: {
  roomNo: number;
  roomMemberToken: string;
}): Promise<ResumeRoomResult> {
  const params = new URLSearchParams({ room_member_token: args.roomMemberToken });
  return requestJson<ResumeRoomResult>(`/api/v1/rooms/${args.roomNo}/resume?${params.toString()}`);
}

export async function startRoom(args: {
  roomNo: number;
  roomMemberToken: string;
}): Promise<StartRoomResult> {
  return requestJson<StartRoomResult>(`/api/v1/rooms/${args.roomNo}/start`, {
    method: "POST",
    body: JSON.stringify({
      room_member_token: args.roomMemberToken,
    }),
  });
}
