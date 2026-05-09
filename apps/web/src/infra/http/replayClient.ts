import type { InboundMessage } from "../../core/contracts/stream";
import {
  buildFrontendConnectionUrl,
  requestFrontendConnectionJson,
} from "./connectionRequestManager";

type ReplayResponseBody = {
  session_id?: unknown;
  events?: unknown;
};

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

export function buildReplayUrl(args: {
  sessionId: string;
  token?: string;
  baseUrl?: string;
}): string {
  return buildFrontendConnectionUrl({
    baseUrl: args.baseUrl,
    path: `/api/v1/sessions/${encodeURIComponent(args.sessionId)}/replay`,
    query: args.token ? { token: args.token } : undefined,
  });
}

export async function fetchReplayMessages(args: {
  sessionId: string;
  token?: string;
  baseUrl?: string;
  signal?: AbortSignal;
}): Promise<InboundMessage[]> {
  let body: ReplayResponseBody;
  try {
    body = await requestFrontendConnectionJson<ReplayResponseBody>({
      baseUrl: args.baseUrl,
      path: `/api/v1/sessions/${encodeURIComponent(args.sessionId)}/replay${args.token ? `?${new URLSearchParams({ token: args.token }).toString()}` : ""}`,
      init: { signal: args.signal },
    });
  } catch {
    return [];
  }
  const events = body.events;
  if (!Array.isArray(events)) {
    return [];
  }
  return events.filter(isInboundMessage);
}
