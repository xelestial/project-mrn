import type { InboundMessage } from "../../core/contracts/stream";

export type PromptChoiceViewModel = {
  choiceId: string;
  title: string;
  description: string;
  value: Record<string, unknown> | null;
};

export type PromptViewModel = {
  requestId: string;
  requestType: string;
  playerId: number;
  timeoutMs: number;
  choices: PromptChoiceViewModel[];
  publicContext: Record<string, unknown>;
};

export type DecisionAckViewModel = {
  status: "accepted" | "rejected" | "stale";
  reason: string;
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
      const value = isRecord(item["value"]) ? { ...item["value"] } : null;
      const valueDescription = value && typeof value["card_description"] === "string" ? String(value["card_description"]) : "";
      const titleRaw = item["title"] ?? item["label"];
      return {
        choiceId,
        title: typeof titleRaw === "string" && titleRaw.trim() ? String(titleRaw) : choiceId,
        description:
          typeof item["description"] === "string" && item["description"].trim() ? String(item["description"]) : valueDescription,
        value,
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
    if (message.type === "decision_ack") {
      if (message.payload["request_id"] !== requestId) {
        continue;
      }
      const status = message.payload["status"];
      if (status === "accepted" || status === "stale") {
        return null;
      }
      break;
    }
    if (message.type !== "event") {
      continue;
    }
    if (message.payload["request_id"] !== requestId) {
      continue;
    }
    const eventType = message.payload["event_type"];
    if (eventType === "decision_resolved" || eventType === "decision_timeout_fallback") {
      return null;
    }
  }

  const playerId = promptMessage.payload["player_id"];
  return {
    requestId,
    requestType:
      typeof promptMessage.payload["request_type"] === "string" ? String(promptMessage.payload["request_type"]) : "-",
    playerId: typeof playerId === "number" ? playerId : 0,
    timeoutMs: typeof promptMessage.payload["timeout_ms"] === "number" ? promptMessage.payload["timeout_ms"] : 30000,
    choices: parseChoices(promptMessage.payload["choices"] ?? promptMessage.payload["legal_choices"]),
    publicContext: isRecord(promptMessage.payload["public_context"]) ? { ...promptMessage.payload["public_context"] } : {},
  };
}

export function selectLatestDecisionAck(messages: InboundMessage[], requestId: string): DecisionAckViewModel | null {
  if (!requestId.trim()) {
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
    if (status !== "accepted" && status !== "rejected" && status !== "stale") {
      return null;
    }
    return {
      status,
      reason: typeof message.payload["reason"] === "string" ? message.payload["reason"] : "",
    };
  }
  return null;
}
