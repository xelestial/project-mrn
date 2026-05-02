import type { ConnectionStatus, InboundMessage } from "../../core/contracts/stream";

export type GameStreamState = {
  status: ConnectionStatus;
  lastSeq: number;
  messages: InboundMessage[];
  debugMessages: InboundMessage[];
  pendingBySeq: Record<number, InboundMessage>;
  manifestHash: string | null;
};

export type GameStreamAction =
  | { type: "status"; status: ConnectionStatus }
  | { type: "message"; message: InboundMessage }
  | { type: "reset" };

export const MAX_STREAM_MESSAGES = 400;

export const initialGameStreamState: GameStreamState = {
  status: "idle",
  lastSeq: 0,
  messages: [],
  debugMessages: [],
  pendingBySeq: {},
  manifestHash: null,
};

function withCappedMessages(messages: InboundMessage[]): InboundMessage[] {
  return messages.length <= MAX_STREAM_MESSAGES ? messages : messages.slice(messages.length - MAX_STREAM_MESSAGES);
}

function debugMessageKey(message: InboundMessage): string {
  return [
    message.session_id,
    message.seq,
    message.type,
    message.server_time_ms ?? "",
    JSON.stringify(message.payload),
  ].join(":");
}

function withDebugMessage(messages: InboundMessage[], message: InboundMessage): InboundMessage[] {
  const key = debugMessageKey(message);
  if (messages.some((existing) => debugMessageKey(existing) === key)) {
    return messages;
  }
  const nextMessages = [...messages, message];
  nextMessages.sort((left, right) => {
    const seqDiff = left.seq - right.seq;
    if (seqDiff !== 0) {
      return seqDiff;
    }
    return (left.server_time_ms ?? 0) - (right.server_time_ms ?? 0);
  });
  return nextMessages;
}

function sameStreamMessage(left: InboundMessage, right: InboundMessage): boolean {
  return debugMessageKey(left) === debugMessageKey(right);
}

function withOrderedReplayMessage(messages: InboundMessage[], message: InboundMessage): InboundMessage[] {
  const nextMessages = [...messages, message];
  nextMessages.sort((left, right) => {
    const seqDiff = left.seq - right.seq;
    if (seqDiff !== 0) {
      return seqDiff;
    }
    return (left.server_time_ms ?? 0) - (right.server_time_ms ?? 0);
  });
  return withCappedMessages(nextMessages);
}

function carriesCurrentProjection(message: InboundMessage): boolean {
  return message.type !== "heartbeat" && typeof message.payload === "object" && message.payload !== null && "view_state" in message.payload;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function runtimeFramePath(message: InboundMessage): string[] {
  const payload = message.payload;
  const viewState = isRecord(payload["view_state"]) ? payload["view_state"] : null;
  const viewRuntime = isRecord(viewState?.["runtime"]) ? viewState["runtime"] : null;
  const viewPath = stringArray(viewRuntime?.["latest_module_path"]);
  if (viewPath.length > 0) {
    return viewPath;
  }

  const runtimeModule = isRecord(payload["runtime_module"]) ? payload["runtime_module"] : null;
  const runtimeModulePath = stringArray(runtimeModule?.["module_path"]);
  if (runtimeModulePath.length > 0) {
    return runtimeModulePath;
  }

  const frameId = typeof runtimeModule?.["frame_id"] === "string" ? runtimeModule["frame_id"] : payload["frame_id"];
  const moduleId = typeof runtimeModule?.["module_id"] === "string" ? runtimeModule["module_id"] : payload["module_id"];
  return [frameId, moduleId].filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function onePathExtendsTheOther(left: string[], right: string[]): boolean {
  const sharedLength = Math.min(left.length, right.length);
  for (let index = 0; index < sharedLength; index += 1) {
    if (left[index] !== right[index]) {
      return false;
    }
  }
  return true;
}

function projectedMessageIsCompatibleWithLatest(messages: InboundMessage[], candidate: InboundMessage): boolean {
  const candidatePath = runtimeFramePath(candidate);
  if (candidatePath.length === 0) {
    return true;
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const latestPath = runtimeFramePath(messages[index]);
    if (latestPath.length === 0) {
      continue;
    }
    return onePathExtendsTheOther(candidatePath, latestPath);
  }
  return true;
}

function flushPendingMessages(
  startSeq: number,
  pendingBySeq: Record<number, InboundMessage>,
  messages: InboundMessage[],
  manifestHash: string | null
): { lastSeq: number; messages: InboundMessage[]; manifestHash: string | null } {
  let nextSeq = startSeq;
  let nextMessages = [...messages];
  let nextManifestHash = manifestHash;

  while (true) {
    const contiguous = pendingBySeq[nextSeq + 1];
    if (contiguous) {
      delete pendingBySeq[nextSeq + 1];
      nextMessages.push(contiguous);
      const contiguousManifestHash = extractManifestHash(contiguous);
      if (contiguousManifestHash) {
        nextManifestHash = contiguousManifestHash;
      }
      nextSeq += 1;
      continue;
    }

    const pendingSeqs = Object.keys(pendingBySeq)
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > nextSeq)
      .sort((left, right) => left - right);
    if (pendingSeqs.length === 0) {
      break;
    }

    const firstProjectedSeq = pendingSeqs.find((seq) => {
      const candidate = pendingBySeq[seq];
      return Boolean(
        candidate &&
          (carriesCurrentProjection(candidate) || candidate.type === "prompt") &&
          projectedMessageIsCompatibleWithLatest(nextMessages, candidate)
      );
    });
    if (firstProjectedSeq === undefined) {
      break;
    }

    for (const pendingSeq of pendingSeqs) {
      if (pendingSeq >= firstProjectedSeq) {
        break;
      }
      delete pendingBySeq[pendingSeq];
    }

    const projected = pendingBySeq[firstProjectedSeq];
    if (!projected) {
      break;
    }
    delete pendingBySeq[firstProjectedSeq];
    nextMessages.push(projected);
    const fastForwardManifestHash = extractManifestHash(projected);
    if (fastForwardManifestHash) {
      nextManifestHash = fastForwardManifestHash;
    }
    nextSeq = firstProjectedSeq;
  }

  return {
    lastSeq: nextSeq,
    messages: nextMessages,
    manifestHash: nextManifestHash,
  };
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
  if (action.message.type === "heartbeat") {
    return state;
  }
  const debugMessages = withDebugMessage(state.debugMessages, action.message);
  const seq = typeof action.message.seq === "number" ? action.message.seq : state.lastSeq;
  if (!Number.isFinite(seq) || seq <= state.lastSeq) {
    if (
      Number.isFinite(seq) &&
      carriesCurrentProjection(action.message) &&
      !state.messages.some((message) => sameStreamMessage(message, action.message))
    ) {
      const messages =
        seq < state.lastSeq
          ? withOrderedReplayMessage(state.messages, action.message)
          : withCappedMessages([...state.messages, action.message]);
      return {
        ...state,
        messages,
        debugMessages,
      };
    }
    return debugMessages === state.debugMessages ? state : { ...state, debugMessages };
  }
  const incomingManifestHash = extractManifestHash(action.message);
  if (incomingManifestHash && state.manifestHash && incomingManifestHash !== state.manifestHash) {
    return {
      ...state,
      lastSeq: seq,
      messages: [action.message],
      debugMessages,
      pendingBySeq: {},
      manifestHash: incomingManifestHash,
    };
  }
  const pendingBySeq: Record<number, InboundMessage> = { ...state.pendingBySeq, [seq]: action.message };
  const flushed = flushPendingMessages(state.lastSeq, pendingBySeq, state.messages, state.manifestHash);
  return {
    ...state,
    lastSeq: flushed.lastSeq,
    messages: withCappedMessages(flushed.messages),
    debugMessages,
    pendingBySeq,
    manifestHash: flushed.manifestHash,
  };
}
