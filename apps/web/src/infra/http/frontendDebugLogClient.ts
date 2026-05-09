import {
  buildFrontendConnectionUrl,
  fetchFrontendConnection,
} from "./connectionRequestManager";

type FrontendDebugLogArgs = {
  event: string;
  sessionId?: string;
  seq?: number;
  payload?: Record<string, unknown>;
  baseUrl?: string;
};

export function isFrontendDebugLogEnabled(raw = import.meta.env.VITE_MRN_DEBUG_GAME_LOGS): boolean {
  return String(raw ?? "").trim().toLowerCase() === "1" || String(raw ?? "").trim().toLowerCase() === "true";
}

export function buildFrontendDebugLogUrl(baseUrl?: string): string {
  return buildFrontendConnectionUrl({ baseUrl, path: "/api/v1/debug/frontend-log" });
}

export function logFrontendDebugEvent(args: FrontendDebugLogArgs): void {
  if (!isFrontendDebugLogEnabled()) {
    return;
  }
  const body = JSON.stringify({
    event: args.event,
    session_id: args.sessionId,
    seq: args.seq,
    payload: args.payload ?? {},
  });
  void fetchFrontendConnection({
    baseUrl: args.baseUrl,
    path: "/api/v1/debug/frontend-log",
    init: {
      method: "POST",
      body,
      keepalive: true,
    },
  }).catch(() => {
    // Debug logging must never affect gameplay.
  });
}
