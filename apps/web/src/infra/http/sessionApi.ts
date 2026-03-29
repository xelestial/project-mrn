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

type CreateSessionResult = {
  session_id: string;
  status: string;
  host_token: string;
  join_tokens: Record<string, string>;
};

type PublicSessionResult = {
  session_id: string;
  status: string;
};

type RuntimeStatusResult = {
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

export async function startSession(args: {
  sessionId: string;
  hostToken: string;
}): Promise<PublicSessionResult> {
  return requestJson<PublicSessionResult>(`/api/v1/sessions/${encodeURIComponent(args.sessionId)}/start`, {
    method: "POST",
    body: JSON.stringify({ host_token: args.hostToken }),
  });
}

export async function getRuntimeStatus(sessionId: string): Promise<RuntimeStatusResult> {
  return requestJson<RuntimeStatusResult>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/runtime-status`);
}
