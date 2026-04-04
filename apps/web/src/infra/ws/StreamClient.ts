import type { ConnectionStatus, InboundMessage, OutboundMessage } from "../../core/contracts/stream";

export class StreamClient {
  private socket: WebSocket | null = null;
  private onMessageHandlers: Array<(message: InboundMessage) => void> = [];
  private onStatusHandlers: Array<(status: ConnectionStatus) => void> = [];
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private closedByUser = false;
  private lastConnectParams: { sessionId: string; token?: string; onOpenResumeSeq?: number } | null = null;

  connect(params: { sessionId: string; token?: string; onOpenResumeSeq?: number }): void {
    this.closedByUser = false;
    this.lastConnectParams = params;
    this.clearReconnectTimer();
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.onerror = null;
      this.socket.onmessage = null;
      this.socket.close();
      this.socket = null;
    }
    this.emitStatus("connecting");
    const tokenQuery = params.token ? `?token=${encodeURIComponent(params.token)}` : "";
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const url = `${protocol}://${host}/api/v1/sessions/${encodeURIComponent(params.sessionId)}/stream${tokenQuery}`;
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.emitStatus("connected");
      if (typeof params.onOpenResumeSeq === "number" && params.onOpenResumeSeq >= 0) {
        this.send({ type: "resume", last_seq: params.onOpenResumeSeq });
      }
    };

    this.socket.onclose = () => {
      this.emitStatus("disconnected");
      this.socket = null;
      if (!this.closedByUser) {
        this.scheduleReconnect();
      }
    };
    this.socket.onerror = () => this.emitStatus("error");
    this.socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(String(event.data)) as InboundMessage;
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
    this.reconnectAttempt = 0;
  }

  send(message: OutboundMessage): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.socket.send(JSON.stringify(message));
    return true;
  }

  requestResume(lastSeq: number): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    return this.send({ type: "resume", last_seq: Math.max(0, Math.floor(lastSeq)) });
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
}
