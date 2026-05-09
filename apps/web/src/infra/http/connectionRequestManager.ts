export type FrontendConnectionRequestCatalogItem = {
  key: string;
  transport: "http";
  method: "GET" | "POST";
  path: string;
};

type ApiEnvelope<T> = {
  ok?: boolean;
  data?: T | null;
  error?: { code?: string; category?: string; message?: string; retryable?: boolean } | null;
  detail?: unknown;
};

export const FRONTEND_CONNECTION_REQUEST_CATALOG: FrontendConnectionRequestCatalogItem[] = [
  { key: "session.create", transport: "http", method: "POST", path: "/api/v1/sessions" },
  { key: "session.list", transport: "http", method: "GET", path: "/api/v1/sessions" },
  { key: "session.get", transport: "http", method: "GET", path: "/api/v1/sessions/:sessionId" },
  { key: "session.join", transport: "http", method: "POST", path: "/api/v1/sessions/:sessionId/join" },
  { key: "session.start", transport: "http", method: "POST", path: "/api/v1/sessions/:sessionId/start" },
  { key: "session.runtimeStatus", transport: "http", method: "GET", path: "/api/v1/sessions/:sessionId/runtime-status" },
  { key: "session.viewCommit", transport: "http", method: "GET", path: "/api/v1/sessions/:sessionId/view-commit" },
  { key: "session.replay", transport: "http", method: "GET", path: "/api/v1/sessions/:sessionId/replay" },
  { key: "room.create", transport: "http", method: "POST", path: "/api/v1/rooms" },
  { key: "room.list", transport: "http", method: "GET", path: "/api/v1/rooms" },
  { key: "room.get", transport: "http", method: "GET", path: "/api/v1/rooms/:roomNo" },
  { key: "room.join", transport: "http", method: "POST", path: "/api/v1/rooms/:roomNo/join" },
  { key: "room.ready", transport: "http", method: "POST", path: "/api/v1/rooms/:roomNo/ready" },
  { key: "room.leave", transport: "http", method: "POST", path: "/api/v1/rooms/:roomNo/leave" },
  { key: "room.resume", transport: "http", method: "GET", path: "/api/v1/rooms/:roomNo/resume" },
  { key: "room.start", transport: "http", method: "POST", path: "/api/v1/rooms/:roomNo/start" },
  { key: "debug.frontendLog", transport: "http", method: "POST", path: "/api/v1/debug/frontend-log" },
];

let connectionBaseUrl = "";

export class FrontendConnectionRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly category?: string;
  readonly retryable?: boolean;
  readonly body?: unknown;

  constructor(
    message: string,
    args: { status: number; code?: string; category?: string; retryable?: boolean; body?: unknown },
  ) {
    super(message);
    this.name = "FrontendConnectionRequestError";
    this.status = args.status;
    this.code = args.code;
    this.category = args.category;
    this.retryable = args.retryable;
    this.body = args.body;
  }
}

export function normalizeFrontendHttpBaseUrl(value: string | null | undefined): string {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) {
    if (
      typeof window !== "undefined" &&
      typeof window.location?.origin === "string" &&
      window.location.origin.trim()
    ) {
      return window.location.origin.replace(/\/+$/, "");
    }
    return "http://127.0.0.1:9090";
  }
  if (/^https?:\/\//i.test(raw)) {
    return raw.replace(/\/+$/, "");
  }
  return `http://${raw}`.replace(/\/+$/, "");
}

export function setFrontendConnectionBaseUrl(value: string): void {
  connectionBaseUrl = normalizeFrontendHttpBaseUrl(value);
}

export function getFrontendConnectionBaseUrl(): string {
  return normalizeFrontendHttpBaseUrl(connectionBaseUrl);
}

export function buildFrontendConnectionUrl(args: {
  baseUrl?: string;
  path: string;
  query?: Record<string, string | number | boolean | null | undefined>;
}): string {
  const url = new URL(`${normalizeFrontendHttpBaseUrl(args.baseUrl ?? connectionBaseUrl)}${args.path}`);
  for (const [key, value] of Object.entries(args.query ?? {})) {
    if (value === null || typeof value === "undefined") {
      continue;
    }
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

export async function fetchFrontendConnection(args: {
  path: string;
  baseUrl?: string;
  init?: RequestInit;
  retryCount?: number;
  retryDelayMs?: number;
}): Promise<Response> {
  return fetchFrontendConnectionUrl({
    url: buildFrontendConnectionUrl({ baseUrl: args.baseUrl, path: args.path }),
    init: args.init,
    retryCount: args.retryCount,
    retryDelayMs: args.retryDelayMs,
  });
}

export async function fetchFrontendConnectionUrl(args: {
  url: string;
  init?: RequestInit;
  retryCount?: number;
  retryDelayMs?: number;
}): Promise<Response> {
  const retryCount = Math.max(0, Math.floor(args.retryCount ?? 0));
  let attempt = 0;
  let lastError: unknown = null;
  while (attempt <= retryCount) {
    try {
      return await fetch(args.url, {
        ...args.init,
        headers: {
          "Content-Type": "application/json",
          ...(args.init?.headers ?? {}),
        },
      });
    } catch (error) {
      lastError = error;
      if (attempt >= retryCount) {
        break;
      }
      await delay(args.retryDelayMs ?? 0);
    }
    attempt += 1;
  }
  throw lastError;
}

export async function requestFrontendConnectionJson<T>(args: {
  path: string;
  baseUrl?: string;
  init?: RequestInit;
  retryCount?: number;
  retryDelayMs?: number;
  requireData?: boolean;
}): Promise<T> {
  const response = await fetchFrontendConnection(args);
  let payload: ApiEnvelope<T> | null = null;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    payload = null;
  }
  if (!response.ok || payload?.ok === false || (args.requireData === true && payload?.data == null)) {
    throw new FrontendConnectionRequestError(extractErrorMessage(payload, response.status), {
      status: response.status,
      code: payload?.error?.code,
      category: payload?.error?.category,
      retryable: payload?.error?.retryable,
      body: payload,
    });
  }
  return (payload?.data ?? payload ?? {}) as T;
}

function extractErrorMessage(payload: ApiEnvelope<unknown> | null | undefined, status: number): string {
  const directMessage = payload?.error?.message;
  if (typeof directMessage === "string" && directMessage.trim()) {
    return directMessage;
  }
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object") {
    const detailRecord = detail as { error?: { message?: string } | null; message?: unknown };
    const nested = detailRecord.error?.message;
    if (typeof nested === "string" && nested.trim()) {
      return nested;
    }
    if (typeof detailRecord.message === "string" && detailRecord.message.trim()) {
      return detailRecord.message;
    }
  }
  return `Request failed: ${status}`;
}

function delay(ms: number): Promise<void> {
  if (ms <= 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}
