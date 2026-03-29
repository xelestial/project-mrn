import type { ConnectionStatus, InboundMessage } from "../../core/contracts/stream";

export type GameStreamState = {
  status: ConnectionStatus;
  lastSeq: number;
  messages: InboundMessage[];
  pendingBySeq: Record<number, InboundMessage>;
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
};

function withCappedMessages(messages: InboundMessage[]): InboundMessage[] {
  return messages.length <= 50 ? messages : messages.slice(messages.length - 50);
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
  const pendingBySeq: Record<number, InboundMessage> = { ...state.pendingBySeq, [seq]: action.message };
  let nextSeq = state.lastSeq;
  let nextMessages = [...state.messages];
  while (pendingBySeq[nextSeq + 1]) {
    const contiguous = pendingBySeq[nextSeq + 1];
    delete pendingBySeq[nextSeq + 1];
    nextMessages.push(contiguous);
    nextSeq += 1;
  }
  return {
    ...state,
    lastSeq: nextSeq,
    messages: withCappedMessages(nextMessages),
    pendingBySeq,
  };
}
