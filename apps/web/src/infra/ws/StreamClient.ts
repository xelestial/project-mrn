import type { ConnectionStatus, InboundMessage, OutboundMessage } from "../../core/contracts/stream";

export class StreamClient {
  private baseUrl = "";
  private socket: WebSocket | null = null;
  private onMessageHandlers: Array<(message: InboundMessage) => void> = [];
  private onStatusHandlers: Array<(status: ConnectionStatus) => void> = [];
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private closedByUser = false;
  private lastConnectParams: { sessionId: string; token?: string; onOpenResumeCommitSeq?: number; baseUrl?: string } | null = null;
  private connectionKey = "";

  connect(params: { sessionId: string; token?: string; onOpenResumeCommitSeq?: number; baseUrl?: string }): void {
    this.closedByUser = false;
    this.lastConnectParams = params;
    this.baseUrl = params.baseUrl ?? this.baseUrl;
    this.clearReconnectTimer();
    const tokenQuery = params.token ? `?token=${encodeURIComponent(params.token)}` : "";
    const url = this.buildSocketUrl(params.sessionId, tokenQuery);
    const nextConnectionKey = `${params.sessionId}\n${params.token ?? ""}\n${this.baseUrl}`;
    if (
      this.socket &&
      this.connectionKey === nextConnectionKey &&
      (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)
    ) {
      return;
    }
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.onerror = null;
      this.socket.onmessage = null;
      this.socket.close();
      this.socket = null;
    }
    this.emitStatus("connecting");
    const socket = new WebSocket(url);
    this.socket = socket;
    this.connectionKey = nextConnectionKey;

    socket.onopen = () => {
      if (this.socket !== socket) {
        return;
      }
      this.reconnectAttempt = 0;
      this.emitStatus("connected");
      if (typeof params.onOpenResumeCommitSeq === "number" && params.onOpenResumeCommitSeq > 0) {
        this.send({
          type: "resume",
          last_commit_seq: Math.max(0, Math.floor(params.onOpenResumeCommitSeq)),
        });
      }
    };

    socket.onclose = () => {
      if (this.socket !== socket) {
        return;
      }
      this.emitStatus("disconnected");
      this.socket = null;
      this.connectionKey = "";
      if (!this.closedByUser) {
        this.scheduleReconnect();
      }
    };
    socket.onerror = () => {
      if (this.socket === socket) {
        this.emitStatus("error");
      }
    };
    socket.onmessage = (event) => {
      if (this.socket !== socket) {
        return;
      }
      try {
        const parsed = JSON.parse(String(event.data)) as InboundMessage;
        if (parsed.type === "error" && parsed.payload?.retryable === false) {
          this.closedByUser = true;
          this.lastConnectParams = null;
          this.emitStatus("error");
        }
        this.onMessageHandlers.forEach((handler) => handler(parsed));
      } catch {
        this.emitStatus("error");
      }
    };
  }

  disconnect(): void {
    this.closedByUser = true;
    this.clearReconnectTimer();
    this.lastConnectParams = null;
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.connectionKey = "";
    this.reconnectAttempt = 0;
  }

  send(message: OutboundMessage): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.socket.send(JSON.stringify(message));
    return true;
  }

  requestResume(lastCommitSeq: number): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    return this.send({ type: "resume", last_commit_seq: Math.max(0, Math.floor(lastCommitSeq)) });
  }

  updateResumeCommitSeq(lastCommitSeq: number): void {
    if (!this.lastConnectParams) {
      return;
    }
    this.lastConnectParams = {
      ...this.lastConnectParams,
      onOpenResumeCommitSeq: Math.max(0, Math.floor(lastCommitSeq)),
    };
  }

  onMessage(handler: (message: InboundMessage) => void): () => void {
    this.onMessageHandlers.push(handler);
    return () => {
      this.onMessageHandlers = this.onMessageHandlers.filter((h) => h !== handler);
    };
  }

  onStatus(handler: (status: ConnectionStatus) => void): () => void {
    this.onStatusHandlers.push(handler);
    return () => {
      this.onStatusHandlers = this.onStatusHandlers.filter((h) => h !== handler);
    };
  }

  private emitStatus(status: ConnectionStatus): void {
    this.onStatusHandlers.forEach((handler) => handler(status));
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null || !this.lastConnectParams) {
      return;
    }
    const base = Math.min(1000 * 2 ** this.reconnectAttempt, 10000);
    const jitter = Math.floor(Math.random() * 300);
    const delay = base + jitter;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectAttempt += 1;
      if (!this.closedByUser && this.lastConnectParams) {
        this.connect(this.lastConnectParams);
      }
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private buildSocketUrl(sessionId: string, tokenQuery: string): string {
    const fallbackOrigin =
      typeof window !== "undefined" &&
      typeof window.location?.origin === "string" &&
      window.location.origin.trim()
        ? window.location.origin
        : "http://127.0.0.1:9090";
    const rawBase = (this.baseUrl || fallbackOrigin).trim();
    const normalizedBase = rawBase.replace(/\/+$/, "");
    const base = /^https?:\/\//i.test(normalizedBase) ? normalizedBase : `http://${normalizedBase}`;
    const wsBase = base.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:");
    return `${wsBase}/api/v1/sessions/${encodeURIComponent(sessionId)}/stream${tokenQuery}`;
  }
}
