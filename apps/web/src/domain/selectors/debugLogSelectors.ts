import type { InboundMessage } from "../../core/contracts/stream";

export const DEBUG_TURN_SELECTION_LATEST = "__latest";
export const DEBUG_TURN_SELECTION_ALL = "__all";

export type DebugTurnMetadata = {
  round: number | null;
  turn: number | null;
};

export type DebugTurnGroup = DebugTurnMetadata & {
  key: string;
  label: string;
  messages: InboundMessage[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function debugPayloadRecord(message: InboundMessage): Record<string, unknown> | null {
  return isRecord(message.payload) ? message.payload : null;
}

function nestedRecord(root: Record<string, unknown> | null, key: string): Record<string, unknown> | null {
  if (!root) {
    return null;
  }
  const value = root[key];
  return isRecord(value) ? value : null;
}

export function debugTurnMetadata(message: InboundMessage): DebugTurnMetadata {
  const payload = debugPayloadRecord(message);
  const publicContext = nestedRecord(payload, "public_context");
  const viewState = nestedRecord(payload, "view_state");
  const turnStage = nestedRecord(viewState, "turn_stage");
  const situation = nestedRecord(viewState, "situation");
  return {
    round:
      numberOrNull(payload?.["round_index"]) ??
      numberOrNull(publicContext?.["round_index"]) ??
      numberOrNull(turnStage?.["round_index"]) ??
      numberOrNull(situation?.["round_index"]),
    turn:
      numberOrNull(payload?.["turn_index"]) ??
      numberOrNull(publicContext?.["turn_index"]) ??
      numberOrNull(turnStage?.["turn_index"]) ??
      numberOrNull(situation?.["turn_index"]),
  };
}

function debugTurnLabel(metadata: DebugTurnMetadata, locale: string): string | null {
  if (metadata.round !== null && metadata.turn !== null) {
    return locale === "ko" ? `${metadata.round}라운드 / ${metadata.turn}턴` : `Round ${metadata.round} / Turn ${metadata.turn}`;
  }
  if (metadata.round !== null) {
    return locale === "ko" ? `${metadata.round}라운드 / 턴 정보 없음` : `Round ${metadata.round} / No turn`;
  }
  if (metadata.turn !== null) {
    return locale === "ko" ? `${metadata.turn}턴` : `Turn ${metadata.turn}`;
  }
  return null;
}

function debugTurnGroupKey(metadata: DebugTurnMetadata, label: string, index: number, firstSeq: number): string {
  const roundKey = metadata.round === null ? "unknown-round" : `r${metadata.round}`;
  const turnKey = metadata.turn === null ? "unknown-turn" : `t${metadata.turn}`;
  return `${roundKey}:${turnKey}:${index}:${label}:${firstSeq}`;
}

export function groupDebugMessagesByTurn(messages: InboundMessage[], locale: string): DebugTurnGroup[] {
  const fallbackLabel = locale === "ko" ? "턴 정보 없음" : "No turn metadata";
  const groups: DebugTurnGroup[] = [];
  let current: DebugTurnGroup | null = null;
  const sortedMessages = [...messages].sort((left, right) => {
    const seqDiff = left.seq - right.seq;
    if (seqDiff !== 0) {
      return seqDiff;
    }
    return (left.server_time_ms ?? 0) - (right.server_time_ms ?? 0);
  });

  for (const message of sortedMessages) {
    const metadata = debugTurnMetadata(message);
    const label = debugTurnLabel(metadata, locale);
    const payload = debugPayloadRecord(message);
    const eventType = typeof payload?.["event_type"] === "string" ? payload["event_type"] : "";
    const startsTurn = eventType === "turn_start" || eventType === "turn_context_started";
    const groupLabel = label ?? fallbackLabel;
    if (!current || (label && (startsTurn || current.label !== label))) {
      current = {
        key: debugTurnGroupKey(metadata, groupLabel, groups.length, message.seq),
        label: groupLabel,
        round: metadata.round,
        turn: metadata.turn,
        messages: [],
      };
      groups.push(current);
    }
    current.messages.push(message);
  }

  return groups;
}

export function selectDebugMessagesForTurn(
  messages: InboundMessage[],
  groups: DebugTurnGroup[],
  selectionKey: string
): InboundMessage[] {
  if (selectionKey === DEBUG_TURN_SELECTION_ALL) {
    return messages;
  }
  const selectedGroup =
    selectionKey === DEBUG_TURN_SELECTION_LATEST
      ? groups[groups.length - 1]
      : groups.find((group) => group.key === selectionKey) ?? groups[groups.length - 1];
  return selectedGroup ? selectedGroup.messages : messages;
}
