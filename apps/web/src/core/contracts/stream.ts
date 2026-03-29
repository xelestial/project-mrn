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
      payload: Record<string, unknown>;
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
  | { type: "decision"; request_id: string; player_id: number; choice_id: string; client_seq: number };

export type ConnectionStatus = "idle" | "connecting" | "connected" | "disconnected" | "error";
