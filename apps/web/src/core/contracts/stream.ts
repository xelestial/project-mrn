export const VIEW_STATE_RESTORED_EVENT = "view_state_restored";

export type InboundMessage =
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
  | { type: "resume"; last_seq: number }
  | {
      type: "decision";
      request_id: string;
      player_id: number;
      choice_id: string;
      choice_payload?: Record<string, unknown>;
      resume_token?: string;
      frame_id?: string;
      module_id?: string;
      module_type?: string;
      module_cursor?: string;
      batch_id?: string;
      client_seq: number;
    };

export type ConnectionStatus = "idle" | "connecting" | "connected" | "disconnected" | "error";
