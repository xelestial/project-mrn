import type { InboundMessage, OutboundMessage } from "../../core/contracts/stream";
import { buildFrontendConnectionUrl } from "../http/connectionRequestManager";

export type FrontendWebSocketCatalogItem = {
  key: string;
  transport: "websocket";
  path: string;
};

export const FRONTEND_WEBSOCKET_CATALOG: FrontendWebSocketCatalogItem[] = [
  { key: "stream.connect", transport: "websocket", path: "/api/v1/sessions/:sessionId/stream" },
  { key: "stream.resume", transport: "websocket", path: "/api/v1/sessions/:sessionId/stream" },
  { key: "stream.decision", transport: "websocket", path: "/api/v1/sessions/:sessionId/stream" },
];

export function buildFrontendStreamWebSocketUrl(args: {
  baseUrl?: string;
  sessionId: string;
  token?: string;
}): string {
  const httpUrl = buildFrontendConnectionUrl({
    baseUrl: args.baseUrl,
    path: `/api/v1/sessions/${encodeURIComponent(args.sessionId)}/stream`,
    query: args.token ? { token: args.token } : undefined,
  });
  return httpUrl.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:");
}

export function createFrontendWebSocket(args: {
  baseUrl?: string;
  sessionId: string;
  token?: string;
}): WebSocket {
  return new WebSocket(buildFrontendStreamWebSocketUrl(args));
}

export function serializeFrontendWebSocketMessage(message: OutboundMessage): string {
  return JSON.stringify(message);
}

export function parseFrontendWebSocketMessage(data: unknown): InboundMessage {
  return JSON.parse(String(data)) as InboundMessage;
}

export function sendFrontendWebSocketMessage(socket: WebSocket, message: OutboundMessage): boolean {
  if (socket.readyState !== WebSocket.OPEN) {
    return false;
  }
  socket.send(serializeFrontendWebSocketMessage(message));
  return true;
}
