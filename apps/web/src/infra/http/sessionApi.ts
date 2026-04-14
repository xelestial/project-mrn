type SeatType = "human" | "ai";

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
  const response = await fetch(path, {
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
