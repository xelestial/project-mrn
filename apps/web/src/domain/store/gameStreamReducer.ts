import type { ConnectionStatus, InboundMessage } from "../../core/contracts/stream";

export type GameStreamState = {
  status: ConnectionStatus;
  lastSeq: number;
  messages: InboundMessage[];
  pendingBySeq: Record<number, InboundMessage>;
  manifestHash: string | null;
};

export type GameStreamAction =
  | { type: "status"; status: ConnectionStatus }
  | { type: "message"; message: InboundMessage }
  | { type: "reset" };

export const initialGameStreamState: GameStreamState = {
  status: "idle",
  lastSeq: 0,
  messages: [],
  pendingBySeq: {},
  manifestHash: null,
};

function withCappedMessages(messages: InboundMessage[]): InboundMessage[] {
  return messages.length <= 400 ? messages : messages.slice(messages.length - 400);
}

function extractManifestHash(message: InboundMessage): string | null {
  if (message.type !== "event") {
    return null;
  }
  const payload = message.payload as Record<string, unknown>;
  const eventType = payload["event_type"];
  if (eventType !== "parameter_manifest") {
    return null;
  }
  const manifest = payload["parameter_manifest"];
  if (manifest && typeof manifest === "object") {
    const nestedHash = (manifest as Record<string, unknown>)["manifest_hash"];
    if (typeof nestedHash === "string" && nestedHash.trim()) {
      return nestedHash;
    }
  }
  const hash = payload["manifest_hash"];
  if (typeof hash !== "string" || !hash.trim()) {
    return null;
  }
  return hash;
}

export function gameStreamReducer(state: GameStreamState, action: GameStreamAction): GameStreamState {
  if (action.type === "reset") {
    return initialGameStreamState;
  }
  if (action.type === "status") {
    return { ...state, status: action.status };
  }
  const seq = typeof action.message.seq === "number" ? action.message.seq : state.lastSeq;
  if (!Number.isFinite(seq) || seq <= state.lastSeq) {
    return state;
  }
  const incomingManifestHash = extractManifestHash(action.message);
  if (incomingManifestHash && state.manifestHash && incomingManifestHash !== state.manifestHash) {
    return {
      ...state,
      lastSeq: seq,
      messages: [action.message],
      pendingBySeq: {},
      manifestHash: incomingManifestHash,
    };
  }
  const pendingBySeq: Record<number, InboundMessage> = { ...state.pendingBySeq, [seq]: action.message };
  let nextSeq = state.lastSeq;
  let nextMessages = [...state.messages];
  let nextManifestHash = state.manifestHash;
  while (pendingBySeq[nextSeq + 1]) {
    const contiguous = pendingBySeq[nextSeq + 1];
    delete pendingBySeq[nextSeq + 1];
    nextMessages.push(contiguous);
    const manifestHash = extractManifestHash(contiguous);
    if (manifestHash) {
      nextManifestHash = manifestHash;
    }
    nextSeq += 1;
  }
  return {
    ...state,
    lastSeq: nextSeq,
    messages: withCappedMessages(nextMessages),
    pendingBySeq,
    manifestHash: nextManifestHash,
  };
}
