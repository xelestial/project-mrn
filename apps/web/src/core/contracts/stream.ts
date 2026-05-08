export type ViewCommitRuntimeStatus = "running" | "waiting_input" | "completed" | "recovery_required";

export type ViewCommitPayload = {
  [key: string]: unknown;
  schema_version: 1;
  commit_seq: number;
  source_event_seq: number;
  viewer: {
    role: "spectator" | "seat" | "admin";
    player_id?: number;
    seat?: number;
  };
  runtime: {
    status: ViewCommitRuntimeStatus;
    round_index: number;
    turn_index: number;
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
          target_player_id?: number;
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
      player_id: number;
      choice_id: string;
      choice_payload?: Record<string, unknown>;
      prompt_instance_id?: number;
      resume_token?: string;
      frame_id?: string;
      module_id?: string;
      module_type?: string;
      module_cursor?: string;
      batch_id?: string;
      missing_player_ids?: number[];
      resume_tokens_by_player_id?: Record<string, string>;
      view_commit_seq_seen: number;
      client_seq: number;
    };

export type ConnectionStatus = "idle" | "connecting" | "connected" | "disconnected" | "error";
