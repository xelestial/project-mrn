import type { ConnectionStatus, InboundMessage } from "../../core/contracts/stream";

export type GameStreamState = {
  status: ConnectionStatus;
  lastSeq: number;
  messages: InboundMessage[];
};

export type GameStreamAction =
  | { type: "status"; status: ConnectionStatus }
  | { type: "message"; message: InboundMessage }
  | { type: "reset" };

export const initialGameStreamState: GameStreamState = {
  status: "idle",
  lastSeq: 0,
  messages: [],
};

export function gameStreamReducer(state: GameStreamState, action: GameStreamAction): GameStreamState {
  if (action.type === "reset") {
    return initialGameStreamState;
  }
  if (action.type === "status") {
    return { ...state, status: action.status };
  }
  const seq = typeof action.message.seq === "number" ? action.message.seq : state.lastSeq;
  return {
    ...state,
    lastSeq: seq,
    messages: [...state.messages.slice(-49), action.message],
  };
}

