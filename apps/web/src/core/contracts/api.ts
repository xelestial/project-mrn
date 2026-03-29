export type ApiEnvelope<T> = {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string; retryable: boolean } | null;
};

export type SeatInput = {
  seat: number;
  seat_type: "human" | "ai";
  ai_profile?: string;
};

export type CreateSessionResponse = {
  session_id: string;
  status: string;
  host_token: string;
  join_tokens: Record<string, string>;
  created_at: string;
};

export type SessionView = {
  session_id: string;
  status: string;
  round_index: number;
  turn_index: number;
  created_at: string;
  started_at?: string | null;
  seats: Array<{
    seat: number;
    seat_type: string;
    ai_profile?: string | null;
    player_id?: number | null;
    connected: boolean;
  }>;
};

