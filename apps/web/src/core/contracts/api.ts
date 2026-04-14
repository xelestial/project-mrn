export type ApiEnvelope<T> = {
  ok: boolean;
  data: T | null;
  error: { code: string; category?: string; message: string; retryable: boolean } | null;
};

export type SeatInput = {
  seat: number;
  seat_type: "human" | "ai";
  ai_profile?: string;
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

export type CreateSessionResponse = {
  session_id: string;
  status: string;
  host_token: string;
  join_tokens: Record<string, string>;
  created_at: string;
  parameter_manifest?: ParameterManifest;
  initial_active_by_card?: Record<string, string>;
};

export type SessionView = {
  session_id: string;
  status: string;
  round_index: number;
  turn_index: number;
  created_at: string;
  started_at?: string | null;
  parameter_manifest?: ParameterManifest;
  initial_active_by_card?: Record<string, string>;
  seats: Array<{
    seat: number;
    seat_type: string;
    ai_profile?: string | null;
    player_id?: number | null;
    connected: boolean;
  }>;
};
