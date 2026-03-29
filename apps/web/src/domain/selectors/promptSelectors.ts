import type { InboundMessage } from "../../core/contracts/stream";

export type PromptChoiceViewModel = {
  choiceId: string;
  title: string;
  description: string;
};

export type PromptViewModel = {
  requestId: string;
  requestType: string;
  playerId: number;
  timeoutMs: number;
  choices: PromptChoiceViewModel[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function parseChoices(raw: unknown): PromptChoiceViewModel[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) => {
      if (!isRecord(item)) {
        return null;
      }
      const choiceId = item["choice_id"];
      if (typeof choiceId !== "string" || !choiceId.trim()) {
        return null;
      }
      return {
        choiceId,
        title: typeof item["title"] === "string" ? item["title"] : choiceId,
        description: typeof item["description"] === "string" ? item["description"] : "",
      };
    })
    .filter((item): item is PromptChoiceViewModel => item !== null);
}

export function selectActivePrompt(messages: InboundMessage[]): PromptViewModel | null {
  let promptMessage: InboundMessage | null = null;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type === "prompt") {
      promptMessage = messages[i];
      break;
    }
  }
  if (!promptMessage) {
    return null;
  }

  const requestId = promptMessage.payload["request_id"];
  if (typeof requestId !== "string" || !requestId.trim()) {
    return null;
  }

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "decision_ack") {
      continue;
    }
    if (message.payload["request_id"] !== requestId) {
      continue;
    }
    const status = message.payload["status"];
    if (status === "accepted" || status === "stale") {
      return null;
    }
    break;
  }

  const playerId = promptMessage.payload["player_id"];
  return {
    requestId,
    requestType:
      typeof promptMessage.payload["request_type"] === "string" ? String(promptMessage.payload["request_type"]) : "-",
    playerId: typeof playerId === "number" ? playerId : 0,
    timeoutMs: typeof promptMessage.payload["timeout_ms"] === "number" ? promptMessage.payload["timeout_ms"] : 30000,
    choices: parseChoices(promptMessage.payload["choices"]),
  };
}

