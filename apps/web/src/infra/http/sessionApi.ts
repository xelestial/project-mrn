type SeatType = "human" | "ai";

export type SeatInput = {
  seat: number;
  seat_type: SeatType;
  ai_profile?: string;
};

type ApiEnvelope<T> = {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string; retryable: boolean } | null;
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
};

export type PublicSessionResult = {
  session_id: string;
  status: string;
  round_index?: number;
  turn_index?: number;
  created_at?: string;
  started_at?: string | null;
  seats?: SeatPublic[];
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
  };
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const payload = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !payload.ok || payload.data == null) {
    const message = payload.error?.message ?? `Request failed: ${response.status}`;
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

