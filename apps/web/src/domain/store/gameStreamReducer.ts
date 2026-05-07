import type { ConnectionStatus, InboundMessage, ViewCommitPayload } from "../../core/contracts/stream";

export type GameStreamState = {
  status: ConnectionStatus;
  latestCommit: ViewCommitPayload | null;
  lastCommitSeq: number;
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
  latestCommit: null,
  lastCommitSeq: 0,
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
  return withCappedMessages(nextMessages);
}

function isViewCommitCarrier(
  message: InboundMessage,
): message is Extract<InboundMessage, { type: "view_commit" | "snapshot_pulse" }> {
  return message.type === "view_commit" || message.type === "snapshot_pulse";
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
  if (!isViewCommitCarrier(action.message)) {
    return debugMessages === state.debugMessages ? state : { ...state, debugMessages };
  }

  const commitSeq = Number(action.message.payload.commit_seq);
  if (!Number.isFinite(commitSeq) || commitSeq <= 0) {
    return debugMessages === state.debugMessages ? state : { ...state, debugMessages };
  }
  const currentLiveCommit = state.messages.find((message) => message.type === "view_commit");
  const shouldRepairSameCommit =
    commitSeq === state.lastCommitSeq &&
    (state.latestCommit === null ||
      currentLiveCommit === undefined ||
      action.message.seq > currentLiveCommit.seq);
  if (commitSeq < state.lastCommitSeq || (commitSeq === state.lastCommitSeq && !shouldRepairSameCommit)) {
    return debugMessages === state.debugMessages ? state : { ...state, debugMessages };
  }

  const liveMessage =
    action.message.type === "snapshot_pulse"
      ? ({ ...action.message, type: "view_commit" } as Extract<InboundMessage, { type: "view_commit" }>)
      : action.message;
  return {
    ...state,
    latestCommit: action.message.payload,
    lastCommitSeq: commitSeq,
    lastSeq: commitSeq,
    messages: [liveMessage],
    debugMessages,
    pendingBySeq: {},
    manifestHash: null,
  };
}
