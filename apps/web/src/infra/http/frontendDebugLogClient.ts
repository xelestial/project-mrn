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
  const fallbackOrigin =
    typeof window !== "undefined" &&
    typeof window.location?.origin === "string" &&
    window.location.origin.trim()
      ? window.location.origin
      : "http://127.0.0.1:9090";
  const rawBase = (baseUrl || fallbackOrigin).trim().replace(/\/+$/, "");
  const normalizedBase = /^https?:\/\//i.test(rawBase) ? rawBase : `http://${rawBase}`;
  return `${normalizedBase}/api/v1/debug/frontend-log`;
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
  void fetch(buildFrontendDebugLogUrl(args.baseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {
    // Debug logging must never affect gameplay.
  });
}
