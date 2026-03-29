import type { ConnectionStatus, InboundMessage, OutboundMessage } from "../../core/contracts/stream";

export class StreamClient {
  private socket: WebSocket | null = null;
  private onMessageHandlers: Array<(message: InboundMessage) => void> = [];
  private onStatusHandlers: Array<(status: ConnectionStatus) => void> = [];

  connect(params: { sessionId: string; token?: string; onOpenResumeSeq?: number }): void {
    this.disconnect();
    this.emitStatus("connecting");
    const tokenQuery = params.token ? `?token=${encodeURIComponent(params.token)}` : "";
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const url = `${protocol}://${host}/api/v1/sessions/${encodeURIComponent(params.sessionId)}/stream${tokenQuery}`;
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      this.emitStatus("connected");
      if (typeof params.onOpenResumeSeq === "number" && params.onOpenResumeSeq >= 0) {
        this.send({ type: "resume", last_seq: params.onOpenResumeSeq });
      }
    };

    this.socket.onclose = () => this.emitStatus("disconnected");
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
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  send(message: OutboundMessage): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(JSON.stringify(message));
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
}

