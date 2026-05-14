export type ViewCommitRuntimeStatus = "running" | "waiting_input" | "completed" | "recovery_required";
export type ProtocolPlayerId = number | string;

export type ViewCommitPayload = {
  [key: string]: unknown;
  schema_version: 1;
  commit_seq: number;
  source_event_seq: number;
  round_index: number;
  turn_index: number;
  turn_label: string;
  viewer: {
    role: "spectator" | "seat" | "admin";
    player_id?: ProtocolPlayerId;
    legacy_player_id?: number;
    public_player_id?: string;
    seat?: number;
    seat_id?: string;
    viewer_id?: string;
    seat_index?: number;
    turn_order_index?: number;
    player_label?: string;
  };
  runtime: {
    status: ViewCommitRuntimeStatus;
    round_index: number;
    turn_index: number;
    turn_label: string;
    active_frame_id: string;
    active_module_id: string;
    active_module_type: string;
    module_path: string[];
  };
  view_state: Record<string, unknown>;
};

export type InboundMessage =
  | {
      type: "view_commit";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: ViewCommitPayload;
    }
  | {
      type: "snapshot_pulse";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: ViewCommitPayload & {
        snapshot_pulse?: {
          reason?: string;
          scope?: "all" | "player";
          target_player_id?: ProtocolPlayerId;
          [key: string]: unknown;
        };
      };
    }
  | {
      type: "event";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: Record<string, unknown>;
    }
  | {
      type: "prompt";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: Record<string, unknown>;
    }
  | {
      type: "decision_ack";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: Record<string, unknown>;
    }
  | {
      type: "heartbeat";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: {
        interval_ms?: number;
        backpressure?: {
          subscriber_count?: number;
          drop_count?: number;
          queue_size?: number;
        };
        [key: string]: unknown;
      };
    }
  | {
      type: "error";
      seq: number;
      session_id: string;
      server_time_ms?: number;
      payload: Record<string, unknown>;
    };

export type OutboundMessage =
  | { type: "resume"; last_commit_seq: number }
  | {
      type: "decision";
      request_id: string;
      player_id: ProtocolPlayerId;
      player_id_alias_role?: "legacy_compatibility_alias";
      primary_player_id?: ProtocolPlayerId;
      primary_player_id_source?: "public" | "protocol" | "legacy";
      legacy_player_id?: number;
      public_player_id?: string;
      seat_id?: string;
      viewer_id?: string;
      choice_id: string;
      choice_payload?: Record<string, unknown>;
      prompt_instance_id?: number;
      public_prompt_instance_id?: string;
      prompt_fingerprint?: string;
      prompt_fingerprint_version?: string;
      resume_token?: string;
      frame_id?: string;
      module_id?: string;
      module_type?: string;
      module_cursor?: string;
      batch_id?: string;
      missing_player_ids?: number[];
      resume_tokens_by_player_id?: Record<string, string>;
      missing_public_player_ids?: string[];
      resume_tokens_by_public_player_id?: Record<string, string>;
      missing_seat_ids?: string[];
      resume_tokens_by_seat_id?: Record<string, string>;
      missing_viewer_ids?: string[];
      resume_tokens_by_viewer_id?: Record<string, string>;
      view_commit_seq_seen: number;
      client_seq: number;
    };

export type ConnectionStatus = "idle" | "connecting" | "connected" | "disconnected" | "error";
