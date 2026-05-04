import { VIEW_STATE_RESTORED_EVENT, type InboundMessage } from "../../core/contracts/stream";

type ReplayResponseBody = {
  ok?: boolean;
  data?: {
    session_id?: unknown;
    events?: unknown;
    view_state?: unknown;
  };
};

function browserOrigin(): string {
  if (
    typeof window !== "undefined" &&
    typeof window.location?.origin === "string" &&
    window.location.origin.trim()
  ) {
    return window.location.origin;
  }
  return "http://127.0.0.1:9090";
}

function normalizeHttpBaseUrl(baseUrl?: string): string {
  const rawBase = (baseUrl || browserOrigin()).trim().replace(/\/+$/, "");
  return /^https?:\/\//i.test(rawBase) ? rawBase : `http://${rawBase}`;
}

function isInboundMessage(value: unknown): value is InboundMessage {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record["type"] === "string" &&
    typeof record["seq"] === "number" &&
    typeof record["session_id"] === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

export function buildReplayUrl(args: {
  sessionId: string;
  token?: string;
  baseUrl?: string;
}): string {
  const base = normalizeHttpBaseUrl(args.baseUrl);
  const url = new URL(
    `${base}/api/v1/sessions/${encodeURIComponent(args.sessionId)}/replay`,
  );
  if (args.token) {
    url.searchParams.set("token", args.token);
  }
  return url.toString();
}

export async function fetchReplayMessages(args: {
  sessionId: string;
  token?: string;
  baseUrl?: string;
  signal?: AbortSignal;
  projectionSeqFloor?: number;
}): Promise<InboundMessage[]> {
  const response = await fetch(buildReplayUrl(args), { signal: args.signal });
  if (!response.ok) {
    return [];
  }
  const body = (await response.json()) as ReplayResponseBody;
  const events = body.data?.events;
  if (!Array.isArray(events)) {
    return [];
  }
  const messages = events.filter(isInboundMessage);
  const viewState = body.data?.view_state;
  if (!isRecord(viewState)) {
    return messages;
  }
  const sessionId =
    typeof body.data?.session_id === "string" && body.data.session_id.trim()
      ? body.data.session_id
      : args.sessionId;
  const maxSeq = messages.reduce((highest, message) => Math.max(highest, message.seq), 0);
  const projectionSeq = Math.max(maxSeq, args.projectionSeqFloor ?? 0) + 1;
  messages.push({
    type: "event",
    seq: projectionSeq,
    session_id: sessionId,
    payload: {
      event_type: VIEW_STATE_RESTORED_EVENT,
      view_state: viewState,
    },
  });
  return messages;
}
